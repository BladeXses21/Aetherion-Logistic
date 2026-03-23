"""
cargo.py — GET /cargo/{id} ендпоінт для отримання деталей вантажу.

Повертає CargoDetailResponse включаючи контакт вантажовідправника (shipper_phone).
Усі запити до Lardi проходять через QueueManager (Story 3.1).

Особливості:
  - shipper_phone = None якщо proposalUser відсутній або phone порожній
  - Логується ltsid_hash (sha256[:8]), але НЕ саме значення LTSID
  - 404 від Lardi → наш HTTP 404 CARGO_NOT_FOUND
  - Інші помилки (крім 401) → HTTP 502 LARDI_DETAIL_UNAVAILABLE
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request

from app.queue.queue_manager import QueueManager, QueueUnavailableError
from app.schemas.cargo import CargoDetailResponse
from app.services.lardi_client import LardiClient, LardiHTTPError, LardiTimeoutError

router = APIRouter(tags=["cargo"])


@router.get("/cargo/{cargo_id}", response_model=CargoDetailResponse)
async def get_cargo_detail(cargo_id: int, request: Request) -> CargoDetailResponse:
    """
    Повертає повні деталі конкретного вантажу, включаючи телефон вантажовідправника.

    Кроки виконання:
      1. Генерує унікальний request_id (UUID) для трасування в логах.
      2. Отримує LTSID з Redis (aetherion:auth:ltsid).
      3. Ставить запит у чергу через QueueManager (rate-limiting, Story 3.1).
      4. LardiClient звертається до GET /webapi/proposal/offer/gruz/{id}/awaiting/.
      5. Парсить відповідь: витягує телефон з proposalUser.contact.phoneItem1.phone.

    Args:
        cargo_id: Числовий ідентифікатор вантажу (64-бітний integer).
        request: FastAPI Request — для доступу до app.state.

    Returns:
        CargoDetailResponse з деталями вантажу та shipper_phone (може бути None).

    Raises:
        HTTPException(404): якщо вантаж не знайдений на Lardi (CARGO_NOT_FOUND).
        HTTPException(503): якщо LTSID відсутній або черга недоступна.
        HTTPException(504): якщо Lardi не відповів у межах таймауту.
        HTTPException(502): якщо Lardi повернув іншу помилку (LARDI_DETAIL_UNAVAILABLE).
    """
    request_id = str(uuid.uuid4())
    log = structlog.get_logger().bind(request_id=request_id, cargo_id=cargo_id)
    log.info("cargo_detail_request_received")

    # Отримуємо LTSID з Redis
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
            detail={"error": {"code": "LTSID_REFRESH_FAILED", "message": "LTSID not available"}},
        )

    # Виконуємо запит через чергу
    lardi_client: LardiClient = request.app.state.lardi_client

    async def do_detail() -> dict:
        """Обгортка корутини деталей — передається в QueueManager як coro_factory."""
        return await lardi_client.get_cargo_detail(cargo_id, ltsid, request_id)

    queue_manager: QueueManager = request.app.state.queue_manager
    try:
        raw = await queue_manager.enqueue(request_id, do_detail)
    except QueueUnavailableError:
        log.error("queue_unavailable")
        raise HTTPException(
            status_code=503,
            detail={"error": {"code": "QUEUE_UNAVAILABLE"}},
        )
    except LardiTimeoutError:
        raise HTTPException(
            status_code=504,
            detail={"error": {"code": "LARDI_TIMEOUT"}},
        )
    except LardiHTTPError as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "CARGO_NOT_FOUND", "message": f"Cargo {cargo_id} not found"}},
            )
        # 401 та інші — 502 (retry буде в Story 3.4)
        log.error("lardi_detail_error", status_code=exc.status_code)
        raise HTTPException(
            status_code=502,
            detail={"error": {"code": "LARDI_DETAIL_UNAVAILABLE"}},
        )

    result = _parse_detail_response(raw)
    log.info("cargo_detail_completed", shipper_phone_available=result.shipper_phone is not None)
    return result


def _parse_detail_response(raw: dict) -> CargoDetailResponse:
    """
    Парсить сиру відповідь Lardi API деталей вантажу в CargoDetailResponse.

    Структура відповіді Lardi: {"cargo": {...}, "offers": []}.
    Телефон витягується з вкладеного шляху:
      cargo.proposalUser.contact.phoneItem1.phone

    Якщо будь-який проміжний об'єкт відсутній або None — shipper_phone = None,
    без виняткових ситуацій.

    Args:
        raw: Розпарсений JSON-словник від Lardi API деталей.

    Returns:
        CargoDetailResponse з усіма доступними полями.
    """
    cargo = raw.get("cargo", {})

    # Витягуємо маршрут з перших waypoints
    waypoints_from = cargo.get("waypointListSource", [])
    waypoints_to = cargo.get("waypointListTarget", [])

    # В деталях waypoints мають поле townName (відрізняється від пошуку де town)
    route_from = None
    if waypoints_from:
        wp = waypoints_from[0]
        route_from = wp.get("townName") or wp.get("town")

    route_to = None
    if waypoints_to:
        wp = waypoints_to[0]
        route_to = wp.get("townName") or wp.get("town")

    # Відстань — у деталях може бути або відсутня (не всі вантажі мають маршрут)
    distance_raw = cargo.get("distance")
    distance_m = int(distance_raw) if distance_raw is not None else None
    distance_km = round(distance_m / 1000, 1) if distance_m is not None else None

    # Телефон вантажовідправника — глибоко вкладений шлях
    shipper_phone = _extract_shipper_phone(cargo.get("proposalUser"))
    shipper_name = _extract_shipper_name(cargo.get("proposalUser"))

    # Числова вага вантажу (в деталях — float gruzMass1, на відміну від рядка у пошуку)
    cargo_mass_kg = cargo.get("gruzMass1")
    if cargo_mass_kg is not None:
        try:
            cargo_mass_kg = float(cargo_mass_kg)
        except (TypeError, ValueError):
            cargo_mass_kg = None

    # Числове значення оплати
    payment_value = cargo.get("paymentValue")
    if payment_value is not None:
        try:
            payment_value = float(payment_value)
        except (TypeError, ValueError):
            payment_value = None

    return CargoDetailResponse(
        id=cargo["id"],
        body_type=cargo.get("bodyType"),
        route_from=route_from,
        route_to=route_to,
        loading_date=cargo.get("dateFrom"),
        cargo_name=cargo.get("gruzName"),
        cargo_mass_kg=cargo_mass_kg,
        distance_m=distance_m,
        distance_km=distance_km,
        shipper_phone=shipper_phone,
        shipper_name=shipper_name,
        payment_value=payment_value,
        payment_currency=cargo.get("paymentCurrency"),
    )


def _extract_shipper_phone(proposal_user: dict | None) -> str | None:
    """
    Безпечно витягує телефон вантажовідправника з вкладеного об'єкта proposalUser.

    Шлях: proposalUser.contact.phoneItem1.phone
    Якщо будь-який рівень відсутній або phone порожній — повертає None без помилок.

    Args:
        proposal_user: Об'єкт proposalUser з відповіді Lardi або None.

    Returns:
        Рядок телефону (наприклад, "+380679078186") або None.
    """
    if not proposal_user:
        return None
    contact = proposal_user.get("contact")
    if not contact:
        return None
    phone_item = contact.get("phoneItem1")
    if not phone_item:
        return None
    phone = phone_item.get("phone")
    # Повертаємо None якщо порожній рядок
    return phone if phone else None


def _extract_shipper_name(proposal_user: dict | None) -> str | None:
    """
    Безпечно витягує ім'я вантажовідправника з proposalUser.contact.name.

    Args:
        proposal_user: Об'єкт proposalUser з відповіді Lardi або None.

    Returns:
        Ім'я контакту або None.
    """
    if not proposal_user:
        return None
    contact = proposal_user.get("contact")
    if not contact:
        return None
    return contact.get("name") or None
