"""main.py — Точка входу сервісу auth-worker.

Відповідає за ініціалізацію Redis, отримання LTSID при старті (Story 2.1),
запуск планувальника оновлення (Story 2.2) та pub/sub підписку (Story 2.3).
"""
from contextlib import asynccontextmanager

import redis.asyncio as redis
import structlog
from fastapi import FastAPI

from app.api import health
from app.browser.lardi_login import fetch_ltsid
from app.core.config import settings  # noqa: F401 — validates ENV on startup
from app.core.errors import ChromeStartupError, LtsidFetchError
from app.scheduler.refresh_scheduler import create_scheduler
from app.session.ltsid_store import ltsid_store

log = structlog.get_logger()


async def _fetch_initial_ltsid(redis_client) -> None:
    """Отримує LTSID через Chrome login та зберігає у Redis при старті сервісу.

    Виконується у lifespan — НЕ зупиняє сервіс у разі помилки.
    При успіху: LTSID зберігається в Redis (або пам'яті якщо Redis недоступний).
    При помилці Chrome: логується ERROR, health буде показувати "ltsid": "missing".

    Args:
        redis_client: Async Redis клієнт для збереження LTSID.
    """
    try:
        ltsid = await fetch_ltsid(
            login=settings.lardi_login,
            password=settings.lardi_password,
            timeout_seconds=settings.chrome_timeout_seconds,
        )
        await ltsid_store.store(redis_client, ltsid, settings.ltsid_ttl_hours)
    except (LtsidFetchError, ChromeStartupError):
        ltsid_store.mark_missing()
        log.error("ltsid_fetch_failed", exc_info=True)
    except Exception:
        ltsid_store.mark_missing()
        log.error("ltsid_fetch_unexpected_error", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan контекст FastAPI — ініціалізація та завершення сервісу."""
    # Ініціалізація Redis connection pool при старті сервісу
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)

    # Story 2.1: отримати початковий LTSID через Chrome login
    await _fetch_initial_ltsid(app.state.redis)

    # Story 2.2: запустити планувальник proactive refresh (APScheduler)
    scheduler = create_scheduler(app.state.redis)
    scheduler.start()
    log.info("ltsid_proactive_refresh_scheduler_started",
             interval_seconds=settings.ltsid_proactive_check_interval_seconds)

    # TODO Story 2.3: підписатись на Redis pub/sub канал aetherion:auth:refresh
    # TODO Story 3.5: запустити fuel price fetcher (async, non-blocking)

    yield

    # Story 2.2: зупинити scheduler
    scheduler.shutdown(wait=False)

    # Закриття Redis pool при зупинці
    await app.state.redis.aclose()
    # TODO Story 2.3: відписатись від pub/sub


app = FastAPI(
    title="Aetherion Auth Worker",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
