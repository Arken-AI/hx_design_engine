"""FastAPI dependency injection for the HX Design Engine."""

from __future__ import annotations

import redis.asyncio as aioredis

from hx_engine.app.config import settings
from hx_engine.app.core.ai_engineer import AIEngineer
from hx_engine.app.core.pipeline_runner import PipelineRunner
from hx_engine.app.core.session_store import SessionStore
from hx_engine.app.core.sse_manager import SSEManager


# ---------------------------------------------------------------------------
# Singleton instances — created at import time, wired in lifespan
# ---------------------------------------------------------------------------

_redis_client: aioredis.Redis | None = None
_session_store: SessionStore | None = None
_sse_manager: SSEManager = SSEManager()
_ai_engineer: AIEngineer | None = None


# ---------------------------------------------------------------------------
# Lifecycle helpers (called from main.py lifespan)
# ---------------------------------------------------------------------------

async def startup() -> None:
    """Initialize shared resources."""
    global _redis_client, _session_store, _ai_engineer  # noqa: PLW0603

    try:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        # Verify connectivity (non-fatal)
        await _redis_client.ping()
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Redis not available at %s — session persistence disabled",
            settings.redis_url,
        )
    _session_store = SessionStore(_redis_client)
    _ai_engineer = AIEngineer(
        stub_mode=(not settings.anthropic_api_key),
    )


async def shutdown() -> None:
    """Clean up shared resources."""
    global _redis_client  # noqa: PLW0603
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


# ---------------------------------------------------------------------------
# FastAPI Depends callables
# ---------------------------------------------------------------------------

def get_session_store() -> SessionStore:
    assert _session_store is not None, "SessionStore not initialised — call startup()"
    return _session_store


def get_sse_manager() -> SSEManager:
    return _sse_manager


def get_ai_engineer() -> AIEngineer:
    assert _ai_engineer is not None, "AIEngineer not initialised — call startup()"
    return _ai_engineer


def get_pipeline_runner() -> PipelineRunner:
    return PipelineRunner(
        session_store=get_session_store(),
        sse_manager=get_sse_manager(),
        ai_engineer=get_ai_engineer(),
    )
