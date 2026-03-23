"""
session_refresh.py — Логіка авто-відновлення сесії після 401 від Lardi.

Публікує подію refresh_requested в Redis pub/sub, опитує Redis до появи
нового LTSID, потім повторює оригінальний запит.

Функції:
  - publish_refresh_request: надсилає подію до каналу aetherion:auth:refresh
  - wait_for_new_ltsid: опитує Redis поки значення LTSID не зміниться
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import redis.asyncio as aioredis
import structlog

from app.core.config import settings

# Ключ Redis де зберігається поточний LTSID сесії
LTSID_KEY = "aetherion:auth:ltsid"
# Канал Redis pub/sub для запитів на оновлення LTSID
REFRESH_CHANNEL = "aetherion:auth:refresh"
# Інтервал опитування Redis при очікуванні нового LTSID (секунди)
POLL_INTERVAL_SECONDS = 1.0


async def wait_for_new_ltsid(
    redis_client: aioredis.Redis,
    old_ltsid: str,
    request_id: str,
    max_wait_seconds: int | None = None,
) -> str | None:
    """
    Чекає поки значення aetherion:auth:ltsid у Redis зміниться.

    Порівнює поточне значення LTSID з old_ltsid кожну секунду.
    Якщо нове значення відрізняється — повертає його.
    Якщо за max_wait_seconds зміни не відбулось — повертає None.

    При помилці Redis продовжує опитування (fail-open для черги).

    Args:
        redis_client: Асинхронний Redis-клієнт.
        old_ltsid: Попереднє значення LTSID, зміну якого ми очікуємо.
        request_id: UUID поточного запиту — для structlog трасування.
        max_wait_seconds: Максимальний час очікування в секундах.
                          Якщо None — береться з settings.ltsid_refresh_wait_seconds.

    Returns:
        Новий LTSID (str) якщо зміна відбулась, або None при таймауті.

    Приклад:
        new_ltsid = await wait_for_new_ltsid(redis, "old_token", "req-123", max_wait_seconds=10)
        if new_ltsid is None:
            raise LtsidRefreshError(LTSID_REFRESH_TIMEOUT)
    """
    if max_wait_seconds is None:
        max_wait_seconds = settings.ltsid_refresh_wait_seconds

    log = structlog.get_logger().bind(request_id=request_id)
    elapsed = 0.0

    while elapsed < max_wait_seconds:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        elapsed += POLL_INTERVAL_SECONDS

        try:
            current = await redis_client.get(LTSID_KEY)
        except aioredis.RedisError:
            log.warning("ltsid_poll_redis_error")
            continue

        if current and current != old_ltsid:
            log.info("ltsid_refresh_detected", elapsed_seconds=elapsed)
            return current

    log.warning("ltsid_refresh_wait_timeout", max_wait_seconds=max_wait_seconds)
    return None


async def publish_refresh_request(
    redis_client: aioredis.Redis,
    request_id: str,
) -> None:
    """
    Публікує подію refresh_requested до Redis pub/sub каналу aetherion:auth:refresh.

    Повідомлення містить event, причину (401) та ISO-мітку часу.
    При помилці Redis — логує але не кидає виняток (best-effort публікація).

    Args:
        redis_client: Асинхронний Redis-клієнт для публікації.
        request_id: UUID поточного запиту — для structlog трасування.

    Формат повідомлення:
        {"event": "refresh_requested", "reason": "401", "timestamp": "<ISO>"}
    """
    log = structlog.get_logger().bind(request_id=request_id)
    message = json.dumps({
        "event": "refresh_requested",
        "reason": "401",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    try:
        await redis_client.publish(REFRESH_CHANNEL, message)
        log.info("ltsid_refresh_requested_published")
    except aioredis.RedisError:
        log.error("ltsid_refresh_publish_failed", exc_info=True)
