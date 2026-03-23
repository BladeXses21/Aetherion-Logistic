"""
lardi_client.py — HTTP-клієнт для взаємодії з Lardi API.

Інкапсулює всі запити до Lardi за допомогою httpx.
Зберігається як app.state.lardi_client в lifespan FastAPI-застосунку.

Клієнт не підтримує постійне з'єднання — кожен запит створює новий
httpx.AsyncClient (stateless), що дозволяє легко тестувати та
уникати проблем з session management.
"""
from __future__ import annotations

import httpx
import structlog


class LardiTimeoutError(Exception):
    """Виникає при перевищенні таймауту HTTP-запиту до Lardi."""


class LardiHTTPError(Exception):
    """
    Виникає при отриманні не-2xx відповіді від Lardi API.

    Attributes:
        status_code: HTTP статус-код відповіді від Lardi.
    """

    def __init__(self, status_code: int, body: str = "") -> None:
        """
        Ініціалізує помилку з HTTP статус-кодом та тілом відповіді.

        Args:
            status_code: HTTP статус-код відповіді від Lardi (наприклад, 401, 500).
            body: Тіло відповіді (необов'язковий, для відладки).
        """
        self.status_code = status_code
        self.body = body
        super().__init__(f"Lardi HTTP error {status_code}")


class LardiClient:
    """
    HTTP-клієнт для Lardi API.

    Виконує авторизовані запити до Lardi, використовуючи LTSID cookie.
    Логує всі запити та помилки через structlog з прив'язкою request_id.

    Використання (lifespan):
        lardi_client = LardiClient(settings.lardi_base_url, settings.lardi_http_timeout_seconds)
        app.state.lardi_client = lardi_client
        ...
        result = await lardi_client.search(payload, ltsid="...", request_id="...")
    """

    # Шлях до ендпоінту пошуку вантажів на Lardi
    SEARCH_PATH = "/webapi/proposal/search/gruz/"

    def __init__(self, base_url: str, timeout_seconds: int) -> None:
        """
        Ініціалізує клієнт з базовим URL та таймаутом.

        Args:
            base_url: Базовий URL Lardi API (наприклад, "https://lardi-trans.com").
            timeout_seconds: Таймаут HTTP-запиту в секундах.
        """
        self._base_url = base_url
        self._timeout = timeout_seconds

    async def search(self, payload: dict, ltsid: str, request_id: str) -> dict:
        """
        Виконує POST /webapi/proposal/search/gruz/ з LTSID cookie.

        Надсилає пошуковий запит до Lardi API з авторизацією через cookie LTSID.
        Логує початок запиту, успіх або помилку через structlog з request_id.

        Args:
            payload: Словник з параметрами пошуку у форматі Lardi API
                     (page, size, filter з напрямками та фільтрами).
            ltsid: Значення cookie LTSID для авторизації на Lardi.
            request_id: UUID запиту — додається до всіх structlog подій.

        Returns:
            Розпарсений JSON-словник відповіді від Lardi API.

        Raises:
            LardiTimeoutError: якщо Lardi не відповів протягом timeout_seconds секунд.
            LardiHTTPError: якщо Lardi повернув не-2xx статус (включаючи 401).

        Приклад:
            result = await lardi_client.search(
                payload={"page": 1, "size": 20, "filter": {...}},
                ltsid="abc123...",
                request_id="550e8400-e29b-41d4-a716-446655440000",
            )
            proposals = result["result"]["proposals"]
        """
        log = structlog.get_logger().bind(request_id=request_id)

        # Заголовки імітують браузер — Lardi може блокувати запити без Referer/Origin
        headers = {
            "Content-Type": "application/json",
            "Cookie": f"LTSID={ltsid}",
            "Referer": "https://lardi-trans.com/log/search/gruz/",
            "Origin": "https://lardi-trans.com",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }

        log.info("lardi_search_started", url=f"{self._base_url}{self.SEARCH_PATH}")

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}{self.SEARCH_PATH}",
                    json=payload,
                    headers=headers,
                )
        except httpx.TimeoutException:
            log.warning(
                "lardi_search_timeout",
                timeout_seconds=self._timeout,
            )
            raise LardiTimeoutError()

        # 401 — сесія застаріла, LTSID потрібно оновити
        if response.status_code == 401:
            log.warning("lardi_search_unauthorized", status_code=401)
            raise LardiHTTPError(401, response.text)

        if not response.is_success:
            log.error(
                "lardi_search_http_error",
                status_code=response.status_code,
                body=response.text[:200],
            )
            raise LardiHTTPError(response.status_code, response.text)

        log.info("lardi_search_success", status_code=response.status_code)
        return response.json()
