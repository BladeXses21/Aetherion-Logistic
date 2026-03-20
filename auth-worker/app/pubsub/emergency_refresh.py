"""emergency_refresh.py — Аварійне оновлення LTSID через Redis Pub/Sub.

Слухає Redis канал `aetherion:auth:refresh`. Коли lardi-connector отримує
HTTP 401, він публікує повідомлення в цей канал і auth-worker негайно
запускає Chrome login для оновлення LTSID.

Захист від race condition: `SET aetherion:auth:refresh:lock NX EX 120` —
тільки один refresh виконується одночасно. Якщо lock вже зайнятий,
поточний цикл чекає до 90 секунд (дедублікація).

Circuit breaker: після 3 послідовних помилок Chrome — пауза 10 хвилин.

Listener запускається як asyncio.Task у lifespan main.py та зупиняється
через task.cancel() при завершенні сервісу.
"""
from __future__ import annotations

import asyncio
import time

import structlog

from app.browser.lardi_login import fetch_ltsid
from app.core.config import settings
from app.session.ltsid_store import ltsid_store

log = structlog.get_logger()

# Redis ключі (ARCH6)
REFRESH_CHANNEL = "aetherion:auth:refresh"
REFRESH_LOCK_KEY = "aetherion:auth:refresh:lock"


class CircuitBreaker:
    """In-memory circuit breaker для Chrome refresh операцій.

    Відстежує кількість послідовних помилок та відкриває circuit після
    досягнення порогу. Під час відкритого circuit всі спроби refresh
    пропускаються. Після паузи circuit закривається автоматично.

    Attributes:
        _threshold: Кількість послідовних помилок до відкриття circuit.
        _pause_seconds: Тривалість паузи у секундах після відкриття.
        _consecutive_failures: Поточний лічильник помилок.
        _open_until: Monotonic timestamp до якого circuit залишається відкритим.

    Example:
        >>> cb = CircuitBreaker(threshold=3, pause_seconds=600)
        >>> cb.is_open()
        False
        >>> cb.record_failure()
        >>> cb.record_failure()
        >>> cb.record_failure()
        >>> cb.is_open()  # True після 3 помилок
        True
    """

    def __init__(self, threshold: int, pause_seconds: int) -> None:
        """Ініціалізує circuit breaker.

        Args:
            threshold: Кількість послідовних помилок до відкриття circuit.
            pause_seconds: Тривалість паузи у секундах після відкриття.
        """
        self._threshold = threshold
        self._pause_seconds = pause_seconds
        self._consecutive_failures = 0
        self._open_until: float = 0.0

    def is_open(self) -> bool:
        """Перевіряє чи circuit зараз відкритий (refresh заблоковано).

        Returns:
            True якщо circuit відкритий і refresh не повинен виконуватись.
        """
        return time.monotonic() < self._open_until

    def record_failure(self) -> None:
        """Реєструє помилку Chrome refresh.

        Якщо кількість послідовних помилок досягає порогу — відкриває
        circuit на `_pause_seconds` секунд та логує WARNING.
        """
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._threshold:
            self._open_until = time.monotonic() + self._pause_seconds
            pause_minutes = self._pause_seconds // 60
            log.warning("ltsid_circuit_breaker_open", pause_minutes=pause_minutes)
            self._consecutive_failures = 0  # скидаємо лічильник після відкриття

    def record_success(self) -> None:
        """Реєструє успішний Chrome refresh — скидає лічильник помилок."""
        self._consecutive_failures = 0


async def _do_emergency_refresh(redis_client, circuit_breaker: CircuitBreaker) -> None:
    """Виконує одну спробу аварійного оновлення LTSID.

    Алгоритм:
        1. Спробувати отримати Redis lock (SET NX EX 120).
        2. Якщо lock отримано → Chrome refresh → зберегти новий LTSID → success.
        3. Якщо lock НЕ отримано → інший процес вже оновлює →
           чекати до 90 секунд поки lock звільниться → дедублікація.
        4. Якщо Chrome fails → логувати ERROR → записати failure у circuit breaker.
           LTSID НЕ перезаписується при помилці.

    Args:
        redis_client: Async Redis клієнт (redis.asyncio.Redis).
        circuit_breaker: Екземпляр CircuitBreaker для реєстрації результатів.
    """
    # Спроба отримати lock (SET NX EX)
    lock_acquired = await redis_client.set(
        REFRESH_LOCK_KEY,
        "1",
        nx=True,
        ex=settings.ltsid_refresh_lock_ttl_seconds,
    )

    if not lock_acquired:
        # Інший процес вже виконує refresh — чекаємо поки lock звільниться
        log.info("ltsid_emergency_refresh_waiting_for_lock")
        await _wait_for_lock_release(redis_client)
        log.info("ltsid_refresh_deduplicated", reason="lock_held_waited")
        return

    # Lock отримано — виконуємо Chrome refresh
    try:
        ltsid = await fetch_ltsid(
            login=settings.lardi_login,
            password=settings.lardi_password,
            timeout_seconds=settings.chrome_timeout_seconds,
        )
        await ltsid_store.store(redis_client, ltsid, settings.ltsid_ttl_hours)
        circuit_breaker.record_success()
        log.info("ltsid_emergency_refresh_completed")
    except Exception:
        circuit_breaker.record_failure()
        log.error("ltsid_emergency_refresh_failed", exc_info=True)
        # LTSID НЕ перезаписується — ltsid_store.store не викликається при помилці
    finally:
        # Завжди звільняємо lock після завершення (успішного чи ні)
        try:
            await redis_client.delete(REFRESH_LOCK_KEY)
        except Exception:
            # Lock закінчиться сам по собі через EX TTL — не критично
            log.warning("ltsid_refresh_lock_release_failed")


async def _wait_for_lock_release(redis_client) -> None:
    """Чекає поки Redis lock `aetherion:auth:refresh:lock` звільниться.

    Polling з інтервалом 1 секунда, максимальний час очікування визначається
    налаштуванням `LTSID_REFRESH_WAIT_SECONDS` (дефолт: 90 секунд).

    Args:
        redis_client: Async Redis клієнт.
    """
    deadline = time.monotonic() + settings.ltsid_refresh_wait_seconds
    while time.monotonic() < deadline:
        try:
            lock_exists = await redis_client.exists(REFRESH_LOCK_KEY)
            if not lock_exists:
                return
        except Exception:
            # Якщо Redis недоступний під час polling — просто виходимо
            log.warning("redis_unavailable_during_lock_wait")
            return
        await asyncio.sleep(1)

    log.warning(
        "ltsid_refresh_lock_wait_timeout",
        timeout_seconds=settings.ltsid_refresh_wait_seconds,
    )


async def listen_for_refresh_events(redis_client) -> None:
    """Нескінченний цикл: слухає Redis pub/sub та запускає аварійний refresh.

    Запускається як asyncio.Task у lifespan main.py. Зупиняється через
    task.cancel() при завершенні сервісу — обробляє CancelledError gracefully.

    При помилці Redis (pub/sub недоступний) — логує ERROR, чекає 5 секунд,
    та автоматично перепідписується. Сервіс НЕ зупиняється.

    Структура зовнішнього циклу (retry loop):
        while True:
            підписатись → слухати повідомлення → при помилці → reconnect

    Args:
        redis_client: Async Redis клієнт (redis.asyncio.Redis).
            Pub/Sub використовує окреме з'єднання всередині цього клієнта.
    """
    circuit_breaker = CircuitBreaker(
        threshold=settings.refresh_circuit_breaker_threshold,
        pause_seconds=settings.refresh_circuit_breaker_pause_minutes * 60,
    )

    while True:  # outer retry loop — reconnects on Redis error
        pubsub = redis_client.pubsub()
        try:
            await pubsub.subscribe(REFRESH_CHANNEL)
            log.info("redis_pubsub_subscribed", channel=REFRESH_CHANNEL)

            async for message in pubsub.listen():
                if message["type"] != "message":
                    # Пропускаємо системні підтвердження subscribe/unsubscribe
                    continue

                log.info(
                    "ltsid_emergency_refresh_event_received",
                    channel=message.get("channel"),
                )

                if circuit_breaker.is_open():
                    log.info("ltsid_emergency_refresh_skipped_circuit_open")
                    continue

                await _do_emergency_refresh(redis_client, circuit_breaker)

        except asyncio.CancelledError:
            # Graceful shutdown — відписуємось та закриваємо з'єднання
            log.info("redis_pubsub_listener_stopping")
            try:
                await pubsub.unsubscribe(REFRESH_CHANNEL)
                await pubsub.aclose()
            except Exception:
                pass
            raise  # re-raise — asyncio.Task завершується коректно

        except Exception:
            log.error("redis_pubsub_unavailable", exc_info=True)
            try:
                await pubsub.aclose()
            except Exception:
                pass
            await asyncio.sleep(5)  # пауза перед повторним підключенням
