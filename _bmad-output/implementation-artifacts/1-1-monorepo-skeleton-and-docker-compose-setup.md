# Story 1.1: Monorepo Skeleton & Docker Compose Setup

Status: done

## Story

As a developer,
I want a complete monorepo structure with all services wired into Docker Compose,
so that I can boot the entire system with a single `make up` command and have a foundation for all subsequent development.

## Acceptance Criteria

**AC1:**
Given the repository is cloned and `.env` is populated from `.env.example`
When `make up` is run
Then all 6 containers start: `api-gateway`, `agent-service`, `lardi-connector`, `auth-worker`, `redis`, `postgres`
And each Python service has: `Dockerfile`, `requirements.txt`, `pytest.ini` (asyncio_mode=auto), `app/main.py` (FastAPI skeleton with lifespan), `app/core/config.py` (pydantic-settings BaseSettings)

**AC2:**
Given the monorepo root
When inspecting the file structure
Then `docker-compose.yml` defines all 6 services with correct ports (8000/8001/8002/8003/6379/5432) and health check dependencies per ARCH15
And `docker-compose.override.yml` adds volume mounts for hot reload
And `.env.example` documents all required ENV variables with comments
And `Makefile` supports: `make up`, `make down`, `make logs`, `make test`, `make migrate`, `make lint`, `make shell s={service}`
And `ruff.toml` is present at monorepo root for shared linting/formatting

## Tasks / Subtasks

- [x] Task 1: Create monorepo root files (AC: #2)
  - [x] `docker-compose.yml` — 6 services, correct ports, health chain per ARCH15
  - [x] `docker-compose.override.yml` — volume mounts for hot reload
  - [x] `.env.example` — all ENV vars per architecture ENV reference
  - [x] `.gitignore` — include `.env`, `__pycache__`, `*.pyc`, `.venv`, `node_modules`
  - [x] `Makefile` — all 7 required commands
  - [x] `ruff.toml` — shared linter/formatter config (line-length=88, target py312)
  - [x] `docs/` directory (copy `lardi_trans_api_reference.md` if present, else create placeholder)

- [x] Task 2: Create api-gateway service skeleton (AC: #1)
  - [x] `api-gateway/Dockerfile` — `python:3.12-slim`
  - [x] `api-gateway/requirements.txt` — pinned versions (see Dev Notes)
  - [x] `api-gateway/pytest.ini` — `asyncio_mode = auto`
  - [x] `api-gateway/app/__init__.py`
  - [x] `api-gateway/app/main.py` — FastAPI skeleton with `@asynccontextmanager lifespan`
  - [x] `api-gateway/app/core/__init__.py`
  - [x] `api-gateway/app/core/config.py` — `Settings(BaseSettings)` with all api-gateway ENVs
  - [x] `api-gateway/app/core/errors.py` — `ErrorCode` enum stub + global exception handler
  - [x] Stub `__init__.py` in: `app/api/`, `app/db/`, `app/db/models/`, `app/schemas/`, `app/services/`
  - [x] `api-gateway/alembic/` directory stub (env.py + alembic.ini filled in Story 1.2)
  - [x] `api-gateway/tests/__init__.py`, `tests/conftest.py` stub

- [x] Task 3: Create agent-service service skeleton (AC: #1)
  - [x] `agent-service/Dockerfile` — `python:3.12-slim`
  - [x] `agent-service/requirements.txt` — pinned versions
  - [x] `agent-service/pytest.ini`
  - [x] `agent-service/app/main.py` — FastAPI skeleton with lifespan
  - [x] `agent-service/app/core/config.py` — Settings with agent-service ENVs
  - [x] `agent-service/app/core/errors.py` — stub
  - [x] Stub `__init__.py` in: `app/api/`, `app/schemas/`, `app/services/`, `app/tools/`, `app/graph/`, `app/prompts/`
  - [x] `agent-service/tests/conftest.py` stub

- [x] Task 4: Create lardi-connector service skeleton (AC: #1)
  - [x] `lardi-connector/Dockerfile` — `python:3.12-slim`
  - [x] `lardi-connector/requirements.txt` — pinned versions
  - [x] `lardi-connector/pytest.ini`
  - [x] `lardi-connector/app/main.py` — FastAPI skeleton with lifespan
  - [x] `lardi-connector/app/core/config.py` — Settings with lardi-connector ENVs
  - [x] `lardi-connector/app/core/errors.py` — stub
  - [x] Stub `__init__.py` in: `app/api/`, `app/schemas/`, `app/services/`
  - [x] `lardi-connector/tests/conftest.py` stub

- [x] Task 5: Create auth-worker service skeleton (AC: #1)
  - [x] `auth-worker/Dockerfile` — `python:3.12-slim` + Chromium deps (see Dev Notes)
  - [x] `auth-worker/requirements.txt` — pinned versions including `undetected-chromedriver`
  - [x] `auth-worker/pytest.ini`
  - [x] `auth-worker/app/main.py` — FastAPI skeleton with lifespan
  - [x] `auth-worker/app/core/config.py` — Settings with auth-worker ENVs
  - [x] `auth-worker/app/core/errors.py` — stub
  - [x] Stub `__init__.py` in: `app/api/`, `app/browser/`, `app/scheduler/`
  - [x] `auth-worker/tests/conftest.py` stub

- [x] Task 6: Verify system boots (AC: #1)
  - [x] Run `make up` — all 6 containers reach `healthy` or `running` status
  - [x] Confirm `GET http://localhost:8000/` or any endpoint returns (even 404 is fine at this stage — service is alive)
  - [x] Confirm `docker compose ps` shows all containers Up

## Dev Notes

### Scope Boundary — What Belongs to THIS Story

**IN SCOPE (Story 1.1):**
- Folder structure, empty `__init__.py` files, skeleton `main.py`/`config.py`
- Dockerfiles, requirements.txt, pytest.ini
- docker-compose.yml + override, .env.example, Makefile, ruff.toml

**OUT OF SCOPE (deferred):**
- `/health` endpoints → Story 1.3
- DB models, Alembic migration → Story 1.2
- Redis/Postgres connection pools in lifespan → Story 1.2/1.3
- Any actual API routes or business logic → Epic 2–4

The `app/main.py` in each service should have a lifespan stub and `app = FastAPI(...)` — nothing else.

---

### Exact Directory Tree to Create

```
aetherion-2.0/                              ← monorepo root (current working directory)
├── .env.example
├── .gitignore
├── docker-compose.yml
├── docker-compose.override.yml
├── Makefile
├── ruff.toml
├── docs/
│   └── lardi_trans_api_reference.md        ← copy if exists, create empty placeholder otherwise
│
├── api-gateway/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── api/
│   │   │   └── __init__.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   └── errors.py
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   └── models/
│   │   │       └── __init__.py
│   │   ├── schemas/
│   │   │   └── __init__.py
│   │   └── services/
│   │       └── __init__.py
│   ├── alembic/
│   │   └── versions/
│   │       └── .gitkeep
│   └── tests/
│       ├── __init__.py
│       └── conftest.py
│
├── agent-service/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── api/
│   │   │   └── __init__.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   └── errors.py
│   │   ├── graph/
│   │   │   └── __init__.py
│   │   ├── tools/
│   │   │   └── __init__.py
│   │   ├── prompts/
│   │   │   └── __init__.py
│   │   ├── schemas/
│   │   │   └── __init__.py
│   │   └── services/
│   │       └── __init__.py
│   └── tests/
│       ├── __init__.py
│       └── conftest.py
│
├── lardi-connector/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── api/
│   │   │   └── __init__.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   └── errors.py
│   │   ├── schemas/
│   │   │   └── __init__.py
│   │   └── services/
│   │       └── __init__.py
│   └── tests/
│       ├── __init__.py
│       └── conftest.py
│
└── auth-worker/
    ├── Dockerfile
    ├── requirements.txt
    ├── pytest.ini
    ├── app/
    │   ├── __init__.py
    │   ├── main.py
    │   ├── api/
    │   │   └── __init__.py
    │   ├── core/
    │   │   ├── __init__.py
    │   │   ├── config.py
    │   │   └── errors.py
    │   ├── browser/
    │   │   └── __init__.py
    │   └── scheduler/
    │       └── __init__.py
    └── tests/
        ├── __init__.py
        └── conftest.py
```

---

### Dockerfile Templates

**Standard services (api-gateway, agent-service, lardi-connector):**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
Change `--port` to match each service: 8000/8001/8002.

**auth-worker Dockerfile** — needs Chromium + system deps (~1.2GB image, memory limit in docker-compose):
```dockerfile
FROM python:3.12-slim

# Chromium and undetected-chromedriver dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libxrender1 \
    libxtst6 \
    libxi6 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libatk1.0-0 \
    libcairo-gobject2 \
    libgtk-3-0 \
    libdrm2 \
    libgbm1 \
    libxshmfence1 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
```

---

### requirements.txt — Pinned Versions

**api-gateway/requirements.txt:**
```
fastapi==0.135.1
uvicorn[standard]==0.34.0
sqlalchemy[asyncio]==2.0.46
asyncpg==0.31.0
alembic==1.18.4
redis[asyncio]>=5.0.0,<6.0.0
pydantic-settings>=2.0.0,<3.0.0
structlog==25.5.0
pytest==8.3.5
pytest-asyncio==1.3.0
httpx>=0.27.0
```

**agent-service/requirements.txt:**
```
fastapi==0.135.1
uvicorn[standard]==0.34.0
langgraph==1.1.0
redis[asyncio]>=5.0.0,<6.0.0
pydantic-settings>=2.0.0,<3.0.0
structlog==25.5.0
httpx>=0.27.0
pytest==8.3.5
pytest-asyncio==1.3.0
```

**lardi-connector/requirements.txt:**
```
fastapi==0.135.1
uvicorn[standard]==0.34.0
redis[asyncio]>=5.0.0,<6.0.0
pydantic-settings>=2.0.0,<3.0.0
structlog==25.5.0
httpx>=0.27.0
pytest==8.3.5
pytest-asyncio==1.3.0
```

**auth-worker/requirements.txt:**
```
fastapi==0.135.1
uvicorn[standard]==0.34.0
redis[asyncio]>=5.0.0,<6.0.0
pydantic-settings>=2.0.0,<3.0.0
structlog==25.5.0
httpx>=0.27.0
undetected-chromedriver>=3.5.5
apscheduler>=3.10.0,<4.0.0
pytest==8.3.5
pytest-asyncio==1.3.0
```

---

### main.py Skeleton Pattern (ALL services — identical structure)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.core.config import settings  # noqa: F401 — imported for startup validation


@asynccontextmanager
async def lifespan(app: FastAPI):
    # TODO Story 1.2/1.3: initialize Redis pool, DB engine here
    yield
    # TODO Story 1.2/1.3: close connections here


app = FastAPI(
    title="<service-name>",  # e.g. "Aetherion API Gateway"
    version="0.1.0",
    lifespan=lifespan,
)
```

**CRITICAL:** Use `@asynccontextmanager lifespan` pattern — do NOT use deprecated `@app.on_event("startup")`.

---

### core/config.py Pattern (pydantic-settings)

**api-gateway/app/core/config.py:**
```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_url: str = "postgresql+asyncpg://aetherion:aetherion@postgres:5432/aetherion"
    redis_url: str = "redis://redis:6379/0"
    agent_service_url: str = "http://agent-service:8001"
    admin_api_key: str = "changeme-replace-in-production"
    allowed_origins: str = "*"

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
```

**agent-service/app/core/config.py:**
```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    lardi_connector_url: str = "http://lardi-connector:8002"
    llm_api_key: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "openrouter/auto"

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
```

**lardi-connector/app/core/config.py:**
```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    lardi_base_url: str = "https://lardi-trans.com"
    lardi_http_timeout_seconds: int = 10
    lardi_request_min_interval_seconds: float = 1.0

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
```

**auth-worker/app/core/config.py:**
```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    lardi_login: str = ""
    lardi_password: str = ""
    admin_api_key: str = "changeme-replace-in-production"
    ltsid_ttl_hours: int = 23
    fuel_cache_ttl_seconds: int = 3600
    ltsid_refresh_lock_ttl_seconds: int = 120
    chrome_timeout_seconds: int = 60
    ltsid_refresh_wait_seconds: int = 90
    refresh_circuit_breaker_threshold: int = 3
    refresh_circuit_breaker_pause_minutes: int = 10
    fuel_price_url: str = ""
    fuel_price_http_timeout_seconds: int = 5

    model_config = {"env_file": ".env", "case_sensitive": False}


settings = Settings()
```

---

### core/errors.py Stub Pattern

```python
from enum import Enum


class ErrorCode(str, Enum):
    # Populated per-service in later stories
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    NOT_FOUND = "NOT_FOUND"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
```

Global exception handler will be added in Story 1.3 when health endpoint is implemented.

---

### pytest.ini (identical for all 4 services)

```ini
[pytest]
asyncio_mode = auto
```

**CRITICAL:** `asyncio_mode = auto` is MANDATORY with pytest-asyncio 1.x. Without it, ALL async tests fail silently or raise `PytestUnraisableExceptionWarning`. Do not use `asyncio_mode = strict` or omit this setting.

---

### ruff.toml (monorepo root)

```toml
line-length = 88
target-version = "py312"
exclude = [".venv", "__pycache__", "alembic/versions"]

[lint]
select = ["E", "F", "W", "I", "N", "UP"]
ignore = ["E501"]  # line length handled by formatter

[format]
quote-style = "double"
indent-style = "space"
```

---

### docker-compose.yml

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-aetherion}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-aetherion}
      POSTGRES_DB: ${POSTGRES_DB:-aetherion}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-aetherion}"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  auth-worker:
    build: ./auth-worker
    env_file: .env
    ports:
      - "8003:8003"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:8003/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s
    deploy:
      resources:
        limits:
          memory: 1536M

  lardi-connector:
    build: ./lardi-connector
    env_file: .env
    ports:
      - "8002:8002"
    depends_on:
      redis:
        condition: service_healthy
      auth-worker:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:8002/health || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 30s

  agent-service:
    build: ./agent-service
    env_file: .env
    ports:
      - "8001:8001"
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:8001/health || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 30s

  api-gateway:
    build: ./api-gateway
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      agent-service:
        condition: service_healthy
      lardi-connector:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "wget -qO- http://localhost:8000/health || exit 1"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 30s

volumes:
  postgres_data:
  redis_data:
```

**IMPORTANT:** `wget` is available in `python:3.12-slim` images. If not, add `RUN apt-get update && apt-get install -y wget` to Dockerfiles. Alternatively use `curl` if preferred — but be consistent across all services.

**NOTE:** Health endpoint `/health` is NOT implemented yet in Story 1.1 — health checks will fail until Story 1.3. For Story 1.1 testing, use `condition: service_started` instead of `service_healthy` if needed, then revert to `service_healthy` after Story 1.3.

---

### docker-compose.override.yml

```yaml
version: "3.9"

services:
  api-gateway:
    volumes:
      - ./api-gateway:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    environment:
      ALLOWED_ORIGINS: "*"

  agent-service:
    volumes:
      - ./agent-service:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

  lardi-connector:
    volumes:
      - ./lardi-connector:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload

  auth-worker:
    volumes:
      - ./auth-worker:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```

---

### .env.example

```bash
# ================================================
# api-gateway
# ================================================
POSTGRES_URL=postgresql+asyncpg://aetherion:aetherion@postgres:5432/aetherion
REDIS_URL=redis://redis:6379/0
AGENT_SERVICE_URL=http://agent-service:8001
ADMIN_API_KEY=changeme-replace-in-production
ALLOWED_ORIGINS=*

# ================================================
# agent-service
# ================================================
LLM_API_KEY=<your-openrouter-api-key>
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=openrouter/auto
LARDI_CONNECTOR_URL=http://lardi-connector:8002
# REDIS_URL already defined above (shared)

# ================================================
# lardi-connector
# ================================================
LARDI_BASE_URL=https://lardi-trans.com
# REDIS_URL already defined above (shared)

# ================================================
# auth-worker
# ================================================
LARDI_LOGIN=<your-lardi-email>
LARDI_PASSWORD=<your-lardi-password>
LTSID_TTL_HOURS=23
FUEL_CACHE_TTL_SECONDS=3600
LTSID_REFRESH_LOCK_TTL_SECONDS=120
CHROME_TIMEOUT_SECONDS=60
LTSID_REFRESH_WAIT_SECONDS=90
REFRESH_CIRCUIT_BREAKER_THRESHOLD=3
REFRESH_CIRCUIT_BREAKER_PAUSE_MINUTES=10
FUEL_PRICE_URL=<url-to-fuel-price-source>
FUEL_PRICE_HTTP_TIMEOUT_SECONDS=5
# ADMIN_API_KEY already defined above (shared)

# ================================================
# postgres (docker-compose service)
# ================================================
POSTGRES_USER=aetherion
POSTGRES_PASSWORD=aetherion
POSTGRES_DB=aetherion
```

---

### Makefile

```makefile
.PHONY: up down logs test migrate lint shell seed-cities

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose exec api-gateway pytest tests/ -v
	docker compose exec agent-service pytest tests/ -v
	docker compose exec lardi-connector pytest tests/ -v
	docker compose exec auth-worker pytest tests/ -v

migrate:
	docker compose exec api-gateway alembic upgrade head

lint:
	ruff check . && ruff format --check .

shell:
	docker compose exec $(s) bash

seed-cities:
	docker compose exec api-gateway python scripts/import_cities_v1.py
```

**Note:** `seed-cities` target references `scripts/import_cities_v1.py` which will be created in Story 1.2. Create the Makefile target now with a placeholder — the script itself is Story 1.2 scope.

---

### Architecture Compliance Rules (MANDATORY)

1. **Async everywhere** — all `app/main.py` endpoint functions must be `async def`. The lifespan must use `@asynccontextmanager`.
2. **pydantic-settings only** — `settings = Settings()` at module level in `config.py`. Never `os.environ["KEY"]` directly anywhere.
3. **Lifespan, not on_event** — `FastAPI(lifespan=lifespan)` pattern. `@app.on_event("startup")` is deprecated and must NOT be used.
4. **pytest-asyncio 1.x** — `asyncio_mode = auto` in `pytest.ini` is non-negotiable. This is a breaking change from 0.x API.
5. **Service port mapping** — api-gateway=8000, agent-service=8001, lardi-connector=8002, auth-worker=8003. Do not swap.
6. **Docker Compose health chain** — postgres/redis → auth-worker (start_period 120s) → lardi-connector + agent-service → api-gateway. Do not change ordering.
7. **auth-worker memory limit** — 1536M (1.5GB) for Chromium. Do not lower.
8. **ruff.toml at root** — one file for entire monorepo. Each service does NOT have its own ruff.toml.
9. **No business logic in main.py** — skeleton only. Routes added in later stories.
10. **Independent requirements.txt per service** — no shared requirements file.

### Project Structure Notes

- **LangGraph 1.1.0 note:** Not installed or used in Story 1.1 — just listed in `agent-service/requirements.txt`. LangGraph graph compilation happens in Epic 4.
- **alembic/ in api-gateway** — create the directory and `versions/.gitkeep`. `alembic.ini` and `env.py` are created in Story 1.2.
- **`app/core/auth.py`** in api-gateway — NOT required for Story 1.1. Added in Story 4.4 (JWT stub).
- **`tests/conftest.py`** stubs — empty for now. Fixtures added when writing actual tests.
- **`docs/` directory** — if `docs/lardi_trans_api_reference.md` exists in the project already, preserve it. Otherwise create `docs/.gitkeep`.

### References

- [Source: architecture.md#Monorepo Layout] — folder structure, service ports, universal service structure
- [Source: architecture.md#Docker Compose Service Configuration] — base images, port mapping
- [Source: architecture.md#Docker Compose Health Check Chain] — ARCH15: health check ordering
- [Source: architecture.md#Technology Stack] — ARCH2: all pinned versions
- [Source: architecture.md#Development Workflow] — ARCH14: Makefile commands, override.yml
- [Source: architecture.md#Environment Variables Reference] — complete .env.example content
- [Source: architecture.md#Enforcement Guidelines] — what AI agents MUST and MUST NOT do
- [Source: epics.md#Story 1.1] — acceptance criteria (verbatim)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — no unexpected errors during implementation.

### Completion Notes List

- All 4 service skeletons created with correct FastAPI lifespan pattern, pydantic-settings BaseSettings, and pytest.ini `asyncio_mode = auto`.
- ruff auto-fixed 12 issues: `UP042` (switched `class ErrorCode(str, Enum)` → `class ErrorCode(StrEnum)`) across all 4 services' errors.py; `I001` (sorted imports in conftest.py files).
- 12/12 smoke tests passing (3 per service × 4 services).
- `ruff check .` — 0 errors after auto-fix.
- Task 6 verified: all 10 containers (postgres, redis, auth-worker, lardi-connector, agent-service, api-gateway + 4 images) reached Healthy/Started state. auth-worker build time ~3.5s (image already cached).
- Healthcheck fix: replaced `wget /health` with Python TCP socket connect (`connect_ex`) for all 4 services — works without a `/health` endpoint. Story 1.3 will replace with proper HTTP health checks.
- `docs/lardi_trans_api_reference.md` not present in repo — created `docs/.gitkeep` placeholder per Dev Notes instructions.
- `api-gateway/alembic/versions/.gitkeep` created — alembic.ini and env.py deferred to Story 1.2.

### File List

- `.env.example`
- `.gitignore`
- `docker-compose.yml`
- `docker-compose.override.yml`
- `Makefile`
- `ruff.toml`
- `docs/.gitkeep`
- `api-gateway/Dockerfile`
- `api-gateway/requirements.txt`
- `api-gateway/pytest.ini`
- `api-gateway/app/__init__.py`
- `api-gateway/app/main.py`
- `api-gateway/app/api/__init__.py`
- `api-gateway/app/core/__init__.py`
- `api-gateway/app/core/config.py`
- `api-gateway/app/core/errors.py`
- `api-gateway/app/db/__init__.py`
- `api-gateway/app/db/models/__init__.py`
- `api-gateway/app/schemas/__init__.py`
- `api-gateway/app/services/__init__.py`
- `api-gateway/alembic/versions/.gitkeep`
- `api-gateway/tests/__init__.py`
- `api-gateway/tests/conftest.py`
- `api-gateway/tests/test_app_startup.py`
- `agent-service/Dockerfile`
- `agent-service/requirements.txt`
- `agent-service/pytest.ini`
- `agent-service/app/__init__.py`
- `agent-service/app/main.py`
- `agent-service/app/api/__init__.py`
- `agent-service/app/core/__init__.py`
- `agent-service/app/core/config.py`
- `agent-service/app/core/errors.py`
- `agent-service/app/graph/__init__.py`
- `agent-service/app/tools/__init__.py`
- `agent-service/app/prompts/__init__.py`
- `agent-service/app/schemas/__init__.py`
- `agent-service/app/services/__init__.py`
- `agent-service/tests/__init__.py`
- `agent-service/tests/conftest.py`
- `agent-service/tests/test_app_startup.py`
- `lardi-connector/Dockerfile`
- `lardi-connector/requirements.txt`
- `lardi-connector/pytest.ini`
- `lardi-connector/app/__init__.py`
- `lardi-connector/app/main.py`
- `lardi-connector/app/api/__init__.py`
- `lardi-connector/app/core/__init__.py`
- `lardi-connector/app/core/config.py`
- `lardi-connector/app/core/errors.py`
- `lardi-connector/app/schemas/__init__.py`
- `lardi-connector/app/services/__init__.py`
- `lardi-connector/tests/__init__.py`
- `lardi-connector/tests/conftest.py`
- `lardi-connector/tests/test_app_startup.py`
- `auth-worker/Dockerfile`
- `auth-worker/requirements.txt`
- `auth-worker/pytest.ini`
- `auth-worker/app/__init__.py`
- `auth-worker/app/main.py`
- `auth-worker/app/api/__init__.py`
- `auth-worker/app/core/__init__.py`
- `auth-worker/app/core/config.py`
- `auth-worker/app/core/errors.py`
- `auth-worker/app/browser/__init__.py`
- `auth-worker/app/scheduler/__init__.py`
- `auth-worker/tests/__init__.py`
- `auth-worker/tests/conftest.py`
- `auth-worker/tests/test_app_startup.py`
