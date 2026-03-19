---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-12-complete']
status: complete
completedAt: '2026-03-17'
inputDocuments:
  - '_bmad-output/planning-artifacts/brainstorming/brainstorming-session-2026-03-15-0130.md'
  - '_bmad-output/brainstorming/brainstorming-session-2026-03-15-0001.md'
  - 'docs/lardi_trans_api_reference.md'
workflowType: 'prd'
documentCounts:
  briefs: 0
  research: 0
  brainstorming: 2
  projectDocs: 1
classification:
  projectType: saas_b2b
  domain: logistics_freight
  complexity: medium
  projectContext: brownfield
---

# Product Requirements Document - Aetherion 2.0

**Author:** Artur
**Date:** 2026-03-17

## Executive Summary

Aetherion 2.0 — AI-агент для вантажоперевізників, що автоматизує пошук і оцінку вантажів на біржі Lardi-Trans. Цільова аудиторія — перевізники (водії та невеликі транспортні компанії), які шукають вигідні рейси напряму, без посередників-логістів.

Ключова проблема: ручний пошук на Lardi-Trans — повільний і виснажливий. Логісти-посередники перехоплюють найкращі вантажі та беруть комісію з обох сторін. Контакти замовників є платними. Aetherion вирішує всі три проблеми одночасно.

### What Makes This Special

**1. Bypass paywall для контактів.** Lardi-Trans приховує телефон замовника за платним бар'єром. Aetherion отримує ці дані через reverse-engineered API — безкоштовно.

**2. AI замість ручного пошуку.** Перевізник описує потребу природною мовою — агент шукає, фільтрує, ранжує за вигідністю та стрімить хід думок у реальному часі. Фоновий моніторинг слідкує за ринком без участі користувача.

**3. Фінансовий скринінг.** Агент розраховує витрати на пальне та маржинальність рейсу — перевізник бачить не список вантажів, а конкретну вигідність кожного рейсу.

**Мета:** частково замінити логіста-посередника; перевізнику залишається прийняти рішення і зателефонувати.

## Project Classification

- **Тип:** SaaS B2B (веб-портал, workspace, командні ролі)
- **Домен:** Logistics / Freight Exchange
- **Складність:** Medium — без регуляторних вимог; технічна складність: Cloudflare bypass, reverse-engineered API, мікросервісна архітектура
- **Контекст:** Brownfield — rebuild з нуля після v1; уроки v1 задокументовано в brainstorming

## Success Criteria

### User Success

- Агент коректно транслює природномовний запит у фільтри Lardi API (маршрут, тип авто, вага, дати)
- Повернуті вантажі відповідають параметрам запиту — якість матчингу пріоритетніша за швидкість
- Розрахунок витрат на пальне та маржинальності рейсу є коректним і відтворюваним
- Контакти замовника отримуються через detail endpoint для обраного вантажу
- Агент стрімить статус обробки — користувач бачить прогрес, а не чекає мовчки

### Business Success

- Система придатна для щоденного внутрішнього використання
- Lardi-сесія стабільна — відсутність несподіваних auth-падінь
- Архітектура розширювана без переписування ядра

### Technical Success

- Мікросервісна архітектура: `agent-service`, `auth-worker`, `lardi-connector`, `redis`, `postgres`, `api-gateway`
- `auth-worker` отримує і оновлює `LTSID` cookie через undetected-chromedriver
- Redis: session storage, global Lardi request queue, fuel price cache, message broker
- Rate limiting перед кожним запитом до Lardi — захист від бану
- Всі Lardi-фільтри використовують integer ID (не string коди як у v1)

### Measurable Outcomes

- Агент коректно обробляє ≥5 типів пошукових запитів: місто→місто, країна→країна, фільтр по типу авто, по вазі, комбіновані
- Розрахунок маржі коректний при відомій відстані (метри → км) і актуальній ціні пального
- Жодних silent failures — всі помилки (401, LLM timeout, CF block) повертають явне повідомлення

## User Journeys

### Journey 1: Перевізник шукає вантаж (Happy Path)

**Персонаж:** Артур — перевізник і власник системи.

**Ситуація:** Вантажівка-тент у Києві, шукає вантаж до Польщі. Відкриває Swagger UI.

**Крок 1 — Запит:** POST до `api-gateway`: *"Шукай вантаж з Києва до Польщі, тент, від 10 тон"*

**Крок 2 — Стрімінг:** Агент одразу повертає статус: *"🔍 Розбираю запит... → Шукаю вантажі Київ→PL, тент, ≥10т..."*

**Крок 3 — Intent Extraction:** `agent-service` витягує: `directionFrom: townId:137`, `directionTo: PL`, `bodyTypeIds:[34]`, `mass1:10`

**Крок 4 — Пошук:** `lardi-connector` → POST `/webapi/proposal/search/gruz/` → список вантажів

**Крок 5 — Ранжування:** Агент розраховує маржу (відстань × витрата × ціна пального), стрімить топ-3 з поясненням

**Крок 6 — Деталі:** Артур обирає вантаж → `get_cargo_detail` → телефон замовника

**Результат:** Один API-запит — відфільтрований список із маржою і контактом. Без ручного гортання Lardi.

---

### Journey 2: Auth Failure — Автовідновлення (Edge Case)

**Ситуація:** LTSID протух. Артур надсилає запит.

**Крок 1:** `lardi-connector` → Lardi повертає 401

**Крок 2:** Агент стрімить: *"Зачекайте, оновлюю авторизацію..."* → `auth-worker` отримує новий LTSID

**Крок 3:** Повторює оригінальний запит → стрімить результат

**Результат:** Автовідновлення без втрати контексту. Жодного silent failure.

---

### Journey 3: Нульовий результат — Actionable Suggestion (Edge Case)

**Ситуація:** Дуже вузькі параметри — нічого не знайдено.

**Крок 1:** `proposals: []`

**Крок 2:** Агент аналізує фільтри → виявляє жорсткі обмеження

**Крок 3:** *"Вантажів не знайдено. Спробуй: прибрати обмеження по вазі або розширити район завантаження до Київської обл."*

**Результат:** Конкретний наступний крок замість порожньої відповіді.

---

### Journey 4: Admin/Ops — Перевірка системи

**Персонаж:** Артур як оператор перед початком роботи.

**Крок 1:** GET `/health` → redis ✓, postgres ✓, auth-worker ✓, lardi-connector ✓

**Крок 2:** Перевіряє timestamp останнього оновлення LTSID

**Крок 3:** За потреби — `POST /admin/cookie` для ручного оновлення сесії

**Результат:** Повна видимість стану без заходу в Docker контейнери.

---

### Journey Requirements Summary

| Journey | Розкриті вимоги |
|---|---|
| Happy Path | Intent extraction, geo resolution, cargo search, streaming, margin calc, detail endpoint |
| Auth Failure | 401 detection, auth-worker trigger, streaming status, auto-retry |
| Zero Results | Empty state handling, filter analysis, suggestion generation |
| Admin/Ops | Health endpoint, session status, manual cookie refresh |

## Domain-Specific Requirements

### Технічні обмеження Lardi-Trans API

- **Cloudflare Bot Management** — прямий HTTP login заблоковано; LTSID отримується виключно через реальний браузер в `auth-worker`
- **Result cap at 500** — `totalSize` обрізається на 500; при широких фільтрах потрібна стратегія звуження або пагінація
- **Integer-only filter IDs** — `bodyTypeIds`, `loadTypes`, `paymentFormIds` приймають тільки integer ID; string-значення ігноруються сервером без помилки (критичний баг v1)
- **Two-step contact retrieval** — `proposalUser` відсутній в search results; телефон доступний тільки через `GET /webapi/proposal/offer/gruz/{id}/awaiting/`
- **Distance in meters** — поле `distance` повертає метри; ділення на 1000 обов'язкове для всіх розрахунків

### Ризики та Мітигації

- **IP/Account ban** — глобальна Redis Queue (по одному запиту до Lardi), rate limiting перед кожним викликом
- **Session expiry mid-request** — при 401: атомарний auto-refresh через `auth-worker`, retry без втрати контексту
- **Session limit** — при запуску перевірка `/webapi/check-auth/`; єдина активна сесія в Redis з TTL

## Innovation & Novel Patterns

### Detected Innovation Areas

**1. AI Agent як заміна логіста-посередника**
Агент виконує роль людини-логіста: розуміє природномовний запит, транслює в API-фільтри, шукає, ранжує за вигідністю, надає контакт. Workflow automation на рівні конкретної професії.

**2. Структурний bypass платного paywall**
Lardi-Trans монетизує контакти замовника. Aetherion отримує ті самі дані через reverse-engineered detail endpoint — безкоштовно. Структурна перевага вбудована в архітектуру.

**3. Cargo Search як фінансовий скринінг**
Стандартні пошуковики показують список. Aetherion показує маржинальність: відстань × витрата пального × ціна = чистий прибуток рейсу. Зміна парадигми з "що є" на "що вигідно".

### Validation Approach

- Intent extraction: тестові запити різних форматів → порівняння витягнутих фільтрів з очікуваними
- Margin calculation: відомі маршрути з відомою відстанню → верифікація формули
- Contact retrieval: пошук реального вантажу → detail endpoint → наявність телефону

### Risk Mitigation

- Lardi може змінити API без попередження — критичні endpoint'и покриті інтеграційними тестами
- Lardi-специфіка ізольована в `lardi-connector` — зміни не поширюються на ядро

## SaaS B2B Specific Requirements

### Architecture Foundation

**Auth (MVP без enforcement):**
- `api-gateway` містить заглушку JWT middleware — активується конфігурацією, не видаляється
- Endpoint'и приймають опціональний `Authorization` header (ігнорується в MVP)
- Таблиця `users` присутня в схемі з першого дня

**Tenant Model:**
- MVP: single-tenant, один Lardi акаунт, один користувач
- Postgres schema: `workspace_id` у всіх релевантних таблицях для майбутнього multi-tenant

### Integration List

| Сервіс | Тип | Призначення |
|---|---|---|
| Lardi-Trans API | Reverse-engineered REST | Пошук вантажів, деталі, контакти |
| OpenRouter | LLM API | Intent extraction, reasoning, streaming відповіді |
| undetected-chromedriver | Browser automation | Отримання LTSID cookie |
| Fuel Price API | Public REST (ОККО, БРСМ або держ. джерело) | Актуальні ціни пального |

**Fuel Price стратегія:** зберігається в Redis; оновлення при старті + cron раз на годину; fallback на останнє збережене при недоступності джерела.

### Permission Matrix

| Роль | Доступ |
|---|---|
| owner (MVP) | Повний доступ до всіх endpoint'ів |
| *(future)* user | Обмежений доступ до свого workspace |
| *(future)* admin | Управління users, перегляд логів |

### Implementation Notes

- Swagger UI на `/docs` без авторизації в MVP
- `docker-compose up` — повний запуск одною командою
- `/health` — статус всіх залежностей
- ENV-based конфігурація для всіх секретів

## Project Scoping & Phased Development

### MVP Strategy

**Підхід:** Problem-solving MVP — повністю функціональний backend без UI. Взаємодія через Swagger UI та pytest. Один розробник, без фіксованих дедлайнів.

### Phase 1 — MVP

- `lardi-connector`: пошук (всі фільтри), detail endpoint з контактами
- `agent-service`: intent extraction, cargo ranking за маржинальністю, fuel cost calculation, streaming thinking + response
- `auth-worker`: auto LTSID refresh через undetected-chromedriver
- `api-gateway`: FastAPI + Swagger, `/health`, `POST /admin/cookie`
- `redis`: session, global Lardi queue, fuel price cache, message broker
- `postgres`: users, workspaces, chats, messages з `workspace_id`
- Fuel price cron: старт + раз на годину, fallback на кеш
- Docker Compose: повний запуск одною командою

### Phase 2 — Growth (UI + Monitoring)

- Веб-портал: Three-panel UI (чат + таблиця вантажів + cargo detail popup з контактами)
- Per-chat filter profile: кожен чат зберігає профіль параметрів (тип авто, витрата пального, улюблені маршрути)
- Cargo Alert Profiles — cron моніторинг за збереженими профілями
- Agent-controlled cargo watch: `create_cargo_watch(params, interval)` через природну мову в чаті; інтервал керується динамічно (в майбутньому — слайдер в UI)
- Proactive Morning Agent — агент ініціює розмову при нових вигідних вантажах
- Telegram як notification channel

### Phase 3 — Expansion

- Plugin архітектура для інших вантажних бірж (Lardi = перший коннектор); при недоступності одного — агент перемикається на інший автоматично
- Team workspace з ролями та запрошеннями
- Account pool для Cloudflare fallback
- Cargo Freshness Tracking через Centrifuge WebSocket

### Risk Mitigation

| Ризик | Мітигація |
|---|---|
| Cloudflare / auth-worker збій | `POST /admin/cookie` — ручне оновлення LTSID без зупинки системи |
| API нестабільність Lardi | Lardi-специфіка ізольована в `lardi-connector`; зміна = один сервіс |
| Multi-connector failover (Phase 3+) | При недоступності коннектора — пошук через решту; система не падає |

## Functional Requirements

### Cargo Search

- **FR1:** User can search for cargo using natural language describing route, vehicle type, weight, and dates
- **FR2:** Agent can extract structured Lardi search filters from natural language input
- **FR3:** Agent can resolve city names to Lardi geo IDs for use in search requests
- **FR4:** User can search cargo by country-level, oblast-level, and city-level directions
- **FR5:** Agent can filter cargo by vehicle body type using correct integer IDs
- **FR6:** Agent can filter cargo by weight, volume, loading type, and date range
- **FR7:** Agent can retrieve paginated search results and present the most relevant matches

### Cargo Profitability Analysis

- **FR8:** Agent can calculate estimated fuel cost for a cargo route based on distance and current fuel price
- **FR9:** Agent can calculate trip margin (cargo payment minus fuel cost)
- **FR10:** Agent can rank search results by profitability and present top matches with a brief explanation
- **FR11:** Agent can suggest specific filter adjustments when search returns zero results

### Cargo Details & Contacts

- **FR12:** Agent can retrieve full cargo offer details including shipper contact phone number
- **FR13:** User can request contact details for a specific cargo from search results

### Agent Interaction & Streaming

- **FR14:** Agent can stream reasoning status messages to the user during request processing
- **FR15:** Agent can stream the final response token-by-token rather than returning a single completed response
- **FR16:** System can queue incoming user requests when the agent is already processing, preventing concurrent execution

### Session & Authentication Management

- **FR17:** System can obtain a valid Lardi session cookie via browser-based login
- **FR18:** System can detect an expired Lardi session and automatically trigger cookie refresh
- **FR19:** System can retry a failed Lardi request after successful session refresh
- **FR20:** Admin can manually set a Lardi session cookie via a protected admin endpoint

### Fuel Price Management

- **FR21:** System can fetch current fuel prices from an external public source
- **FR22:** System can update stored fuel price on startup and on an hourly schedule
- **FR23:** System can fall back to the last stored fuel price when the external source is unavailable

### System Operations & Health

- **FR24:** Admin can check the health status of all system services via a single endpoint
- **FR25:** Admin can trigger a manual Lardi session refresh without restarting the system
- **FR26:** System can queue Lardi API requests globally to prevent concurrent calls and rate-limit violations
- **FR27:** User can interact with the agent via HTTP API through Swagger UI

### Data Persistence

- **FR28:** System can persist chat history per conversation session
- **FR29:** System can store and retrieve user and workspace records with multi-tenant-ready schema
- **FR30:** System can store Lardi session data in Redis with TTL-based expiry

## Non-Functional Requirements

### Performance

- Відповідь агента — не більше 15 секунд за нормальних умов (Lardi latency + LLM reasoning); перший streaming chunk — не більше 3 секунд
- Не більше 1 паралельного запиту до Lardi через глобальну Redis Queue
- Fuel price fetch при старті не блокує запуск (виконується асинхронно)

### Reliability

- При 401 від Lardi система автоматично відновлюється без втрати запиту
- При недоступності fuel price API — система продовжує роботу з останнім кешованим значенням
- При LLM timeout/503 — агент повертає явне повідомлення протягом 30 секунд; не залишає з'єднання відкритим безкінечно
- Всі помилки логуються з достатнім контекстом для дебагу
- `/health` коректно відображає статус кожного залежного сервісу

### Security

- Lardi credentials та OpenRouter API key — виключно в ENV, не логуються, не передаються в LLM контекст
- LTSID cookie ізольований в `auth-worker` та `lardi-connector` — LLM не має до нього доступу
- Admin endpoint `POST /admin/cookie` захищений (базова авторизація або IP restriction в MVP)
- **Prompt Injection Defense (три шари):**
  - Tool scope: агент має доступ тільки до cargo-related інструментів (`search_cargo`, `get_cargo_detail`, `calculate_margin`)
  - Data isolation: дані з Lardi обгортаються як `[EXTERNAL DATA]` перед передачею в LLM
  - System prompt hardening: чіткий role definition з явною забороною виходити за межі логістики

### Integration

- `lardi-connector` ізолює всю Lardi-специфіку — зміна API потребує змін лише в одному сервісі
- Всі зовнішні HTTP виклики (Lardi, OpenRouter, fuel price API) мають явний timeout
- Docker Compose запускає сервіси в правильному порядку з health check залежностями

### Maintainability

- Кожен сервіс має єдину зону відповідальності (single responsibility)
- Жодних hardcoded значень — виключно ENV-based конфігурація
- Postgres schema містить `workspace_id` і `user_id` у всіх релевантних таблицях з першого дня
