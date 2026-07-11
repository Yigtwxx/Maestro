# Deployment

Maestro deploys as a single Docker Compose stack on one host: Postgres, MongoDB,
Qdrant, an embedding server, the API, the web app, and Caddy for TLS. Caddy is
the only service that opens a port. Everything reachable from the internet is
served from **one origin**, which is why the frontend image carries no domain
and there is no CORS to configure.

Any VM with 4 GB of RAM will do. Oracle Cloud's Always Free Ampere instance
(4 ARM cores, 24 GB) runs it comfortably at no cost; the published images are
built for `arm64` as well as `amd64` on every release tag.

## Why not Vercel, Railway, or a serverless platform

The API cannot run as a serverless function:

- **WebSockets.** `/api/v1/tasks/{id}/stream` and `/api/v1/architect/live` are
  long-lived upgrades. Vercel Functions do not serve them.
- **Task duration.** `TASK_TIMEOUT_SECONDS` defaults to 1800. Vercel's ceiling
  is 300 seconds.
- **Background work.** A task keeps running after the HTTP response is returned.
  A serverless runtime freezes or kills the process at that point.

The frontend alone would sit happily on Vercel. See
[Running the frontend elsewhere](#running-the-frontend-elsewhere) if you want
that split.

---

## First deploy

### 1. Prepare the host

Install Docker Engine with the Compose plugin (**v2.17 or newer** — the stack
relies on `service_completed_successfully`):

```bash
curl -fsSL https://get.docker.com | sh
docker compose version
```

Point a DNS `A` record at the host and open ports 80 and 443.

### 2. Place the deployment files

Only three files live on the server, and one of them holds every secret you
have. None of them come from a `git clone`:

```bash
sudo mkdir -p /opt/maestro && cd /opt/maestro
# copy docker-compose.prod.yml, Caddyfile and .env.prod.example from the repo
cp .env.prod.example .env.prod
chmod 600 .env.prod
```

### 3. Fill in `.env.prod`

Generate real secrets — the defaults in `.env.example` are placeholders and the
app will start with them:

```bash
openssl rand -hex 32        # JWT_SECRET
openssl rand -base64 32     # API_KEY_MASTER_KEY  (AES-256-GCM, encrypts BYOK keys)
openssl rand -base64 24     # POSTGRES_PASSWORD, MONGO_PASSWORD, QDRANT_API_KEY
```

Set `DOMAIN` to your hostname, then substitute the passwords you generated into
`POSTGRES_URL` and `MONGODB_URL`. Keep `?authSource=admin` on the Mongo URL: the
root user cannot authenticate without it and index creation fails at startup.

### 4. Bring it up

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
docker compose -f docker-compose.prod.yml --env-file .env.prod ps
```

`migrate` and `ollama-pull` run once and exit `0`; the rest should report
`healthy` or `running`. `backend` does not start until `migrate` succeeds, so a
broken migration leaves the previous release serving rather than starting a new
one against an unmigrated schema.

Caddy requests a certificate on first request. Then:

```bash
curl https://your-domain/health          # {"status":"ok"}
```

### 5. Seed the marketplace (optional, once)

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  run --rm --no-deps backend python -m app.scripts.seed_marketplace
```

### 6. Schedule the account purge

Deletion requests are irreversible after a 30-day grace period, and something
has to do the purging. Compose has no scheduler, so use the host's:

```cron
0 3 * * * cd /opt/maestro && docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm --no-deps backend python -m app.scripts.purge_deleted_accounts
```

The script takes a Postgres advisory lock and is idempotent, so an overlapping
run is harmless.

---

## Continuous deployment

Pushing a `v*` tag triggers `.github/workflows/deploy.yml`, which SSHes to the
host and runs `docker compose pull && up -d`. Migrations are part of the stack,
not a separate step.

Repository secrets:

| Secret | Purpose |
| --- | --- |
| `DEPLOY_HOST` | Server hostname or IP |
| `DEPLOY_USER` | SSH user with docker access |
| `DEPLOY_SSH_KEY` | Private key for that user |

Add required reviewers to the `production` environment in repository settings to
gate rollouts behind an approval.

Images are published to `ghcr.io/yigtwxx/maestro-backend` and
`ghcr.io/yigtwxx/maestro-frontend` on every push to `main` (amd64) and every
release tag (amd64 + arm64). If you keep the packages private, run
`docker login ghcr.io` once on the host with a read-only token.

### Rolling back

Images are immutable per tag, so a rollback is a re-deploy of the previous one:

```bash
cd /opt/maestro
IMAGE_TAG=1.2.2 docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

Note that this does **not** roll back the database. Migrations must be
backward-compatible with the release before them, or a rollback needs
`alembic downgrade` run by hand first.

---

## Models

The `ollama` service exists for one reason: **embeddings**. RAG retrieval and
document upload call it no matter which chat provider a user picked, so without
it document upload fails and memory retrieval silently degrades. It pulls only
`nomic-embed-text` (~275 MB), which is fast on CPU.

**No chat model is served by default.** Users bring their own key (Gemini,
OpenAI, Anthropic). To offer the free local tier as well, and only if the host
has several GB of RAM to spare:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec ollama ollama pull qwen3.5:9b
```

> A user's own Ollama, running on their laptop, **cannot** be used by a hosted
> instance. Every LLM call is made by the backend, so `localhost:11434` is the
> server, not the visitor's machine. The `ollama` provider only works when the
> operator has pulled a chat model into the container above, or when the whole
> stack is running on the user's own machine.
>
> Until a chat model is pulled, picking the `ollama` provider does not raise a
> visible error: every subtask fails with `ollama chat failed`, and the task
> still reports `completed` with the answer `"No successful subtask output."`
> Consider hiding the provider until you have pulled a model.
>
> If you want to point the backend at an Ollama on the host rather than in a
> container, set `FREE_MODEL_ENDPOINT=http://host.docker.internal:11434/v1` and
> start that Ollama with `OLLAMA_HOST=0.0.0.0` — bound to loopback it will
> refuse the connection.

---

## Security notes

- **`CODE_EXECUTION_ENABLED=false`** in production. The tool shells out to the
  `docker` CLI, so enabling it means mounting `/var/run/docker.sock` into the
  backend — which hands agent-generated code the ability to start privileged
  containers on the host. The tool detects the missing daemon and disables
  itself cleanly, so leaving it off costs nothing but that one feature.
- **`PAYMENT_PROVIDER=mock`.** No real money moves, and no real card should ever
  be entered: `payment_methods` would fall under PCI scope. Ship a real
  processor adapter before advertising billing.
- FastAPI's Swagger UI, ReDoc and `/openapi.json` are disabled when
  `ENVIRONMENT=production`.
- Datastores publish no ports. They are reachable only from the compose network.
- `.env.prod` holds `API_KEY_MASTER_KEY`, which decrypts every user's stored
  provider keys. Losing it means losing them; leaking it means leaking them.

---

## Monitoring

The stack ships a lightweight observability setup: dependency health probes,
structured logs, and optional error tracking. No metrics stack (Prometheus /
Grafana) runs on the host — deliberately, to keep RAM free on a single small box.

### Health probes

Two endpoints, both reachable through Caddy without authentication:

- **`GET /health`** — liveness. Returns `{"status":"ok"}` without touching any
  dependency. The Docker `HEALTHCHECK` uses this; keep an uptime monitor on it.
- **`GET /health/ready`** — readiness. Pings Postgres, Mongo, Qdrant and Redis
  and returns `200 {"status":"ready", ...}` or, if any required service is down,
  `503 {"status":"degraded","checks":{...}}`.

Point a free uptime monitor (UptimeRobot, Better Stack, …) at both:

```
https://<your-domain>/health        # expect 200 — process is up
https://<your-domain>/health/ready   # expect 200 — dependencies are up
```

Set a 1–3 minute interval and an email/Slack alert on a non-200 response. The
`/health/ready` monitor catches "the API is running but Mongo/Qdrant is
unreachable" — a state `/health` alone would miss.

### Error tracking (Sentry)

Optional and off by default. To enable:

1. Create a project at [sentry.io](https://sentry.io) (free tier is enough) and
   copy its DSN.
2. Set `SENTRY_DSN=<dsn>` in `.env.prod` (see also `SENTRY_ENVIRONMENT`,
   `SENTRY_TRACES_SAMPLE_RATE`) and restart the backend.
3. Configure an alert rule + email in the Sentry project.

Unhandled errors — including background task failures, which never reach the
request handler — are reported automatically via the logging integration. PII is
scrubbed before events leave the process: `send_default_pii=False` plus a
`before_send` hook that masks credential headers and drops request bodies, so
API keys, prompts and card data are never sent. With `SENTRY_DSN` empty, Sentry
is a no-op and the app makes no external calls.

### Logs

`LOG_FORMAT=json` (the production default in `.env.prod.example`) emits one JSON
object per line — pipe `docker compose logs` into any aggregator. `LOG_FORMAT=text`
keeps the readable format for local debugging.

---

## Analytics (optional, self-hosted Umami)

Off by default. When enabled it is first-party (data never leaves the host),
cookieless, consent-gated (the notice becomes a real Accept/Reject, the script
loads only after an explicit yes), and counts the public marketing pages only —
never the signed-in app. The Umami dashboard is deliberately not exposed to the
internet; only `/a/script.js` and `/a/api/send` pass through Caddy.

### Enabling

1. In `.env.prod`, set:

   ```env
   COMPOSE_PROFILES=analytics
   UMAMI_DB_PASSWORD=<openssl rand -base64 24>
   UMAMI_APP_SECRET=<openssl rand -hex 32>
   ```

2. `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d`.
   `umami-db-init` runs once and creates the `umami` role and database inside
   the existing Postgres (idempotent — safe on an already-initialized `pgdata`
   volume, which is why an initdb script would not work); `umami` then runs its
   own Prisma migrations and comes up healthy.

3. Reach the dashboard through an SSH tunnel — it listens on the host's
   loopback only:

   ```bash
   ssh -N -L 3001:127.0.0.1:3001 <user>@<host>
   ```

   Open `http://localhost:3001`, log in as `admin` / `umami`, and **change that
   password immediately**. Then Settings → Websites → Add website (name:
   maestro, domain: your `DOMAIN`) and copy the Website ID.

4. Put the id in `.env.prod` as `UMAMI_WEBSITE_ID=<id>` and restart the
   frontend so it picks up the new env:

   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.prod up -d frontend
   ```

Visitors now get the Accept/Reject notice; views appear in the dashboard only
for those who accept, and only on marketing pages. Consent can be changed any
time at the bottom of `/cookies`.

### Enabling on an existing deployment

Copy the updated `docker-compose.prod.yml` and `Caddyfile` to the host first,
then follow the steps above. `up -d` recreates Caddy with the `/a/*` route (or
reload in place: `docker compose -f docker-compose.prod.yml --env-file .env.prod
exec caddy caddy reload --config /etc/caddy/Caddyfile`). Nothing else in the
stack restarts.

### Disabling

Set `COMPOSE_PROFILES=` and `UMAMI_WEBSITE_ID=` back to empty and `up -d
--remove-orphans`. The frontend reverts to the informational notice; the
`umami` database stays in `pgdata` (harmless) unless you drop it.

---

## Backups

Everything durable lives in named volumes: `pgdata`, `mongodata`, `qdrantdata`.
Postgres is the one that matters most — it holds accounts, subscriptions and the
quota ledger.

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  exec -T postgres pg_dump -U maestro maestro | gzip > "maestro-$(date +%F).sql.gz"
```

If analytics is enabled, the `umami` database lives in the same instance but is
owned by the `umami` role, so it needs its own dump line (or accept the loss of
anonymous view counts and skip it — nothing else depends on them):

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  exec -T -e PGPASSWORD="$UMAMI_DB_PASSWORD" postgres \
  pg_dump -U umami umami | gzip > "umami-$(date +%F).sql.gz"
```

Back up `.env.prod` separately and somewhere else. A Postgres dump without
`API_KEY_MASTER_KEY` cannot decrypt any BYOK key it contains.

---

## Local smoke test

Verify the production stack on your own machine before touching a server. Set
`DOMAIN=http://localhost` in `.env.prod` — the `http://` prefix tells Caddy to
serve plain HTTP and skip certificate provisioning.

```bash
cp .env.prod.example .env.prod    # DOMAIN=http://localhost, fill the secrets
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Then check, in order:

1. `docker compose -f docker-compose.prod.yml --env-file .env.prod ps` —
   `migrate` and `ollama-pull` `exited (0)`, the rest `healthy`.
2. `curl http://localhost/health` → `{"status":"ok"}`.
3. `curl http://localhost/api/v1/billing/plans/public` → JSON.
4. Open `http://localhost/pricing`. Prices must render — the "unreachable"
   banner means the server-side fetch failed.
5. Open `http://localhost/docs`. You should get the marketing page, not Swagger.
6. Register, log in, start a task. In DevTools → Network → WS, the connection to
   `/api/v1/tasks/<id>/stream` must report **101 Switching Protocols** and
   stream events.
7. Upload a `.txt` under Documents. A `200` proves the embedding service is
   wired up.
8. If testing analytics (`COMPOSE_PROFILES=analytics` + the `UMAMI_*` vars): in
   a fresh browser profile the notice must show Accept/Reject with **no**
   `/a/script.js` request before you answer. After Accept, each marketing page
   navigation sends one `POST /a/api/send`; navigating into `/login` or
   `/dashboard` must send **zero**. `curl http://localhost/api/send` must still
   reach the backend (a FastAPI 404/405, not Umami) — that proves the `/a`
   matcher split.

---

## Running the frontend elsewhere

The frontend image is domain-agnostic, and the code supports a split deploy
without a rebuild. On Vercel (or any Node host), set:

| Variable | Value |
| --- | --- |
| `BACKEND_ORIGIN` | `https://api.your-domain` — proxies `/api/*`, keeping the browser same-origin |
| `INTERNAL_API_ORIGIN` | `https://api.your-domain` — used by the server-rendered `/pricing` and `/templates` |
| `NEXT_PUBLIC_WS_BASE_URL` | `wss://api.your-domain` — WebSockets cannot be proxied through Next rewrites |
| `SITE_URL` | `https://your-domain` — origin for canonical URLs, `sitemap.xml`, OG tags |

The backend then needs `CORS_ORIGINS` set to the app's origin, since the
WebSocket handshake no longer shares it. The API itself still has to run as a
long-lived container somewhere.

`SITE_URL` is what keeps the image domain-agnostic despite SEO needing an
absolute origin: it is read at request time, not baked in, so the same image
serves any domain and changing it needs only a container restart, not a
rebuild. It is deliberately not `NEXT_PUBLIC_` (that would inline it at build
time) and not derived from `DOMAIN` (which may carry a scheme). Unset, the
pages fall back to a placeholder domain — visibly wrong rather than silently
plausible.
