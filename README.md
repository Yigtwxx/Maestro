<div align="center">

# Maestro

**Self-hostable AI agent orchestration platform. Bring your own LLM keys (BYOK).**

Route a single prompt through a multi-layer agent hierarchy — Orchestrator, Main Agent,
Subagents, and an optional Reviewer — with live streaming, per-user RAG memory, and a
community Marketplace for sharing agent teams.

[![CI](https://github.com/Yigtwxx/maestro/actions/workflows/ci.yml/badge.svg)](https://github.com/Yigtwxx/maestro/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=nextdotjs)](https://nextjs.org)

[Overview](#overview) · [Architecture](#architecture) · [Getting Started](#getting-started) · [Configuration](#configuration) · [API Reference](#api-reference) · [Security](#security) · [Deployment](#deployment) · [Roadmap](#roadmap)

</div>

---

## Overview

Maestro is a public, general-purpose platform for orchestrating teams of AI agents. A
user enters one prompt; an Orchestrator classifies the task and routes it to a domain
Main Agent, which decomposes the work into atomic subtasks, dispatches Subagents, and —
optionally — runs the results past a Reviewer before returning a synthesized answer. The
entire run is streamed to the client over WebSocket, and agents can pause to ask the user
a clarifying question mid-task (human-in-the-loop).

The platform is **bring-your-own-key**: users connect their own OpenAI, Anthropic, or
Google Gemini credentials, encrypted at rest with AES-256-GCM. It also runs with **no
paid key at all** — Gemini offers a free tier (no credit card required at
[aistudio.google.com/apikey](https://aistudio.google.com/apikey)), and tasks fall back to
**Qwen3.5 via a local Ollama endpoint** when a quota is exhausted or no key is connected.
Embeddings for RAG are generated locally with `nomic-embed-text`, so the full pipeline can
run offline and free.

Architecture, conventions, and code standards live in a single source of truth:
[`CLAUDE.md`](./CLAUDE.md). The original product specification is in
[`project-docs.md`](./project-docs.md).

## How It Works

1. The user submits a single prompt.
2. The **Orchestrator** analyzes the task and routes it to the appropriate domain expert.
3. The **Main Agent** breaks the task into subtasks and dispatches Subagents.
4. **Subagents** execute their atomic tasks, each with access to a bounded tool set.
5. An optional **Reviewer** audits each output and returns errors with retry hints,
   bounded by `MAX_REVIEW_ITERATIONS`.
6. The result is streamed to the client over WebSocket, including any clarifying question
   the Main Agent needs to ask the user before continuing.

## Architecture

### Agent Hierarchy

The Orchestrator only routes — it never produces work product. The Main Agent plans and
coordinates. Each Subagent performs exactly one atomic task. The Reviewer (toggle:
`reviewer_enabled`) validates outputs and bounces errors back, bounded by
`MAX_REVIEW_ITERATIONS`.

```mermaid
flowchart TD
    U(["User Prompt"]) --> O["Orchestrator<br/><i>routes the task to the right domain</i>"]
    O --> M["Main Agent<br/><i>domain expert — plans subtasks</i>"]
    M --> S1["Subagent<br/><i>data fetching</i>"]
    M --> S2["Subagent<br/><i>analysis</i>"]
    M --> S3["Subagent<br/><i>reporting</i>"]
    S1 --> R{"Reviewer<br/><i>optional</i>"}
    S2 --> R
    S3 --> R
    R -- "issues + retry hints<br/>(MAX_REVIEW_ITERATIONS)" --> M
    R -- "approved" --> OUT(["Result — WebSocket stream"])
```

### Task Lifecycle

```mermaid
sequenceDiagram
    actor User
    participant API as FastAPI
    participant ORC as Orchestrator
    participant MAIN as Main Agent
    participant SUB as Subagent
    participant REV as Reviewer

    User->>API: POST /api/v1/tasks
    API-->>User: task_id + live WebSocket stream
    API->>ORC: dispatch task
    ORC->>MAIN: route to domain expert
    opt Human-in-the-loop
        MAIN-->>User: clarifying question (WS)
        User->>API: POST /tasks/{id}/answer
    end
    MAIN->>SUB: atomic subtask
    SUB-->>REV: structured output (JSON)
    loop until approved (MAX_REVIEW_ITERATIONS)
        REV-->>SUB: issues + retry hints
        SUB-->>REV: revised output
    end
    REV-->>MAIN: approved
    MAIN-->>User: final result (WS)
```

### System Overview

```mermaid
flowchart LR
    subgraph Client
        FE["Frontend<br/>Next.js + React + TS"]
    end
    subgraph Server
        BE["Backend<br/>FastAPI (async)"]
        RD[("Redis<br/>rate limiting")]
    end
    subgraph Data
        PG[("PostgreSQL<br/>users, keys,<br/>subscriptions, usage")]
        MG[("MongoDB<br/>agent logs, marketplace,<br/>task sessions")]
        QD[("Qdrant<br/>conversation &amp; document<br/>embeddings")]
    end
    subgraph Providers["LLM Provider Adapters"]
        OL["Ollama (Qwen3.5)"]
        GM["Gemini"]
        OA["OpenAI"]
        AN["Anthropic"]
    end

    FE <-- "REST / WebSocket" --> BE
    BE --> RD
    BE --> PG
    BE --> MG
    BE --> QD
    BE --> OL
    BE --> GM
    BE --> OA
    BE --> AN
```

Agents communicate via structured JSON messages; the Subagent output format and Reviewer
feedback format are defined in [`CLAUDE.md`](./CLAUDE.md) §5.4.

## Features

| Module | Description | Status |
|---|---|---|
| Auth | Register / login / refresh token, JWT-based session management | Live |
| BYOK API key management | Encrypted storage (AES-256-GCM) for OpenAI, Anthropic, Gemini keys | Live |
| Task flow | Orchestrator → Main Agent → Subagent → optional Reviewer, live progress over WebSocket | Live |
| Architect view | Live node map / log stream of inter-agent communication | Live |
| RAG / memory | Per-user conversation history + document embeddings (Qdrant), retrieved at task start | Live |
| Document upload | `.txt` / `.md` upload → chunking → embedding (`nomic-embed-text`) | Live |
| Web search tool | Subagents can query DuckDuckGo (`ddgs`), bounded per subtask | Live |
| Dashboard & metrics | Token usage, success/failure rate, cost summary from real data | Live |
| Agent profile | Custom agent CRUD, system prompt editing, tool assignment, security scanning | Live |
| Marketplace | Publish agent teams (mandatory security scan), one-click install, install counter | Live |
| Human-in-the-loop | Main Agent can ask the user one clarifying question when uncertain | Live |
| Loop protection | `MAX_ITERATIONS`, `MAX_REVIEW_ITERATIONS`, `TASK_TIMEOUT_SECONDS` limits | Live |
| Multi-LLM provider | Ollama (free/default), Gemini, OpenAI, Anthropic — extensible via adapter pattern | Live |
| Rate limiting | Every endpoint throttled; Redis-backed sliding window with in-memory fallback | Live |
| Subscriptions & quota | Starter / Pro / Scale plans, per-period token quota, usage ledger; **mock payment gateway** | Live |
| Legal & GDPR | Terms / privacy / security / acceptable-use / cookies pages; account deletion + data export | Live |
| Deployment | Single Docker Compose stack, Caddy single-origin TLS, GHCR images, SSH rollout | Live |
| Real payment processor | Swap the mock gateway for iyzico / PayTR / Adyen / Stripe via one adapter | Planned |
| Marketplace ratings | Community reviews and scoring on agent teams | Planned |
| Refresh token rotation | Hardened production auth | Planned |
| i18n / GraphQL | UI localization; GraphQL API if REST performance requires it | Planned |

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | Next.js 16 (App Router) + React 19 + TypeScript + Tailwind + Zustand | UI, SSR, routing, state |
| Backend | FastAPI (async) + Pydantic v2 | Agent communication, REST / WebSocket API |
| Relational DB | PostgreSQL + SQLAlchemy (async) + Alembic | Users, subscriptions, billing, usage |
| NoSQL DB | MongoDB + Motor | Agent logs, marketplace content, task sessions |
| Vector DB | Qdrant | RAG memory, document embeddings |
| Cache / limiter | Redis | Sliding-window rate limiting across workers |
| Real-time | WebSocket (FastAPI) | Live agent status, human-in-the-loop Q&A |
| Authentication | Backend JWT (in-house auth) | User session management |
| Encryption | AES-256-GCM | BYOK API key security |
| LLM providers | Ollama (Qwen3.5), Gemini, OpenAI, Anthropic | Provider-agnostic adapter layer |
| Embeddings | `nomic-embed-text` via Ollama | Free / local embeddings for RAG |
| Web search | DuckDuckGo via `ddgs` | Subagent web-lookup tool |
| Containerization | Docker Compose + Caddy | Local infra and single-origin production stack |

The frontend uses the `class-variance-authority` + `clsx` + `tailwind-merge` primitive
pattern for components; there is no runtime `shadcn/ui` dependency.

## Getting Started

### Prerequisites

- **Docker** — for PostgreSQL, MongoDB, and Qdrant
- **Python 3.11+**
- **Node.js 20+**
- **[Ollama](https://ollama.com)** — for the free local model and embeddings

### Quick Start (single command)

The dev scripts bring up the full stack in one terminal: infrastructure (Docker), then
the backend (virtualenv, dependency install, `alembic upgrade head`, marketplace seed,
uvicorn), then the frontend (`npm install`, `next dev`). Ctrl+C stops everything.

```powershell
# Windows
./scripts/dev.ps1
```

```bash
# macOS / Linux
./scripts/dev.sh
```

Backend serves on `http://localhost:8000` (Swagger at `/docs`); frontend on
`http://localhost:3000`.

### Manual Setup

**1. Environment variables**

```bash
cp .env.example .env
# fill in JWT_SECRET and API_KEY_MASTER_KEY (see Configuration below)
```

**2. Infrastructure**

```bash
docker compose up -d          # postgres, mongo, qdrant
```

**3. Ollama models (free tier)**

```bash
ollama serve                  # run in a separate terminal
ollama pull qwen3.5:9b
ollama pull nomic-embed-text
```

**4. Backend**

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head           # apply DB migrations
uvicorn app.main:app --reload  # http://localhost:8000  (Swagger: /docs)
```

**5. Frontend**

```bash
cd frontend
npm install
npm run dev                    # http://localhost:3000
```

### Project Structure

```
maestro/
├── frontend/                        # Next.js + React + TypeScript
│   └── src/
│       ├── app/
│       │   ├── (auth)/              # login, register
│       │   ├── (app)/              # dashboard, architect, marketplace, agents, documents, settings
│       │   └── (marketing)/        # landing, pricing, legal, docs, how-it-works, use-cases
│       ├── components/              # ui/ dashboard/ architect/ marketplace/ agents/ layout/ legal/
│       ├── lib/                     # API client, SEO config, legal content
│       ├── stores/                  # Zustand stores
│       └── types/                   # Shared TS types
│
├── backend/                         # FastAPI (Python 3.11+)
│   ├── app/
│   │   ├── main.py                  # Entry point
│   │   ├── core/                    # config, security, constants, database
│   │   ├── api/v1/                  # auth, users, api_keys, agents, tasks, billing,
│   │   │                            # documents, dashboard, marketplace
│   │   ├── api/websocket.py         # WS connection management
│   │   ├── agents/                  # orchestrator, main_agent, subagent, reviewer, registry
│   │   ├── models/                  # SQLAlchemy & Pydantic models
│   │   ├── schemas/                 # Request/response schemas
│   │   ├── services/                # llm_service, memory_service, marketplace_service,
│   │   │                            # billing/quota/usage, payment/, task, user, web_search
│   │   ├── scripts/                 # purge_deleted_accounts, seed_marketplace
│   │   └── utils/                   # prompt_guard, rate_limiter, events
│   ├── alembic/                     # PostgreSQL migrations
│   └── tests/
│
├── scripts/                         # dev.ps1 (Windows) / dev.sh (macOS/Linux)
├── docker-compose.yml               # dev: Postgres, Mongo, Qdrant, Redis
├── docker-compose.prod.yml          # prod: full stack + Caddy + Ollama
├── Caddyfile                        # single-origin reverse proxy + auto TLS
├── docs/DEPLOYMENT.md               # deployment guide
├── .env.example / .env.prod.example
├── CLAUDE.md                        # Architecture & standards (single source of truth)
└── project-docs.md                  # Original product requirements
```

## Configuration

All settings are read from environment variables; the `.env` file is gitignored and never
committed. Generate the two secrets before first run:

```bash
openssl rand -hex 32       # JWT_SECRET
openssl rand -base64 32    # API_KEY_MASTER_KEY (32-byte AES-256 master key)
```

### Databases

| Variable | Description | Default |
|---|---|---|
| `POSTGRES_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://maestro:maestro@localhost:5433/maestro` |
| `MONGODB_URL` | MongoDB connection string | `mongodb://localhost:27017` |
| `MONGODB_DB_NAME` | MongoDB database name | `maestro` |
| `QDRANT_URL` | Qdrant vector DB address | `http://localhost:6333` |
| `QDRANT_API_KEY` | Qdrant API key (optional for local) | — |

### Rate limiting

| Variable | Description | Default |
|---|---|---|
| `REDIS_URL` | Redis for shared sliding-window buckets; empty falls back to in-process memory (single dev worker) | — |
| `RATE_LIMIT_ENABLED` | Master throttle switch; never `false` in production | `true` |
| `TRUST_PROXY_HEADERS` | Only `true` behind a proxy that appends `X-Forwarded-For` (e.g. Caddy) | `false` |

### Security & auth

| Variable | Description | Default |
|---|---|---|
| `JWT_SECRET` | JWT signing secret — random and confidential | — |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime | `7` |
| `API_KEY_MASTER_KEY` | AES-256-GCM master key for encrypting BYOK keys | — |
| `CORS_ORIGINS` | Allowed frontend origins (comma-separated) | `http://localhost:3000,http://127.0.0.1:3000` |

### Payments

| Variable | Description | Default |
|---|---|---|
| `PAYMENT_PROVIDER` | Payment gateway; only `mock` is implemented (Luhn/BIN validation, moves no real money) | `mock` |

Plan prices, quotas, trial length, and the first-month discount are product constants in
`backend/app/core/constants.py`, not environment variables.

### Models & embeddings

| Variable | Description | Default |
|---|---|---|
| `FREE_MODEL_ENDPOINT` | Ollama OpenAI-compatible endpoint | `http://localhost:11434/v1` |
| `FREE_MODEL_NAME` | Free-tier / local model | `qwen3.5:9b` |
| `EMBEDDING_ENDPOINT` | Embedding endpoint; reuses `FREE_MODEL_ENDPOINT` when blank | — |
| `EMBEDDING_MODEL_NAME` | RAG embedding model | `nomic-embed-text` |
| `EMBEDDING_DIM` | Embedding vector dimension | `768` |
| `GEMINI_MODEL_NAME` | Gemini model via OpenAI-compatible endpoint (BYOK free tier) | `gemini-3.5-flash` |

### Web search

| Variable | Description | Default |
|---|---|---|
| `WEB_SEARCH_ENABLED` | Enable the DuckDuckGo web-search tool | `true` |
| `WEB_SEARCH_MAX_RESULTS` | Results per query | `5` |
| `WEB_SEARCH_TIMEOUT_SECONDS` | Per-query timeout | `10` |
| `WEB_SEARCH_MAX_USES_PER_SUBTASK` | Cap on searches per subtask | `2` |

### Agent limits, retention & timeouts

| Variable | Description | Default |
|---|---|---|
| `MAX_ITERATIONS` | Max steps per Subagent | `10` |
| `MAX_REVIEW_ITERATIONS` | Reviewer ↔ Subagent loop limit | `3` |
| `TASK_TIMEOUT_SECONDS` | Total timeout per task (whole pipeline) | `1800` |
| `TASK_RETENTION_DAYS` | Mongo TTL on task sessions + agent logs | `7` |
| `LLM_REQUEST_TIMEOUT_SECONDS` | Per-LLM-call read timeout | `180` |
| `LLM_CONNECT_TIMEOUT_SECONDS` | Per-LLM-call connect timeout | `10` |
| `ENVIRONMENT` | `development` disables prod hardening; `production` closes Swagger | `development` |
| `LOG_LEVEL` | Application log level | `INFO` |

## Plans & Quota

Maestro has no free plan; new accounts begin on a 14-day trial with Starter-tier quota.
Quota is enforced solely through the Postgres `usage_records` ledger; every terminal task
path (success, error, timeout, cancellation) writes the tokens it spent.

| Plan | Price / month | Monthly token quota |
|---|---|---|
| Starter | $15 | 500,000 |
| Pro | $50 | 3,000,000 |
| Scale | $100 | 10,000,000 |

- 14-day Starter-quota trial for new accounts; if it lapses, task creation returns HTTP 402.
- 50% first-month discount, once per user ever (server-enforced via `users.first_discount_used`).
- 30-day rolling billing window anchored to the subscription period start.
- Payments run through the **mock gateway** — well-formed Visa / Mastercard numbers are
  validated (Luhn + BIN) but **no real money moves**. A real processor is a single new
  adapter; existing code does not change.

## API Reference

The full OpenAPI schema is available at `http://localhost:8000/docs` while the backend is
running. All non-public endpoints require JWT authentication and carry an explicit rate
limit; request and response bodies are validated with Pydantic v2.

```
# Authentication
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh

# User account (GDPR)
GET    /api/v1/users/me
GET    /api/v1/users/me/export              # downloadable JSON data export (Art. 20)
DELETE /api/v1/users/me                     # request account deletion (30-day grace)
POST   /api/v1/users/me/deletion/cancel     # cancel a pending deletion

# BYOK API key management
GET    /api/v1/api-keys
POST   /api/v1/api-keys
DELETE /api/v1/api-keys/{id}

# Agent management
GET    /api/v1/agents
POST   /api/v1/agents
GET    /api/v1/agents/{id}
PUT    /api/v1/agents/{id}
DELETE /api/v1/agents/{id}
PATCH  /api/v1/agents/{id}/system-prompt

# Task management
POST   /api/v1/tasks
GET    /api/v1/tasks/{id}
POST   /api/v1/tasks/{id}/cancel
POST   /api/v1/tasks/{id}/answer            # human-in-the-loop answer
WS     /api/v1/tasks/{id}/stream            # live task stream

# Billing & subscriptions
GET    /api/v1/billing/plans                # user-priced plan list (discount applied)
GET    /api/v1/billing/subscription         # plan, status + live quota usage
POST   /api/v1/billing/subscribe            # take card, charge first period, activate
POST   /api/v1/billing/cancel               # stop renewal (usable until period end)

# Documents (RAG)
POST   /api/v1/documents
GET    /api/v1/documents

# Dashboard & metrics
GET    /api/v1/dashboard/metrics
GET    /api/v1/dashboard/token-usage
GET    /api/v1/dashboard/cost-summary

# Marketplace
GET    /api/v1/marketplace
POST   /api/v1/marketplace
POST   /api/v1/marketplace/{id}/install
GET    /api/v1/marketplace/{id}/reviews

# Architect (live view)
WS     /api/v1/architect/live
```

## Database Schemas

- **PostgreSQL** — relational data: `users`, `api_keys` (encrypted), `subscriptions`,
  `payment_methods` (brand + last4 + expiry only — raw PAN is never stored), and the
  append-only `usage_records` quota ledger.
- **MongoDB** — dynamic data: `agent_logs`, `marketplace_items`, `task_sessions`,
  `agent_configurations`.
- **Qdrant** — vector data: `conversation_memories`, `document_chunks`.

See [`CLAUDE.md`](./CLAUDE.md) §6 for column-level detail.

## Security

- **BYOK keys** are encrypted with AES-256-GCM; never stored, logged, or returned to the
  frontend in plaintext. The master key exists only in `API_KEY_MASTER_KEY`.
- If a required key is missing when a task starts, the system halts the task and warns the
  user.
- **Loop protection:** `MAX_ITERATIONS` per Subagent, `MAX_REVIEW_ITERATIONS` for the
  Reviewer loop, and `TASK_TIMEOUT_SECONDS` per task (raise the timeouts when running slow
  local / CPU models).
- **Prompt-injection protection:** Marketplace uploads and custom system prompts pass
  through automatic security scanning (`backend/app/utils/prompt_guard.py`). Marketplace
  agents cannot reach the installing user's keys directly; all calls go through a sandboxed
  service layer.
- **Isolation:** RAG memory and all user data are partitioned per user. Every WebSocket
  connection is authenticated before `accept()`, and is subject to the same rate limiter as
  HTTP routes.
- **Rate limiting** keys on the authenticated user (`user:{sub}`) when a valid token is
  present, otherwise the caller IP — read from the rightmost `X-Forwarded-For` entry only
  when `TRUST_PROXY_HEADERS` is enabled.
- **Right to erasure / portability:** `DELETE /users/me` locks the account and schedules a
  30-day-grace purge (Mongo → Qdrant → Postgres, ordered so the flag row is removed last);
  `GET /users/me/export` returns a full JSON export. The purge runs via
  `python -m app.scripts.purge_deleted_accounts` (cron).

See [`CLAUDE.md`](./CLAUDE.md) §9 for the full policy. To report a vulnerability, follow
[`SECURITY.md`](./SECURITY.md) — please do not open a public issue.

## Development & Verification

CI runs on every push and PR to `main`: backend (ruff lint + format check + pytest) and
frontend (ESLint + type-check + production build). See
[`.github/workflows/ci.yml`](./.github/workflows/ci.yml).

```bash
# Backend
cd backend
pytest                            # tests
ruff check .                      # lint
ruff format --check .             # format check

# Frontend
cd frontend
npm run lint                      # ESLint
npm run type-check                # tsc --noEmit
npm run build                     # production build
```

When adding a new LLM provider, existing code is never modified — a new adapter class is
added under `backend/app/services/llm_service.py`. The same pattern applies to payment
providers (`backend/app/services/payment/`). See [`CLAUDE.md`](./CLAUDE.md) §11 and §15.

## Deployment

Maestro ships as a single Docker Compose stack: Postgres, MongoDB, Qdrant, Redis, an
Ollama embedding service, the API, the web app, and Caddy for automatic TLS. Caddy is the
only service that opens a port and serves the app and API from one origin, so there is no
CORS and no domain baked into any image. A 4 GB VM is sufficient.

```bash
# on the host, alongside docker-compose.prod.yml and Caddyfile
cp .env.prod.example .env.prod        # fill in DOMAIN and the generated secrets
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

Pushing a `v*` tag builds multi-arch images to GHCR and rolls them out over SSH.
Migrations run as a one-shot service the API waits on, so a failed migration never starts
a new backend. Full guide — including rollback, backups, the account-purge cron, and why
the API cannot run on Vercel — is in [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md).

## Roadmap

Development follows a vertical-slice-first approach — a solid foundation, then one
end-to-end flow at a time.

- **Round 1** — Auth, BYOK key management, end-to-end task flow, live WebSocket streaming.
- **Round 2** — RAG memory + document upload, four LLM adapters, dashboard metrics, agent
  profile CRUD, Marketplace, human-in-the-loop, dev scripts.
- **Round 3** — Subscriptions, per-period token quota, usage ledger, mock payment gateway.
- **Round 4** — Legal pages, GDPR account deletion + data export, cookie notice.
- **Round 5** — Containerization, single-origin Caddy stack, GHCR + SSH deployment.
- **Round 6** — Redis-backed rate limiting across every route and WebSocket.
- **Round 7** — SEO surface (sitemap, robots, OG images, JSON-LD).
- **Next** — real payment processor, Marketplace ratings, dynamic agents in the task flow,
  refresh-token rotation, transactional email, i18n, GraphQL (if needed), broader test
  coverage.

See [`CLAUDE.md`](./CLAUDE.md) §16 for the full breakdown.

## Contributing

Contributions are welcome. Start with [`CONTRIBUTING.md`](./CONTRIBUTING.md) for local
setup and the pull request workflow; participation is governed by the
[Code of Conduct](./CODE_OF_CONDUCT.md). The project follows the standards in
[`CLAUDE.md`](./CLAUDE.md):

- Code, identifiers, and comments are in English; user-facing UI text may be localized.
- Backend: Python 3.11+, type annotations required, `ruff` lint + format.
- Frontend: TypeScript `strict: true`, functional components, Zustand for state, Prettier.
- Business logic lives in the `services/` layer; route handlers stay thin.
- New LLM and payment providers are added via the adapter pattern; existing code is not
  modified.
- Every new endpoint declares an explicit rate limit.
- Before opening a PR, run the relevant layer's lint / test / type-check commands.

## License

Maestro is licensed under the [Apache License 2.0](./LICENSE) — free to use, modify, and
distribute, commercially or otherwise, with an explicit patent grant. Contributions are
covered by the same license under section 5; there is no CLA.

The Maestro name and logo are trademarks and are not licensed under Apache-2.0 (section 6).
Fork the code freely; ship it under your own name.

---

<div align="center">

Architecture and standards: [`CLAUDE.md`](./CLAUDE.md) · Product spec:
[`project-docs.md`](./project-docs.md)

</div>
