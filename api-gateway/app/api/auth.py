"""
auth.py — Ендпоінти автентифікації (Epic 9.1).

Маршрути:
  POST /api/v1/auth/login   — логін з email/паролем → JWT access token
  GET  /api/v1/auth/me      — інформація про поточного користувача (потребує JWT)

Логіка логіну:
  1. Знаходимо User по email.
  2. Перевіряємо пароль через bcrypt.
  3. Перевіряємо is_active (whitelist — лише активні можуть увійти).
  4. Видаємо JWT з sub=user_id, email, role.

Безпека:
  - Однаковий час відповіді при "user not found" і "wrong password" (prevent user enumeration).
  - Пароль ніколи не логується.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.services.user_service import user_service

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Логін з email та паролем → JWT токен",
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    POST /api/v1/auth/login — Автентифікація через email/пароль.

    Повертає JWT Bearer токен дійсний протягом access_token_expire_minutes.
    Whitelist: тільки користувачі що існують у БД з is_active=True можуть увійти.

    Args:
        body: LoginRequest — email та пароль.
        db: Async сесія PostgreSQL.

    Returns:
        TokenResponse — JWT access_token, token_type="bearer", expires_in.

    Raises:
        HTTPException 401: Невірний email або пароль, або акаунт деактивовано.

    Примітка щодо безпеки: відповідь однакова для "user not found" та "wrong password"
    щоб унеможливити перебір email адрес.
    """
    # Константа для уніфікованого повідомлення про помилку (user enumeration prevention)
    _auth_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Невірний email або пароль.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user = await user_service.get_by_email(db, body.email)

    # Перевіряємо пароль навіть якщо user=None щоб час відповіді був однаковим
    if user is None or not user.hashed_password:
        # Dummy check — захист від timing attack
        verify_password("dummy", "$2b$12$dummy.hash.to.prevent.timing.attack.xxxxx")
        raise _auth_error

    if not verify_password(body.password, user.hashed_password):
        log.info("login_failed_wrong_password", email=body.email)
        raise _auth_error

    if not user.is_active:
        log.warning("login_blocked_inactive_user", email=body.email, user_id=str(user.id))
        raise _auth_error  # Не розкриваємо причину — "user blocked" через той самий 401

    token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
    )

    log.info("login_success", email=user.email, role=user.role, user_id=str(user.id))

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Профіль поточного користувача",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    GET /api/v1/auth/me — Повертає профіль поточного автентифікованого користувача.

    Використовується фронтендом для ініціалізації сесії (отримати роль, email).

    Headers:
        Authorization: Bearer <jwt_token>

    Returns:
        UserResponse — id, email, role, is_active, created_at.

    Raises:
        HTTPException 401: Токен відсутній або невалідний.
    """
    return UserResponse.model_validate(current_user)
