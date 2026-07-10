<div align="center">

# 🎼 Maestro

**Orchestrate AI agent teams with your own keys.**

A public, general-purpose AI agent orchestration platform. Connect your own LLM API keys
(**BYOK — Bring Your Own Key**) and run complex tasks end-to-end through a multi-layer
agent hierarchy — or share your agent teams with the community via the **Marketplace**.

[![CI](https://github.com/Yigtwxx/maestro/actions/workflows/ci.yml/badge.svg)](https://github.com/Yigtwxx/maestro/actions/workflows/ci.yml)
[![Next.js](https://img.shields.io/badge/Next.js-App_Router-black?logo=nextdotjs)](https://nextjs.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-relational-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![MongoDB](https://img.shields.io/badge/MongoDB-logs_&_sessions-47A248?logo=mongodb&logoColor=white)](https://www.mongodb.com)
[![Qdrant](https://img.shields.io/badge/Qdrant-vector_DB-DC244C)](https://qdrant.tech)
[![Docker](https://img.shields.io/badge/Docker-compose-2496ED?logo=docker&logoColor=white)](https://www.docker.com)
[![Ollama](https://img.shields.io/badge/Ollama-free_local_tier-white?logo=ollama&logoColor=black)](https://ollama.com)
[![License](https://img.shields.io/badge/License-Apache_2.0-D22128?logo=apache&logoColor=white)](./LICENSE)

[Features](#-features) · [Architecture](#-architecture) · [Getting Started](#-getting-started) · [API](#-api-overview) · [Security](#-security) · [Roadmap](#-roadmap) · [License](#-license)

</div>

---

## 💡 How It Works

One prompt in — an orchestrated agent team out:

1. **You enter a single prompt.**
2. The **Orchestrator** analyzes the task and routes it to the right domain expert.
3. The **Main Agent** breaks the task into sub-steps and dispatches Subagents.
4. **Subagents** execute their atomic tasks in parallel.
5. An optional **Reviewer** audits the output and bounces errors back for retry.
6. The result is **streamed to you live over WebSocket** — including the ability for
   agents to ask *you* a clarifying question mid-task (human-in-the-loop).

**Zero-cost by default.** Connect your own OpenAI / Anthropic / Google Gemini keys, or
use none at all: Gemini has a free tier (get a key at
[aistudio.google.com/apikey](https://aistudio.google.com/apikey) — no credit card), and
tasks automatically fall back to **Qwen3.5 via Ollama — fully free and local** when the
quota runs out or no key is connected.

> 📐 Single source of truth for architecture, conventions, and code standards: [`CLAUDE.md`](./CLAUDE.md)
> 📋 Original product requirements (spec): [`project-docs.md`](./project-docs.md)

## ✨ Features

| Module | Description | Status |
|---|---|---|
| **Auth** | Register / login / refresh token, JWT-based session management | ✅ Live |
| **BYOK API Key Management** | Encrypted storage (AES-256-GCM) for OpenAI, Anthropic, X, GitHub keys | ✅ Live |
| **Task Flow** | Orchestrator → Main Agent → Subagent → (optional) Reviewer, live progress via WebSocket | ✅ Live |
| **Architect View** | Live node map / log stream of inter-agent communication | ✅ Live |
| **RAG / Memory** | Per-user conversation history + document embeddings (Qdrant), automatic retrieval at task start | ✅ Live |
| **Document Upload** | `.txt` / `.md` upload → chunking → embedding (`nomic-embed-text`) | ✅ Live |
| **Dashboard & Metrics** | Token usage, success/failure rate, cost summary (from real data) | ✅ Live |
| **Agent Profile** | Custom agent CRUD, system prompt editing, tool assignment, security scanning | ✅ Live |
| **Marketplace** | Publish agent teams (mandatory security scan), one-click install, install counter | ✅ Live |
| **Human-in-the-loop** | Main Agent can ask the user one clarifying question when uncertain | ✅ Live |
| **Infinite Loop Protection** | `max_iterations`, `max_review_iterations`, `task_timeout_seconds` limits | ✅ Live |
| **Multi-LLM Provider** | Ollama (free/default), Gemini, OpenAI, Anthropic — extensible via adapter pattern | ✅ Live |
| **Rate limiting** | Every endpoint throttled; Redis-backed sliding window shared across instances, in-memory fallback | ✅ Live |
| **User profile & billing (Stripe)** | Subscription management | 🔜 Planned |
| **Marketplace ratings/reviews** | Community feedback on agent teams | 🔜 Planned |
| **Refresh token rotation** | Hardened production auth | 🔜 Planned |

## 🏗 Architecture

### Agent Hierarchy

The **Orchestrator** only routes — it never produces work product. The **Main Agent**
plans and coordinates. Each **Subagent** performs exactly one atomic task. The
**Reviewer** (toggle: `reviewer_enabled`) validates outputs and bounces errors back,
bounded by `max_review_iterations`.

```mermaid
flowchart TD
    U(["👤 User Prompt"]) --> O["🎯 Orchestrator<br/><i>routes the task to the right domain</i>"]
    O --> M["🧠 Main Agent<br/><i>domain expert — plans sub-tasks</i>"]
    M --> S1["⚙️ Subagent<br/><i>data fetching</i>"]
    M --> S2["⚙️ Subagent<br/><i>analysis</i>"]
    M --> S3["⚙️ Subagent<br/><i>reporting</i>"]
    S1 --> R{"🔍 Reviewer<br/><i>optional</i>"}
    S2 --> R
    S3 --> R
    R -- "❌ issues + retry hints<br/>(max_review_iterations)" --> M
    R -- "✅ approved" --> OUT(["📦 Result → WebSocket stream"])
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
    MAIN->>SUB: atomic sub-task
    SUB-->>REV: structured output (JSON)
    loop until approved (max_review_iterations)
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
        FE["🖥 Frontend<br/>Next.js + React + TS"]
    end
    subgraph Server
        BE["⚡ Backend<br/>FastAPI (async)"]
    end
    subgraph Data
        PG[("🐘 PostgreSQL<br/>users, keys,<br/>subscriptions")]
        MG[("🍃 MongoDB<br/>agent logs, marketplace,<br/>task sessions")]
        QD[("🧭 Qdrant<br/>conversation & document<br/>embeddings")]
    end
    subgraph Providers["LLM Provider Adapters"]
        OL["Ollama (Qwen3.5)"]
        GM["Gemini"]
        OA["OpenAI"]
        AN["Anthropic"]
    end

    FE <-- "REST / WebSocket" --> BE
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

## 🧰 Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Frontend** | Next.js (App Router) + React + TypeScript + Tailwind + shadcn/ui + Zustand | UI, SSR, routing, state |
| **Backend** | FastAPI (async) + Pydantic v2 | Agent communication, REST/WebSocket API |
| **Relational DB** | PostgreSQL + SQLAlchemy (async) + Alembic | Users, subscriptions, billing |
| **NoSQL DB** | MongoDB + Motor | Agent logs, marketplace content, task sessions |
| **Vector DB** | Qdrant | RAG memory system, document embeddings |
| **Real-time** | WebSocket (FastAPI) | Live agent status, human-in-the-loop Q&A |
| **Authentication** | Backend JWT (in-house auth) | User session management |
| **Encryption** | AES-256-GCM | BYOK API key security |
| **Free Model** | Gemini Flash (BYOK free tier) + Qwen3.5 via Ollama (local fallback) | Free tier / local development |
| **Embedding** | nomic-embed-text via Ollama | Free/local embeddings for RAG |
| **Containerization** | Docker Compose | Postgres, Mongo, Qdrant infrastructure |

## 🚀 Getting Started

### Prerequisites

- **Docker** (for Postgres / Mongo / Qdrant)
- **Python 3.11+**
- **Node.js 20+**
- **[Ollama](https://ollama.com)** (for the free local model)

### Quick Start (Single Command)

Brings up every layer at once — infra + backend + frontend:

```powershell
# Windows
./scripts/dev.ps1
```

```bash
# macOS / Linux
./scripts/dev.sh
```

### Manual Setup (Step by Step)

**1. Environment variables**

```bash
cp .env.example .env
# fill in values such as JWT_SECRET, API_KEY_MASTER_KEY
```

**2. Infrastructure (Docker)**

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
# Windows: .venv\Scripts\activate     |  macOS/Linux: source .venv/bin/activate
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

<details>
<summary><b>📂 Project Structure</b></summary>

```
maestro/
├── frontend/                        # Next.js + React + TypeScript
│   └── src/
│       ├── app/
│       │   ├── (auth)/              # login, register
│       │   └── (app)/               # dashboard, architect, marketplace,
│       │                            # agents, documents, settings
│       ├── components/              # ui/ dashboard/ architect/ marketplace/ agents/ layout/
│       ├── lib/                     # API client and utilities
│       ├── stores/                  # Zustand stores
│       └── types/                   # Shared TS types
│
├── backend/                         # FastAPI (Python 3.11+)
│   ├── app/
│   │   ├── main.py                  # Entry point
│   │   ├── core/                    # config, security, database
│   │   ├── api/v1/                  # auth, agents, tasks, marketplace,
│   │   │                            # api_keys, dashboard, documents
│   │   ├── api/websocket.py         # WS connection management
│   │   ├── agents/                  # orchestrator, main_agent, subagent,
│   │   │                            # reviewer, registry
│   │   ├── models/                  # SQLAlchemy & Pydantic models
│   │   ├── schemas/                 # Request/response schemas
│   │   ├── services/                # llm_service, memory_service,
│   │   │                            # marketplace_service, billing_service
│   │   └── utils/                   # prompt_guard, rate_limiter
│   ├── alembic/                     # PostgreSQL migrations
│   └── tests/
│
├── scripts/                         # dev.ps1 (Windows) / dev.sh (macOS/Linux)
├── docker-compose.yml               # Postgres, Mongo, Qdrant
├── .env.example
├── CLAUDE.md                        # Architecture & standards (single source of truth)
└── project-docs.md                  # Original product requirements
```

</details>

<details>
<summary><b>🔧 Environment Variables</b></summary>

Description of every variable in `.env.example`:

| Variable | Description | Default |
|---|---|---|
| `POSTGRES_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://user:pass@localhost:5433/maestro` |
| `MONGODB_URL` | MongoDB connection string | `mongodb://localhost:27017/maestro` |
| `JWT_SECRET` | JWT signing secret — **random and confidential** | — |
| `API_KEY_MASTER_KEY` | AES-256 master key for encrypting BYOK keys | — |
| `CORS_ORIGINS` | Allowed frontend origins | `http://localhost:3000` |
| `QDRANT_URL` | Qdrant vector DB address | `http://localhost:6333` |
| `QDRANT_API_KEY` | Qdrant API key (optional, empty for local setup) | — |
| `FREE_MODEL_ENDPOINT` | Ollama OpenAI-compatible endpoint | `http://localhost:11434/v1` |
| `FREE_MODEL_NAME` | Free-tier model name | `qwen3.5:9b` |
| `EMBEDDING_MODEL_NAME` | RAG embedding model | `nomic-embed-text` |
| `GEMINI_MODEL_NAME` | Gemini model (BYOK free tier) | `gemini-3.5-flash` |
| `MAX_ITERATIONS` | Max step limit per Subagent | `10` |
| `MAX_REVIEW_ITERATIONS` | Reviewer ↔ Subagent loop limit | `3` |
| `TASK_TIMEOUT_SECONDS` | Total timeout per task (whole pipeline) | `1800` |
| `LLM_REQUEST_TIMEOUT_SECONDS` | Per-LLM-call read timeout | `180` |
| `LLM_CONNECT_TIMEOUT_SECONDS` | Per-LLM-call connect timeout | `10` |

> ⚠️ The `.env` file is never committed — it is gitignored. Secrets are read only from
> environment variables, never hardcoded into the codebase.

</details>

## 🔌 API Overview

For the full OpenAPI schema, visit `http://localhost:8000/docs` while the backend is
running. All endpoints (except public ones) require JWT authentication and rate
limiting; request/response bodies are validated with Pydantic v2.

<details>
<summary><b>Endpoint groups</b></summary>

```
# Authentication
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh

# BYOK API Key Management
GET    /api/v1/api-keys
POST   /api/v1/api-keys
DELETE /api/v1/api-keys/{id}

# Agent Management
GET    /api/v1/agents
POST   /api/v1/agents
GET    /api/v1/agents/{id}
PUT    /api/v1/agents/{id}
DELETE /api/v1/agents/{id}
PATCH  /api/v1/agents/{id}/system-prompt

# Task Management
POST   /api/v1/tasks
GET    /api/v1/tasks/{id}
POST   /api/v1/tasks/{id}/cancel
POST   /api/v1/tasks/{id}/answer     # human-in-the-loop answer
WS     /api/v1/tasks/{id}/stream     # live task stream

# Documents (RAG)
POST   /api/v1/documents
GET    /api/v1/documents

# Dashboard & Metrics
GET    /api/v1/dashboard/metrics
GET    /api/v1/dashboard/token-usage
GET    /api/v1/dashboard/cost-summary

# Marketplace
GET    /api/v1/marketplace
POST   /api/v1/marketplace
POST   /api/v1/marketplace/{id}/install
GET    /api/v1/marketplace/{id}/reviews

# Architect (Live View)
WS     /api/v1/architect/live
```

</details>

<details>
<summary><b>🗄 Database Schemas</b></summary>

- **PostgreSQL** — relational data: `users`, `api_keys` (encrypted), `subscriptions`.
- **MongoDB** — dynamic/flexible data: `agent_logs`, `marketplace_items`,
  `task_sessions`, `agent_configurations`.
- **Qdrant** — vector data: `conversation_memories`, `document_chunks`.

See [`CLAUDE.md`](./CLAUDE.md) §6 for full column-level detail.

</details>

## 🔐 Security

- **BYOK API keys** are encrypted with AES-256-GCM; never stored, logged, or returned
  to the frontend in plaintext. The master key lives only in the `API_KEY_MASTER_KEY`
  environment variable.
- If a required API key is missing when a task starts, the system **halts** the task
  and warns the user.
- **Infinite loop protection:** `MAX_ITERATIONS` per Subagent, `MAX_REVIEW_ITERATIONS`
  for the Reviewer ↔ Subagent loop, and `TASK_TIMEOUT_SECONDS` per task (raise this and
  `LLM_REQUEST_TIMEOUT_SECONDS` if you're running slow local/CPU models).
- **Prompt injection protection:** agent teams uploaded to the Marketplace and custom
  system prompts go through automatic security scanning (`utils/prompt_guard.py`).
- Marketplace agents cannot access the installing user's API keys directly; all calls
  go through a sandboxed service layer.
- User memory (RAG) and data are isolated per user; all WebSocket connections require
  authentication; schema changes happen only via Alembic migrations.

See [`CLAUDE.md`](./CLAUDE.md) §9 for the full policy. Found a vulnerability? Please
report it privately — see [`SECURITY.md`](./SECURITY.md). Do not open a public issue.

## 🧪 Development & Verification

CI runs on every push and PR to `main` — backend (ruff lint + format + pytest) and
frontend (ESLint + type-check + build). See
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

When adding a new provider, existing code is never modified — a new **adapter class**
is added under `services/llm_service.py` (adapter pattern — see [`CLAUDE.md`](./CLAUDE.md) §11 and §15).

## 🚢 Deployment

Maestro ships as a single Docker Compose stack — Postgres, MongoDB, Qdrant, an
embedding server, the API, the web app, and Caddy for automatic TLS. Caddy is the
only service that opens a port, and it serves the app and the API from one origin,
so there is no CORS and no domain baked into any image. Any 4 GB VM will run it.

```bash
# on the host: docker-compose.prod.yml, Caddyfile and .env.prod
cp .env.prod.example .env.prod        # fill in DOMAIN and the generated secrets
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

Pushing a `v*` tag builds multi-arch images to GHCR and rolls them out over SSH.
Migrations run as a one-shot service the API waits on, so a failed migration never
starts a new backend.

Full guide, including rollback, backups, the account-purge cron and why the API
cannot run on Vercel: [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md).

## 🗺 Roadmap

Development follows a **vertical-slice-first** approach.

- [x] **Round 1** — Auth, BYOK API key management, end-to-end task flow
  (Orchestrator → Main → Subagent → optional Reviewer, via Ollama/Qwen3),
  live WebSocket task/architect streaming, `(auth)` pages, `settings/api-keys`,
  task launch screen, live `architect` view.
- [x] **Round 2** — RAG (per-user memory + document retrieval at task start),
  document upload, `OllamaAdapter` + `OpenAIAdapter` + `AnthropicAdapter`,
  Dashboard with real metrics, agent profile CRUD + tool assignment editor,
  Marketplace (security-scanned publishing + one-click install), human-in-the-loop
  clarifying questions, `scripts/dev.ps1` / `scripts/dev.sh`.
- [ ] **Next rounds** — User profile & subscription billing (Stripe), Marketplace
  ratings/reviews, dynamic agents in the task flow, GraphQL (if needed),
  long-polling fallback, i18n infrastructure, refresh token rotation,
  WS/task_service test coverage.

See [`CLAUDE.md`](./CLAUDE.md) §16 for full detail.

## 🤝 Contributing

Contributions are welcome. Start with [`CONTRIBUTING.md`](./CONTRIBUTING.md) for local
setup and the pull request workflow, and note that participation is governed by our
[Code of Conduct](./CODE_OF_CONDUCT.md).

This project is developed according to the standards defined in [`CLAUDE.md`](./CLAUDE.md):

- Code, identifiers, and comments are in **English**; user-facing UI text may be in
  Turkish (via i18n infrastructure).
- Backend: Python 3.11+, type annotations required, `ruff` lint + format.
- Frontend: TypeScript `strict: true`, functional components, `Zustand` for state
  management, `prettier` format.
- Business logic lives in the `services/` layer; route handlers stay thin.
- Every new LLM provider is added via the adapter pattern; existing code is never
  modified.
- Before opening a PR, make sure the relevant layer's lint/test/type-check commands
  pass cleanly (see [Development & Verification](#-development--verification)).

## 📄 License

Maestro is licensed under the **[Apache License 2.0](./LICENSE)** — free to use, modify,
and distribute, commercially or otherwise, with an explicit patent grant. Contributions
are covered by the same license under section 5; there is no CLA to sign.

The **Maestro name and logo are trademarks** and are not licensed under Apache-2.0
(section 6). Fork the code freely; ship it under your own name.

---

<div align="center">

For questions and detailed architecture decisions, see [`CLAUDE.md`](./CLAUDE.md) ·
for the product's original requirements, see [`project-docs.md`](./project-docs.md)

</div>
