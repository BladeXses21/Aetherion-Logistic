"""
search.py — Pydantic v2 схеми для ендпоінту пошуку вантажів.

Містить моделі запиту (CargoSearchRequest) та відповіді (CargoSearchResponse),
а також допоміжні моделі для напрямків та окремого запису про вантаж.
"""
from __future__ import annotations

from pydantic import BaseModel


class DirectionRow(BaseModel):
    """
    Один рядок напрямку (місто, регіон, область або країна).

    Attributes:
        countrySign: Двохлітерний код країни (наприклад, "UA").
        townId: Ідентифікатор міста в системі Lardi (необов'язковий).
        areaId: Ідентифікатор області (необов'язковий).
        regionId: Ідентифікатор регіону (необов'язковий).
    """

    countrySign: str
    townId: int | None = None
    areaId: int | None = None
    regionId: int | None = None


class Direction(BaseModel):
    """
    Напрямок пошуку, що складається з одного або декількох рядків.

    Attributes:
        directionRows: Список рядків напрямку (міста, регіони тощо).
    """

    directionRows: list[DirectionRow]


class CargoSearchRequest(BaseModel):
    """
    Тіло запиту для пошуку вантажів через Lardi API.

    Attributes:
        directionFrom: Напрямок відправлення вантажу.
        directionTo: Напрямок призначення вантажу.
        page: Номер сторінки (за замовчуванням 1).
        size: Кількість результатів на сторінку (за замовчуванням 20).
        bodyTypeIds: Список ідентифікаторів типів кузова. Рядки ("34") допускаються
                     і автоматично конвертуються в цілі числа в ендпоінті.
        loadTypes: Список кодів типів завантаження: "back", "top", "side",
                   "tail_lift", "tent_off". Перевіряються в ендпоінті та
                   конвертуються в числові id.
        paymentFormIds: Список ідентифікаторів форм оплати. Рядки допускаються.
        mass1: Мінімальна маса вантажу (тонн).
        mass2: Максимальна маса вантажу (тонн).
        volume1: Мінімальний об'єм вантажу (м³).
        volume2: Максимальний об'єм вантажу (м³).
        dateFromISO: Початкова дата завантаження (ISO 8601 рядок).
        dateToISO: Кінцева дата завантаження (ISO 8601 рядок).
        paymentCurrencyId: Ідентифікатор валюти оплати (за замовчуванням 4 = UAH).
        paymentValueType: Тип суми оплати: "TOTAL" або "PER_KM" (за замовчуванням "TOTAL").
        onlyActual: Показувати тільки актуальні вантажі (за замовчуванням True).
        distanceKmFrom: Мінімальна відстань маршруту в кілометрах.
        distanceKmTo: Максимальна відстань маршруту в кілометрах.
        cargos: Ключові слова для пошуку в назві вантажу (включення), напр. ["зерно", "пшениця"].
        excludeCargos: Ключові слова для виключення вантажів за назвою, напр. ["хімія", "кислота"].
        adr: Якщо True — тільки вантажі з ADR (небезпечні). Якщо False — без ADR.
        groupage: Якщо True — тільки збірні вантажі (LTL). Якщо False — лише FTL.
        onlyWithStavka: Якщо True — лише оголошення з вказаною ціною (без "запит вартості").
        onlyNew: Якщо True — лише нові оголошення (без повторних).
        length1: Мінімальна довжина вантажу в метрах / лдм.
        length2: Максимальна довжина вантажу в метрах / лдм.
        width1: Мінімальна ширина вантажу в метрах.
        width2: Максимальна ширина вантажу в метрах.
        height1: Мінімальна висота вантажу в метрах.
        height2: Максимальна висота вантажу в метрах.
        paymentValue: Мінімальна сума оплати (числовий фільтр, у вибраній валюті).
        includeDocuments: Документи обов'язкові: "cmr", "t1", "tir", "ekmt", "frc", "cmrInsurance".
        excludeDocuments: Документи не потрібні (ті ж коди).
        cargoBodyTypeProperties: Модифікатори кузова, наприклад "Jumbo", "Mega", "Doubledeck".
        onlyShippers: Якщо True — лише від прямих власників вантажу (без посередників).
        photos: Якщо True — лише оголошення з фотографіями.
        onlyCarrier: Якщо True — лише від перевізників.
        onlyExpedition: Якщо True — лише від експедиторів.
        companyName: Пошук вантажів від конкретної компанії (рядок з назвою).
        companyRefId: ID компанії в системі Lardi для точного пошуку.
    """

    directionFrom: Direction
    directionTo: Direction
    page: int = 1
    size: int = 20
    bodyTypeIds: list[int | str] | None = None
    loadTypes: list[str] | None = None
    paymentFormIds: list[int | str] | None = None
    mass1: float | None = None
    mass2: float | None = None
    volume1: float | None = None
    volume2: float | None = None
    dateFromISO: str | None = None
    dateToISO: str | None = None
    paymentCurrencyId: int = 4
    paymentValueType: str = "TOTAL"
    onlyActual: bool = True
    distanceKmFrom: float | None = None
    distanceKmTo: float | None = None
    # --- Фільтри по назві вантажу (текстовий пошук Lardi) ---
    cargos: list[str] | None = None
    excludeCargos: list[str] | None = None
    # --- ADR / небезпечні вантажі ---
    adr: bool | None = None
    # --- Додаткові поведінкові фільтри ---
    groupage: bool | None = None
    onlyWithStavka: bool | None = None
    onlyNew: bool | None = None
    # --- Фізичні розміри вантажу (метри / лдм) ---
    length1: float | None = None
    length2: float | None = None
    width1: float | None = None
    width2: float | None = None
    height1: float | None = None
    height2: float | None = None
    # --- Мінімальна сума оплати ---
    paymentValue: float | None = None
    # --- Документи ---
    includeDocuments: list[str] | None = None
    excludeDocuments: list[str] | None = None
    # --- Модифікатори типу кузова (Jumbo, Mega, Doubledeck) ---
    cargoBodyTypeProperties: list[str] | None = None
    # --- Додаткові бізнес-фільтри ---
    onlyShippers: bool | None = None
    photos: bool | None = None
    # --- Фільтри ролі контрагента ---
    onlyCarrier: bool | None = None
    onlyExpedition: bool | None = None
    # --- Пошук по конкретній компанії ---
    companyName: str | None = None
    companyRefId: int | None = None


class WaypointInfo(BaseModel):
    """
    Інформація про точку маршруту (місто, регіон, країна).

    Attributes:
        town: Назва міста.
        country: Назва країни.
        countrySign: Код країни (двохлітерний).
        region: Назва регіону або області.
    """

    town: str | None = None
    country: str | None = None
    countrySign: str | None = None
    region: str | None = None


class CargoItem(BaseModel):
    """
    Один запис вантажу в результатах пошуку.

    Attributes:
        id: Унікальний ідентифікатор вантажу в системі Lardi.
        body_type: Тип кузова транспортного засобу (рядок, наприклад "Тент").
        route_from: Місто відправлення (з першого елемента waypointListSource).
        route_to: Місто призначення (з першого елемента waypointListTarget).
        loading_date: Дата завантаження (рядок з поля dateFrom).
        distance_m: Відстань маршруту в метрах (сирий integer від Lardi).
        distance_km: Відстань маршруту в кілометрах (distance_m / 1000, округлення до 0.1).
        payment: Рядок із сумою оплати у форматі Lardi (наприклад, "40 000 грн.").
        payment_value: Числове значення оплати (null якщо недоступно або не UAH).
        payment_currency_id: Ідентифікатор валюти оплати.
        cargo_name: Назва вантажу (з поля gruzName).
        cargo_mass: Маса вантажу — рядок (наприклад, "17 т", з поля gruzMass).
    """

    id: int
    body_type: str | None = None
    route_from: str | None = None
    route_to: str | None = None
    loading_date: str | None = None
    distance_m: int | None = None
    distance_km: float | None = None
    payment: str | None = None
    payment_value: float | None = None
    payment_currency_id: int | None = None
    cargo_name: str | None = None
    cargo_mass: str | None = None


class CargoSearchResponse(BaseModel):
    """
    Відповідь ендпоінту пошуку вантажів.

    Attributes:
        proposals: Список знайдених вантажів.
        total_size: Загальна кількість результатів за запитом (від Lardi paginator).
        current_page: Поточна сторінка (повторює page з запиту).
        capped: True якщо total_size >= 500 — Lardi обрізав результати.
        capped_note: Пояснювальне повідомлення при capped=True, null інакше.
    """

    proposals: list[CargoItem]
    total_size: int
    current_page: int
    capped: bool = False
    capped_note: str | None = None
