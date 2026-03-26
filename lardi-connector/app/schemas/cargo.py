"""
cargo.py — Pydantic v2 схема відповіді для деталей вантажу (Story 3.3).

Містить CargoDetailResponse — структуру що повертається GET /cargo/{id},
включаючи контактний телефон вантажовідправника (shipper_phone).
"""
from __future__ import annotations

from pydantic import BaseModel


class CargoDetailResponse(BaseModel):
    """
    Повна інформація про конкретний вантаж, включаючи контакти вантажовідправника.

    Отримується через GET /cargo/{id}, який звертається до Lardi API
    GET /webapi/proposal/offer/gruz/{id}/awaiting/?currentId={id}.

    shipper_phone — None якщо proposalUser відсутній або phone порожній.
    cargo_mass_kg — числове значення ваги (з деталі, float), на відміну від
                    cargo_mass у пошуку (рядок типу "17 т").

    Attributes:
        id: Унікальний ідентифікатор вантажу (64-бітний integer).
        body_type: Тип кузова (наприклад, "Тент, Зерновоз").
        route_from: Перша точка завантаження (назва міста).
        route_to: Перша точка розвантаження (назва міста).
        loading_date: Дата завантаження у форматі ISO 8601.
        cargo_name: Назва вантажу (gruzName).
        cargo_mass_kg: Вага вантажу в тоннах (gruzMass1, float).
        distance_m: Відстань маршруту в метрах (сире значення Lardi).
        distance_km: Відстань маршруту в кілометрах (округлено до 1 знаку).
        shipper_phone: Телефон вантажовідправника (null якщо недоступний).
        shipper_name: Ім'я контакту вантажовідправника (null якщо недоступний).
        payment_value: Числове значення оплати (0 = "за домовленістю").
        payment_currency: Рядок валюти (з відповіді Lardi, може бути порожнім).
    """

    id: int
    body_type: str | None = None
    route_from: str | None = None
    route_to: str | None = None
    loading_date: str | None = None
    loading_date_to: str | None = None  # кінцева дата актуальності (dateTo)
    cargo_name: str | None = None
    cargo_mass_kg: float | None = None
    distance_m: int | None = None
    distance_km: float | None = None
    shipper_phone: str | None = None
    shipper_name: str | None = None
    payment_value: float | None = None
    payment_currency: str | None = None
