# API Reference

The full OpenAPI schema is served at `http://localhost:8000/docs` while the backend is
running (disabled when `ENVIRONMENT=production`). Every non-public endpoint requires JWT
authentication and carries an explicit rate limit; request and response bodies are
validated with Pydantic v2.

## Endpoints

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

## Agent contracts

Layers exchange structured JSON, never free text.

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

## Database schemas

- **PostgreSQL** — relational data: `users`, `api_keys` (encrypted), `refresh_tokens`
  (session families), `email_tokens`, `recovery_codes` (2FA), `subscriptions`,
  `payment_methods` (brand + last4 + expiry only — raw PAN is never stored), the
  append-only `usage_records` quota ledger, and the durable task engine tables
  `task_runs` / `task_checkpoints` / `task_questions`.
- **MongoDB** — dynamic data: `agent_logs`, `marketplace_items` plus reviews, moderation
  reports and the admin audit log, `task_sessions`, `agent_configurations`, `trace_spans`
  (TTL-bound).
- **Qdrant** — vector data: `conversation_memories`, `document_chunks`.

Memory and vectors are partitioned per user; data never crosses accounts.

See [`CLAUDE.md`](../CLAUDE.md) §6 for column-level detail.
