"""HX Engine configuration — reads from environment / .env file.

Supports both ``HX_`` prefixed vars (e.g. ``HX_REDIS_URL``) and
non-prefixed vars (e.g. ``ANTHROPIC_API_KEY``) so the existing ``.env``
works without changes.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HXEngineSettings(BaseSettings):
    """All settings for the HX Engine microservice."""

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- API ---
    host: str = "0.0.0.0"
    port: int = 8100
    debug: bool = False

    # --- Pipeline ---
    pipeline_orphan_threshold_seconds: int = 120

    # --- AI (reads HX_ANTHROPIC_API_KEY *or* ANTHROPIC_API_KEY) ---
    anthropic_api_key: str = Field(
        default="",
        validation_alias="ANTHROPIC_API_KEY",
    )
    ai_model: str = "claude-sonnet-4-6"

    # --- Internal auth ---
    hx_engine_secret: str = "dev-secret-change-me"
    backend_url: str = "http://localhost:8001"
    internal_secret: str = "dev-internal-secret"

    # --- MongoDB (reads HX_MONGODB_URI *or* MONGODB_URI) ---
    mongodb_uri: str = Field(
        default="",
        validation_alias="MONGODB_URI",
    )
    mongodb_db_name: str = Field(
        default="arken_process_db",
        validation_alias="MONGODB_DB_NAME",
    )

    # --- Logging ---
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="HX_",
        case_sensitive=False,
        extra="ignore",
    )


settings = HXEngineSettings()
