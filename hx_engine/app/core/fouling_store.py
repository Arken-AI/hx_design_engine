"""MongoDB persistence for AI-provided fouling factors.

Collection: ai_fouling_factors in arken_process_db.
Acts as a learning cache — first AI lookup is an API call, subsequent
lookups for the same fluid hit MongoDB instantly.

User overrides are stored with accepted_by="user" and always preferred.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# Re-review cached values older than this
_CACHE_TTL_DAYS = 90

# Singleton client — initialized lazily
_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def _normalize_name(fluid_name: str) -> str:
    return re.sub(r"\s+", " ", fluid_name.strip().lower())


async def get_db() -> AsyncIOMotorDatabase | None:
    """Get or create the shared MongoDB connection.

    Returns None if MONGODB_URL is not configured (engine runs without DB).
    """
    global _client, _db
    if _db is not None:
        return _db

    url = os.environ.get("HX_MONGODB_URI") or os.environ.get("MONGODB_URI")
    if not url:
        logger.info("MONGODB_URL not set — fouling cache disabled")
        return None

    db_name = os.environ.get("HX_MONGODB_DB_NAME") or os.environ.get("MONGODB_DB_NAME", "arken_process_db")
    try:
        _client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=3000)
        # Ping to verify connectivity
        await _client.admin.command("ping")
        _db = _client[db_name]
        # Ensure indexes
        await _db.ai_fouling_factors.create_index(
            [("fluid_name", 1), ("temperature_C", 1)],
        )
        logger.info("Connected to MongoDB fouling cache: %s", db_name)
        return _db
    except Exception:
        logger.warning("MongoDB unavailable — fouling cache disabled", exc_info=True)
        _client = None
        _db = None
        return None


async def close_db() -> None:
    """Close the MongoDB connection (for clean shutdown)."""
    global _client, _db
    if _client:
        _client.close()
    _client = None
    _db = None


async def find_cached_fouling(
    fluid_name: str,
    temperature_C: float | None = None,
) -> dict[str, Any] | None:
    """Look up a cached AI fouling factor from MongoDB.

    Returns the document dict if found and not expired, else None.
    User-accepted values (accepted_by="user") never expire.
    """
    db = await get_db()
    if db is None:
        return None

    name = _normalize_name(fluid_name)
    query: dict[str, Any] = {"fluid_name": name}
    if temperature_C is not None:
        # Match within ±10°C range
        query["temperature_C"] = {
            "$gte": temperature_C - 10,
            "$lte": temperature_C + 10,
        }
    else:
        query["temperature_C"] = None

    try:
        doc = await db.ai_fouling_factors.find_one(
            query, sort=[("created_at", -1)],
        )
    except Exception:
        logger.warning("MongoDB query failed for fouling lookup", exc_info=True)
        return None

    if doc is None:
        return None

    # Check expiry (user overrides never expire)
    if doc.get("accepted_by") != "user":
        created = doc.get("created_at")
        if created and isinstance(created, datetime):
            age = datetime.now(timezone.utc) - created
            if age > timedelta(days=_CACHE_TTL_DAYS):
                logger.info(
                    "Cached fouling for '%s' expired (%d days old)",
                    name, age.days,
                )
                return None

    return doc


async def save_fouling_factor(
    fluid_name: str,
    temperature_C: float | None,
    rf_value: float,
    confidence: float,
    reasoning: str,
    source: str,
    accepted_by: str = "ai",
    user_override: float | None = None,
) -> None:
    """Save an AI-provided (or user-provided) fouling factor to MongoDB."""
    db = await get_db()
    if db is None:
        return

    name = _normalize_name(fluid_name)
    doc = {
        "fluid_name": name,
        "temperature_C": temperature_C,
        "rf_value": rf_value,
        "confidence": confidence,
        "reasoning": reasoning,
        "source": source,
        "accepted_by": accepted_by,
        "user_override": user_override,
        "created_at": datetime.now(timezone.utc),
    }

    try:
        await db.ai_fouling_factors.insert_one(doc)
        logger.info(
            "Saved fouling factor for '%s': R_f=%.6f (by %s)",
            name, rf_value, accepted_by,
        )
    except Exception:
        logger.warning("Failed to save fouling factor to MongoDB", exc_info=True)
