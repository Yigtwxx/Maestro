# Maestro Platform

**A public, general-purpose AI agent orchestration platform.** Users connect their own
LLM API keys (**BYOK — Bring Your Own Key**) and run complex tasks end-to-end through a
multi-layer agent hierarchy (**Orchestrator → Main Agent → Subagent → Reviewer**). The
community can share their own agent teams via the **Marketplace**, and others can install
them with a single click.

> 📐 Single source of truth for architecture, conventions, and code standards: [`CLAUDE.md`](./CLAUDE.md)
> 📋 Original product requirements (spec): [`project-docs.md`](./project-docs.md)

---

## Table of Contents

- [Core Value Proposition](#core-value-proposition)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [API Overview](#api-overview)
- [Database Schemas](#database-schemas)
- [Security](#security)
- [Development & Verification](#development--verification)
- [Roadmap](#roadmap)
- [Contributing](#contributing)

---

## Core Value Proposition

```
User enters a single prompt
        │
        ▼
Orchestrator analyzes the task → routes it to the right Main Agent
        │
        ▼
Main Agent breaks the task into sub-steps → dispatches Subagents
        │
        ▼
Subagents execute their tasks
        │
        ▼
(optional) Reviewer Agent checks quality, bounces errors back
        │
        ▼
Result is streamed to the user live over WebSocket
```

Users can connect their own OpenAI / Anthropic API keys; without one, they can still try
the platform at zero cost using **Qwen3 (via Ollama — fully free and local)**.

## Features

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
| **Multi-LLM Provider** | Ollama (free/default), OpenAI, Anthropic — extensible via adapter pattern | ✅ Live |
| User profile & billing (Stripe) | | 🔜 Planned |
| Marketplace ratings/reviews | | 🔜 Planned |
| Redis-based rate limiting, refresh token rotation | | 🔜 Planned |

See [Roadmap](#roadmap) and `CLAUDE.md` §16 for full detail.

## Architecture

### Agent Hierarchy

```
User Prompt
       │
       ▼
┌─────────────────┐
│  ORCHESTRATOR    │  ← runs on the user's connected LLM API
│  (Router)        │     determines which domain the task belongs to
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   MAIN AGENT    │  ← domain expert (finance, software, marketing, ...)
│    (Expert)     │     splits the task into sub-steps, dispatches Subagents
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────┐
│SUBAGENT│ │SUBAGENT│  ← one specific task each (data fetch, analysis, ...)
│(Worker)│ │(Worker)│
└────┬───┘ └────┬───┘
     │          │
     ▼          ▼
┌─────────────────┐
│    REVIEWER     │  ← optional (reviewer_enabled: boolean)
│   (Auditor)     │     bounces errors back to the Subagent (max_review_iterations)
└─────────────────┘
```

- The **Orchestrator** only routes; it never produces work product directly.
- The **Main Agent** builds the sub-task plan and coordinates its Subagents.
- Each **Subagent** performs exactly one atomic task.
- The **Reviewer**, when enabled, validates a Subagent's output and — if it finds an
  error — sends the task back with the specific issue (bounded by `max_review_iterations`).

Agents communicate via structured JSON messages; the Subagent output format and Reviewer
feedback format are defined in `CLAUDE.md` §5.4.

### System Architecture

```
┌────────────┐        REST / WebSocket        ┌──────────────┐
│  Frontend   │ ◄─────────────────────────────► │   Backend    │
│  (Next.js)  │                                  │  (FastAPI)   │
└────────────┘                                  └──────┬───────┘
                                                         │
                       ┌─────────────────────────────────┼───────────────────────────┐
                       ▼                                 ▼                           ▼
               ┌───────────────┐                ┌────────────────┐          ┌───────────────┐
               │ PostgreSQL    │                │ MongoDB         │          │ Qdrant         │
               │ users, keys,  │                │ agent_logs,     │          │ conversation & │
               │ subscriptions │                │ marketplace,    │          │ document       │
               │               │                │ task_sessions   │          │ embeddings     │
               └───────────────┘                └────────────────┘          └───────────────┘
                                                         │
                                                         ▼
                                          ┌───────────────────────────┐
                                          │  LLM Provider Adapters     │
                                          │  Ollama (Qwen3) / OpenAI / │
                                          │  Anthropic                │
                                          └───────────────────────────┘
```

## Tech Stack

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
| **Free Model** | Qwen3 via Ollama (OpenAI-compatible endpoint) | Free tier / local development |
| **Embedding** | nomic-embed-text via Ollama | Free/local embeddings for RAG |
| **Containerization** | Docker Compose | Postgres, Mongo, Qdrant infrastructure |

## Project Structure

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
├── docker-compose.yml                # Postgres, Mongo, Qdrant
├── .env.example
├── CLAUDE.md                        # Architecture & standards (single source of truth)
└── project-docs.md                  # Original product requirements
```

## Getting Started

### Prerequisites

- **Docker** (for Postgres / Mongo / Qdrant)
- **Python 3.11+**
- **Node.js 20+**
- **[Ollama](https://ollama.com)** (for the free local model)

### 1. Set Environment Variables

```bash
cp .env.example .env
# fill in values such as JWT_SECRET, API_KEY_MASTER_KEY
```

### 2. Infrastructure (Docker)

```bash
docker compose up -d          # postgres, mongo, qdrant
```

### 3. Ollama Models (Free Tier)

```bash
ollama serve                  # run in a separate terminal
ollama pull qwen3
ollama pull nomic-embed-text
```

### 4. Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate     |  macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head           # apply DB migrations
uvicorn app.main:app --reload  # http://localhost:8000  (Swagger: /docs)
```

### 5. Frontend

```bash
cd frontend
npm install
npm run dev                    # http://localhost:3000
```

### Quick Start (Single Command)

To bring up every layer (infra + backend + frontend) at once:

```powershell
# Windows
./scripts/dev.ps1
```

```bash
# macOS / Linux
./scripts/dev.sh
```

## Environment Variables

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
| `FREE_MODEL_NAME` | Free-tier model name | `qwen3` |
| `EMBEDDING_MODEL_NAME` | RAG embedding model | `nomic-embed-text` |
| `MAX_ITERATIONS` | Max step limit per Subagent | `10` |
| `MAX_REVIEW_ITERATIONS` | Reviewer ↔ Subagent loop limit | `3` |
| `TASK_TIMEOUT_SECONDS` | Total timeout per task | `300` |

> ⚠️ The `.env` file is never committed — it is gitignored. Secrets are read only from
> environment variables, never hardcoded into the codebase.

## API Overview

For the full OpenAPI schema, visit `http://localhost:8000/docs` while the backend is
running. Main endpoint groups:

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

All endpoints (except public ones) require JWT authentication and rate limiting;
request/response bodies are validated with Pydantic v2.

## Database Schemas

**PostgreSQL** — relational data: `users`, `api_keys` (encrypted), `subscriptions`.
**MongoDB** — dynamic/flexible data: `agent_logs`, `marketplace_items`,
`task_sessions`, `agent_configurations`.
**Qdrant** — vector data: `conversation_memories`, `document_chunks`.

See `CLAUDE.md` §6 for full column-level detail.

## Security

- **BYOK API keys** are encrypted with AES-256-GCM; never stored, logged, or returned
  to the frontend in plaintext.
- The master encryption key is read only from the `API_KEY_MASTER_KEY` environment
  variable; it is never embedded in code.
- If a required API key is missing when a task starts, the system **halts** the task
  and warns the user.
- **Infinite loop protection:** `MAX_ITERATIONS` per Subagent, `MAX_REVIEW_ITERATIONS`
  for the Reviewer ↔ Subagent loop, and `TASK_TIMEOUT_SECONDS` per task.
- **Prompt injection protection:** agent teams uploaded to the Marketplace and custom
  system prompts go through automatic security scanning (`utils/prompt_guard.py`).
- Agents installed from the Marketplace cannot access the installing user's API keys
  directly; all calls go through a sandboxed service layer.
- User memory (RAG) and data are isolated per user.
- All WebSocket connections require authentication.
- Database schema changes are made only via Alembic migrations.

See `CLAUDE.md` §9 for the full policy.

## Development & Verification

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
npm test                          # vitest/jest (if present)
```

When adding a new provider, existing code is never modified — a new **adapter class**
is added under `services/llm_service.py` (adapter pattern — see `CLAUDE.md` §11 and §15).

## Roadmap

Development follows a **vertical-slice-first** approach.

- **Round 1 — Done:** Auth, BYOK API key management, end-to-end task flow
  (Orchestrator → Main → Subagent → optional Reviewer, via Ollama/Qwen3),
  live WebSocket task/architect streaming, `(auth)` pages, `settings/api-keys`,
  task launch screen, live `architect` view.
- **Round 2 — Done:** RAG (per-user memory + document retrieval at task start),
  document upload, `OllamaAdapter` + `OpenAIAdapter` + `AnthropicAdapter`,
  Dashboard with real metrics, agent profile CRUD + tool assignment editor,
  Marketplace (security-scanned publishing + one-click install), human-in-the-loop
  clarifying questions, `scripts/dev.ps1` / `scripts/dev.sh`.
- **Next rounds:** User profile & subscription billing (Stripe), Marketplace
  ratings/reviews, dynamic agents in the task flow, GraphQL (if needed),
  long-polling fallback, i18n infrastructure, Redis-based rate limiting +
  refresh token rotation, WS/task_service test coverage.

See `CLAUDE.md` §16 for full detail.

## Contributing

This project is developed according to the standards defined in `CLAUDE.md`:

- Code, identifiers, and comments are in **English**; user-facing UI text may be in
  Turkish (via i18n infrastructure).
- Backend: Python 3.11+, type annotations required, `ruff` lint + format.
- Frontend: TypeScript `strict: true`, functional components, `Zustand` for state
  management, `prettier` format.
- Business logic lives in the `services/` layer; route handlers stay thin.
- Every new LLM provider is added via the adapter pattern; existing code is never
  modified.
- Before opening a PR, make sure the relevant layer's lint/test/type-check commands
  pass cleanly (see [Development & Verification](#development--verification)).

---

For questions and detailed architecture decisions, see `CLAUDE.md`; for the product's
original requirements, see `project-docs.md`.
