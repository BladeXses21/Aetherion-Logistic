"""
lardi_client.py — HTTP клієнт для взаємодії з lardi-connector сервісом.

Інкапсулює всі HTTP-запити до lardi-connector:
  - POST /search  → пошук вантажів
  - GET /cargo/{id} → деталі вантажу + телефон

LTSID cookie управляється виключно в lardi-connector — agent-service ніколи
не отримує та не логує значення LTSID.

Використання:
    async with LardiConnectorClient(settings.lardi_connector_url) as client:
        response = await client.search(request)
        detail = await client.get_cargo_detail(cargo_id)
"""
from __future__ import annotations

import structlog
from httpx import AsyncClient, HTTPStatusError, TimeoutException

from app.core.config import settings

log = structlog.get_logger()

# Таймаут HTTP-запитів до lardi-connector (секунди)
HTTP_TIMEOUT = 30.0


class LardiConnectorClient:
    """
    Асинхронний HTTP клієнт для lardi-connector.

    Використовує httpx.AsyncClient з базовим URL lardi-connector.
    Рекомендується використовувати як context manager.

    Args:
        base_url: Базовий URL lardi-connector сервісу.

    Приклад:
        async with LardiConnectorClient() as client:
            results = await client.search(search_request_dict)
    """

    def __init__(self, base_url: str | None = None) -> None:
        """Ініціалізує клієнт з базовим URL."""
        self._base_url = base_url or settings.lardi_connector_url
        self._client: AsyncClient | None = None

    async def __aenter__(self) -> "LardiConnectorClient":
        """Відкриває HTTP-з'єднання."""
        self._client = AsyncClient(
            base_url=self._base_url,
            timeout=HTTP_TIMEOUT,
        )
        return self

    async def __aexit__(self, *args) -> None:
        """Закриває HTTP-з'єднання."""
        if self._client:
            await self._client.aclose()

    async def search(self, request_dict: dict) -> dict:
        """
        Виконує пошук вантажів через lardi-connector.

        Відправляє POST /search з JSON-тілом запиту.
        Повертає десеріалізовану відповідь CargoSearchResponse.

        Args:
            request_dict: Словник запиту у форматі CargoSearchRequest:
                {
                    "directionFrom": {"directionRows": [...]},
                    "directionTo": {"directionRows": [...]},
                    "bodyTypeIds": [...],
                    "mass1": float | None,
                    ...
                }

        Returns:
            Словник CargoSearchResponse з полями proposals, total_size, capped тощо.

        Raises:
            RuntimeError: При HTTP помилці або таймауті.
        """
        if not self._client:
            raise RuntimeError("LardiConnectorClient не ініціалізовано. Використовуй як context manager.")

        try:
            response = await self._client.post("/search", json=request_dict)
            response.raise_for_status()
            return response.json()
        except TimeoutException:
            log.warning("lardi_client_search_timeout", timeout=HTTP_TIMEOUT)
            raise RuntimeError("lardi-connector search timeout")
        except HTTPStatusError as e:
            log.warning(
                "lardi_client_search_error",
                status=e.response.status_code,
                body=e.response.text[:200],
            )
            raise RuntimeError(f"lardi-connector search error: {e.response.status_code}")

    async def get_cargo_detail(self, cargo_id: int) -> dict:
        """
        Отримує детальну інформацію про конкретний вантаж.

        Відправляє GET /cargo/{cargo_id} та повертає CargoDetailResponse.
        Включає контактний телефон вантажовідправника (якщо доступний).

        Args:
            cargo_id: Унікальний ідентифікатор вантажу в Lardi.

        Returns:
            Словник CargoDetailResponse з полями id, shipper_phone, route тощо.

        Raises:
            ValueError: Якщо вантаж не знайдено (HTTP 404).
            RuntimeError: При інших HTTP помилках або таймауті.
        """
        if not self._client:
            raise RuntimeError("LardiConnectorClient не ініціалізовано. Використовуй як context manager.")

        try:
            response = await self._client.get(f"/cargo/{cargo_id}")
            if response.status_code == 404:
                raise ValueError(f"Вантаж {cargo_id} не знайдено в Lardi")
            response.raise_for_status()
            return response.json()
        except TimeoutException:
            log.warning("lardi_client_detail_timeout", cargo_id=cargo_id)
            raise RuntimeError(f"lardi-connector detail timeout для cargo {cargo_id}")
        except HTTPStatusError as e:
            log.warning(
                "lardi_client_detail_error",
                cargo_id=cargo_id,
                status=e.response.status_code,
            )
            raise RuntimeError(f"lardi-connector detail error: {e.response.status_code}")
