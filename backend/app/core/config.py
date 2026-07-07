"""Application settings loaded from environment variables.

All configuration comes from the environment (or a local `.env`); nothing
secret is hard-coded. See `.env.example` at the repo root.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    log_level: str = "INFO"

    # --- Databases ---
    postgres_url: str = "postgresql+asyncpg://maestro:maestro@localhost:5433/maestro"
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "maestro"

    # --- Vector DB (Qdrant) ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None

    # --- Security ---
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    # 32-byte AES-256 master key, provided as base64 or 64-char hex.
    api_key_master_key: str = "change-me-32-byte-base64-master-key"

    # --- CORS (comma-separated in env; NoDecode lets our validator split it) ---
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # --- Free / local model (Ollama, OpenAI-compatible) ---
    free_model_endpoint: str = "http://localhost:11434/v1"
    free_model_name: str = "qwen3.5:9b"
    embedding_model_name: str = "nomic-embed-text"
    embedding_dim: int = 768

    # --- Gemini (BYOK, free tier; OpenAI-compatible endpoint) ---
    gemini_model_name: str = "gemini-3.5-flash"

    # --- Web search (ddgs / DuckDuckGo, free, no API key) ---
    web_search_enabled: bool = True
    web_search_max_results: int = 5
    web_search_timeout_seconds: int = 10
    web_search_max_uses_per_subtask: int = 2

    # --- Default agent limits (CLAUDE.md §9.2) ---
    max_iterations: int = 10
    max_review_iterations: int = 3
    # Total budget for the whole orchestrator->main_agent->subagent(s)->reviewer
    # pipeline. Local/CPU models need much more headroom than cloud APIs.
    task_timeout_seconds: int = 1800

    # --- LLM HTTP client timeouts ---
    llm_request_timeout_seconds: float = 180.0
    llm_connect_timeout_seconds: float = 10.0

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated string for CORS_ORIGINS."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()
