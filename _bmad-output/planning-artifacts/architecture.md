---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-03-17'
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/brainstorming/brainstorming-session-2026-03-15-0001.md'
  - 'docs/lardi_trans_api_reference.md'
workflowType: 'architecture'
project_name: 'Aetherion 2.0'
user_name: 'Artur'
date: '2026-03-17'
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements — 30 FRs у 7 категоріях:**

| Категорія | FRs | Архітектурна імплікація |
|---|---|---|
| Cargo Search | FR1–7 | NLP pipeline → intent extraction → geo resolution → Lardi API |
| Profitability Analysis | FR8–11 | Розрахунковий шар у agent-service; формула: distance × fuel × price |
| Cargo Details & Contacts | FR12–13 | Двокроковий запит до Lardi (search → detail endpoint) |
| Agent Interaction & Streaming | FR14–16 | SSE або WebSocket для стрімінгу; request lock на рівні сесії |
| Session & Auth Management | FR17–20 | Окремий `auth-worker` сервіс; Redis як єдиний session store |
| Fuel Price Management | FR21–23 | Background cron job; Redis key з TTL; fallback логіка |
| System Ops & Health | FR24–27 | `/health` endpoint агрегує статус усіх залежностей; Redis queue |
| Data Persistence | FR28–30 | Postgres: users, workspaces, chats, messages; Redis: session + cache |

**Non-Functional Requirements — архітектурні вимоги:**

- **Performance:** ≤15с повна відповідь агента; ≤3с перший streaming chunk → потребує async архітектури скрізь
- **Reliability:** auto-recovery від 401 без втрати запиту → retry logic в `lardi-connector`; LLM timeout ≤30с
- **Security:** LTSID ніколи не в LLM контексті → hard boundary між `auth-worker`/`lardi-connector` і `agent-service`; prompt injection defense (tool scope + data wrapping + system prompt)
- **Integration:** всі зовнішні виклики мають explicit timeout; Docker Compose health check ordering

**Scale & Complexity:**
- Складність: Medium
- Primary domain: Backend microservices + AI agent
- MVP: single-tenant, 1 Lardi акаунт, 1–2 користувачі
- Сервіси: 6–7 контейнерів у Docker Compose

### Technical Constraints & Dependencies

- **Cloudflare bypass** — LTSID отримується виключно через headless Chrome (`undetected-chromedriver`); ізольовано в `auth-worker`
- **Lardi API quirks** — integer-only filter IDs; result cap 500; distance в метрах; contacts тільки через detail endpoint
- **LLM via OpenRouter** — зовнішній сервіс; потрібен timeout + graceful degradation
- **Redis** — єдине джерело правди для: LTSID сесії (TTL), global Lardi request queue, fuel price cache, message broker між сервісами
- **Postgres** — multi-tenant-ready schema від першого дня (`workspace_id` скрізь)
- **Streaming** — API gateway повинен підтримувати SSE або WebSocket для streaming chunks від agent-service

### Cross-Cutting Concerns Identified

1. **Session Management** — `auth-worker` і `lardi-connector` розділяють Redis; будь-який сервіс що викликає Lardi залежить від валідного LTSID
2. **Streaming Architecture** — `api-gateway` → `agent-service` → client потребує єдиного підходу (SSE/WebSocket) скрізь
3. **Error Handling & Graceful Degradation** — кожен сервіс явно обробляє свої помилки; silent failures заборонені
4. **Rate Limiting & Queuing** — глобальна Redis Queue гарантує ≤1 запиту до Lardi одночасно; прозора для `agent-service`
5. **Configuration Management** — ENV-based конфігурація; Docker Compose `.env` як єдине джерело секретів
6. **Observability** — структуроване логування з контекстом у всіх сервісах; `/health` агрегує стан залежностей

## Starter Template Evaluation

### Primary Technology Domain

Python backend microservices з AI agent orchestration. MVP не має фронтенду — "starter template" — це **еталонна структура папок** кожного мікросервісу, узгоджена між усіма сервісами проекту.

**Reference:** адаптовано з [benavlabs/FastAPI-boilerplate](https://github.com/benavlabs/FastAPI-boilerplate) — production-ready boilerplate з FastAPI + SQLAlchemy 2.0 async + PostgreSQL + Redis.

### Technology Stack (верифіковані версії)

| Інструмент | Версія | Призначення |
|---|---|---|
| Python | 3.12+ | Runtime для всіх сервісів |
| FastAPI | 0.135.1 | HTTP framework для api-gateway, agent-service, lardi-connector, auth-worker |
| SQLAlchemy (async) | 2.0.46 | ORM для PostgreSQL з підтримкою AsyncSession |
| asyncpg | 0.31.0 | Async PostgreSQL driver (3–5x швидший за sync) |
| Alembic | 1.18.4 | Database migrations з async підтримкою |
| LangGraph | 1.1.0 | Agent orchestration в agent-service (GA з жовтня 2025; v2 streaming API) |
| redis-py | 5.x (async) | Redis client для всіх сервісів |
| pydantic-settings | 2.x | Типізована ENV-конфігурація через BaseSettings |
| Ruff | 0.15.3 | Linter + formatter (замінює Black + Flake8 + isort; написаний на Rust, 100x швидший) |
| structlog | 25.5.0 | Structured JSON logging з async context (contextvars) |
| pytest | 8.x | Testing framework |
| pytest-asyncio | 1.3.0 | Підтримка async тестів (1.x API — стартуємо відразу з нею) |

### Starter Options Considered

#### ORM: Порівняльна матриця

| Критерій | SQLAlchemy 2.x async | SQLModel | Raw asyncpg |
|---|---|---|---|
| Гнучкість запитів | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Мінімум boilerplate | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| Alembic migrations | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ❌ ручний |
| Документація / спільнота | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| Multi-tenant підтримка | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **РАЗОМ** | **23/25** | **18/25** | **15/25** |

**Обрано: SQLAlchemy 2.0.46 async + asyncpg.** SQLModel обмежує гнучкість для складних queries і relationships. Raw asyncpg потребує ручного mapping рядків БД в Python об'єкти.

#### Inter-service Communication: Hybrid рішення (ADR)

| Пара сервісів | Протокол | Обґрунтування |
|---|---|---|
| api-gateway → agent-service | HTTP + SSE | Request/response контракт; SSE для streaming chunks |
| agent-service → lardi-connector | HTTP | Sync запит з явним timeout; легко тестувати |
| agent-service → auth-worker | Redis | LTSID — shared state, не request/response |
| auth-worker → всі | Redis | LTSID запис при оновленні; TTL-based expiry |

Redis — для shared state. HTTP — для control flow між сервісами.

### Selected Foundation: Custom Monorepo Structure

**Монорепо стратегія: Flat (Варіант C)**

Кожен сервіс — повністю self-contained (власний Dockerfile, requirements.txt, tests). Shared types дублюються там де потрібні. Для MVP з 4-5 спільних типів — прийнятно; надає повну незалежність між сервісами.

**Initialization: Ручне створення структури папок**

```bash
# Корінь монорепо
mkdir -p aetherion-2.0/{api-gateway,agent-service,lardi-connector,auth-worker}/app/{api,core,db,schemas,services}
mkdir -p aetherion-2.0/{api-gateway,agent-service,lardi-connector,auth-worker}/tests
# agent-service додаткові директорії
mkdir -p aetherion-2.0/agent-service/app/{tools,graph,prompts}
# auth-worker додаткові директорії
mkdir -p aetherion-2.0/auth-worker/app/{browser,scheduler}
```

### Monorepo Layout

```
aetherion-2.0/                   # Корінь монорепо
├── api-gateway/                  # Єдина точка входу (PORT 8000)
├── agent-service/                # LangGraph + LLM orchestration (PORT 8001, internal)
├── lardi-connector/              # Lardi API adapter + queue (PORT 8002, internal)
├── auth-worker/                  # Cloudflare bypass + LTSID refresh (PORT 8003)
├── docker-compose.yml            # Оркестрація всіх сервісів
├── docker-compose.override.yml   # Dev overrides (volume mounts для hot reload)
├── .env.example                  # Шаблон всіх ENV змінних з коментарями
├── ruff.toml                     # Єдиний конфіг Ruff для всього монорепо
└── docs/                         # Lardi API reference та інша документація
```

### Universal Service Structure

Кожен Python мікросервіс слідує одній файловій структурі:

```
{service-name}/
├── app/
│   ├── api/           # FastAPI routers — HTTP endpoints та їх обробники
│   ├── core/          # Config (settings.py через pydantic-settings), константи
│   ├── db/            # SQLAlchemy models, async session factory, base class
│   ├── schemas/       # Pydantic моделі для request/response валідації
│   ├── services/      # Бізнес-логіка — orchestration layer між API і DB/external
│   └── main.py        # FastAPI app factory + @asynccontextmanager lifespan
├── tests/
│   ├── conftest.py    # pytest fixtures: test client, DB session, Redis mock
│   └── test_*.py      # Тести за модулями
├── Dockerfile
└── requirements.txt   # Зафіксовані версії (pip freeze після першого setup)
```

**agent-service — додаткові директорії:**

```
app/
├── tools/         # LangGraph tool definitions: search_cargo, get_details, calc_profit
├── graph/         # LangGraph graph: state schema, nodes, edges, compiled graph
└── prompts/       # System prompts (hardcoded рядки — не в БД, не через ENV)
```

**auth-worker — додаткові директорії:**

```
app/
├── browser/       # undetected-chromedriver: login flow, cookie extraction, session
└── scheduler/     # Background refresh task (asyncio task або APScheduler)
```

### Docker Compose Service Configuration

```
Сервіс           | Port  | Base Image                      | Примітка
-----------------+-------+---------------------------------+---------------------------
api-gateway      | 8000  | python:3.12-slim                | Публічний; health check
agent-service    | 8001  | python:3.12-slim                | Internal only
lardi-connector  | 8002  | python:3.12-slim                | Internal only
auth-worker      | 8003  | python:3.12-slim + Chromium     | ~1.2GB image; memory limit
redis            | 6379  | redis:7-alpine                  | Persistence via AOF
postgres         | 5432  | postgres:16-alpine              | Named volume для даних
```

### Architectural Decisions від вибору стеку

- **Async everywhere** — всі FastAPI ендпоінти `async def`; Redis і PostgreSQL клієнти — async. Синхронні виклики в async контексті заборонені.
- **Pydantic BaseSettings** — кожен сервіс читає ENV через типізований `Settings` клас (`pydantic-settings`), не `os.environ` напряму. Валідація при старті сервісу.
- **Lifespan events** — connection pool Redis та DB engine ініціалізуються через `@asynccontextmanager lifespan(app)` (сучасний підхід замість deprecated `@app.on_event`).
- **Independent requirements.txt** — кожен сервіс має власні залежності та незалежний Docker image. Версії зафіксовані через `pip freeze` після першого setup.
- **Shared ruff.toml** — єдиний конфіг linting/formatting для всього монорепо. Ruff замінює Black, Flake8 та isort одним інструментом.
- **pytest configuration** — `asyncio_mode = "auto"` в `pytest.ini` обов'язково (pytest-asyncio 1.x вимога). Без цього всі async тести падають з неочевидними помилками.
- **auth-worker Dockerfile** — відрізняється від інших: потребує Chromium та системних залежностей. Окрема build стратегія; memory limit в docker-compose вищий (~1.5GB).
- **LangGraph streaming** — використовується `version="v2"` streaming API (LangGraph 1.1.0). Дає типізовані `StreamPart` об'єкти → конвертуються в SSE events в `agent-service`.
- **Redis secondary cache** — `agent-service` тримає last known fuel price в пам'яті процесу як fallback якщо Redis недоступний. Redis — primary, in-memory — secondary.

**Примітка:** Перша implementation story = створення Docker Compose монорепо зі структурою папок, базовим `main.py` та `Dockerfile` для кожного сервісу.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (блокують імплементацію):**
- Multi-tenant schema підхід → row-level tenancy з `workspace_id`
- Redis key naming convention та TTL стратегія
- Inter-service communication протоколи
- Docker Compose health check ланцюг

**Important Decisions (формують архітектуру):**
- API versioning prefix `/api/v1/`
- Стандартний error response format
- LLM timeout стратегія (connection vs completion)
- LTSID proactive refresh механізм

**Deferred Decisions (Post-MVP):**
- CI/CD pipeline (GitHub Actions) — Phase 2
- Centralized log collection (Loki/Grafana) — Phase 2
- Redis Sentinel для HA — Phase 2

### Data Architecture

**Рішення 1: Multi-tenant Schema — Row-level Tenancy**
- **Обрано:** `workspace_id UUID NOT NULL` колонка в кожній таблиці; єдиний Postgres schema
- **Відхилено:** schema-per-tenant — зайвий overhead для MVP з одним workspace
- **Наслідок:** всі SQLAlchemy queries фільтруються по `workspace_id`; Alembic migration від дня 1

**Рішення 2: Redis Key Naming Convention**
```
aetherion:{service}:{entity}:{id}

# Конкретні ключі:
aetherion:auth:ltsid              # єдиний LTSID (один Lardi акаунт)
aetherion:auth:refresh:lock       # Redis lock під час refresh (SET NX EX)
aetherion:fuel:price:diesel       # fuel price cache
aetherion:queue:lardi             # global Lardi request queue (Redis List)
aetherion:session:{user_id}       # user session data
```

**Рішення 3: Redis TTL Значення**

| Key | TTL | ENV змінна | Обґрунтування |
|---|---|---|---|
| `aetherion:auth:ltsid` | 23 год | `LTSID_TTL_HOURS=23` | Конфігурується; proactive refresh за 1 год до закінчення |
| `aetherion:fuel:price:*` | 1 год | `FUEL_CACHE_TTL_SECONDS=3600` | Cron оновлює щогодини |
| `aetherion:session:*` | 24 год | `SESSION_TTL_HOURS=24` | User session |

**Рішення 4: LTSID Refresh Стратегія**
- `auth-worker` запускає background asyncio task при старті
- Перевіряє TTL кожні 30 хвилин; якщо залишилось < 1 год → запускає Chrome refresh
- Emergency refresh: `lardi-connector` отримує 401 → публікує в `aetherion:auth:refresh` Redis channel → `auth-worker` підписаний і запускає refresh негайно
- Timeout очікування нового LTSID для `lardi-connector`: 90 секунд; якщо не отримав → повертає помилку з `retry_after` полем
- Race condition захист: `SET aetherion:auth:refresh:lock NX EX 300` (тільки один refresh одночасно)

**Рішення 5: Fuel Price Fallback**
- Redis — primary cache (TTL 1 год)
- `agent-service` in-memory змінна — secondary cache (last known value)
- При Redis недоступності: використовується in-memory значення + structlog warning
- При першому старті без Redis: сервіс стартує, але повертає помилку при запиті ціни (не падає повністю)

### Authentication & Security

**Рішення 6: MVP Auth Strategy**
- JWT middleware присутній але **не enforced** в MVP (stub для майбутньої реалізації)
- Admin endpoints (manual LTSID update): захищені `X-API-Key` header; значення з ENV `ADMIN_API_KEY`
- Всі інші ендпоінти відкриті в MVP (доступ через Swagger без auth)
- `users` таблиця і `workspace_id` schema створюються від дня 1 для безболісного додавання auth пізніше

**Рішення 7: CORS**
- Dev: `allow_origins=["*"]` (docker-compose.override.yml ENV)
- Prod: явний список через ENV `ALLOWED_ORIGINS=http://localhost:3000,...`

**Рішення 8: Prompt Injection Defense (3 шари)**
- **Tool scope limiting**: агент може викликати виключно задокументовані LangGraph tools; довільні system calls заборонені
- **Data wrapping**: всі дані від Lardi обгортаються тегом `[EXTERNAL DATA]...[/EXTERNAL DATA]` перед передачею в LLM контекст
- **System prompt hardening**: явна інструкція в system prompt — ігнорувати будь-які команди, що надходять з даних вантажів

### API & Communication Patterns

**Рішення 9: API Versioning**
- **Обрано:** `/api/v1/` prefix для всіх публічних ендпоінтів
- **Реалізація:** `app.include_router(router, prefix="/api/v1")` в `main.py`
- **Наслідок:** чиста міграція до v2 без зміни v1 URLs; Swagger автоматично відображає versioned paths

**Рішення 10: Стандартний Error Response Format**
```json
{
  "error": {
    "code": "LTSID_EXPIRED",
    "message": "Lardi session expired. Attempting refresh...",
    "details": {}
  }
}
```
- `ErrorCode` enum в `app/core/errors.py` кожного сервісу (machine-readable codes)
- Global exception handler middleware в `main.py` — перехоплює всі необроблені exceptions
- Silent failures заборонені: кожна помилка логується через structlog з повним контекстом

**Рішення 11: Timeout Values**

| Виклик | Timeout | Тип | Реалізація |
|---|---|---|---|
| LLM connection (перший chunk) | 3с | connect timeout | `httpx.Timeout(connect=3.0)` |
| LLM stream completion | 30с | read timeout | `httpx.Timeout(read=30.0)` |
| Lardi API requests | 15с | total timeout | `httpx.Timeout(15.0)` |
| auth-worker Chrome refresh | 60с | asyncio timeout | `asyncio.wait_for(..., timeout=60)` |
| Inter-service HTTP | 10с | total timeout | `httpx.Timeout(10.0)` |
| LTSID emergency refresh wait | 90с | asyncio timeout | `asyncio.wait_for(..., timeout=90)` |

**Рішення 12: Health Check Format**
```json
GET /health  →  200 OK
{
  "status": "healthy",
  "service": "api-gateway",
  "dependencies": {
    "redis": "ok",
    "postgres": "ok",
    "agent_service": "ok"
  }
}
```
- `auth-worker` `/health` додатково перевіряє: `"ltsid": "valid"` (EXISTS в Redis + TTL > 0)
- HTTP 503 якщо будь-яка critical залежність недоступна

### Infrastructure & Deployment

**Рішення 13: Docker Compose Health Check Chain**
```
postgres   → healthcheck: pg_isready
redis      → healthcheck: redis-cli ping
               ↓
auth-worker → depends_on: postgres(healthy), redis(healthy)
              healthcheck: GET /health → ltsid valid
              start_period: 120s  (час на Chrome запуск і отримання LTSID)
               ↓
lardi-connector → depends_on: redis(healthy), auth-worker(healthy)
agent-service   → depends_on: redis(healthy), postgres(healthy)
               ↓
api-gateway → depends_on: agent-service(healthy), lardi-connector(healthy)
```

**Рішення 14: Development Workflow**
- `docker-compose.override.yml` — volume mounts для hot reload; debug ports
- `Makefile` в корені монорепо з командами:

```makefile
make up          # docker compose up -d
make down        # docker compose down
make logs        # docker compose logs -f
make test        # pytest для всіх сервісів
make migrate     # alembic upgrade head
make shell s=api-gateway  # docker compose exec {s} bash
make lint        # ruff check . && ruff format --check .
```

**Рішення 15: CI/CD**
- MVP: локальний Docker Compose; ніякого CI/CD
- Phase 2: GitHub Actions з `ruff check`, `pytest`, `docker build` на PR

### Decision Impact Analysis

**Implementation Sequence (порядок залежностей):**
1. Postgres schema (Alembic migration) — базова основа
2. Redis key structure + TTL config — shared state foundation
3. `auth-worker` з lifespan LTSID fetch — prerequisite для всього
4. `lardi-connector` з queue та 401 handling — prerequisite для agent
5. `agent-service` з LangGraph graph — core business logic
6. `api-gateway` з SSE proxy — фінальна інтеграція

**Cross-Component Dependencies:**
- `lardi-connector` залежить від `auth-worker` (LTSID в Redis)
- `agent-service` залежить від `lardi-connector` (HTTP) та Redis (fuel cache)
- `api-gateway` залежить від `agent-service` (SSE stream) та Postgres (chat persistence)
- Всі сервіси залежать від Redis (session, queue, cache) та Postgres (persistence)

## Implementation Patterns & Consistency Rules

### Critical Conflict Points Identified

7 категорій де AI агенти можуть зробити несумісні рішення без явних правил: naming, structure, API format, data format, communication, async patterns, error handling.

### Naming Patterns

**Database (SQLAlchemy / Postgres):**

| Елемент | Конвенція | Приклад |
|---|---|---|
| Таблиці | snake_case, множина | `users`, `workspaces`, `cargo_searches` |
| Колонки | snake_case | `workspace_id`, `created_at`, `ltsid_token` |
| Foreign keys | `{table_singular}_id` | `user_id`, `workspace_id`, `chat_id` |
| Indexes | `ix_{table}_{column}` | `ix_users_email`, `ix_messages_chat_id` |
| Primary key | `id UUID` | `id UUID PRIMARY KEY DEFAULT gen_random_uuid()` |

**API Endpoints (FastAPI routers):**

| Елемент | Конвенція | Приклад |
|---|---|---|
| Resources | snake_case, множина | `/api/v1/cargo_searches`, `/api/v1/workspaces` |
| Path params | snake_case | `/api/v1/chats/{chat_id}/messages` |
| Query params | snake_case | `?workspace_id=...&page_size=20` |
| HTTP GET list | множина resource | `GET /api/v1/cargo_searches` |
| HTTP GET one | `/{id}` suffix | `GET /api/v1/cargo_searches/{id}` |
| HTTP POST | множина resource | `POST /api/v1/cargo_searches` |
| HTTP PATCH | часткове оновлення | `PATCH /api/v1/cargo_searches/{id}` |

**Python код:**

| Елемент | Конвенція | Приклад |
|---|---|---|
| Файли/папки | snake_case | `cargo_search.py`, `auth_worker/` |
| Класи | PascalCase | `CargoSearchResult`, `LardiConnector` |
| Функції/методи | snake_case | `get_cargo_details()`, `refresh_ltsid()` |
| Змінні | snake_case | `cargo_id`, `fuel_price` |
| Константи | UPPER_SNAKE_CASE | `MAX_RESULTS = 500`, `DEFAULT_TTL = 3600` |
| Pydantic моделі | PascalCase + суфікс | `CargoSearchRequest`, `CargoSearchResponse` |

### Structure Patterns

**Де що знаходиться в кожному сервісі:**

```
app/api/          → тільки FastAPI router + endpoint функції (БЕЗ бізнес-логіки)
app/services/     → бізнес-логіка (orchestration); викликається з api/
app/db/models.py  → SQLAlchemy ORM моделі
app/db/session.py → async engine, AsyncSession factory, get_db() dependency
app/schemas/      → Pydantic моделі; окремий файл на entity (cargo.py, chat.py)
app/core/config.py→ Settings клас (pydantic-settings); єдине місце для ENV
app/core/errors.py→ ErrorCode enum + custom exception classes
tests/            → дзеркалює структуру app/ (test_api/, test_services/, тощо)
```

**Ключове правило:** router handler містить тільки `await service.method()` і `return response`. Вся логіка в `services/`.

### Format Patterns

**JSON API — snake_case скрізь:**
```json
{"workspace_id": "...", "cargo_search_id": "...", "created_at": "2026-03-17T14:30:00Z"}
```

**Success response — прямий об'єкт (без wrapper):**
```json
GET /api/v1/cargo_searches/{id}  →  {"id": "...", "status": "completed", "results": [...]}
```

**List response — з pagination:**
```json
GET /api/v1/cargo_searches  →  {"items": [...], "total": 42, "page": 1, "page_size": 20}
```

**Error response — завжди обгортка `error`:**
```json
{"error": {"code": "CARGO_NOT_FOUND", "message": "Cargo not found", "details": {}}}
```

**Дати/час:** ISO 8601 UTC — `"2026-03-17T14:30:00Z"`. В Postgres — `TIMESTAMP WITH TIME ZONE`.

**Булеві значення:** Python/JSON `true`/`false`. Не `1`/`0`.

### Communication Patterns

**Redis Channels (pub/sub):**
```
aetherion:auth:refresh   → auth-worker підписаний; запускає LTSID refresh при отриманні
```

**Redis Queue (List):**
```
aetherion:queue:lardi    → lardi-connector читає через BLPOP; один consumer
```

**Redis Message Payload:**
```json
{"event": "refresh_requested", "reason": "401", "timestamp": "2026-03-17T14:30:00Z"}
```

**structlog — обов'язкові поля в кожному log event:**
```python
# ✅ Structured logging з контекстом
log.info("cargo_search_completed",
    service="agent-service",
    workspace_id=str(workspace_id),
    chat_id=str(chat_id),
    duration_ms=elapsed,
)

# ❌ Заборонено — f-string в log message
log.info(f"Search done for {chat_id}")
```

**Log levels:**
- `DEBUG` — детальний flow для розробки
- `INFO` — успішні операції з бізнес-контекстом
- `WARNING` — degraded mode (Redis fallback, retry attempt)
- `ERROR` — помилка з повним контекстом (завжди з `exc_info=True`)

### Process Patterns

**Async rules:**
```python
# ✅ Завжди async def для ендпоінтів, сервісів і DB викликів
async def search_cargo(query: str, db: AsyncSession = Depends(get_db)) -> list[Cargo]:
    return await cargo_service.search(query, db)

# ❌ Заборонено — sync функція в async FastAPI контексті
def search_cargo(...):  # блокує весь event loop
    ...
```

**DB Session — виключно через DI:**
```python
# ✅ Через FastAPI Depends
async def endpoint(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))

# ❌ Заборонено — ручне створення session в endpoint або service
session = AsyncSession(engine)  # ЗАБОРОНЕНО поза lifespan/get_db
```

**Exception handling:**
```python
# ✅ Підіймай конкретні exceptions в services/
raise LardiConnectionError("Rate limit exceeded")

# ✅ Global handler в main.py конвертує в стандартний HTTP response

# ❌ Заборонено — silent failure
try:
    result = await lardi_api.search()
except Exception:
    pass  # ЗАБОРОНЕНО — завжди або re-raise або log + raise
```

**Retry логіка — тільки в `lardi-connector`:**
- Max 3 спроби з exponential backoff (1с → 2с → 4с)
- Retry тільки для: Lardi API 429/503, LTSID-related 401
- Не retry: 400 (bad request), 404 (not found), LLM timeout, inter-service errors

**Config — виключно через Settings:**
```python
# ✅ Через pydantic-settings
from app.core.config import settings
redis_url = settings.redis_url

# ❌ Заборонено — прямий os.environ
import os
redis_url = os.environ["REDIS_URL"]  # ЗАБОРОНЕНО
```

### Enforcement Guidelines

**AI агенти МУСЯТЬ:**
- Дотримуватись snake_case в Python файлах, DB колонках і JSON полях
- Розміщувати бізнес-логіку в `services/`, не в `api/` routers
- Використовувати `ErrorCode` enum (не рядкові literals)
- Логувати через `structlog` з полями `service` і `workspace_id`
- Оголошувати всі ендпоінти і сервіси як `async def`
- Читати конфіг через `Settings` клас

**AI агенти НЕ МОЖУТЬ:**
- Створювати таблиці без `workspace_id` колонки
- Ловити exceptions мовчки (`except: pass`)
- Використовувати sync DB/Redis виклики в async контексті
- Зберігати LTSID або Lardi credentials в logs або LLM контексті
- Додавати бізнес-логіку напряму в router handlers
- Використовувати `os.environ` напряму (тільки через `Settings`)

## Project Structure & Boundaries

### FR Categories → Компоненти

| FR Категорія | FRs | Живе в |
|---|---|---|
| Cargo Search | FR1–7 | `agent-service/app/graph/`, `agent-service/app/tools/`, `lardi-connector/app/api/` |
| Profitability Analysis | FR8–11 | `agent-service/app/tools/calc_profit.py`, `lardi-connector/app/services/distance.py` |
| Cargo Details & Contacts | FR12–13 | `lardi-connector/app/api/cargo.py` (detail endpoint) |
| Agent Interaction & Streaming | FR14–16 | `api-gateway/app/api/chat.py`, `agent-service/app/api/stream.py` |
| Session & Auth Management | FR17–20 | `auth-worker/app/browser/`, `auth-worker/app/scheduler/`, `api-gateway/app/core/auth.py` |
| Fuel Price Management | FR21–23 | `agent-service/app/services/fuel_price.py`, `auth-worker/app/scheduler/fuel_fetcher.py` |
| System Ops & Health | FR24–27 | `app/api/health.py` в кожному сервісі |
| Data Persistence | FR28–30 | `api-gateway/app/db/models/`, `api-gateway/alembic/` |

### Complete Project Directory Structure

```
aetherion-2.0/                              # Корінь монорепо
│
├── .env.example                            # Шаблон всіх ENV змінних з коментарями
├── .gitignore
├── docker-compose.yml                      # Production оркестрація
├── docker-compose.override.yml            # Dev overrides (hot reload, debug ports)
├── Makefile                                # make up/down/logs/test/migrate/lint/shell
├── ruff.toml                               # Єдиний linting/formatting конфіг для монорепо
│
├── docs/
│   ├── lardi_trans_api_reference.md        # Reverse-engineered Lardi API документація
│   └── architecture.md
│
├── api-gateway/                            # Сервіс: єдина точка входу (PORT 8000)
│   ├── Dockerfile                          # python:3.12-slim
│   ├── requirements.txt
│   ├── pytest.ini                          # asyncio_mode = "auto"
│   ├── app/
│   │   ├── main.py                        # FastAPI app factory + lifespan
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── chat.py                    # FR14-16: POST /api/v1/chats, SSE stream proxy
│   │   │   ├── workspaces.py              # FR17: GET/POST /api/v1/workspaces
│   │   │   ├── admin.py                   # FR19-20: PATCH /api/v1/admin/ltsid (X-API-Key)
│   │   │   └── health.py                  # FR24: GET /health
│   │   ├── core/
│   │   │   ├── config.py                  # Settings: REDIS_URL, POSTGRES_URL, AGENT_SERVICE_URL
│   │   │   ├── errors.py                  # ErrorCode enum + global exception handler
│   │   │   └── auth.py                    # JWT middleware stub (не enforced в MVP)
│   │   ├── db/
│   │   │   ├── base.py                    # DeclarativeBase + timestamp mixin
│   │   │   ├── session.py                 # AsyncEngine, AsyncSession, get_db()
│   │   │   └── models/
│   │   │       ├── __init__.py
│   │   │       ├── user.py                # FR28: users table (workspace_id, email)
│   │   │       ├── workspace.py           # FR28: workspaces table
│   │   │       ├── chat.py                # FR29: chats table (workspace_id, title)
│   │   │       └── message.py             # FR30: messages (chat_id, role, content, timestamp)
│   │   ├── schemas/
│   │   │   ├── chat.py                    # ChatCreateRequest, ChatResponse, MessageResponse
│   │   │   ├── workspace.py               # WorkspaceCreateRequest, WorkspaceResponse
│   │   │   └── admin.py                   # LtsidUpdateRequest
│   │   └── services/
│   │       ├── chat_service.py            # DB save + SSE proxy to agent-service
│   │       └── workspace_service.py       # CRUD для workspace
│   ├── alembic/                           # FR28-30: Database migrations
│   │   ├── env.py
│   │   ├── alembic.ini
│   │   └── versions/
│   │       └── 0001_initial_schema.py
│   └── tests/
│       ├── conftest.py                    # TestClient, test DB session
│       ├── test_api/
│       │   ├── test_chat.py
│       │   ├── test_workspaces.py
│       │   └── test_health.py
│       └── test_services/
│           └── test_chat_service.py
│
├── agent-service/                         # Сервіс: LangGraph + LLM (PORT 8001, internal)
│   ├── Dockerfile                          # python:3.12-slim
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py                        # FastAPI + lifespan (Redis pool, fuel price init)
│   │   ├── api/
│   │   │   ├── stream.py                  # FR14-16: POST /stream → SSE response
│   │   │   └── health.py                  # FR24: GET /health (Redis, LLM ping)
│   │   ├── core/
│   │   │   ├── config.py                  # OPENROUTER_API_KEY, LARDI_CONNECTOR_URL, REDIS_URL
│   │   │   └── errors.py                  # AgentTimeoutError, LLMUnavailableError
│   │   ├── graph/
│   │   │   ├── state.py                   # AgentState TypedDict (LangGraph state schema)
│   │   │   ├── nodes.py                   # Node functions: parse_intent, call_tool, format_response
│   │   │   ├── edges.py                   # Conditional edges (tool routing logic)
│   │   │   └── graph.py                   # Compiled LangGraph graph (singleton)
│   │   ├── tools/
│   │   │   ├── __init__.py                # Tool registry для LangGraph
│   │   │   ├── search_cargo.py            # FR1-7: tool → lardi-connector POST /search
│   │   │   ├── get_cargo_detail.py        # FR12-13: tool → lardi-connector GET /cargo/{id}
│   │   │   └── calc_profit.py             # FR8-11: distance × fuel × price формула
│   │   ├── prompts/
│   │   │   └── system_prompt.py           # System prompt з prompt injection defense
│   │   └── services/
│   │       ├── agent_runner.py            # Запускає graph, повертає async generator для SSE
│   │       └── fuel_price.py              # FR21-23: Redis primary + in-memory fallback
│   └── tests/
│       ├── conftest.py
│       ├── test_api/
│       │   └── test_stream.py
│       ├── test_tools/
│       │   ├── test_search_cargo.py
│       │   └── test_calc_profit.py
│       └── test_services/
│           └── test_fuel_price.py
│
├── lardi-connector/                       # Сервіс: Lardi API adapter + queue (PORT 8002, internal)
│   ├── Dockerfile                          # python:3.12-slim
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py                        # FastAPI + lifespan (Redis pool, queue consumer start)
│   │   ├── api/
│   │   │   ├── cargo.py                   # POST /search (FR1-7), GET /cargo/{id} (FR12-13)
│   │   │   └── health.py                  # FR24: GET /health
│   │   ├── core/
│   │   │   ├── config.py                  # LARDI_BASE_URL, REDIS_URL, timeout values
│   │   │   └── errors.py                  # LardiRateLimitError, LardiConnectionError, LtsidExpiredError
│   │   ├── schemas/
│   │   │   ├── cargo_search.py            # CargoSearchRequest, CargoSearchResponse, CargoItem
│   │   │   └── cargo_detail.py            # CargoDetailResponse (з contacts)
│   │   └── services/
│   │       ├── lardi_client.py            # httpx AsyncClient; retry logic; 401 → publish refresh
│   │       ├── queue_manager.py           # FR26: Redis BLPOP consumer; ≤1 concurrent request
│   │       └── distance.py               # Meters → km conversion; geo ID resolution
│   └── tests/
│       ├── conftest.py
│       ├── test_api/
│       │   └── test_cargo.py
│       └── test_services/
│           ├── test_lardi_client.py
│           └── test_queue_manager.py
│
└── auth-worker/                           # Сервіс: Cloudflare bypass + LTSID (PORT 8003)
    ├── Dockerfile                          # python:3.12-slim + Chromium deps (~1.2GB image)
    ├── requirements.txt
    ├── pytest.ini
    ├── app/
    │   ├── main.py                        # FastAPI + lifespan (initial LTSID fetch + scheduler)
    │   ├── api/
    │   │   ├── admin.py                   # FR20: POST /admin/ltsid/refresh (X-API-Key)
    │   │   └── health.py                  # FR24: GET /health → LTSID valid check
    │   ├── core/
    │   │   ├── config.py                  # LARDI_LOGIN, LARDI_PASSWORD, REDIS_URL, LTSID_TTL_HOURS
    │   │   └── errors.py                  # ChromeStartupError, LtsidFetchError
    │   ├── browser/
    │   │   ├── driver.py                  # undetected-chromedriver setup (headless, bypass)
    │   │   ├── login_flow.py              # FR18: Lardi login automation → cookie extraction
    │   │   └── cookie_parser.py           # Extract LTSID value від Set-Cookie header
    │   └── scheduler/
    │       ├── refresh_scheduler.py       # Proactive LTSID refresh (asyncio task, 30min check)
    │       └── fuel_fetcher.py            # FR21: hourly HTTP fetch → Redis write
    └── tests/
        ├── conftest.py
        ├── test_api/
        │   └── test_admin.py
        └── test_scheduler/
            └── test_refresh_scheduler.py
```

### Architectural Boundaries

**Зовнішні межі:**
```
Internet → api-gateway:8000            # єдина публічна точка входу
              ↓ internal Docker network
         agent-service:8001            # internal only
         lardi-connector:8002          # internal only
         auth-worker:8003              # internal only (адмін через Makefile/direct)
```

**Security boundary — LTSID isolation:**
```
auth-worker  → пише  aetherion:auth:ltsid  в Redis
lardi-connector → читає aetherion:auth:ltsid  з Redis
agent-service   → НЕ знає про LTSID key; не має доступу
LLM context     → LTSID НІКОЛИ не передається
```

**Data flow — cargo search (FR1–FR11):**
```
Client
  POST /api/v1/chats/{id}/messages       → api-gateway
  SSE proxy                              → agent-service
  LangGraph: parse_intent node           → agent-service/graph
  search_cargo tool                      → agent-service/tools
  POST /search                           → lardi-connector
  Redis queue (BLPOP, ≤1 concurrent)    → lardi-connector/services/queue_manager
  GET aetherion:auth:ltsid               → Redis
  Lardi API                              → internet
  calc_profit tool                       → agent-service/tools
  GET aetherion:fuel:price:diesel        → Redis (fallback: in-memory)
  SSE stream tokens                      → agent-service → api-gateway → Client
  save message                           → api-gateway → Postgres
```

### Integration Points

**Internal HTTP:**

| Caller | Target URL | Purpose |
|---|---|---|
| api-gateway | `http://agent-service:8001/stream` | SSE stream для chat response |
| agent-service | `http://lardi-connector:8002/search` | FR1-7: cargo search |
| agent-service | `http://lardi-connector:8002/cargo/{id}` | FR12-13: cargo detail + contacts |

**Redis cross-service keys:**

| Key | Writer | Reader |
|---|---|---|
| `aetherion:auth:ltsid` | auth-worker | lardi-connector |
| `aetherion:auth:refresh:lock` | auth-worker | auth-worker |
| `aetherion:auth:refresh` (channel) | lardi-connector (publish) | auth-worker (subscribe) |
| `aetherion:queue:lardi` (List) | lardi-connector (LPUSH) | lardi-connector (BLPOP) |
| `aetherion:fuel:price:diesel` | auth-worker/fuel_fetcher | agent-service |

**External integrations:**

| Service | From | Purpose |
|---|---|---|
| Lardi API (`lardi.com.ua/api/*`) | lardi-connector | Cargo search, details, contacts |
| OpenRouter API | agent-service | LLM completions (streaming) |
| Fuel price source (ОККО або аналог) | auth-worker/fuel_fetcher | FR21: hourly price update |
| Lardi login page | auth-worker/browser | LTSID acquisition via Chromium |

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility:**
Всі технологічні рішення сумісні між собою:
- FastAPI 0.135.1 + SQLAlchemy 2.0.46 async + asyncpg 0.31.0 — офіційно підтримувана комбінація
- LangGraph 1.1.0 + httpx async — без конфліктів; v2 streaming API → SSE pipeline
- redis-py 5.x async + FastAPI lifespan — стандартний підхід для connection pooling
- pytest-asyncio 1.3.0 + `asyncio_mode=auto` — задокументовано в pytest.ini кожного сервісу
- pydantic-settings 2.x вбудований в FastAPI (Pydantic v2 dependency)

**Pattern Consistency:**
Naming (snake_case), структура (`api/` → `services/` → `db/`), error handling (ErrorCode enum), logging (structlog з обов'язковими полями) — консистентні між усіма 4 сервісами.

**Structure Alignment:**
Дерево папок відповідає технологічному стеку і паттернам. Кожен FR mapped до конкретного файлу. Security boundary (LTSID isolation) підтримується структурою — `agent-service` фізично не має `lardi_client.py` і не знає Redis key name.

### Requirements Coverage Validation ✅

**Functional Requirements (30/30 покрито):**

| Категорія | FRs | Файли |
|---|---|---|
| Cargo Search | FR1–7 | `tools/search_cargo.py` + `lardi-connector/api/cargo.py` |
| Profitability Analysis | FR8–11 | `tools/calc_profit.py` + `services/fuel_price.py` |
| Cargo Details & Contacts | FR12–13 | `tools/get_cargo_detail.py` + `lardi-connector/api/cargo.py` |
| Agent Interaction & Streaming | FR14–16 | `api/chat.py` (SSE proxy) + `agent-service/api/stream.py` |
| Session & Auth Management | FR17–20 | `browser/login_flow.py` + `api/admin.py` (manual endpoint) |
| Fuel Price Management | FR21–23 | `scheduler/fuel_fetcher.py` + `services/fuel_price.py` (fallback) |
| System Ops & Health | FR24–27 | `api/health.py` в кожному сервісі + Docker depends_on chain |
| Data Persistence | FR28–30 | `db/models/` (4 таблиці) + `alembic/versions/` |

**Non-Functional Requirements (всі покриті):**

| NFR | Механізм |
|---|---|
| ≤15с повна відповідь | async скрізь + LLM read timeout 30с |
| ≤3с перший streaming chunk | `httpx.Timeout(connect=3.0)` до OpenRouter |
| Auto-recovery від 401 | lardi-connector → Redis publish → auth-worker emergency refresh (90с timeout) |
| LTSID isolation | Security boundary: agent-service не має доступу до `aetherion:auth:ltsid` |
| Prompt injection defense | 3 шари: tool scope + `[EXTERNAL DATA]` wrapping + system prompt hardening |
| Explicit timeouts | 6 значень задокументовано в Core Decisions |
| Docker health ordering | depends_on chain з healthcheck для всіх 6 сервісів |

### Implementation Readiness Validation ✅

**Decision Completeness:** 15 архітектурних рішень задокументовано з версіями, rationale та наслідками.

**Structure Completeness:** Повне дерево папок із 60+ файлів; кожен файл прокоментований; всі integration points специфіковані.

**Pattern Completeness:** 7 категорій конфліктів адресовано; заборонені паттерни явно перераховані.

### Gap Analysis Results

**Critical Gaps:** Відсутні.

**Important Gaps (закриті в цьому кроці):**

1. **ENV змінні зведені в таблицю** — додано нижче в `.env.example` reference
2. **LLM модель обрана** — `openrouter/auto` через OpenRouter API

**Nice-to-Have (Post-MVP):**
- Alembic `env.py` шаблон — покривається першою implementation story
- Повний вміст `Makefile` — перша story
- Centralized log collection (Loki/Grafana) — Phase 2

### Environment Variables Reference

Повна таблиця ENV змінних для `.env.example`:

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
REDIS_URL=redis://redis:6379/0

# ================================================
# lardi-connector
# ================================================
LARDI_BASE_URL=https://lardi-trans.com
REDIS_URL=redis://redis:6379/0

# ================================================
# auth-worker
# ================================================
LARDI_LOGIN=<your-lardi-email>
LARDI_PASSWORD=<your-lardi-password>
REDIS_URL=redis://redis:6379/0
LTSID_TTL_HOURS=23
FUEL_CACHE_TTL_SECONDS=3600
ADMIN_API_KEY=changeme-replace-in-production

# ================================================
# postgres (docker-compose service)
# ================================================
POSTGRES_USER=aetherion
POSTGRES_PASSWORD=aetherion
POSTGRES_DB=aetherion
```

**Security note:** `.env` файл з реальними credentials завжди в `.gitignore`. В репозиторій комітиться тільки `.env.example` з placeholder значеннями.

### Architecture Completeness Checklist

**✅ Requirements Analysis**
- [x] Project context thoroughly analyzed (30 FRs + NFRs)
- [x] Scale and complexity assessed (Medium; MVP single-tenant)
- [x] Technical constraints identified (Cloudflare, Lardi API quirks, Redis roles)
- [x] Cross-cutting concerns mapped (6 категорій)

**✅ Architectural Decisions**
- [x] Critical decisions documented with versions (15 рішень)
- [x] Technology stack fully specified (12 інструментів з версіями)
- [x] Integration patterns defined (HTTP hybrid + Redis)
- [x] Performance considerations addressed (timeouts, async, streaming)

**✅ Implementation Patterns**
- [x] Naming conventions established (DB, API, Python code)
- [x] Structure patterns defined (api/ → services/ → db/)
- [x] Communication patterns specified (Redis keys, structlog fields)
- [x] Process patterns documented (async, DI, error handling, retry)

**✅ Project Structure**
- [x] Complete directory structure defined (60+ файлів)
- [x] Component boundaries established (security boundary для LTSID)
- [x] Integration points mapped (HTTP URLs + Redis keys таблиці)
- [x] Requirements to structure mapping complete (FR → файл)

### Architecture Readiness Assessment

**Overall Status: READY FOR IMPLEMENTATION**

**Confidence Level: High**

**Key Strengths:**
- Чітка security boundary для LTSID — жодна випадкова зміна не зможе витікти credentials в LLM
- Async-first архітектура із задокументованими timeout values на кожному рівні
- Flat monorepo з повністю self-contained сервісами — легко онбордити нового розробника/агента
- Кожен FR mapped до конкретного файлу — реалізація не потребує додаткового аналізу

**Areas for Future Enhancement (Post-MVP):**
- Centralized structured log collection (Loki + Grafana)
- Redis Sentinel для high availability
- GitHub Actions CI/CD pipeline
- Per-chat filter profiles (FR відкладено на Phase 2)
- Multi-connector failover (Phase 3)

### Implementation Handoff

**AI Agent Guidelines:**
- Дотримуватись усіх архітектурних рішень точно як задокументовано
- Використовувати implementation patterns консистентно між усіма сервісами
- Поважати project structure та boundaries (особливо LTSID security boundary)
- Звертатись до цього документу для будь-яких архітектурних питань

**First Implementation Priority:**
Створення Docker Compose монорепо:
```bash
mkdir -p aetherion-2.0/{api-gateway,agent-service,lardi-connector,auth-worker}/app/{api,core,db,schemas,services}
mkdir -p aetherion-2.0/agent-service/app/{tools,graph,prompts}
mkdir -p aetherion-2.0/auth-worker/app/{browser,scheduler}
# + docker-compose.yml, .env.example, ruff.toml, Makefile
```
