"""
geo_resolver.py — Сервіс розв'язання назв міст/країн у DirectionFilter для Lardi API.

Ланцюжок розв'язання (від точного до загального):
  1. In-memory кеш (session-level)
  2. Перевірка чи це назва країни (словник COUNTRY_UA_TO_SIGN)
  3. Точний пошук у таблиці ua_cities (case-insensitive)
  4. Нечіткий пошук за pg_trgm (схожість >= 0.4)
  5. Nominatim geocoding fallback → зберігає координати в ua_cities, повертає country-level
  6. Якщо все не знайдено → WARNING + повертає None

Якщо місто знайдено але lardi_town_id = NULL → автоматичний fallback до country-level.

Формат DirectionFilter для Lardi:
  Місто:    {"directionRows": [{"countrySign": "UA", "townId": 137}]}
  Країна:   {"directionRows": [{"countrySign": "PL"}]}

Використання:
    resolver = GeoResolver()
    direction = await resolver.resolve("Київ", db_session, http_client)
    # → {"directionRows": [{"countrySign": "UA", "townId": 137}]}
"""
from __future__ import annotations

import structlog
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import COUNTRY_UA_TO_SIGN, resolve_country_sign

log = structlog.get_logger()

# Мінімальний поріг схожості для pg_trgm
TRGM_THRESHOLD = 0.35

# Таймаут Nominatim HTTP-запиту (секунди)
NOMINATIM_TIMEOUT = 5.0

# Базовий URL Nominatim
NOMINATIM_BASE = "https://nominatim.openstreetmap.org"


class GeoResolver:
    """
    Розв'язувач назв місць у структури DirectionFilter для Lardi API.

    Зберігає in-memory кеш результатів протягом сесії агента.
    Один екземпляр створюється при старті сервісу та перевикористовується.

    Attributes:
        _cache: Словник назва_нижній_регістр → DirectionFilter dict або None
    """

    def __init__(self) -> None:
        """Ініціалізує GeoResolver з порожнім кешем."""
        self._cache: dict[str, dict | None] = {}

    async def resolve(
        self,
        name: str,
        db: AsyncSession,
        http_client: AsyncClient,
        user_agent: str = "Aetherion/2.0",
    ) -> dict | None:
        """
        Розв'язує назву міста або країни у DirectionFilter для Lardi API.

        Ланцюжок розв'язання:
          1. In-memory кеш → повертає збережений результат
          2. Якщо це назва країни → повертає {"directionRows": [{"countrySign": "XX"}]}
          3. Точний пошук у ua_cities (name_ua ILIKE name)
          4. pg_trgm нечіткий пошук у ua_cities (threshold=0.35)
          5. Nominatim → якщо знайдено → зберігає координати, повертає country-level
          6. Якщо нічого → логує WARNING, повертає None

        Args:
            name: Назва міста або країни (будь-який регістр).
            db: Активна асинхронна сесія PostgreSQL.
            http_client: Асинхронний httpx клієнт для Nominatim запитів.
            user_agent: User-Agent заголовок для Nominatim.

        Returns:
            DirectionFilter словник або None якщо розв'язання не вдалось.

        Приклад:
            await resolver.resolve("Київ", db, client)
            # → {"directionRows": [{"countrySign": "UA", "townId": 137}]}

            await resolver.resolve("Польща", db, client)
            # → {"directionRows": [{"countrySign": "PL"}]}
        """
        cache_key = name.lower().strip()

        # Крок 1: In-memory кеш
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = None

        # Крок 2: Перевіряємо чи це назва країни
        country_sign = resolve_country_sign(name)
        if country_sign:
            result = {"directionRows": [{"countrySign": country_sign}]}
            self._cache[cache_key] = result
            log.debug("geo_resolved_country", name=name, country_sign=country_sign)
            return result

        # Крок 3: Точний пошук у ua_cities
        result = await self._exact_match(name, db)
        if result:
            self._cache[cache_key] = result
            return result

        # Крок 4: Нечіткий пошук через pg_trgm
        result = await self._trgm_match(name, db)
        if result:
            self._cache[cache_key] = result
            return result

        # Крок 5: Nominatim geocoding fallback
        result = await self._nominatim_fallback(name, db, http_client, user_agent)
        if result:
            self._cache[cache_key] = result
            return result

        # Крок 6: Нічого не знайдено
        log.warning("geo_resolution_failed", name=name)
        self._cache[cache_key] = None
        return None

    async def _exact_match(self, name: str, db: AsyncSession) -> dict | None:
        """
        Точний пошук міста в ua_cities (case-insensitive).

        Args:
            name: Назва міста.
            db: Сесія PostgreSQL.

        Returns:
            DirectionFilter або None.
        """
        row = await db.execute(
            text(
                "SELECT lardi_town_id, name_ua FROM ua_cities "
                "WHERE LOWER(name_ua) = LOWER(:name) "
                "LIMIT 1"
            ),
            {"name": name},
        )
        city = row.fetchone()
        if city:
            return self._build_direction(city.lardi_town_id, "UA", name=city.name_ua)
        return None

    async def _trgm_match(self, name: str, db: AsyncSession) -> dict | None:
        """
        Нечіткий пошук міста в ua_cities за допомогою pg_trgm розширення.

        Встановлює мінімальний поріг схожості 0.35 (word_similarity).
        Повертає найближчий збіг якщо він вище порогу.

        Args:
            name: Назва міста для пошуку.
            db: Сесія PostgreSQL.

        Returns:
            DirectionFilter або None.
        """
        try:
            row = await db.execute(
                text(
                    "SELECT lardi_town_id, name_ua, "
                    "word_similarity(:name, name_ua) AS sim "
                    "FROM ua_cities "
                    "WHERE word_similarity(:name, name_ua) >= :threshold "
                    "ORDER BY sim DESC "
                    "LIMIT 1"
                ),
                {"name": name, "threshold": TRGM_THRESHOLD},
            )
            city = row.fetchone()
            if city:
                log.debug(
                    "geo_trgm_match",
                    query=name,
                    matched=city.name_ua,
                    similarity=round(city.sim, 3),
                )
                return self._build_direction(city.lardi_town_id, "UA", name=city.name_ua)
        except Exception:
            log.warning("geo_trgm_error", name=name, exc_info=True)
        return None

    async def _nominatim_fallback(
        self,
        name: str,
        db: AsyncSession,
        http_client: AsyncClient,
        user_agent: str,
    ) -> dict | None:
        """
        Geocoding через Nominatim (OpenStreetMap) як останній fallback.

        Якщо місто знайдено:
        - Зберігає координати (lat, lon) в ua_cities з source='nominatim' та lardi_town_id=NULL
        - Намагається отримати country_code з відповіді Nominatim
        - Повертає country-level DirectionFilter (оскільки lardi_town_id = NULL)

        Якщо Nominatim недоступний — логує WARNING та повертає None.

        Args:
            name: Назва міста для geocoding.
            db: Сесія PostgreSQL для збереження нових міст.
            http_client: Асинхронний httpx клієнт.
            user_agent: User-Agent рядок для Nominatim.

        Returns:
            Country-level DirectionFilter або None.
        """
        try:
            response = await http_client.get(
                f"{NOMINATIM_BASE}/search",
                params={
                    "q": name,
                    "format": "json",
                    "addressdetails": "1",
                    "limit": "1",
                    "accept-language": "uk",
                },
                headers={"User-Agent": user_agent},
                timeout=NOMINATIM_TIMEOUT,
            )
            response.raise_for_status()
            results = response.json()

            if not results:
                log.debug("geo_nominatim_no_results", name=name)
                return None

            place = results[0]
            lat = float(place.get("lat", 0))
            lon = float(place.get("lon", 0))
            address = place.get("address", {})
            country_code: str | None = address.get("country_code", "").upper() or None

            log.info(
                "geo_nominatim_found",
                name=name,
                lat=lat,
                lon=lon,
                country_code=country_code,
            )

            # Зберігаємо місто в ua_cities з lardi_town_id=NULL
            try:
                await db.execute(
                    text(
                        "INSERT INTO ua_cities (name_ua, lat, lon, source, created_at) "
                        "VALUES (:name, :lat, :lon, 'nominatim', NOW()) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {"name": name, "lat": lat, "lon": lon},
                )
                await db.commit()
            except Exception:
                await db.rollback()
                log.warning("geo_nominatim_save_failed", name=name, exc_info=True)

            # Повертаємо country-level якщо є country_code
            if country_code:
                return {"directionRows": [{"countrySign": country_code}]}

            return None

        except Exception:
            log.warning("geo_nominatim_error", name=name, exc_info=True)
            return None

    @staticmethod
    def _build_direction(
        lardi_town_id: int | None, country_sign: str, name: str = ""
    ) -> dict:
        """
        Будує DirectionFilter словник для Lardi API.

        Якщо lardi_town_id присутній → city-level фільтр.
        Якщо lardi_town_id = None → country-level фільтр.

        Args:
            lardi_town_id: Ідентифікатор міста в Lardi (або None).
            country_sign: ISO 3166-1 alpha-2 код країни (наприклад "UA").
            name: Назва міста для логування.

        Returns:
            DirectionFilter словник з полем directionRows.
        """
        if lardi_town_id is not None:
            return {
                "directionRows": [
                    {"countrySign": country_sign, "townId": lardi_town_id}
                ]
            }
        else:
            log.debug(
                "geo_fallback_to_country",
                city=name,
                reason="lardi_town_id_null",
            )
            return {"directionRows": [{"countrySign": country_sign}]}


# Singleton екземпляр — ініціалізується при старті сервісу
geo_resolver = GeoResolver()
