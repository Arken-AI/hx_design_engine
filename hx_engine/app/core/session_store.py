"""Redis session store for DesignState with in-memory fallback.

Provides save/load by session_id, heartbeat for orphan detection,
and 24-hour TTL for automatic cleanup. Falls back to a local dict
when Redis is unavailable.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 86_400  # 24 hours
HEARTBEAT_KEY_PREFIX = "hx:heartbeat:"
SESSION_KEY_PREFIX = "hx:session:"
HEARTBEAT_TTL_SECONDS = 120  # orphan threshold


class SessionStore:
    """Async Redis-backed session persistence for DesignState.

    When Redis is ``None`` or unavailable, all operations fall back to
    an in-memory dict so the pipeline still works in local dev.
    """

    def __init__(self, redis_client: aioredis.Redis | None) -> None:
        self.redis = redis_client
        # In-memory fallback stores
        self._mem_sessions: dict[str, str] = {}
        self._mem_heartbeats: dict[str, float] = {}

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @property
    def _has_redis(self) -> bool:
        return self.redis is not None

    # ------------------------------------------------------------------
    # save / load
    # ------------------------------------------------------------------

    async def save(self, session_id: str, state: "DesignState") -> None:
        """Serialize and store a DesignState with 24h TTL."""
        payload = state.model_dump_json()
        if self._has_redis:
            try:
                await self.redis.setex(
                    f"{SESSION_KEY_PREFIX}{session_id}",
                    SESSION_TTL_SECONDS,
                    payload,
                )
                return
            except Exception:
                logger.warning(
                    "Redis save failed for session %s — using in-memory fallback",
                    session_id,
                    exc_info=True,
                )
        # Fallback
        self._mem_sessions[session_id] = payload

    async def load(self, session_id: str) -> "DesignState | None":
        """Load a DesignState. Returns None if not found or corrupt."""
        from hx_engine.app.models.design_state import DesignState

        data: str | None = None

        if self._has_redis:
            try:
                data = await self.redis.get(f"{SESSION_KEY_PREFIX}{session_id}")
            except Exception:
                logger.warning(
                    "Redis load failed for session %s — trying in-memory",
                    session_id,
                    exc_info=True,
                )

        if data is None:
            data = self._mem_sessions.get(session_id)

        if data is None:
            return None

        try:
            return DesignState.model_validate_json(data)
        except Exception:
            logger.error(
                "Corrupted session %s — could not deserialize",
                session_id,
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # heartbeat / orphan detection
    # ------------------------------------------------------------------

    async def heartbeat(self, session_id: str) -> None:
        """Reset the heartbeat timer (call during each step)."""
        if self._has_redis:
            try:
                await self.redis.setex(
                    f"{HEARTBEAT_KEY_PREFIX}{session_id}",
                    HEARTBEAT_TTL_SECONDS,
                    "alive",
                )
                return
            except Exception:
                logger.warning(
                    "Redis heartbeat failed for session %s — using in-memory",
                    session_id,
                    exc_info=True,
                )
        # Fallback
        self._mem_heartbeats[session_id] = time.monotonic()

    async def is_orphaned(self, session_id: str) -> bool:
        """True if the heartbeat has expired (client disconnected)."""
        if self._has_redis:
            try:
                return not await self.redis.exists(
                    f"{HEARTBEAT_KEY_PREFIX}{session_id}"
                )
            except Exception:
                logger.warning(
                    "Redis orphan check failed for session %s — using in-memory",
                    session_id,
                    exc_info=True,
                )

        # Fallback: check in-memory heartbeat
        last_beat = self._mem_heartbeats.get(session_id)
        if last_beat is None:
            return False  # No heartbeat recorded yet — assume alive
        return (time.monotonic() - last_beat) > HEARTBEAT_TTL_SECONDS

    # ------------------------------------------------------------------
    # delete
    # ------------------------------------------------------------------

    async def delete(self, session_id: str) -> None:
        """Remove session and heartbeat keys."""
        if self._has_redis:
            try:
                await self.redis.delete(
                    f"{SESSION_KEY_PREFIX}{session_id}",
                    f"{HEARTBEAT_KEY_PREFIX}{session_id}",
                )
            except Exception:
                logger.warning(
                    "Redis delete failed for session %s", session_id, exc_info=True
                )
        # Always clean up in-memory too
        self._mem_sessions.pop(session_id, None)
        self._mem_heartbeats.pop(session_id, None)
