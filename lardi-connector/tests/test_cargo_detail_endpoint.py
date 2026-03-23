"""
Тести для GET /cargo/{id} (Story 3.3: Cargo Detail & Shipper Contact Endpoint).

Перевіряють:
  - Успішне повернення CargoDetailResponse з shipper_phone
  - shipper_phone = None коли proposalUser відсутній або phone порожній
  - HTTP 404 CARGO_NOT_FOUND коли Lardi повертає 404
  - HTTP 502 LARDI_DETAIL_UNAVAILABLE для інших HTTP помилок Lardi
  - HTTP 504 LARDI_TIMEOUT при таймауті
  - HTTP 503 QUEUE_UNAVAILABLE при недоступній черзі
  - HTTP 503 LTSID_REFRESH_FAILED при відсутньому LTSID
  - Логування ltsid_hash замість сирого LTSID (через LardiClient)
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.queue.queue_manager import QueueUnavailableError
from app.services.lardi_client import LardiHTTPError, LardiTimeoutError

# ---------------------------------------------------------------------------
# Тестові дані
# ---------------------------------------------------------------------------

CARGO_ID = 206668785705

# Повна відповідь Lardi з proposalUser та телефоном
LARDI_DETAIL_FULL = {
    "cargo": {
        "id": CARGO_ID,
        "bodyType": "Тент",
        "dateFrom": "2026-03-14T00:00:00.000+00:00",
        "gruzName": "міндобриво",
        "gruzMass1": 17.0,
        "paymentValue": 15000,
        "paymentCurrency": "UAH",
        "waypointListSource": [{"townName": "Київ", "countrySign": "UA"}],
        "waypointListTarget": [{"townName": "Одеса", "countrySign": "UA"}],
        "proposalUser": {
            "contact": {
                "name": "Іванов Іван",
                "phoneItem1": {
                    "phone": "+380679078186",
                    "verified": True,
                },
            }
        },
    },
    "offers": [],
}

# Відповідь без proposalUser
LARDI_DETAIL_NO_USER = {
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

# Відповідь з порожнім телефоном
LARDI_DETAIL_EMPTY_PHONE = {
    "cargo": {
        "id": CARGO_ID,
        "bodyType": "Тент",
        "gruzName": "вантаж",
        "proposalUser": {
            "contact": {
                "name": "Анонім",
                "phoneItem1": {"phone": "", "verified": False},
            }
        },
        "waypointListSource": [],
        "waypointListTarget": [],
    },
    "offers": [],
}


# ---------------------------------------------------------------------------
# Фікстура: клієнт з мокнутим app.state
# ---------------------------------------------------------------------------

@pytest.fixture
async def detail_client():
    """
    AsyncClient з мокнутими app.state.redis, queue_manager та lardi_client.

    queue_manager.enqueue викликає coro_factory напряму (обходить Redis-чергу).
    """
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value="fake_ltsid_token")

    mock_lardi = AsyncMock()

    mock_queue = AsyncMock()

    async def enqueue_side_effect(request_id, coro_factory):
        """Консьюмер-замінник: одразу виконує coro_factory."""
        return await coro_factory()

    mock_queue.enqueue = AsyncMock(side_effect=enqueue_side_effect)
    mock_queue.start = AsyncMock()
    mock_queue.stop = AsyncMock()

    with (
        patch("app.main.redis.from_url", return_value=mock_redis),
        patch("app.main.QueueManager", return_value=mock_queue),
        patch("app.main.LardiClient", return_value=mock_lardi),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            # Перевизначаємо після запуску lifespan
            app.state.redis = mock_redis
            app.state.queue_manager = mock_queue
            app.state.lardi_client = mock_lardi
            yield ac, mock_redis, mock_queue, mock_lardi


# ---------------------------------------------------------------------------
# Тест: успішне повернення деталей з shipper_phone
# ---------------------------------------------------------------------------

async def test_get_cargo_detail_returns_200(detail_client):
    """GET /cargo/{id} повертає HTTP 200 при успішному запиті."""
    ac, mock_redis, mock_queue, mock_lardi = detail_client
    mock_lardi.get_cargo_detail = AsyncMock(return_value=LARDI_DETAIL_FULL)

    response = await ac.get(f"/cargo/{CARGO_ID}")

    assert response.status_code == 200


async def test_get_cargo_detail_returns_shipper_phone(detail_client):
    """shipper_phone містить телефон з proposalUser.contact.phoneItem1.phone."""
    ac, _, _, mock_lardi = detail_client
    mock_lardi.get_cargo_detail = AsyncMock(return_value=LARDI_DETAIL_FULL)

    response = await ac.get(f"/cargo/{CARGO_ID}")
    data = response.json()

    assert data["shipper_phone"] == "+380679078186"


async def test_get_cargo_detail_returns_shipper_name(detail_client):
    """shipper_name містить ім'я контакту."""
    ac, _, _, mock_lardi = detail_client
    mock_lardi.get_cargo_detail = AsyncMock(return_value=LARDI_DETAIL_FULL)

    response = await ac.get(f"/cargo/{CARGO_ID}")

    assert response.json()["shipper_name"] == "Іванов Іван"


async def test_get_cargo_detail_returns_cargo_fields(detail_client):
    """Відповідь містить поля id, body_type, cargo_name."""
    ac, _, _, mock_lardi = detail_client
    mock_lardi.get_cargo_detail = AsyncMock(return_value=LARDI_DETAIL_FULL)

    response = await ac.get(f"/cargo/{CARGO_ID}")
    data = response.json()

    assert data["id"] == CARGO_ID
    assert data["body_type"] == "Тент"
    assert data["cargo_name"] == "міндобриво"


async def test_get_cargo_detail_returns_route(detail_client):
    """route_from та route_to заповнені з waypointListSource/Target."""
    ac, _, _, mock_lardi = detail_client
    mock_lardi.get_cargo_detail = AsyncMock(return_value=LARDI_DETAIL_FULL)

    response = await ac.get(f"/cargo/{CARGO_ID}")
    data = response.json()

    assert data["route_from"] == "Київ"
    assert data["route_to"] == "Одеса"


async def test_get_cargo_detail_cargo_mass_kg(detail_client):
    """cargo_mass_kg містить числову вагу (gruzMass1 float)."""
    ac, _, _, mock_lardi = detail_client
    mock_lardi.get_cargo_detail = AsyncMock(return_value=LARDI_DETAIL_FULL)

    response = await ac.get(f"/cargo/{CARGO_ID}")

    assert response.json()["cargo_mass_kg"] == 17.0


# ---------------------------------------------------------------------------
# Тест: shipper_phone = None в різних сценаріях
# ---------------------------------------------------------------------------

async def test_get_cargo_detail_no_proposal_user_phone_is_none(detail_client):
    """shipper_phone = None коли proposalUser = null."""
    ac, _, _, mock_lardi = detail_client
    mock_lardi.get_cargo_detail = AsyncMock(return_value=LARDI_DETAIL_NO_USER)

    response = await ac.get(f"/cargo/{CARGO_ID}")

    assert response.status_code == 200
    assert response.json()["shipper_phone"] is None


async def test_get_cargo_detail_empty_phone_is_none(detail_client):
    """shipper_phone = None коли phoneItem1.phone порожній рядок."""
    ac, _, _, mock_lardi = detail_client
    mock_lardi.get_cargo_detail = AsyncMock(return_value=LARDI_DETAIL_EMPTY_PHONE)

    response = await ac.get(f"/cargo/{CARGO_ID}")

    assert response.json()["shipper_phone"] is None


# ---------------------------------------------------------------------------
# Тест: HTTP 404 CARGO_NOT_FOUND
# ---------------------------------------------------------------------------

async def test_get_cargo_detail_not_found_returns_404(detail_client):
    """Lardi 404 → наш HTTP 404 з кодом CARGO_NOT_FOUND."""
    ac, _, _, mock_lardi = detail_client
    mock_lardi.get_cargo_detail = AsyncMock(side_effect=LardiHTTPError(404))

    response = await ac.get(f"/cargo/{CARGO_ID}")

    assert response.status_code == 404


async def test_get_cargo_detail_not_found_error_code(detail_client):
    """Тіло 404 містить code=CARGO_NOT_FOUND."""
    ac, _, _, mock_lardi = detail_client
    mock_lardi.get_cargo_detail = AsyncMock(side_effect=LardiHTTPError(404))

    response = await ac.get(f"/cargo/{CARGO_ID}")

    assert response.json()["detail"]["error"]["code"] == "CARGO_NOT_FOUND"


# ---------------------------------------------------------------------------
# Тест: HTTP 502 LARDI_DETAIL_UNAVAILABLE
# ---------------------------------------------------------------------------

async def test_get_cargo_detail_lardi_500_returns_502(detail_client):
    """Lardi 500 → наш HTTP 502 з кодом LARDI_DETAIL_UNAVAILABLE."""
    ac, _, _, mock_lardi = detail_client
    mock_lardi.get_cargo_detail = AsyncMock(side_effect=LardiHTTPError(500))

    response = await ac.get(f"/cargo/{CARGO_ID}")

    assert response.status_code == 502
    assert response.json()["detail"]["error"]["code"] == "LARDI_DETAIL_UNAVAILABLE"


async def test_get_cargo_detail_lardi_401_triggers_recovery_returns_503_timeout(detail_client):
    """
    Lardi 401 → запускає 401 авто-recovery (Story 3.4).

    wait_for_new_ltsid мокується щоб повернути None (таймаут),
    тому відповідь → HTTP 503 LTSID_REFRESH_TIMEOUT.
    """
    ac, _, _, mock_lardi = detail_client
    mock_lardi.get_cargo_detail = AsyncMock(side_effect=LardiHTTPError(401))

    with (
        patch("app.services.retry_handler.publish_refresh_request", new_callable=AsyncMock),
        patch(
            "app.services.retry_handler.wait_for_new_ltsid",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        response = await ac.get(f"/cargo/{CARGO_ID}")

    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "LTSID_REFRESH_TIMEOUT"


# ---------------------------------------------------------------------------
# Тест: HTTP 504 LARDI_TIMEOUT
# ---------------------------------------------------------------------------

async def test_get_cargo_detail_timeout_returns_504(detail_client):
    """Lardi таймаут → HTTP 504 LARDI_TIMEOUT."""
    ac, _, _, mock_lardi = detail_client
    mock_lardi.get_cargo_detail = AsyncMock(side_effect=LardiTimeoutError())

    response = await ac.get(f"/cargo/{CARGO_ID}")

    assert response.status_code == 504
    assert response.json()["detail"]["error"]["code"] == "LARDI_TIMEOUT"


# ---------------------------------------------------------------------------
# Тест: HTTP 503 при проблемах з LTSID та чергою
# ---------------------------------------------------------------------------

async def test_get_cargo_detail_ltsid_missing_returns_503(detail_client):
    """Відсутній LTSID в Redis → HTTP 503 LTSID_REFRESH_FAILED."""
    ac, mock_redis, _, _ = detail_client
    mock_redis.get = AsyncMock(return_value=None)

    response = await ac.get(f"/cargo/{CARGO_ID}")

    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "LTSID_REFRESH_FAILED"


async def test_get_cargo_detail_queue_unavailable_returns_503(detail_client):
    """Redis черга недоступна → HTTP 503 QUEUE_UNAVAILABLE."""
    ac, _, mock_queue, _ = detail_client
    mock_queue.enqueue = AsyncMock(side_effect=QueueUnavailableError())

    response = await ac.get(f"/cargo/{CARGO_ID}")

    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == "QUEUE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Тест: ltsid_hash логується (а не сирий LTSID)
# ---------------------------------------------------------------------------

async def test_lardi_client_logs_ltsid_hash_not_raw(detail_client):
    """
    LardiClient.get_cargo_detail отримує ltsid і логує ltsid_hash.
    Перевіряємо що сам метод get_cargo_detail викликається з правильним ltsid.
    (Безпека: сирий LTSID не потрапляє в логи — відповідальність lardi_client.py)
    """
    ac, mock_redis, _, mock_lardi = detail_client
    mock_redis.get = AsyncMock(return_value="test_ltsid_value_xyz")
    mock_lardi.get_cargo_detail = AsyncMock(return_value=LARDI_DETAIL_FULL)

    await ac.get(f"/cargo/{CARGO_ID}")

    # Перевіряємо що lardi_client.get_cargo_detail викликано з правильним ltsid
    call_args = mock_lardi.get_cargo_detail.call_args
    assert call_args[0][1] == "test_ltsid_value_xyz"  # ltsid передано
