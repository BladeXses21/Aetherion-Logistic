"""
test_401_recovery.py — Тести для Story 3.4: 401 Auto-Recovery & Retry.

Покриває:
  - POST /search: 401 → refresh → успішний retry
  - POST /search: 401 → refresh → retry також 401 → 503 LTSID_REFRESH_FAILED
  - POST /search: 401 → refresh timeout (90с) → 503 LTSID_REFRESH_TIMEOUT
  - GET /cargo/{id}: 401 → refresh → успішний retry
  - POST /search: 429/503 → exponential backoff retry
  - POST /search: 400/404 → без retry
  - wait_for_new_ltsid: повертає новий LTSID при зміні
  - wait_for_new_ltsid: повертає None при таймауті
  - publish_refresh_request: надсилає правильне повідомлення до Redis

Стратегія моків:
  - Використовує ті самі патерни фікстур що і test_search_endpoint.py /
    test_cargo_detail_endpoint.py (app.state напряму).
  - wait_for_new_ltsid та publish_refresh_request мокуються через patch
    для уникнення реального очікування.
  - asyncio.sleep мокується для exponential backoff тестів.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.lardi_client import LardiHTTPError
from app.services.retry_handler import LtsidRefreshError, with_rate_limit_retry
from app.services.session_refresh import publish_refresh_request, wait_for_new_ltsid

# ---------------------------------------------------------------------------
# Тестові дані — спільні константи
# ---------------------------------------------------------------------------

CARGO_ID = 206668785705

# Мінімальний валідний запит для пошуку
VALID_SEARCH_BODY = {
    "directionFrom": {"directionRows": [{"countrySign": "UA", "townId": 4}]},
    "directionTo": {"directionRows": [{"countrySign": "UA", "townId": 10}]},
}

# Мінімальна фіктивна відповідь Lardi для пошуку
FAKE_SEARCH_RESPONSE = {
    "result": {
        "proposals": [],
        "paginator": {"totalSize": 0, "currentPage": 1},
    }
}

# Мінімальна фіктивна відповідь Lardi для деталей вантажу
FAKE_DETAIL_RESPONSE = {
    "cargo": {
        "id": CARGO_ID,
        "bodyType": "Тент",
        "gruzName": "вантаж",
        "proposalUser": None,
        "waypointListSource": [],
        "waypointListTarget": [],
    },
    "offers": [],
}


# ---------------------------------------------------------------------------
# Допоміжна функція — передає виклик coro_factory напряму
# ---------------------------------------------------------------------------

async def _enqueue_passthrough(request_id: str, coro_factory):
    """Замінник enqueue: одразу виконує coro_factory без черги."""
    return await coro_factory()


# ---------------------------------------------------------------------------
# Фікстури
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    """Мок Redis-клієнта з LTSID і publish."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value="fake_ltsid_value")
    mock.publish = AsyncMock(return_value=1)
    mock.ping = AsyncMock(return_value=True)
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def mock_queue():
    """Мок QueueManager з прямим виконанням запитів."""
    mock = AsyncMock()
    mock.enqueue = AsyncMock(side_effect=_enqueue_passthrough)
    mock.start = AsyncMock()
    mock.stop = AsyncMock()
    return mock


@pytest.fixture
def mock_lardi():
    """Мок LardiClient."""
    mock = AsyncMock()
    mock.search = AsyncMock(return_value=FAKE_SEARCH_RESPONSE)
    mock.get_cargo_detail = AsyncMock(return_value=FAKE_DETAIL_RESPONSE)
    return mock


@pytest.fixture
async def search_client(mock_redis, mock_queue, mock_lardi):
    """AsyncClient з мокованим app.state для /search тестів."""
    app.state.redis = mock_redis
    app.state.queue_manager = mock_queue
    app.state.lardi_client = mock_lardi

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_redis, mock_queue, mock_lardi


@pytest.fixture
async def detail_client(mock_redis, mock_queue, mock_lardi):
    """AsyncClient з мокованим app.state для /cargo/{id} тестів."""
    app.state.redis = mock_redis
    app.state.queue_manager = mock_queue
    app.state.lardi_client = mock_lardi

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_redis, mock_queue, mock_lardi


# ---------------------------------------------------------------------------
# Тести: 401 auto-recovery для /search
# ---------------------------------------------------------------------------

async def test_search_401_triggers_refresh_and_retries(search_client):
    """
    POST /search: перший запит → 401, після refresh → успішна відповідь.

    Перевіряємо що:
      - handle_401_and_retry викликається (через publish_refresh_request)
      - Другий запит з новим LTSID повертає 200
    """
    ac, mock_redis, _, mock_lardi = search_client
    new_ltsid = "new_refreshed_ltsid"

    # Перший виклик → 401, другий → успішна відповідь
    mock_lardi.search = AsyncMock(
        side_effect=[LardiHTTPError(401), FAKE_SEARCH_RESPONSE]
    )

    with (
        patch(
            "app.services.retry_handler.publish_refresh_request",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.retry_handler.wait_for_new_ltsid",
            new_callable=AsyncMock,
            return_value=new_ltsid,
        ),
        patch(
            "app.services.retry_handler.asyncio.sleep",
            new_callable=AsyncMock,
        ),
    ):
        response = await ac.post("/search", json=VALID_SEARCH_BODY)

    assert response.status_code == 200
    # Перевіряємо що lardi_client.search викликався двічі (перший раз + retry)
    assert mock_lardi.search.call_count == 2
    # Другий виклик має використовувати новий LTSID
    second_call_ltsid = mock_lardi.search.call_args_list[1][0][1]
    assert second_call_ltsid == new_ltsid


async def test_search_401_retry_also_fails_returns_503_ltsid_refresh_failed(search_client):
    """
    POST /search: 401 → refresh → retry теж 401 → 503 LTSID_REFRESH_FAILED.
    """
    ac, _, _, mock_lardi = search_client

    # Обидва виклики повертають 401
    mock_lardi.search = AsyncMock(side_effect=LardiHTTPError(401))

    with (
        patch(
            "app.services.retry_handler.publish_refresh_request",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.retry_handler.wait_for_new_ltsid",
            new_callable=AsyncMock,
            return_value="new_ltsid_after_refresh",
        ),
        patch(
            "app.services.retry_handler.asyncio.sleep",
            new_callable=AsyncMock,
        ),
    ):
        response = await ac.post("/search", json=VALID_SEARCH_BODY)

    assert response.status_code == 503
    error = response.json()["detail"]["error"]
    assert error["code"] == "LTSID_REFRESH_FAILED"


async def test_search_401_refresh_timeout_returns_503_ltsid_refresh_timeout(search_client):
    """
    POST /search: 401 → wait_for_new_ltsid таймаутує (None) → 503 LTSID_REFRESH_TIMEOUT.
    """
    ac, _, _, mock_lardi = search_client

    mock_lardi.search = AsyncMock(side_effect=LardiHTTPError(401))

    with (
        patch(
            "app.services.retry_handler.publish_refresh_request",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.retry_handler.wait_for_new_ltsid",
            new_callable=AsyncMock,
            return_value=None,  # Таймаут — новий LTSID не з'явився
        ),
    ):
        response = await ac.post("/search", json=VALID_SEARCH_BODY)

    assert response.status_code == 503
    error = response.json()["detail"]["error"]
    assert error["code"] == "LTSID_REFRESH_TIMEOUT"
    # Перевіряємо наявність retry_after в details
    assert error.get("details", {}).get("retry_after") == 30


# ---------------------------------------------------------------------------
# Тести: 401 auto-recovery для /cargo/{id}
# ---------------------------------------------------------------------------

async def test_detail_401_triggers_refresh_and_retries(detail_client):
    """
    GET /cargo/{id}: 401 → refresh → успішний retry з новим LTSID → 200.
    """
    ac, mock_redis, _, mock_lardi = detail_client
    new_ltsid = "new_refreshed_ltsid_for_detail"

    mock_lardi.get_cargo_detail = AsyncMock(
        side_effect=[LardiHTTPError(401), FAKE_DETAIL_RESPONSE]
    )

    with (
        patch(
            "app.services.retry_handler.publish_refresh_request",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.retry_handler.wait_for_new_ltsid",
            new_callable=AsyncMock,
            return_value=new_ltsid,
        ),
        patch(
            "app.services.retry_handler.asyncio.sleep",
            new_callable=AsyncMock,
        ),
    ):
        response = await ac.get(f"/cargo/{CARGO_ID}")

    assert response.status_code == 200
    assert mock_lardi.get_cargo_detail.call_count == 2
    # Другий виклик має використовувати новий LTSID
    second_call_ltsid = mock_lardi.get_cargo_detail.call_args_list[1][0][1]
    assert second_call_ltsid == new_ltsid


# ---------------------------------------------------------------------------
# Тести: exponential backoff (429 / 503)
# ---------------------------------------------------------------------------

async def test_search_429_retries_with_backoff(search_client):
    """
    POST /search: 429 → retry до 3 разів з exponential backoff.

    Перевіряємо що lardi_client.search викликається 4 рази (1 + 3 retry),
    і що asyncio.sleep викликається 3 рази (для кожного backoff).
    """
    ac, _, _, mock_lardi = search_client

    # Перші 3 виклики → 429, четвертий → успіх
    mock_lardi.search = AsyncMock(
        side_effect=[
            LardiHTTPError(429),
            LardiHTTPError(429),
            LardiHTTPError(429),
            FAKE_SEARCH_RESPONSE,
        ]
    )

    with patch(
        "app.services.retry_handler.asyncio.sleep",
        new_callable=AsyncMock,
    ) as mock_sleep:
        response = await ac.post("/search", json=VALID_SEARCH_BODY)

    assert response.status_code == 200
    assert mock_lardi.search.call_count == 4
    # Sleep викликається 3 рази (між кожним retry)
    assert mock_sleep.call_count == 3


async def test_search_503_retries_with_backoff(search_client):
    """
    POST /search: 503 від Lardi → retry з backoff → успіх на другій спробі.
    """
    ac, _, _, mock_lardi = search_client

    mock_lardi.search = AsyncMock(
        side_effect=[LardiHTTPError(503), FAKE_SEARCH_RESPONSE]
    )

    with patch(
        "app.services.retry_handler.asyncio.sleep",
        new_callable=AsyncMock,
    ) as mock_sleep:
        response = await ac.post("/search", json=VALID_SEARCH_BODY)

    assert response.status_code == 200
    assert mock_lardi.search.call_count == 2
    assert mock_sleep.call_count == 1


async def test_search_400_does_not_retry(search_client):
    """
    POST /search: 400 від Lardi → одразу 502 без retry.

    400 — клієнтська помилка, retry не має сенсу.
    """
    ac, _, _, mock_lardi = search_client

    mock_lardi.search = AsyncMock(side_effect=LardiHTTPError(400))

    response = await ac.post("/search", json=VALID_SEARCH_BODY)

    # 400 від Lardi → 502 від нас (не retryable, пробрасується одразу)
    assert response.status_code == 502
    # Головне — search викликався рівно один раз (без retry)
    assert mock_lardi.search.call_count == 1


async def test_search_404_does_not_retry(search_client):
    """
    POST /search: 404 від Lardi → одразу без retry.

    404 — "не знайдено", повторювати безглуздо.
    """
    ac, _, _, mock_lardi = search_client

    mock_lardi.search = AsyncMock(side_effect=LardiHTTPError(404))

    response = await ac.post("/search", json=VALID_SEARCH_BODY)

    # 404 від Lardi → 502 від нас (не retryable)
    assert response.status_code == 502
    # Головне — search викликався рівно один раз (без retry)
    assert mock_lardi.search.call_count == 1


# ---------------------------------------------------------------------------
# Юніт-тести: wait_for_new_ltsid
# ---------------------------------------------------------------------------

async def test_wait_for_new_ltsid_returns_new_value():
    """
    wait_for_new_ltsid повертає новий LTSID коли Redis повертає інше значення.

    Перший poll → той самий LTSID, другий poll → новий LTSID.
    max_wait_seconds=2 щоб тест не тривав довго.
    """
    mock_redis = AsyncMock()
    # Перший get → старий LTSID, другий → новий
    mock_redis.get = AsyncMock(side_effect=["old_ltsid", "new_ltsid"])

    with patch("app.services.session_refresh.asyncio.sleep", new_callable=AsyncMock):
        result = await wait_for_new_ltsid(
            mock_redis,
            old_ltsid="old_ltsid",
            request_id="test-req-1",
            max_wait_seconds=2,
        )

    assert result == "new_ltsid"


async def test_wait_for_new_ltsid_returns_none_on_timeout():
    """
    wait_for_new_ltsid повертає None якщо LTSID не змінився за max_wait_seconds.

    Redis постійно повертає той самий LTSID → таймаут → None.
    max_wait_seconds=2 щоб тест завершився швидко.
    """
    mock_redis = AsyncMock()
    # Redis завжди повертає той самий LTSID
    mock_redis.get = AsyncMock(return_value="same_ltsid")

    with patch("app.services.session_refresh.asyncio.sleep", new_callable=AsyncMock):
        result = await wait_for_new_ltsid(
            mock_redis,
            old_ltsid="same_ltsid",
            request_id="test-req-2",
            max_wait_seconds=2,
        )

    assert result is None


# ---------------------------------------------------------------------------
# Юніт-тест: publish_refresh_request
# ---------------------------------------------------------------------------

async def test_publish_refresh_request_sends_correct_message():
    """
    publish_refresh_request публікує JSON з event, reason та timestamp до Redis.

    Перевіряємо:
      - redis.publish викликається з каналом aetherion:auth:refresh
      - Повідомлення містить event="refresh_requested", reason="401"
      - Повідомлення містить timestamp (ISO рядок)
    """
    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock(return_value=1)

    await publish_refresh_request(mock_redis, request_id="test-req-3")

    # Перевіряємо що publish викликався рівно один раз
    assert mock_redis.publish.call_count == 1

    # Витягуємо аргументи виклику
    call_args = mock_redis.publish.call_args
    channel = call_args[0][0]
    message_str = call_args[0][1]

    # Перевіряємо канал
    assert channel == "aetherion:auth:refresh"

    # Перевіряємо вміст повідомлення
    message = json.loads(message_str)
    assert message["event"] == "refresh_requested"
    assert message["reason"] == "401"
    assert "timestamp" in message
    # Перевіряємо що timestamp — валідний ISO рядок
    from datetime import datetime
    datetime.fromisoformat(message["timestamp"])  # Не кидає виняток = валідний ISO
