"""Application settings loaded from environment variables.

All configuration comes from the environment (or a local `.env`); nothing
secret is hard-coded. See `.env.example` at the repo root.
"""

from __future__ import annotations

import base64
import binascii
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Development-only placeholders. Rejected at startup when ENVIRONMENT=production
# (see Settings._guard_production_secrets). Kept as the field defaults below so
# the sentinel values live in exactly one place.
_DEV_JWT_SECRET = "change-me"
_DEV_MASTER_KEY = "change-me-32-byte-base64-master-key"
_MIN_JWT_SECRET_LENGTH = 32
_MASTER_KEY_BYTES = 32  # AES-256


def _decoded_key_len(raw: str) -> int:
    """Return the byte length of the master key (base64 → hex → utf-8).

    Mirrors ``security._load_master_key`` but stays local to config to avoid a
    circular import (``security`` imports ``config``).
    """
    stripped = raw.strip()
    for decoder in (base64.b64decode, binascii.unhexlify):
        try:
            key = decoder(stripped)
        except (binascii.Error, ValueError):
            continue
        if len(key) == _MASTER_KEY_BYTES:
            return len(key)
    return len(stripped.encode("utf-8"))


class Settings(BaseSettings):
    """Typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---
    environment: str = "development"
    # Mirrors the Dockerfile's `--workers ${WEB_CONCURRENCY:-1}`. The app reads
    # it only to validate the topology (see _guard_multi_worker_redis); uvicorn
    # does the actual scaling.
    web_concurrency: int = Field(default=1, ge=1)
    log_level: str = "INFO"
    # "text" (default) keeps the human-readable basicConfig format for local dev;
    # "json" emits one JSON object per line for log aggregation in production.
    log_format: str = "text"

    # --- Observability (Sentry, error tracking) ---
    # Empty DSN disables Sentry entirely (dev/test add no extra dependency at
    # runtime). Tracing/APM starts off (sample_rate 0.0) to protect the free-tier
    # quota and single-host RAM. sentry_environment falls back to `environment`.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0
    sentry_environment: str = ""

    # --- Observability (own execution tracing, Backend v2 §4.5) ---
    # Off by default: when on, the engine records OTel-shaped spans to the Mongo
    # `trace_spans` collection (best-effort — a Mongo hiccup never fails a task)
    # and the trace/cost endpoints have data to serve. Adds no network egress:
    # spans stay in the same Mongo the app already uses.
    tracing_enabled: bool = False
    # Trace spans are dropped by a MongoDB TTL index this many days after
    # creation (independent of task_retention_days: traces are heavier).
    trace_retention_days: int = Field(default=30, ge=1)

    # --- Databases ---
    postgres_url: str = "postgresql+asyncpg://maestro:maestro@localhost:5433/maestro"
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "maestro"

    # --- Vector DB (Qdrant) ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None

    # --- Rate limiting ---
    # Empty means "no Redis": the limiter falls back to process-local counters,
    # which is correct for a single-worker dev server and for the test suite.
    redis_url: str = ""
    rate_limit_enabled: bool = True
    # Only enable behind a reverse proxy that overwrites/appends X-Forwarded-For
    # (our Caddy does). With the backend directly exposed, a client could forge
    # the header and mint a fresh bucket per request.
    trust_proxy_headers: bool = False

    # --- Security ---
    jwt_secret: str = _DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    # 32-byte AES-256 master key, provided as base64 or 64-char hex.
    api_key_master_key: str = _DEV_MASTER_KEY

    # --- CORS (comma-separated in env; NoDecode lets our validator split it) ---
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # --- Payments ---
    # Prices, quotas and the trial length live in constants.py; they are product
    # decisions, not deployment config.
    payment_provider: str = "mock"

    # --- Transactional email ---
    # "console" logs messages (dev/self-host default, zero dependencies);
    # "resend" sends through the Resend HTTP API. Send failures never fail the
    # calling endpoint. Prices of nothing: templates/TTLs live in constants.py.
    email_provider: str = "console"
    resend_api_key: str = ""
    email_from: str = "Maestro <noreply@maestro.example.com>"
    # Base URL for action links inside emails (verification, password reset).
    # The frontend's SITE_URL is a separate, frontend-container-only variable;
    # the backend reads its own copy because emails are built server-side.
    site_url: str = "http://localhost:3000"
    # Soft gate: unverified accounts get 403 on task start and API-key create.
    # Self-hosters may disable it; verification emails still go out.
    email_verification_required: bool = True

    # --- Free / local model (Ollama, OpenAI-compatible) ---
    free_model_endpoint: str = "http://localhost:11434/v1"
    free_model_name: str = "qwen3.5:9b"
    # Whether this deployment actually serves a chat model at
    # free_model_endpoint. Hosted instances set this to false (the prod ollama
    # service pulls only the embedding model), which turns task starts on the
    # local model into an explicit 400 instead of a task whose every subtask
    # fails. Embeddings are unaffected — see embedding_endpoint below.
    ollama_chat_enabled: bool = True
    # Embeddings are needed by RAG and document upload whatever chat provider the
    # user picked, so they get their own endpoint: a deployment can serve only
    # nomic-embed-text without also hosting a chat model. Falls back to
    # free_model_endpoint, which is where both live during local development.
    embedding_endpoint: str = ""
    embedding_model_name: str = "nomic-embed-text"
    embedding_dim: int = 768

    # --- Gemini (BYOK, free tier; OpenAI-compatible endpoint) ---
    # Must be a valid Google model id, else every call 404s and (with Ollama
    # unavailable) the whole task fails with "all subtasks failed". The
    # "-latest" alias tracks the newest Flash release, so it survives model
    # retirements (gemini-2.5-flash started 404ing before its announced
    # shutdown date). Pin a stable id via GEMINI_MODEL_NAME if deterministic
    # behavior matters more than availability.
    gemini_model_name: str = "gemini-flash-latest"

    # --- Web search (ddgs / DuckDuckGo, free, no API key) ---
    web_search_enabled: bool = True
    web_search_max_results: int = 5
    web_search_timeout_seconds: int = 10
    web_search_max_uses_per_subtask: int = 3

    # --- Data fetch tool (subagent directive loop, HTTP GET → text) ---
    data_fetch_enabled: bool = True
    data_fetch_timeout_seconds: int = 15
    data_fetch_max_uses_per_subtask: int = 3

    # --- Code execution tool (Docker sandbox; degrades gracefully if absent) ---
    code_execution_enabled: bool = True
    code_execution_image: str = "python:3.12-slim"
    code_execution_timeout_seconds: int = 30
    code_execution_memory_limit: str = "512m"
    code_execution_cpus: str = "1"
    code_execution_max_uses_per_subtask: int = 3

    # --- LLM layer v2 ---
    # Whether the local Ollama model is driven with native function-calling.
    # Off by default: qwen-class local models are unreliable at native tools, so
    # the directive/extract_json protocol stays the default for Ollama.
    ollama_native_tools: bool = False

    # --- Quality (reviewer) ---
    # What the Reviewer does when *it* fails (LLMError / unparseable verdict):
    # "approve" (silent pass, legacy), "warn" (pass but flag review_skipped —
    # default), or "reject" (fail the check). A flaky model no longer silently
    # turns the quality gate into a no-op (Backend v2 §4.6/D8).
    reviewer_fail_mode: str = "warn"

    # --- Subagent execution ---
    # Concurrent subagents per task (protects local Ollama queue depth).
    subagent_max_parallel: int = 3
    # Total tool calls (all kinds) per subtask run.
    subagent_max_tool_calls: int = 6

    # --- Default agent limits (CLAUDE.md §9.2) ---
    max_iterations: int = 10
    max_review_iterations: int = 3
    # Total budget for the whole orchestrator->main_agent->subagent(s)->reviewer
    # pipeline. Local/CPU models need much more headroom than cloud APIs.
    task_timeout_seconds: int = 1800

    # --- Retention ---
    # Task sessions and agent logs are dropped by a MongoDB TTL index this many
    # days after creation. Dashboard metrics only cover this window, and it must
    # stay >= TREND_WINDOW_DAYS or the oldest sparkline days read as zero.
    task_retention_days: int = Field(default=30, ge=1)

    # --- LLM HTTP client timeouts ---
    llm_request_timeout_seconds: float = 180.0
    llm_connect_timeout_seconds: float = 10.0

    # --- Custom LLM endpoint SSRF guard ---
    # A user-supplied ``custom`` provider stores an arbitrary base_url the
    # backend then POSTs to server-side. With this on (default), that URL must
    # be http(s), credential-free, and resolve only to globally-routable
    # addresses — blocking probes of cloud metadata and internal services from
    # a hosted deployment. Turn OFF only for a fully self-hosted stack where the
    # custom endpoint legitimately points at a private host (e.g. localhost).
    llm_ssrf_guard_enabled: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated string for CORS_ORIGINS."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _guard_production_secrets(self) -> Settings:
        """Refuse to boot in production with placeholder or weak secrets.

        Runs at import time via ``get_settings()``, so a failure here blocks
        startup instead of silently serving with a publicly-known JWT signing
        key or AES master key. Messages never echo the secret values.
        """
        if self.environment != "production":
            return self
        problems: list[str] = []
        if (
            self.jwt_secret == _DEV_JWT_SECRET
            or len(self.jwt_secret) < _MIN_JWT_SECRET_LENGTH
        ):
            problems.append(
                f"JWT_SECRET must be set to a strong value "
                f"(>= {_MIN_JWT_SECRET_LENGTH} chars)"
            )
        if self.api_key_master_key == _DEV_MASTER_KEY:
            problems.append("API_KEY_MASTER_KEY must be set to a real 32-byte key")
        elif _decoded_key_len(self.api_key_master_key) != _MASTER_KEY_BYTES:
            problems.append(
                "API_KEY_MASTER_KEY must decode to 32 bytes (base64/hex/utf-8)"
            )
        if self.email_provider == "resend" and not self.resend_api_key:
            problems.append("RESEND_API_KEY must be set when EMAIL_PROVIDER=resend")
        if problems:
            raise ValueError(
                "Insecure production configuration: " + "; ".join(problems)
            )
        return self

    @model_validator(mode="after")
    def _guard_multi_worker_redis(self) -> Settings:
        """Refuse to boot multi-worker without Redis, in every environment.

        The event bus, the HITL/cancel control channel and the rate limiter all
        coordinate across workers over Redis. Without REDIS_URL they silently
        fall back to process-local state, so a multi-worker deploy degrades
        invisibly: cancel/answer requests landing on a different worker than
        the task never arrive. Not gated on ENVIRONMENT — WEB_CONCURRENCY>1 is
        explicit opt-in and broken without Redis everywhere.
        """
        if self.web_concurrency > 1 and not self.redis_url:
            raise ValueError(
                "WEB_CONCURRENCY>1 requires REDIS_URL: the event bus, "
                "HITL/cancel control channel, and rate limiter coordinate "
                "across workers over Redis; without it they silently fall "
                "back to process-local state."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()
