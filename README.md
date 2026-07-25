<div align="center">

# Maestro

**Self-hostable AI agent orchestration platform. Bring your own LLM keys (BYOK).**

One prompt in — a multi-layer agent hierarchy out: an Orchestrator routes the task, a
domain Main Agent plans it, Subagents execute it with real tools (web search, data fetch,
sandboxed code execution), and an optional Reviewer audits the results. Everything streams
live over WebSocket, backed by per-user RAG memory and a community Marketplace.

[![CI](https://github.com/Yigtwxx/Maestro/actions/workflows/ci.yml/badge.svg)](https://github.com/Yigtwxx/Maestro/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Sustainable_Use-blue)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=nextdotjs)](https://nextjs.org)

[Overview](#overview) · [Architecture](#architecture) · [Features](#features) · [Getting Started](#getting-started) · [Configuration](#configuration) · [API Reference](#api-reference) · [Security](#security) · [Deployment](#deployment) · [Roadmap](#roadmap)

</div>

---

## Overview

Maestro is a general-purpose platform for orchestrating teams of AI agents. A user submits
a single prompt; the **Orchestrator** classifies it and routes it to a domain **Main
Agent**, which decomposes the work into atomic subtasks and dispatches **Subagents** —
each with a bounded tool set — and, optionally, runs every output past a **Reviewer**
before returning a synthesized answer. The full run streams to the client over WebSocket,
and the Main Agent can pause mid-task to ask the user a clarifying question
(human-in-the-loop).

The platform is **bring-your-own-key**: users connect credentials for any of a dozen
providers — OpenAI, Anthropic, Google Gemini, Groq, DeepSeek, Mistral, xAI, OpenRouter,
Together, Perplexity, or any custom OpenAI-compatible endpoint — encrypted at rest with
AES-256-GCM. It also runs with **no paid key at all**: Gemini offers a free tier (no
credit card, [aistudio.google.com/apikey](https://aistudio.google.com/apikey)), and tasks
fall back to **Qwen3.5 via a local Ollama endpoint** when a quota is exhausted or no key
is connected. RAG embeddings are generated locally with `nomic-embed-text`, so the entire
pipeline can run offline and free.

Architecture, conventions, and code standards live in a single source of truth:
[`CLAUDE.md`](./CLAUDE.md).

## Self-Hosting vs Maestro Cloud

Maestro follows the fair-code model (like n8n): the source is public and
self-hosting is free, while a hosted subscription funds development.

| | Self-hosted | Maestro Cloud (hosted) |
|---|---|---|
| Cost | Free | Subscription (Starter / Pro / Scale) |
| Setup | `docker compose up` — you run Postgres, Mongo, Qdrant, Redis, Ollama | None — sign up and start |
| LLM access | Your own keys (BYOK) or fully local via Ollama + Qwen — zero external calls | Your own keys (BYOK) |
| Data | Never leaves your machine | Encrypted at rest, GDPR tooling built in |
| Updates & maintenance | You pull and migrate | Managed |
| Restrictions | Internal, personal, and non-commercial use — you may not resell Maestro as a hosted service to third parties | — |

Self-hosting is a first-class path, not a demo: the entire pipeline — LLM calls
and RAG embeddings included — can run offline and free on your own hardware.
See [License](#license) for the exact terms.

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
        MORE["Groq · DeepSeek · Mistral · xAI<br/>OpenRouter · Together · Perplexity · Custom"]
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
    BE --> MORE
```

Agents communicate via structured JSON messages; the Subagent output format and Reviewer
feedback format are defined in [`CLAUDE.md`](./CLAUDE.md) §5.4.

## Features

| Module | Description | Status |
|---|---|---|
| Auth | Register / login / logout, JWT access tokens + rotating refresh tokens | Live |
| Email verification | Verify / resend / forgot / reset flows via pluggable email providers (console, Resend); soft-gates task start and key creation | Live |
| Two-factor auth | TOTP with QR provisioning and single-use recovery codes | Live |
| Session management | List active sessions, revoke one or all others | Live |
| BYOK key management | AES-256-GCM encrypted storage for 12 LLM providers, incl. custom endpoints | Live |
| Task flow | Orchestrator → Main Agent → Subagents → optional Reviewer, live over WebSocket | Live |
| Durable task engine | Postgres-checkpointed steps with lease + heartbeat — a crashed worker's tasks resume instead of hanging; runs multi-worker over a Redis event bus | Live |
| Task history | List, inspect, cancel, and delete past tasks | Live |
| Architect view | Live node map / log stream of inter-agent communication | Live |
| RAG / memory | Per-user conversation history + document embeddings (Qdrant), retrieved at task start | Live |
| Document upload | `.txt` / `.md` upload → chunking → embedding (`nomic-embed-text`) | Live |
| Web search tool | Subagents query DuckDuckGo (`ddgs`), bounded per subtask | Live |
| Data fetch tool | Subagents pull public HTTP resources (GET → text), bounded per subtask | Live |
| Code execution tool | Subagents run Python in a resource-limited Docker sandbox; degrades gracefully when Docker is absent | Live |
| Dashboard & metrics | Token usage, success/failure rate, cost summary from real data | Live |
| Agent profile | Custom agent CRUD, system prompt editing, tool assignment, security scanning | Live |
| Dynamic agents | Custom agents run inside the task flow (`custom:{id}` routing, sandboxed persona) | Live |
| Marketplace | Publish agent teams (mandatory security scan), one-click install, install counter | Live |
| Marketplace reviews | Ratings (one review per user), aggregated scores, install trends, abuse reports | Live |
| Human-in-the-loop | Main Agent can ask the user one clarifying question when uncertain | Live |
| Loop protection | `MAX_ITERATIONS`, `MAX_REVIEW_ITERATIONS`, `TASK_TIMEOUT_SECONDS`, per-subtask tool-call caps | Live |
| Multi-LLM providers | 12 adapters over one abstract interface, with automatic fallback chains — new provider = one new adapter class | Live |
| Model routing | Per-role model selection: per-task overrides > user preferences > plan-tier defaults | Live |
| SSRF guard | Custom provider endpoints validated: http(s) only, credential-free, publicly routable | Live |
| Rate limiting | Every endpoint throttled; Redis-backed sliding window with in-memory fallback | Live |
| Subscriptions & quota | Starter / Pro / Scale plans, per-period token quota, usage ledger; **mock payment gateway** | Live |
| Legal & GDPR | Terms / privacy / security / acceptable-use / cookies pages; account deletion + data export | Live |
| Admin & moderation | Role-gated admin surface: user suspension, marketplace / review moderation, report queue, audit log | Live |
| Observability | Optional Sentry error tracking (backend + frontend), structured JSON logging, request IDs | Live |
| Tracing & costs | Optional per-task span tracing with waterfall + cost breakdowns by day / model / domain | Live |
| Deployment | Single Docker Compose stack, Caddy single-origin TLS, GHCR images, SSH rollout, off-site backups | Live |
| Real payment processor | Swap the mock gateway for iyzico / PayTR / Adyen / Stripe via one adapter | Planned |
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
| LLM providers | Ollama, OpenAI, Anthropic, Gemini, Groq, DeepSeek, Mistral, xAI, OpenRouter, Together, Perplexity, custom | Provider-agnostic adapter layer with fallback |
| Embeddings | `nomic-embed-text` via Ollama | Free / local embeddings for RAG |
| Agent tools | DuckDuckGo (`ddgs`), HTTP data fetch, Docker code sandbox | Bounded per-subtask tool calls |
| Containerization | Docker Compose + Caddy | Local infra and single-origin production stack |

The frontend uses the `class-variance-authority` + `clsx` + `tailwind-merge` primitive
pattern for components; there is no runtime `shadcn/ui` dependency.

## Getting Started

### Prerequisites

- **Docker** — for PostgreSQL, MongoDB, and Qdrant (and the optional code-execution sandbox)
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
docker compose up -d          # postgres, mongo, qdrant, redis
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
│       │   ├── (auth)/              # login, register, verify-email, password reset
│       │   ├── (app)/               # dashboard, architect, traces, marketplace, agents,
│       │   │                        # documents, settings, admin
│       │   └── (marketing)/         # landing, pricing, legal, docs, how-it-works, use-cases
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
│   │   │                            # documents, dashboard, marketplace, admin
│   │   ├── api/websocket.py         # WS connection management
│   │   ├── agents/                  # orchestrator, main_agent, subagent, reviewer, registry
│   │   ├── models/                  # SQLAlchemy & Pydantic models
│   │   ├── schemas/                 # Request/response schemas
│   │   ├── services/                # llm, memory, task_engine, marketplace, moderation,
│   │   │                            # billing/quota/usage, payment/, email/, trace,
│   │   │                            # two_factor, web_search, data_fetch, code_execution
│   │   ├── scripts/                 # purge_deleted_accounts, seed_marketplace, grant_admin
│   │   └── utils/                   # prompt_guard, rate_limiter, events, tracing
│   ├── alembic/                     # PostgreSQL migrations
│   └── tests/
│
├── scripts/                         # dev.ps1 / dev.sh (one-command dev), backup.sh
├── docker-compose.yml               # dev: Postgres, Mongo, Qdrant, Redis
├── docker-compose.prod.yml          # prod: full stack + Caddy + Ollama
├── Caddyfile                        # single-origin reverse proxy + auto TLS
├── docs/DEPLOYMENT.md               # deployment guide
├── .env.example / .env.prod.example
└── CLAUDE.md                        # Architecture & standards (single source of truth)
```

## Configuration

All settings are read from environment variables; the `.env` file is gitignored and never
committed. In production the backend refuses to boot with placeholder or weak secrets.
Generate the two required secrets before first run:

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

### Security & auth

| Variable | Description | Default |
|---|---|---|
| `JWT_SECRET` | JWT signing secret — random and confidential, min 32 chars in production | — |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime | `7` |
| `API_KEY_MASTER_KEY` | AES-256-GCM master key for encrypting BYOK keys (32 bytes, base64 or hex) | — |
| `CORS_ORIGINS` | Allowed frontend origins (comma-separated) | `http://localhost:3000` |
| `LLM_SSRF_GUARD_ENABLED` | Validate custom provider endpoints (http(s), credential-free, public addresses only); disable only on a fully self-hosted stack | `true` |

### Rate limiting

| Variable | Description | Default |
|---|---|---|
| `REDIS_URL` | Redis for shared sliding-window buckets; empty falls back to in-process memory (single dev worker) | — |
| `RATE_LIMIT_ENABLED` | Master throttle switch; never `false` in production | `true` |
| `TRUST_PROXY_HEADERS` | Only `true` behind a proxy that appends `X-Forwarded-For` (e.g. Caddy) | `false` |

### Models & embeddings

| Variable | Description | Default |
|---|---|---|
| `FREE_MODEL_ENDPOINT` | Ollama OpenAI-compatible endpoint | `http://localhost:11434/v1` |
| `FREE_MODEL_NAME` | Free-tier / local model | `qwen3.5:9b` |
| `OLLAMA_CHAT_ENABLED` | Serve the local Ollama chat model; `false` on hosted deployments where the Ollama service only runs embeddings | `true` |
| `OLLAMA_NATIVE_TOOLS` | Use Ollama's native function calling instead of the directive fallback | `false` |
| `EMBEDDING_ENDPOINT` | Embedding endpoint; reuses `FREE_MODEL_ENDPOINT` when blank | — |
| `EMBEDDING_MODEL_NAME` | RAG embedding model | `nomic-embed-text` |
| `EMBEDDING_DIM` | Embedding vector dimension | `768` |
| `GEMINI_MODEL_NAME` | Gemini model id; the `-latest` alias survives model retirements — pin a stable id for deterministic behavior | `gemini-flash-latest` |
| `LLM_REQUEST_TIMEOUT_SECONDS` | Per-LLM-call read timeout | `180` |
| `LLM_CONNECT_TIMEOUT_SECONDS` | Per-LLM-call connect timeout | `10` |

### Agent tools

| Variable | Description | Default |
|---|---|---|
| `WEB_SEARCH_ENABLED` | DuckDuckGo web-search tool | `true` |
| `WEB_SEARCH_MAX_RESULTS` | Results per query | `5` |
| `WEB_SEARCH_TIMEOUT_SECONDS` | Per-query timeout | `10` |
| `WEB_SEARCH_MAX_USES_PER_SUBTASK` | Searches per subtask | `3` |
| `DATA_FETCH_ENABLED` | Data-fetch tool (Scrapling: TLS-impersonating GET → page text, or CSS-selected JSON) | `true` |
| `DATA_FETCH_TIMEOUT_SECONDS` | Per-fetch timeout | `15` |
| `DATA_FETCH_MAX_USES_PER_SUBTASK` | Fetches per subtask | `3` |
| `DATA_FETCH_ENGINE` | `scrapling` or `httpx` (the pre-Scrapling path: no selectors, no impersonation, but a streaming size cap) | `scrapling` |
| `DATA_FETCH_RENDER_ENABLED` | Browser tier for JS-rendered pages; needs `scrapling install` in the image plus ~1GB RAM. Self-host only — the tool works fully without it | `false` |
| `DATA_FETCH_RENDER_TIMEOUT_SECONDS` | Per-render timeout | `45` |
| `DATA_FETCH_RENDER_MAX_CONCURRENCY` | Concurrent browser renders | `1` |
| `REPO_INTEL_ENABLED` | GitHub repository intelligence for the Open Source squad. Works with no key at all (anonymous reads, 60/hour); a user's stored token raises it to 5000 | `true` |
| `SOCIAL_SEARCH_ENABLED` | X post search for the Social Listening squad. Needs the user's X key; withheld without one | `true` |
| `COMMUNITY_READ_ENABLED` | Discord / Slack / Telegram channel reading for the Community squad. Needs the user's key for that platform | `true` |
| `PLACES_INTEL_ENABLED` | Google Places lookup for the Local Market squad. Needs the user's Maps key | `true` |
| `CODE_EXECUTION_ENABLED` | Docker code sandbox; requires access to the Docker daemon — keep `false` on hosted deployments | `true` |
| `CODE_EXECUTION_IMAGE` | Sandbox container image | `python:3.12-slim` |
| `CODE_EXECUTION_TIMEOUT_SECONDS` | Per-run timeout | `30` |
| `CODE_EXECUTION_MEMORY_LIMIT` / `CODE_EXECUTION_CPUS` | Sandbox resource limits | `512m` / `1` |
| `CODE_EXECUTION_MAX_USES_PER_SUBTASK` | Runs per subtask | `3` |

### Agent limits & execution

| Variable | Description | Default |
|---|---|---|
| `MAX_ITERATIONS` | Max steps per Subagent | `10` |
| `MAX_REVIEW_ITERATIONS` | Reviewer ↔ Subagent loop limit | `3` |
| `TASK_TIMEOUT_SECONDS` | Total timeout per task (whole pipeline) | `1800` |
| `SUBAGENT_MAX_PARALLEL` | Concurrent Subagents per task | `3` |
| `SUBAGENT_MAX_TOOL_CALLS` | Total tool calls (all kinds) per subtask | `6` |
| `REVIEWER_FAIL_MODE` | What a reviewer crash means for the subtask: `warn`, `approve`, or `reject` | `warn` |
| `TASK_RETENTION_DAYS` | Mongo TTL on task sessions + agent logs; dashboard metrics cover this window | `30` |

### Payments

| Variable | Description | Default |
|---|---|---|
| `PAYMENT_PROVIDER` | Payment gateway; only `mock` is implemented (Luhn/BIN validation, moves no real money) | `mock` |

Plan prices and quotas are product constants in
`backend/app/core/constants.py`, not environment variables.

### Transactional email

| Variable | Description | Default |
|---|---|---|
| `EMAIL_PROVIDER` | `console` logs messages (dev / self-host — verification links are read from the log); `resend` sends via the Resend API | `console` |
| `RESEND_API_KEY` | Required when `EMAIL_PROVIDER=resend`; checked at boot in production | — |
| `EMAIL_FROM` | From header for outgoing mail | `Maestro <noreply@maestro.example.com>` |
| `SITE_URL` | Base URL the backend uses to build verification / reset links | `http://localhost:3000` |
| `EMAIL_VERIFICATION_REQUIRED` | Soft-gates task start and API-key creation until the email is verified | `true` |

### App & observability

| Variable | Description | Default |
|---|---|---|
| `ENVIRONMENT` | `production` enforces strong secrets and closes Swagger | `development` |
| `LOG_LEVEL` | Application log level | `INFO` |
| `LOG_FORMAT` | `text` for local dev, `json` for structured logs in production | `text` |
| `SENTRY_DSN` | Sentry error tracking; empty disables Sentry entirely | — |
| `SENTRY_TRACES_SAMPLE_RATE` | Tracing/APM sample rate (`0.0` = off) | `0.0` |
| `SENTRY_ENVIRONMENT` | Sentry environment tag; falls back to `ENVIRONMENT` | — |
| `TRACING_ENABLED` | Per-task span tracing (Mongo `trace_spans`); disabled = zero overhead | `false` |
| `TRACE_RETENTION_DAYS` | TTL on stored trace spans | `30` |

## Plans & Quota

Maestro has no free plan, no trial, and no discount: registration creates no
subscription, so an active paid plan is required before starting any task. Quota is
enforced solely through the Postgres `usage_records` ledger; every terminal task path
(success, error, timeout, cancellation) writes the tokens it spent.

| Plan | Price / month | Monthly token quota |
|---|---|---|
| Starter | $5 | 500,000 |
| Pro | $15 | 3,000,000 |
| Scale | $50 | 10,000,000 |

- Without an active subscription, task creation returns HTTP 402 — including the local
  Ollama model, which on a hosted instance is itself a served service.
- 30-day rolling billing window anchored to the subscription period start.
- Payments run through the **mock gateway** — well-formed Visa / Mastercard numbers are
  validated (Luhn + BIN) but **no real money moves**. A real processor is a single new
  adapter; existing code does not change.

## API Reference

The full OpenAPI schema is available at `http://localhost:8000/docs` while the backend is
running (disabled when `ENVIRONMENT=production`). All non-public endpoints require JWT
authentication and carry an explicit rate limit; request and response bodies are validated
with Pydantic v2.

```
# Health
GET    /health                              # liveness
GET    /health/ready                        # Postgres / Mongo / Qdrant / Redis probes

# Authentication
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/login/totp              # second step when 2FA is enabled
POST   /api/v1/auth/refresh                 # rotating refresh tokens (reuse detection)
POST   /api/v1/auth/logout
POST   /api/v1/auth/verify-email
POST   /api/v1/auth/resend-verification
POST   /api/v1/auth/forgot-password
POST   /api/v1/auth/reset-password

# User account (profile, sessions, 2FA, GDPR)
GET    /api/v1/users/me
PATCH  /api/v1/users/me                     # profile + model preferences
POST   /api/v1/users/me/password
GET    /api/v1/users/me/sessions
DELETE /api/v1/users/me/sessions/{family_id}
POST   /api/v1/users/me/sessions/revoke-others
POST   /api/v1/users/me/2fa/setup
POST   /api/v1/users/me/2fa/enable
POST   /api/v1/users/me/2fa/disable
GET    /api/v1/users/me/export              # downloadable JSON data export (Art. 20)
DELETE /api/v1/users/me                     # request account deletion (30-day grace)
POST   /api/v1/users/me/deletion/cancel     # cancel a pending deletion

# BYOK API key management
GET    /api/v1/api-keys
POST   /api/v1/api-keys
DELETE /api/v1/api-keys/{id}

# Agent management
GET    /api/v1/agents
GET    /api/v1/agents/tools                 # assignable tool catalog
POST   /api/v1/agents
GET    /api/v1/agents/{id}
PUT    /api/v1/agents/{id}
PATCH  /api/v1/agents/{id}/system-prompt
DELETE /api/v1/agents/{id}

# Task management
POST   /api/v1/tasks
GET    /api/v1/tasks                        # task history
GET    /api/v1/tasks/{id}
GET    /api/v1/tasks/{id}/trace             # span waterfall (when tracing is enabled)
GET    /api/v1/tasks/{id}/trace/summary
POST   /api/v1/tasks/{id}/cancel
POST   /api/v1/tasks/{id}/answer            # human-in-the-loop answer
DELETE /api/v1/tasks/{id}
WS     /api/v1/tasks/{id}/stream            # live task stream

# Billing & subscriptions
GET    /api/v1/billing/plans                # plan list with prices and quotas
GET    /api/v1/billing/plans/public         # anonymous pricing for marketing pages
GET    /api/v1/billing/subscription         # plan, status + live quota usage
GET    /api/v1/billing/payment-method       # brand + last4 + expiry only
POST   /api/v1/billing/subscribe            # take card, charge first period, activate
POST   /api/v1/billing/cancel               # stop renewal (usable until period end)

# Documents (RAG)
POST   /api/v1/documents
GET    /api/v1/documents
DELETE /api/v1/documents/{id}

# Dashboard & metrics
GET    /api/v1/dashboard/metrics
GET    /api/v1/dashboard/token-usage
GET    /api/v1/dashboard/cost-summary
GET    /api/v1/dashboard/costs              # trace-derived costs by day / model / domain

# Marketplace
GET    /api/v1/marketplace                  # includes ratings + install trends
GET    /api/v1/marketplace/showcase         # anonymous landing showcase
GET    /api/v1/marketplace/{id}
POST   /api/v1/marketplace
POST   /api/v1/marketplace/{id}/install
GET    /api/v1/marketplace/{id}/reviews
POST   /api/v1/marketplace/{id}/reviews     # one review per user (upsert)
POST   /api/v1/marketplace/{id}/report
POST   /api/v1/marketplace/reviews/{review_id}/report

# Admin & moderation (role-gated)
GET    /api/v1/admin/overview
GET    /api/v1/admin/users                  # + /{id}, /{id}/suspend, /{id}/unsuspend, /{id}/role
GET    /api/v1/admin/marketplace/items      # + /{id}/status, /{id}/reviews, review hide
DELETE /api/v1/admin/agents/{id}            # custom-agent takedown
GET    /api/v1/admin/reports                # + /{id}/resolve
GET    /api/v1/admin/audit

# Architect (live view)
WS     /api/v1/architect/live
```

## Database Schemas

- **PostgreSQL** — relational data: `users`, `api_keys` (encrypted), `refresh_tokens`
  (session families), `email_tokens`, `recovery_codes` (2FA), `subscriptions`,
  `payment_methods` (brand + last4 + expiry only — raw PAN is never stored), the
  append-only `usage_records` quota ledger, and the durable task engine tables
  `task_runs` / `task_checkpoints` / `task_questions`.
- **MongoDB** — dynamic data: `agent_logs`, `marketplace_items` plus reviews,
  moderation reports and the admin audit log, `task_sessions`, `agent_configurations`,
  `trace_spans` (TTL-bound).
- **Qdrant** — vector data: `conversation_memories`, `document_chunks`.

See [`CLAUDE.md`](./CLAUDE.md) §6 for column-level detail.

## Security

- **BYOK keys** are encrypted with AES-256-GCM; never stored, logged, or returned to the
  frontend in plaintext. The master key exists only in `API_KEY_MASTER_KEY`, and the
  backend refuses to start in production with placeholder or weak secrets.
- If a required key is missing when a task starts, the system halts the task and warns the
  user.
- **Loop protection:** `MAX_ITERATIONS` per Subagent, `MAX_REVIEW_ITERATIONS` for the
  Reviewer loop, `TASK_TIMEOUT_SECONDS` per task, and per-subtask caps on every tool
  (searches, fetches, sandbox runs, total calls).
- **SSRF guard:** user-supplied custom provider endpoints must be http(s),
  credential-free, and resolve only to publicly routable addresses — blocking probes of
  cloud metadata and internal services from a hosted deployment.
- **Sandboxed code execution:** subagent-generated Python runs in a throwaway Docker
  container with memory, CPU, and wall-clock limits — never in the API process.
- **Prompt-injection protection:** Marketplace uploads and custom system prompts pass
  through automatic security scanning (`backend/app/utils/prompt_guard.py`). Marketplace
  agents cannot reach the installing user's keys directly; all calls go through a
  sandboxed service layer.
- **Account security:** optional TOTP two-factor auth (encrypted secret, Argon2-hashed
  single-use recovery codes) and rotating refresh tokens with reuse detection — replaying
  a rotated token revokes the entire session family. Active sessions can be listed and
  revoked individually. Email verification soft-gates task start and API-key creation.
- **Moderation:** a role-gated admin surface handles user suspension, marketplace item
  and review moderation, and a user-facing report queue; every admin action is written
  to an audit log.
- **Isolation:** RAG memory and all user data are partitioned per user. Every WebSocket
  connection is authenticated before `accept()` and subject to the same rate limiter as
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

CI runs on every push and PR to `main`: backend (ruff lint + format check + pytest +
dependency-lock freshness check) and frontend (ESLint + type-check + production build);
non-draft PRs additionally build-verify both Docker images. See
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
added in `backend/app/services/llm_service.py` (OpenAI-compatible providers subclass a
shared base and are a few lines each). The same pattern applies to payment providers
(`backend/app/services/payment/`). See [`CLAUDE.md`](./CLAUDE.md) §11 and §15.

## Deployment

Maestro ships as a single Docker Compose stack: Postgres, MongoDB, Qdrant, Redis, an
Ollama embedding service, the API, the web app, and Caddy for automatic TLS. Caddy is the
only service that opens a port and serves the app and API from one origin, so there is no
CORS and no domain baked into any image. A 4 GB VM is sufficient. An optional
self-hosted Umami analytics service ships behind a Compose profile
(`COMPOSE_PROFILES=analytics`).

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
- **Round 2** — RAG memory + document upload, multi-provider LLM adapters, dashboard
  metrics, agent profile CRUD, Marketplace, human-in-the-loop, dev scripts.
- **Round 3** — Subscriptions (no free tier, no trial), per-period token quota, usage ledger, mock payment gateway.
- **Round 4** — Legal pages, GDPR account deletion + data export, cookie notice.
- **Round 5** — Containerization, single-origin Caddy stack, GHCR + SSH deployment.
- **Round 6** — Redis-backed rate limiting across every route and WebSocket.
- **Round 7** — SEO surface (sitemap, robots, OG images, JSON-LD).
- **Rounds 8–13** — Backend v2: durable execution engine (Postgres checkpoints,
  crash-safe resume), distributed runtime (Redis event bus, multi-worker), LLM layer v2
  (streaming, native tool calls, per-role model routing), dynamic agent registry, span
  tracing + cost observability, quality layer (weighted review rubric, effort scaling,
  token budgets).
- **Since then** — email verification + transactional email, TOTP two-factor auth,
  session management with refresh-token rotation, marketplace reviews & ratings, the
  admin / moderation surface, off-site backups, fully pinned dependency lockfiles.
- **Next** — real payment processor, pre-purge reminder email, i18n (starting with the
  Turkish KVKK notice), GraphQL (if REST performance requires it).

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

Maestro is distributed under the [Sustainable Use License](./LICENSE) (fair-code, the
same model as n8n). In short:

- **Free to self-host** — use, modify, and run Maestro for your own internal business,
  personal, or non-commercial purposes, on any hardware, at no cost.
- **Free to redistribute** non-commercially and free of charge.
- **Not allowed:** offering Maestro (or a modified version) to third parties as a hosted
  or managed service — i.e. running a competing "Maestro Cloud".

This is a source-available license, not an OSI-approved open-source license. It exists so
the code can stay public while the hosted service funds development. When in doubt about
a use case, open an issue and ask.

Versions published before 2026-07-11 were distributed under Apache-2.0 and remain
available under that license.

The Maestro name and logo are trademarks and are not covered by the license.

---

<div align="center">

Architecture and standards: [`CLAUDE.md`](./CLAUDE.md)

</div>
