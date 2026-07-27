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
MAIN AGENT     Domain expert (finance, software, marketing, …). May first run a
     │         read-only discovery pass over the user's own data, then builds the
     │         subtask plan, assigns each subagent its tools, and coordinates them.
     ├──────────────┐
     ▼              ▼
SUBAGENT       SUBAGENT      One atomic task each (fetch data, analyze, summarize).
     │              │        May escalate to the Main Agent for a tool it was not
     │              │        assigned (see §8, autonomous, not human-in-the-loop).
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
The `tools` list is resolved **per subagent**, not just per domain: the Main
Agent may assign each member a subset of the domain's tools (an unassigned member
falls back to the full domain set). A member's effective set is always
`main-assigned ∩ domain-declared ∩ operator-switches ∩ credentials` — an
assignment can only ever *narrow* it. A subagent that finds it needs a tool it
was not given may `request_tool` from the Main Agent mid-run (§8).

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
| Web fetch | Scrapling (curl_cffi TLS impersonation, lxml/CSS) | `data_fetch` tool: page text plus CSS-selector extraction |
| Connected APIs | GitHub REST, X API v2, Discord/Slack/Telegram, Google Places | `repo_intel` / `social_search` / `community_read` / `places_intel` tools, authenticated with the user's own BYOK service keys |

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
If a task needs a **brain** key that is missing, the task is stopped and the user is told.

A missing **service** key (X, GitHub, Maps, Discord/Slack/Telegram) is deliberately *not*
fatal: `resolve_enabled_tools` withholds that tool, the squad falls back to `web_search`,
and its mandatory `Data coverage` section — enforced by a `hard_fail` review criterion —
states what could not be reached. Stopping the task instead would make every connected
squad unusable for the majority of accounts, which hold no service keys at all.
`service_key_service.load_service_credentials` decrypts them once per run at the engine
edge and hands the agent layer a `ServiceCredentials` value whose `__repr__` renders
provider names only, never secrets.

**Loop protection.** `max_iterations` (default 10), `max_review_iterations` (default 3),
and `task_timeout_seconds` (default 300) bound every run. Exceeding a bound terminates
the task and logs it. Two more bounds cap the tool-delegation paths: a subagent's
`request_tool` escalations are capped by `max_tool_grants` (default 2), and the Main
Agent's pre-planning discovery pass by `max_discovery_calls` (default 2). Each grant
raises tool *variety*, never call *volume* — the per-tool and total `max_tool_calls`
caps still bound executions.

**Tool escalation (agent-to-agent, not HITL).** When a subagent needs a tool it was
not assigned, it emits a `request_tool` directive; the Main Agent LLM, acting as a
gatekeeper, autonomously grants or denies it. This is distinct from the §12
human-in-the-loop channel (`ask_user` / `task_questions` / `AWAITING_ANSWER`): there
is no task pause and no human, just one Main-Agent-persona LLM call. A grant can never
bypass a gate — the grantable pool is resolved through the same
domain/switch/credential filter as any other tool, so a subagent cannot obtain a tool
the operator disabled or the user has no key for. The requesting member's brief and
justification reach the gatekeeper as delimited untrusted data, never instructions.
Grant state is kept local to each subtask run, so a grant to one member in a parallel
wave never leaks to its siblings sharing the same `AgentContext`.

**Per-user RAG isolation.** The `document_search` and `memory_recall` tools search the
user's own Qdrant collections and are keyless. Every query is scoped by `user_id`
(`memory_service._user_filter`); the tool spec closes over the run's `user_id` and must
never fall back to a global default — this is the load-bearing property that keeps one
user's documents and conversation memory out of another's context (§6). The Main Agent's
discovery pass is restricted to exactly these two tools, so no external or action tool
can ever run at the main tier.

**Prompt injection.** Marketplace submissions are security-scanned on publish. Custom
system prompts are scanned on write and sandboxed inside `<agent_persona>` at execution
time. Installed marketplace agents never touch the installing user's API keys directly;
all provider calls go through the service layer.

**Outbound fetches (SSRF).** Every user- or model-supplied URL passes `url_guard`:
http(s) only, no embedded credentials, and every resolved address must be globally
routable. On the `data_fetch` static tier, redirects additionally use libcurl's SAFE
mode, which refuses a hop to an internal address before the request is made, and the
landed URL is re-validated afterwards so a body from an unexpected host never reaches the
LLM. The browser tier has neither protection — a rendered page issues subresource
requests to arbitrary hosts — which is a second reason `DATA_FETCH_RENDER_ENABLED`
defaults to `false`. Fetched content is delimited and carries
`UNTRUSTED_CONTENT_NOTICE`, and is injection-scanned before it is shown to a model.

The connected-API tools have **no SSRF surface** and deliberately do not use `url_guard`:
every host is a constant in `constants.py`, never model-supplied. What they do validate is
any value that reaches a URL *path* — a repo slug and a channel id are pattern-matched
before a request can be built. Their results are the richest prompt-injection surface in
the product (a post or a commit message is attacker-authored), so items are scanned and
dropped **individually** rather than blanking the whole block, and every block still
carries `UNTRUSTED_CONTENT_NOTICE`. Telegram is the one provider that puts its token in
the URL path, so that call passes an explicit redacted log label.

The shared client follows no redirects. `repo_intel` is the single exception and opts in
per call via `request_api(follow_redirect_host=...)`: GitHub answers a renamed repository
with 301, so refusing to follow one turns every moved project into a missing one. It is
**one** hop, to **one** hard-coded host, and a `Location` pointing anywhere else is
refused before the request is built — which is also what keeps the `Authorization` header
from ever reaching another origin. Widening this to a general "follow redirects" flag
would reintroduce the SSRF surface the paragraph above says these tools do not have.

**General.** JWT on every non-public endpoint, including WebSockets. Rate limiting on
every route. Pydantic validation on every input. In the single-origin production topology
CORS does not apply; in split deployments only known origins are allowed. Secrets live in
`.env`, which is gitignored.

---

## 9. Non-Negotiable Rules

1. Never log, store in plaintext, or return API keys to the frontend.
2. Every agent loop carries an iteration bound. This includes the delegation
   paths: subagent `request_tool` escalations are capped by `max_tool_grants` and
   the Main Agent's discovery pass by `max_discovery_calls`. A tool grant widens
   variety, never the `max_tool_calls` execution cap.
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
npm test               # vitest unit tests (pure logic: stores, lib, color maps)

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
and `type-check`, `lint`, `test`, and `build` pass on the frontend.

### CI quality gates

`.github/workflows/ci.yml` runs the blocking gates: backend `ruff check` / `ruff format
--check` + `pytest` (with `--cov=app` — coverage is **reported in the log, never gated on
a threshold**, so a coverage dip cannot fail a PR) + lock-freshness; frontend `eslint` +
`tsc --noEmit` + `vitest run` + `next build`.

**Lint policy (deliberate — do not "tighten" without auditing the fallout).** Four
react-hooks v7 rules (`set-state-in-effect`, `refs`, `purity`, `static-components`) are
kept at `warn` in `eslint.config.mjs`: they fire on *correct* code — the canonical
fetch-then-`setState` data-loading pattern and intentional imperative canvas/animation
code. Warnings do not fail CI; only errors do (`eslint` runs without `--max-warnings=0`,
and `next build` treats warnings as non-fatal). Never add `--max-warnings=0` while these
are demoted, and do not enable typescript-eslint's type-checked mode — `tsc --noEmit`
covers type correctness deterministically, without the flakiness of typed lint rules.

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
- `OLLAMA_NATIVE_API` — the Ollama adapter drives Ollama's own `/api/chat` rather than its
  OpenAI-compatible `/v1` shim, because three controls exist only there. Set `false` to
  force the shim; the adapter also falls back on its own if `/api/chat` answers 404, so a
  non-Ollama OpenAI-compatible server behind `FREE_MODEL_ENDPOINT` keeps working. The
  native path is also what makes `json_schema` a real capability for this provider:
  `format` compiles the schema into a grammar, so `structured_call` is enforced rather
  than parsed back out of prose.
- `OLLAMA_THINK` — on by default, and *always* suppressed for schema-constrained calls
  regardless of the setting. Two opposing facts pin it there. Reasoning is charged against
  `max_tokens` while being returned in a field Maestro never reads, so a quarter to a third
  of replies used to arrive with **empty content** and `finish_reason=length` (raising
  `max_tokens` does not help — the model reasons longer). But thinking is also what makes a
  member use its tools: with it off, the model must choose between emitting a bare tool
  directive and writing prose in one shot, and it reliably writes prose — 0 tool calls over
  18 cases, and 0 again after four escalating prompt rules. The empty-reply cost is now
  absorbed in code (schema calls never think; an empty free-form reply is retried once
  without it), so the setting can stay on for the capability. The `/v1` shim ignores every
  thinking-control parameter, which is the main reason the native endpoint is used at all.
- `OLLAMA_NUM_CTX` — Ollama loads a model with a 4096-token context unless told otherwise
  and truncates a longer prompt **from the front**, which is where the system prompt is. A
  subagent carrying a fetched page plus a teammate's output passes that easily, so the
  member would silently lose its role, output format and grounding rules first.
- `SITE_URL` — server-only and read at request time, never `NEXT_PUBLIC_*`, so the built
  image stays domain-agnostic. The backend reads its own copy for building email links.
- `PAYMENT_PROVIDER` — only `mock` is implemented here. `BILLING_LIVE` gates the honesty
  banner shown on `/terms` and `/pricing`.
- `EMAIL_PROVIDER` — `console` (default; links appear in logs) or `resend`.
- `SENTRY_DSN` / `FRONTEND_SENTRY_DSN` — two separate projects. Empty means fully off with
  zero egress; the frontend SDK chunk is never even downloaded.
- `DATA_FETCH_ENGINE` — `scrapling` (default) or `httpx`. The httpx path is the
  pre-Scrapling implementation, kept so a misbehaving engine rolls back with one env var
  and no redeploy. It is the only engine that enforces the response size cap *while
  streaming*; Scrapling returns a fully-read response, so there the cap is post-hoc.
- `DATA_FETCH_RENDER_ENABLED` — self-host only, and off by default. The image ships no
  browser binaries (`scrapling install` fetches ~400MB) and a headless Chromium costs
  300-500MB RSS. The tool is fully functional without it: the TLS-impersonating HTTP tier
  is the baseline capability, not a fallback, so a missing browser degrades one request
  rather than disabling the tool. That is also why `resolve_enabled_tools` deliberately
  does *not* gate `data_fetch` on a browser probe the way it gates `code_execution` on
  Docker.
- `REPO_INTEL_ENABLED` / `SOCIAL_SEARCH_ENABLED` / `COMMUNITY_READ_ENABLED` /
  `PLACES_INTEL_ENABLED` — the connected-API tools. Nothing is configured operator-side
  beyond these switches; the credential is the *user's*, stored under Settings > API Keys.
  Setting one to `false` removes that tool from every squad declaring it, which is the
  per-tool rollback. `repo_intel` is the odd one out: GitHub serves anonymous reads at
  60/hour, so the `opensource` squad is fully functional with no key and a stored token
  only raises the ceiling to 5000. It is therefore the only connected tool that can be
  smoke-tested live from this repo.
- `CODE_EXECUTION_ENABLED` — must stay `false` in production; enabling it requires mounting
  the Docker socket.
- `DOCUMENT_SEARCH_ENABLED` / `MEMORY_RECALL_ENABLED` — the RAG tools over the user's own
  data (uploads and conversation memory). Keyless and per-user scoped, so unlike the
  connected tools there is nothing to configure beyond the switch; setting one to `false`
  is the per-tool rollback. They degrade to a "no results" note on a cold Qdrant, never an
  error, so they are safe to leave on even before any documents are ingested.
- `MAIN_AGENT_DISCOVERY_ENABLED` — lets the Main Agent run a bounded, read-only pass over
  the user's own data (the two RAG tools only) before planning, to ground its plan. Off
  disables the pass entirely; `MAIN_AGENT_DISCOVERY_MAX_CALLS` bounds it when on.

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
