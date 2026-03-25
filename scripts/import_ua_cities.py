"""
scripts/import_ua_cities.py — Заповнює таблицю ua_cities основними містами України.

Джерела даних:
  - Lardi-Trans geo API (/webapi/geo/region-area-town/) — для lardi_town_id
  - Nominatim OpenStreetMap — для координат (lat, lon)

Запуск (всередині agent-service контейнера або локально з доступом до postgres):
    python scripts/import_ua_cities.py

Або через Docker:
    docker exec aetherion20-agent-service-1 python /scripts/import_ua_cities.py
"""

import asyncio
import os
import time

import httpx
import redis as redis_sync

# ── Налаштування ──────────────────────────────────────────────────────────────
POSTGRES_URL = os.environ.get(
    "POSTGRES_URL",
    "postgresql://aetherion:aetherion@postgres:5432/aetherion",
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
LTSID_KEY = "aetherion:auth:ltsid"

LARDI_BASE = "https://lardi-trans.com"
NOMINATIM_BASE = "https://nominatim.openstreetmap.org"

# Список основних міст України для імпорту
UA_CITIES = [
    "Київ", "Харків", "Одеса", "Дніпро", "Запоріжжя", "Львів",
    "Кривий Ріг", "Миколаїв", "Вінниця", "Херсон", "Полтава", "Чернігів",
    "Черкаси", "Суми", "Житомир", "Хмельницький", "Рівне", "Луцьк",
    "Тернопіль", "Івано-Франківськ", "Ужгород", "Чернівці", "Кропивницький",
    "Маріуполь", "Луганськ", "Донецьк", "Горлівка", "Макіївка",
    "Бердянськ", "Мелітополь", "Нікополь", "Кам'янське", "Павлоград",
    "Краматорськ", "Слов'янськ", "Лисичанськ", "Северодонецьк",
    "Дрогобич", "Мукачево", "Стрий", "Трускавець",
    "Біла Церква", "Бровари", "Бориспіль", "Ірпінь", "Буча",
    "Умань", "Кам'янець-Подільський", "Шостка", "Конотоп",
    "Прилуки", "Ніжин", "Коломия", "Калуш",
    "Нова Каховка", "Очаків", "Южноукраїнськ",
    "Лозова", "Ізюм", "Куп'янськ",
    "Дубно", "Броди", "Коростень", "Бердичів",
    "Кременчук", "Лубни", "Миргород",
]


def get_ltsid() -> str:
    """Отримує LTSID токен з Redis."""
    r = redis_sync.from_url(REDIS_URL, decode_responses=True)
    ltsid = r.get(LTSID_KEY)
    if not ltsid:
        raise RuntimeError("LTSID не знайдено в Redis. Переконайтесь що auth-worker healthy.")
    return ltsid


async def get_lardi_town_id(client: httpx.AsyncClient, city_name: str, ltsid: str) -> int | None:
    """Отримує Lardi town ID для міста через geo API."""
    try:
        resp = await client.get(
            f"{LARDI_BASE}/webapi/geo/region-area-town/",
            params={"query": city_name, "sign": "UA"},
            headers={
                "cookie": f"LTSID={ltsid}",
                "accept": "application/json",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "referer": f"{LARDI_BASE}/log/search/gruz/",
            },
            timeout=10.0,
        )
        if resp.status_code == 200:
            items = resp.json()
            # Шукаємо точний збіг типу TOWN
            for item in items:
                if item.get("type") == "TOWN" and city_name.lower() in item.get("name", "").lower():
                    return item["id"]
            # Якщо точного немає — беремо перший TOWN
            for item in items:
                if item.get("type") == "TOWN":
                    return item["id"]
    except Exception as e:
        print(f"  [WARN] Lardi geo API помилка для '{city_name}': {e}")
    return None


async def get_nominatim_coords(client: httpx.AsyncClient, city_name: str) -> tuple[float, float] | None:
    """Отримує координати міста через Nominatim."""
    try:
        resp = await client.get(
            f"{NOMINATIM_BASE}/search",
            params={
                "q": f"{city_name}, Україна",
                "format": "json",
                "limit": "1",
                "accept-language": "uk",
            },
            headers={"User-Agent": "Aetherion/2.0 city-import-script"},
            timeout=10.0,
        )
        if resp.status_code == 200:
            results = resp.json()
            if results:
                return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception as e:
        print(f"  [WARN] Nominatim помилка для '{city_name}': {e}")
    return None


async def insert_city(
    conn,
    name_ua: str,
    lat: float,
    lon: float,
    lardi_town_id: int | None,
) -> bool:
    """Вставляє місто в ua_cities. Повертає True якщо вставлено."""
    try:
        if lardi_town_id:
            await conn.execute(
                """
                INSERT INTO ua_cities (name_ua, lat, lon, lardi_town_id, source, created_at)
                VALUES ($1, $2, $3, $4, 'import', NOW())
                ON CONFLICT (lardi_town_id) DO UPDATE
                    SET name_ua=EXCLUDED.name_ua, lat=EXCLUDED.lat, lon=EXCLUDED.lon
                """,
                name_ua, lat, lon, lardi_town_id,
            )
        else:
            await conn.execute(
                """
                INSERT INTO ua_cities (name_ua, lat, lon, source, created_at)
                VALUES ($1, $2, $3, 'import', NOW())
                ON CONFLICT DO NOTHING
                """,
                name_ua, lat, lon,
            )
        return True
    except Exception as e:
        print(f"  [ERR] DB помилка для '{name_ua}': {e}")
        return False


async def main():
    import asyncpg

    print("=" * 60)
    print("Імпорт українських міст в ua_cities")
    print("=" * 60)

    # Отримуємо LTSID
    print("\n[1] Отримання LTSID з Redis...")
    ltsid = get_ltsid()
    print(f"    OK — LTSID: {ltsid[:8]}***")

    # Підключення до Postgres
    print("\n[2] Підключення до PostgreSQL...")
    db_url = POSTGRES_URL.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql://", "")
    conn = await asyncpg.connect(f"postgresql://{db_url}")
    print("    OK")

    stats = {"inserted": 0, "failed_coords": 0, "failed_db": 0}
    total = len(UA_CITIES)

    print(f"\n[3] Обробка {total} міст...\n")

    async with httpx.AsyncClient() as http_client:
        for i, city in enumerate(UA_CITIES, 1):
            print(f"  [{i:>3}/{total}] {city}...", end=" ", flush=True)

            # Координати від Nominatim
            coords = await get_nominatim_coords(http_client, city)
            if not coords:
                print("❌ coords not found")
                stats["failed_coords"] += 1
                continue

            lat, lon = coords

            # Lardi town ID
            town_id = await get_lardi_town_id(http_client, city, ltsid)

            # Вставляємо в БД
            ok = await insert_city(conn, city, lat, lon, town_id)
            if ok:
                id_str = f"id={town_id}" if town_id else "no lardi_id"
                print(f"✅ ({lat:.3f}, {lon:.3f}) {id_str}")
                stats["inserted"] += 1
            else:
                stats["failed_db"] += 1

            # Throttle — не флудимо Nominatim
            await asyncio.sleep(1.1)

    await conn.close()

    print("\n" + "=" * 60)
    print(f"Готово!")
    print(f"  Вставлено:       {stats['inserted']}")
    print(f"  Без координат:   {stats['failed_coords']}")
    print(f"  Помилки БД:      {stats['failed_db']}")

    # Підрахунок фінального стану
    conn2 = await asyncpg.connect(f"postgresql://{db_url}")
    count = await conn2.fetchval("SELECT COUNT(*) FROM ua_cities WHERE lardi_town_id IS NOT NULL")
    await conn2.close()
    print(f"  З lardi_town_id: {count}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
