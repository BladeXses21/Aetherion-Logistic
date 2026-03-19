"""ltsid_store.py — Зберігання та отримання LTSID cookie.

Надає єдиний модульний синглтон `ltsid_store` для зберігання LTSID у Redis
з автоматичним fallback в оперативну пам'ять при недоступності Redis.

Redis ключ: `aetherion:auth:ltsid` (відповідно до ARCH6).
TTL: береться з ENV `LTSID_TTL_HOURS` (дефолт: 23 години).

Стани LTSID (для /health):
    - "valid"          — збережений у Redis, TTL > 0
    - "in_memory_only" — Redis недоступний, збережений в оперативній пам'яті
    - "missing"        — не отримано (Chrome fail або ще не запускався)
"""
from __future__ import annotations

import structlog

log = structlog.get_logger()

# Redis ключ для LTSID (ARCH6: aetherion:{service}:{entity}:{id})
LTSID_REDIS_KEY = "aetherion:auth:ltsid"


class LtsidStore:
    """Менеджер зберігання LTSID у Redis із fallback в оперативну пам'ять.

    Використовується як модульний синглтон: `from app.session.ltsid_store import ltsid_store`.
    Кожен модуль отримує один і той самий екземпляр.
    """

    def __init__(self) -> None:
        self._ltsid_memory: str | None = None
        self._mode: str = "missing"  # "valid" | "in_memory_only" | "missing"

    async def store(self, redis_client, ltsid: str, ttl_hours: int) -> None:
        """Зберігає LTSID у Redis (основне сховище) або пам'яті (fallback).

        Завжди оновлює in-memory копію. Спочатку намагається записати в Redis
        з TTL у годинах. Якщо Redis недоступний — зберігає тільки в пам'яті
        та виставляє статус "in_memory_only".

        Args:
            redis_client: Async Redis клієнт (redis.asyncio.Redis).
            ltsid: Значення LTSID cookie (НЕ логується повністю).
            ttl_hours: TTL зберігання у Redis у годинах.
        """
        ttl_seconds = ttl_hours * 3600
        self._ltsid_memory = ltsid

        try:
            await redis_client.set(LTSID_REDIS_KEY, ltsid, ex=ttl_seconds)
            self._mode = "valid"
            log.info(
                "ltsid_stored_in_redis",
                key=LTSID_REDIS_KEY,
                ttl_hours=ttl_hours,
                ltsid_prefix=ltsid[:8] + "***",  # логуємо лише перші 8 символів
            )
        except Exception:
            self._mode = "in_memory_only"
            log.error(
                "redis_unavailable_ltsid_stored_in_memory",
                key=LTSID_REDIS_KEY,
                exc_info=True,
            )

    async def get(self, redis_client) -> str | None:
        """Повертає поточний LTSID — з Redis або fallback з пам'яті.

        Спочатку намагається прочитати з Redis. Якщо Redis недоступний або
        ключ відсутній — повертає in-memory значення (якщо є).

        Args:
            redis_client: Async Redis клієнт.

        Returns:
            Рядок LTSID або None якщо не збережено.
        """
        try:
            value = await redis_client.get(LTSID_REDIS_KEY)
            if value:
                return value
        except Exception:
            log.warning("ltsid_redis_read_failed_using_memory", exc_info=False)

        return self._ltsid_memory

    @property
    def health_status(self) -> str:
        """Повертає статус LTSID для /health endpoint.

        Returns:
            "valid"          — є у Redis
            "in_memory_only" — Redis недоступний, але є в пам'яті
            "missing"        — LTSID відсутній
        """
        return self._mode

    def mark_missing(self) -> None:
        """Встановлює статус LTSID як "missing" (Chrome login провалився).

        Використовується у lifespan при перехопленні LtsidFetchError.
        """
        self._mode = "missing"


# Модульний синглтон — один об'єкт на весь процес
ltsid_store = LtsidStore()
