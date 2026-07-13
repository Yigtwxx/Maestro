#!/usr/bin/env bash
#
# Maestro backup: Postgres + MongoDB + Qdrant -> $BACKUP_DIR, with 7-daily /
# 4-weekly retention and an optional offsite push to any rclone remote
# (Oracle Object Storage via its S3-compatible endpoint in production).
#
# Designed for the production host (cron, see docs/DEPLOYMENT.md) but
# parameterized so the identical script can be tested against the local dev
# stack. Run it from the directory that contains the compose file.
#
#   prod (defaults):  ./backup.sh
#   dev (from repo):  COMPOSE_FILE=docker-compose.yml ENV_FILE= \
#                     BACKUP_DIR=./.backups bash scripts/backup.sh
#
# Failure model: every store is attempted even if an earlier one fails;
# failures are collected and reported at the end with a non-zero exit so
# cron surfaces them. Dumps are written to *.part and only mv'd into place
# on success — retention and the offsite push never see partial files.
#
# NOT backed up (deliberate): redis (ephemeral rate-limit buckets), ollama
# models (re-pulled by ollama-pull), caddy TLS certs (re-issued on demand),
# and .env.prod — that file must be backed up manually and encrypted, never
# by this script (it must not leave the host in plain text).
#
set -uo pipefail # no -e: one store failing must not skip the others

# --- Parameters (env-overridable; defaults are the production values) -------
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE-.env.prod}" # set ENV_FILE= (empty) for the dev stack
BACKUP_DIR="${BACKUP_DIR:-/opt/maestro/backups}"
# Compose network the one-shot curl container joins to reach Qdrant (which is
# distroless and publishes no ports). "maestro" is the compose project name in
# prod (`name:` in the compose file); override if COMPOSE_PROJECT_NAME differs.
DOCKER_NETWORK="${DOCKER_NETWORK:-maestro_default}"
# rclone remote for the offsite copy, e.g. "oci:maestro-backups".
# Empty = local-only (same env-gating pattern as EMAIL_PROVIDER/SENTRY_DSN).
RCLONE_REMOTE="${RCLONE_REMOTE:-}"
CURL_IMAGE="curlimages/curl:8.11.1"
DAILY_KEEP_DAYS=7
WEEKLY_KEEP_DAYS=28

TS="$(date -u +%Y-%m-%dT%H-%M)"
FAILED=()

log() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$1"; }
fail() {
  echo "ERROR: $1 backup failed" >&2
  FAILED+=("$1")
}

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "ERROR: compose file '$COMPOSE_FILE' not found — run from the directory that contains it." >&2
  exit 1
fi

COMPOSE=(docker compose -f "$COMPOSE_FILE")
[ -n "$ENV_FILE" ] && COMPOSE+=(--env-file "$ENV_FILE")

# Read one variable from $ENV_FILE. NEVER `source` the env file: values like
# EMAIL_FROM contain an unquoted '<' that bash would parse as a redirect.
get_env() {
  [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ] || return 0
  sed -n "s/^$1=//p" "$ENV_FILE" | tail -n1 | tr -d '\r'
}

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"

# --- 1. Postgres (maestro DB) ------------------------------------------------
# In-container socket connections are trust-authenticated; no password needed.
# --clean --if-exists makes the restore a plain `psql <` drop-and-recreate.
log "postgres: dumping maestro"
f="$BACKUP_DIR/daily/maestro-pg-$TS.sql.gz"
if "${COMPOSE[@]}" exec -T postgres pg_dump -U maestro --clean --if-exists maestro |
  gzip >"$f.part"; then
  mv "$f.part" "$f"
else
  rm -f "$f.part"
  fail "postgres"
fi

# --- 2. Umami analytics DB (same instance; only when the profile is active) --
if get_env COMPOSE_PROFILES | grep -q analytics; then
  log "postgres: dumping umami"
  f="$BACKUP_DIR/daily/maestro-umami-$TS.sql.gz"
  if "${COMPOSE[@]}" exec -T postgres pg_dump -U maestro --clean --if-exists umami |
    gzip >"$f.part"; then
    mv "$f.part" "$f"
  else
    rm -f "$f.part"
    fail "umami"
  fi
fi

# --- 3. MongoDB (maestro DB) ---------------------------------------------------
# Auth flags only when credentials are configured (the dev mongo is authless).
# The password is visible on the container's argv for the dump duration;
# acceptable on a single-operator host.
log "mongo: dumping maestro"
MONGO_ARGS=(--archive --gzip --db maestro)
MONGO_USER="$(get_env MONGO_USER)"
if [ -n "$MONGO_USER" ]; then
  MONGO_ARGS+=(-u "$MONGO_USER" -p "$(get_env MONGO_PASSWORD)" --authenticationDatabase admin)
fi
f="$BACKUP_DIR/daily/maestro-mongo-$TS.archive.gz"
if "${COMPOSE[@]}" exec -T mongo mongodump "${MONGO_ARGS[@]}" >"$f.part"; then
  mv "$f.part" "$f"
else
  rm -f "$f.part"
  fail "mongo"
fi

# --- 4. Qdrant (per-collection snapshots over HTTP) --------------------------
# The qdrant image is distroless (no shell) and publishes no ports in prod, so
# every API call runs in a throwaway curl container joined to the compose
# network. Snapshots are downloaded over HTTP and then DELETEd server-side so
# they never accumulate inside the qdrantdata volume. Per-collection snapshots
# (not the full-storage one) restore through the plain HTTP upload API while
# the stack is running. JSON is parsed with grep on purpose — no jq dependency
# on the host; the image is version-pinned so the response shape is stable.
QDRANT_KEY="$(get_env QDRANT_API_KEY)"
QCURL_HDR=()
[ -n "$QDRANT_KEY" ] && QCURL_HDR=(-H "api-key: $QDRANT_KEY")
qcurl() {
  docker run --rm -i --network "$DOCKER_NETWORK" "$CURL_IMAGE" \
    -fsS ${QCURL_HDR[@]+"${QCURL_HDR[@]}"} "$@"
}
json_names() { grep -o '"name":"[^"]*"' | cut -d'"' -f4; }

log "qdrant: listing collections"
if COLLECTIONS_JSON="$(qcurl http://qdrant:6333/collections)"; then
  COLLECTIONS="$(printf '%s' "$COLLECTIONS_JSON" | json_names || true)"
  for c in $COLLECTIONS; do
    log "qdrant: snapshotting $c"
    # Drop stale snapshots left behind by a previously crashed run.
    for old in $(qcurl "http://qdrant:6333/collections/$c/snapshots" | json_names || true); do
      qcurl -X DELETE "http://qdrant:6333/collections/$c/snapshots/$old?wait=true" >/dev/null || true
    done
    snap="$(qcurl -X POST "http://qdrant:6333/collections/$c/snapshots?wait=true" | json_names || true)"
    if [ -z "$snap" ]; then
      fail "qdrant-$c-create"
      continue
    fi
    f="$BACKUP_DIR/daily/maestro-qdrant-$c-$TS.snapshot"
    if qcurl "http://qdrant:6333/collections/$c/snapshots/$snap" >"$f.part"; then
      mv "$f.part" "$f"
    else
      rm -f "$f.part"
      fail "qdrant-$c-download"
    fi
    qcurl -X DELETE "http://qdrant:6333/collections/$c/snapshots/$snap?wait=true" >/dev/null ||
      fail "qdrant-$c-cleanup"
  done
else
  fail "qdrant-list"
fi

# --- 5. Weekly copies (Sundays) ----------------------------------------------
if [ "$(date -u +%u)" = "7" ]; then
  cp "$BACKUP_DIR"/daily/maestro-*"$TS"* "$BACKUP_DIR/weekly/" 2>/dev/null || true
fi

# --- 6. Local retention (scoped to our naming pattern — deletes nothing else)
find "$BACKUP_DIR/daily" -name 'maestro-*' -type f -mtime +"$DAILY_KEEP_DAYS" -delete
find "$BACKUP_DIR/weekly" -name 'maestro-*' -type f -mtime +"$WEEKLY_KEEP_DAYS" -delete

# --- 7. Offsite push (env-gated) ----------------------------------------------
# `copy` (additive), deliberately NOT `sync`: syncing from a freshly rebuilt
# host with an empty backups dir would wipe every offsite backup — exactly the
# disaster the offsite copy exists to survive. Remote retention is pruned
# separately with --min-age. Only $BACKUP_DIR is pushed; .env.prod never
# enters it, so secrets structurally cannot leave the host through this path.
if [ -n "$RCLONE_REMOTE" ]; then
  log "offsite: rclone copy to $RCLONE_REMOTE"
  rclone copy "$BACKUP_DIR/daily" "$RCLONE_REMOTE/daily" --include 'maestro-*' || fail "rclone-daily"
  rclone copy "$BACKUP_DIR/weekly" "$RCLONE_REMOTE/weekly" --include 'maestro-*' || fail "rclone-weekly"
  rclone delete "$RCLONE_REMOTE/daily" --min-age "$((DAILY_KEEP_DAYS + 1))d" --include 'maestro-*' || fail "rclone-prune-daily"
  rclone delete "$RCLONE_REMOTE/weekly" --min-age "$((WEEKLY_KEEP_DAYS + 1))d" --include 'maestro-*' || fail "rclone-prune-weekly"
else
  log "offsite: skipped (RCLONE_REMOTE not set)"
fi

# --- 8. Summary ---------------------------------------------------------------
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "BACKUP FAILED: ${FAILED[*]}" >&2
  exit 1
fi
log "backup ok: $TS ($(du -sh "$BACKUP_DIR/daily" | cut -f1) local)"
