# Configuration

Every setting is read from an environment variable; the `.env` file is gitignored and never
committed. In production the backend refuses to boot with placeholder or weak secrets.

Generate the two required secrets before the first run:

```bash
openssl rand -hex 32       # JWT_SECRET
openssl rand -base64 32    # API_KEY_MASTER_KEY (32-byte AES-256 master key)
```

`.env.example` carries the full annotated list; `.env.prod.example` is the production
variant. The tables below group the settings by concern.

## Databases

| Variable | Description | Default |
|---|---|---|
| `POSTGRES_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://maestro:maestro@localhost:5433/maestro` |
| `MONGODB_URL` | MongoDB connection string. Port 27018, not the stock 27017 — a natively-installed MongoDB binds loopback and beats Docker's wildcard bind, so 27017 can silently reach the wrong server | `mongodb://localhost:27018` |
| `MONGODB_DB_NAME` | MongoDB database name | `maestro` |
| `QDRANT_URL` | Qdrant vector DB address | `http://localhost:6333` |
| `QDRANT_API_KEY` | Qdrant API key (optional for local) | — |

## Security & auth

| Variable | Description | Default |
|---|---|---|
| `JWT_SECRET` | JWT signing secret — random and confidential, min 32 chars in production | — |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime | `7` |
| `API_KEY_MASTER_KEY` | AES-256-GCM master key for encrypting BYOK keys (32 bytes, base64 or hex) | — |
| `CORS_ORIGINS` | Allowed frontend origins (comma-separated) | `http://localhost:3000` |
| `LLM_SSRF_GUARD_ENABLED` | Validate custom provider endpoints (http(s), credential-free, public addresses only); disable only on a fully self-hosted stack | `true` |

## Rate limiting

| Variable | Description | Default |
|---|---|---|
| `REDIS_URL` | Redis for shared sliding-window buckets; empty falls back to in-process memory (single dev worker) | — |
| `RATE_LIMIT_ENABLED` | Master throttle switch; never `false` in production | `true` |
| `TRUST_PROXY_HEADERS` | Only `true` behind a proxy that appends `X-Forwarded-For` (e.g. Caddy) | `false` |

`TRUST_PROXY_HEADERS` cuts both ways: exposed directly to the internet, a client forges the
header and opens a fresh bucket per request; left `false` behind a proxy, every user shares
the proxy's single bucket.

## Models & embeddings

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

## Agent tools

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
| `CODE_EXECUTION_ENABLED` | Docker code sandbox. Off by default and self-host only: it needs access to the Docker daemon, so enabling it on a hosted deployment puts the host in the tool's blast radius | `false` |
| `CODE_EXECUTION_IMAGE` | Sandbox container image | `python:3.12-slim` |
| `CODE_EXECUTION_TIMEOUT_SECONDS` | Per-run timeout | `30` |
| `CODE_EXECUTION_MEMORY_LIMIT` / `CODE_EXECUTION_CPUS` | Sandbox resource limits | `512m` / `1` |
| `CODE_EXECUTION_MAX_USES_PER_SUBTASK` | Runs per subtask | `3` |

A missing *service* key is deliberately not fatal: the tool is withheld from the squad, the
members fall back to `web_search`, and the answer's mandatory data-coverage section states
what could not be reached. A missing *brain* key stops the task and tells the user.

## Agent limits & execution

| Variable | Description | Default |
|---|---|---|
| `MAX_ITERATIONS` | Max steps per Subagent | `10` |
| `MAX_REVIEW_ITERATIONS` | Reviewer ↔ Subagent loop limit | `3` |
| `TASK_TIMEOUT_SECONDS` | Total timeout per task (whole pipeline) | `1800` |
| `SUBAGENT_MAX_PARALLEL` | Concurrent Subagents per task | `3` |
| `SUBAGENT_MAX_TOOL_CALLS` | Total tool calls (all kinds) per subtask | `6` |
| `REVIEWER_FAIL_MODE` | What a reviewer crash means for the subtask: `warn`, `approve`, or `reject` | `warn` |
| `TASK_RETENTION_DAYS` | Mongo TTL on task sessions + agent logs; dashboard metrics cover this window | `30` |

## Payments

| Variable | Description | Default |
|---|---|---|
| `PAYMENT_PROVIDER` | Payment gateway; only `mock` is implemented (Luhn/BIN validation, moves no real money) | `mock` |
| `BILLING_ENABLED` | Whether paid plans are reachable. `false` parks them: subscribe/cancel answer 403 for everyone but admins, and every account runs on the unlimited `free` plan. Flip together with `BILLING_LIVE` in `frontend/src/lib/legal/config.ts` | `false` |
| `GRANT_ADMIN_EMAILS` | Comma-separated accounts `python -m app.scripts.grant_admin` promotes to admin | *(empty)* |

Plan prices and quotas are product constants in `backend/app/core/constants.py`, not
environment variables.

## Transactional email

| Variable | Description | Default |
|---|---|---|
| `EMAIL_PROVIDER` | `console` logs messages (dev / self-host — verification links are read from the log); `resend` sends via the Resend API | `console` |
| `RESEND_API_KEY` | Required when `EMAIL_PROVIDER=resend`; checked at boot in production | — |
| `EMAIL_FROM` | From header for outgoing mail | `Maestro <noreply@maestro.example.com>` |
| `SITE_URL` | Base URL the backend uses to build verification / reset links | `http://localhost:3000` |
| `EMAIL_VERIFICATION_REQUIRED` | Soft-gates task start and API-key creation until the email is verified | `true` |

## App & observability

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

---

Deployment-specific settings — domain, TLS, backups, the purge cron — live in
[`DEPLOYMENT.md`](./DEPLOYMENT.md). Architectural rationale for the non-obvious settings is
in [`CLAUDE.md`](https://github.com/Yigtwxx/Maestro/blob/main/CLAUDE.md) §11.
