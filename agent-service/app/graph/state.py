"""
state.py — Визначення стану LangGraph агента (AgentState).

AgentState — центральна структура даних що передається між вузлами графу.
Кожен вузол може читати та оновлювати окремі поля стану.

Поле messages використовує оператор add_messages (накопичення повідомлень),
решта полів — звичайне присвоєння (перезапис).
"""
from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """
    Стан агента що передається між вузлами LangGraph.

    Attributes:
        messages: Список повідомлень (user/assistant/tool). Використовує
                  оператор add_messages — нові повідомлення додаються,
                  а не перезаписують попередні.
        extracted_filters: Структуровані фільтри вилучені LLM з природної мови.
                           Формат: {from_location, to_location, body_type, min_weight, ...}
        search_results: Результати пошуку вантажів після виклику search_cargo інструмента.
                        Список словників з полями id, route, margin тощо.
        selected_cargo_id: ID конкретного вантажу обраного для детального перегляду.
        error: Рядок з описом помилки якщо щось пішло не так під час виконання.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    extracted_filters: dict[str, Any] | None
    search_results: list[dict[str, Any]] | None
    selected_cargo_id: int | None
    error: str | None
