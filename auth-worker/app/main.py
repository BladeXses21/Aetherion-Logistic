from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI

from app.api import health
from app.core.config import settings  # noqa: F401 — validates ENV on startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ініціалізація Redis connection pool при старті сервісу (Story 1.3)
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    # TODO Story 2.1: fetch initial LTSID via Chrome, store in Redis
    # TODO Story 2.2: start proactive refresh scheduler
    # TODO Story 2.3: subscribe to Redis pub/sub channel aetherion:auth:refresh
    # TODO Story 3.5: start fuel price fetcher (async, non-blocking)
    yield
    # Закриття Redis pool при зупинці
    await app.state.redis.aclose()
    # TODO: stop scheduler, unsubscribe pub/sub


app = FastAPI(
    title="Aetherion Auth Worker",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
