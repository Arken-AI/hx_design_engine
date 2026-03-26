"""Redis session store for DesignState.

Provides save/load by session_id, heartbeat for orphan detection,
and 24-hour TTL for automatic cleanup.
"""

from __future__ import annotations

import logging
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
    """Async Redis-backed session persistence for DesignState."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self.redis = redis_client

    async def save(self, session_id: str, state: "DesignState") -> None:
        """Serialize and store a DesignState with 24h TTL."""
        try:
            await self.redis.setex(
                f"{SESSION_KEY_PREFIX}{session_id}",
                SESSION_TTL_SECONDS,
                state.model_dump_json(),
            )
        except Exception:
            logger.warning(
                "Redis save failed for session %s", session_id, exc_info=True
            )

    async def load(self, session_id: str) -> "DesignState | None":
        """Load a DesignState from Redis. Returns None if not found or corrupt."""
        from hx_engine.app.models.design_state import DesignState

        data = await self.redis.get(f"{SESSION_KEY_PREFIX}{session_id}")
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

    async def heartbeat(self, session_id: str) -> None:
        """Reset the heartbeat timer (call during each step)."""
        try:
            await self.redis.setex(
                f"{HEARTBEAT_KEY_PREFIX}{session_id}",
                HEARTBEAT_TTL_SECONDS,
                "alive",
            )
        except Exception:
            logger.warning(
                "Redis heartbeat failed for session %s", session_id, exc_info=True
            )

    async def is_orphaned(self, session_id: str) -> bool:
        """True if the heartbeat has expired (client disconnected).

        Returns False if Redis is unavailable (assume alive).
        """
        try:
            return not await self.redis.exists(
                f"{HEARTBEAT_KEY_PREFIX}{session_id}"
            )
        except Exception:
            logger.warning(
                "Redis orphan check failed for session %s", session_id, exc_info=True
            )
            return False

    async def delete(self, session_id: str) -> None:
        """Remove session and heartbeat keys."""
        try:
            await self.redis.delete(
                f"{SESSION_KEY_PREFIX}{session_id}",
                f"{HEARTBEAT_KEY_PREFIX}{session_id}",
            )
        except Exception:
            logger.warning(
                "Redis delete failed for session %s", session_id, exc_info=True
            )
