"""
test_health.py — тести для GET /health endpoint api-gateway.

api-gateway перевіряє 3 залежності: Redis, Postgres, agent-service.
Всі зовнішні залежності мокуються для offline тестування.
app.state.redis встановлюється напряму, бо ASGITransport не запускає lifespan.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def mock_redis_ok():
    """Мок Redis клієнта — PING повертає True."""
    mock = AsyncMock()
    mock.ping = AsyncMock(return_value=True)
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
def mock_redis_down():
    """Мок Redis клієнта — PING кидає exception."""
    mock = AsyncMock()
    mock.ping = AsyncMock(side_effect=Exception("Connection refused"))
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
async def client_all_ok(mock_redis_ok):
    """AsyncClient — всі залежності доступні (Redis + Postgres + agent-service)."""
    app.state.redis = mock_redis_ok
    with (
        patch("app.api.health._check_postgres", return_value="ok"),
        patch("app.api.health._check_agent_service", return_value="ok"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


@pytest.fixture
async def client_redis_down(mock_redis_down):
    """AsyncClient — Redis недоступний, решта OK."""
    app.state.redis = mock_redis_down
    with (
        patch("app.api.health._check_postgres", return_value="ok"),
        patch("app.api.health._check_agent_service", return_value="ok"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


@pytest.fixture
async def client_postgres_down(mock_redis_ok):
    """AsyncClient — Postgres недоступний, решта OK."""
    app.state.redis = mock_redis_ok
    with (
        patch("app.api.health._check_postgres", return_value="error"),
        patch("app.api.health._check_agent_service", return_value="ok"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


@pytest.fixture
async def client_agent_down(mock_redis_ok):
    """AsyncClient — agent-service недоступний, решта OK."""
    app.state.redis = mock_redis_ok
    with (
        patch("app.api.health._check_postgres", return_value="ok"),
        patch("app.api.health._check_agent_service", return_value="error"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


async def test_health_returns_200_when_all_healthy(client_all_ok):
    """GET /health повертає 200 коли всі залежності доступні."""
    response = await client_all_ok.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "api-gateway"
    assert data["dependencies"]["redis"] == "ok"
    assert data["dependencies"]["postgres"] == "ok"
    assert data["dependencies"]["agent-service"] == "ok"


async def test_health_returns_503_when_redis_down(client_redis_down):
    """GET /health повертає 503 якщо Redis недоступний."""
    response = await client_redis_down.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["dependencies"]["redis"] == "error"
    # Інші залежності залишаються ok
    assert data["dependencies"]["postgres"] == "ok"
    assert data["dependencies"]["agent-service"] == "ok"


async def test_health_returns_503_when_postgres_down(client_postgres_down):
    """GET /health повертає 503 якщо Postgres недоступний."""
    response = await client_postgres_down.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["dependencies"]["postgres"] == "error"


async def test_health_returns_503_when_agent_service_down(client_agent_down):
    """GET /health повертає 503 якщо agent-service недоступний."""
    response = await client_agent_down.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["dependencies"]["agent-service"] == "error"


async def test_health_response_has_required_fields(client_all_ok):
    """GET /health відповідь містить обов'язкові поля: status, service, dependencies."""
    response = await client_all_ok.get("/health")
    data = response.json()
    assert "status" in data
    assert "service" in data
    assert "dependencies" in data
    assert isinstance(data["dependencies"], dict)
    assert len(data["dependencies"]) == 3  # redis, postgres, agent-service
