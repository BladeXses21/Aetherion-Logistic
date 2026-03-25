"""
graph.py — LangGraph скомпільований граф агента Aetherion (singleton).

Реалізує ReAct агент із двома інструментами:
  - search_cargo: пошук вантажів з розрахунком паливної маржі
  - get_cargo_detail: деталі вантажу + телефон вантажовідправника

Граф ініціалізується один раз при старті сервісу та зберігається в app.state.agent_graph.
Streaming реалізований через astream_events(version="v2") (ARCH11).

Функція build_graph() приймає всі залежності через параметри (dependency injection),
що забезпечує тестабельність та уникає глобального стану.
"""
from __future__ import annotations

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from app.core.config import settings
from app.prompts.system import SYSTEM_PROMPT
from app.services.fuel_price import fuel_price_service
from app.services.geo_resolver import geo_resolver
from app.tools.get_cargo_detail import make_get_cargo_detail_tool
from app.tools.search_cargo import make_search_cargo_tool


def build_graph(
    redis_client,
    db_session_factory,
    http_client_factory,
    lardi_client_factory,
):
    """
    Збирає та компілює LangGraph ReAct агент із усіма залежностями.

    Всі залежності передаються через параметри щоб уникнути глобального стану
    та забезпечити можливість підміни в тестах.

    Args:
        redis_client: Async Redis клієнт (для FuelPriceService).
        db_session_factory: Callable що повертає AsyncSession context manager
                            (для GeoResolver → ua_cities запити).
        http_client_factory: Callable що повертає httpx.AsyncClient context manager
                             (для GeoResolver → Nominatim запити).
        lardi_client_factory: Callable що повертає LardiConnectorClient context manager
                              (для пошуку та деталей вантажів).

    Returns:
        Скомпільований LangGraph CompiledGraph готовий до виклику astream_events().

    Приклад:
        graph = build_graph(redis, db_factory, http_factory, lardi_factory)
        async for event in graph.astream_events({"messages": [...]}, version="v2"):
            ...
    """
    # Ініціалізуємо LLM (OpenRouter через OpenAI-сумісний інтерфейс)
    llm = ChatOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=0.1,  # Низька температура для стабільного вилучення фільтрів
        timeout=33,        # read timeout (connect=3s вбудований в httpx)
        streaming=True,    # Потрібно для astream_events
    )

    # Ін'єктуємо залежності в інструменти через factory-функції
    search_tool = make_search_cargo_tool(
        geo_resolver=geo_resolver,
        fuel_price_service=fuel_price_service,
        lardi_client_factory=lardi_client_factory,
        db_session_factory=db_session_factory,
        http_client_factory=http_client_factory,
        fuel_consumption=settings.fuel_consumption_l_per_100km,
        overhead_coeff=settings.margin_overhead_coefficient,
        redis_client=redis_client,
    )

    detail_tool = make_get_cargo_detail_tool(
        lardi_client_factory=lardi_client_factory,
    )

    tools = [search_tool, detail_tool]

    # Компілюємо ReAct агент (create_react_agent з LangGraph prebuilt)
    # Системний промпт передається через prompt (в LangGraph 1.1.0 state_modifier → prompt)
    graph = create_react_agent(
        model=llm,
        tools=tools,
        prompt=SYSTEM_PROMPT,
    )

    return graph
