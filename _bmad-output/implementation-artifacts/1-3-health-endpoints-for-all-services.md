# Story 1.3: Health Endpoints for All Services

Status: done

## Story

As an operator,
I want a `/health` endpoint on every service,
so that I can verify system status at a glance without entering Docker containers.

## Acceptance Criteria

**AC1:** Given all services are running healthy
When `GET /health` is called on each service port
Then each returns HTTP 200 with `{"status": "healthy", "service": "<name>", "dependencies": {...}}`
And `api-gateway /health` checks: Redis reachable, Postgres reachable, agent-service reachable
And `agent-service /health` checks: Redis reachable
And `lardi-connector /health` checks: Redis reachable
And `auth-worker /health` checks: Redis reachable (LTSID check deferred to Story 2.1)

**AC2:** Given Redis is stopped
When `GET /health` is called on any Redis-dependent service
Then response is HTTP 503 with `"status": "unhealthy"` and failing dependency marked as `"error"`
And healthy dependencies remain marked as `"ok"`

**AC3:** Given all services running
When `GET /docs` is accessed on `api-gateway:8000`
Then Swagger UI is accessible without authentication (already works — verify not broken)

**AC4:** Given `/health` is implemented on all services
When `docker compose up` is run
Then all 4 Python service healthchecks pass using HTTP GET `/health` (replacing TCP socket fallback from Story 1.1)

## Tasks / Subtasks

- [x] Task 1: Initialize Redis connection pool in lifespan for all 4 services (AC: #1, #2)
  - [x]`api-gateway/app/main.py` — init `redis.asyncio.from_url()` → `app.state.redis`; `aclose()` on shutdown (replace `# TODO Story 1.3: initialize Redis pool` comments)
  - [x]`agent-service/app/main.py` — same Redis pool pattern
  - [x]`lardi-connector/app/main.py` — same Redis pool pattern
  - [x]`auth-worker/app/main.py` — same Redis pool pattern

- [x] Task 2: Create `app/api/health.py` for all 4 services (AC: #1, #2)
  - [x]`api-gateway/app/api/health.py` — checks Redis (`ping`), Postgres (`SELECT 1`), agent-service (`GET /health`)
  - [x]`agent-service/app/api/health.py` — checks Redis (`ping`) only
  - [x]`lardi-connector/app/api/health.py` — checks Redis (`ping`) only
  - [x]`auth-worker/app/api/health.py` — checks Redis (`ping`) only

- [x] Task 3: Register health router in `app/main.py` for all 4 services (AC: #1)
  - [x]Each `main.py`: `app.include_router(health.router)`

- [x] Task 4: Update `docker-compose.yml` healthchecks (AC: #4)
  - [x]Replace TCP socket checks with HTTP GET `/health` for all 4 Python services

- [x] Task 5: Write tests and validate (AC: #1, #2)
  - [x]`api-gateway/tests/test_health.py` — test 200 healthy + 503 Redis down
  - [x]`agent-service/tests/test_health.py` — test 200 healthy + 503 Redis down
  - [x]`lardi-connector/tests/test_health.py` — test 200 healthy + 503 Redis down
  - [x]`auth-worker/tests/test_health.py` — test 200 healthy + 503 Redis down
  - [x]Run `ruff check .` across all 4 services — 0 errors
  - [x]Run `python -m pytest tests/ -v` in each service — all pass

- [x] Task 6: Verify end-to-end in Docker (AC: #1, #2, #3, #4)
  - [x]`docker compose up --build -d` — all 10 containers healthy
  - [x]`curl http://localhost:8000/health` → 200 healthy
  - [x]`curl http://localhost:8001/health` → 200 healthy
  - [x]`curl http://localhost:8002/health` → 200 healthy
  - [x]`curl http://localhost:8003/health` → 200 healthy
  - [x]`curl http://localhost:8000/docs` → 200 (Swagger UI not broken)

---

## Dev Notes

### Scope Boundary

**IN SCOPE (Story 1.3):**
- Redis pool init in lifespan for all 4 services
- `app/api/health.py` in each service with dependency checks
- Register router in each `main.py`
- Update `docker-compose.yml` healthchecks from TCP to HTTP
- Tests for health endpoints

**OUT OF SCOPE (deferred):**
- `auth-worker /health` LTSID check (`"ltsid": "valid"`) → Story 2.1 (no Chrome/LTSID yet)
- `agent-service /health` LLM ping check → Story 4.1
- Any other endpoints (chat, workspaces, search) → Epic 4

---

### File: Redis Pool Pattern (ALL 4 services — identical pattern)

```python
# In app/main.py — update lifespan to initialize Redis pool
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI

from app.api import health
from app.core.config import settings  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ініціалізація Redis pool при старті сервісу
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    yield
    # Закриття Redis pool при зупинці сервісу
    await app.state.redis.aclose()


app = FastAPI(title="...", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
```

**CRITICAL for api-gateway:** keep existing engine.dispose() in lifespan — do NOT remove it:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    yield
    await engine.dispose()          # ← Story 1.2: keep this
    await app.state.redis.aclose()  # ← Story 1.3: add this
```

`redis.from_url()` creates a connection pool — does NOT connect on creation, connects lazily on first command. This is correct — no timeout on startup if Redis is slow.

---

### File: `app/api/health.py` — agent-service, lardi-connector, auth-worker (identical)

```python
"""
health.py — GET /health endpoint.

Перевіряє доступність Redis. Повертає 200 якщо здоровий, 503 якщо ні.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = structlog.get_logger()

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    """Перевірка стану сервісу та залежностей (Redis).

    Returns:
        200 {"status": "healthy", "service": "<name>", "dependencies": {"redis": "ok"}}
        503 {"status": "unhealthy", ...} якщо Redis недоступний
    """
    redis_status = await _check_redis(request.app.state.redis)
    dependencies = {"redis": redis_status}
    all_ok = all(v == "ok" for v in dependencies.values())
    status = "healthy" if all_ok else "unhealthy"
    http_code = 200 if all_ok else 503

    if not all_ok:
        log.warning("health_check_degraded", service="<service-name>", dependencies=dependencies)

    return JSONResponse(
        status_code=http_code,
        content={"status": status, "service": "<service-name>", "dependencies": dependencies},
    )


async def _check_redis(client) -> str:
    """Перевіряє доступність Redis через PING команду."""
    try:
        await client.ping()
        return "ok"
    except Exception:
        return "error"
```

Replace `<service-name>` with the literal service name:
- `agent-service` in agent-service
- `lardi-connector` in lardi-connector
- `auth-worker` in auth-worker

---

### File: `api-gateway/app/api/health.py` — differs from others (3 checks)

```python
"""
health.py — GET /health endpoint для api-gateway.

Перевіряє Redis, Postgres та agent-service. Повертає 200/503.
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine

log = structlog.get_logger()

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    """Перевірка стану api-gateway та трьох залежностей.

    Checks:
        - Redis: PING
        - Postgres: SELECT 1 (через async engine)
        - agent-service: GET /health (HTTP probe з timeout 3s)

    Returns:
        200 якщо всі залежності доступні, 503 якщо хоча б одна недоступна.
    """
    redis_status = await _check_redis(request.app.state.redis)
    postgres_status = await _check_postgres()
    agent_status = await _check_agent_service(settings.agent_service_url)

    dependencies = {
        "redis": redis_status,
        "postgres": postgres_status,
        "agent-service": agent_status,
    }
    all_ok = all(v == "ok" for v in dependencies.values())
    status = "healthy" if all_ok else "unhealthy"
    http_code = 200 if all_ok else 503

    if not all_ok:
        log.warning("health_check_degraded", service="api-gateway", dependencies=dependencies)

    return JSONResponse(
        status_code=http_code,
        content={"status": status, "service": "api-gateway", "dependencies": dependencies},
    )


async def _check_redis(client) -> str:
    """Перевіряє доступність Redis через PING."""
    try:
        await client.ping()
        return "ok"
    except Exception:
        return "error"


async def _check_postgres() -> str:
    """Перевіряє доступність Postgres через SELECT 1 (engine.connect(), не get_db())."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "error"


async def _check_agent_service(base_url: str) -> str:
    """Перевіряє доступність agent-service через HTTP GET /health з timeout 3s."""
    import httpx  # noqa: PLC0415 — локальний імпорт для уникнення циклічних залежностей

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{base_url}/health", timeout=3.0)
            return "ok" if r.status_code == 200 else "error"
    except Exception:
        return "error"
```

**Why `engine.connect()` and NOT `Depends(get_db)`:**
- `get_db()` commits/rollbacks the session and is designed for business operations
- For a health check we only need a lightweight connection probe
- `engine.connect()` bypasses the session layer and is correct for infrastructure checks
- `engine` is already initialized in lifespan (Story 1.2) — no additional setup needed

---

### File: `docker-compose.yml` — healthcheck update for 4 Python services

Replace TCP socket check with HTTP `/health` using Python's `urllib.request` (always available in `python:3.12-slim`, no external tools needed):

```yaml
# auth-worker (port 8003):
healthcheck:
  test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8003/health')\""]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 120s  # ← keep this (Chrome startup time, used in Epic 2)

# lardi-connector (port 8002):
healthcheck:
  test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8002/health')\""]
  interval: 15s
  timeout: 5s
  retries: 3
  start_period: 30s

# agent-service (port 8001):
healthcheck:
  test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8001/health')\""]
  interval: 15s
  timeout: 5s
  retries: 3
  start_period: 30s

# api-gateway (port 8000):
healthcheck:
  test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\""]
  interval: 15s
  timeout: 5s
  retries: 3
  start_period: 30s
```

**Why urllib and NOT wget:** `python:3.12-slim` does not guarantee wget. Python's stdlib `urllib.request` is always available.
**Why NOT curl:** Same reason — not guaranteed in slim images.
**urlopen() raises exception on non-200** — Docker interprets non-zero exit as unhealthy. This is correct.

---

### Test Pattern for Health Endpoints

Use `unittest.mock.patch` to mock `redis.asyncio.from_url` before creating the test client. This ensures `app.state.redis` gets a mock instead of a real client during tests.

```python
# tests/test_health.py (same pattern for all 4 services)
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

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
    """Мок Redis клієнта — PING кидає exception (симулює недоступний Redis)."""
    mock = AsyncMock()
    mock.ping = AsyncMock(side_effect=Exception("Connection refused"))
    mock.aclose = AsyncMock()
    return mock


@pytest.fixture
async def client_ok(mock_redis_ok):
    """Тест клієнт з доступним Redis."""
    with patch("redis.asyncio.from_url", return_value=mock_redis_ok):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac


@pytest.fixture
async def client_redis_down(mock_redis_down):
    """Тест клієнт з недоступним Redis."""
    with patch("redis.asyncio.from_url", return_value=mock_redis_down):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            yield ac


async def test_health_returns_200_when_healthy(client_ok):
    response = await client_ok.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["dependencies"]["redis"] == "ok"


async def test_health_returns_503_when_redis_down(client_redis_down):
    response = await client_redis_down.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["dependencies"]["redis"] == "error"


async def test_health_response_has_service_name(client_ok):
    response = await client_ok.get("/health")
    data = response.json()
    assert "service" in data
    assert data["service"] != ""  # перевірити, що service name не пустий
```

**CRITICAL for api-gateway tests:** also need to mock `_check_postgres` and `_check_agent_service`:
```python
# In api-gateway/tests/test_health.py — additional patches
with patch("app.api.health._check_postgres", return_value="ok"), \
     patch("app.api.health._check_agent_service", return_value="ok"), \
     patch("redis.asyncio.from_url", return_value=mock_redis_ok):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
```

---

### Previous Story Intelligence (Story 1.2)

**Patterns established (follow exactly):**
- `from __future__ import annotations` at top of every file
- `TYPE_CHECKING` imports for forward references (not needed in health.py, but be aware)
- `structlog.get_logger()` for logging — NOT stdlib `logging`
- All functions `async def` — NO sync code in FastAPI handlers
- No business logic in routers — health.py is an exception (checks are simple enough to stay in health.py, no separate service layer needed)
- `ruff check .` must pass with 0 errors — watch for UP042, UP017, F821, I001

**Debug learnings from Story 1.2 to avoid:**
- DO NOT use Python `try/except` to recover from database/Redis failures at the SQL/protocol level — they poison the underlying connection. Use individual `try/except` per check, catch broadly, return `"error"` string.
- Ruff may flag `import httpx` inside function body as `PLC0415` — suppress with `# noqa: PLC0415` if needed, or move to module level.

---

### Project Structure Notes

**Files to create (NEW):**
- `api-gateway/app/api/health.py`
- `agent-service/app/api/health.py`
- `lardi-connector/app/api/health.py`
- `auth-worker/app/api/health.py`
- `api-gateway/tests/test_health.py`
- `agent-service/tests/test_health.py`
- `lardi-connector/tests/test_health.py`
- `auth-worker/tests/test_health.py`

**Files to update (MODIFY):**
- `api-gateway/app/main.py` — Redis lifespan + include_router + keep engine.dispose()
- `agent-service/app/main.py` — Redis lifespan + include_router
- `lardi-connector/app/main.py` — Redis lifespan + include_router
- `auth-worker/app/main.py` — Redis lifespan + include_router
- `docker-compose.yml` — 4 healthcheck blocks (TCP → HTTP)

**DO NOT TOUCH:**
- `api-gateway/app/main.py` existing imports (engine from Story 1.2)
- `docker-compose.yml` `depends_on` chains — only healthcheck blocks change
- `docker-compose.yml` `start_period: 120s` on auth-worker — keep it (Epic 2 needs it)
- `requirements.txt` for any service — `redis[asyncio]` and `httpx` are already present in all 4 services

**app/api/__init__.py** — already exists and is empty in all 4 services. Do NOT add imports there.

---

### Architecture Compliance Checklist

1. `async def` for all endpoint functions ✓
2. Redis client via `request.app.state.redis` (not module-level global) ✓
3. No `os.environ` — all config via `settings` ✓
4. `structlog` for logging — log warning when degraded ✓
5. Error response format: `{"status": "unhealthy", "service": "...", "dependencies": {...}}` ✓
6. Endpoint returns `JSONResponse` (not dict) — needed to set `status_code=503` ✓
7. `GET /health` — no `/api/v1/` prefix (health endpoints are infrastructure, not API) ✓
8. `ruff check .` passes in all 4 services ✓

---

### References

- [Source: epics.md#Story 1.3] — Acceptance Criteria (verbatim)
- [Source: architecture.md#Рішення 12: Health Check Format] — exact JSON response schema
- [Source: architecture.md#Рішення 13: Docker Compose Health Check Chain] — depends_on ordering
- [Source: architecture.md#Рішення 15: Docker Compose Health Check Chain] — ARCH15
- [Source: architecture.md#Implementation Patterns] — async rules, structlog, config patterns
- [Source: architecture.md#Complete Project Directory Structure] — `app/api/health.py` path
- [Source: 1-2-database-schema-and-alembic-migration.md#Dev Agent Record] — ruff F821/UP037 patterns, `from __future__ import annotations`

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- `AsyncClient(app=app)` removed in httpx >= 0.20 → fix: `ASGITransport(app=app)`
- `ASGITransport` не запускає ASGI lifespan → `app.state.redis` не встановлювалось → fix: встановлювати `app.state.redis` напряму в тест-фікситах
- Видалено `patch("redis.asyncio.from_url")` з фікситів (зайве без lifespan)

### Completion Notes List

- 15 health тестів (5 api-gateway + 4 agent-service + 3 lardi-connector + 3 auth-worker) — всі PASSED
- `curl http://localhost:8000/health` → 200 `{"status":"healthy","service":"api-gateway","dependencies":{"redis":"ok","postgres":"ok","agent-service":"ok"}}`
- Всі 4 Python сервіси `(healthy)` у docker compose ps
- `conftest.py` у всіх 4 сервісах оновлено на `ASGITransport`

### File List

- `api-gateway/app/main.py` — оновлено (Redis lifespan + health router)
- `agent-service/app/main.py` — оновлено
- `lardi-connector/app/main.py` — оновлено
- `auth-worker/app/main.py` — оновлено
- `api-gateway/app/api/health.py` — NEW (Redis + Postgres + agent-service checks)
- `agent-service/app/api/health.py` — NEW (Redis check)
- `lardi-connector/app/api/health.py` — NEW (Redis check)
- `auth-worker/app/api/health.py` — NEW (Redis check)
- `docker-compose.yml` — оновлено (4 HTTP healthchecks)
- `api-gateway/tests/test_health.py` — NEW (5 тестів)
- `agent-service/tests/test_health.py` — NEW (4 тести)
- `lardi-connector/tests/test_health.py` — NEW (3 тести)
- `auth-worker/tests/test_health.py` — NEW (3 тести)
- `api-gateway/tests/conftest.py` — оновлено (ASGITransport)
- `agent-service/tests/conftest.py` — оновлено
- `lardi-connector/tests/conftest.py` — оновлено
- `auth-worker/tests/conftest.py` — оновлено
