"""
main.py — FastAPI додаток agent-service.

Lifecycle (lifespan):
  1. Ініціалізація Redis connection pool
  2. Ініціалізація DB engine (для geo_resolver → ua_cities)
  3. Збірка та компіляція LangGraph графу (singleton)
  4. Очищення ресурсів при зупинці
"""
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI
from httpx import AsyncClient

from app.api import health, stream
from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine
from app.graph.graph import build_graph
from app.services.lardi_client import LardiConnectorClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управляє lifecycle ресурсів agent-service.

    Startup:
      - Підключення до Redis
      - Ініціалізація singleton LangGraph графу з усіма залежностями

    Shutdown:
      - Закриття Redis pool
      - Dispose DB engine
    """
    # Ініціалізація Redis connection pool
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)

    # Фабрики для LangGraph tools (dependency injection)
    # db_session_factory — повертає async context manager для AsyncSession
    def db_session_factory():
        return AsyncSessionLocal()

    # http_client_factory — повертає async context manager для httpx.AsyncClient
    def http_client_factory():
        return AsyncClient(
            headers={"User-Agent": settings.nominatim_user_agent},
            timeout=10.0,
        )

    # lardi_client_factory — повертає async context manager для LardiConnectorClient
    def lardi_client_factory():
        return LardiConnectorClient(settings.lardi_connector_url)

    # Компілюємо LangGraph граф (singleton) — один раз при старті
    app.state.agent_graph = build_graph(
        redis_client=app.state.redis,
        db_session_factory=db_session_factory,
        http_client_factory=http_client_factory,
        lardi_client_factory=lardi_client_factory,
    )

    yield

    # Закриття ресурсів при зупинці сервісу
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(
    title="Aetherion Agent Service",
    version="0.1.0",
    description=(
        "AI-агент для пошуку вантажів на Lardi-Trans з розрахунком паливної маржі. "
        "Реалізований на базі LangGraph ReAct архітектури з SSE streaming."
    ),
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(stream.router)
