"""
get_cargo_detail.py — LangChain інструмент отримання деталей вантажу та контакту вантажовідправника.

Викликає lardi-connector GET /cargo/{id} та повертає:
  - Маршрут, тип вантажу, дата завантаження
  - Контактний телефон вантажовідправника (shipper_phone)
  - Ім'я контакту (shipper_name)

В LLM контекст передаються ТІЛЬКИ trimmed поля (NFR12: мінімізація даних).
LTSID залишається виключно в lardi-connector.
"""
from __future__ import annotations

import json

import structlog
from langchain_core.tools import tool

log = structlog.get_logger()


def make_get_cargo_detail_tool(lardi_client_factory):
    """
    Фабрика LangChain інструмента get_cargo_detail з ін'єкцією залежностей.

    Args:
        lardi_client_factory: Callable що повертає LardiConnectorClient context manager.

    Returns:
        Async LangChain tool функція.
    """

    @tool
    async def get_cargo_detail(cargo_id: int) -> str:
        """
        Отримує детальну інформацію про конкретний вантаж включно з контактом вантажовідправника.

        Використовуй цей інструмент коли користувач просить контакт або повні деталі
        про конкретний вантаж зі списку результатів пошуку.

        Args:
            cargo_id: Числовий ідентифікатор вантажу (з поля "id" в результатах пошуку).

        Returns:
            JSON рядок з деталями вантажу та контактним телефоном.
        """
        try:
            async with lardi_client_factory() as lardi:
                detail = await lardi.get_cargo_detail(cargo_id)
        except ValueError as e:
            # 404 — вантаж не знайдено
            log.info("get_cargo_detail_not_found", cargo_id=cargo_id)
            return json.dumps(
                {"error": str(e)},
                ensure_ascii=False,
            )
        except Exception as e:
            log.error("get_cargo_detail_error", cargo_id=cargo_id, error=str(e))
            return json.dumps(
                {"error": f"Помилка отримання деталей вантажу {cargo_id}: {e}"},
                ensure_ascii=False,
            )

        # Trimmed поля для LLM контексту — повний JSON НЕ передається (Story 4.2)
        trimmed = {
            "id": detail.get("id"),
            "route_from": detail.get("route_from"),
            "route_to": detail.get("route_to"),
            "body_type": detail.get("body_type"),
            "cargo_name": detail.get("cargo_name"),
            "loading_date": detail.get("loading_date"),
            "shipper_phone": detail.get("shipper_phone"),
            "shipper_name": detail.get("shipper_name"),
        }

        log.info(
            "get_cargo_detail_success",
            cargo_id=cargo_id,
            has_phone=trimmed["shipper_phone"] is not None,
        )

        # Обгортаємо в [EXTERNAL DATA] (NFR12)
        return (
            "[EXTERNAL DATA]\n"
            + json.dumps(trimmed, ensure_ascii=False, indent=2)
            + "\n[/EXTERNAL DATA]"
        )

    return get_cargo_detail
