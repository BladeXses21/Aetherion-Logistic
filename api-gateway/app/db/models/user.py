from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.chat import Chat
    from app.db.models.workspace_user import WorkspaceUser


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str | None] = mapped_column(Text, nullable=True)

    chats: Mapped[list[Chat]] = relationship("Chat", back_populates="user")
    workspaces: Mapped[list[WorkspaceUser]] = relationship(
        "WorkspaceUser", back_populates="user"
    )
