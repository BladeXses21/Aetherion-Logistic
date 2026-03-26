"""
chat.py — Pydantic v2 схеми для чатів та повідомлень (Story 4.4).

Моделі:
  ChatCreate — тіло запиту POST /api/v1/chats
  ChatResponse — відповідь з даними нового чату
  MessageSendRequest — тіло запиту POST /api/v1/chats/{id}/messages
  MessageResponse — метадані збереженого повідомлення
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ChatCreate(BaseModel):
    """
    Тіло запиту для створення нового чату.

    Attributes:
        workspace_id: UUID робочого простору (для multi-tenant). За замовчуванням
                      використовується дефолтний stub workspace.
        title: Назва чату. За замовчуванням "Новий пошук".

    Примітка:
        user_id більше не передається у тілі запиту — читається з JWT токену (Epic 9.1).
    """

    workspace_id: uuid.UUID = Field(
        default_factory=lambda: uuid.UUID("00000000-0000-0000-0000-000000000001"),
        description="UUID робочого простору (MVP: використовується дефолтний stub)",
    )
    title: str = Field(default="Новий пошук", max_length=255)


class ChatResponse(BaseModel):
    """
    Відповідь після створення чату.

    Attributes:
        id: UUID нового чату.
        workspace_id: UUID робочого простору.
        user_id: UUID користувача.
        title: Назва чату.
        created_at: Час створення (UTC).
    """

    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageSendRequest(BaseModel):
    """
    Тіло запиту для відправки повідомлення в чат.

    Attributes:
        content: Текст повідомлення користувача.
    """

    content: str = Field(min_length=1, max_length=10000)


class MessageResponse(BaseModel):
    """
    Метадані збереженого повідомлення (без SSE стріму).

    Attributes:
        id: UUID повідомлення.
        chat_id: UUID чату.
        role: Роль відправника ("user" або "assistant").
        status: Статус ("complete", "streaming", "incomplete").
        created_at: Час створення.
    """

    id: uuid.UUID
    chat_id: uuid.UUID
    role: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
