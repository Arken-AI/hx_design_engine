"""HX Engine configuration — reads from environment / .env file.

All variables use the ``HX_`` prefix (e.g. ``HX_ANTHROPIC_API_KEY``,
``HX_REDIS_URL``). See ``.env.example`` for the full list.
"""

from __future__ import annotations

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

    # --- AI (reads HX_ANTHROPIC_API_KEY via env_prefix) ---
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"

    # --- Internal auth ---
    hx_engine_secret: str = "dev-secret-change-me"
    backend_url: str = "http://localhost:8001"
    internal_secret: str = "dev-internal-secret"

    # --- MongoDB (reads HX_MONGODB_URI and HX_MONGODB_DB_NAME via env_prefix) ---
    mongodb_uri: str = ""
    mongodb_db_name: str = "arken_process_db"

    # --- Logging ---
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="HX_",
        case_sensitive=False,
        extra="ignore",
    )


settings = HXEngineSettings()
