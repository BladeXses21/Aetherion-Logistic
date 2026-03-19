"""
test_health.py — тести для GET /health endpoint auth-worker.

Перевіряє HTTP 200 (здоровий) та HTTP 503 (Redis недоступний).
app.state.redis встановлюється напряму, бо ASGITransport не запускає lifespan.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def mock_redis_ok():
    """Мок Redis клієнта — PING повертає True (Redis доступний)."""
    mock = AsyncMock()
    mock.ping = AsyncMock(return_value=True)
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def mock_redis_down():
    """Мок Redis клієнта — PING кидає exception (Redis недоступний)."""
    mock = AsyncMock()
    mock.ping = AsyncMock(side_effect=Exception("Connection refused"))
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
async def client_ok(mock_redis_ok):
    """AsyncClient з доступним Redis — app.state.redis встановлюється напряму."""
    app.state.redis = mock_redis_ok
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def client_redis_down(mock_redis_down):
    """AsyncClient з недоступним Redis."""
    app.state.redis = mock_redis_down
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_health_returns_200_when_healthy(client_ok):
    """GET /health повертає 200 і status=healthy коли Redis доступний."""
    response = await client_ok.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "auth-worker"
    assert data["dependencies"]["redis"] == "ok"


async def test_health_returns_503_when_redis_down(client_redis_down):
    """GET /health повертає 503 і status=unhealthy коли Redis недоступний."""
    response = await client_redis_down.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["dependencies"]["redis"] == "error"


async def test_health_response_has_required_fields(client_ok):
    """GET /health відповідь містить обов'язкові поля: status, service, dependencies."""
    response = await client_ok.get("/health")
    data = response.json()
    assert "status" in data
    assert "service" in data
    assert "dependencies" in data
    assert isinstance(data["dependencies"], dict)
