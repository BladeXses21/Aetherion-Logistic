"""
stream.py — SSE streaming ендпоінт агента (Story 4.3 + Story 4.4).

POST /stream:
  - Встановлює Redis busy lock (aetherion:agent:busy) на початку
  - Запускає LangGraph агент через astream_events(version="v2")
  - Маппить події LangGraph → SSE JSON рядки:
      on_tool_start      → {"type": "status", "message": "..."}
      on_chat_model_stream → {"type": "token", "content": "..."}
      stream end         → {"type": "done"}
  - Знімає busy lock при завершенні (успіх або помилка)

SSE формат:
  data: {"type": "status", "message": "🔍 Розбираємо запит..."}\n\n
  data: {"type": "token", "content": "Знайшов "}\n\n
  ...
  data: {"type": "done"}\n\n
"""
from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage

from app.core.config import settings
from app.core.errors import ErrorCode
from app.schemas.agent import StreamRequest

log = structlog.get_logger()

router = APIRouter()

# Redis ключ для busy lock (Story 4.4)
AGENT_BUSY_KEY = "aetherion:agent:busy"

# Статусні повідомлення що відправляються при виклику інструментів
_TOOL_STATUS_MESSAGES: dict[str, str] = {
    "search_cargo": "📦 Шукаємо вантажі в Lardi...",
    "get_cargo_detail": "📞 Отримуємо деталі вантажу...",
}


async def _stream_agent(request: StreamRequest, app_state):
    """
    Async генератор SSE подій з LangGraph агента.

    Встановлює busy lock, запускає агент, маппить події LangGraph в SSE рядки,
    знімає lock після завершення.

    Args:
        request: Вхідний StreamRequest з повідомленням та історією.
        app_state: FastAPI app.state з redis та agent_graph.

    Yields:
        SSE рядки у форматі "data: {...}\n\n"
    """
    redis = app_state.redis
    graph = app_state.agent_graph

    # Встановлюємо busy lock (Story 4.4)
    await redis.set(
        AGENT_BUSY_KEY,
        "1",
        nx=True,
        ex=settings.agent_busy_ttl_seconds,
    )

    # Будуємо список повідомлень для LangGraph
    messages = []
    if request.history:
        for msg in request.history:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))

    messages.append(HumanMessage(content=request.message))

    full_response = ""
    last_tool_name: str | None = None

    try:
        # Перший статус — завжди відправляємо одразу (NFR1: ≤3с перший chunk)
        yield f"data: {json.dumps({'type': 'status', 'message': '🔍 Розбираємо запит...'}, ensure_ascii=False)}\n\n"

        # Запускаємо LangGraph streaming з version="v2" (ARCH11)
        async for event in graph.astream_events(
            {"messages": messages},
            version="v2",
        ):
            event_type = event.get("event", "")
            event_name = event.get("name", "")
            event_data = event.get("data", {})

            # Початок виклику інструмента → статусне повідомлення
            if event_type == "on_tool_start":
                tool_name = event_name
                last_tool_name = tool_name
                status_msg = _TOOL_STATUS_MESSAGES.get(
                    tool_name, f"⚙️ Виконуємо {tool_name}..."
                )
                yield f"data: {json.dumps({'type': 'status', 'message': status_msg}, ensure_ascii=False)}\n\n"

                # Якщо пошук — додаємо повідомлення про розрахунок маржі
                if tool_name == "search_cargo":
                    yield f"data: {json.dumps({'type': 'status', 'message': '💰 Розраховуємо паливну маржу...'}, ensure_ascii=False)}\n\n"

            # Стрімінг токенів відповіді LLM
            elif event_type == "on_chat_model_stream":
                chunk = event_data.get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    content = chunk.content
                    if isinstance(content, str) and content:
                        full_response += content
                        yield f"data: {json.dumps({'type': 'token', 'content': content}, ensure_ascii=False)}\n\n"

        # Завершення стріму
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    except asyncio.TimeoutError:
        log.warning("agent_stream_timeout", chat_id=request.chat_id)
        error_event = {
            "type": "error",
            "code": ErrorCode.AGENT_TIMEOUT,
            "message": "⚠️ Час очікування вичерпано. Спробуй ще раз.",
        }
        yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    except Exception as e:
        log.error("agent_stream_error", chat_id=request.chat_id, error=str(e), exc_info=True)
        # Перевіряємо чи це LLM помилка
        error_str = str(e).lower()
        if "503" in error_str or "timeout" in error_str or "unavailable" in error_str:
            error_event = {
                "type": "error",
                "code": ErrorCode.LLM_UNAVAILABLE,
                "message": "Service temporarily unavailable",
            }
        else:
            error_event = {
                "type": "error",
                "code": ErrorCode.INTERNAL_ERROR,
                "message": f"Помилка агента: {e}",
            }
        yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    finally:
        # Знімаємо busy lock незалежно від результату (Story 4.4)
        try:
            await redis.delete(AGENT_BUSY_KEY)
        except Exception:
            log.warning("agent_busy_lock_delete_failed", exc_info=True)


@router.post(
    "/stream",
    summary="Streaming запит до AI-агента",
    description=(
        "Відправляє повідомлення користувача до LangGraph агента та повертає SSE потік. "
        "Перший chunk завжди надходить протягом ≤3с. "
        "Кожна SSE подія є JSON об'єктом з полем 'type': 'status'|'token'|'error'|'done'."
    ),
)
async def stream_agent(body: StreamRequest, request: Request):
    """
    POST /stream — SSE ендпоінт LangGraph агента.

    Приймає повідомлення користувача та опціональну історію чату.
    Повертає Server-Sent Events потік із розмірковуванням агента та фінальною відповіддю.

    Формат SSE подій:
      {"type": "status", "message": "📦 Шукаємо вантажі..."}  — статус операції
      {"type": "token", "content": "Знайшов 45 вантажів..."}  — токен відповіді LLM
      {"type": "error", "code": "...", "message": "..."}      — помилка
      {"type": "done"}                                          — завершення стріму

    Встановлює Redis ключ aetherion:agent:busy на час обробки.
    """
    log.info(
        "agent_stream_request",
        chat_id=body.chat_id,
        message_len=len(body.message),
    )

    return StreamingResponse(
        _stream_agent(body, request.app.state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Вимикаємо буферизацію в nginx
        },
    )
