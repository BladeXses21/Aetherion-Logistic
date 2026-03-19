"""test_ltsid_acquisition.py — Тести Story 2.1: Initial LTSID Acquisition on Startup.

Тестує логіку отримання, зберігання та відображення LTSID у /health:
    - Успішне отримання LTSID та збереження у Redis
    - Fallback в пам'ять коли Redis недоступний
    - Обробка помилки Chrome (сервіс стартує, /health = missing)
    - Credentials НЕ потрапляють у логи
    - /health показує коректний статус залежно від стану LTSID

Всі тести замінюють реальний Chrome мок-функцією щоб уникнути залежності
від браузера в CI/CD середовищі.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.errors import ChromeStartupError, LtsidFetchError
from app.main import _fetch_initial_ltsid, app
from app.session.ltsid_store import LtsidStore, ltsid_store

FAKE_LTSID = "abc123fake_ltsid_value_for_tests_xyz"


# ---------------------------------------------------------------------------
# Фікстури
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_ltsid_store():
    """Скидає стан модульного синглтона ltsid_store перед кожним тестом."""
    ltsid_store._ltsid_memory = None
    ltsid_store._mode = "missing"
    yield
    ltsid_store._ltsid_memory = None
    ltsid_store._mode = "missing"


@pytest.fixture
def mock_redis_ok():
    """Мок Redis — успішні команди SET/GET/PING."""
    mock = AsyncMock()
    mock.ping = AsyncMock(return_value=True)
    mock.set = AsyncMock(return_value=True)
    mock.get = AsyncMock(return_value=FAKE_LTSID)
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def mock_redis_down():
    """Мок Redis — всі команди кидають exception (Redis недоступний)."""
    mock = AsyncMock()
    mock.ping = AsyncMock(side_effect=Exception("Connection refused"))
    mock.set = AsyncMock(side_effect=Exception("Connection refused"))
    mock.get = AsyncMock(side_effect=Exception("Connection refused"))
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
async def client_with_ltsid(mock_redis_ok):
    """HTTP клієнт із доступним Redis та valid LTSID."""
    app.state.redis = mock_redis_ok
    ltsid_store._ltsid_memory = FAKE_LTSID
    ltsid_store._mode = "valid"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def client_ltsid_in_memory(mock_redis_ok):
    """HTTP клієнт: LTSID є в пам'яті але Redis недоступний при збереженні."""
    app.state.redis = mock_redis_ok
    ltsid_store._ltsid_memory = FAKE_LTSID
    ltsid_store._mode = "in_memory_only"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def client_ltsid_missing(mock_redis_ok):
    """HTTP клієнт: LTSID відсутній (Chrome login провалився)."""
    app.state.redis = mock_redis_ok
    ltsid_store._ltsid_memory = None
    ltsid_store._mode = "missing"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Тести: _fetch_initial_ltsid (логіка запуску при lifespan)
# ---------------------------------------------------------------------------


async def test_successful_ltsid_stored_in_redis(mock_redis_ok):
    """Успішний fetch_ltsid зберігає LTSID у Redis і виставляє mode=valid."""
    with patch("app.main.fetch_ltsid", new=AsyncMock(return_value=FAKE_LTSID)):
        await _fetch_initial_ltsid(mock_redis_ok)

    assert ltsid_store._mode == "valid"
    assert ltsid_store._ltsid_memory == FAKE_LTSID
    mock_redis_ok.set.assert_called_once()
    # Перевіряємо що ключ правильний
    call_args = mock_redis_ok.set.call_args
    assert call_args[0][0] == "aetherion:auth:ltsid"
    assert call_args[0][1] == FAKE_LTSID


async def test_successful_ltsid_ttl_correct(mock_redis_ok):
    """Redis SET викликається з правильним TTL у секундах (23 год = 82800 сек)."""
    with patch("app.main.fetch_ltsid", new=AsyncMock(return_value=FAKE_LTSID)):
        with patch("app.main.settings") as mock_settings:
            mock_settings.lardi_login = "user@test.com"
            mock_settings.lardi_password = "secret"
            mock_settings.chrome_timeout_seconds = 60
            mock_settings.ltsid_ttl_hours = 23
            await _fetch_initial_ltsid(mock_redis_ok)

    call_kwargs = mock_redis_ok.set.call_args[1]
    assert call_kwargs.get("ex") == 23 * 3600


async def test_redis_unavailable_ltsid_stored_in_memory(mock_redis_down):
    """При недоступному Redis LTSID зберігається в пам'яті, mode=in_memory_only."""
    with patch("app.main.fetch_ltsid", new=AsyncMock(return_value=FAKE_LTSID)):
        await _fetch_initial_ltsid(mock_redis_down)

    assert ltsid_store._mode == "in_memory_only"
    assert ltsid_store._ltsid_memory == FAKE_LTSID


async def test_chrome_ltsid_fetch_error_sets_missing(mock_redis_ok):
    """LtsidFetchError призводить до mode=missing, сервіс НЕ крашиться."""
    with patch("app.main.fetch_ltsid", new=AsyncMock(side_effect=LtsidFetchError("login failed"))):
        # Не має кидати exception — lifespan продовжується
        await _fetch_initial_ltsid(mock_redis_ok)

    assert ltsid_store._mode == "missing"
    assert ltsid_store._ltsid_memory is None


async def test_chrome_startup_error_sets_missing(mock_redis_ok):
    """ChromeStartupError також призводить до mode=missing без краша сервісу."""
    with patch("app.main.fetch_ltsid", new=AsyncMock(side_effect=ChromeStartupError("no chrome"))):
        await _fetch_initial_ltsid(mock_redis_ok)

    assert ltsid_store._mode == "missing"


async def test_unexpected_exception_sets_missing(mock_redis_ok):
    """Будь-який непередбачений виняток НЕ зупиняє сервіс, mode=missing."""
    with patch("app.main.fetch_ltsid", new=AsyncMock(side_effect=RuntimeError("unexpected"))):
        await _fetch_initial_ltsid(mock_redis_ok)

    assert ltsid_store._mode == "missing"


# ---------------------------------------------------------------------------
# Тести: /health endpoint — LTSID статуси
# ---------------------------------------------------------------------------


async def test_health_valid_ltsid_returns_200(client_with_ltsid):
    """GET /health повертає 200 і ltsid=valid коли LTSID успішно збережено."""
    response = await client_with_ltsid.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["dependencies"]["ltsid"] == "valid"
    assert data["dependencies"]["redis"] == "ok"


async def test_health_in_memory_only_returns_200(client_ltsid_in_memory):
    """GET /health повертає 200 коли LTSID є в пам'яті (Redis fallback)."""
    response = await client_ltsid_in_memory.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["dependencies"]["ltsid"] == "in_memory_only"


async def test_health_missing_ltsid_returns_503(client_ltsid_missing):
    """GET /health повертає 503 якщо LTSID не отримано (Chrome fail)."""
    response = await client_ltsid_missing.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["dependencies"]["ltsid"] == "missing"


# ---------------------------------------------------------------------------
# Тести: LtsidStore — unit тести сховища
# ---------------------------------------------------------------------------


async def test_ltsid_store_get_from_redis_preferred():
    """LtsidStore.get() повертає значення з Redis якщо воно є."""
    store = LtsidStore()
    store._ltsid_memory = "memory_value"
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value="redis_value")

    result = await store.get(mock_redis)
    assert result == "redis_value"


async def test_ltsid_store_get_fallback_to_memory():
    """LtsidStore.get() повертає in-memory значення якщо Redis недоступний."""
    store = LtsidStore()
    store._ltsid_memory = "memory_fallback"
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=Exception("connection error"))

    result = await store.get(mock_redis)
    assert result == "memory_fallback"


async def test_ltsid_store_get_returns_none_when_empty():
    """LtsidStore.get() повертає None якщо ні Redis, ні пам'ять не містять LTSID."""
    store = LtsidStore()
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    result = await store.get(mock_redis)
    assert result is None


async def test_ltsid_store_store_sets_correct_key():
    """LtsidStore.store() записує у Redis з правильним ключем aetherion:auth:ltsid."""
    store = LtsidStore()
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)

    await store.store(mock_redis, FAKE_LTSID, ttl_hours=23)

    mock_redis.set.assert_called_once_with("aetherion:auth:ltsid", FAKE_LTSID, ex=82800)


async def test_ltsid_store_health_status_initial():
    """Початковий стан LtsidStore — mode=missing."""
    store = LtsidStore()
    assert store.health_status == "missing"


async def test_ltsid_store_mark_missing():
    """LtsidStore.mark_missing() скидає стан до missing."""
    store = LtsidStore()
    store._mode = "valid"
    store.mark_missing()
    assert store.health_status == "missing"


# ---------------------------------------------------------------------------
# Тест: credentials НЕ логуються
# ---------------------------------------------------------------------------


async def test_credentials_not_logged(mock_redis_ok, capfd):
    """Перевіряє що LARDI_PASSWORD та повний LTSID не з'являються у stdout/stderr."""
    secret_password = "SuperSecretPassword123!"
    full_ltsid = "a" * 64  # повне значення LTSID

    with patch("app.main.fetch_ltsid", new=AsyncMock(return_value=full_ltsid)):
        with patch("app.main.settings") as mock_settings:
            mock_settings.lardi_login = "user@test.com"
            mock_settings.lardi_password = secret_password
            mock_settings.chrome_timeout_seconds = 60
            mock_settings.ltsid_ttl_hours = 23
            await _fetch_initial_ltsid(mock_redis_ok)

    captured = capfd.readouterr()
    assert secret_password not in captured.out
    assert secret_password not in captured.err
    # Повний LTSID не повинен з'являтись у логах (лише перші 8 символів)
    assert full_ltsid not in captured.out
    assert full_ltsid not in captured.err
