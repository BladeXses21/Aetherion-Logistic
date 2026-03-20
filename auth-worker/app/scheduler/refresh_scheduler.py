"""refresh_scheduler.py — Планувальник проактивного оновлення LTSID.

Запускає фоновий APScheduler job, який кожні N хвилин (ENV: LTSID_PROACTIVE_CHECK_INTERVAL_SECONDS,
дефолт: 1800 с = 30 хв) перевіряє TTL ключа `aetherion:auth:ltsid` у Redis.

Якщо TTL менший за поріг (ENV: LTSID_REFRESH_THRESHOLD_SECONDS, дефолт: 3600 с = 1 год),
запускається Chrome login та новий LTSID зберігається у Redis.

ПланувальникНІКОЛИ не крашиться — всі помилки Redis і Chrome перехоплюються
та логуються, після чого job продовжує роботу до наступного циклу.
"""
from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.browser.lardi_login import fetch_ltsid
from app.core.config import settings
from app.session.ltsid_store import LTSID_REDIS_KEY, ltsid_store

log = structlog.get_logger()


async def check_and_refresh_ltsid(redis_client) -> None:
    """Фонова задача: перевіряє TTL LTSID і оновлює його при потребі.

    Ця функція виконується планувальником кожні LTSID_PROACTIVE_CHECK_INTERVAL_SECONDS секунд.
    Вона НЕ кидає виключень — усі помилки перехоплюються та логуються.

    Логіка:
        1. Отримати TTL ключа `aetherion:auth:ltsid` з Redis.
        2. Якщо Redis недоступний — логувати WARNING і повернутись (пропустити цикл).
        3. Якщо TTL < LTSID_REFRESH_THRESHOLD_SECONDS (або ключ відсутній) → запустити Chrome refresh.
        4. Якщо TTL достатній → пропустити refresh (DEBUG лог).
        5. Якщо Chrome refresh провалився → логувати ERROR і повернутись.

    Семантика значень redis.ttl():
        -2 — ключ не існує (необхідно оновити)
        -1 — ключ існує, але без TTL (необхідно оновити)
        >=0 — секунди до закінчення TTL

    Args:
        redis_client: Async Redis клієнт (redis.asyncio.Redis), переданий з lifespan.

    Example:
        # Викликається планувальником автоматично; для тестів:
        >>> await check_and_refresh_ltsid(redis_client)
    """
    # Крок 1: Отримати TTL з Redis
    try:
        ttl = await redis_client.ttl(LTSID_REDIS_KEY)
    except Exception:
        log.warning("redis_unavailable_skipping_ttl_check")
        return

    # Крок 2: Перевірити чи потрібен refresh
    # ttl < 0 означає: ключ відсутній (-2) або без TTL (-1) — завжди оновлюємо
    needs_refresh = ttl < 0 or ttl < settings.ltsid_refresh_threshold_seconds
    if not needs_refresh:
        log.debug("ltsid_proactive_refresh_skipped", ttl_remaining_seconds=ttl)
        return

    log.info("ltsid_proactive_refresh_triggered", ttl_remaining_seconds=ttl)

    # Крок 3: Запустити Chrome login та зберегти новий LTSID
    try:
        ltsid = await fetch_ltsid(
            login=settings.lardi_login,
            password=settings.lardi_password,
            timeout_seconds=settings.chrome_timeout_seconds,
        )
        await ltsid_store.store(redis_client, ltsid, settings.ltsid_ttl_hours)
        new_ttl_seconds = settings.ltsid_ttl_hours * 3600
        log.info("ltsid_proactive_refresh_completed", new_ttl_seconds=new_ttl_seconds)
    except Exception:
        log.error("ltsid_proactive_refresh_failed", exc_info=True)


def create_scheduler(redis_client) -> AsyncIOScheduler:
    """Створює та налаштовує APScheduler для проактивного оновлення LTSID.

    Використовує AsyncIOScheduler (APScheduler 3.x), який інтегрується
    з asyncio event loop FastAPI/uvicorn.

    Інтервал між запусками задається через ENV: LTSID_PROACTIVE_CHECK_INTERVAL_SECONDS
    (дефолт: 1800 секунд = 30 хвилин).

    Args:
        redis_client: Async Redis клієнт (redis.asyncio.Redis), переданий з app.state.redis.

    Returns:
        Налаштований AsyncIOScheduler, ще НЕ запущений.
        Виклик scheduler.start() — в lifespan main.py.

    Example:
        >>> scheduler = create_scheduler(app.state.redis)
        >>> scheduler.start()
        >>> # ... при завершенні:
        >>> scheduler.shutdown(wait=False)
    """
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_and_refresh_ltsid,
        trigger=IntervalTrigger(seconds=settings.ltsid_proactive_check_interval_seconds),
        args=[redis_client],
        id="ltsid_proactive_refresh",
        replace_existing=True,
    )
    return scheduler
