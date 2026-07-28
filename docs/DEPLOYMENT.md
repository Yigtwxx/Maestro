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

#### Oracle Cloud (Always Free Ampere) specifics

The reference free host is a `VM.Standard.A1.Flex` instance (4 OCPU / 24 GB,
arm64). Three things bite on Oracle that don't elsewhere:

- **Ingress is blocked at two layers.** Add an ingress rule for TCP 80 and 443
  in the VCN **Security List** (or NSG) *and* open the host firewall — Oracle's
  Ubuntu images ship iptables rules that REJECT everything but SSH, and `ufw`
  does not remove them:

  ```bash
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
  sudo netfilter-persistent save
  ```

- **A1 capacity is scarce.** "Out of capacity" on launch is normal for Always
  Free accounts: retry, try another availability domain, or upgrade the account
  to Pay As You Go — Always Free resources stay free, but provisioning gets
  priority.
- **Use a release tag, not `latest`.** arm64 app images are only built on `v*`
  release tags; pushes to `main` publish amd64 only. On an Ampere host,
  `IMAGE_TAG` in `.env.prod` must always be a release version or the pull will
  fail (or run nothing) for lack of an arm64 manifest.

### 2. Place the deployment files

Only four files live on the server, and one of them holds every secret you
have. None of them come from a `git clone`:

```bash
sudo mkdir -p /opt/maestro && cd /opt/maestro
# copy docker-compose.prod.yml, Caddyfile, scripts/backup.sh and
# .env.prod.example from the repo
cp .env.prod.example .env.prod
chmod 600 .env.prod
chmod +x backup.sh
```

After the first placement, `deploy.yml` keeps `backup.sh` in sync with the
repo on every tagged rollout; the other three files are host-managed only.

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

### 7. Schedule the backups

See [Backups](#backups) below for what gets backed up and how restore works;
the cron line lives there next to the rest of the backup documentation.

---

## Continuous deployment

Pushing a `v*` tag triggers `.github/workflows/deploy.yml`, which SSHes to the
host and runs `docker compose pull && up -d`. Migrations are part of the stack,
not a separate step.

After `up -d` the workflow **gates on health**: it polls the backend's
`/health/ready` and the frontend's `/` from inside the containers for up to
~3 minutes. If the gate fails, it dumps the last container logs into the
Actions output, **rolls back automatically** to the image tag that was serving
before the rollout, and fails the job. A release that starts but cannot serve
never stays up just because `docker compose up -d` exited 0. (On a first
deploy there is nothing to roll back to; the job just fails loudly.)

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

A rollout whose health gate fails is rolled back automatically (see above).
For a manual rollback — images are immutable per tag, so it is a re-deploy of
the previous one:

```bash
cd /opt/maestro
IMAGE_TAG=1.2.2 docker compose -f docker-compose.prod.yml --env-file .env.prod \
  up -d --no-deps backend frontend
```

`--no-deps` matters: a plain `up -d` re-runs the `migrate` one-shot with the
*old* image, whose alembic cannot resolve a head revision created by the newer
release — the migration fails and `backend` (which waits on it) never starts.
Skipping `migrate` leaves the schema where it is.

Note that this does **not** roll back the database. Migrations must be
backward-compatible with the release before them, or a rollback needs
`alembic downgrade` run by hand first.

---

## Models

The `ollama` service exists for one reason: **embeddings**. RAG retrieval and
document upload call it no matter which chat provider a user picked, so without
it document upload fails and memory retrieval silently degrades. It pulls only
`nomic-embed-text` (~275 MB), which is fast on CPU.

**No chat model is served.** Users bring their own key (Gemini, OpenAI,
Anthropic). `.env.prod` sets `OLLAMA_CHAT_ENABLED=false`, so picking the free
local model rejects the task start with an explicit 400 telling the user to
connect a key or self-host — instead of spawning a task whose every subtask
fails with `ollama chat failed` and still reports `completed`. The UI shows the
same guidance next to the provider selector.

> A user's own Ollama, running on their laptop, **cannot** be used by a hosted
> instance. Every LLM call is made by the backend, so `localhost:11434` is the
> server, not the visitor's machine. The free tier only works when the whole
> stack runs on the user's own machine — or if you, the operator, opt in below.

To actually offer the free chat tier from the server, all three steps are
required:

1. Raise the `ollama` service memory limit in `docker-compose.prod.yml` well
   above its default `2g` (a 9B model needs roughly 8 GB to load; the limit
   exists for the embedding-only default and the model will be OOM-killed
   inside it).
2. Pull a chat model:
   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.prod exec ollama ollama pull qwen3.5:9b
   ```
3. Set `OLLAMA_CHAT_ENABLED=true` in `.env.prod` and `up -d backend`.

If you want to point the backend at an Ollama on the host rather than in a
container, set `FREE_MODEL_ENDPOINT=http://host.docker.internal:11434/v1` and
start that Ollama with `OLLAMA_HOST=0.0.0.0` — bound to loopback it will
refuse the connection.

---

## Scaling to multiple workers

The backend defaults to a single uvicorn worker. To run more, set
`WEB_CONCURRENCY` (the Dockerfile passes it to `uvicorn --workers`):

```env
WEB_CONCURRENCY=4
```

**Multi-worker (>1) requires `REDIS_URL` to be set — enforced at boot.** The
backend refuses to start (clear config error in the logs) when
`WEB_CONCURRENCY>1` and `REDIS_URL` is empty, instead of silently degrading to
process-local state. With more than one worker,
task execution, the live event stream, human-in-the-loop answers, and task
cancellation must coordinate across processes; they do so over Redis:

- **Event bus** — an event emitted by the worker running a task is published on
  `maestro:events:{task_id}` so a WebSocket subscribed on any worker receives it.
  With no `REDIS_URL`, the bus is in-process and a client connected to a
  different worker sees no live updates.
- **Control channel** — cancel and HITL answers are routed on
  `maestro:ctrl:{task_id}` to whichever worker owns the task.
- **Reconciliation** — every worker sweeps for tasks orphaned by a crashed peer
  and atomically re-claims them (a single conditional `UPDATE` guarantees exactly
  one winner), so a mid-run crash never leaves a task stuck at `running`.

Durable state (Postgres `task_runs`/checkpoints, Mongo `agent_logs`) is always
authoritative, so a Redis outage degrades liveness (missed live ticks, slower
cancel) but never correctness — clients recover on reconnect via the
`?after_seq=` snapshot cursor. Leave `WEB_CONCURRENCY` unset (single worker) if
you are not running Redis.

---

## Security notes

- **`CODE_EXECUTION_ENABLED`** ships `false` and must stay that way in
  production. The tool shells out to the `docker` CLI, so enabling it means
  mounting `/var/run/docker.sock` into the backend — which hands agent-generated
  code the ability to start privileged containers on the host. Two independent
  things have to go wrong before that happens now (the socket mounted *and* the
  variable set), and the missing-daemon probe is a third, but it is an
  availability check rather than a security boundary — do not treat it as the
  gate. Leaving the tool off costs nothing but that one feature.
- **`PAYMENT_PROVIDER=mock`.** No real money moves, and no real card should ever
  be entered: `payment_methods` would fall under PCI scope. Ship a real
  processor adapter before advertising billing.
- **Transactional email.** Five variables in `.env.prod`: `EMAIL_PROVIDER`,
  `RESEND_API_KEY`, `EMAIL_FROM`, `SITE_URL`, `EMAIL_VERIFICATION_REQUIRED`.
  A hosted instance sets `EMAIL_PROVIDER=resend`, a real `RESEND_API_KEY`, and
  `SITE_URL=https://<your-domain>` (the base for verification/reset links in
  emails). The default `EMAIL_PROVIDER=console` only logs messages, so
  verification and password-reset links would never reach users. The backend
  reads these via `env_file: .env.prod`, so no compose change is needed.
- FastAPI's Swagger UI, ReDoc and `/openapi.json` are disabled when
  `ENVIRONMENT=production`.
- **Security headers come from Caddy** (`header` blocks in the `Caddyfile`),
  on every response — app, API and Umami alike: HSTS (one year,
  `includeSubDomains`, no `preload`), a Content-Security-Policy,
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy` and `Permissions-Policy`; `Server` and `X-Powered-By` are
  stripped. The CSP is pragmatic rather than strict: `script-src` and
  `style-src` keep `'unsafe-inline'` because Next.js hydration scripts, the
  JSON-LD block in the root layout and React style attributes all break
  without nonces. The only external origin allowed is `https://*.sentry.io`
  in `connect-src` — if you point `FRONTEND_SENTRY_DSN` at a self-hosted
  Sentry, edit that line to match its host. Header changes take effect with
  the zero-downtime reload documented under "Enabling on an existing
  deployment" (`exec caddy caddy reload`).
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

Optional and off by default, on both sides of the stack.

**Backend** — to enable:

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

**Frontend** — a *second* Sentry project (platform: Next.js), because backend
and frontend events need separate DSNs and dashboards:

1. Create the project and copy its DSN.
2. Set `FRONTEND_SENTRY_DSN=<dsn>` in `.env.prod` and
   `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d frontend`.

The DSN is read at runtime (server-side, like `SITE_URL`), so the image stays
domain-agnostic. Server-side render errors are captured via `onRequestError`;
browser errors are captured by the error boundaries once the lazily-loaded SDK
initializes. With the variable empty, no Sentry chunk is ever served to
browsers and the app makes zero requests to any ingest host.

Deliberate trade-offs (all cheap to revisit): no source-map upload (client
stack traces are minified; enabling it would need `withSentryConfig` plus a CI
auth token), no tunnel route (ad-blockers may drop *browser* events; server
capture is unaffected), no session replay (bundle size + PII surface).

### Logs

`LOG_FORMAT=json` (the production default in `.env.prod.example`) emits one JSON
object per line — pipe `docker compose logs` into any aggregator. `LOG_FORMAT=text`
keeps the readable format for local debugging.

Every HTTP response carries an `X-Request-ID` header, and each request emits one
`maestro.access` log line with `request_id`, `method`, `path`, `status` and
`duration_ms` (health probes excluded to keep the noise down). The same id is
attached to error logs and Sentry events, so a user-reported failure correlates
directly:

```bash
docker compose -f docker-compose.prod.yml logs backend | grep <request-id>
```

Caddy writes JSON access logs to stdout (`log` directive in the `Caddyfile`),
giving request-level visibility in front of both apps — including uptime-monitor
hits on `/health*`, which are not filtered at the proxy.

Container logs are rotated by the `json-file` caps in `docker-compose.prod.yml`
(`max-size: 10m`, `max-file: 5` per service — roughly 550 MB worst case for the
whole stack). Changing the caps requires recreating the containers; `up -d`
does that and drops the old log files.

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

`backup.sh` (from `scripts/backup.sh` in the repo, kept in sync by `deploy.yml`)
dumps every durable store into `/opt/maestro/backups`, applies retention and
optionally pushes the files offsite. It is scheduled from the host crontab,
exactly like the purge job.

### What is backed up

| Store | What | File |
|---|---|---|
| Postgres | `maestro` DB — accounts, subscriptions, quota ledger; the one that matters most | `maestro-pg-<ts>.sql.gz` (`pg_dump --clean --if-exists`) |
| Postgres | `umami` DB — only when the `analytics` profile is active in `.env.prod` | `maestro-umami-<ts>.sql.gz` |
| MongoDB | `maestro` DB — agent logs, task sessions, marketplace, agent configs | `maestro-mongo-<ts>.archive.gz` (`mongodump --archive --gzip`) |
| Qdrant | every collection, enumerated dynamically — per-collection snapshots over the HTTP API | `maestro-qdrant-<collection>-<ts>.snapshot` |

Qdrant is distroless and publishes no ports, so the script talks to it through
a one-shot `curlimages/curl` container joined to the compose network; each
snapshot is downloaded over HTTP and then deleted server-side so nothing
accumulates inside the `qdrantdata` volume.

> **Qdrant snapshots require named-volume storage.** On the production
> stack (`qdrantdata` named volume) a snapshot of a near-empty collection is
> ~140 KB and restores cleanly. On a Windows Docker Desktop **bind mount**
> (the dev stack's `./.data/qdrant`) the same snapshot balloons to ~400 MB
> (sparse WAL files get materialized) and its `wal/first-index` is zeroed,
> so the restore fails with a WAL deserialize error. This is a dev-only
> filesystem artifact — verified 2026-07-13 against `v1.18.2` both ways —
> not a production risk.

**Deliberately not backed up:** `redis` (ephemeral rate-limit buckets,
persistence is disabled on purpose), `ollamadata` (models are re-pulled by
`ollama-pull`), `caddydata` (TLS certificates re-issue automatically on the
first request after a rebuild).

**`.env.prod` is never touched by the script.** Back it up manually,
encrypted (e.g. in a password manager) — losing `API_KEY_MASTER_KEY` makes
every BYOK key in a Postgres dump permanently undecryptable, and leaking it
decrypts all of them. The script pushes only the backups directory offsite,
so secrets structurally cannot leave the host through it.

### Schedule and retention

Daily at 03:30 (offset from the 03:00 purge), guarded by `flock` so an
overlapping run exits instead of stacking:

```cron
30 3 * * * cd /opt/maestro && RCLONE_REMOTE=oci:maestro-backups flock -n /opt/maestro/backup.lock ./backup.sh >> /opt/maestro/backup.log 2>&1
```

Retention is applied by the script itself, locally and remotely: `daily/`
keeps 7 days, `weekly/` (a copy made every Sunday) keeps 28 days. Pruning is
scoped to the `maestro-*` naming pattern and never deletes anything else.
Run the script once by hand over SSH before trusting the cron line, and note
`backup.log` grows about a line per day — truncate it ad hoc.

### Offsite copy (Oracle Object Storage via rclone)

The offsite push is env-gated: leave `RCLONE_REMOTE` unset (drop it from the
cron line) and the script stays local-only. To enable it:

1. In the OCI console create a **private** bucket, e.g. `maestro-backups`
   (Always Free includes 20 GB of Object Storage).
2. Create a **Customer Secret Key** for a least-privilege IAM user (Identity →
   Users → Customer Secret Keys) — this is OCI's S3-compatible credential.
3. Install rclone on the host (`sudo apt install rclone` or the arm64 static
   binary) and configure `~/.config/rclone/rclone.conf`:

   ```ini
   [oci]
   type = s3
   provider = Other
   access_key_id = <customer secret key id>
   secret_access_key = <customer secret key>
   endpoint = https://<namespace>.compat.objectstorage.<region>.oraclecloud.com
   region = <region>
   ```

4. Set `RCLONE_REMOTE=oci:maestro-backups` in the cron line.

The script uses `rclone copy` (additive), deliberately not `sync`: syncing
from a freshly rebuilt host with an empty backups directory would delete
every offsite backup — exactly the disaster the offsite copy exists to
survive. Remote retention is pruned separately with `rclone delete --min-age`.

### Restore runbook

All commands run from `/opt/maestro`. Define the compose prefix once:

```bash
DC="docker compose -f docker-compose.prod.yml --env-file .env.prod"
```

**Postgres** — the dump carries `--clean --if-exists`, so piping it in
drops and recreates every object:

```bash
$DC stop backend
gunzip -c maestro-pg-<ts>.sql.gz | $DC exec -T postgres psql -U maestro -d maestro
$DC up -d backend
```

Umami restores the same way into `-d umami`. For a cheap drill without
touching live data, restore into a scratch DB first:
`$DC exec -T postgres createdb -U maestro scratch` then `psql ... -d scratch`.

**MongoDB** — `--drop` replaces each collection in place:

```bash
$DC exec -T mongo mongorestore --archive --gzip --drop --nsInclude 'maestro.*' \
  -u "$MONGO_USER" -p "$MONGO_PASSWORD" --authenticationDatabase admin \
  < maestro-mongo-<ts>.archive.gz
```

**Qdrant** — upload the snapshot per collection; the upload recreates the
collection even if it no longer exists (read `QDRANT_API_KEY` from `.env.prod`
rather than exporting it into shell history):

```bash
cat maestro-qdrant-<collection>-<ts>.snapshot | docker run --rm -i \
  --network maestro_default curlimages/curl:8.11.1 -fsS \
  -H "api-key: $QDRANT_API_KEY" \
  -F "snapshot=@-;filename=restore.snapshot" \
  "http://qdrant:6333/collections/<collection>/snapshots/upload?priority=snapshot"
```

**Full disaster recovery**, in order: provision a fresh host → place the four
files (compose, Caddyfile, `.env.prod` from your encrypted copy, `backup.sh`)
→ `up -d` (this runs `migrate` against the empty database) → restore Postgres,
Mongo, then Qdrant from the offsite bucket (`rclone copy oci:maestro-backups/daily .`)
→ `$DC restart backend`. If the dump predates the current migration head,
restoring it rewinds the schema to the dump's state; run
`$DC up -d migrate` afterwards to bring it forward again.

---

## Local smoke test

Verify the production stack on your own machine before touching a server. Set
`DOMAIN=http://localhost` in `.env.prod` — the `http://` prefix tells Caddy to
serve plain HTTP and skip certificate provisioning.

```bash
cp .env.prod.example .env.prod    # DOMAIN=http://localhost, fill the secrets
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

> **Keep real secrets out of the repo tree.** A `.env.prod` filled with
> production values (notably `API_KEY_MASTER_KEY`, which decrypts every stored
> BYOK key) must not sit inside the working tree — it is `.gitignore`d, but one
> `git add -f` away from being committed. Keep the real file outside the repo
> (e.g. `~/.maestro/.env.prod`, locked to your user) and pass its absolute path
> to `--env-file`. On the production host the file already lives beside the
> compose file at `/opt/maestro/.env.prod`, so the relative form is correct
> there; only local runs off an out-of-tree copy need the absolute path:
>
> ```bash
> docker compose -f docker-compose.prod.yml \
>   --env-file /absolute/path/to/.env.prod up -d --build
> ```

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
