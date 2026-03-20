"""admin.py — POST /admin/ltsid/refresh: ручне оновлення LTSID через Chrome.

Захищений ендпоінт для операторів. Дозволяє примусово запустити Chrome login
та оновити LTSID без перезапуску контейнерів.

Аутентифікація: заголовок `X-API-Key` зі значенням з ENV `ADMIN_API_KEY`.
При невалідному або відсутньому ключі → HTTP 401.
При помилці Chrome → HTTP 503, існуючий LTSID не перезаписується.

Формат успішної відповіді:
    {
        "status": "ok",
        "ltsid_ttl_seconds": 82800,
        "refreshed_at": "2026-03-21T14:00:00+00:00"
    }
"""
from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from app.browser.lardi_login import fetch_ltsid
from app.core.config import settings
from app.core.errors import ChromeStartupError, ErrorCode, LtsidFetchError
from app.session.ltsid_store import LTSID_REDIS_KEY, ltsid_store

log = structlog.get_logger()

router = APIRouter(tags=["admin"])


@router.post("/admin/ltsid/refresh")
async def refresh_ltsid(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> JSONResponse:
    """Ручний запуск Chrome refresh для оновлення LTSID.

    Захищений заголовком X-API-Key (значення з ENV ADMIN_API_KEY).
    Дозволяє відновити сесію Lardi без перезапуску будь-яких контейнерів.

    Args:
        request: FastAPI Request — надає доступ до app.state.redis.
        x_api_key: Значення заголовку X-API-Key (опціональний, None якщо відсутній).

    Returns:
        HTTP 200: `{"status": "ok", "ltsid_ttl_seconds": int, "refreshed_at": str}`
        HTTP 401: `{"error": {"code": "UNAUTHORIZED", "message": "Invalid API key"}}`
        HTTP 503: `{"error": {"code": "LTSID_FETCH_FAILED", "message": "Chrome refresh failed"}}`
    """
    # Валідація API ключа — порівнюємо з settings.admin_api_key
    if not x_api_key or x_api_key != settings.admin_api_key:
        log.warning("ltsid_manual_refresh_unauthorized")
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "code": ErrorCode.UNAUTHORIZED,
                    "message": "Invalid API key",
                }
            },
        )

    # Chrome refresh — запускаємо headless browser та отримуємо новий LTSID
    redis_client = request.app.state.redis
    try:
        ltsid = await fetch_ltsid(
            login=settings.lardi_login,
            password=settings.lardi_password,
            timeout_seconds=settings.chrome_timeout_seconds,
        )
        await ltsid_store.store(redis_client, ltsid, settings.ltsid_ttl_hours)

        # Зчитуємо реальний TTL з Redis після збереження
        ttl = await redis_client.ttl(LTSID_REDIS_KEY)
        refreshed_at = datetime.now(UTC).isoformat()

        log.info("ltsid_manual_refresh_completed", ltsid_ttl_seconds=ttl)
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "ltsid_ttl_seconds": ttl,
                "refreshed_at": refreshed_at,
            },
        )
    except (LtsidFetchError, ChromeStartupError):
        # Chrome відмовив — LTSID НЕ перезаписується, повертаємо 503
        log.error("ltsid_manual_refresh_failed", exc_info=True)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": ErrorCode.LTSID_FETCH_FAILED,
                    "message": "Chrome refresh failed",
                }
            },
        )
