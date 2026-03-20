"""test_admin_endpoint.py — Тести Story 2.4: Manual Session Management Admin Endpoint.

Тестує:
    - POST /admin/ltsid/refresh: валідний X-API-Key + Chrome success → HTTP 200 з коректним тілом
    - POST /admin/ltsid/refresh: невалідний або відсутній X-API-Key → HTTP 401 UNAUTHORIZED
    - POST /admin/ltsid/refresh: Chrome fails → HTTP 503 LTSID_FETCH_FAILED, LTSID не перезаписується
    - Реєстрація роутера в main.py
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from app.core.config import settings
from app.core.errors import ChromeStartupError, LtsidFetchError
from app.main import app
from app.session.ltsid_store import ltsid_store
from httpx import ASGITransport, AsyncClient

FAKE_LTSID = "abc123fake_ltsid_value_for_tests_xyz"
FAKE_TTL = 82800  # 23 години в секундах


# ---------------------------------------------------------------------------
# Фікстури
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_ltsid_store():
    """Скидає стан синглтона ltsid_store перед кожним тестом."""
    ltsid_store._ltsid_memory = None
    ltsid_store._mode = "missing"
    yield
    ltsid_store._ltsid_memory = None
    ltsid_store._mode = "missing"


@pytest.fixture(autouse=True)
def mock_app_redis():
    """Виставляє замоканий Redis клієнт в app.state перед кожним тестом."""
    mock_redis = AsyncMock()
    mock_redis.ttl = AsyncMock(return_value=FAKE_TTL)
    mock_redis.set = AsyncMock(return_value=True)
    app.state.redis = mock_redis
    yield mock_redis
    del app.state.redis


# ---------------------------------------------------------------------------
# Тести: HTTP 200 — валідний ключ + Chrome success
# ---------------------------------------------------------------------------


async def test_admin_refresh_valid_key_returns_200():
    """Валідний X-API-Key + Chrome success → HTTP 200."""
    with patch("app.api.admin.fetch_ltsid", new=AsyncMock(return_value=FAKE_LTSID)):
        with patch("app.api.admin.ltsid_store.store", new=AsyncMock()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/admin/ltsid/refresh",
                    headers={"X-API-Key": settings.admin_api_key},
                )

    assert response.status_code == 200


async def test_admin_refresh_valid_key_returns_status_ok():
    """Відповідь містить status='ok'."""
    with patch("app.api.admin.fetch_ltsid", new=AsyncMock(return_value=FAKE_LTSID)):
        with patch("app.api.admin.ltsid_store.store", new=AsyncMock()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/admin/ltsid/refresh",
                    headers={"X-API-Key": settings.admin_api_key},
                )

    assert response.json()["status"] == "ok"


async def test_admin_refresh_valid_key_returns_ltsid_ttl():
    """Відповідь містить ltsid_ttl_seconds як ціле число."""
    with patch("app.api.admin.fetch_ltsid", new=AsyncMock(return_value=FAKE_LTSID)):
        with patch("app.api.admin.ltsid_store.store", new=AsyncMock()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/admin/ltsid/refresh",
                    headers={"X-API-Key": settings.admin_api_key},
                )

    data = response.json()
    assert isinstance(data["ltsid_ttl_seconds"], int)
    assert data["ltsid_ttl_seconds"] == FAKE_TTL
    assert data["ltsid_ttl_seconds"] >= 0


async def test_admin_refresh_valid_key_returns_refreshed_at():
    """Відповідь містить refreshed_at як рядок ISO timestamp."""
    with patch("app.api.admin.fetch_ltsid", new=AsyncMock(return_value=FAKE_LTSID)):
        with patch("app.api.admin.ltsid_store.store", new=AsyncMock()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/admin/ltsid/refresh",
                    headers={"X-API-Key": settings.admin_api_key},
                )

    data = response.json()
    assert isinstance(data["refreshed_at"], str)
    assert len(data["refreshed_at"]) > 0


async def test_admin_refresh_calls_fetch_ltsid():
    """fetch_ltsid викликається з правильними аргументами при валідному ключі."""
    with patch(
        "app.api.admin.fetch_ltsid", new=AsyncMock(return_value=FAKE_LTSID)
    ) as mock_fetch:
        with patch("app.api.admin.ltsid_store.store", new=AsyncMock()):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post(
                    "/admin/ltsid/refresh",
                    headers={"X-API-Key": settings.admin_api_key},
                )

    mock_fetch.assert_called_once_with(
        login=settings.lardi_login,
        password=settings.lardi_password,
        timeout_seconds=settings.chrome_timeout_seconds,
    )


async def test_admin_refresh_calls_ltsid_store_on_success():
    """ltsid_store.store викликається після успішного отримання LTSID."""
    with patch("app.api.admin.fetch_ltsid", new=AsyncMock(return_value=FAKE_LTSID)):
        with patch(
            "app.api.admin.ltsid_store.store", new=AsyncMock()
        ) as mock_store:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post(
                    "/admin/ltsid/refresh",
                    headers={"X-API-Key": settings.admin_api_key},
                )

    mock_store.assert_called_once()


# ---------------------------------------------------------------------------
# Тести: HTTP 401 — невалідний або відсутній X-API-Key
# ---------------------------------------------------------------------------


async def test_admin_refresh_invalid_key_returns_401():
    """Невалідний X-API-Key → HTTP 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/admin/ltsid/refresh",
            headers={"X-API-Key": "wrong-key-123"},
        )

    assert response.status_code == 401


async def test_admin_refresh_invalid_key_returns_unauthorized_code():
    """Невалідний X-API-Key → тіло відповіді містить код UNAUTHORIZED."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/admin/ltsid/refresh",
            headers={"X-API-Key": "wrong-key-123"},
        )

    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert "message" in data["error"]


async def test_admin_refresh_missing_key_returns_401():
    """Відсутній X-API-Key → HTTP 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/admin/ltsid/refresh")

    assert response.status_code == 401


async def test_admin_refresh_missing_key_returns_unauthorized_code():
    """Відсутній X-API-Key → тіло відповіді містить код UNAUTHORIZED."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/admin/ltsid/refresh")

    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"


async def test_admin_refresh_invalid_key_does_not_call_chrome():
    """Невалідний ключ → fetch_ltsid НЕ викликається."""
    with patch(
        "app.api.admin.fetch_ltsid", new=AsyncMock(return_value=FAKE_LTSID)
    ) as mock_fetch:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post(
                "/admin/ltsid/refresh",
                headers={"X-API-Key": "wrong-key"},
            )

    mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# Тести: HTTP 503 — Chrome fails
# ---------------------------------------------------------------------------


async def test_admin_refresh_chrome_ltsid_error_returns_503():
    """LtsidFetchError → HTTP 503."""
    with patch(
        "app.api.admin.fetch_ltsid",
        new=AsyncMock(side_effect=LtsidFetchError("login failed")),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/admin/ltsid/refresh",
                headers={"X-API-Key": settings.admin_api_key},
            )

    assert response.status_code == 503


async def test_admin_refresh_chrome_startup_error_returns_503():
    """ChromeStartupError → HTTP 503."""
    with patch(
        "app.api.admin.fetch_ltsid",
        new=AsyncMock(side_effect=ChromeStartupError("no chrome")),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/admin/ltsid/refresh",
                headers={"X-API-Key": settings.admin_api_key},
            )

    assert response.status_code == 503


async def test_admin_refresh_chrome_fails_returns_ltsid_fetch_failed_code():
    """Chrome fail → тіло відповіді містить код LTSID_FETCH_FAILED."""
    with patch(
        "app.api.admin.fetch_ltsid",
        new=AsyncMock(side_effect=LtsidFetchError("fail")),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/admin/ltsid/refresh",
                headers={"X-API-Key": settings.admin_api_key},
            )

    data = response.json()
    assert data["error"]["code"] == "LTSID_FETCH_FAILED"


async def test_admin_refresh_chrome_fails_does_not_overwrite_ltsid():
    """Chrome fail → ltsid_store НЕ перезаписується (залишається 'missing')."""
    with patch(
        "app.api.admin.fetch_ltsid",
        new=AsyncMock(side_effect=LtsidFetchError("fail")),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post(
                "/admin/ltsid/refresh",
                headers={"X-API-Key": settings.admin_api_key},
            )

    assert ltsid_store._mode == "missing"


async def test_admin_refresh_chrome_fails_logs_error():
    """Chrome fail → логується ERROR 'ltsid_manual_refresh_failed'."""
    with patch(
        "app.api.admin.fetch_ltsid",
        new=AsyncMock(side_effect=LtsidFetchError("fail")),
    ):
        with patch("app.api.admin.log") as mock_log:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post(
                    "/admin/ltsid/refresh",
                    headers={"X-API-Key": settings.admin_api_key},
                )

    mock_log.error.assert_called_once_with(
        "ltsid_manual_refresh_failed", exc_info=True
    )
