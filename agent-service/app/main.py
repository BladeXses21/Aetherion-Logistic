from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI

from app.api import health
from app.core.config import settings  # noqa: F401 — validates ENV on startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ініціалізація Redis connection pool при старті сервісу (Story 1.3)
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    # TODO Story 3.1/4.1: compile LangGraph graph, init fuel price
    yield
    # Закриття Redis pool при зупинці
    await app.state.redis.aclose()
    # TODO Story 3.1: stop queue consumer


app = FastAPI(
    title="Aetherion Agent Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
