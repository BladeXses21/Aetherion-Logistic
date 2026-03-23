"""
test_search_endpoint.py — тести для POST /search ендпоінту (Story 3.2).

Покриває всі Acceptance Criteria:
  - Валідний запит → 200 з правильною структурою відповіді
  - bodyTypeIds: рядки ("34") конвертуються в int
  - bodyTypeIds: нечисловий рядок ("truck") → 422 INVALID_FILTER_TYPE
  - loadTypes: валідні коди приймаються та маппяться в числові id
  - loadTypes: невалідний код → 422 INVALID_FILTER_TYPE
  - distance_m і distance_km: правильна конвертація (distance / 1000)
  - totalSize >= 500 → capped=True з capped_note
  - Lardi timeout → 504 LARDI_TIMEOUT
  - QueueUnavailable → 503 QUEUE_UNAVAILABLE
  - LTSID відсутній → 503 LTSID_REFRESH_FAILED

Стратегія моків:
  - app.state.redis, app.state.queue_manager, app.state.lardi_client
    встановлюються напряму в app.state перед AsyncClient (без запуску lifespan).
  - QueueManager.enqueue мокується з side_effect, що одразу викликає coro_factory.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.queue.queue_manager import QueueUnavailableError
from app.services.lardi_client import LardiTimeoutError

# --- Допоміжні дані для тестів ---

# Мінімальний валідний запит для пошуку вантажів
VALID_REQUEST_BODY = {
    "directionFrom": {
        "directionRows": [{"countrySign": "UA", "townId": 4}]
    },
    "directionTo": {
        "directionRows": [{"countrySign": "UA", "townId": 10}]
    },
}

# Фіктивна відповідь від Lardi API з одним вантажем
FAKE_LARDI_RESPONSE = {
    "result": {
        "proposals": [
            {
                "id": 123456,
                "bodyType": "Тент",
                "waypointListSource": [{"town": "Київ", "country": "Україна"}],
                "waypointListTarget": [{"town": "Львів", "country": "Україна"}],
                "dateFrom": "2026-03-25",
                "distance": 540000,
                "payment": "40 000 грн.",
                "paymentValue": "40000",
                "paymentCurrencyId": 4,
                "gruzName": "Будматеріали",
                "gruzMass": "17 т",
            }
        ],
        "paginator": {"totalSize": 42, "currentPage": 1},
    }
}


# --- Допоміжна функція enqueue (викликає coro_factory напряму) ---

async def _enqueue_passthrough(request_id: str, coro_factory):
    """Мок enqueue, що негайно виконує coro_factory без черги."""
    return await coro_factory()


# --- Фікстури ---

@pytest.fixture
def mock_redis():
    """Мок Redis клієнта з LTSID."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value="fake_ltsid_value")
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
    """Мок LardiClient, що повертає фіктивну відповідь."""
    mock = AsyncMock()
    mock.search = AsyncMock(return_value=FAKE_LARDI_RESPONSE)
    return mock


@pytest.fixture
async def search_client(mock_redis, mock_queue, mock_lardi):
    """
    AsyncClient з повністю мокованим app.state.

    Встановлює мокі напряму в app.state — без запуску lifespan,
    що дозволяє уникнути реального підключення до Redis.
    """
    app.state.redis = mock_redis
    app.state.queue_manager = mock_queue
    app.state.lardi_client = mock_lardi

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_redis, mock_queue, mock_lardi


# --- Тести ---

async def test_search_valid_request_returns_200(search_client):
    """POST /search з валідним запитом повертає 200 і правильну структуру."""
    ac, mock_redis, mock_queue, mock_lardi = search_client

    response = await ac.post("/search", json=VALID_REQUEST_BODY)

    assert response.status_code == 200
    data = response.json()
    assert "proposals" in data
    assert "total_size" in data
    assert "current_page" in data
    assert "capped" in data
    assert data["total_size"] == 42
    assert data["current_page"] == 1
    assert data["capped"] is False
    assert len(data["proposals"]) == 1


async def test_search_valid_request_proposal_fields(search_client):
    """POST /search повертає правильно наповнені поля CargoItem."""
    ac, *_ = search_client

    response = await ac.post("/search", json=VALID_REQUEST_BODY)
    assert response.status_code == 200

    proposal = response.json()["proposals"][0]
    assert proposal["id"] == 123456
    assert proposal["body_type"] == "Тент"
    assert proposal["route_from"] == "Київ"
    assert proposal["route_to"] == "Львів"
    assert proposal["loading_date"] == "2026-03-25"
    assert proposal["cargo_name"] == "Будматеріали"
    assert proposal["cargo_mass"] == "17 т"
    assert proposal["payment"] == "40 000 грн."


async def test_search_body_type_ids_string_cast_to_int(search_client):
    """bodyTypeIds: рядки типу "34" конвертуються в int без помилок."""
    ac, *_ = search_client

    body = {**VALID_REQUEST_BODY, "bodyTypeIds": ["34", "5", 12]}
    response = await ac.post("/search", json=body)

    assert response.status_code == 200


async def test_search_body_type_ids_invalid_string_returns_422(search_client):
    """bodyTypeIds: нечисловий рядок "truck" → 422 INVALID_FILTER_TYPE."""
    ac, *_ = search_client

    body = {**VALID_REQUEST_BODY, "bodyTypeIds": ["truck"]}
    response = await ac.post("/search", json=body)

    assert response.status_code == 422
    # FastAPI обгортає HTTPException detail у {"detail": ...}
    error = response.json()["detail"]["error"]
    assert error["code"] == "INVALID_FILTER_TYPE"
    assert "bodyTypeIds" in error["message"]


async def test_search_load_types_valid_codes_accepted(search_client):
    """loadTypes: валідні коди ("back", "top", "side") приймаються без помилок."""
    ac, *_ = search_client

    body = {**VALID_REQUEST_BODY, "loadTypes": ["back", "top", "side"]}
    response = await ac.post("/search", json=body)

    assert response.status_code == 200


async def test_search_load_types_invalid_code_returns_422(search_client):
    """loadTypes: невалідний код "flatbed" → 422 INVALID_FILTER_TYPE."""
    ac, *_ = search_client

    body = {**VALID_REQUEST_BODY, "loadTypes": ["flatbed"]}
    response = await ac.post("/search", json=body)

    assert response.status_code == 422
    # FastAPI обгортає HTTPException detail у {"detail": ...}
    error = response.json()["detail"]["error"]
    assert error["code"] == "INVALID_FILTER_TYPE"
    assert "loadTypes" in error["message"]
    assert "flatbed" in error["message"]


async def test_search_distance_conversion(search_client, mock_lardi):
    """distance_m = сирий integer, distance_km = distance / 1000 (1 знак після коми)."""
    ac, *_ = search_client

    # Відповідь з відстанню 540000 метрів = 540.0 км
    response = await ac.post("/search", json=VALID_REQUEST_BODY)
    assert response.status_code == 200

    proposal = response.json()["proposals"][0]
    assert proposal["distance_m"] == 540000
    assert proposal["distance_km"] == 540.0


async def test_search_distance_conversion_non_round(search_client, mock_lardi):
    """distance_km округлюється до 1 знаку: 54500 метрів = 54.5 км."""
    ac, _, _, mock_lardi = search_client

    # Змінюємо відстань на некруглу
    custom_response = {
        "result": {
            "proposals": [{**FAKE_LARDI_RESPONSE["result"]["proposals"][0], "distance": 54500}],
            "paginator": {"totalSize": 1, "currentPage": 1},
        }
    }
    mock_lardi.search = AsyncMock(return_value=custom_response)

    response = await ac.post("/search", json=VALID_REQUEST_BODY)
    assert response.status_code == 200

    proposal = response.json()["proposals"][0]
    assert proposal["distance_m"] == 54500
    assert proposal["distance_km"] == 54.5


async def test_search_capped_results(search_client, mock_lardi):
    """totalSize == 500 → capped=True і capped_note містить пояснення."""
    ac, _, _, mock_lardi = search_client

    # Відповідь із 500 результатами (максимум Lardi)
    capped_response = {
        "result": {
            "proposals": FAKE_LARDI_RESPONSE["result"]["proposals"],
            "paginator": {"totalSize": 500, "currentPage": 1},
        }
    }
    mock_lardi.search = AsyncMock(return_value=capped_response)

    response = await ac.post("/search", json=VALID_REQUEST_BODY)
    assert response.status_code == 200

    data = response.json()
    assert data["total_size"] == 500
    assert data["capped"] is True
    assert data["capped_note"] is not None
    assert "pagination" in data["capped_note"].lower() or "Lardi" in data["capped_note"]


async def test_search_capped_results_not_triggered_below_500(search_client, mock_lardi):
    """totalSize < 500 → capped=False і capped_note=None."""
    ac, _, _, mock_lardi = search_client

    response = await ac.post("/search", json=VALID_REQUEST_BODY)
    assert response.status_code == 200

    data = response.json()
    assert data["capped"] is False
    assert data["capped_note"] is None


async def test_search_lardi_timeout_returns_504(search_client, mock_queue, mock_lardi):
    """Lardi HTTP timeout → 504 LARDI_TIMEOUT."""
    ac, _, mock_queue, mock_lardi = search_client

    # Симулюємо timeout — enqueue кидає LardiTimeoutError
    async def enqueue_timeout(request_id, coro_factory):
        raise LardiTimeoutError()

    mock_queue.enqueue = AsyncMock(side_effect=enqueue_timeout)

    response = await ac.post("/search", json=VALID_REQUEST_BODY)

    assert response.status_code == 504
    # FastAPI обгортає HTTPException detail у {"detail": ...}
    assert response.json()["detail"]["error"]["code"] == "LARDI_TIMEOUT"


async def test_search_queue_unavailable_returns_503(search_client, mock_queue):
    """Redis черга недоступна → 503 QUEUE_UNAVAILABLE."""
    ac, _, mock_queue, _ = search_client

    async def enqueue_unavailable(request_id, coro_factory):
        raise QueueUnavailableError()

    mock_queue.enqueue = AsyncMock(side_effect=enqueue_unavailable)

    response = await ac.post("/search", json=VALID_REQUEST_BODY)

    assert response.status_code == 503
    # FastAPI обгортає HTTPException detail у {"detail": ...}
    assert response.json()["detail"]["error"]["code"] == "QUEUE_UNAVAILABLE"


async def test_search_ltsid_missing_returns_503(search_client, mock_redis):
    """LTSID відсутній в Redis → 503 LTSID_REFRESH_FAILED."""
    ac, mock_redis, *_ = search_client

    # Redis повертає None — LTSID не знайдено
    mock_redis.get = AsyncMock(return_value=None)

    response = await ac.post("/search", json=VALID_REQUEST_BODY)

    assert response.status_code == 503
    # FastAPI обгортає HTTPException detail у {"detail": ...}
    error = response.json()["detail"]["error"]
    assert error["code"] == "LTSID_REFRESH_FAILED"
    assert "LTSID" in error["message"]


async def test_search_ltsid_redis_error_returns_503(search_client, mock_redis):
    """Redis кидає exception при get(ltsid) → 503 LTSID_REFRESH_FAILED."""
    ac, mock_redis, *_ = search_client

    # Redis недоступний при читанні LTSID
    mock_redis.get = AsyncMock(side_effect=Exception("Redis connection lost"))

    response = await ac.post("/search", json=VALID_REQUEST_BODY)

    assert response.status_code == 503
    # FastAPI обгортає HTTPException detail у {"detail": ...}
    assert response.json()["detail"]["error"]["code"] == "LTSID_REFRESH_FAILED"


async def test_search_payment_form_ids_string_cast_to_int(search_client):
    """paymentFormIds: рядки типу "2" конвертуються в int без помилок."""
    ac, *_ = search_client

    body = {**VALID_REQUEST_BODY, "paymentFormIds": ["2", "3"]}
    response = await ac.post("/search", json=body)

    assert response.status_code == 200


async def test_search_payment_form_ids_invalid_string_returns_422(search_client):
    """paymentFormIds: нечисловий рядок → 422 INVALID_FILTER_TYPE."""
    ac, *_ = search_client

    body = {**VALID_REQUEST_BODY, "paymentFormIds": ["cash"]}
    response = await ac.post("/search", json=body)

    assert response.status_code == 422
    # FastAPI обгортає HTTPException detail у {"detail": ...}
    error = response.json()["detail"]["error"]
    assert error["code"] == "INVALID_FILTER_TYPE"
    assert "paymentFormIds" in error["message"]


async def test_search_load_types_tail_lift_and_tent_off_accepted(search_client):
    """loadTypes: placeholder коди "tail_lift" та "tent_off" також приймаються."""
    ac, *_ = search_client

    body = {**VALID_REQUEST_BODY, "loadTypes": ["tail_lift", "tent_off"]}
    response = await ac.post("/search", json=body)

    assert response.status_code == 200


async def test_search_request_id_generated_per_request(search_client, mock_queue):
    """Кожен запит отримує унікальний request_id (перевіряємо що enqueue викликається)."""
    ac, _, mock_queue, _ = search_client

    await ac.post("/search", json=VALID_REQUEST_BODY)
    await ac.post("/search", json=VALID_REQUEST_BODY)

    # Enqueue має бути викликаний двічі
    assert mock_queue.enqueue.call_count == 2

    # Обидва request_id мають бути різними
    call_args_1 = mock_queue.enqueue.call_args_list[0][0][0]
    call_args_2 = mock_queue.enqueue.call_args_list[1][0][0]
    assert call_args_1 != call_args_2
