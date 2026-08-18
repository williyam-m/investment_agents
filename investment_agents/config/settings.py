"""
Application settings using Pydantic Settings.
All configuration comes from environment variables or .env file.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration — loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM ──────────────────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    default_model: str = "ollama/llama2:7b"

    openai_api_key: SecretStr = SecretStr("")
    anthropic_api_key: SecretStr = SecretStr("")
    google_api_key: SecretStr = SecretStr("")

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./debates.db"

    # ── Observability ─────────────────────────────────────────────────────────
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    log_level: str = "INFO"

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ── Debate defaults ───────────────────────────────────────────────────────
    default_budget: int = 40000
    default_max_rounds: int = 3
    min_synthesis_tokens: int = 2000
    tiebreaker_min_budget: int = 3000

    # ── Explore-Exploit thresholds ────────────────────────────────────────────
    # > explore_threshold → EXPLORE mode (high divergence, keep exploring)
    explore_threshold: float = 0.55
    # < exploit_threshold → EXPLOIT mode (converging, go deep)
    exploit_threshold: float = 0.30

    # ── Agent settings ────────────────────────────────────────────────────────
    agent_max_retries: int = 3
    agent_retry_delay: float = 1.0
    agent_request_timeout: int = 120  # seconds

    # ── Embedding model (local, for divergence scoring) ───────────────────────
    embedding_model: str = "all-MiniLM-L6-v2"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str) -> str:
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    def get_openai_api_key(self) -> str:
        """Return the OpenAI API key value (use instead of accessing directly)."""
        return self.openai_api_key.get_secret_value()

    def get_anthropic_api_key(self) -> str:
        """Return the Anthropic API key value."""
        return self.anthropic_api_key.get_secret_value()

    def get_google_api_key(self) -> str:
        """Return the Google API key value."""
        return self.google_api_key.get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
