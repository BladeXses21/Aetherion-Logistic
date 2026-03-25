"""
scripts/import_ua_cities_full.py — Повний імпорт ВСІХ міст України з Lardi-Trans.

Стратегія: перебираємо 1-2 літерні префікси через Lardi geo API і збираємо
всі унікальні TOWN. Координати не важливі для Lardi пошуку — головне lardi_town_id.

Запуск:
    docker exec aetherion20-agent-service-1 python import_ua_cities_full.py
"""

import asyncio
import os

import asyncpg
import httpx
import redis as redis_sync

POSTGRES_URL = os.environ.get(
    "POSTGRES_URL", "postgresql://aetherion:aetherion@postgres:5432/aetherion"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
LTSID_KEY = "aetherion:auth:ltsid"
LARDI_BASE = "https://lardi-trans.com"

# Всі літери + двобуквені комбінації для повного покриття
SINGLE = list("абвгґдеєжзиіїйклмнопрстуфхцчшщьюя")
DOUBLE = [
    f"{a}{b}"
    for a in "абвгдезікмноп рстухч"
    for b in "абвгдеєжзиіїйклмнопрстуфхцчш"
    if a.strip()
]
# Відомі складні префікси
EXTRA = [
    "кам", "кри", "кро", "кре", "іва", "іль",
    "пол", "пер", "при", "пра",
    "нов", "нор", "ніж",
    "вел", "вер", "він",
    "бел", "бер", "бой", "бро",
    "зап", "зах", "зол",
    "тер", "тро",
    "хар", "хмел",
    "чер", "чор",
    "шос", "шум",
]
ALL_PREFIXES = SINGLE + DOUBLE + EXTRA


def get_ltsid() -> str:
    r = redis_sync.from_url(REDIS_URL, decode_responses=True)
    ltsid = r.get(LTSID_KEY)
    if not ltsid:
        raise RuntimeError("LTSID не знайдено в Redis!")
    return ltsid


async def fetch_towns(client: httpx.AsyncClient, prefix: str, ltsid: str) -> list[dict]:
    """Отримує TOWN записи з Lardi geo API."""
    try:
        r = await client.get(
            f"{LARDI_BASE}/webapi/geo/region-area-town/",
            params={"query": prefix, "sign": "UA"},
            headers={
                "cookie": f"LTSID={ltsid}",
                "accept": "application/json",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "referer": f"{LARDI_BASE}/log/search/gruz/",
            },
            timeout=15.0,
        )
        if r.status_code == 200:
            return [t for t in r.json() if t.get("type") == "TOWN"]
    except Exception as e:
        print(f"  [WARN] '{prefix}': {e}")
    return []


async def main():
    print("=" * 60)
    print("Повний імпорт міст України з Lardi-Trans")
    print("=" * 60)

    ltsid = get_ltsid()
    print(f"\nLTSID: {ltsid[:8]}***")

    db_url = POSTGRES_URL.replace("postgresql+asyncpg://", "").replace("postgresql://", "")
    conn = await asyncpg.connect(f"postgresql://{db_url}")

    existing_ids = set(
        r["lardi_town_id"]
        for r in await conn.fetch(
            "SELECT lardi_town_id FROM ua_cities WHERE lardi_town_id IS NOT NULL"
        )
    )
    print(f"Вже в БД: {len(existing_ids)} міст з lardi_town_id")

    # ── Крок 1: Зібрати всі унікальні TOWN з Lardi ───────────────────────────
    print(f"\n[1] Збір міст ({len(ALL_PREFIXES)} префіксів)...\n")
    all_towns: dict[int, dict] = {}

    async with httpx.AsyncClient() as http:
        for i, prefix in enumerate(ALL_PREFIXES, 1):
            towns = await fetch_towns(http, prefix, ltsid)
            new = sum(1 for t in towns if t["id"] not in all_towns)
            for t in towns:
                all_towns[t["id"]] = t
            if new:
                print(f"  [{i:>4}/{len(ALL_PREFIXES)}] '{prefix}' → +{new} (всього: {len(all_towns)})")
            await asyncio.sleep(0.25)

    to_import = {tid: t for tid, t in all_towns.items() if tid not in existing_ids}
    print(f"\nЗібрано: {len(all_towns)} | Вже є: {len(existing_ids)} | Нових: {len(to_import)}")

    if not to_import:
        print("Нема нових міст.")
        await conn.close()
        return

    # ── Крок 2: Вставити в БД (без Nominatim — тільки lardi_town_id) ─────────
    print(f"\n[2] Запис {len(to_import)} нових міст у БД...")
    inserted = errors = 0

    for tid, town in to_import.items():
        full = town.get("name", "")
        # "Київ, Київська обл." → "Київ"
        city_name = full.split(",")[0].strip()
        try:
            await conn.execute(
                """
                INSERT INTO ua_cities (name_ua, lat, lon, lardi_town_id, source, created_at)
                VALUES ($1, 0.0, 0.0, $2, 'lardi-full', NOW())
                ON CONFLICT (lardi_town_id) DO NOTHING
                """,
                city_name, tid,
            )
            inserted += 1
        except Exception as e:
            errors += 1
            print(f"  [ERR] {city_name}: {e}")

    await conn.close()

    print("\n" + "=" * 60)
    print(f"Вставлено: {inserted} | Помилки: {errors}")

    conn2 = await asyncpg.connect(f"postgresql://{db_url}")
    total = await conn2.fetchval("SELECT COUNT(*) FROM ua_cities")
    with_id = await conn2.fetchval(
        "SELECT COUNT(*) FROM ua_cities WHERE lardi_town_id IS NOT NULL"
    )
    await conn2.close()
    print(f"ua_cities разом: {total} (з lardi_town_id: {with_id})")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
