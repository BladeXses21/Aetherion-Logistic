"""
admin.py — Адмін ендпоінти api-gateway (Story 2.4 + Epic 9.1).

Маршрути:
  PATCH /api/v1/admin/ltsid          — ручне оновлення Lardi сесії (Story 2.4)
  POST  /api/v1/admin/users          — створити нового користувача (whitelist)
  GET   /api/v1/admin/users          — список всіх користувачів
  DELETE /api/v1/admin/users/{id}    — деактивувати користувача (soft-delete)

Захист: X-API-Key заголовок для всіх адмін ендпоінтів.
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.schemas.auth import CreateUserRequest, UserResponse
from app.services.user_service import user_service

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# URL auth-worker для проксування
AUTH_WORKER_URL = "http://auth-worker:8003"


def _check_admin_api_key(request: Request) -> None:
    """
    Перевіряє наявність та коректність X-API-Key заголовка.

    Цей захист використовується для всіх адмін ендпоінтів.
    У Phase 2 адміни також можуть автентифікуватись через JWT role="admin".

    Args:
        request: HTTP запит FastAPI.

    Raises:
        HTTPException 401: Якщо X-API-Key відсутній або невалідний.
    """
    api_key = request.headers.get("x-api-key", "")
    if api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалідний або відсутній X-API-Key.",
        )


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


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=201,
    summary="Додати користувача у whitelist (створити акаунт)",
)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    POST /api/v1/admin/users — Створює нового користувача (додає у whitelist).

    Тільки адміністратори (X-API-Key) можуть створювати нових користувачів.
    Реєстрація через публічний інтерфейс заблокована — лише через цей ендпоінт.

    Headers:
        X-API-Key: значення з ENV ADMIN_API_KEY

    Args:
        body: CreateUserRequest — email, password, role.
        request: HTTP запит (для перевірки API ключа).
        db: Async сесія PostgreSQL.

    Returns:
        UserResponse — профіль нового користувача.

    Raises:
        HTTP 401: Невалідний X-API-Key.
        HTTP 409: Користувач з таким email вже існує.
    """
    _check_admin_api_key(request)

    try:
        user = await user_service.create_user(
            db=db,
            email=body.email,
            password=body.password,
            role=body.role,
        )
        await db.commit()
        log.info("admin_user_created", email=user.email, role=user.role, user_id=str(user.id))
        return UserResponse.model_validate(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Користувач з email '{body.email}' вже існує.",
        )


@router.get(
    "/users",
    response_model=list[UserResponse],
    summary="Список всіх користувачів (whitelist)",
)
async def list_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> list[UserResponse]:
    """
    GET /api/v1/admin/users — Повертає список всіх користувачів системи.

    Використовується адмін панеллю для управління whitelist.

    Headers:
        X-API-Key: значення з ENV ADMIN_API_KEY

    Returns:
        Список UserResponse відсортованих за датою створення.

    Raises:
        HTTP 401: Невалідний X-API-Key.
    """
    _check_admin_api_key(request)
    users = await user_service.list_users(db)
    return [UserResponse.model_validate(u) for u in users]


@router.delete(
    "/users/{user_id}",
    status_code=204,
    summary="Деактивувати користувача (видалити з whitelist)",
)
async def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    DELETE /api/v1/admin/users/{user_id} — Деактивує користувача (soft-delete).

    Встановлює is_active=False. Користувач не може увійти після цього.
    Дані (чати, повідомлення) зберігаються.

    Headers:
        X-API-Key: значення з ENV ADMIN_API_KEY

    Args:
        user_id: UUID користувача для деактивації.

    Raises:
        HTTP 401: Невалідний X-API-Key.
        HTTP 404: Користувача не знайдено.
    """
    _check_admin_api_key(request)

    user = await user_service.deactivate_user(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Користувача {user_id} не знайдено.",
        )
    await db.commit()
    log.info("admin_user_deactivated", user_id=str(user_id))
