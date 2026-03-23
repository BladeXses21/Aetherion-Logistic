"""
Точка входу FastAPI-застосунку lardi-connector.

Lifespan керує:
  - Redis connection pool
  - QueueManager (фоновий BLPOP-консьюмер для Lardi-запитів)
"""

from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI

from app.api import health
from app.core.config import settings  # noqa: F401 — validates ENV on startup
from app.queue.queue_manager import QueueManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ініціалізація Redis connection pool при старті сервісу
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)

    # Запуск менеджера черги (Story 3.1): всі Lardi-запити проходять через нього
    app.state.queue_manager = QueueManager(app.state.redis)
    await app.state.queue_manager.start()

    yield

    # Зупинка менеджера черги та закриття Redis pool
    await app.state.queue_manager.stop()
    await app.state.redis.aclose()


app = FastAPI(
    title="Aetherion Lardi Connector",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
