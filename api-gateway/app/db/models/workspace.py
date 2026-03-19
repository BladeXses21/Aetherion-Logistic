from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.chat import Chat
    from app.db.models.workspace_user import WorkspaceUser


class Workspace(Base, TimestampMixin):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    members: Mapped[list[WorkspaceUser]] = relationship(
        "WorkspaceUser", back_populates="workspace", cascade="all, delete-orphan"
    )
    chats: Mapped[list[Chat]] = relationship(
        "Chat", back_populates="workspace", cascade="all, delete-orphan"
    )
