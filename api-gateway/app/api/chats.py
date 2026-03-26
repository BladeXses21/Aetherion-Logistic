"""
chats.py — API ендпоінти для чатів та повідомлень (Story 4.4 + Epic 9.1).

Ендпоінти:
  POST /api/v1/chats                           — створити новий чат (захищено JWT)
  GET  /api/v1/chats/{chat_id}                 — отримати інформацію про чат (захищено JWT)
  POST /api/v1/chats/{chat_id}/messages        — відправити повідомлення (SSE streaming, JWT)

Логіка POST .../messages:
  1. Перевірка JWT → 401 якщо токен відсутній або невалідний
  2. Перевірка aetherion:agent:busy Redis ключа → 429 якщо зайнятий
  3. Збереження повідомлення користувача (status="complete")
  4. Створення placeholder відповіді асистента (status="streaming")
  5. Проксування запиту до agent-service POST /stream
  6. Forwarding SSE стріму клієнту
  7. Після завершення → оновлення статусу placeholder (complete/incomplete)

Аутентифікація: JWT через get_current_user dependency (Epic 9.1).
"""
from __future__ import annotations

import json
import uuid
from typing import AsyncGenerator

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.errors import ErrorCode
from app.db.models.user import User
from app.db.session import AsyncSessionLocal, get_db
from app.schemas.chat import ChatCreate, ChatResponse, MessageSendRequest
from app.services.chat_service import chat_service

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/chats", tags=["chats"])

# Redis ключ busy lock (повинен співпадати з agent-service)
AGENT_BUSY_KEY = "aetherion:agent:busy"

# Таймаут підключення до agent-service
AGENT_CONNECT_TIMEOUT = 5.0
AGENT_READ_TIMEOUT = 90.0  # максимальний час відповіді агента


@router.post(
    "",
    response_model=ChatResponse,
    status_code=201,
    summary="Створити новий чат",
)
async def create_chat(
    body: ChatCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    """
    POST /api/v1/chats — Створює новий чат для поточного автентифікованого користувача.

    user_id береться з JWT токена (current_user.id).
    workspace_id залишається опційним у body (для майбутньої multi-workspace підтримки).

    Args:
        body: ChatCreate — workspace_id (опційно), title.
        db: Async сесія PostgreSQL.
        current_user: Поточний JWT-автентифікований користувач.

    Returns:
        ChatResponse — дані нового чату включно з UUID.

    Raises:
        HTTPException 401: Токен відсутній або невалідний.
    """
    chat = await chat_service.create_chat(
        db=db,
        workspace_id=body.workspace_id,
        user_id=current_user.id,  # JWT → user_id замість stub
        title=body.title,
    )
    return ChatResponse.model_validate(chat)


@router.post(
    "/{chat_id}/messages",
    summary="Відправити повідомлення та отримати SSE відповідь агента",
)
async def send_message(
    chat_id: uuid.UUID,
    body: MessageSendRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    POST /api/v1/chats/{chat_id}/messages — Відправляє повідомлення та повертає SSE стрім.

    Послідовність:
      1. Перевіряє aetherion:agent:busy → 429 якщо агент зайнятий
      2. Зберігає повідомлення користувача (role="user", status="complete")
      3. Створює placeholder для відповіді асистента (status="streaming")
      4. Отримує історію чату для контексту агента
      5. Проксує запит до agent-service POST /stream
      6. Стрімить SSE події клієнту
      7. Після завершення — оновлює статус placeholder у БД

    Returns:
        StreamingResponse з Content-Type: text/event-stream

    Raises:
        HTTPException 429: Агент зайнятий обробкою іншого запиту.
        HTTPException 503: agent-service недоступний.
    """
    redis = request.app.state.redis

    # Перевіряємо busy lock
    is_busy = await redis.exists(AGENT_BUSY_KEY)
    if is_busy:
        log.info("agent_busy_rejected", chat_id=str(chat_id))
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "code": ErrorCode.AGENT_BUSY,
                    "message": "Agent is processing another request",
                    "details": {"retry_after_seconds": 3},
                }
            },
        )

    # Зберігаємо повідомлення користувача
    user_message = await chat_service.save_user_message(
        db=db,
        chat_id=chat_id,
        content=body.content,
    )

    # Створюємо placeholder для відповіді асистента
    assistant_placeholder = await chat_service.create_assistant_placeholder(
        db=db,
        chat_id=chat_id,
    )
    await db.commit()

    # Отримуємо історію чату для контексту (останні 20 повідомлень)
    history = await chat_service.get_chat_history(db=db, chat_id=chat_id, limit=20)

    # Формуємо history list для agent-service (без поточного повідомлення)
    history_for_agent = [
        {"role": msg.role, "content": msg.content}
        for msg in history
        if msg.id != user_message.id  # поточне вже в message
    ]

    # Payload для agent-service
    agent_payload = {
        "message": body.content,
        "chat_id": str(chat_id),
        "history": history_for_agent,
    }

    async def stream_and_persist() -> AsyncGenerator[bytes, None]:
        """
        Генератор що проксує SSE стрім від agent-service та акумулює відповідь.

        Накопичує всі токени в буфер для збереження в БД після завершення.
        При перериванні з'єднання — зберігає частковий контент зі статусом "incomplete".
        """
        full_content = ""
        final_status = "incomplete"  # за замовчуванням — захист від переривання

        try:
            async with AsyncClient(
                timeout=AGENT_READ_TIMEOUT,
                follow_redirects=True,
            ) as client:
                async with client.stream(
                    "POST",
                    f"{settings.agent_service_url}/stream",
                    json=agent_payload,
                ) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        log.error(
                            "agent_service_error",
                            status=response.status_code,
                            chat_id=str(chat_id),
                        )
                        error_event = {
                            "type": "error",
                            "code": ErrorCode.SERVICE_UNAVAILABLE,
                            "message": "agent-service повернув помилку",
                        }
                        yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n".encode()
                        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n".encode()
                        return

                    # Стрімимо SSE від agent-service до клієнта
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            event_data = line[6:]
                            yield f"data: {event_data}\n\n".encode()

                            # Акумулюємо токени для збереження в БД
                            try:
                                event_obj = json.loads(event_data)
                                if event_obj.get("type") == "token":
                                    full_content += event_obj.get("content", "")
                                elif event_obj.get("type") == "done":
                                    final_status = "complete"
                            except json.JSONDecodeError:
                                pass

        except Exception as e:
            log.error(
                "agent_stream_proxy_error",
                chat_id=str(chat_id),
                error=str(e),
                exc_info=True,
            )
            error_event = {
                "type": "error",
                "code": ErrorCode.SERVICE_UNAVAILABLE,
                "message": f"Помилка підключення до агента: {e}",
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n".encode()
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n".encode()

        finally:
            # Оновлюємо placeholder у БД незалежно від результату
            try:
                async with AsyncSessionLocal() as update_db:
                    await chat_service.update_assistant_message(
                        db=update_db,
                        message_id=assistant_placeholder.id,
                        content=full_content,
                        status=final_status,
                    )
                    await update_db.commit()

                log.info(
                    "assistant_message_persisted",
                    chat_id=str(chat_id),
                    status=final_status,
                    content_len=len(full_content),
                )
            except Exception:
                log.error(
                    "assistant_message_persist_failed",
                    chat_id=str(chat_id),
                    exc_info=True,
                )

    return StreamingResponse(
        stream_and_persist(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
