from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI

from app.api import health
from app.core.config import settings  # noqa: F401 — validates ENV on startup
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ініціалізація Redis connection pool при старті сервісу (Story 1.3)
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    yield
    # Закриття DB engine (Story 1.2) та Redis pool (Story 1.3) при зупинці
    await engine.dispose()
    await app.state.redis.aclose()


app = FastAPI(
    title="Aetherion API Gateway",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
