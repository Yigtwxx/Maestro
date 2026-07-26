---
title: Quick Start
description: >-
  Run the whole Maestro stack locally in two commands with Docker Compose, or
  from source with the dev scripts. No paid API key is required - tasks can run
  on a local Ollama model.
---

# Quick Start

Two commands, no build, no configuration. The published images run the whole stack behind a
local reverse proxy.

```bash
git clone https://github.com/Yigtwxx/Maestro.git && cd Maestro
docker compose -f docker-compose.quickstart.yml up -d
```

Then open **`http://localhost:8080`** and register.

The first run pulls the images and the embedding model, so give it a few minutes; afterwards
it starts in seconds. If something already owns port 8080, set `MAESTRO_PORT=8090` in front
of the command — it moves the proxy and the generated links together.

!!! warning "The quickstart file is a trial environment, not a deployment"
    It uses fixed, publicly known credentials and binds only to `127.0.0.1`. For anything
    reachable from outside your machine, follow [Deployment](DEPLOYMENT.md) instead.

## Make your account usable

Registration alone cannot start tasks: the platform gates task start on an active plan, and
the bundled payment gateway is a mock. Make your account unmetered instead:

```bash
docker compose -f docker-compose.quickstart.yml exec backend \
  python -m app.scripts.grant_admin --email you@example.com
```

This sets the admin role, marks the address verified, and seeds a plan — enough to use every
feature locally.

!!! tip "Where is the verification email?"
    The default email provider is `console`, which writes the message to the backend log
    rather than sending it. `docker compose -f docker-compose.quickstart.yml logs backend`
    shows the verification and password-reset links.

## Connect a model

Add a provider key under **Settings → API Keys**. [Gemini's free
tier](https://aistudio.google.com/apikey) needs no credit card and is the fastest way to a
working task.

RAG embeddings already run locally, so no key is needed for conversation memory or document
upload.

To run chat locally as well — no key anywhere in the pipeline:

```bash
docker compose -f docker-compose.quickstart.yml exec ollama ollama pull qwen3.5:9b
docker compose -f docker-compose.quickstart.yml restart backend
```

Now submit a prompt. Open the **Architect** view while it runs to watch the orchestrator
route the task, the main agent plan it, and the subagents execute in parallel.

!!! note "A local 9B model is a real model, with real limits"
    It works end to end, but it reasons slowly and will occasionally spend an entire output
    budget thinking and return nothing. Maestro reports that as a failed subtask rather than
    a silent success, so you will see it. A hosted provider key removes the ceiling.

## Running from source

For development rather than a trial. **Prerequisites:** Docker (for Postgres, Mongo, Qdrant
and Redis), Python 3.11+, Node.js 20+, and [Ollama](https://ollama.com) for the local model
and embeddings.

The dev scripts bring the whole stack up in one terminal — infrastructure, then the backend
(virtualenv, dependencies, `alembic upgrade head`, marketplace seed, uvicorn), then the
frontend. Ctrl+C stops everything.

```bash
./scripts/dev.ps1     # Windows
./scripts/dev.sh      # macOS / Linux
```

The backend serves on `http://localhost:8000` (OpenAPI at `/docs`), the frontend on
`http://localhost:3000`.

??? example "Manual setup, step by step"

    ```bash
    # 1. Environment
    cp .env.example .env                 # fill in JWT_SECRET and API_KEY_MASTER_KEY
    openssl rand -hex 32                 # JWT_SECRET
    openssl rand -base64 32              # API_KEY_MASTER_KEY

    # 2. Infrastructure
    docker compose up -d                 # postgres, mongo, qdrant, redis

    # 3. Local models
    ollama serve                         # separate terminal
    ollama pull qwen3.5:9b
    ollama pull nomic-embed-text

    # 4. Backend
    cd backend
    python -m venv .venv
    # Windows: .venv\Scripts\activate | macOS/Linux: source .venv/bin/activate
    pip install -r requirements.txt
    alembic upgrade head
    uvicorn app.main:app --reload        # http://localhost:8000

    # 5. Frontend
    cd frontend
    npm install
    npm run dev                          # http://localhost:3000
    ```

## Verifying a change

CI runs both suites on every push and pull request to `main`. Locally:

```bash
cd backend  && pytest && ruff check . && ruff format --check .
cd frontend && npm run lint && npm run type-check && npm run build
```

A change is done when all of those pass. See [Contributing](CONTRIBUTING.md) for the full
standards, and [Configuration](CONFIGURATION.md) for every environment variable.
