"""
agent.py — Pydantic v2 схеми для API агента (Story 4.3).

StreamRequest — тіло запиту для POST /stream.
Відповідь — SSE потік подій у форматі JSON рядків.
"""
from __future__ import annotations

from pydantic import BaseModel


class MessageHistory(BaseModel):
    """
    Одне повідомлення з історії чату для передачі в агент.

    Attributes:
        role: Роль відправника ("user" або "assistant").
        content: Текстовий вміст повідомлення.
    """

    role: str  # "user" або "assistant"
    content: str


class StreamRequest(BaseModel):
    """
    Тіло запиту для POST /stream ендпоінту агента.

    Attributes:
        message: Поточне повідомлення користувача (запит природною мовою).
        chat_id: Ідентифікатор чату (передається для логування та контексту).
        history: Попередні повідомлення чату для підтримки контексту розмови.
    """

    message: str
    chat_id: str | None = None
    history: list[MessageHistory] | None = None
