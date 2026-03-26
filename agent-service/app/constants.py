"""
constants.py — Канонічні константи Lardi-Trans API для agent-service.

Портовано з v1: Aetherion Agent/agent/lardi/constants.py

КРИТИЧНО: Сервер Lardi ігнорує поле bodyTypes (рядковий масив).
Єдине правильне поле — bodyTypeIds (масив цілих чисел).
TENT=34 підтверджено через аналіз filterCode (b34 в URL).
"""
from enum import IntEnum
from typing import Optional


class BodyTypeID(IntEnum):
    """
    Цілочисельні ідентифікатори типів кузова для поля bodyTypeIds.

    ПІДТВЕРДЖЕНО: TENT=34 (via filterCode b34 з живого мережевого трафіку).
    Решта значень — оціночні за порядком фільтрів в UI Lardi, потребують верифікації.
    Оновлювати enum по мірі підтвердження ID через аналіз filterCode.
    """

    TENT = 34        # Тент / Тентований — ПІДТВЕРДЖЕНО via filterCode b34
    REF = 3          # Рефрижератор        — не верифіковано
    IZOTERM = 4      # Ізотермічний         — не верифіковано
    CELNOMET = 5     # Цільнометалевий      — не верифіковано
    ONBOARD = 6      # Відкрита/бортова     — не верифіковано
    GRAIN = 7        # Зерновоз             — не верифіковано
    CISTERN = 8      # Цистерна             — не верифіковано
    TIPPER = 9       # Самоскид             — не верифіковано
    CONTAINER = 10   # Контейнер            — не верифіковано
    CAR_CARRIER = 11 # Автовоз              — не верифіковано
    MANIPULATOR = 12 # Маніпулятор          — не верифіковано
    PLATFORM = 13    # Платформа            — не верифіковано
    LOGGER = 14      # Лісовоз              — не верифіковано
    NEGABARIT = 15   # Трал / Негабарит     — не верифіковано
    BUS = 16         # Бус                  — не верифіковано
    JUMBO = 17       # Джамбо / Mega        — не верифіковано


# Словник: українська назва кузова (в нижньому регістрі) → BodyTypeID
# Лише TENT безпечно використовувати у продакшені — решта з неверифікованими ID.
BODY_TYPE_UA_TO_ID: dict[str, BodyTypeID] = {
    "тент":          BodyTypeID.TENT,
    "тентований":    BodyTypeID.TENT,
    "реф":           BodyTypeID.REF,
    "рефрижератор":  BodyTypeID.REF,
    "ізотерм":       BodyTypeID.IZOTERM,
    "ізотермічний":  BodyTypeID.IZOTERM,
    "цільномет":     BodyTypeID.CELNOMET,
    "відкрита":      BodyTypeID.ONBOARD,
    "відкритий":     BodyTypeID.ONBOARD,
    "бортова":       BodyTypeID.ONBOARD,
    "зерновоз":      BodyTypeID.GRAIN,
    "цистерна":      BodyTypeID.CISTERN,
    "самоскид":      BodyTypeID.TIPPER,
    "контейнер":     BodyTypeID.CONTAINER,
    "автовоз":       BodyTypeID.CAR_CARRIER,
    "маніпулятор":   BodyTypeID.MANIPULATOR,
    "платформа":     BodyTypeID.PLATFORM,
    "лісовоз":       BodyTypeID.LOGGER,
    "трал":          BodyTypeID.NEGABARIT,
    "негабарит":     BodyTypeID.NEGABARIT,
    "бус":           BodyTypeID.BUS,
    "джамбо":        BodyTypeID.JUMBO,
}


def resolve_body_type_id(name: str) -> Optional[BodyTypeID]:
    """
    Перетворює українську назву типу кузова в BodyTypeID.

    Args:
        name: Рядок назви кузова (будь-який регістр).

    Returns:
        BodyTypeID або None якщо назва не розпізнана.

    Приклад:
        resolve_body_type_id("Тентований")  # → BodyTypeID.TENT (34)
        resolve_body_type_id("невідомо")    # → None
    """
    return BODY_TYPE_UA_TO_ID.get(name.lower().strip())


# Словник: типи завантаження — строкові коди для поля loadTypes[].
# ПІДТВЕРДЖЕНО: сервер приймає ці значення як рядки.
LOAD_TYPE_UA_TO_CODE: dict[str, str] = {
    "задня":               "back",
    "заднє":               "back",
    "верхня":              "top",
    "верхнє":              "top",
    "бічна":               "side",
    "бічне":               "side",
    "гідроборт":           "tail_lift",
    "повне розтентування": "tent_off",
}

# Допустимі коди типів завантаження (для валідації)
VALID_LOAD_TYPES: frozenset[str] = frozenset(LOAD_TYPE_UA_TO_CODE.values())


def resolve_load_type_code(name: str) -> Optional[str]:
    """
    Перетворює українську назву типу завантаження в строковий код.

    Args:
        name: Рядок назви завантаження.

    Returns:
        Строковий код ("back", "top", "side", "tail_lift", "tent_off") або None.
    """
    return LOAD_TYPE_UA_TO_CODE.get(name.lower().strip())


# Словник: назви країн (українська та англійська, нижній регістр) → ISO 3166-1 alpha-2 код
COUNTRY_UA_TO_SIGN: dict[str, str] = {
    # Центральна та Східна Європа
    "польща": "PL",
    "poland": "PL",
    "польщі": "PL",
    "германія": "DE",
    "germany": "DE",
    "угорщина": "HU",
    "hungary": "HU",
    "австрія": "AT",
    "austria": "AT",
    "румунія": "RO",
    "romania": "RO",
    "словаччина": "SK",
    "slovakia": "SK",
    "словенія": "SI",
    "slovenia": "SI",
    "чехія": "CZ",
    "czech": "CZ",
    "чеська": "CZ",
    "білорусь": "BY",
    "belarus": "BY",
    "молдова": "MD",
    "moldova": "MD",
    "туреччина": "TR",
    "turkey": "TR",
    # Захід
    "франція": "FR",
    "france": "FR",
    "іспанія": "ES",
    "spain": "ES",
    "нідерланди": "NL",
    "netherlands": "NL",
    "бельгія": "BE",
    "belgium": "BE",
    "болгарія": "BG",
    "bulgaria": "BG",
    "литва": "LT",
    "lithuania": "LT",
    "латвія": "LV",
    "latvia": "LV",
    "естонія": "EE",
    "estonia": "EE",
    "фінляндія": "FI",
    "finland": "FI",
    "швеція": "SE",
    "sweden": "SE",
    "норвегія": "NO",
    "norway": "NO",
    "данія": "DK",
    "denmark": "DK",
    "швейцарія": "CH",
    "switzerland": "CH",
    "австрія": "AT",
    "austria": "AT",
    "italy": "IT",
    "італія": "IT",
    "хорватія": "HR",
    "croatia": "HR",
    "сербія": "RS",
    "serbia": "RS",
    "греція": "GR",
    "greece": "GR",
    "португалія": "PT",
    "portugal": "PT",
    "великобританія": "GB",
    "uk": "GB",
    "england": "GB",
    # СНД та Азія
    "україна": "UA",
    "ukraine": "UA",
    "росія": "RU",
    "russia": "RU",
    "казахстан": "KZ",
    "kazakhstan": "KZ",
    "узбекистан": "UZ",
    "azerbaijan": "AZ",
    "азербайджан": "AZ",
    "вірменія": "AM",
    "armenia": "AM",
    "грузія": "GE",
    "georgia": "GE",
}


def resolve_country_sign(name: str) -> Optional[str]:
    """
    Перетворює назву країни (українська або англійська) в ISO код.

    Args:
        name: Назва країни у довільному регістрі.

    Returns:
        ISO 3166-1 alpha-2 код (наприклад "PL") або None якщо не знайдено.

    Приклад:
        resolve_country_sign("Польща")  # → "PL"
        resolve_country_sign("PL")      # → None (очікується повна назва)
    """
    return COUNTRY_UA_TO_SIGN.get(name.lower().strip())


# ---------------------------------------------------------------------------
# Форми оплати — paymentFormIds (integer array)
# УВАГА: ID не підтверджені через filterCode — потребують верифікації!
# Спостережені назви у відповідях Lardi: "безготівка", "готівка", "карта".
# Типові значення для українських B2B-платформ (оціночні):
# ---------------------------------------------------------------------------
PAYMENT_FORM_UA_TO_ID: dict[str, int] = {
    "готівка":          1,   # cash — НЕ верифіковано
    "нал":              1,   # скорочення готівки — НЕ верифіковано
    "нал.":             1,
    "безготівка":       2,   # bank transfer — НЕ верифіковано
    "безнал":           2,
    "безнал.":          2,
    "банківський":      2,
    "перерахунок":      2,
    "карта":            3,   # card — НЕ верифіковано
    "картка":           3,
}


def resolve_payment_form_id(name: str) -> Optional[int]:
    """
    Перетворює українську назву форми оплати в числовий ID для Lardi API.

    УВАГА: ID є оціночними та потребують верифікації через живий мережевий трафік.
    Для верифікації: обери фільтр "Форма оплати" в UI Lardi, виконай пошук
    та перевір filterCode або тіло POST запиту в DevTools.

    Args:
        name: Назва форми оплати (будь-який регістр), наприклад "готівка", "безнал".

    Returns:
        Числовий ID або None якщо назва не розпізнана.
    """
    return PAYMENT_FORM_UA_TO_ID.get(name.lower().strip())


# ---------------------------------------------------------------------------
# Валюта оплати — paymentCurrencyId
# ПІДТВЕРДЖЕНО з документації Lardi API та filterCode "pc{n}".
# ---------------------------------------------------------------------------
PAYMENT_CURRENCY_UA_TO_ID: dict[str, int] = {
    # UAH (гривня)
    "uah":      4,
    "грн":      4,
    "гривня":   4,
    "гривні":   4,
    # USD (долар)
    "usd":      1,
    "долар":    1,
    "долари":   1,
    "$":        1,
    # EUR (євро)
    "eur":      2,
    "євро":     2,
    "euro":     2,
    "€":        2,
    # Інша валюта
    "інша":     3,
    "other":    3,
}


def resolve_payment_currency_id(name: str) -> Optional[int]:
    """
    Перетворює назву валюти в числовий ID для поля paymentCurrencyId.

    Підтверджені значення (з filterCode: pc4=UAH, pc1=USD, pc2=EUR):
        4 = UAH (гривня) — за замовчуванням
        1 = USD
        2 = EUR
        3 = інша валюта

    Args:
        name: Назва валюти або символ (будь-який регістр).

    Returns:
        Числовий ID або None якщо не знайдено.

    Приклад:
        resolve_payment_currency_id("USD")  # → 1
        resolve_payment_currency_id("грн")  # → 4
    """
    return PAYMENT_CURRENCY_UA_TO_ID.get(name.lower().strip())


# ---------------------------------------------------------------------------
# Тип суми оплати — paymentValueType
# ПІДТВЕРДЖЕНО: filterCode "pt1"=TOTAL, "pt2"=PER_KM, "pt3"=PER_TON.
# ---------------------------------------------------------------------------
PAYMENT_VALUE_TYPE_UA_TO_CODE: dict[str, str] = {
    # TOTAL — загальна сума за рейс
    "всього":       "TOTAL",
    "загалом":      "TOTAL",
    "за рейс":      "TOTAL",
    "total":        "TOTAL",
    # PER_KM — ставка за кілометр
    "за км":        "PER_KM",
    "за кілометр":  "PER_KM",
    "per_km":       "PER_KM",
    "per km":       "PER_KM",
    # PER_TON — ставка за тонну
    "за тонну":     "PER_TON",
    "за т":         "PER_TON",
    "per_ton":      "PER_TON",
    "per ton":      "PER_TON",
}


def resolve_payment_value_type(name: str) -> Optional[str]:
    """
    Перетворює опис типу суми оплати в код для поля paymentValueType.

    Підтверджені коди (з filterCode: pt1=TOTAL, pt2=PER_KM, pt3=PER_TON):
        "TOTAL"   — загальна сума за весь рейс (за замовчуванням)
        "PER_KM"  — ставка за кілометр
        "PER_TON" — ставка за тонну

    Args:
        name: Текстовий опис (будь-який регістр), наприклад "за км", "за тонну".

    Returns:
        Рядковий код або None якщо не знайдено.
    """
    return PAYMENT_VALUE_TYPE_UA_TO_CODE.get(name.lower().strip())
