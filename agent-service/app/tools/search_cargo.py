"""
search_cargo.py — LangChain інструмент пошуку вантажів з розрахунком паливної маржі.

Обробляє повний цикл пошуку:
  1. Розв'язання назв міст/країн у DirectionFilter (geo_resolver)
  2. Виклик lardi-connector POST /search
  3. Розрахунок паливної маржі для кожного результату
  4. Ранжування за маржею (спадання), відбір топ-3
  5. Генерація пропозицій при 0 результатах (Story 4.5)

Вхідні дані: природномовні параметри від LLM (назви міст як рядки).
Вихідні дані: JSON рядок з топ-3 результатами обгорнутими в [EXTERNAL DATA].

Все що стосується LTSID залишається в lardi-connector — інструмент не має доступу до сесійних даних.
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from langchain_core.tools import tool

log = structlog.get_logger()

# Пріоритет пропозицій при 0 результатах (Story 4.5)
# route > weight > bodyType > payment
_ZERO_RESULTS_SUGGESTIONS = [
    # (перевірка наявності фільтру, текст пропозиції)
    ("townId_set", "Розшир район завантаження до область або країна"),
    ("mass1_set", "Спробуй зменшити вагу або прибрати фільтр ваги"),
    ("bodyTypeIds_set", "Спробуй без фільтру типу кузова"),
    ("paymentFormIds_set", "Спробуй без фільтру форми оплати"),
]


def _calculate_margin(
    distance_km: float | None,
    payment_value: float | None,
    fuel_price: float | None,
    fuel_consumption: float,
    overhead_coeff: float,
) -> float | None:
    """
    Розраховує приблизну паливну маржу для одного вантажу.

    Формула:
        fuel_cost = distance_km × (fuel_consumption / 100) × fuel_price × overhead_coeff
        margin = payment_value - fuel_cost

    Args:
        distance_km: Відстань маршруту в кілометрах (або None).
        payment_value: Сума оплати в UAH (або None якщо не в UAH / не числова).
        fuel_price: Поточна ціна дизелю в UAH/л (або None).
        fuel_consumption: Витрата палива в л/100км.
        overhead_coeff: Коефіцієнт накладних витрат (1.0 = тільки паливо).

    Returns:
        Маржа в UAH (float) або None якщо розрахунок неможливий.
    """
    if not distance_km or distance_km <= 0:
        return None
    if payment_value is None:
        return None
    if fuel_price is None:
        return None

    fuel_cost = distance_km * (fuel_consumption / 100.0) * fuel_price * overhead_coeff
    return round(payment_value - fuel_cost, 2)


def _build_zero_results_suggestion(search_request: dict) -> str:
    """
    Генерує конкретну пропозицію для розширення фільтрів при 0 результатах.

    Пріоритет: route (townId) > weight (mass1) > bodyType > payment.
    Перевіряє наявність фільтрів у вихідному запиті та повертає першу доречну пораду.

    Args:
        search_request: Словник запиту що був відправлений в lardi-connector.

    Returns:
        Рядок з конкретною порадою (ніколи не порожній).
    """
    direction_from = search_request.get("directionFrom", {})
    direction_rows = direction_from.get("directionRows", [])
    has_town_id = any(row.get("townId") for row in direction_rows)

    has_mass1 = search_request.get("mass1") is not None
    has_body_type = bool(search_request.get("bodyTypeIds"))
    has_payment_form = bool(search_request.get("paymentFormIds"))

    if has_town_id:
        return "Розшир район завантаження до область або країна"
    if has_mass1:
        return "Спробуй зменшити вагу або прибрати фільтр ваги"
    if has_body_type:
        return "Спробуй без фільтру типу кузова"
    if has_payment_form:
        return "Спробуй без фільтру форми оплати"

    return "Спробуй розширити маршрут до рівня країни або прибрати деякі фільтри"


def make_search_cargo_tool(
    geo_resolver,
    fuel_price_service,
    lardi_client_factory,
    db_session_factory,
    http_client_factory,
    fuel_consumption: float,
    overhead_coeff: float,
    redis_client,
):
    """
    Фабрика LangChain інструмента search_cargo з ін'єкцією залежностей.

    Повертає async функцію-інструмент що замикається на переданих сервісах.
    Використовується в graph.py при ініціалізації графу.

    Args:
        geo_resolver: Екземпляр GeoResolver для розв'язання назв місць.
        fuel_price_service: FuelPriceService для отримання ціни дизелю.
        lardi_client_factory: Callable що повертає LardiConnectorClient.
        db_session_factory: Async callable що повертає AsyncSession.
        http_client_factory: Async callable що повертає httpx.AsyncClient.
        fuel_consumption: Витрата палива л/100км (з ENV).
        overhead_coeff: Коефіцієнт накладних витрат (з ENV).
        redis_client: Async Redis клієнт для отримання ціни палива.

    Returns:
        Async LangChain tool функція.
    """

    @tool
    async def search_cargo(
        from_location: str,
        to_location: str,
        body_type: str | None = None,
        load_type: str | None = None,
        min_weight: float | None = None,
        max_weight: float | None = None,
        load_date_from: str | None = None,
        load_date_to: str | None = None,
    ) -> str:
        """
        Шукає вантажі на Lardi-Trans та ранжує за паливною маржею.

        Використовуй цей інструмент коли користувач хоче знайти вантаж.
        Передавай назви міст і країн точно як надав користувач (наприклад "Київ", "Польща").

        Args:
            from_location: Місто або країна відправлення (рядок, наприклад "Київ", "Харків", "Україна").
            to_location: Місто або країна призначення (рядок, наприклад "Варшава", "Польща", "Германія").
            body_type: Тип кузова українською (наприклад "тент", "реф", "бус"). Необов'язково.
            load_type: Тип завантаження українською (наприклад "задня", "верхня", "бічна", "гідроборт"). Необов'язково.
            min_weight: Мінімальна вага вантажу в тоннах. Необов'язково.
            max_weight: Максимальна вага вантажу в тоннах. Необов'язково.
            load_date_from: Початкова дата завантаження у форматі ISO 8601 (YYYY-MM-DD). Необов'язково.
            load_date_to: Кінцева дата завантаження у форматі ISO 8601 (YYYY-MM-DD). Необов'язково.

        Returns:
            JSON рядок з топ-3 результатами за паливною маржею або пропозиціями при 0 результатах.
        """
        from app.constants import BODY_TYPE_UA_TO_ID, LOAD_TYPE_UA_TO_CODE

        # Отримуємо поточну ціну палива
        fuel_price = await fuel_price_service.get_price(redis_client)

        # Розв'язуємо географію через geo_resolver
        async with db_session_factory() as db:
            async with http_client_factory() as http_client:
                from_direction = await geo_resolver.resolve(
                    from_location, db, http_client
                )
                to_direction = await geo_resolver.resolve(
                    to_location, db, http_client
                )

        if not from_direction or not to_direction:
            failed = from_location if not from_direction else to_location
            log.warning(
                "search_cargo_geo_resolution_failed",
                from_location=from_location,
                to_location=to_location,
                failed=failed,
            )
            return json.dumps(
                {
                    "error": f"Не вдалось розпізнати місце: '{failed}'. "
                    "Спробуй вказати більш точну назву міста або країни."
                },
                ensure_ascii=False,
            )

        # Розв'язуємо тип кузова
        body_type_ids: list[int] | None = None
        if body_type:
            resolved_id = BODY_TYPE_UA_TO_ID.get(body_type.lower().strip())
            if resolved_id:
                body_type_ids = [int(resolved_id)]
            else:
                log.warning(
                    "intent_filter_cast_failed",
                    field="bodyType",
                    raw_value=body_type,
                )

        # Розв'язуємо тип завантаження (задня, верхня, бічна тощо)
        load_type_codes: list[str] | None = None
        if load_type:
            resolved_code = LOAD_TYPE_UA_TO_CODE.get(load_type.lower().strip())
            if resolved_code:
                load_type_codes = [resolved_code]
            else:
                log.warning(
                    "intent_filter_cast_failed",
                    field="loadType",
                    raw_value=load_type,
                )

        # Формуємо запит до lardi-connector
        search_request: dict[str, Any] = {
            "directionFrom": from_direction,
            "directionTo": to_direction,
            "size": 50,  # отримуємо більше для кращого ранжування
        }
        if body_type_ids:
            search_request["bodyTypeIds"] = body_type_ids
        if load_type_codes:
            search_request["loadTypes"] = load_type_codes
        if min_weight is not None:
            search_request["mass1"] = min_weight
        if max_weight is not None:
            search_request["mass2"] = max_weight
        if load_date_from:
            search_request["dateFromISO"] = load_date_from
        if load_date_to:
            search_request["dateToISO"] = load_date_to

        # Викликаємо lardi-connector
        try:
            async with lardi_client_factory() as lardi:
                search_response = await lardi.search(search_request)
        except Exception as e:
            log.error("search_cargo_lardi_error", error=str(e), exc_info=True)
            return json.dumps(
                {"error": f"Помилка пошуку в Lardi: {e}"},
                ensure_ascii=False,
            )

        proposals: list[dict] = search_response.get("proposals", [])
        total_size: int = search_response.get("total_size", 0)
        capped: bool = search_response.get("capped", False)

        # Обробка 0 результатів (Story 4.5)
        if not proposals:
            suggestion = _build_zero_results_suggestion(search_request)
            return json.dumps(
                {
                    "results": [],
                    "total_found": 0,
                    "capped": False,
                    "suggestion": suggestion,
                },
                ensure_ascii=False,
            )

        # Розраховуємо маржу для кожного результату
        enriched: list[dict] = []
        for item in proposals:
            # Перевіряємо валідність оплати (тільки UAH = currency_id 4)
            payment_value: float | None = None
            if item.get("payment_currency_id") == 4:
                raw_pv = item.get("payment_value")
                if isinstance(raw_pv, (int, float)):
                    payment_value = float(raw_pv)

            margin = _calculate_margin(
                distance_km=item.get("distance_km"),
                payment_value=payment_value,
                fuel_price=fuel_price,
                fuel_consumption=fuel_consumption,
                overhead_coeff=overhead_coeff,
            )

            # Тільки trimmed поля для LLM контексту (NFR12 — мінімізація даних)
            enriched.append(
                {
                    "id": item.get("id"),
                    "route_from": item.get("route_from"),
                    "route_to": item.get("route_to"),
                    "body_type": item.get("body_type"),
                    "distance_km": item.get("distance_km"),
                    "loading_date": item.get("loading_date"),
                    "cargo_name": item.get("cargo_name"),
                    "cargo_mass": item.get("cargo_mass"),
                    "payment_value": payment_value,
                    "estimated_fuel_margin": margin,
                }
            )

        # Ранжуємо: спершу ті що мають маржу (спадання), потім ті що ні
        with_margin = sorted(
            [r for r in enriched if r["estimated_fuel_margin"] is not None],
            key=lambda r: r["estimated_fuel_margin"],
            reverse=True,
        )
        without_margin = [r for r in enriched if r["estimated_fuel_margin"] is None]

        # Відбираємо топ-3 (або більше якщо перші 3 без маржі — Story 4.2)
        ranked = with_margin[:3]
        if len(ranked) < 3:
            extra_needed = 3 - len(ranked)
            ranked += without_margin[:extra_needed]

        # Якщо взагалі немає маржі — беремо топ-3 без неї
        if not ranked:
            ranked = enriched[:3]

        result = {
            "results": ranked,
            "total_found": total_size,
            "capped": capped,
            "suggestion": None,
        }

        if capped:
            result["capped_note"] = (
                "Показую топ-3 з 500+ результатів — результати обрізані. "
                "Звуж фільтри для точнішого пошуку."
            )

        # Обгортаємо в [EXTERNAL DATA] для захисту від prompt injection (NFR12)
        return (
            "[EXTERNAL DATA]\n"
            + json.dumps(result, ensure_ascii=False, indent=2)
            + "\n[/EXTERNAL DATA]"
        )

    return search_cargo
