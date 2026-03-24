"""
main.py — FastAPI додаток api-gateway.

Lifecycle (lifespan):
  - Ініціалізація Redis connection pool (для busy lock та health checks)
  - Dispose DB engine при зупинці

Ендпоінти:
  GET  /health                           — перевірка стану сервісів
  POST /api/v1/chats                     — створення чату (Story 4.4)
  POST /api/v1/chats/{id}/messages       — SSE стрімінг відповіді агента (Story 4.4)
  PATCH /api/v1/admin/ltsid             — proxy до auth-worker (Story 2.4)
"""
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.admin import router as admin_router
from app.api.chats import router as chats_router
from app.core.config import settings
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Управляє lifecycle ресурсів api-gateway.

    Startup:
      - Підключення до Redis (для busy lock checks та health)

    Shutdown:
      - Закриття Redis pool
      - Dispose DB engine
    """
    # Ініціалізація Redis connection pool
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    yield
    # Закриття ресурсів при зупинці
    await engine.dispose()
    await app.state.redis.aclose()


app = FastAPI(
    title="Aetherion API Gateway",
    version="0.1.0",
    description=(
        "Публічний API gateway для Aetherion 2.0. "
        "Надає chat API з SSE streaming до AI-агента пошуку вантажів."
    ),
    lifespan=lifespan,
)

# CORS middleware (дозволяє Swagger UI та зовнішні клієнти)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(chats_router)
app.include_router(admin_router)
