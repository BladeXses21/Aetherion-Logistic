"""health.py — GET /health endpoint для auth-worker.

Перевіряє доступність Redis та наявність LTSID.
Повертає HTTP 200 якщо здоровий, 503 якщо Redis або LTSID недоступні.

Статуси LTSID:
    - "valid"          — збережений у Redis, TTL > 0
    - "in_memory_only" — Redis недоступний, але LTSID є в пам'яті
    - "missing"        — LTSID не отримано (Chrome login провалився або ще не запускався)
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.session.ltsid_store import ltsid_store

log = structlog.get_logger()

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    """Перевірка стану auth-worker та залежностей.

    Перевіряє:
        - Redis: команда PING
        - LTSID: статус зі сховища ltsid_store (valid / in_memory_only / missing)

    Returns:
        HTTP 200 з `{"status": "healthy", "service": "auth-worker",
                     "dependencies": {"redis": "ok", "ltsid": "valid"}}`
        HTTP 503 з `{"status": "unhealthy", ...}` якщо Redis або LTSID недоступні.

    Note:
        Статус "in_memory_only" для LTSID НЕ призводить до 503 — сервіс продовжує
        функціонувати, але без гарантій відновлення TTL після рестарту Redis.
    """
    redis_status = await _check_redis(request.app.state.redis)
    ltsid_status = ltsid_store.health_status

    dependencies = {
        "redis": redis_status,
        "ltsid": ltsid_status,
    }

    # Unhealthy якщо Redis недоступний або LTSID повністю відсутній
    is_healthy = redis_status == "ok" and ltsid_status != "missing"
    http_code = 200 if is_healthy else 503
    status = "healthy" if is_healthy else "unhealthy"

    if not is_healthy:
        log.warning(
            "health_check_degraded",
            service="auth-worker",
            dependencies=dependencies,
        )

    return JSONResponse(
        status_code=http_code,
        content={"status": status, "service": "auth-worker", "dependencies": dependencies},
    )


async def _check_redis(client) -> str:
    """Перевіряє доступність Redis через команду PING.

    Args:
        client: Async Redis клієнт (redis.asyncio.Redis), збережений в app.state.redis.

    Returns:
        "ok" якщо Redis відповів, "error" якщо з'єднання не вдалось.
    """
    try:
        await client.ping()
        return "ok"
    except Exception:
        return "error"
