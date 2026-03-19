"""
health.py — GET /health endpoint для api-gateway.

Перевіряє Redis, Postgres та agent-service. Повертає HTTP 200 якщо всі залежності здорові,
HTTP 503 якщо хоча б одна недоступна.
"""
from __future__ import annotations

import httpx
import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

log = structlog.get_logger()

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    """Перевірка стану api-gateway та трьох залежностей.

    Перевіряє:
        - Redis: команда PING
        - Postgres: SELECT 1 через async engine (легковажна перевірка з'єднання)
        - agent-service: HTTP GET /health з таймаутом 3s

    Returns:
        HTTP 200 з {"status": "healthy", "service": "api-gateway", "dependencies": {...}}
        HTTP 503 якщо будь-яка з залежностей недоступна
    """
    redis_status = await _check_redis(request.app.state.redis)
    postgres_status = await _check_postgres()
    agent_status = await _check_agent_service(settings.agent_service_url)

    dependencies = {
        "redis": redis_status,
        "postgres": postgres_status,
        "agent-service": agent_status,
    }
    all_ok = all(v == "ok" for v in dependencies.values())
    status = "healthy" if all_ok else "unhealthy"
    http_code = 200 if all_ok else 503

    if not all_ok:
        log.warning("health_check_degraded", service="api-gateway", dependencies=dependencies)

    return JSONResponse(
        status_code=http_code,
        content={"status": status, "service": "api-gateway", "dependencies": dependencies},
    )


async def _check_redis(client) -> str:
    """Перевіряє доступність Redis через команду PING.

    Args:
        client: Async Redis client (redis.asyncio.Redis), збережений в app.state.redis.

    Returns:
        "ok" якщо Redis відповів, "error" якщо з'єднання не вдалось.
    """
    try:
        await client.ping()
        return "ok"
    except Exception:
        return "error"


async def _check_postgres() -> str:
    """Перевіряє доступність Postgres через SELECT 1.

    Використовує engine.connect() напряму (не get_db()), оскільки health check
    не є бізнес-операцією і не потребує повноцінного session lifecycle.
    Engine ініціалізований в lifespan (Story 1.2).

    Returns:
        "ok" якщо Postgres відповів, "error" якщо з'єднання не вдалось.
    """
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


async def _check_agent_service(base_url: str) -> str:
    """Перевіряє доступність agent-service через HTTP GET /health.

    Args:
        base_url: Базова URL адреса agent-service (наприклад, "http://agent-service:8001").
                  Береться з settings.agent_service_url.

    Returns:
        "ok" якщо agent-service повернув HTTP 200, "error" в іншому випадку
        або при таймауті (3s).
    """
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{base_url}/health", timeout=3.0)
            return "ok" if r.status_code == 200 else "error"
    except Exception:
        return "error"
