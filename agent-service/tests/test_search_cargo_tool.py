"""
test_search_cargo_tool.py — тести інструмента search_cargo (трансляція параметрів).

Перевіряє що параметри інструмента коректно транслюються у поля search_request
що передаються в lardi-connector.search(). Тестується весь ланцюжок:

  tool param → [resolve/cast] → search_request key

Покриття:
  - Priority 1: розміри (width/height), мінімальна оплата (paymentValue),
                документи (includeDocuments/excludeDocuments),
                модифікатори кузова (cargoBodyTypeProperties)
  - Priority 2: onlyShippers, photos
  - Priority 3: onlyCarrier, onlyExpedition, companyName
  - Резолюція документів: українські назви → Lardi коди
  - Резолюція модифікаторів: "джамбо" → "Jumbo"
  - None-поведінка: параметри що не передані → відсутні в search_request

Стратегія: інспекція call_args mock_lardi.search — перевіряємо саме
що потрапило в search_request, а не результат відповіді.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.tools.search_cargo import make_search_cargo_tool

# --- Константи ---

FAKE_DIRECTION = {"directionRows": [{"countrySign": "UA"}]}

FAKE_LARDI_RESPONSE = {"proposals": [], "total_size": 0, "capped": False}


# --- Фікстури ---

@pytest.fixture
def mock_geo_resolver():
    """Мок GeoResolver — завжди повертає UA-напрямок."""
    mock = AsyncMock()
    mock.resolve = AsyncMock(return_value=FAKE_DIRECTION)
    return mock


@pytest.fixture
def mock_fuel_price_service():
    """Мок FuelPriceService — повертає фіксовану ціну 55 грн/л."""
    mock = AsyncMock()
    mock.get_price = AsyncMock(return_value=55.0)
    return mock


@pytest.fixture
def mock_lardi():
    """Мок lardi клієнта — повертає порожню відповідь."""
    mock = AsyncMock()
    mock.search = AsyncMock(return_value=FAKE_LARDI_RESPONSE)
    return mock


@pytest.fixture
def mock_lardi_factory(mock_lardi):
    """Мок фабрики lardi клієнта як async context manager."""
    @asynccontextmanager
    async def factory():
        yield mock_lardi
    return factory


@pytest.fixture
def mock_db_session():
    """Мок async DB session factory."""
    @asynccontextmanager
    async def factory():
        yield AsyncMock()
    return factory


@pytest.fixture
def mock_http_client():
    """Мок async HTTP client factory."""
    @asynccontextmanager
    async def factory():
        yield AsyncMock()
    return factory


@pytest.fixture
def search_tool(
    mock_geo_resolver,
    mock_fuel_price_service,
    mock_lardi_factory,
    mock_lardi,
    mock_db_session,
    mock_http_client,
):
    """
    Зібраний search_cargo tool з мокованими залежностями.

    Повертає (tool, mock_lardi) — tool для виклику,
    mock_lardi для інспекції переданого search_request.
    """
    tool = make_search_cargo_tool(
        geo_resolver=mock_geo_resolver,
        fuel_price_service=mock_fuel_price_service,
        lardi_client_factory=mock_lardi_factory,
        db_session_factory=mock_db_session,
        http_client_factory=mock_http_client,
        fuel_consumption=30.0,
        overhead_coeff=1.0,
        redis_client=AsyncMock(),
    )
    return tool, mock_lardi


def _get_search_request(mock_lardi) -> dict[str, Any]:
    """Витягує search_request зі словника що передавався в lardi.search."""
    return mock_lardi.search.call_args[0][0]


async def _invoke(tool, **kwargs) -> None:
    """Виклик tool через ainvoke з базовими обов'язковими полями."""
    params = {"from_location": "Київ", "to_location": "Одеса", **kwargs}
    await tool.ainvoke(params)


# --- Тести: розміри (Priority 1) ---

async def test_min_width_translates_to_width1(search_tool):
    """min_width → search_request['width1']."""
    tool, mock_lardi = search_tool
    await _invoke(tool, min_width=2.0)
    req = _get_search_request(mock_lardi)
    assert req["width1"] == 2.0


async def test_max_width_translates_to_width2(search_tool):
    """max_width → search_request['width2']."""
    tool, mock_lardi = search_tool
    await _invoke(tool, max_width=2.4)
    req = _get_search_request(mock_lardi)
    assert req["width2"] == 2.4


async def test_min_height_translates_to_height1(search_tool):
    """min_height → search_request['height1']."""
    tool, mock_lardi = search_tool
    await _invoke(tool, min_height=1.5)
    req = _get_search_request(mock_lardi)
    assert req["height1"] == 1.5


async def test_max_height_translates_to_height2(search_tool):
    """max_height → search_request['height2']."""
    tool, mock_lardi = search_tool
    await _invoke(tool, max_height=3.0)
    req = _get_search_request(mock_lardi)
    assert req["height2"] == 3.0


async def test_width_height_absent_when_not_provided(search_tool):
    """width1/width2/height1/height2 відсутні якщо не передані."""
    tool, mock_lardi = search_tool
    await _invoke(tool)
    req = _get_search_request(mock_lardi)
    assert "width1" not in req
    assert "width2" not in req
    assert "height1" not in req
    assert "height2" not in req


# --- Тести: мінімальна оплата (Priority 1) ---

async def test_min_payment_translates_to_payment_value(search_tool):
    """min_payment → search_request['paymentValue']."""
    tool, mock_lardi = search_tool
    await _invoke(tool, min_payment=8000.0)
    req = _get_search_request(mock_lardi)
    assert req["paymentValue"] == 8000.0


async def test_payment_value_absent_when_not_provided(search_tool):
    """paymentValue відсутній якщо min_payment не передано."""
    tool, mock_lardi = search_tool
    await _invoke(tool)
    req = _get_search_request(mock_lardi)
    assert "paymentValue" not in req


# --- Тести: документи (Priority 1) ---

async def test_required_documents_direct_code(search_tool):
    """required_documents=['cmr'] → includeDocuments=['cmr'] (прямий код)."""
    tool, mock_lardi = search_tool
    await _invoke(tool, required_documents=["cmr"])
    req = _get_search_request(mock_lardi)
    assert req["includeDocuments"] == ["cmr"]


async def test_required_documents_uppercase_code(search_tool):
    """required_documents=['CMR'] → includeDocuments=['cmr'] (регістронезалежний)."""
    tool, mock_lardi = search_tool
    await _invoke(tool, required_documents=["CMR"])
    req = _get_search_request(mock_lardi)
    assert req["includeDocuments"] == ["cmr"]


async def test_required_documents_ukrainian_cmr(search_tool):
    """required_documents=['цмр'] → includeDocuments=['cmr'] (українська назва)."""
    tool, mock_lardi = search_tool
    await _invoke(tool, required_documents=["цмр"])
    req = _get_search_request(mock_lardi)
    assert req["includeDocuments"] == ["cmr"]


async def test_required_documents_ukrainian_tir(search_tool):
    """required_documents=['тір'] → includeDocuments=['tir'] (українська назва)."""
    tool, mock_lardi = search_tool
    await _invoke(tool, required_documents=["тір"])
    req = _get_search_request(mock_lardi)
    assert req["includeDocuments"] == ["tir"]


async def test_required_documents_insurance(search_tool):
    """required_documents=['страховка cmr'] → includeDocuments=['cmrInsurance']."""
    tool, mock_lardi = search_tool
    await _invoke(tool, required_documents=["страховка cmr"])
    req = _get_search_request(mock_lardi)
    assert req["includeDocuments"] == ["cmrInsurance"]


async def test_required_documents_multiple(search_tool):
    """required_documents=['cmr', 'tir'] → includeDocuments=['cmr', 'tir']."""
    tool, mock_lardi = search_tool
    await _invoke(tool, required_documents=["cmr", "tir"])
    req = _get_search_request(mock_lardi)
    assert req["includeDocuments"] == ["cmr", "tir"]


async def test_required_documents_unknown_skipped(search_tool):
    """Невідомий код документа ігнорується — не потрапляє в includeDocuments."""
    tool, mock_lardi = search_tool
    await _invoke(tool, required_documents=["невідомий_документ"])
    req = _get_search_request(mock_lardi)
    assert "includeDocuments" not in req


async def test_excluded_documents_translates_correctly(search_tool):
    """excluded_documents=['tir'] → excludeDocuments=['tir']."""
    tool, mock_lardi = search_tool
    await _invoke(tool, excluded_documents=["tir"])
    req = _get_search_request(mock_lardi)
    assert req["excludeDocuments"] == ["tir"]


async def test_excluded_documents_ukrainian(search_tool):
    """excluded_documents=['транзит'] → excludeDocuments=['t1']."""
    tool, mock_lardi = search_tool
    await _invoke(tool, excluded_documents=["транзит"])
    req = _get_search_request(mock_lardi)
    assert req["excludeDocuments"] == ["t1"]


async def test_documents_absent_when_not_provided(search_tool):
    """includeDocuments/excludeDocuments відсутні якщо не передані."""
    tool, mock_lardi = search_tool
    await _invoke(tool)
    req = _get_search_request(mock_lardi)
    assert "includeDocuments" not in req
    assert "excludeDocuments" not in req


# --- Тести: модифікатори кузова (Priority 1) ---

async def test_body_modifier_jumbo_resolves(search_tool):
    """body_modifiers=['jumbo'] → cargoBodyTypeProperties=['Jumbo']."""
    tool, mock_lardi = search_tool
    await _invoke(tool, body_modifiers=["jumbo"])
    req = _get_search_request(mock_lardi)
    assert req["cargoBodyTypeProperties"] == ["Jumbo"]


async def test_body_modifier_ukrainian_jumbo(search_tool):
    """body_modifiers=['джамбо'] → cargoBodyTypeProperties=['Jumbo']."""
    tool, mock_lardi = search_tool
    await _invoke(tool, body_modifiers=["джамбо"])
    req = _get_search_request(mock_lardi)
    assert req["cargoBodyTypeProperties"] == ["Jumbo"]


async def test_body_modifier_mega(search_tool):
    """body_modifiers=['мега'] → cargoBodyTypeProperties=['Mega']."""
    tool, mock_lardi = search_tool
    await _invoke(tool, body_modifiers=["мега"])
    req = _get_search_request(mock_lardi)
    assert req["cargoBodyTypeProperties"] == ["Mega"]


async def test_body_modifier_doubledeck(search_tool):
    """body_modifiers=['двоповерховий'] → cargoBodyTypeProperties=['Doubledeck']."""
    tool, mock_lardi = search_tool
    await _invoke(tool, body_modifiers=["двоповерховий"])
    req = _get_search_request(mock_lardi)
    assert req["cargoBodyTypeProperties"] == ["Doubledeck"]


async def test_body_modifier_unknown_skipped(search_tool):
    """Невідомий модифікатор ігнорується — cargoBodyTypeProperties відсутній."""
    tool, mock_lardi = search_tool
    await _invoke(tool, body_modifiers=["гігант"])
    req = _get_search_request(mock_lardi)
    assert "cargoBodyTypeProperties" not in req


async def test_body_modifiers_absent_when_not_provided(search_tool):
    """cargoBodyTypeProperties відсутній якщо body_modifiers не передано."""
    tool, mock_lardi = search_tool
    await _invoke(tool)
    req = _get_search_request(mock_lardi)
    assert "cargoBodyTypeProperties" not in req


# --- Тести: Priority 2 (onlyShippers, photos) ---

async def test_only_shippers_true(search_tool):
    """only_shippers=True → search_request['onlyShippers'] = True."""
    tool, mock_lardi = search_tool
    await _invoke(tool, only_shippers=True)
    req = _get_search_request(mock_lardi)
    assert req["onlyShippers"] is True


async def test_only_shippers_false(search_tool):
    """only_shippers=False → search_request['onlyShippers'] = False."""
    tool, mock_lardi = search_tool
    await _invoke(tool, only_shippers=False)
    req = _get_search_request(mock_lardi)
    assert req["onlyShippers"] is False


async def test_with_photos_true(search_tool):
    """with_photos=True → search_request['photos'] = True."""
    tool, mock_lardi = search_tool
    await _invoke(tool, with_photos=True)
    req = _get_search_request(mock_lardi)
    assert req["photos"] is True


async def test_only_shippers_absent_when_none(search_tool):
    """onlyShippers відсутній якщо only_shippers не передано."""
    tool, mock_lardi = search_tool
    await _invoke(tool)
    req = _get_search_request(mock_lardi)
    assert "onlyShippers" not in req
    assert "photos" not in req


# --- Тести: Priority 3 (onlyCarrier, onlyExpedition, companyName) ---

async def test_only_carrier_true(search_tool):
    """only_carrier=True → search_request['onlyCarrier'] = True."""
    tool, mock_lardi = search_tool
    await _invoke(tool, only_carrier=True)
    req = _get_search_request(mock_lardi)
    assert req["onlyCarrier"] is True


async def test_only_expedition_true(search_tool):
    """only_expedition=True → search_request['onlyExpedition'] = True."""
    tool, mock_lardi = search_tool
    await _invoke(tool, only_expedition=True)
    req = _get_search_request(mock_lardi)
    assert req["onlyExpedition"] is True


async def test_company_name_passed(search_tool):
    """company_name='АТБ' → search_request['companyName'] = 'АТБ'."""
    tool, mock_lardi = search_tool
    await _invoke(tool, company_name="АТБ")
    req = _get_search_request(mock_lardi)
    assert req["companyName"] == "АТБ"


async def test_priority3_absent_when_not_provided(search_tool):
    """onlyCarrier/onlyExpedition/companyName відсутні якщо не передані."""
    tool, mock_lardi = search_tool
    await _invoke(tool)
    req = _get_search_request(mock_lardi)
    assert "onlyCarrier" not in req
    assert "onlyExpedition" not in req
    assert "companyName" not in req


# --- Тести: комбінований запит (всі нові параметри разом) ---

async def test_all_new_params_combined(search_tool):
    """Всі нові параметри P1+P2+P3 коректно транслюються одночасно."""
    tool, mock_lardi = search_tool
    await _invoke(
        tool,
        min_width=2.0,
        max_width=2.4,
        min_height=1.5,
        max_height=3.0,
        min_payment=5000.0,
        required_documents=["cmr", "tir"],
        excluded_documents=["t1"],
        body_modifiers=["jumbo"],
        only_shippers=True,
        with_photos=True,
        only_carrier=False,
        only_expedition=False,
        company_name="АТБ",
    )
    req = _get_search_request(mock_lardi)
    assert req["width1"] == 2.0
    assert req["width2"] == 2.4
    assert req["height1"] == 1.5
    assert req["height2"] == 3.0
    assert req["paymentValue"] == 5000.0
    assert req["includeDocuments"] == ["cmr", "tir"]
    assert req["excludeDocuments"] == ["t1"]
    assert req["cargoBodyTypeProperties"] == ["Jumbo"]
    assert req["onlyShippers"] is True
    assert req["photos"] is True
    assert req["onlyCarrier"] is False
    assert req["onlyExpedition"] is False
    assert req["companyName"] == "АТБ"
