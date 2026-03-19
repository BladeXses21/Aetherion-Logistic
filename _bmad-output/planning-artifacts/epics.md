---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
status: complete
completedAt: '2026-03-19'
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/planning-artifacts/architecture.md'
---

# Aetherion 2.0 - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for Aetherion 2.0, decomposing the requirements from the PRD and Architecture into implementable stories.

## Requirements Inventory

### Functional Requirements

**Cargo Search**
- FR1: User can search for cargo using natural language describing route, vehicle type, weight, and dates
- FR2: Agent can extract structured Lardi search filters from natural language input
- FR3: Agent can resolve city names to Lardi geo IDs for use in search requests
- FR4: User can search cargo by country-level, oblast-level, and city-level directions
- FR5: Agent can filter cargo by vehicle body type using correct integer IDs
- FR6: Agent can filter cargo by weight, volume, loading type, and date range
- FR7: Agent can retrieve paginated search results and present the most relevant matches

**Cargo Profitability Analysis**
- FR8: Agent can calculate estimated fuel cost for a cargo route based on distance and current fuel price
- FR9: Agent can calculate trip margin (cargo payment minus fuel cost)
- FR10: Agent can rank search results by profitability and present top matches with a brief explanation
- FR11: Agent can suggest specific filter adjustments when search returns zero results

**Cargo Details & Contacts**
- FR12: Agent can retrieve full cargo offer details including shipper contact phone number
- FR13: User can request contact details for a specific cargo from search results

**Agent Interaction & Streaming**
- FR14: Agent can stream reasoning status messages to the user during request processing
- FR15: Agent can stream the final response token-by-token rather than returning a single completed response
- FR16: System can queue incoming user requests when the agent is already processing, preventing concurrent execution

**Session & Authentication Management**
- FR17: System can obtain a valid Lardi session cookie via browser-based login
- FR18: System can detect an expired Lardi session and automatically trigger cookie refresh
- FR19: System can retry a failed Lardi request after successful session refresh
- FR20: Admin can manually set a Lardi session cookie via a protected admin endpoint

**Fuel Price Management**
- FR21: System can fetch current fuel prices from an external public source
- FR22: System can update stored fuel price on startup and on an hourly schedule
- FR23: System can fall back to the last stored fuel price when the external source is unavailable

**System Operations & Health**
- FR24: Admin can check the health status of all system services via a single endpoint
- FR25: Admin can trigger a manual Lardi session refresh without restarting the system
- FR26: System can queue Lardi API requests globally to prevent concurrent calls and rate-limit violations
- FR27: User can interact with the agent via HTTP API through Swagger UI

**Data Persistence**
- FR28: System can persist chat history per conversation session
- FR29: System can store and retrieve user and workspace records with multi-tenant-ready schema
- FR30: System can store Lardi session data in Redis with TTL-based expiry

### NonFunctional Requirements

**Performance**
- NFR1: Agent response time ≤15 seconds under normal conditions; first streaming chunk ≤3 seconds
- NFR2: Maximum 1 concurrent request to Lardi via global Redis Queue
- NFR3: Fuel price fetch on startup is non-blocking (executes asynchronously)

**Reliability**
- NFR4: On 401 from Lardi, system automatically recovers without losing the request
- NFR5: When fuel price API is unavailable, system continues with last cached value
- NFR6: On LLM timeout/503, agent returns explicit message within 30 seconds; no infinite open connections
- NFR7: All errors logged with sufficient context for debugging
- NFR8: /health correctly reflects status of each dependent service

**Security**
- NFR9: Lardi credentials and OpenRouter API key exclusively in ENV — not logged, not passed to LLM context
- NFR10: LTSID cookie isolated in auth-worker and lardi-connector — LLM has no access
- NFR11: Admin endpoint POST /admin/cookie protected (X-API-Key header; value from ENV ADMIN_API_KEY)
- NFR12: Prompt injection defense: tool scope limiting + [EXTERNAL DATA] wrapping + system prompt hardening

**Integration**
- NFR13: lardi-connector isolates all Lardi-specific logic — API changes require modifications to only one service
- NFR14: All external HTTP calls (Lardi, OpenRouter, fuel price API) have explicit timeouts
- NFR15: Docker Compose starts services in correct order with health check dependencies

**Maintainability**
- NFR16: Each service has single responsibility
- NFR17: No hardcoded values — exclusively ENV-based configuration via pydantic-settings
- NFR18: Postgres schema contains workspace_id and user_id in all relevant tables from day one

### Additional Requirements

**Infrastructure / Monorepo Setup**
- ARCH1: Starter template — flat monorepo structure (Variant C), manually created; reference: benavlabs/FastAPI-boilerplate. **First implementation story = creating monorepo skeleton with Docker Compose, folder structure, base main.py and Dockerfile for each service.**
- ARCH2: Technology stack pinned versions: Python 3.12+, FastAPI 0.135.1, SQLAlchemy 2.0.46 async + asyncpg 0.31.0, Alembic 1.18.4, LangGraph 1.1.0, redis-py 5.x async, pydantic-settings 2.x, Ruff 0.15.3, structlog 25.5.0, pytest 8.x, pytest-asyncio 1.3.0
- ARCH3: 4 Python services (api-gateway:8000, agent-service:8001, lardi-connector:8002, auth-worker:8003) + redis:6379 + postgres:5432; each service self-contained Docker image
- ARCH4: Makefile at monorepo root: make up/down/logs/test/migrate/lint/shell commands

**Data Architecture**
- ARCH5: Postgres row-level tenancy: workspace_id UUID NOT NULL in every table; Alembic migration from day 1
- ARCH6: Redis key naming: aetherion:{service}:{entity}:{id}; TTL via ENV (LTSID_TTL_HOURS=23, FUEL_CACHE_TTL_SECONDS=3600, SESSION_TTL_HOURS=24)

**Communication & API Patterns**
- ARCH7: Inter-service: api-gateway→agent-service via HTTP+SSE; agent-service→lardi-connector via HTTP; auth events via Redis pub/sub (aetherion:auth:refresh)
- ARCH8: API versioning: /api/v1/ prefix for all public endpoints
- ARCH9: Standard error response format with ErrorCode enum in core/errors.py; global exception handler in main.py
- ARCH10: All endpoints and services declared as async def; sync DB/Redis calls forbidden in async context
- ARCH11: LangGraph streaming uses version="v2" API (typed StreamPart objects → SSE events)

**Auth & Session**
- ARCH12: JWT middleware present but not enforced in MVP (stub); admin endpoints protected via X-API-Key
- ARCH13: LTSID refresh: proactive check every 30min (refresh if TTL < 1hr) + emergency (401 → Redis channel → immediate refresh); race condition protection via SET NX EX lock
- ARCH14: Fuel price fallback: Redis primary (1hr TTL) → agent-service in-memory secondary

**Deployment**
- ARCH15: Docker Compose health check chain: postgres/redis → auth-worker (start_period: 120s) → lardi-connector + agent-service → api-gateway
- ARCH16: Implementation sequence: Postgres schema → Redis key structure → auth-worker → lardi-connector → agent-service → api-gateway

### UX Design Requirements (none)

No UX Design document exists — MVP is backend-only with Swagger UI as the interaction interface (FR27).

### FR Coverage Map

- FR1–FR7: Epic 3 Story 3.2 (raw Lardi search API in lardi-connector) + Epic 4 (NLP orchestration in agent-service)
- FR8–FR11: Epic 4 — calc_profit tool in agent-service; profitability ranking + zero-results suggestions
- FR12–FR13: Epic 3 Story 3.3 (raw detail API in lardi-connector) + Epic 4 (get_cargo_detail tool in agent-service)
- FR14–FR16: Epic 4 — SSE streaming via api-gateway; request queuing
- FR17–FR20: Epic 2 — auth-worker: browser login, proactive refresh, emergency refresh, manual admin endpoint
- FR21–FR23: Epic 3 Story 3.5 — fuel_fetcher scheduler: startup + hourly fetch, Redis cache, fallback
- FR24: Epic 1 — /health endpoints on all 4 services
- FR25: Epic 2 — POST /admin/ltsid/refresh in auth-worker
- FR26: Epic 3 Story 3.1 — Redis BLPOP queue in lardi-connector/queue_manager.py
- FR27: Epic 1 — Swagger UI on api-gateway:8000
- FR28–FR30: Epic 1 (schema created via Alembic) + Epic 4 (chat/message persistence active)

## Epic List

### Epic 1: System Foundation & Infrastructure
The complete monorepo skeleton is running. All 6 services boot healthy via `make up`, Swagger UI is accessible at port 8000, the database schema is initialized with multi-tenant-ready tables, and Redis is configured with the correct key namespace.
**FRs covered:** FR24, FR27, FR28 (schema), FR29 (schema), FR30 (Redis TTL structure)
**ARCH covered:** ARCH1–ARCH16
**NFRs covered:** NFR15 (Docker Compose health chain), NFR16 (single responsibility), NFR17 (ENV config), NFR18 (workspace_id from day 1)

### Epic 2: Automated Lardi Session Management
The system autonomously handles Lardi authentication — obtains LTSID via Chrome on startup, refreshes proactively before expiry, and auto-recovers from 401 responses. Admin can manually update the session via a protected endpoint without restarting the system.
**FRs covered:** FR17, FR18, FR19, FR20, FR25
**NFRs covered:** NFR4 (auto-recovery), NFR9 (credentials in ENV only), NFR10 (LTSID isolation), NFR11 (admin endpoint protection)

### Epic 3: Lardi Data Access & Fuel Intelligence
Raw cargo search and shipper contact data is accessible through the internal lardi-connector API with all filter types (city/oblast/country, vehicle type, weight, dates). A global Redis queue prevents concurrent Lardi requests. Fuel pricing is fetched, cached, and available with fallback.
**FRs covered:** FR1–FR7, FR12, FR13, FR21, FR22, FR23, FR26
**NFRs covered:** NFR2 (≤1 concurrent Lardi request), NFR3 (non-blocking fuel fetch), NFR5 (fuel fallback), NFR13 (Lardi isolation), NFR14 (explicit timeouts)

### Epic 4: AI-Powered Cargo Search with Streaming
Artur types a natural language request in Swagger UI and receives a streaming agent response with real-time reasoning status, top cargo results ranked by profitability (fuel cost + margin), actionable suggestions when no results are found, and the shipper's contact for the selected cargo. All chat history is persisted.
**FRs covered:** FR1–FR16, FR8–FR11, FR28–FR30
**NFRs covered:** NFR1 (≤15s response, ≤3s first chunk), NFR6 (LLM timeout), NFR7 (structured logging), NFR8 (/health complete), NFR12 (prompt injection defense)

---

## Epic 1: System Foundation & Infrastructure

The complete monorepo skeleton is running. All 6 services boot healthy via `make up`, Swagger UI is accessible at port 8000, the database schema is initialized with multi-tenant-ready tables, and Redis is configured with the correct key namespace.

### Story 1.1: Monorepo Skeleton & Docker Compose Setup

As a developer,
I want a complete monorepo structure with all services wired into Docker Compose,
So that I can boot the entire system with a single `make up` command and have a foundation for all subsequent development.

**Acceptance Criteria:**

**Given** the repository is cloned and `.env` is populated from `.env.example`
**When** `make up` is run
**Then** all 6 containers start: `api-gateway`, `agent-service`, `lardi-connector`, `auth-worker`, `redis`, `postgres`
**And** each Python service has: `Dockerfile`, `requirements.txt`, `pytest.ini` (asyncio_mode=auto), `app/main.py` (FastAPI skeleton with lifespan), `app/core/config.py` (pydantic-settings BaseSettings)

**Given** the monorepo root
**When** inspecting the file structure
**Then** `docker-compose.yml` defines all 6 services with correct ports (8000/8001/8002/8003/6379/5432) and health check dependencies per ARCH15
**And** `docker-compose.override.yml` adds volume mounts for hot reload
**And** `.env.example` documents all required ENV variables with comments
**And** `Makefile` supports: `make up`, `make down`, `make logs`, `make test`, `make migrate`, `make lint`, `make shell s={service}`
**And** `ruff.toml` is present at monorepo root for shared linting/formatting

### Story 1.2: Database Schema & Alembic Migration

As a developer,
I want the Postgres database schema with multi-tenant-ready tables initialized via Alembic,
So that all services have a shared data foundation from day one.

**Acceptance Criteria:**

**Given** Postgres is running and `DATABASE_URL` is set
**When** `make migrate` is run (i.e., `alembic upgrade head` in `api-gateway`)
**Then** 6 tables are created: `users`, `workspaces`, `workspace_users`, `chats`, `messages`, `ua_cities`
**And** `workspaces`: `id UUID PK`, `name VARCHAR(100) UNIQUE`, `created_at TIMESTAMPTZ` — no `owner_id` column; ownership is via `workspace_users`
**And** `workspace_users`: `workspace_id UUID FK → workspaces.id`, `user_id UUID FK → users.id`, `role VARCHAR` (owner/admin/member), `joined_at TIMESTAMPTZ` — composite PK (`workspace_id`, `user_id`)
**And** `chats` has FK `workspace_id` → `workspaces.id` and FK `user_id` → `users.id`
**And** `messages` has FK `chat_id` → `chats.id` with columns: `role VARCHAR`, `content TEXT`, `status VARCHAR` (complete/streaming/incomplete), `created_at TIMESTAMPTZ`
**And** `ua_cities`: `id SERIAL PK`, `name_ua VARCHAR(150)`, `region_name VARCHAR(100)`, `lat FLOAT`, `lon FLOAT`, `lardi_town_id INTEGER UNIQUE`, `source VARCHAR(30)`, `created_at TIMESTAMPTZ` — `pg_trgm` extension enabled; `embedding vector(384)` added if pgvector extension is available
**And** all indexes follow the `ix_{table}_{column}` naming convention
**And** SQLAlchemy async models in `api-gateway/app/db/models/` mirror the schema exactly

**Given** a clean Postgres instance
**When** migration runs twice (idempotency check)
**Then** the second run reports "already at head" with no errors

**Given** the `ua_cities` table is empty after migration
**When** the dev runs `make seed-cities` (script: `scripts/import_cities_v1.py`)
**Then** city data is imported from the v1 project's `ua_cities` table (export via `pg_dump` or direct SQL copy) — `lardi_town_id` values preserved
**Note:** v1 source: `C:\Users\artur\.gemini\antigravity\scratch\Aetherion Agent` Postgres DB

### Story 1.3: Health Endpoints for All Services

As an operator,
I want a `/health` endpoint on every service,
So that I can verify system status at a glance without entering Docker containers.

**Acceptance Criteria:**

**Given** all services are running healthy
**When** `GET /health` is called on each service port
**Then** each returns HTTP 200 with: `{"status": "healthy", "service": "<name>", "dependencies": {...}}`
**And** `api-gateway /health` checks: Redis reachable, Postgres reachable, agent-service reachable
**And** `agent-service /health` checks: Redis reachable
**And** `lardi-connector /health` checks: Redis reachable
**And** `auth-worker /health` checks: Redis reachable (LTSID check added in Epic 2)

**Given** Redis is stopped
**When** `GET /health` is called on any service that depends on Redis
**Then** the response is HTTP 503 with `"status": "unhealthy"` and the failing dependency marked

**Given** all services running
**When** `GET /docs` is accessed on `api-gateway:8000`
**Then** Swagger UI is accessible without authentication

---

## Epic 2: Automated Lardi Session Management

The system autonomously handles Lardi authentication — obtains LTSID via Chrome on startup, refreshes proactively before expiry, and auto-recovers from 401 responses. Admin can manually update the session via a protected endpoint without restarting the system.

### Story 2.1: Initial LTSID Acquisition on Startup

As a system operator,
I want the system to automatically obtain a valid Lardi session cookie when auth-worker starts,
So that the system is ready to make Lardi API calls without any manual browser work.

**Acceptance Criteria:**

**Given** `LARDI_LOGIN`, `LARDI_PASSWORD`, and `REDIS_URL` are set in ENV
**When** auth-worker starts (lifespan event)
**Then** undetected-chromedriver launches a headless Chromium browser, executes Lardi login, and extracts the `LTSID` cookie
**And** LTSID is stored in Redis as `aetherion:auth:ltsid` with TTL from `LTSID_TTL_HOURS` (default: 23h)
**And** `GET /health` returns `{"ltsid": "valid", "redis": "ok"}`

**Given** Redis is unavailable at startup
**When** auth-worker lifespan runs
**Then** LTSID is stored in an in-memory fallback variable instead of Redis
**And** structlog logs `ERROR "redis_unavailable_ltsid_stored_in_memory"`
**And** `GET /health` returns `{"ltsid": "in_memory_only", "redis": "down"}` — container does NOT crash

**Given** Chrome fails to start or Lardi login fails
**When** auth-worker lifespan runs
**Then** `LtsidFetchError` is raised and logged via structlog with `exc_info=True`
**And** auth-worker still starts but `/health` reports `"ltsid": "missing"`

**Given** the system is running at any log level (DEBUG, INFO, WARNING, ERROR)
**When** structlog output is inspected
**Then** the values of `LARDI_PASSWORD`, `OPENROUTER_API_KEY`, and the full `LTSID` cookie value do NOT appear in any log line

### Story 2.2: Proactive LTSID Refresh Scheduler

As a system operator,
I want the auth-worker to automatically refresh the Lardi session before it expires,
So that the system never hits a 401 error due to session expiry during normal operation.

**Acceptance Criteria:**

**Given** auth-worker is running with a valid LTSID in Redis
**When** the background scheduler checks every 30 minutes
**Then** if `TTL aetherion:auth:ltsid` < 3600 seconds, a Chrome refresh is triggered
**And** the new LTSID overwrites the old key with a fresh 23-hour TTL
**And** structlog logs `INFO "ltsid_proactive_refresh_completed"` with new TTL value

**Given** Redis is unavailable when scheduler runs
**When** the TTL check fails with a Redis connection error
**Then** scheduler logs `WARNING "redis_unavailable_skipping_ttl_check"` and continues running
**And** the next cycle (30 min later) attempts the check again — scheduler does NOT crash

**Given** the LTSID still has > 1 hour TTL
**When** the scheduler checks
**Then** no refresh is triggered

### Story 2.3: Emergency Refresh via Redis Pub/Sub

As a system operator,
I want the auth-worker to immediately refresh the Lardi session when any service reports a 401,
So that in-flight requests can be retried without user-visible failures.

**Acceptance Criteria:**

**Given** auth-worker is subscribed to Redis channel `aetherion:auth:refresh`
**When** a message `{"event": "refresh_requested", "reason": "401", "timestamp": "..."}` is published
**Then** auth-worker attempts `SET aetherion:auth:refresh:lock NX EX 120` (ENV: `LTSID_REFRESH_LOCK_TTL_SECONDS=120`)
**And** if lock acquired → triggers Chrome refresh within 60s (`CHROME_TIMEOUT_SECONDS=60`) and writes new LTSID to Redis
**And** structlog logs `INFO "ltsid_emergency_refresh_completed"`

**Given** a refresh is already in progress (lock NOT acquired — race condition scenario)
**When** a second 401-event arrives on the channel
**Then** auth-worker does NOT launch a second Chrome instance
**And** polls until `aetherion:auth:refresh:lock` is released (max 90s)
**And** after lock released, new LTSID is already in Redis — no additional refresh needed
**And** structlog logs `INFO "ltsid_refresh_deduplicated" reason="lock_held_waited"`

**Given** Redis pub/sub is unavailable
**When** auth-worker attempts to subscribe
**Then** structlog logs `ERROR "redis_pubsub_unavailable"` and auth-worker does NOT crash
**And** upon Redis recovery, pub/sub subscription is re-established via lifespan retry logic

**Given** Chrome refresh has failed 3 consecutive times (circuit breaker threshold: `REFRESH_CIRCUIT_BREAKER_THRESHOLD=3`)
**When** another refresh is triggered
**Then** auth-worker pauses all refresh attempts for `REFRESH_CIRCUIT_BREAKER_PAUSE_MINUTES=10`
**And** structlog logs `WARNING "ltsid_circuit_breaker_open" pause_minutes=10`
**And** after the pause, circuit breaker resets and the next refresh attempt proceeds normally

**Given** Chrome refresh fails with error
**When** the emergency refresh completes
**Then** `aetherion:auth:ltsid` is NOT overwritten
**And** structlog logs `ERROR "ltsid_emergency_refresh_failed"` with `exc_info=True`

### Story 2.4: Manual Session Management Admin Endpoint

As an operator,
I want a protected admin endpoint to manually trigger a Lardi session refresh,
So that I can recover from auth failures without restarting any containers.

**Acceptance Criteria:**

**Given** `ADMIN_API_KEY` is set in ENV
**When** `POST /admin/ltsid/refresh` is called on auth-worker with header `X-API-Key: <value>`
**Then** an immediate Chrome LTSID refresh is triggered
**And** response is HTTP 200 with `{"status": "ok", "ltsid_ttl_seconds": <new_ttl>, "refreshed_at": "<ISO timestamp>"}`

**Given** an invalid or missing `X-API-Key` header
**When** `POST /admin/ltsid/refresh` is called
**Then** response is HTTP 401 with `{"error": {"code": "UNAUTHORIZED", "message": "Invalid API key"}}`

**Given** a valid `X-API-Key`
**When** `PATCH /api/v1/admin/ltsid` is called on `api-gateway:8000`
**Then** api-gateway proxies the request to `auth-worker:8003/admin/ltsid/refresh` forwarding the `X-API-Key` header
**And** the response is returned to the caller unchanged

---

## Epic 3: Lardi Data Access & Fuel Intelligence

Raw cargo search and shipper contact data is accessible through the internal lardi-connector API with all filter types. A global Redis queue with rate limiting prevents concurrent Lardi requests. Fuel pricing is fetched, cached, and available with fallback.

### Story 3.1: Global Redis Queue with Rate Limiting

As a system operator,
I want all Lardi API calls to flow through a rate-limited Redis queue,
So that the system never sends more than one concurrent request to Lardi and respects a minimum interval between calls.

**Acceptance Criteria:**

**Given** lardi-connector is running
**When** any Lardi API request is initiated (search or detail)
**Then** the request is enqueued in `aetherion:queue:lardi` (Redis List) and a single consumer processes it via `BLPOP` with timeout=5s in a retry loop
**And** after dequeuing, the consumer waits `LARDI_REQUEST_MIN_INTERVAL_SECONDS` (ENV, default: 1.0s) before executing the HTTP call — this enforces rate limiting
**And** at most 1 Lardi request is in-flight at any given time

**Given** two simultaneous requests arrive at lardi-connector
**When** the first request is being processed
**Then** the second waits in queue; structlog logs `INFO "lardi_request_queued" request_id=<id> queue_depth=<n> wait_ms=<ms>`

**Given** the BLPOP consumer does not receive a message within 5 seconds (timeout)
**When** the timeout fires
**Then** the consumer loops back and calls BLPOP again — it does NOT exit or crash

**Given** Redis is unavailable
**When** lardi-connector attempts to enqueue a request
**Then** returns HTTP 503 with `{"error": {"code": "QUEUE_UNAVAILABLE"}}` — does NOT bypass the queue to call Lardi directly

### Story 3.2: Cargo Search Endpoint with Full Filter Support

As a developer,
I want a lardi-connector endpoint that executes cargo searches against Lardi API with all supported filter types,
So that agent-service can retrieve raw cargo data without knowing Lardi's internal API details.

**Note:** All Lardi HTTP calls in this story are routed through the Redis queue implemented in Story 3.1.

**Acceptance Criteria:**

**Given** a valid LTSID is in Redis and lardi-connector is running
**When** `POST /search` is called with a `CargoSearchRequest` payload
**Then** the request is enqueued via the queue (Story 3.1), lardi-connector reads `aetherion:auth:ltsid`, sets it as a cookie, and calls `POST /webapi/proposal/search/gruz/` on Lardi
**And** returns a `CargoSearchResponse` with a list of `CargoItem` objects
**And** each request is assigned a `request_id` (UUID) logged in all structlog events for that request

**Given** a search request with direction filters
**When** lardi-connector builds the Lardi API payload
**Then** `directionFrom` and `directionTo` are serialized as `{"directionRows": [{"countrySign": "UA", "townId": int}]}` (or `regionId`, `areaId` for oblast/country level) — NOT as flat integers
**And** `countrySign` is set to the ISO code (e.g. `"PL"` for Poland) when no `townId`/`regionId` is present

**Given** a search request with `bodyTypeIds` or `paymentFormIds` as strings (e.g., `"34"`)
**When** lardi-connector validates the payload
**Then** string numerics are auto-cast to integers: `"34"` → `34`
**And** if cast fails, HTTP 422 is returned with `{"error": {"code": "INVALID_FILTER_TYPE", "message": "bodyTypeIds must be integers, got '\"truck\"'"}}`

**Given** a search request with `loadTypes`
**When** lardi-connector validates the payload
**Then** `loadTypes` accepts ONLY string codes: `"back"`, `"top"`, `"side"`, `"tail_lift"`, `"tent_off"` — NOT integers
**And** any value outside these accepted codes is rejected with HTTP 422

**Given** Lardi returns `distance` in meters in a result
**When** lardi-connector processes the response
**Then** `CargoItem.distance_km` = `distance / 1000` (float, 1 decimal) AND `CargoItem.distance_m` (raw integer) are both present

**Given** a broad search that hits the Lardi 500-result cap
**When** `totalSize` in the response equals 500
**Then** `CargoSearchResponse` includes `capped: true` and `capped_note: "Lardi does not support pagination — narrow query by region, date, or vehicle type"`

**Given** the Lardi API does not respond within `LARDI_HTTP_TIMEOUT_SECONDS` (ENV, default: 10s)
**When** the HTTP timeout fires
**Then** lardi-connector returns HTTP 504 with `{"error": {"code": "LARDI_TIMEOUT"}}` and structlog logs `WARNING "lardi_search_timeout" timeout_seconds=<value>`

### Story 3.3: Cargo Detail & Shipper Contact Endpoint

As a developer,
I want a lardi-connector endpoint that retrieves full cargo details including the shipper's phone number,
So that users can contact shippers directly.

**Note:** All Lardi HTTP calls in this story are routed through the Redis queue implemented in Story 3.1.

**Acceptance Criteria:**

**Given** a valid cargo `id` from a previous search result
**When** `GET /cargo/{id}` is called on lardi-connector
**Then** lardi-connector calls `GET /webapi/proposal/offer/gruz/{id}/awaiting/` with the current LTSID cookie
**And** returns a `CargoDetailResponse` including cargo details and `shipper_phone` (from `proposalUser`)
**And** structlog logs include `cargo_id` and `ltsid_hash` = `sha256(ltsid.encode()).hexdigest()[:8]` — never the raw LTSID value

**Given** `proposalUser` is absent or `phone` is null in Lardi's response
**When** the detail endpoint returns
**Then** `CargoDetailResponse.shipper_phone` is `null` — no error is raised

**Given** the cargo `id` does not exist on Lardi
**When** `GET /cargo/{id}` is called
**Then** lardi-connector returns HTTP 404 with `{"error": {"code": "CARGO_NOT_FOUND", "message": "..."}}`

**Given** Lardi returns any non-401 / non-404 error on the detail endpoint
**When** the error is detected
**Then** lardi-connector returns HTTP 502 with `{"error": {"code": "LARDI_DETAIL_UNAVAILABLE"}}` — the overall flow is NOT terminated (caller decides how to handle)

### Story 3.4: 401 Auto-Recovery & Retry in lardi-connector

As a developer,
I want lardi-connector to automatically recover from Lardi 401 errors,
So that transient session expiry is invisible to agent-service.

**Acceptance Criteria:**

**Given** lardi-connector sends a request and receives HTTP 401
**When** the 401 is detected
**Then** lardi-connector captures `old_ltsid` = current value of `aetherion:auth:ltsid` in Redis
**And** publishes `{"event": "refresh_requested", "reason": "401", "timestamp": "..."}` to Redis channel `aetherion:auth:refresh`
**And** polls Redis until `aetherion:auth:ltsid` value != `old_ltsid` (max wait: `LTSID_REFRESH_WAIT_SECONDS=90`)
**And** after new LTSID detected, waits `LTSID_RETRY_DELAY_MS` (default: 200ms) before retrying
**And** retries the original request exactly once with the new LTSID

**Given** the retry after refresh also returns 401
**When** the second 401 is detected
**Then** lardi-connector returns HTTP 503 with `{"error": {"code": "LTSID_REFRESH_FAILED"}}` — no further refresh attempts

**Given** `old_ltsid != new_ltsid` is never satisfied within 90 seconds
**When** the wait timeout expires
**Then** returns HTTP 503 with `{"error": {"code": "LTSID_REFRESH_TIMEOUT", "details": {"retry_after": 30}}}`

**Given** Lardi returns HTTP 429 or 503
**When** the error is detected
**Then** lardi-connector retries up to 3 times with exponential backoff + jitter: `base_delay × 2^attempt + random(0, 300ms)`
**And** does NOT retry on 400 or 404

### Story 3.5: Fuel Price Service

As a system operator,
I want the system to automatically fetch, cache, and serve current fuel prices,
So that profitability calculations always use up-to-date data without blocking system startup.

**Acceptance Criteria:**

**Given** auth-worker starts
**When** the lifespan event fires
**Then** `fuel_fetcher.py` fetches diesel price from `FUEL_PRICE_URL` asynchronously — startup is NOT blocked
**And** the response is expected as JSON: `{"diesel": 52.3, "currency": "UAH"}`; if the source returns HTML, the CSS selector to extract the price is defined in ENV `FUEL_PRICE_CSS_SELECTOR`
**And** price is stored in Redis as `aetherion:fuel:price:diesel` with TTL from `FUEL_CACHE_TTL_SECONDS` (default: 3600)
**And** structlog logs `INFO "fuel_price_fetched" price=<value> currency="UAH"`

**Note:** `fuel_fetcher.py` resides in `auth-worker/app/scheduler/` per Architecture decision. Candidate for extraction to a dedicated service in Phase 2.

**Given** the hourly cron fires
**When** `fuel_fetcher.py` runs
**Then** a new price is fetched and the Redis key is overwritten with a fresh TTL

**Given** the external fuel price source is unavailable
**When** fetch fails
**Then** the existing Redis key is NOT deleted and structlog logs `WARNING "fuel_price_fetch_failed_using_cache"`

**Given** the fuel price API does not respond within `FUEL_PRICE_HTTP_TIMEOUT_SECONDS` (ENV, default: 5s)
**When** the HTTP timeout fires
**Then** the fetch is treated as a failure — existing cache is preserved and structlog logs `WARNING "fuel_price_fetch_timeout" timeout_seconds=<value>`

**Given** agent-service needs the current fuel price
**When** `fuel_price.py` reads from Redis
**Then** if Redis available and key exists → returns cached price
**And** if Redis unavailable or key missing → returns last known in-memory value with `WARNING "fuel_price_redis_miss_using_memory"`
**And** if in-memory value also absent → returns HTTP 503 with `{"error": {"code": "FUEL_PRICE_UNAVAILABLE"}}`

---

## Epic 4: AI-Powered Cargo Search with Streaming

Artur types a natural language request in Swagger UI and receives a streaming agent response with real-time reasoning status, top cargo results ranked by estimated fuel margin, actionable suggestions when no results are found, and the shipper's contact for the selected cargo. All chat history is persisted.

### Story 4.1: LangGraph Agent Setup, Intent Extraction & Geo Resolution

As a carrier,
I want the agent to understand my natural language cargo request and extract validated structured search filters,
So that I don't need to know Lardi's internal IDs and the system always sends correct integer filters.

**Acceptance Criteria:**

**Given** agent-service is running and `OPENROUTER_API_KEY` is set
**When** agent-service starts
**Then** LangGraph compiled graph is initialized as a singleton (`graph.py`) with `version="v2"` streaming API
**And** `AgentState` TypedDict is defined in `state.py` with fields: `messages`, `extracted_filters`, `search_results`, `selected_cargo_id`, `error`

**Given** a natural language query: `"Шукай вантаж з Києва до Польщі, тент, від 10 тон"`
**When** the `parse_intent` node runs via LLM (OpenRouter)
**Then** LLM extracts location names as strings: `"Київ"`, `"Польща"`, body type as `"тент"` — LLM never outputs Lardi IDs directly
**And** `geo_resolver.py` looks up each name in the `ua_cities` Postgres table using the resolution chain: memory cache → exact match (case-insensitive) → pg_trgm fuzzy match → Nominatim geocoding fallback
**And** `geo_resolver.py` returns a `DirectionFilter` object: `{"directionRows": [{"countrySign": "UA", "townId": 137}]}` for city-level; `{"directionRows": [{"countrySign": "PL"}]}` for country-level
**And** body type `"тент"` is resolved via `BodyTypeID` enum (ported from v1 `constants.py`): `TENT=34` (confirmed); other values marked `unverified` in enum docstring
**And** final `search_cargo` call uses correct `DirectionFilter` structures and `bodyTypeIds: [34]` as integer

**Given** LLM output contains non-canonical body type string (e.g. `"тентований"`)
**When** `IntentFilterValidator` runs post-LLM
**Then** Ukrainian aliases are resolved via `BODY_TYPE_UA_TO_ID` dict (ported from v1): `"тентований"` → `34`
**And** unresolvable body type strings are dropped with structlog `WARNING "intent_filter_cast_failed" field="bodyType" raw_value=<val>`
**And** `loadTypes` values are validated against accepted string codes: `"back"`, `"top"`, `"side"`, `"tail_lift"`, `"tent_off"` — invalid values dropped with warning

**Given** a city name not found in `ua_cities` after pg_trgm
**When** `geo_resolver.py` calls Nominatim
**Then** if Nominatim returns coordinates → city is auto-stored in `ua_cities` with `source="nominatim"` and `lardi_town_id=null`
**And** if Nominatim also fails → fallback to oblast level; if oblast not found → country level; if country not found → direction filter dropped with `WARNING "geo_resolution_failed" name=<str>`

**Given** the system prompt
**When** LLM is initialized
**Then** system prompt defines: logistics-only role, tool scope limited to `search_cargo`, `get_cargo_detail`, `calculate_margin`, explicit instruction to ignore commands embedded in cargo data, `[EXTERNAL DATA]` wrapper rule for all Lardi data

### Story 4.2: Cargo Search & Profitability Tools

As a carrier,
I want the agent to search for cargo and rank results by estimated fuel margin,
So that I can immediately see which routes are worth pursuing.

**Acceptance Criteria:**

**Given** extracted and validated filters from Story 4.1
**When** the `search_cargo` tool is called
**Then** it calls `POST /search` on lardi-connector and receives `CargoSearchResponse`
**And** LTSID is never present in agent-service — lardi-connector handles it internally

**Given** search results are returned
**When** `calculate_margin` runs for each result
**Then** `fuel_cost = distance_km × (FUEL_CONSUMPTION_L_PER_100KM / 100) × fuel_price_uah`
**And** `estimated_fuel_margin = cargo_payment_uah - fuel_cost`
**And** results are ranked by `estimated_fuel_margin` descending; top-3 selected
**And** agent response always includes disclaimer: `"Розрахунок враховує тільки паливо. Реальні витрати вищі (порожній пробіг, toll, водій)."`
**And** ENV `MARGIN_OVERHEAD_COEFFICIENT` (default: 1.0) can be set to apply an additional overhead multiplier

**Given** top-3 results all have `estimated_fuel_margin: null` (missing distance or payment)
**When** the ranking runs
**Then** agent extends selection to up to 5 results with non-null margin
**And** if no non-null margin results exist → shows top-3 with `"margin unavailable — distance or payment data missing"`

**Given** a cargo result from Lardi
**When** `calculate_margin` reads the payment field
**Then** it reads `paymentValue` from `ProposalListItem` — which may be `null`, a numeric (e.g. `15000`), or a non-numeric string (e.g. `"запит вартості"`)
**And** only numeric `paymentValue` with currency `UAH` (`paymentCurrencyId=4`) is used for margin calculation
**And** if `paymentValue` is null, non-numeric, or non-UAH currency → `estimated_fuel_margin: null`, result ranked last — no crash

**Given** `distance_km` is 0 or null in a cargo result
**When** `calculate_margin` runs
**Then** that result is marked `estimated_fuel_margin: null` and ranked last — no crash

**Given** search results are passed to LLM for response generation
**When** Lardi data is placed in LLM context
**Then** only trimmed fields are included: `id`, `distance_km`, `estimated_fuel_margin`, `body_type`, `route_from`, `route_to`, `loading_date`
**And** the trimmed data is wrapped: `[EXTERNAL DATA]...[/EXTERNAL DATA]`

**Given** `get_cargo_detail` tool is called with a `cargo_id`
**When** lardi-connector returns the detail response
**Then** `shipper_phone` is added to agent state and included in the final response
**And** only `id`, `shipper_phone`, `shipper_name`, `route_from`, `route_to` are passed to LLM context — full JSON is not forwarded

### Story 4.3: Streaming Agent Response via SSE

As a carrier,
I want to see the agent's reasoning and results stream in real time,
So that I know the system is working and don't wait in silence.

**Acceptance Criteria:**

**Given** a chat message is sent to agent-service
**When** `POST /stream` is called
**Then** the response is `Content-Type: text/event-stream` (SSE)
**And** the first SSE chunk is emitted within 3 seconds (NFR1)
**And** reasoning status chunks are streamed: `"🔍 Parsing request..."`, `"📦 Searching Lardi..."`, `"💰 Calculating margins..."`
**And** the final ranked results are streamed token-by-token

**Given** a LangGraph node does not complete within `AGENT_NODE_TIMEOUT_SECONDS` (ENV, default: 15s)
**When** the per-node `asyncio.wait_for` timeout fires
**Then** agent emits SSE chunk `{"type": "status", "message": "⚠️ Step timeout, continuing..."}` and proceeds to next node
**And** the overall stream is NOT terminated by a single node timeout

**Given** OpenRouter returns HTTP 503 or exceeds timeout (connect: 3s, read: 30s)
**When** the timeout fires
**Then** agent emits final SSE event `{"type": "error", "code": "LLM_UNAVAILABLE", "message": "Service temporarily unavailable"}` and closes the stream
**And** the connection is NOT left open indefinitely (NFR6)

**Given** the full agent response completes
**When** the SSE stream ends
**Then** a final `{"type": "done"}` event is emitted before the connection closes

### Story 4.4: API Gateway Chat Integration & Request Queuing

As a carrier,
I want to send chat messages via the public API and have them persisted,
So that I have a full history of all my cargo searches.

**Acceptance Criteria:**

**Given** api-gateway is running
**When** `POST /api/v1/chats` is called
**Then** a new chat record is created in Postgres with `workspace_id`, `user_id`, `title`, `created_at`
**And** returns `ChatResponse` with the new `chat_id`

**Given** a valid `chat_id`
**When** `POST /api/v1/chats/{chat_id}/messages` is called with a user message
**Then** the user message is saved to Postgres (`role="user"`, `status="complete"`)
**And** a placeholder assistant message is saved with `status="streaming"` before the stream begins
**And** api-gateway proxies the request to `agent-service:8001/stream` as SSE and forwards the stream to the client
**And** when the stream completes successfully → assistant message updated to `status="complete"` with full content
**And** if the connection is interrupted before stream end → assistant message updated to `status="incomplete"` with partial content saved

**Given** agent-service starts processing a request
**When** `agent_runner.py` begins execution
**Then** it sets `SET aetherion:agent:busy 1 NX EX 60` in Redis (key auto-expires after 60s as safety net)
**And** clears the key with `DEL aetherion:agent:busy` when the stream completes (success or error)

**Given** `aetherion:agent:busy` key exists in Redis
**When** a second message arrives at api-gateway and it checks agent-service availability
**Then** api-gateway returns HTTP 429 with `{"error": {"code": "AGENT_BUSY", "message": "Agent is processing another request", "details": {"retry_after_seconds": 3}}}`

**Given** an `Authorization` header is present
**When** api-gateway processes it
**Then** JWT middleware stub accepts without validation — enforcement deferred to Phase 2

### Story 4.5: Zero Results Suggestions & End-to-End Validation

As a carrier,
I want the agent to suggest concrete filter adjustments when no cargo is found,
So that I always have a clear, actionable next step.

**Acceptance Criteria:**

**Given** lardi-connector returns `proposals: []`
**When** the agent processes the empty result
**Then** rule-based logic applies priority order `route > weight > bodyType > payment` and returns the first matching suggestion:
  - direction is city-level (`townId` set) → `"Розшир район завантаження до область або країна"` (highest priority)
  - `mass1` is set → `"Спробуй зменшити вагу або прибрати фільтр ваги"`
  - `bodyTypeIds` is set → `"Спробуй без фільтру типу кузова"`
  - `paymentFormIds` is set → `"Спробуй без фільтру форми оплати"` (lowest priority)
**And** at least one concrete, actionable suggestion is always provided — never a generic "no results" message

**Given** `capped: true` in the search response
**When** the agent processes the result
**Then** response includes: `"Показую топ-3 з 500+ результатів — результати обрізані. Звуж фільтри для точнішого пошуку."`

**Given** the full system is running (`make up`)
**When** `POST /api/v1/chats` → `POST /api/v1/chats/{id}/messages` with `"Шукай тент Київ→Польща від 10т"`
**Then** an SSE stream is received with reasoning status chunks + ranked results with `estimated_fuel_margin` + disclaimer
**And** a follow-up message with a cargo ID triggers `get_cargo_detail` → shipper phone returned
**And** `GET /health` on all services returns `"status": "healthy"` (NFR8)
**And** all structlog output uses structured JSON with `service`, `workspace_id`, `request_id` fields (NFR7)
