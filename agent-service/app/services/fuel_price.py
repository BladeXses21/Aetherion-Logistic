"""
fuel_price.py — Сервіс читання поточної ціни дизельного палива.

Реалізує ланцюжок fallback для отримання ціни:
  1. Redis ключ aetherion:fuel:price:diesel (основний, актуальний)
  2. In-memory кеш (остання відома ціна з попереднього успішного читання)
  3. None → caller отримує HTTP 503 FUEL_PRICE_UNAVAILABLE

Призначений для використання в інструменті calculate_margin (Story 4.2).

Примітка: Ціна зберігається в Redis сервісом auth-worker/scheduler/fuel_fetcher.py
(Story 3.5). Agent-service НЕ отримує ціну напряму з зовнішнього джерела.
"""
from __future__ import annotations

import structlog

log = structlog.get_logger()

# Ключ Redis де auth-worker зберігає ціну дизелю (Story 3.5)
FUEL_REDIS_KEY = "aetherion:fuel:price:diesel"


class FuelPriceService:
    """
    Сервіс отримання поточної ціни дизельного палива для розрахунку маржі.

    Зберігає останнє відоме значення в пам'яті як fallback при недоступності Redis.
    Один екземпляр ініціалізується в lifespan і зберігається як app.state.fuel_price.

    Attributes:
        _memory_cache: Остання відома ціна (float) або None якщо ніколи не читали.

    Використання:
        fuel_service = FuelPriceService()
        price = await fuel_service.get_price(redis_client)
        if price is None:
            raise HTTPException(503, {"error": {"code": "FUEL_PRICE_UNAVAILABLE"}})
    """

    def __init__(self) -> None:
        """Ініціалізує сервіс з порожнім in-memory кешем."""
        self._memory_cache: float | None = None

    async def get_price(self, redis_client) -> float | None:
        """
        Повертає поточну ціну дизелю з Redis або in-memory кешу.

        Ланцюжок отримання:
          1. Redis: читає aetherion:fuel:price:diesel
             - Якщо Redis доступний та ключ існує → повертає значення
               (також оновлює _memory_cache для наступного fallback).
          2. In-memory: якщо Redis недоступний або ключ відсутній → _memory_cache
             - Якщо є → логує WARNING та повертає збережене значення.
          3. None: якщо обидва недоступні.

        Args:
            redis_client: Async Redis клієнт (redis.asyncio.Redis).

        Returns:
            Ціна дизелю як float (наприклад, 52.3) або None якщо ціна недоступна.

        Приклад:
            price = await fuel_service.get_price(app.state.redis)
            # → 52.3  або  None
        """
        # Крок 1: Спробуємо прочитати з Redis
        try:
            raw = await redis_client.get(FUEL_REDIS_KEY)
        except Exception:
            log.warning("fuel_price_redis_unavailable_using_memory", exc_info=True)
            raw = None

        if raw is not None:
            try:
                price = float(raw)
                self._memory_cache = price  # оновлюємо in-memory для наступного fallback
                return price
            except (ValueError, TypeError):
                log.warning("fuel_price_redis_value_invalid", raw=raw)
                raw = None

        # Крок 2: Redis недоступний або ключ відсутній — in-memory fallback
        if self._memory_cache is not None:
            log.warning(
                "fuel_price_redis_miss_using_memory",
                memory_price=self._memory_cache,
            )
            return self._memory_cache

        # Крок 3: Обидва джерела недоступні
        log.error("fuel_price_unavailable_no_cache")
        return None


# Singleton-екземпляр — ініціалізується один раз, зберігається через app.state
fuel_price_service = FuelPriceService()
