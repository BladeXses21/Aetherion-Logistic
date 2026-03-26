"""
get_cargo_detail.py — LangChain інструмент отримання контактних даних вантажів.

Підтримує запит по одному або кількох вантажах одночасно через asyncio.gather.
Повертає список результатів: телефон, ім'я, маршрут, оплата для кожного ID.

Переваги паралельного запиту:
  - Одним викликом агент отримує контакти всіх 3 знайдених вантажів
  - Скорочується кількість round-trip між агентом та lardi-connector
  - QueueManager lardi-connector серіалізує запити — без перевантаження API
"""
from __future__ import annotations

import asyncio
import json

import structlog
from langchain_core.tools import tool

log = structlog.get_logger()

# Максимальна кількість ID в одному запиті (захист від перевантаження черги)
MAX_BATCH_SIZE = 10


def make_get_cargo_detail_tool(lardi_client_factory):
    """
    Фабрика LangChain інструмента get_cargo_contacts з ін'єкцією залежностей.

    Args:
        lardi_client_factory: Callable що повертає LardiConnectorClient context manager.

    Returns:
        Async LangChain tool функція.
    """

    @tool
    async def get_cargo_contacts(cargo_ids: list[int]) -> str:
        """
        Отримує контактні дані та деталі для одного або кількох вантажів одночасно.

        Використовуй цей інструмент коли користувач просить контакт або телефон
        одного чи кількох вантажів зі списку результатів пошуку.
        Передавай всі потрібні ID в одному виклику — це ефективніше ніж кілька окремих запитів.

        Args:
            cargo_ids: Список числових ідентифікаторів вантажів (поле "id" з результатів пошуку).
                Приклад: [204333882919] — один вантаж.
                Приклад: [204333882919, 282377239780, 206668785705] — одразу три.

        Returns:
            JSON рядок зі списком результатів: телефон, ім'я, маршрут, оплата для кожного ID.
        """
        if not cargo_ids:
            return json.dumps({"error": "Список cargo_ids порожній"}, ensure_ascii=False)

        # Обрізаємо до MAX_BATCH_SIZE для безпеки
        ids_to_fetch = cargo_ids[:MAX_BATCH_SIZE]
        if len(cargo_ids) > MAX_BATCH_SIZE:
            log.warning(
                "get_cargo_contacts_batch_truncated",
                requested=len(cargo_ids),
                limit=MAX_BATCH_SIZE,
            )

        async def fetch_one(cargo_id: int) -> dict:
            """
            Запитує деталі одного вантажу.

            При помилці не кидає виняток — повертає dict з полем error,
            щоб часткові помилки не блокували весь батч.

            Args:
                cargo_id: ID вантажу в Lardi.

            Returns:
                Dict з деталями або {"id": ..., "error": "..."} при невдачі.
            """
            try:
                async with lardi_client_factory() as lardi:
                    detail = await lardi.get_cargo_detail(cargo_id)

                # Trimmed поля для LLM (NFR12 — мінімізація даних)
                return {
                    "id": cargo_id,
                    "route_from": detail.get("route_from"),
                    "route_to": detail.get("route_to"),
                    "cargo_name": detail.get("cargo_name"),
                    "body_type": detail.get("body_type"),
                    "loading_date": detail.get("loading_date"),
                    "loading_date_to": detail.get("loading_date_to"),  # кінцевий термін завантаження
                    "cargo_mass_kg": detail.get("cargo_mass_kg"),
                    "distance_km": detail.get("distance_km"),
                    "payment_value": detail.get("payment_value"),
                    "payment_currency": detail.get("payment_currency"),
                    "shipper_name": detail.get("shipper_name"),
                    "shipper_phone": detail.get("shipper_phone"),
                }
            except ValueError:
                log.info("get_cargo_contacts_not_found", cargo_id=cargo_id)
                return {"id": cargo_id, "error": "Вантаж не знайдено або вже неактуальний"}
            except Exception as e:
                log.error("get_cargo_contacts_error", cargo_id=cargo_id, error=str(e))
                return {"id": cargo_id, "error": f"Помилка отримання деталей: {e}"}

        # Паралельний запит до всіх ID — QueueManager в lardi-connector серіалізує їх сам
        results = await asyncio.gather(*[fetch_one(cid) for cid in ids_to_fetch])

        log.info(
            "get_cargo_contacts_batch_done",
            total=len(ids_to_fetch),
            success=sum(1 for r in results if "error" not in r),
            with_phone=sum(1 for r in results if r.get("shipper_phone")),
        )

        # Обгортаємо в [EXTERNAL DATA] для захисту від prompt injection (NFR12)
        return (
            "[EXTERNAL DATA]\n"
            + json.dumps({"contacts": list(results)}, ensure_ascii=False, indent=2)
            + "\n[/EXTERNAL DATA]"
        )

    return get_cargo_contacts
