"""
user.py — SQLAlchemy модель користувача.

Зберігає облікові дані та статус користувача.
Whitelist = наявність запису у таблиці + is_active=True.
role: "user" | "admin" — адміни мають доступ до управлінських ендпоінтів.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.chat import Chat
    from app.db.models.workspace_user import WorkspaceUser


class User(Base, TimestampMixin):
    """
    Модель користувача системи.

    Поля:
        id: UUID первинний ключ.
        email: Email адреса — унікальний ідентифікатор (whitelist).
        hashed_password: bcrypt хеш пароля.
        is_active: True — може логінитись, False — заблокований (soft-delete).
        role: "user" (звичайний) або "admin" (доступ до /admin API).

    Зв'язки:
        chats: Всі чати цього користувача.
        workspaces: Прив'язки до workspace через workspace_users.
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")

    chats: Mapped[list[Chat]] = relationship("Chat", back_populates="user")
    workspaces: Mapped[list[WorkspaceUser]] = relationship(
        "WorkspaceUser", back_populates="user"
    )
