# CLAUDE.md — Maestro Platform

Single source of truth for AI assistants and contributors working in this repository:
architecture, conventions, and the invariants that must not be broken.

All code, identifiers, comments, commit messages, and documentation are written in English.

---

## 1. What Maestro Is

Maestro is a general-purpose AI agent orchestration platform. Users connect their own
model provider keys (BYOK — Bring Your Own Key) and automate complex tasks through a
multi-layer agent hierarchy.

One prompt in → the Orchestrator classifies the domain → a Main Agent decomposes the work
→ Subagents execute atomic subtasks → an optional Reviewer enforces quality → a synthesized
result comes out. Community-built agent teams are shared and installed through a Marketplace.

---

## 2. Agent Hierarchy

```
User prompt
     │
     ▼
ORCHESTRATOR   Routing only. Classifies the task domain; produces no work itself.
     │
     ▼
MAIN AGENT     Domain expert (finance, software, marketing, …).
     │         Builds the subtask plan and coordinates subagents.
     ├──────────────┐
     ▼              ▼
SUBAGENT       SUBAGENT      One atomic task each (fetch data, analyze, summarize).
     │              │
     └──────┬───────┘
            ▼
      REVIEWER     Optional (`reviewer_enabled`). Validates subagent output and
                   sends it back with issues. Bounded by `max_review_iterations`.
```

Contracts between layers are structured JSON, never free text.

Subagent output:

```json
{
  "status": "success | error | needs_review",
  "data": {},
  "metadata": { "tokens_used": 0, "execution_time_ms": 0, "model_used": "string" }
}
```

Reviewer feedback:

```json
{ "approved": false, "issues": ["..."], "retry_hints": ["..."] }
```

Every agent has a `system_prompt`, a `tools` list, and a `max_iterations` bound.

---

## 3. Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | Next.js (App Router) + React + TypeScript + Tailwind | UI, SSR, routing |
| Backend | FastAPI (Python 3.11+) | API, agent runtime, WebSocket |
| Relational DB | PostgreSQL (SQLAlchemy async, Alembic) | Users, subscriptions, billing, durable task state |
| Document DB | MongoDB (Motor) | Agent logs, marketplace, task sessions, traces |
| Vector DB | Qdrant | RAG memory and document embeddings |
| Cache / bus | Redis | Rate-limit buckets, cross-worker event bus |
| Realtime | WebSocket | Live task streams, human-in-the-loop, architect view |
| Auth | Backend-issued JWT + refresh-token rotation, optional TOTP 2FA | Sessions |
| Encryption | AES-256-GCM | BYOK key storage |
| Local models | Qwen3 + nomic-embed-text via Ollama (OpenAI-compatible endpoint) | Zero-cost local/self-hosted operation |

---

## 4. Repository Layout

```
maestro/
├── frontend/src/
│   ├── app/            (app)/ authenticated, (auth)/ login+register, (marketing)/ public
│   ├── components/     ui/ shared primitives, then one directory per feature area
│   ├── lib/            api client, seo/, legal/, analytics/, observability/, helpers
│   ├── stores/         Zustand stores
│   └── types/          API response types
│
├── backend/app/
│   ├── main.py         App entrypoint, middleware, exception handlers
│   ├── core/           config, security (crypto), database, observability
│   ├── api/v1/         auth, users, api_keys, tasks, agents, documents,
│   │                   marketplace, billing, dashboard, admin
│   ├── api/websocket.py
│   ├── agents/         orchestrator, main_agent, subagent, reviewer, registry
│   ├── models/         SQLAlchemy models
│   ├── schemas/        Pydantic request/response models
│   ├── services/       Business logic. Notable seams:
│   │                     llm_service.py     provider adapters
│   │                     task_engine.py     durable step loop
│   │                     task_service.py    public task API
│   │                     quota_service.py   quota enforcement
│   │                     memory_service.py  RAG / vectors
│   │                     payment/           PaymentProvider protocol + mock
│   │                     email/             EmailProvider protocol + console/resend
│   ├── scripts/        Operational one-shots (purge, grant_admin)
│   └── utils/          prompt_guard, rate_limiter, tracing
│
├── docker-compose.yml / docker-compose.prod.yml / Caddyfile
├── scripts/            dev.ps1, dev.sh, backup.sh
└── docs/DEPLOYMENT.md
```

---

## 5. Conventions

### General

- Formatting: frontend ESLint + Prettier; backend Ruff (linter + formatter).
- Every function and class carries a docstring or JSDoc.
- No magic numbers or strings. Constants live in `constants.ts` / `constants.py`.

### Frontend

- Function components only; no class components.
- Zustand for state.
- All API calls go through the central client in `lib/`; every response is typed in `types/`.
- Pages in `app/`, shared components in `components/`.

### Backend

- Every endpoint is `async`. Pydantic v2 validates every request and response.
- Business logic lives in `services/`; route handlers stay thin.
- Errors are handled by the central exception handler.
- Schema changes go through Alembic. Never hand-run SQL.

---

## 6. Data Model

### PostgreSQL

```
users              id, email, hashed_password, display_name, role (user|admin),
                   subscription_tier (starter|pro|scale|NULL — NULL means no subscription),
                   email_verified, totp_secret (encrypted), model_preferences,
                   deletion_requested_at, suspended_at

api_keys           user_id, provider, encrypted_key (AES-256-GCM), label, is_active
refresh_tokens     session families; rotation + reuse detection
recovery_codes     Argon2-hashed, single-use 2FA fallbacks
email_tokens       SHA-256 hash only; single-use; purpose-scoped TTL

subscriptions      one row per user: plan, status, provider, provider ids,
                   current_period_start (quota window anchor), current_period_end,
                   cancel_at_period_end
payment_methods    brand, last4, exp_month, exp_year. Raw PAN is never stored.
usage_records      append-only quota ledger. task_id is the idempotency key.

task_runs / task_checkpoints / task_questions
                   durable execution state: leases, heartbeats, replay checkpoints
```

### MongoDB

```
agent_logs             Step-by-step agent execution history (seq-ordered)
marketplace_items      Published agent teams, ratings, install counts
task_sessions          Task sessions and analytics
agent_configurations   Custom agent prompts, tools, provenance
trace_spans            Execution spans with TTL
```

### Qdrant

```
conversation_memories  Per-user conversation embeddings
document_chunks        Uploaded document chunks
```

Memory is scoped per user. Data must never leak across users.

---

## 7. API Surface

All routes are under `/api/v1`. Every route declares an explicit rate limit.

```
auth          register, login, login/totp, refresh, logout,
              verify-email, resend-verification, forgot-password, reset-password
users         me (GET/PATCH), password, sessions (list/revoke/revoke-others),
              2fa/setup|enable|disable, export, deletion (request/cancel)
api-keys      list, create, delete
tasks         create, get, cancel, answer, WS stream
agents        CRUD, system-prompt patch
documents     upload, list, delete
marketplace   list, publish, install, reviews (submit/list), report
billing       plans, subscription, subscribe, cancel, payment-method
dashboard     metrics, token-usage, cost-summary, costs
admin         overview, users, marketplace items, agents takedown, reports, audit
architect     WS live agent communication stream
health        /health, /health/ready (outside /api/v1)
```

---

## 8. Security Policy

**BYOK.** Keys are encrypted with AES-256-GCM using a master key held only in the
environment. Keys are never returned to the frontend — only `provider` and `label`.
If a task needs a key that is missing, the task is stopped and the user is told.

**Loop protection.** `max_iterations` (default 10), `max_review_iterations` (default 3),
and `task_timeout_seconds` (default 300) bound every run. Exceeding a bound terminates
the task and logs it.

**Prompt injection.** Marketplace submissions are security-scanned on publish. Custom
system prompts are scanned on write and sandboxed inside `<agent_persona>` at execution
time. Installed marketplace agents never touch the installing user's API keys directly;
all provider calls go through the service layer.

**General.** JWT on every non-public endpoint, including WebSockets. Rate limiting on
every route. Pydantic validation on every input. In the single-origin production topology
CORS does not apply; in split deployments only known origins are allowed. Secrets live in
`.env`, which is gitignored.

---

## 9. Non-Negotiable Rules

1. Never log, store in plaintext, or return API keys to the frontend.
2. Every agent loop carries an iteration bound.
3. Marketplace security scanning is never skipped.
4. User data — including memory and vectors — is isolated per user.
5. New LLM providers are added as new adapters. Do not modify existing adapter code.
6. WebSocket connections require authentication before `accept()`.
7. Migrations go through Alembic. Never hand-run SQL.
8. This is a web platform. The global `torch device` (CUDA → MPS → CPU) rule does **not**
   apply here — no local torch model is ever loaded. All LLM and embedding work happens
   over HTTP against Ollama or a BYOK provider.
9. Raw card numbers (PAN) are never stored, logged, or returned. Only `brand + last4 +
   expiry` persist. A PAN lives in memory for the duration of one provider call.
10. During account purge the PostgreSQL row is deleted **last**. `deletion_requested_at`
    is how the sweep re-finds the account; deleting the PG row before Mongo and Qdrant are
    clean orphans data irreversibly. `purge_user_data` must raise, never swallow, so the
    sweep retries.
11. Quota is enforced solely through the PostgreSQL `usage_records` ledger. MongoDB
    `task_sessions` is analytics only. Tokens are counted by `TokenMeter` and written to
    the ledger in the task's `finally` block on every terminal path — success, error,
    timeout, cancellation.
12. Every new endpoint carries an explicit `dependencies=[rate_limit(...)]`. Do not set a
    router-level default: FastAPI merges router- and route-level dependency lists, so an
    overriding route would be counted twice. `tests/test_rate_limiter.py` fails on any
    route without a limit. New WebSocket routes must call `check_websocket` before
    `accept()` and be added to the test's allow-list.
13. `TRUST_PROXY_HEADERS` must be `true` only behind a reverse proxy that sets
    `X-Forwarded-For`. Exposed directly, a client forges the header and opens a fresh
    bucket per request. Left `false` behind a proxy, every user shares the proxy's bucket.

---

## 10. Development

```bash
# Frontend
cd frontend
npm ci
npm run dev            # localhost:3000
npm run build
npm run lint
npm run type-check

# Backend
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload   # localhost:8000
pytest
ruff check .
ruff format .

# Full stack
docker-compose up -d
./scripts/dev.sh                # or scripts/dev.ps1 on Windows
```

A change is done when `pytest` and `ruff check`/`ruff format --check` pass on the backend,
and `type-check`, `lint`, and `build` pass on the frontend.

### Dependency locking

`requirements.in` / `requirements-dev.in` are hand-edited intent; the `.txt` files are
generated locks and must never be edited by hand. Regenerate with:

```bash
uv pip compile --universal --python-version 3.11 --generate-hashes requirements.in -o requirements.txt
```

CI regenerates the locks and fails the PR if they drift. Frontend versions are pinned
exactly (`.npmrc` sets `save-exact=true`); install with `npm ci`.

---

## 11. Configuration

See `.env.example` for the full list. The settings whose behavior is not obvious:

- `REDIS_URL` — empty falls back to in-process rate-limit buckets and event bus. Boot is
  refused if `WEB_CONCURRENCY > 1` while this is empty.
- `TRUST_PROXY_HEADERS` — see rule 13 above.
- `EMBEDDING_ENDPOINT` — separate from `FREE_MODEL_ENDPOINT`; falls back to it when empty.
- `SITE_URL` — server-only and read at request time, never `NEXT_PUBLIC_*`, so the built
  image stays domain-agnostic. The backend reads its own copy for building email links.
- `PAYMENT_PROVIDER` — only `mock` is implemented here. `BILLING_LIVE` gates the honesty
  banner shown on `/terms` and `/pricing`.
- `EMAIL_PROVIDER` — `console` (default; links appear in logs) or `resend`.
- `SENTRY_DSN` / `FRONTEND_SENTRY_DSN` — two separate projects. Empty means fully off with
  zero egress; the frontend SDK chunk is never even downloaded.
- `CODE_EXECUTION_ENABLED` — must stay `false` in production; enabling it requires mounting
  the Docker socket.

Prices and quotas are not secrets and live in `constants.py`.

---

## 12. License and Business Model

Maestro is fair-code / open-core, following the n8n model.

- **License:** Sustainable Use License v1.0 (source-available). Anyone may read, run, and
  modify it for their own use. Reselling it as a commercial service to third parties is not
  permitted. See `LICENSE`.
- **Public:** the entire platform — auth, orchestration, BYOK, RAG, marketplace, the mock
  payment provider, and the fully local Ollama flow. `docker-compose up` gives a complete
  working self-hosted instance at zero cost.
- **Not public:** the real payment processor adapter, cloud tenancy infrastructure, and
  operational deployment scripts. The `PaymentProvider` adapter seam already accommodates
  this split — only the mock lives here.
- **Revenue:** hosted subscriptions (starter / pro / scale).

Contributions are inbound-licensed under the same terms; see `CONTRIBUTING.md`.

---

## 13. Known Architectural Limit

A hosted instance cannot reach an Ollama server running on a user's own machine — all LLM
calls are made backend-side, so `localhost:11434` resolves to the server itself. The
`ollama` provider works when the operator pulls a chat model into the container, or when a
user runs the whole stack locally. Running everything locally is the intended
self-hosting path and remains free.
