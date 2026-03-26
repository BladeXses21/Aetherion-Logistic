"""
auth.py — Pydantic схеми для автентифікації (Epic 9.1).

LoginRequest: email + password для POST /api/v1/auth/login
TokenResponse: JWT access_token у відповіді після логіну
UserResponse: публічний профіль користувача (без пароля)
CreateUserRequest: для адмін ендпоінта POST /api/v1/admin/users
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """
    Тіло запиту для логіну.

    Attributes:
        email: Email адреса користувача.
        password: Відкритий пароль (передається через HTTPS).
    """
    email: EmailStr
    password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    """
    Відповідь після успішного логіну.

    Attributes:
        access_token: Підписаний JWT Bearer token.
        token_type: Завжди "bearer" (стандарт OAuth2).
        expires_in: TTL токена в секундах.
    """
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # секунди


class UserResponse(BaseModel):
    """
    Публічний профіль користувача (без пароля).

    Використовується в GET /api/v1/auth/me та списку користувачів.
    """
    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateUserRequest(BaseModel):
    """
    Тіло запиту для створення нового користувача (адмін ендпоінт).

    Attributes:
        email: Email нового користувача.
        password: Початковий пароль (мінімум 8 символів).
        role: Роль — "user" або "admin".
    """
    email: EmailStr
    password: str = Field(min_length=8)
    role: str = Field(default="user", pattern="^(user|admin)$")
