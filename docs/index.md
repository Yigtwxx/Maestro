---
title: Maestro - Self-Hosted AI Agent Orchestration Platform
description: >-
  Maestro is a self-hostable AI agent orchestration platform. One prompt is
  routed to a domain squad that plans, executes and reviews the work. Bring
  your own model keys for 25 providers, or run entirely on a local model.
---

# Maestro

Maestro is a **self-hostable platform for orchestrating teams of AI agents**. It is not a
library you import into your own service — it is the application you deploy. Users sign in,
connect their own model provider keys, and submit a prompt; a routing layer picks the agent
team, decomposes the work, runs it, reviews it, and returns a synthesized answer.

The whole stack runs from one `docker compose` command, and it runs at **zero cost** against
a local Ollama model if you never connect a paid key.

<div class="grid cards" markdown>

- **[Quick Start](quickstart.md)** — the whole platform running locally in two commands.
- **[Architecture](architecture.md)** — how the orchestrator, main agents, subagents and reviewer fit together.
- **[Comparison](comparison.md)** — where Maestro fits against CrewAI, AutoGen, LangGraph and n8n.
- **[Configuration](CONFIGURATION.md)** — every environment variable and what it actually changes.
- **[Deployment](DEPLOYMENT.md)** — running it in production behind a reverse proxy.
- **[API Reference](API.md)** — the REST surface and the agent-layer JSON contracts.

</div>

## What it does

One prompt goes in. The **Orchestrator** classifies the domain and hands off to a **Main
Agent** — a domain expert in finance, software, marketing, SEO, legal and ten other areas —
which builds a subtask plan. **Subagents** execute the atomic pieces, each with a bounded
tool set and a token budget. An optional **Reviewer** grades the output against a weighted
rubric with hard-fail criteria and sends it back with specific issues. The run streams to
the browser over WebSocket while it happens, and the Main Agent can pause mid-task to ask a
clarifying question.

Contracts between the layers are structured JSON, never free text, so a step that fails
fails visibly instead of returning plausible prose.

## What makes it different

Most agent tooling ships as a library: you import it, write the crew or the graph in Python,
and then build everything around it — accounts, key storage, quotas, a UI, a way to watch a
run. Maestro ships that surrounding system as the product.

**Bring your own key.** Users connect credentials for any of **25 chat providers** — OpenAI,
Anthropic, Google Gemini, Groq, DeepSeek, Mistral, xAI, OpenRouter, Together, Perplexity,
Cerebras, Fireworks, Moonshot, Qwen and Z.ai among them, plus a `custom` entry for any
OpenAI-compatible endpoint. Keys are encrypted at rest with AES-256-GCM under a master key
held only in the environment, and are never returned to the frontend. A further **42 service
integrations** (GitHub, X, Slack, Discord, Telegram, Google Places and more) live in the same
vault and drive the connected-API tools.

**It runs free.** With no provider selected, tasks run on a local Ollama model that needs no
key. RAG embeddings are generated locally with `nomic-embed-text`, so the entire pipeline —
routing, execution, review, memory — can run offline with no paid account anywhere.

**Failure is honest.** A blank subagent answer is recorded as a failure, not a silent
success. A run that could not reach a data source says so in a mandatory coverage section
instead of inventing numbers. A crashed worker resumes from a Postgres checkpoint rather
than hanging in "running" forever.

## The unglamorous parts

The things that separate a demo from something you can leave running:

- **Durable execution** — Postgres checkpoints, leases and heartbeats, with a reconciliation
  sweep that resumes or finalizes anything a crashed worker left behind.
- **Token budgets** — hierarchical, enforced per wave and per call, with a quota re-check at
  every step boundary.
- **Per-user isolation** — across PostgreSQL, MongoDB and the Qdrant vector store. Memory
  never crosses accounts.
- **Rate limiting on every route** — enforced by a test that walks the route table and fails
  on any endpoint without an explicit limit.
- **SSRF protection** — every model-supplied URL passes a guard requiring a globally routable
  address, with libcurl SAFE redirect mode on top.
- **Prompt-injection handling** — fetched content is delimited, labelled untrusted, and
  scanned per item before a model ever sees it.

## Getting started

```bash
git clone https://github.com/Yigtwxx/Maestro.git && cd Maestro
docker compose -f docker-compose.quickstart.yml up -d
```

Then open `http://localhost:8080`. Full walkthrough in the **[Quick Start](quickstart.md)**.

## License

Maestro is **fair-code**, released under the [Sustainable Use License
v1.0](https://github.com/Yigtwxx/Maestro/blob/main/LICENSE). Anyone may read, run, modify and
self-host it, including commercially inside their own organization. Reselling it as a hosted
service to third parties is not permitted. Self-hosting is free and always will be.
