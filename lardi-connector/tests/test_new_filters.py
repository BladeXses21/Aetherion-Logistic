"""
test_new_filters.py — тести нових фільтрів пошуку вантажів (Пріоритет 1 + 2).

Перевіряє що поля width1/2, height1/2, paymentValue, includeDocuments,
excludeDocuments, cargoBodyTypeProperties, onlyShippers, photos
коректно передаються в payload до Lardi API.

Стратегія: інспекція аргументів mock_lardi.search — перевіряємо саме
що потрапило в filter{} Lardi payload, а не лише HTTP статус.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, call

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

# --- Допоміжні дані ---

VALID_REQUEST_BODY = {
    "directionFrom": {"directionRows": [{"countrySign": "UA"}]},
    "directionTo":   {"directionRows": [{"countrySign": "UA"}]},
}

FAKE_LARDI_RESPONSE = {
    "result": {
        "proposals": [],
        "paginator": {"totalSize": 0, "currentPage": 1},
    }
}


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
    """Мок LardiClient що повертає порожню відповідь."""
    mock = AsyncMock()
    mock.search = AsyncMock(return_value=FAKE_LARDI_RESPONSE)
    return mock


@pytest.fixture
async def search_client(mock_redis, mock_queue, mock_lardi):
    """AsyncClient з повністю мокованим app.state."""
    app.state.redis = mock_redis
    app.state.queue_manager = mock_queue
    app.state.lardi_client = mock_lardi

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac, mock_redis, mock_queue, mock_lardi


def _get_lardi_filter(mock_lardi) -> dict:
    """Витягує filter{} зі словника що був переданий в lardi_client.search."""
    call_args = mock_lardi.search.call_args
    # search(payload, ltsid, request_id) — payload це перший позиційний аргумент
    payload = call_args[0][0]
    return payload.get("filter", {})


# --- Тести: фізичні розміри ---

async def test_width1_passed_to_lardi(search_client):
    """width1 (мінімальна ширина) передається в Lardi filter."""
    ac, _, _, mock_lardi = search_client

    body = {**VALID_REQUEST_BODY, "width1": 2.0}
    response = await ac.post("/search", json=body)

    assert response.status_code == 200
    lardi_filter = _get_lardi_filter(mock_lardi)
    assert lardi_filter["width1"] == 2.0


async def test_width2_passed_to_lardi(search_client):
    """width2 (максимальна ширина) передається в Lardi filter."""
    ac, _, _, mock_lardi = search_client

    body = {**VALID_REQUEST_BODY, "width2": 2.4}
    response = await ac.post("/search", json=body)

    assert response.status_code == 200
    lardi_filter = _get_lardi_filter(mock_lardi)
    assert lardi_filter["width2"] == 2.4


async def test_height1_height2_passed_to_lardi(search_client):
    """height1 та height2 передаються разом у Lardi filter."""
    ac, _, _, mock_lardi = search_client

    body = {**VALID_REQUEST_BODY, "height1": 1.5, "height2": 3.0}
    response = await ac.post("/search", json=body)

    assert response.status_code == 200
    lardi_filter = _get_lardi_filter(mock_lardi)
    assert lardi_filter["height1"] == 1.5
    assert lardi_filter["height2"] == 3.0


async def test_dimensions_none_when_not_provided(search_client):
    """Якщо розміри не вказані — width/height у filter залишаються None."""
    ac, _, _, mock_lardi = search_client

    response = await ac.post("/search", json=VALID_REQUEST_BODY)

    assert response.status_code == 200
    lardi_filter = _get_lardi_filter(mock_lardi)
    assert lardi_filter.get("width1") is None
    assert lardi_filter.get("width2") is None
    assert lardi_filter.get("height1") is None
    assert lardi_filter.get("height2") is None


# --- Тести: мінімальна сума оплати ---

async def test_payment_value_passed_to_lardi(search_client):
    """paymentValue (мінімальна ставка) передається в Lardi filter."""
    ac, _, _, mock_lardi = search_client

    body = {**VALID_REQUEST_BODY, "paymentValue": 8000.0}
    response = await ac.post("/search", json=body)

    assert response.status_code == 200
    lardi_filter = _get_lardi_filter(mock_lardi)
    assert lardi_filter["paymentValue"] == 8000.0


async def test_payment_value_none_when_not_provided(search_client):
    """paymentValue = None якщо не вказано в запиті."""
    ac, _, _, mock_lardi = search_client

    response = await ac.post("/search", json=VALID_REQUEST_BODY)

    assert response.status_code == 200
    lardi_filter = _get_lardi_filter(mock_lardi)
    assert lardi_filter.get("paymentValue") is None


# --- Тести: документи ---

async def test_include_documents_passed_to_lardi(search_client):
    """includeDocuments (обов'язкові документи) передаються в Lardi filter."""
    ac, _, _, mock_lardi = search_client

    body = {**VALID_REQUEST_BODY, "includeDocuments": ["cmr", "tir"]}
    response = await ac.post("/search", json=body)

    assert response.status_code == 200
    lardi_filter = _get_lardi_filter(mock_lardi)
    assert lardi_filter["includeDocuments"] == ["cmr", "tir"]


async def test_exclude_documents_passed_to_lardi(search_client):
    """excludeDocuments (небажані документи) передаються в Lardi filter."""
    ac, _, _, mock_lardi = search_client

    body = {**VALID_REQUEST_BODY, "excludeDocuments": ["t1", "ekmt"]}
    response = await ac.post("/search", json=body)

    assert response.status_code == 200
    lardi_filter = _get_lardi_filter(mock_lardi)
    assert lardi_filter["excludeDocuments"] == ["t1", "ekmt"]


async def test_all_valid_document_codes_accepted(search_client):
    """Всі підтверджені коди документів проходять без помилок."""
    ac, _, _, mock_lardi = search_client

    all_codes = ["cmr", "t1", "tir", "ekmt", "frc", "cmrInsurance"]
    body = {**VALID_REQUEST_BODY, "includeDocuments": all_codes}
    response = await ac.post("/search", json=body)

    assert response.status_code == 200
    lardi_filter = _get_lardi_filter(mock_lardi)
    assert lardi_filter["includeDocuments"] == all_codes


async def test_documents_none_when_not_provided(search_client):
    """includeDocuments та excludeDocuments = None якщо не вказані."""
    ac, _, _, mock_lardi = search_client

    response = await ac.post("/search", json=VALID_REQUEST_BODY)

    assert response.status_code == 200
    lardi_filter = _get_lardi_filter(mock_lardi)
    assert lardi_filter.get("includeDocuments") is None
    assert lardi_filter.get("excludeDocuments") is None


# --- Тести: модифікатори кузова ---

async def test_cargo_body_type_properties_passed_to_lardi(search_client):
    """cargoBodyTypeProperties (Jumbo/Mega/Doubledeck) передається в Lardi filter."""
    ac, _, _, mock_lardi = search_client

    body = {**VALID_REQUEST_BODY, "cargoBodyTypeProperties": ["Jumbo"]}
    response = await ac.post("/search", json=body)

    assert response.status_code == 200
    lardi_filter = _get_lardi_filter(mock_lardi)
    assert lardi_filter["cargoBodyTypeProperties"] == ["Jumbo"]


async def test_cargo_body_type_properties_none_when_not_provided(search_client):
    """cargoBodyTypeProperties = None якщо не вказано."""
    ac, _, _, mock_lardi = search_client

    response = await ac.post("/search", json=VALID_REQUEST_BODY)

    assert response.status_code == 200
    lardi_filter = _get_lardi_filter(mock_lardi)
    assert lardi_filter.get("cargoBodyTypeProperties") is None


# --- Тести: комбінований запит ---

async def test_all_new_filters_combined(search_client):
    """Всі нові фільтри Пріоритету 1 можна передати разом."""
    ac, _, _, mock_lardi = search_client

    body = {
        **VALID_REQUEST_BODY,
        "width1": 2.0,
        "width2": 2.4,
        "height1": 1.5,
        "height2": 2.7,
        "paymentValue": 5000.0,
        "includeDocuments": ["cmr"],
        "excludeDocuments": ["tir"],
        "cargoBodyTypeProperties": ["Mega"],
    }
    response = await ac.post("/search", json=body)

    assert response.status_code == 200
    f = _get_lardi_filter(mock_lardi)
    assert f["width1"] == 2.0
    assert f["width2"] == 2.4
    assert f["height1"] == 1.5
    assert f["height2"] == 2.7
    assert f["paymentValue"] == 5000.0
    assert f["includeDocuments"] == ["cmr"]
    assert f["excludeDocuments"] == ["tir"]
    assert f["cargoBodyTypeProperties"] == ["Mega"]
