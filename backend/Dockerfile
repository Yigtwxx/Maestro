# =========================================================================
# Maestro backend — FastAPI on uvicorn.
# The same image serves the API, the `alembic upgrade head` migration job and
# the account-purge cron, so alembic/ and alembic.ini must ship with it.
#
# The base image is pinned by digest, not just by tag: official images are
# rebuilt under the same version tag whenever the Debian layer gets a security
# update, so a tag alone does not describe a fixed set of bytes. The digest is
# a multi-arch OCI index (amd64 + arm64/v8), which the arm64 release build
# needs. Dependabot watches this file and opens a PR when it moves -- that PR
# is how OS patches arrive now, so do not let it go stale.
# =========================================================================

FROM python:3.11.15-slim-bookworm@sha256:b18992999dbe963a45a8a4da40ac2b1975be1a776d939d098c647482bcad5cba AS builder

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Every runtime dependency ships a cp311 manylinux wheel, so no compiler is
# needed. Should a source build ever appear, add build-essential here only —
# the runtime stage stays lean either way.
COPY requirements.txt ./
RUN pip install -r requirements.txt


FROM python:3.11.15-slim-bookworm@sha256:b18992999dbe963a45a8a4da40ac2b1975be1a776d939d098c647482bcad5cba AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN useradd --uid 10001 --create-home appuser
USER appuser

EXPOSE 8000

# /health is a liveness probe that touches no database, so it stays green while
# a dependency is down — which is what a container probe should report.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"]

# Shell form so WEB_CONCURRENCY can scale workers. Multi-worker (>1) REQUIRES
# REDIS_URL set: the event bus, HITL/cancel control channel, and reconciliation
# all coordinate across workers over Redis (Backend v2 §4.2). Defaults to 1.
# Enforced at boot: config.py refuses WEB_CONCURRENCY>1 with an empty REDIS_URL.
CMD uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-1}
