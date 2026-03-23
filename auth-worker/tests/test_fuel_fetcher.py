"""
Тести для fuel_fetcher.py (Story 3.5: Fuel Price Service — auth-worker частина).

Перевіряють:
  - Успішне отримання ціни з JSON відповіді та збереження в Redis
  - Успішне отримання з HTML відповіді (regex)
  - Таймаут → логується WARNING, кеш не видаляється
  - HTTP помилка → логується WARNING, кеш не видаляється
  - Redis недоступний → логується WARNING без краша
  - FUEL_PRICE_URL не налаштований → без дій
  - _parse_price: JSON, HTML, невалідні дані
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.scheduler.fuel_fetcher import (
    FUEL_REDIS_KEY,
    _parse_price,
    fetch_and_store_fuel_price,
)


# ---------------------------------------------------------------------------
# Тести _parse_price (unit)
# ---------------------------------------------------------------------------

def test_parse_price_json_returns_float():
    """JSON {"diesel": 52.3} → 52.3."""
    result = _parse_price('{"diesel": 52.3, "currency": "UAH"}', "application/json")
    assert result == 52.3


def test_parse_price_json_integer_returns_float():
    """JSON {"diesel": 52} → 52.0 (конвертується у float)."""
    result = _parse_price('{"diesel": 52, "currency": "UAH"}', "application/json")
    assert result == 52.0


def test_parse_price_json_missing_diesel_key_returns_none():
    """JSON без ключа "diesel" → None."""
    result = _parse_price('{"gasoline": 52.3}', "application/json")
    assert result is None


def test_parse_price_json_invalid_returns_none():
    """Невалідний JSON → None."""
    result = _parse_price("not json", "application/json")
    assert result is None


def test_parse_price_html_finds_decimal():
    """HTML з числом у форматі 52.30 → 52.3."""
    html = '<html><body><span class="price">52.30</span></body></html>'
    result = _parse_price(html, "text/html")
    assert result == 52.3


def test_parse_price_html_finds_comma_decimal():
    """HTML з числом у форматі 52,30 (кома) → 52.3."""
    html = '<html><body><span>52,30 грн/л</span></body></html>'
    result = _parse_price(html, "text/html")
    assert result == 52.3


def test_parse_price_html_no_number_returns_none():
    """HTML без числа → None."""
    result = _parse_price('<html><body>ціна недоступна</body></html>', "text/html")
    assert result is None


# ---------------------------------------------------------------------------
# Тести fetch_and_store_fuel_price (integration з мок HTTP/Redis)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    """Мок Redis клієнта."""
    r = AsyncMock()
    r.set = AsyncMock(return_value=True)
    return r


async def test_fetch_stores_price_in_redis(mock_redis):
    """Успішний запит JSON → ціна зберігається в Redis з правильним TTL."""
    mock_response = MagicMock()
    mock_response.text = '{"diesel": 55.5, "currency": "UAH"}'
    mock_response.headers = {"content-type": "application/json"}
    mock_response.raise_for_status = MagicMock()

    with (
        patch("app.scheduler.fuel_fetcher.settings") as mock_settings,
        patch("app.scheduler.fuel_fetcher.httpx.AsyncClient") as MockClient,
    ):
        mock_settings.fuel_price_url = "https://fake-fuel-api.ua/prices"
        mock_settings.fuel_price_http_timeout_seconds = 5
        mock_settings.fuel_cache_ttl_seconds = 3600

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        await fetch_and_store_fuel_price(mock_redis)

    mock_redis.set.assert_called_once_with(FUEL_REDIS_KEY, "55.5", ex=3600)


async def test_fetch_stores_correct_key(mock_redis):
    """Ціна зберігається під ключем aetherion:fuel:price:diesel."""
    mock_response = MagicMock()
    mock_response.text = '{"diesel": 50.0, "currency": "UAH"}'
    mock_response.headers = {"content-type": "application/json"}
    mock_response.raise_for_status = MagicMock()

    with (
        patch("app.scheduler.fuel_fetcher.settings") as mock_settings,
        patch("app.scheduler.fuel_fetcher.httpx.AsyncClient") as MockClient,
    ):
        mock_settings.fuel_price_url = "https://fake.ua/prices"
        mock_settings.fuel_price_http_timeout_seconds = 5
        mock_settings.fuel_cache_ttl_seconds = 3600

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        await fetch_and_store_fuel_price(mock_redis)

    assert mock_redis.set.call_args[0][0] == "aetherion:fuel:price:diesel"


async def test_fetch_timeout_does_not_overwrite_redis(mock_redis):
    """Таймаут → Redis.set НЕ викликається (кеш збережено)."""
    with (
        patch("app.scheduler.fuel_fetcher.settings") as mock_settings,
        patch("app.scheduler.fuel_fetcher.httpx.AsyncClient") as MockClient,
    ):
        mock_settings.fuel_price_url = "https://fake.ua/prices"
        mock_settings.fuel_price_http_timeout_seconds = 5
        mock_settings.fuel_cache_ttl_seconds = 3600

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        await fetch_and_store_fuel_price(mock_redis)

    mock_redis.set.assert_not_called()


async def test_fetch_http_error_does_not_overwrite_redis(mock_redis):
    """HTTP помилка → Redis.set НЕ викликається (кеш збережено)."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=MagicMock())
    )

    with (
        patch("app.scheduler.fuel_fetcher.settings") as mock_settings,
        patch("app.scheduler.fuel_fetcher.httpx.AsyncClient") as MockClient,
    ):
        mock_settings.fuel_price_url = "https://fake.ua/prices"
        mock_settings.fuel_price_http_timeout_seconds = 5
        mock_settings.fuel_cache_ttl_seconds = 3600

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        await fetch_and_store_fuel_price(mock_redis)

    mock_redis.set.assert_not_called()


async def test_fetch_redis_store_fails_no_crash(mock_redis):
    """Redis.set кидає виключення → функція не падає (логується WARNING)."""
    mock_response = MagicMock()
    mock_response.text = '{"diesel": 52.0, "currency": "UAH"}'
    mock_response.headers = {"content-type": "application/json"}
    mock_response.raise_for_status = MagicMock()
    mock_redis.set = AsyncMock(side_effect=Exception("redis down"))

    with (
        patch("app.scheduler.fuel_fetcher.settings") as mock_settings,
        patch("app.scheduler.fuel_fetcher.httpx.AsyncClient") as MockClient,
    ):
        mock_settings.fuel_price_url = "https://fake.ua/prices"
        mock_settings.fuel_price_http_timeout_seconds = 5
        mock_settings.fuel_cache_ttl_seconds = 3600

        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        MockClient.return_value.__aexit__ = AsyncMock(return_value=None)

        # Не повинно підняти виключення
        await fetch_and_store_fuel_price(mock_redis)


async def test_fetch_no_url_configured_does_nothing(mock_redis):
    """FUEL_PRICE_URL не налаштований → HTTP запит НЕ виконується."""
    with patch("app.scheduler.fuel_fetcher.settings") as mock_settings:
        mock_settings.fuel_price_url = ""

        with patch("app.scheduler.fuel_fetcher.httpx.AsyncClient") as MockClient:
            await fetch_and_store_fuel_price(mock_redis)
            MockClient.assert_not_called()

    mock_redis.set.assert_not_called()
