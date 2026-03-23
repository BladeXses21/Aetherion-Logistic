"""
Тести для fuel_price.py (Story 3.5: Fuel Price Service — agent-service частина).

Перевіряють:
  - Redis доступний, ключ існує → повертається ціна
  - Redis доступний, ключ відсутній → in-memory fallback
  - Redis недоступний → in-memory fallback
  - In-memory порожній → повертається None
  - In-memory оновлюється після успішного читання Redis
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.fuel_price import FuelPriceService


async def test_get_price_from_redis_returns_float():
    """Redis повертає рядок "52.3" → get_price повертає float 52.3."""
    service = FuelPriceService()
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value="52.3")

    price = await service.get_price(redis_mock)

    assert price == 52.3


async def test_get_price_from_redis_updates_memory_cache():
    """Після успішного читання Redis, _memory_cache оновлюється."""
    service = FuelPriceService()
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value="55.0")

    await service.get_price(redis_mock)

    assert service._memory_cache == 55.0


async def test_get_price_redis_miss_returns_memory_cache():
    """Redis повертає None (ключ відсутній) → повертається _memory_cache."""
    service = FuelPriceService()
    service._memory_cache = 51.5
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)

    price = await service.get_price(redis_mock)

    assert price == 51.5


async def test_get_price_redis_unavailable_returns_memory_cache():
    """Redis кидає виключення → повертається _memory_cache."""
    service = FuelPriceService()
    service._memory_cache = 49.9
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(side_effect=Exception("connection refused"))

    price = await service.get_price(redis_mock)

    assert price == 49.9


async def test_get_price_no_cache_returns_none():
    """Redis недоступний та _memory_cache порожній → повертається None."""
    service = FuelPriceService()
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)

    price = await service.get_price(redis_mock)

    assert price is None


async def test_get_price_redis_invalid_value_falls_back_to_memory():
    """Redis повертає невалідний рядок → in-memory fallback."""
    service = FuelPriceService()
    service._memory_cache = 48.0
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value="not-a-number")

    price = await service.get_price(redis_mock)

    assert price == 48.0


async def test_get_price_redis_integer_string_works():
    """Redis повертає "52" (без дробової частини) → 52.0."""
    service = FuelPriceService()
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value="52")

    price = await service.get_price(redis_mock)

    assert price == 52.0


async def test_memory_cache_not_updated_on_redis_error():
    """При помилці Redis _memory_cache НЕ змінюється."""
    service = FuelPriceService()
    service._memory_cache = 50.0
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(side_effect=Exception("down"))

    await service.get_price(redis_mock)

    assert service._memory_cache == 50.0
