"""
admin.py — Адмін ендпоінти api-gateway (Story 2.4).

Проксує запит ручного оновлення LTSID до auth-worker.
Захист: X-API-Key заголовок (той самий ADMIN_API_KEY що й у auth-worker).
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from httpx import AsyncClient

from app.core.config import settings

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# URL auth-worker для проксування
AUTH_WORKER_URL = "http://auth-worker:8003"


@router.patch(
    "/ltsid",
    summary="Ручне оновлення Lardi сесії (проксі до auth-worker)",
)
async def refresh_ltsid(request: Request):
    """
    PATCH /api/v1/admin/ltsid — Проксує запит ручного LTSID refresh до auth-worker.

    Передає X-API-Key заголовок без змін до auth-worker:8003/admin/ltsid/refresh.
    Повертає відповідь auth-worker незміненою (Story 2.4).

    Headers:
        X-API-Key: значення з ENV ADMIN_API_KEY

    Returns:
        Відповідь auth-worker: {"status": "ok", "ltsid_ttl_seconds": ..., "refreshed_at": ...}

    Raises:
        HTTP 401: якщо X-API-Key невалідний або відсутній
        HTTP 503: якщо auth-worker недоступний
    """
    api_key = request.headers.get("x-api-key", "")

    try:
        async with AsyncClient(timeout=90.0) as client:
            response = await client.post(
                f"{AUTH_WORKER_URL}/admin/ltsid/refresh",
                headers={"X-API-Key": api_key},
            )
            return JSONResponse(
                status_code=response.status_code,
                content=response.json(),
            )
    except Exception as e:
        log.error("admin_ltsid_proxy_error", error=str(e), exc_info=True)
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "SERVICE_UNAVAILABLE", "message": "auth-worker недоступний"}},
        )
