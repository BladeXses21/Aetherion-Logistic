"""
Менеджер черги запитів до Lardi через Redis.

Реалізує глобальну чергу на основі Redis List (RPUSH/BLPOP), яка гарантує:
- Не більше 1 одночасного HTTP-запиту до Lardi (серіалізація)
- Мінімальний інтервал між запитами (rate limiting)
- Відмова з HTTP 503, якщо Redis недоступний (fail-closed, без обходу черги)

Архітектура:
  - Продюсер: кожен endpoint RPUSH-ить request_id до Redis List + зберігає
    coroutine factory і asyncio.Future у локальний словник _pending.
  - Консьюмер: фоновий task виконує BLPOP у нескінченному циклі, при отриманні
    request_id — знаходить coro_factory в _pending, чекає min_interval, виконує
    coro, резолвить Future.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

import redis.asyncio as aioredis
import structlog

from app.core.config import settings

logger = structlog.get_logger()

# Ключ Redis List, куди потрапляють усі запити до Lardi
QUEUE_KEY = "aetherion:queue:lardi"
# Таймаут BLPOP — після закінчення консьюмер просто знову викликає BLPOP
BLPOP_TIMEOUT_SECONDS = 5


class QueueUnavailableError(Exception):
    """Виникає, коли Redis недоступний і не можна додати запит до черги."""


class QueueManager:
    """
    Менеджер Redis-черги для Lardi-запитів.

    Забезпечує серіалізований доступ до Lardi API:
    усі запити проходять через чергу по одному. Консьюмер (фоновий asyncio.Task)
    виконує BLPOP на ключі QUEUE_KEY і обробляє запити послідовно.

    Використання (lifespan):
        manager = QueueManager(redis_client)
        await manager.start()
        ...
        result = await manager.enqueue("req-uuid", lambda: httpx_client.post(...))
        ...
        await manager.stop()
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        # Redis-клієнт (передається із app.state)
        self._redis = redis_client
        # Словник очікуючих запитів: request_id → (coro_factory, future, enqueued_at)
        self._pending: dict[str, tuple[Callable[[], Awaitable], asyncio.Future, float]] = {}
        # Фоновий task консьюмера
        self._consumer_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Запускає фоновий task консьюмера черги."""
        self._consumer_task = asyncio.create_task(self._consumer_loop())
        logger.info("queue_consumer_started", queue_key=QUEUE_KEY)

    async def stop(self) -> None:
        """Зупиняє консьюмер і скасовує всі очікуючі Future."""
        if self._consumer_task:
            self._consumer_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._consumer_task
            self._consumer_task = None

        # Скасовуємо всі futures, що ще чекають результату
        for request_id, (_, future, _) in list(self._pending.items()):
            if not future.done():
                future.cancel()
        self._pending.clear()
        logger.info("queue_consumer_stopped")

    async def enqueue(
        self,
        request_id: str,
        coro_factory: Callable[[], Awaitable],
    ) -> Any:
        """
        Додає запит до Redis-черги та чекає на результат виконання.

        Отримує унікальний request_id і callable (coroutine factory — функцію без
        аргументів, яка повертає Awaitable). RPUSH-ить request_id до Redis List,
        реєструє coro_factory та asyncio.Future у _pending, повертає await Future.

        Args:
            request_id: Унікальний ідентифікатор запиту (UUID рядок).
            coro_factory: Callable[[], Awaitable] — фабрика корутини. Викликається
                          консьюмером вже після rate-limit інтервалу.

        Returns:
            Будь-який результат, що повертає coro_factory().

        Raises:
            QueueUnavailableError: якщо Redis недоступний (не можна RPUSH).
            Exception: якщо coro_factory() підняло виключення — воно прокидається
                       через Future назад до caller.

        Приклад:
            result = await queue_manager.enqueue(
                request_id="550e8400-e29b-41d4-a716-446655440000",
                coro_factory=lambda: httpx_client.post("/search", json=payload),
            )
        """
        # Перевіряємо доступність Redis та отримуємо поточну глибину черги
        try:
            queue_depth = await self._redis.llen(QUEUE_KEY)
            await self._redis.rpush(QUEUE_KEY, request_id)
        except aioredis.RedisError as exc:
            logger.error("queue_redis_unavailable_on_enqueue", request_id=request_id, exc_info=True)
            raise QueueUnavailableError("Redis is unavailable") from exc

        enqueued_at = time.monotonic()
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = (coro_factory, future, enqueued_at)

        logger.info(
            "lardi_request_queued",
            request_id=request_id,
            queue_depth=queue_depth + 1,
            wait_ms=0,  # оновлюється консьюмером при старті виконання
        )

        return await future

    async def _consumer_loop(self) -> None:
        """
        Нескінченний цикл консьюмера BLPOP.

        Виконує BLPOP на QUEUE_KEY з таймаутом BLPOP_TIMEOUT_SECONDS секунд.
        Якщо таймаут — просто знову викликає BLPOP (не падає, не виходить).
        При отриманні request_id:
          1. Чекає LARDI_REQUEST_MIN_INTERVAL_SECONDS (rate limiting)
          2. Викликає coro_factory()
          3. Резолвить або відхиляє відповідний Future

        Обробляє RedisError: логує помилку і повторює спробу через 1 секунду.
        При CancelledError — виходить чисто.
        """
        logger.info("queue_consumer_loop_started")
        while True:
            try:
                # BLPOP повертає (queue_key, value) або None при таймауті
                result = await self._redis.blpop(QUEUE_KEY, timeout=BLPOP_TIMEOUT_SECONDS)
                if result is None:
                    # Таймаут — нормально, повертаємось до BLPOP
                    continue

                _, request_id = result

                pending_entry = self._pending.pop(request_id, None)
                if pending_entry is None:
                    # Запит міг бути скасований — ігноруємо
                    logger.warning("queue_request_id_not_found", request_id=request_id)
                    continue

                coro_factory, future, enqueued_at = pending_entry
                wait_ms = int((time.monotonic() - enqueued_at) * 1000)
                logger.info("lardi_request_dequeued", request_id=request_id, wait_ms=wait_ms)

                # Rate limiting: мінімальний інтервал перед виконанням HTTP-запиту
                await asyncio.sleep(settings.lardi_request_min_interval_seconds)

                if future.cancelled():
                    # Future скасовано поки чекали — виконання не потрібне
                    continue

                try:
                    call_result = await coro_factory()
                    if not future.done():
                        future.set_result(call_result)
                except Exception as exc:
                    logger.error(
                        "queue_request_execution_failed",
                        request_id=request_id,
                        exc_info=True,
                    )
                    if not future.done():
                        future.set_exception(exc)

            except asyncio.CancelledError:
                logger.info("queue_consumer_loop_cancelled")
                raise
            except aioredis.RedisError:
                logger.error("queue_consumer_redis_error", exc_info=True)
                # Не падаємо — чекаємо секунду і повторюємо
                await asyncio.sleep(1)
            except Exception:
                logger.error("queue_consumer_unexpected_error", exc_info=True)
                await asyncio.sleep(1)
