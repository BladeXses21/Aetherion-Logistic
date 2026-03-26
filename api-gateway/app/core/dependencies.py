"""
dependencies.py — FastAPI залежності для автентифікації (Epic 9.1).

Надає:
  - get_current_user: витягує та валідує JWT з Authorization заголовка,
    повертає User об'єкт. Кидає 401 якщо токен відсутній або невалідний.
  - require_admin: те саме, але додатково вимагає role="admin". Кидає 403.

Використання в ендпоінтах:
    @router.get("/protected")
    async def protected(user: User = Depends(get_current_user)):
        return {"email": user.email}
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.models.user import User
from app.db.session import get_db

log = structlog.get_logger()

# HTTPBearer схема — витягує токен з "Authorization: Bearer <token>"
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI залежність — повертає поточного автентифікованого користувача.

    Алгоритм:
      1. Читає Bearer токен з Authorization заголовка.
      2. Декодує JWT через decode_access_token.
      3. Завантажує User з БД по sub (UUID).
      4. Перевіряє is_active.

    Args:
        credentials: Bearer токен з HTTP заголовка (або None якщо відсутній).
        db: Async сесія PostgreSQL.

    Returns:
        User — об'єкт активного користувача.

    Raises:
        HTTPException 401: Токен відсутній, невалідний, прострочений або користувач не знайдений.
        HTTPException 403: Користувач заблокований (is_active=False).
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Необхідна автентифікація. Передайте Bearer токен.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалідний або прострочений токен.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Некоректний payload токена.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Некоректний ідентифікатор користувача у токені.",
        )

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()

    if user is None:
        log.warning("jwt_user_not_found", user_id=user_id_str)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Користувача не знайдено.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Обліковий запис заблокований.",
        )

    return user


async def require_admin(
    user: User = Depends(get_current_user),
) -> User:
    """
    FastAPI залежність — вимагає role="admin".

    Надбудова над get_current_user — спочатку перевіряє JWT (401),
    потім перевіряє роль (403).

    Args:
        user: Поточний автентифікований користувач.

    Returns:
        User — якщо role="admin".

    Raises:
        HTTPException 403: Якщо роль не "admin".
    """
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ тільки для адміністраторів.",
        )
    return user
