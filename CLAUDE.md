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
│   ├── core/           config, security (crypto), database, observability, metrics
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
│   │                     alerts/            AlertChannel protocol + webhook/email
│   │                     alert_service.py   redaction, dedupe, fan-out
│   │                     watchdog.py        readiness/5xx alerting, metrics publish
│   ├── scripts/        Operational one-shots (purge, email-token sweep, grant_admin)
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
                   subscription_tier (free|starter|pro|scale — every account is
                   provisioned with an active free plan at registration),
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

The **connected**-API tools have **no SSRF surface** and deliberately do not use `url_guard`:
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
from ever reaching another origin. `custom_api` never opts in: a 3xx from a user endpoint
is reported as a failure, because there is no hard-coded host to bound the hop to.
Widening this to a general "follow redirects" flag
would reintroduce the SSRF surface the paragraph above says these tools do not have.

The **alert webhook** (`ALERT_WEBHOOK_URL`) is the one outbound URL that is neither a
constant of ours nor guarded, and deliberately so: it is an *operator* value from
`.env.prod`, written by the same person who writes `POSTGRES_URL` and
`API_KEY_MASTER_KEY` — neither of which is guarded either. Running `url_guard` over it
would actively break the common self-hosted case, because `resolve_is_public` rejects a
non-globally-routable address and an internal notifier on the compose network is exactly
that; in exchange it would defend only against an attacker who can already rewrite the
env file, at which point the master key is theirs. What *is* enforced: scheme validation
at boot, `follow_redirects=False` so the POST cannot be bounced to another origin, a hard
timeout, and the URL never reaching a log line or an exception message — a Slack/Discord
webhook URL is itself the credential. This is not a precedent for user-supplied hosts;
that case is `custom_api` below.

**Custom API tools (`custom_api__{slug}`).** The one exception to everything above: a user
registers their own endpoint from the agent wizard's Capabilities step, so the *host is
user-supplied* and none of the "it's a constant" reasoning applies. Safety comes from
`url_guard` instead, run **twice** — at registration (`schemas/custom_api_tool` for the
shape, the route for the DNS resolution) and again inside `custom_api_service.call`,
because a record outlives its validation and the DNS for a host the user owns is theirs to
change. Path parameters are percent-encoded with an empty safe set (`urljoin` is
deliberately not used — an absolute-looking value would replace the base), query values go
through httpx `params=`, static headers cannot be `Authorization`/`Cookie`/`Host`,
responses are byte-capped while streaming, and the tool's own `name`/`description` pass
`prompt_guard` at write time because they are interpolated into the subagent's system
prompt. The stored credential is AES-256-GCM in Mongo — the first ciphertext in that
datastore — kept out of every response by both a query projection and an explicit
`CustomApiToolPublic` field list. The residual risk is DNS rebinding, which `url_guard`
already documents as unclosed — and which is why `CUSTOM_API_TOOLS_ENABLED` defaults to
`false` rather than shipping on. A per-user action id never enters
`TOOL_CATALOG`/`TOOL_IDS`: those are process-wide constants that
`agent_service._validate_tools`, the marketplace publish filter and the frontend parity
tests all key off.

**Token storage.** The refresh token lives in an httpOnly, `Secure`, `SameSite=Strict`
cookie scoped to `/api/v1/auth`, set by `core/cookies.py` and absent from every response
body; the access token lives in a module-level variable in `frontend/src/lib/api.ts` and
is never persisted. Neither `localStorage` nor `sessionStorage` holds a credential, so an
XSS foothold can spend the current access token for at most its 30-minute life and cannot
exfiltrate a 7-day session — which is what rotation alone could never do, since a thief
holding *both* halves just rotates like a normal user and trips no detection. `/refresh`
and `/logout` are therefore cookie-authenticated and CSRF-reachable in principle;
`SameSite` is the whole control, and it is sufficient because both are POST-only, so the
cookie is simply not sent on a cross-site POST under either allowed value. CORS is a
second layer, not the control — it blocks *reading* a response, not sending a request.
`SameSite=None` is deliberately not offered: a deployment whose app and API sit on
different registrable domains routes the API through the frontend's `BACKEND_ORIGIN`
rewrite rather than deleting the control. If that ever changes, `/refresh` and `/logout`
must first gain a required custom header, which forces a preflight a form POST cannot
satisfy. Because memory starts empty, **every** document load spends one rotation, and
several tabs restoring at once would replay one cookie into the reuse-detection at
`auth_service.rotate_refresh_token` and burn the family; `navigator.locks`
(`lib/refresh-lock.ts`) serializes rotation across the origin's documents, so a waiting
tab presents the successor rather than a token already spent. That per-load rotation is
also why `/refresh` carries its own rate-limit tier instead of the shared `auth` bucket:
routine page loads must not be throttled alongside credential stuffing.

**Email ownership.** An account's address is only ever set by proving the inbox is
reachable. `PATCH /users/me` cannot touch `email` at all; the change goes through
`POST /users/me/email`, which requires the current password, leaves the account on its old
address, mails a link plus code to the new one and an actionable-nothing notice to the old
one, and revokes other sessions when it lands. The pending address rides on the token row,
never on `users`, so it expires and rotates with the token and a stale link can never
apply an older address. Single-use tokens are claimed with one conditional
`UPDATE … RETURNING`, never a read-then-write: two concurrent redemptions of the same link
cannot both succeed.

**Verification codes.** Every verification and email-change mail carries a 6-digit code
beside the link. The two are not interchangeable security-wise and must not be conflated:
a 256-bit token is globally unique, which is what lets the link endpoints stay
unauthenticated, while 10⁶ is guessable — so a code carries a short TTL
(`EMAIL_CODE_TTL_MINUTES`), an attempt cap that burns the row
(`EMAIL_CODE_MAX_ATTEMPTS`), and a lookup scoped to one `user_id`, which is why the code
endpoints require a session. Password reset deliberately has no code: it grants account
takeover and must not gain a guessable second credential.

**Account existence.** `/register`, `/forgot-password` and `/resend-verification` all
answer with a fixed body whether or not the address is known; a duplicate registration
creates nothing, leaves the existing account's credentials untouched, and notifies the
real owner instead. `POST /users/me/email` likewise never reports that a target address is
taken — a collision surfaces only at confirm time, once the caller has proven they can
read that inbox. The residual is `/login`: registering a *free* address sets a password
the caller knows, so a follow-up login still distinguishes the two cases. Closing that
would mean gating login on verification, which the soft gate deliberately does not do.

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
    `accept()` and be added to the test's allow-list. `RATE_LIMIT_ENABLED=false` is a
    development escape hatch only; production refuses to boot with it off.
13. `TRUST_PROXY_HEADERS` must be `true` only behind a reverse proxy that sets
    `X-Forwarded-For`. Exposed directly, a client forges the header and opens a fresh
    bucket per request. Left `false` behind a proxy, every user shares the proxy's bucket.
    It is therefore `bool | None` and production refuses to boot with it unset — there is
    no safe default to guess. Code reads `settings.proxy_headers_are_trusted`, never the
    raw field: on a `None` the field is merely falsy, which is a decision nobody made.
14. The refresh token never reaches JavaScript. It is set and read as an httpOnly cookie
    only: no endpoint accepts one in a request body, none returns one in a response body,
    and the frontend persists no credential. `tests/test_auth_cookie.py` fails on any of
    the three.

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

Two further blocking gates cover what those cannot:

- **Smoke (`ci.yml`).** Boots the built backend image against the four compose services,
  runs `alembic upgrade head` from inside that image, then polls `/health/ready` until all
  of Postgres/Mongo/Qdrant/Redis answer and asserts one public route responds. pytest
  exercises the app over an ASGI transport with fixtures in place of real servers, so a
  runtime dependency missing from `requirements.txt`, a broken migration chain, or a
  settings default that only fails at import time passes every other gate and surfaces
  first on deploy. Draft PRs skip it, like the image build.
- **Integration (`ci.yml`, inside the `smoke` job).** `pytest -m integration` against the
  real Mongo and Qdrant that job already starts. The unit suite replaces both with
  in-memory doubles, and every double hand-defines the methods it answers to — so when
  `qdrant-client` removed `AsyncQdrantClient.search`, the fakes kept replying while
  `retrieve_memories` (which degrades to `[]` on any exception) returned "no results" for
  every user in production, with every gate green. Nothing else runs the service code
  against a real client. `REQUIRE_INTEGRATION_SERVERS=1` turns the fixtures' "no server,
  skip" path into a failure, because a skip here is a green job that asserted nothing.
  The marker is **deselected by default** via `-m 'not integration'` in `pyproject.toml`,
  so a bare `pytest` never reaches for a server — which also means running one of those
  files by path collects nothing unless you pass `-m integration`. The cheap half of the
  same coverage runs in the default suite: `tests/test_qdrant_roundtrip.py` drives
  `AsyncQdrantClient(":memory:")`, which is qdrant-client's own implementation, so filters
  and vector dimensions are genuinely enforced without any infrastructure.
- **Invariants (`security.yml`).** `semgrep --error` over `.semgrep/maestro.yml`:
  hand-written rules for the §9 invariants that no public ruleset knows — unscoped Qdrant
  queries, `follow_redirect_host` outside `repo_intel`, a redirect-following HTTP client
  outside `data_fetch`, a credential reaching a logger, raw SQL outside Alembic. It is a
  **separate job from the advisory `SAST (semgrep)` scan on purpose**: that one is
  `continue-on-error` so pre-existing debt in a public ruleset never fails a contributor's
  PR, while a hit here means an invariant was broken in this PR. Do not merge them.
  A second step re-runs the rules against `.semgrep/fixtures/` and asserts the exact
  per-rule hit count on `bad.py` and zero on `good.py` — a rule that silently stops
  matching otherwise reports zero findings and looks identical to a clean tree. Add a
  fixture case and update the expected counts in the same commit as any rule change.

A rule belongs in `maestro.yml` only when no pytest already enforces it. Rate limits,
WebSocket auth ordering, PAN persistence and domain/frontend parity are covered by
`tests/` and are deliberately not duplicated there.

**Lint policy (deliberate — do not "tighten" without auditing the fallout).** Four
react-hooks v7 rules (`set-state-in-effect`, `refs`, `purity`, `static-components`) are
kept at `warn` in `eslint.config.mjs`: they fire on *correct* code — the canonical
fetch-then-`setState` data-loading pattern and intentional imperative canvas/animation
code. Warnings do not fail CI; only errors do (`eslint` runs without `--max-warnings=0`,
and `next build` treats warnings as non-fatal). Never add `--max-warnings=0` while these
are demoted, and do not enable typescript-eslint's type-checked mode — `tsc --noEmit`
covers type correctness deterministically, without the flakiness of typed lint rules.

What *is* enabled is `eslint-config-next/typescript` (typescript-eslint's `recommended`
set, which needs no type information and so does not cross the line above). It is the
reason `@typescript-eslint/no-explicit-any` is an **error** and an `any` fails the PR.
Keep it spread in: `tsc --noEmit` accepts `any` by definition, so lint is the *only*
gate that sees one — before this config was added, four hand-written `any`s sat in the
tree with every check green. `no-unused-vars` stays at `warn` (Next's own override).

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
- `POSTGRES_URL` / `MONGODB_URL` / `REDIS_URL` / `QDRANT_API_KEY` — production rejects the dev
  defaults, a `CHANGE_ME` left over from `.env.prod.example`, and a guessable password (one
  equal to its username, or a compose default). It deliberately does **not** require
  credentials at all: a MongoDB or Redis reachable only on the compose network legitimately
  runs without auth, and demanding one would refuse a working deploy. `REDIS_URL` is the one
  that most needs this — a wrong password there boots fine and silently degrades every
  throttle to per-process buckets. The error names the variable and never the value: a
  datastore URL is itself a credential, and a boot failure lands in logs and issue reports.
- `TRUST_PROXY_HEADERS` — see rule 13 above. Tri-state like `REFRESH_COOKIE_SECURE`, but for
  the opposite reason: unset resolves to `false` rather than to the secure value, because no
  single value is safe in every topology, so production refuses to boot until the operator
  chooses. Consumers read `settings.proxy_headers_are_trusted`.
- `REFRESH_COOKIE_SECURE` / `REFRESH_COOKIE_SAMESITE` / `REFRESH_COOKIE_DOMAIN` — the
  refresh cookie's attributes (§8, "Token storage"). `SECURE` is deliberately *unset*
  rather than `true`: Safari has historically refused a `Secure` cookie over
  `http://localhost`, so a hard default would break `npm run dev` in one major browser.
  Unset resolves to "on outside development", and the production guard refuses a boot
  that turns it off. `SAMESITE` accepts only `strict` (default) and `lax` — `none` would
  delete the only CSRF control on `/refresh` and `/logout`, so it is rejected at parse
  time rather than documented as discouraged. `DOMAIN` empty means host-only and should
  stay that way; naming a domain shares the session cookie with *every* subdomain, and is
  only for an `app.` / `api.` split under one registrable domain. A plain-HTTP LAN install
  can set `SECURE=false`, but such an origin is not a secure context, so `navigator.locks`
  is unavailable and multi-tab reloads can trip reuse-detection — see
  `docs/CONFIGURATION.md`.
- `HEALTH_DETAIL_TOKEN` — unlocks the per-dependency `checks` map on
  `/health/ready` for callers sending it as `X-Health-Token`. Empty (the default)
  withholds the map from everyone. The probe has to stay publicly reachable for an
  uptime monitor, but *which* backing service is down is reconnaissance: a
  degraded Redis, for instance, announces that rate-limit buckets just fell back
  to process-local counters. The 200/503 status code carries the alertable signal
  without the token, so monitoring needs no credential.
- `ALERT_WEBHOOK_URL` / `ALERT_EMAIL_TO` — the operator alert channels, and the reason a
  default deploy is no longer silent when it breaks. Both empty makes alerting a no-op
  with zero egress (the `SENTRY_DSN` contract), and there is deliberately **no**
  `ALERTING_ENABLED` switch: configuring a channel *is* the enable, so there is no second
  thing to forget. The webhook body carries `text` and `content` in one payload, which is
  what makes a single URL work for both Slack and Discord with no per-platform setting.
  `url_guard` is deliberately not applied — see §8. The channels sit behind the same
  adapter seam as `EmailProvider`/`PaymentProvider`, so a pager integration is one module.
- `ALERT_ERROR_RATE_THRESHOLD` — a *ratio*, not a count, and that is the whole point:
  each uvicorn worker serves roughly 1/N of the traffic, so a raw count threshold would
  silently become N times stricter per worker while a ratio is topology-invariant.
  `ALERT_ERROR_RATE_MIN_REQUESTS` floors it so a handful of overnight requests cannot
  page anyone. Probe traffic is excluded from the counters because `/health/ready` answers
  503 while degraded — counting it would make every dependency outage also trip this
  alert, double-paging for one fault.
- `ALERT_READINESS_FAILURES` — alerts fire on a **state transition**, never on a tick, so
  a dependency that stays down pages once. Two failing ticks to declare degraded (a
  restarting Postgres finishes well inside 120s, and a backend that boots ahead of its
  dependencies must not wake anyone), one good tick to declare recovery. Degraded and
  recovered carry different dedupe keys, so a recovery is never swallowed by the outage's
  cooldown. With Redis configured the send right is claimed with `SET NX EX` so N workers
  page once; on a Redis *error* the claim falls back to process-local, deliberately —
  N workers each reporting a Redis outage beats an outage that silences its own alert.
- `METRICS_TOKEN` — unlocks `GET /metrics` (Prometheus text exposition, hand-rolled over
  in-process counters, no new dependency). Empty answers **404 rather than 401**, so an
  install that never configured it is indistinguishable from one where the route does not
  exist. A *separate* token from `HEALTH_DETAIL_TOKEN` on purpose: this one lives in a
  long-lived scraper config and exposes traffic volume, latency distribution and error
  rate, so their rotations should not be coupled. The `Caddyfile` deliberately does not
  route `/metrics` — reachable from the compose network or an SSH tunnel only, with the
  token as defence in depth rather than the boundary. No `path` label is ever emitted:
  path cardinality is unbounded, and label-exploding a hand-rolled registry is how
  "lightweight" becomes an OOM.
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
- `EMAIL_VERIFICATION_REQUIRED` — the soft gate behind `deps.get_verified_user`: task
  start, API-key create and custom-API-tool writes answer 403 for an unverified account.
  It ships **off**, and that is one decision with `EMAIL_PROVIDER=console`, not two — the
  console sender writes verification mail to the server log, so an enforced gate would lock
  every account on a fresh install with no way through. Enable it only alongside a real
  sender. Its frontend twin is `EMAIL_VERIFICATION_LIVE` in `lib/legal/config.ts`, which
  hides the reminder banner and the "we sent you a link" toast while the gate is off; the
  backend cannot set a build-time constant, so the pair is flipped together, exactly like
  `BILLING_ENABLED`/`BILLING_LIVE`. Nothing is removed meanwhile: `/verify-email`, the
  6-digit code and the resend endpoint all keep working for anyone who wants them.
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
- `CODE_EXECUTION_ENABLED` — the one tool whose blast radius is the *host*, so it defaults
  to `false` and must stay there in production: enabling it requires mounting the Docker
  socket, which hands agent-authored code the ability to start privileged containers
  outside the sandbox. The daemon probe in `code_execution_service` is an availability
  check, not a security boundary — it must never be the only gate, which is exactly why the
  default is off rather than "on, but harmless without Docker".
- `CUSTOM_API_TOOLS_ENABLED` — user-registered HTTP endpoints exposed as agent tools.
  Off by default, like `CODE_EXECUTION_ENABLED` and for the same kind of reason: the
  guard in front of it is real but incomplete. `url_guard` checks that a hostname
  resolves to a globally routable address without pinning that address to the socket, so
  whoever controls the DNS record can answer the check and the connection differently.
  Everywhere else that window is theoretical because the host is a constant of ours;
  this is the only tool where a *user* supplies it. Turning it on says the deployment
  can accept outbound requests to hosts its users choose. Off removes every
  `custom_api__*` action from the enabled set and the executor refuses a second time.
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
- **Revenue:** hosted subscriptions (starter / pro / scale). Paid plans are currently
  **parked**: `BILLING_ENABLED` (backend) and `BILLING_LIVE` (frontend) are both false while
  no real processor is integrated, so `/billing/subscribe` and `/billing/cancel` answer 403
  for everyone except admins — who keep the live flow so the operator can test it — and the
  billing surfaces render "coming soon". Every account runs on the unlimited `free` plan
  meanwhile. Flip both flags together.

Contributions are inbound-licensed under the same terms; see `CONTRIBUTING.md`.

---

## 13. Known Architectural Limit

A hosted instance cannot reach an Ollama server running on a user's own machine — all LLM
calls are made backend-side, so `localhost:11434` resolves to the server itself. The
`ollama` provider works when the operator pulls a chat model into the container, or when a
user runs the whole stack locally. Running everything locally is the intended
self-hosting path and remains free.
