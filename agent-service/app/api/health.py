"""
health.py — GET /health endpoint для agent-service.

Перевіряє доступність Redis. Повертає HTTP 200 якщо здоровий, 503 якщо Redis недоступний.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = structlog.get_logger()

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    """Перевірка стану agent-service та залежностей.

    Перевіряє:
        - Redis: команда PING

    Returns:
        HTTP 200 з {"status": "healthy", "service": "agent-service", "dependencies": {"redis": "ok"}}
        HTTP 503 з {"status": "unhealthy", ...} якщо Redis недоступний
    """
    redis_status = await _check_redis(request.app.state.redis)
    dependencies = {"redis": redis_status}
    all_ok = all(v == "ok" for v in dependencies.values())
    status = "healthy" if all_ok else "unhealthy"
    http_code = 200 if all_ok else 503

    if not all_ok:
        log.warning("health_check_degraded", service="agent-service", dependencies=dependencies)

    return JSONResponse(
        status_code=http_code,
        content={"status": status, "service": "agent-service", "dependencies": dependencies},
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
