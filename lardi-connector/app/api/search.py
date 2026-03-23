"""
search.py — POST /search ендпоінт для пошуку вантажів через Lardi API.

Ендпоінт:
  - Перевіряє та конвертує фільтри (bodyTypeIds, loadTypes, paymentFormIds)
  - Отримує LTSID з Redis (aetherion:auth:ltsid)
  - Формує payload у форматі Lardi API
  - Передає запит через QueueManager (Story 3.1) для rate-limiting
  - Парсить відповідь Lardi та повертає нормалізовану структуру

Кожен запит отримує унікальний request_id (UUID), який прив'язується
до всіх structlog подій для трасування.
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request

from app.queue.queue_manager import QueueManager, QueueUnavailableError
from app.schemas.search import (
    CargoItem,
    CargoSearchRequest,
    CargoSearchResponse,
    Direction,
)
from app.services.lardi_client import LardiClient, LardiHTTPError, LardiTimeoutError
from app.services.retry_handler import LtsidRefreshError, handle_401_and_retry, with_rate_limit_retry

router = APIRouter(tags=["search"])

# --- Маппінг типів завантаження ---
# Підтверджені значення з документації Lardi API:
#   "back"  → 26  (підтверджено: "заднє"/rear, filterCode "l26")
#   "top"   → 25  (орієнтовно: з патерну "l25i24i26" = верх+бік+зад)
#   "side"  → 24  (орієнтовно: з патерну "l25i24i26")
# Невідомі/placeholder значення (не підтверджені документацією):
#   "tail_lift"  → 27  (гідроборт, placeholder)
#   "tent_off"   → 28  (повне розтентування, placeholder)
LOAD_TYPE_MAP: dict[str, int] = {
    "back": 26,
    "top": 25,
    "side": 24,
    "tail_lift": 27,
    "tent_off": 28,
}
ALLOWED_LOAD_TYPES: set[str] = set(LOAD_TYPE_MAP.keys())

# Межа "обрізання" результатів — Lardi не повертає більше 500 записів
CAPPED_SIZE = 500
CAPPED_NOTE = (
    "Lardi does not support pagination — "
    "narrow query by region, date, or vehicle type"
)


@router.post("/search", response_model=CargoSearchResponse)
async def search_cargo(payload: CargoSearchRequest, request: Request) -> CargoSearchResponse:
    """
    Шукає вантажі через Lardi API з повною підтримкою фільтрів.

    Кроки виконання:
      1. Генерує унікальний request_id (UUID) для трасування в логах.
      2. Валідує та конвертує bodyTypeIds і paymentFormIds (рядки → int).
      3. Валідує loadTypes та конвертує коди у числові id Lardi.
      4. Отримує LTSID з Redis (aetherion:auth:ltsid).
      5. Формує payload у форматі Lardi API.
      6. Ставить запит у чергу через QueueManager (rate-limiting).
      7. Парсить відповідь та повертає CargoSearchResponse.

    Args:
        payload: Тіло запиту CargoSearchRequest з параметрами пошуку.
        request: FastAPI Request — для доступу до app.state (redis, queue_manager, lardi_client).

    Returns:
        CargoSearchResponse з переліком вантажів та метаданими (total_size, capped тощо).

    Raises:
        HTTPException(422): Якщо bodyTypeIds, paymentFormIds або loadTypes містять невалідні значення.
        HTTPException(503): Якщо LTSID відсутній в Redis або черга недоступна.
        HTTPException(504): Якщо Lardi не відповів у межах таймауту.
    """
    # Генеруємо унікальний ідентифікатор для трасування цього запиту в логах
    request_id = str(uuid.uuid4())
    log = structlog.get_logger().bind(request_id=request_id)
    log.info("cargo_search_request_received", page=payload.page, size=payload.size)

    # Крок 1: Валідація та конвертація числових фільтрів
    body_type_ids = _cast_int_list(payload.bodyTypeIds, "bodyTypeIds")
    payment_form_ids = _cast_int_list(payload.paymentFormIds, "paymentFormIds")

    # Крок 2: Валідація та маппінг типів завантаження (рядкові коди → числові id Lardi)
    load_type_ids: list[int] | None = None
    if payload.loadTypes is not None:
        for code in payload.loadTypes:
            if code not in ALLOWED_LOAD_TYPES:
                log.warning("invalid_load_type", code=code)
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": {
                            "code": "INVALID_FILTER_TYPE",
                            "message": f"loadTypes invalid value: '{code}'",
                        }
                    },
                )
        load_type_ids = [LOAD_TYPE_MAP[c] for c in payload.loadTypes]

    # Крок 3: Отримуємо LTSID з Redis — без нього авторизація на Lardi неможлива
    redis_client = request.app.state.redis
    try:
        ltsid = await redis_client.get("aetherion:auth:ltsid")
    except Exception:
        log.error("ltsid_redis_get_failed", exc_info=True)
        ltsid = None

    if not ltsid:
        log.error("ltsid_not_available")
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "LTSID_REFRESH_FAILED",
                    "message": "LTSID not available",
                }
            },
        )

    # Крок 4: Формуємо payload у форматі Lardi API
    lardi_payload = _build_lardi_payload(payload, body_type_ids, load_type_ids, payment_form_ids)

    # Крок 5: Виконуємо запит через чергу (rate-limiting, серіалізація)
    lardi_client: LardiClient = request.app.state.lardi_client

    async def do_search() -> dict:
        """
        Обгортка корутини пошуку з підтримкою 401 auto-recovery та rate limit retry.

        Виконує пошук з поточним LTSID. При 401 — запускає handle_401_and_retry,
        що публікує refresh_requested і чекає нового LTSID. При 429/503 —
        with_rate_limit_retry повторює до 3 разів з exponential backoff.
        """
        async def search_with_ltsid(current_ltsid: str) -> dict:
            """Виконує пошук з конкретним LTSID — використовується при refresh."""
            return await lardi_client.search(lardi_payload, current_ltsid, request_id)

        async def execute() -> dict:
            """Виконує початковий запит; при 401 ініціює авто-відновлення сесії."""
            try:
                return await search_with_ltsid(ltsid)
            except LardiHTTPError as exc:
                if exc.status_code == 401:
                    return await handle_401_and_retry(
                        search_with_ltsid,
                        redis_client,
                        request_id,
                    )
                raise

        return await with_rate_limit_retry(execute, request_id)

    queue_manager: QueueManager = request.app.state.queue_manager
    try:
        raw = await queue_manager.enqueue(request_id, do_search)
    except QueueUnavailableError:
        log.error("queue_unavailable")
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "QUEUE_UNAVAILABLE"}},
        )
    except LardiTimeoutError:
        log.error("lardi_timeout_in_endpoint")
        raise HTTPException(
            status_code=504,
            detail={"error": {"code": "LARDI_TIMEOUT"}},
        )
    except LtsidRefreshError as exc:
        # 401 авто-recovery завершилось невдачею (timeout або повторний 401)
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": exc.code, **({"details": exc.details} if exc.details else {})}},
        )
    except LardiHTTPError as exc:
        # Інші HTTP помилки від Lardi (400, 404, 500, тощо)
        log.error("lardi_search_http_error_in_endpoint", status_code=exc.status_code)
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "LARDI_SEARCH_UNAVAILABLE"}},
        )

    # Крок 6: Парсимо відповідь та повертаємо нормалізовану структуру
    result = _parse_response(raw, payload.page)
    log.info(
        "cargo_search_completed",
        total_size=result.total_size,
        capped=result.capped,
        proposals_count=len(result.proposals),
    )
    return result


def _cast_int_list(values: list | None, field_name: str) -> list[int] | None:
    """
    Конвертує список значень (int або рядки) у список цілих чисел.

    Прийнятні вхідні значення: int (34), рядок-число ("34").
    Неприйнятні: рядки типу "truck", None-елементи.

    Args:
        values: Список значень для конвертації або None.
        field_name: Назва поля (для повідомлення про помилку).

    Returns:
        Список int значень або None якщо values is None.

    Raises:
        HTTPException(422): Якщо хоча б одне значення не можна конвертувати в int.

    Приклад:
        _cast_int_list(["34", 5], "bodyTypeIds")  # → [34, 5]
        _cast_int_list(["truck"], "bodyTypeIds")   # → raises HTTPException 422
    """
    if values is None:
        return None
    result = []
    for v in values:
        try:
            result.append(int(v))
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "INVALID_FILTER_TYPE",
                        "message": f"{field_name} must be integers, got '{v!r}'",
                    }
                },
            )
    return result


def _build_lardi_payload(
    payload: CargoSearchRequest,
    body_type_ids: list[int] | None,
    load_type_ids: list[int] | None,
    payment_form_ids: list[int] | None,
) -> dict:
    """
    Формує словник payload у форматі Lardi API з даних CargoSearchRequest.

    Вкладена структура filter.directionFrom/To будується з DirectionRow моделей
    з виключенням None-полів (exclude_none=True).

    Args:
        payload: Вхідний запит з усіма параметрами пошуку.
        body_type_ids: Список числових ідентифікаторів типів кузова (вже конвертовані).
        load_type_ids: Список числових ідентифікаторів типів завантаження (вже конвертовані).
        payment_form_ids: Список числових ідентифікаторів форм оплати (вже конвертовані).

    Returns:
        Словник у форматі Lardi API, готовий для передачі в httpx POST запит.
    """

    def build_direction(d: Direction) -> dict:
        """Перетворює об'єкт Direction на словник для Lardi API."""
        return {
            "directionRows": [
                row.model_dump(exclude_none=True) for row in d.directionRows
            ]
        }

    return {
        "page": payload.page,
        "size": payload.size,
        "sortByCountryFirst": False,
        "filter": {
            "directionFrom": build_direction(payload.directionFrom),
            "directionTo": build_direction(payload.directionTo),
            "mass1": payload.mass1,
            "mass2": payload.mass2,
            "volume1": payload.volume1,
            "volume2": payload.volume2,
            "dateFromISO": payload.dateFromISO,
            "dateToISO": payload.dateToISO,
            "bodyTypeIds": body_type_ids,
            "loadTypes": load_type_ids,
            "paymentFormIds": payment_form_ids,
            "paymentCurrencyId": payload.paymentCurrencyId,
            "paymentValueType": payload.paymentValueType,
            "onlyActual": payload.onlyActual,
            "distanceKmFrom": payload.distanceKmFrom,
            "distanceKmTo": payload.distanceKmTo,
        },
    }


def _parse_response(raw: dict, page: int) -> CargoSearchResponse:
    """
    Парсить сиру відповідь від Lardi API в нормалізовану CargoSearchResponse.

    Визначає, чи обрізано результати (capped=True якщо totalSize >= 500).
    У такому разі додає capped_note з порадою звузити запит.

    Args:
        raw: Розпарсений JSON-словник від Lardi API.
        page: Номер сторінки з оригінального запиту (для current_page).

    Returns:
        CargoSearchResponse з переліком вантажів та метаданими.
    """
    result = raw.get("result", {})
    proposals_raw = result.get("proposals", [])
    paginator = result.get("paginator", {})
    total_size = paginator.get("totalSize", 0)

    items = [_parse_cargo_item(p) for p in proposals_raw]

    # Перевіряємо чи Lardi обрізав результати (максимум 500 записів)
    capped = total_size >= CAPPED_SIZE

    return CargoSearchResponse(
        proposals=items,
        total_size=total_size,
        current_page=page,
        capped=capped,
        capped_note=CAPPED_NOTE if capped else None,
    )


def _parse_cargo_item(p: dict) -> CargoItem:
    """
    Парсить один запис вантажу з відповіді Lardi в об'єкт CargoItem.

    Конвертує відстань: distance_m = сирий integer, distance_km = distance_m / 1000
    (float, округлений до 1 знаку після коми).

    Маршрут: route_from з waypointListSource[0].town,
             route_to з waypointListTarget[0].town.

    Args:
        p: Словник з одним записом про вантаж від Lardi API.

    Returns:
        CargoItem — нормалізований запис вантажу.
    """
    # Конвертація відстані: Lardi повертає метри, ми зберігаємо і метри і кілометри
    distance_raw = p.get("distance")
    distance_m = int(distance_raw) if distance_raw is not None else None
    distance_km = round(distance_m / 1000, 1) if distance_m is not None else None

    # Маршрут: беремо першу точку зі списків waypoints
    waypoints_from = p.get("waypointListSource", [])
    waypoints_to = p.get("waypointListTarget", [])
    route_from = waypoints_from[0].get("town") if waypoints_from else None
    route_to = waypoints_to[0].get("town") if waypoints_to else None

    # Числове значення оплати — конвертуємо в float якщо можливо
    payment_value = p.get("paymentValue")
    if payment_value is not None:
        try:
            payment_value = float(payment_value)
        except (TypeError, ValueError):
            payment_value = None

    return CargoItem(
        id=p["id"],
        body_type=p.get("bodyType"),
        route_from=route_from,
        route_to=route_to,
        loading_date=p.get("dateFrom"),
        distance_m=distance_m,
        distance_km=distance_km,
        payment=p.get("payment"),
        payment_value=payment_value,
        payment_currency_id=p.get("paymentCurrencyId"),
        cargo_name=p.get("gruzName"),
        cargo_mass=p.get("gruzMass"),
    )
