"""
retry_handler.py — Обробник повторних спроб для Lardi API.

Реалізує два механізми захисту від збоїв:
  1. 401 auto-recovery: публікує refresh_requested, чекає новий LTSID, повторює
     запит один раз. При невдачі кидає LtsidRefreshError.
  2. 429/503 exponential backoff + jitter: до 3 спроб із наростаючою затримкою.
     На 400/404 — одразу пробрасує помилку без retry.

Використання в ендпоінтах:
    result = await with_rate_limit_retry(execute_factory, request_id)
    де execute_factory містить виклик handle_401_and_retry при потребі.
"""
from __future__ import annotations

import asyncio
import random

import redis.asyncio as aioredis
import structlog

from app.core.config import settings
from app.core.errors import ErrorCode
from app.services.lardi_client import LardiHTTPError
from app.services.session_refresh import publish_refresh_request, wait_for_new_ltsid

# Ключ Redis де зберігається поточний LTSID сесії
LTSID_KEY = "aetherion:auth:ltsid"
# HTTP-коди, що підлягають retry з exponential backoff
RETRYABLE_STATUS_CODES = {429, 503}
# HTTP-коди, що НЕ підлягають retry (клієнтська помилка або "не знайдено")
NON_RETRYABLE_STATUS_CODES = {400, 404}
# Максимальна кількість повторних спроб при rate limit / service unavailable
MAX_RETRIES = 3
# Базова затримка для exponential backoff (секунди)
BACKOFF_BASE_SECONDS = 1.0
# Максимальний випадковий jitter (мілісекунди)
MAX_JITTER_MS = 300


class LtsidRefreshError(Exception):
    """
    Виникає коли авто-відновлення LTSID завершилось невдачею.

    Attributes:
        code: Код помилки (LTSID_REFRESH_FAILED або LTSID_REFRESH_TIMEOUT).
        details: Додаткові дані (наприклад, {"retry_after": 30} для timeout).
    """

    def __init__(self, code: str, details: dict | None = None) -> None:
        """
        Ініціалізує помилку з кодом і опціональними деталями.

        Args:
            code: Рядковий код помилки (з ErrorCode enum).
            details: Словник з додатковими деталями або None.
        """
        self.code = code
        self.details = details or {}
        super().__init__(code)


async def handle_401_and_retry(
    coro_factory_with_ltsid,
    redis_client: aioredis.Redis,
    request_id: str,
) -> dict:
    """
    Обробляє 401 від Lardi: публікує refresh_requested, чекає новий LTSID,
    повторює оригінальний запит один раз із новим LTSID.

    Алгоритм:
      1. Зчитує поточний LTSID з Redis (old_ltsid).
      2. Публікує {"event": "refresh_requested"} до каналу aetherion:auth:refresh.
      3. Опитує Redis до зміни LTSID або таймауту (90с).
      4. Чекає ltsid_retry_delay_ms перед повторним запитом.
      5. Виконує запит з новим LTSID. Якщо знову 401 — кидає LtsidRefreshError(FAILED).

    Args:
        coro_factory_with_ltsid: callable(ltsid: str) → Awaitable — фабрика
            корутини запиту, що приймає LTSID як єдиний аргумент.
        redis_client: Асинхронний Redis-клієнт для pub/sub і опитування.
        request_id: UUID поточного запиту для structlog.

    Returns:
        Словник — результат успішного повторного запиту.

    Raises:
        LtsidRefreshError(LTSID_REFRESH_FAILED): якщо retry після refresh теж 401.
        LtsidRefreshError(LTSID_REFRESH_TIMEOUT): якщо новий LTSID не з'явився за 90с.
        LardiHTTPError: якщо повторний запит повернув іншу не-2xx помилку.

    Приклад:
        async def search_with_ltsid(ltsid: str) -> dict:
            return await lardi_client.search(payload, ltsid, request_id)

        result = await handle_401_and_retry(search_with_ltsid, redis, request_id)
    """
    log = structlog.get_logger().bind(request_id=request_id)
    log.warning("lardi_401_detected_starting_refresh")

    # Зберігаємо поточний LTSID щоб відстежити його зміну
    try:
        old_ltsid = await redis_client.get(LTSID_KEY)
    except Exception:
        old_ltsid = None

    # Публікуємо запит на оновлення сесії
    await publish_refresh_request(redis_client, request_id)

    # Чекаємо поки auth-worker оновить LTSID
    new_ltsid = await wait_for_new_ltsid(redis_client, old_ltsid or "", request_id)

    if new_ltsid is None:
        raise LtsidRefreshError(
            ErrorCode.LTSID_REFRESH_TIMEOUT,
            details={"retry_after": 30},
        )

    # Невелика затримка перед повторним запитом (налаштовується через ENV)
    await asyncio.sleep(settings.ltsid_retry_delay_ms / 1000)

    log.info("ltsid_refresh_retry_attempt", ltsid_changed=True)

    try:
        return await coro_factory_with_ltsid(new_ltsid)
    except LardiHTTPError as exc:
        if exc.status_code == 401:
            log.error("ltsid_refresh_retry_also_401")
            raise LtsidRefreshError(ErrorCode.LTSID_REFRESH_FAILED)
        raise


async def with_rate_limit_retry(
    coro_factory,
    request_id: str,
) -> dict:
    """
    Виконує coro_factory з exponential backoff retry при 429/503 від Lardi.

    Логіка:
      - Виконує coro_factory() до MAX_RETRIES+1 разів (тобто 1 початкова + 3 retry).
      - При 429 або 503 — чекає (base × 2^attempt + jitter) і повторює.
      - При 400 або 404 — одразу пробрасує (не retry, клієнтська помилка).
      - При інших кодах — одразу пробрасує без retry.
      - Якщо всі спроби вичерпані — пробрасує останній LardiHTTPError.

    Формула затримки: BACKOFF_BASE_SECONDS × 2^attempt + random(0, MAX_JITTER_MS/1000)
      attempt=0 → ~1с, attempt=1 → ~2с, attempt=2 → ~4с

    Args:
        coro_factory: callable() → Awaitable — фабрика корутини запиту без аргументів.
        request_id: UUID поточного запиту для structlog.

    Returns:
        Словник — результат першого успішного виклику.

    Raises:
        LardiHTTPError: якщо всі retry вичерпані або помилка не підлягає retry.

    Приклад:
        result = await with_rate_limit_retry(
            lambda: lardi_client.search(payload, ltsid, request_id),
            request_id,
        )
    """
    log = structlog.get_logger().bind(request_id=request_id)

    for attempt in range(MAX_RETRIES + 1):
        try:
            return await coro_factory()
        except LardiHTTPError as exc:
            # Клієнтські помилки — retry не має сенсу
            if exc.status_code in NON_RETRYABLE_STATUS_CODES:
                raise
            # Коди без retry (наприклад, 401 — обробляється окремо)
            if exc.status_code not in RETRYABLE_STATUS_CODES:
                raise
            # Всі спроби вичерпані
            if attempt >= MAX_RETRIES:
                log.error(
                    "lardi_rate_limit_max_retries_exceeded",
                    status_code=exc.status_code,
                )
                raise

            # Exponential backoff з jitter для рівномірного розподілу запитів
            jitter_s = random.uniform(0, MAX_JITTER_MS / 1000)
            delay = BACKOFF_BASE_SECONDS * (2 ** attempt) + jitter_s
            log.warning(
                "lardi_rate_limit_retry",
                status_code=exc.status_code,
                attempt=attempt + 1,
                delay_seconds=round(delay, 3),
            )
            await asyncio.sleep(delay)
