---
title: Architecture
description: >-
  How Maestro routes one prompt through an orchestrator, a domain main agent,
  parallel subagents and an optional reviewer - plus the durable execution,
  BYOK encryption and data model underneath.
---

# Architecture

Maestro turns a single prompt into a bounded, resumable, reviewable run. This page covers
the agent hierarchy, what guarantees each layer carries, and the storage and security model
underneath.

## Agent hierarchy

```
User prompt
     │
     ▼
ORCHESTRATOR   Routing only. Classifies the task domain; produces no work itself.
     │
     ▼
MAIN AGENT     Domain expert (finance, software, marketing, ...).
     │         Builds the subtask plan and coordinates subagents.
     ├──────────────┐
     ▼              ▼
SUBAGENT       SUBAGENT      One atomic task each (fetch data, analyze, summarize).
     │              │
     └──────┬───────┘
            ▼
      REVIEWER     Optional. Validates subagent output and sends it back with
                   issues. Bounded by max_review_iterations.
```

Every agent carries a system prompt, an explicit tool list, and an iteration bound.

### The layers

**Orchestrator.** Classifies the prompt into a domain and a complexity tier, and produces
nothing else. Complexity is judged by *how many kinds of work* a request contains, not by how
long it is: `simple` gets one member and skips review entirely, `standard` gets four,
`complex` gets up to eight. Custom agents published by users are merged into the routing
catalog, so the orchestrator can route to a team it did not ship with.

**Main agent.** A domain expert — fifteen built-in squads covering finance, software,
marketing, SEO, legal, data, community, open source and more. It decomposes the request into
a subtask plan, assigns each member a task-specific brief, and declares dependencies between
members. It may pause once to ask the user a clarifying question when the prompt is genuinely
ambiguous.

**Subagents.** Each executes one atomic task with a bounded tool set and its own token
budget. Members that do not depend on each other run in parallel. A member whose answer comes
back blank is recorded as an **error**, not a success — this matters more than it sounds,
because an empty string merged into a synthesis is invisible, and a run where every member
came back blank would otherwise report as completed.

**Reviewer.** Optional and off for simple tasks. It grades output against a structured
rubric with weighted criteria and `hard_fail` conditions, and returns specific issues plus
retry hints rather than a verdict.

### Contracts between layers

Structured JSON, never free text. A subagent returns:

```json
{
  "status": "success | error | needs_review",
  "data": {},
  "metadata": { "tokens_used": 0, "execution_time_ms": 0, "model_used": "string" }
}
```

The reviewer returns:

```json
{ "approved": false, "issues": ["..."], "retry_hints": ["..."] }
```

Free text between layers is how agent systems fail quietly. A schema is how a failed step
stays a failed step.

## Watching a run

The full execution streams to the browser over an authenticated WebSocket. The **Architect**
view draws the live agent graph — which member is running, which tool it just called, which
external provider it reached, and where the edges between them are.

<img src="assets/architect-live.gif" alt="Maestro architect view streaming a live agent run" loading="lazy">

Connected-API calls get their own rail, one edge per member-provider pair, so "two of four
members went to GitHub" stays readable instead of drawing a line per call.

## Durable execution

An agent run is long, expensive and easy to lose. Maestro treats it as a durable step loop
rather than an in-memory coroutine.

- **Checkpoints.** `task_runs`, `task_checkpoints` and `task_questions` in PostgreSQL record
  the state machine (ROUTE → EXECUTE → FINALIZE). A resumed run replays from its last
  checkpoint instead of restarting.
- **Leases and heartbeats.** A worker holds a lease on a run and refreshes it. A
  reconciliation sweep finds runs whose lease expired and either resumes or finalizes them,
  so nothing hangs in "running" forever after a crash.
- **Cross-worker coordination.** With Redis configured, a pub/sub event bus carries the live
  stream, human-in-the-loop answers and cancellations between workers. Booting with more than
  one worker and no Redis is refused at startup rather than silently falling back to a
  process-local bus.
- **Bounded everywhere.** `max_iterations`, `max_review_iterations` and
  `task_timeout_seconds` bound every run. A hierarchical token budget is enforced per wave and
  per call, with a quota re-check at each step boundary.

Terminal states are honest: a run where every member failed is `failed`, a run where some
failed is `completed_with_warnings` and carries a "Known gaps" section naming what is missing.

## Tools

Subagents get a bounded tool set resolved per run:

| Tool | What it does |
|---|---|
| `web_search` | Search with an automatic query-simplification ladder, invisible to the tool budget |
| `data_fetch` | Fetch a page with TLS impersonation, optionally extracting by CSS selector |
| `repo_intel` | GitHub repository activity, contributors, releases, issue close times |
| `social_search` | X/Twitter search |
| `community_read` | Discord, Slack or Telegram channel reading |
| `places_intel` | Google Places lookups |
| `code_execution` | Sandboxed execution, off by default in production |

A **missing service key degrades rather than stops.** The tool is withheld from the enabled
set, the squad falls back to `web_search`, and a mandatory coverage section — enforced by a
`hard_fail` review criterion — states plainly what could not be reached. Stopping instead
would make every connected squad unusable for the majority of accounts, which hold no service
keys at all. A missing **brain** key is different: that stops the task, because there is
nothing to run.

## Storage

Three stores, each doing what it is good at.

**PostgreSQL** — users, encrypted API keys, refresh-token families, subscriptions, the
append-only `usage_records` quota ledger, and durable task state. Schema changes go through
Alembic; SQL is never run by hand.

**MongoDB** — step-by-step `agent_logs` (sequence-ordered, the source for stream replay),
marketplace items, task sessions, custom agent configurations, and trace spans with a TTL.

**Qdrant** — `conversation_memories` and `document_chunks`. Vectors are scoped per user and
deleted on account purge.

Data isolation is per user across all three. Memory never crosses accounts.

## Security model

**BYOK.** Provider keys are encrypted with AES-256-GCM under a master key held only in the
environment. Only `provider` and `label` are ever returned to the frontend — never the key.
Credentials are decrypted once per run at the engine edge and handed to the agent layer as a
value whose string representation renders provider names only, so a traceback or a log record
cannot print a secret.

**Outbound requests.** Every user- or model-supplied URL passes a guard: http(s) only, no
embedded credentials, and every resolved address must be globally routable. Redirects use
libcurl's SAFE mode, which refuses a hop to an internal address before the request is made,
and the landed URL is re-validated afterwards. The connected-API tools have no SSRF surface
at all — every host is a compile-time constant — but any value reaching a URL *path*, such as
a repository slug or a channel id, is pattern-matched before a request can be built.

**Prompt injection.** Fetched content is delimited, labelled untrusted, and scanned before a
model sees it. Because a commit message or a social post is attacker-authored, connected-API
results are scanned and dropped **individually** rather than blanking a whole block.
Marketplace submissions are security-scanned on publish, custom system prompts are scanned on
write and sandboxed inside an `<agent_persona>` boundary at execution time, and installed
marketplace agents never touch the installing user's keys directly.

**Everything else.** JWT on every non-public endpoint including WebSockets, which
authenticate *before* accepting the connection. An explicit rate limit on every route,
enforced by a test that walks the route table and fails on any endpoint without one. Pydantic
v2 validation on every input. Refresh-token rotation with reuse detection that revokes an
entire session family. Optional TOTP 2FA with Argon2-hashed single-use recovery codes.

Full policy and the reasoning behind each decision: [Security](SECURITY.md).

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (App Router), React, TypeScript, Tailwind |
| Backend | FastAPI, Python 3.11+ |
| Relational | PostgreSQL via SQLAlchemy async, Alembic migrations |
| Documents | MongoDB via Motor |
| Vectors | Qdrant |
| Cache and bus | Redis |
| Realtime | WebSocket |
| Local models | Qwen3 and `nomic-embed-text` via Ollama |
| Reverse proxy | Caddy, single origin, automatic TLS |

Next: [Configuration](CONFIGURATION.md) for what each setting changes, or
[Deployment](DEPLOYMENT.md) for running it in production.
