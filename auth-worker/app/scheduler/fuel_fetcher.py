"""
fuel_fetcher.py — Отримання та кешування поточної ціни дизельного палива.

Виконується при старті auth-worker (асинхронно, не блокує запуск) та
щогодинним scheduler job. Зберігає ціну в Redis:
  aetherion:fuel:price:diesel  з TTL = FUEL_CACHE_TTL_SECONDS (default: 3600)

Джерело: WOG API (https://api.wog.ua/fuel_stations)
Паливо для фур: ДП Євро5 (дизель Euro 5 — стандарт для сучасних вантажівок).

Підтримує три формати відповіді:
  1. WOG API JSON: {"data": {"fuel_filters": [{"name": "ДП", "brand": "Євро5",
     "price": 8699, ...}]}}  — ціна в копійках, ділимо на 100.
  2. Загальний JSON: {"diesel": 52.3, "currency": "UAH"}  (запасний формат)
  3. HTML: число знаходиться regex-пошуком у тексті сторінки

При будь-якій помилці (мережа, таймаут, парсинг) — існуючий кеш у Redis
НЕ видаляється. Логуються WARNING, але сервіс продовжує роботу.

Примітка (Architecture): fuel_fetcher.py розміщено в auth-worker/app/scheduler/
згідно рішення з epics.md. Кандидат на перенесення в окремий сервіс у Phase 2.
"""
from __future__ import annotations

import json
import re

import httpx
import structlog

from app.core.config import settings

# Ключ Redis для зберігання ціни дизелю
FUEL_REDIS_KEY = "aetherion:fuel:price:diesel"

log = structlog.get_logger()


async def fetch_and_store_fuel_price(redis_client) -> None:
    """
    Отримує поточну ціну дизелю з зовнішнього джерела та зберігає в Redis.

    Ніколи не видаляє існуючий кеш при помилці — агент-сервіс продовжить
    використовувати останнє відоме значення.

    Якщо FUEL_PRICE_URL не налаштований — функція просто виходить без дій.

    Args:
        redis_client: Async Redis клієнт (redis.asyncio.Redis).

    Приклад (lifespan):
        asyncio.create_task(fetch_and_store_fuel_price(app.state.redis))
    """
    if not settings.fuel_price_url:
        log.debug("fuel_price_url_not_configured_skipping")
        return

    # Виконуємо HTTP запит до зовнішнього джерела цін
    try:
        async with httpx.AsyncClient(
            timeout=settings.fuel_price_http_timeout_seconds
        ) as client:
            response = await client.get(settings.fuel_price_url)
            response.raise_for_status()
    except httpx.TimeoutException:
        log.warning(
            "fuel_price_fetch_timeout",
            timeout_seconds=settings.fuel_price_http_timeout_seconds,
        )
        return
    except Exception:
        log.warning("fuel_price_fetch_failed_using_cache", exc_info=True)
        return

    # Парсимо отримані дані
    content_type = response.headers.get("content-type", "")
    price = _parse_price(response.text, content_type)

    if price is None:
        log.warning("fuel_price_parse_failed_using_cache", content_type=content_type)
        return

    # Зберігаємо в Redis із TTL
    try:
        await redis_client.set(
            FUEL_REDIS_KEY,
            str(price),
            ex=settings.fuel_cache_ttl_seconds,
        )
        log.info("fuel_price_fetched", price=price, currency="UAH")
    except Exception:
        log.warning("fuel_price_redis_store_failed", exc_info=True)


def _parse_price(body: str, content_type: str) -> float | None:
    """
    Витягує числове значення ціни дизелю ДП Євро5 з тіла HTTP-відповіді.

    Підтримує три формати (пріоритет зверху вниз):
      1. WOG API JSON: {"data": {"fuel_filters": [{"name": "ДП", "brand": "Євро5",
         "price": 8699}]}}
         Ціна в API зберігається в копійках — ділимо на 100 для отримання грн.
         ДП Євро5 = стандартний дизель Euro 5 для вантажівок (фур).
      2. Загальний JSON: {"diesel": <число>}
         Запасний формат для інших потенційних JSON-джерел.
      3. HTML/текст: regex-пошук першого числа у форматі "52.3" або "52,3"
         (якщо FUEL_PRICE_CSS_SELECTOR задано — шукаємо в його околицях).

    Args:
        body: Тіло HTTP-відповіді у вигляді рядка.
        content_type: Значення заголовку Content-Type відповіді.

    Returns:
        Ціна дизелю як float (наприклад, 86.99) або None якщо не вдалося розпарсити.

    Приклади:
        # WOG API формат:
        _parse_price('{"data": {"fuel_filters": [{"name": "ДП", "brand": "Євро5", "price": 8699}]}}',
                     "application/json")  # → 86.99
        # Загальний JSON:
        _parse_price('{"diesel": 52.3, "currency": "UAH"}', "application/json")  # → 52.3
        # HTML:
        _parse_price('<span class="price">52,30</span>', "text/html")  # → 52.3
    """
    # JSON формат — основний, найнадійніший варіант
    if "json" in content_type:
        try:
            data = json.loads(body)

            # Формат 1: WOG API — data.fuel_filters[].{name, brand, price(копійки)}
            fuel_filters = data.get("data", {}).get("fuel_filters", [])
            for fuel in fuel_filters:
                if fuel.get("name") == "ДП" and fuel.get("brand") == "Євро5":
                    # Ціна в копійках (наприклад, 8699 = 86.99 грн)
                    return round(float(fuel["price"]) / 100, 2)

            # Формат 2: загальний {"diesel": 52.3} — запасний варіант
            if "diesel" in data:
                return float(data["diesel"])

            return None
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            return None

    # HTML/текст — шукаємо ціну за допомогою regex
    # Якщо FUEL_PRICE_CSS_SELECTOR задано — шукаємо число після рядка-маркера
    search_body = body
    if settings.fuel_price_css_selector:
        # Шукаємо текст навколо CSS-селектора (спрощений підхід без повноцінного DOM)
        selector_pos = body.find(settings.fuel_price_css_selector)
        if selector_pos != -1:
            # Беремо 200 символів після знайденого маркера
            search_body = body[selector_pos : selector_pos + 200]

    # Знаходимо перше число у форматі "52.3" або "52,3" або "52"
    match = re.search(r"\b(\d{1,5}[.,]\d{1,3})\b", search_body)
    if match:
        try:
            return float(match.group(1).replace(",", "."))
        except ValueError:
            return None

    return None
