"""MongoDB persistence for AI-provided fluid properties.

Collection: ai_fluid_properties in arken_process_db.
Acts as a learning cache — first AI lookup is an LLM call, subsequent
lookups for the same fluid + temperature hit MongoDB instantly.

Mirrors the fouling_store.py pattern: lazy singleton connection,
graceful degradation when MongoDB is unavailable.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from anthropic import AsyncAnthropic

from hx_engine.app.config import settings
from hx_engine.app.models.design_state import FluidProperties

logger = logging.getLogger(__name__)

# Re-query AI for cached values older than this
_CACHE_TTL_DAYS = 90

# Temperature tolerance for cache hits (±5°C)
_TEMP_TOLERANCE_C = 5.0

# Minimum confidence to cache AI results
_MIN_CONFIDENCE = 0.6

_COLLECTION_NAME = "ai_fluid_properties"

# ── LLM prompt for fluid property estimation ──────────────────────────────────

_FLUID_PROPERTY_PROMPT = """\
You are a senior chemical/process engineer. Given a fluid name, temperature, \
and pressure, provide accurate thermophysical properties.

Use your knowledge of engineering handbooks (Perry's, Yaws, GPSA, DIPPR) \
and thermodynamic databases. For pure compounds, use standard reference data. \
For mixtures, use established correlations.

IMPORTANT:
- All values must be for the LIQUID phase unless the fluid is clearly a gas \
at the given conditions (e.g. nitrogen at 25°C, 1 atm).
- If the fluid is a gas at the given conditions, provide gas-phase properties.
- Be conservative — if uncertain, note it in the confidence score.

Fluid: {fluid_name}
Temperature: {temperature_C} °C
Pressure: {pressure_Pa} Pa

Respond ONLY with a JSON object — no text before or after:
{{
    "density_kg_m3": <float>,
    "viscosity_Pa_s": <float>,
    "cp_J_kgK": <float>,
    "k_W_mK": <float>,
    "confidence": <float 0.0-1.0>,
    "reasoning": "<brief explanation of data source and any caveats, max 200 chars>"
}}

confidence guide:
- 1.0: Standard reference compound with well-known properties (water, ethanol)
- 0.8-0.9: Common industrial fluid with reliable handbook data
- 0.6-0.8: Less common fluid but reasonable engineering estimates available
- 0.3-0.6: Uncertain — limited data, extrapolation required
- <0.3: Highly uncertain — should not be trusted for design
"""


def _normalize_name(fluid_name: str) -> str:
    """Normalize a fluid name for consistent cache lookups."""
    return re.sub(r"\s+", " ", fluid_name.strip().lower())


# ── MongoDB helpers (reuse fouling_store connection) ──────────────────────────

async def _get_collection():
    """Get the ai_fluid_properties collection, reusing fouling_store's DB.

    Returns None if MongoDB is unavailable.
    """
    try:
        from hx_engine.app.core.fouling_store import get_db
        db = await get_db()
        if db is None:
            return None
        # Ensure index on first access (idempotent)
        coll = db[_COLLECTION_NAME]
        await coll.create_index(
            [("fluid_name", 1), ("temperature_C", 1)],
        )
        return coll
    except Exception:
        logger.debug("MongoDB unavailable for fluid property cache", exc_info=True)
        return None


async def find_cached_properties(
    fluid_name: str,
    temperature_C: float,
) -> FluidProperties | None:
    """Look up cached AI fluid properties from MongoDB.

    Returns FluidProperties if found, valid, and not expired. Else None.
    """
    coll = await _get_collection()
    if coll is None:
        return None

    name = _normalize_name(fluid_name)
    query = {
        "fluid_name": name,
        "temperature_C": {
            "$gte": temperature_C - _TEMP_TOLERANCE_C,
            "$lte": temperature_C + _TEMP_TOLERANCE_C,
        },
    }

    try:
        doc = await coll.find_one(query, sort=[("created_at", -1)])
    except Exception:
        logger.warning("MongoDB query failed for fluid property lookup", exc_info=True)
        return None

    if doc is None:
        return None

    # Check expiry
    created = doc.get("created_at")
    if created and isinstance(created, datetime):
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - created
        if age > timedelta(days=_CACHE_TTL_DAYS):
            logger.info(
                "Cached fluid properties for '%s' expired (%d days old)",
                name, age.days,
            )
            return None

    # Reconstruct FluidProperties
    try:
        cp = doc["cp_J_kgK"]
        rho = doc["density_kg_m3"]
        mu = doc["viscosity_Pa_s"]
        k = doc["k_W_mK"]
        Pr = mu * cp / k if (k and k > 0) else None

        return FluidProperties(
            density_kg_m3=rho,
            viscosity_Pa_s=mu,
            cp_J_kgK=cp,
            k_W_mK=k,
            Pr=Pr,
            property_source="mongodb_cached",
            property_confidence=doc.get("confidence", 0.7),
        )
    except (KeyError, TypeError):
        logger.warning("Malformed cached fluid property document for '%s'", name)
        return None


async def save_fluid_properties(
    fluid_name: str,
    temperature_C: float,
    density_kg_m3: float,
    viscosity_Pa_s: float,
    cp_J_kgK: float,
    k_W_mK: float,
    confidence: float,
    reasoning: str,
) -> None:
    """Save AI-provided fluid properties to MongoDB."""
    coll = await _get_collection()
    if coll is None:
        return

    name = _normalize_name(fluid_name)
    doc = {
        "fluid_name": name,
        "temperature_C": temperature_C,
        "density_kg_m3": density_kg_m3,
        "viscosity_Pa_s": viscosity_Pa_s,
        "cp_J_kgK": cp_J_kgK,
        "k_W_mK": k_W_mK,
        "confidence": confidence,
        "reasoning": reasoning,
        "source": "llm_estimated",
        "created_at": datetime.now(timezone.utc),
    }

    try:
        await coll.insert_one(doc)
        logger.info(
            "Saved AI fluid properties for '%s' at %.1f°C (confidence=%.2f)",
            name, temperature_C, confidence,
        )
    except Exception:
        logger.warning("Failed to save fluid properties to MongoDB", exc_info=True)


# ── LLM call ──────────────────────────────────────────────────────────────────

async def ask_ai_for_properties(
    fluid_name: str,
    temperature_C: float,
    pressure_Pa: float,
) -> FluidProperties | None:
    """Ask Claude for fluid properties, cache if confidence >= threshold.

    Returns FluidProperties if the AI provides a confident answer.
    Returns None if the API key is missing, the call fails, or confidence
    is below the threshold.
    """
    api_key = settings.anthropic_api_key
    if not api_key:
        logger.warning("No ANTHROPIC_API_KEY — cannot ask AI for fluid properties")
        return None

    prompt = _FLUID_PROPERTY_PROMPT.format(
        fluid_name=fluid_name,
        temperature_C=temperature_C,
        pressure_Pa=pressure_Pa,
    )

    try:
        client = AsyncAnthropic(api_key=api_key)
        message = await client.messages.create(
            model=settings.ai_model,
            max_tokens=512,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}],
        )

        text = ""
        for block in message.content:
            if hasattr(block, "text"):
                text += block.text

        # Parse JSON response
        # Strip markdown fences if present
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        data = json.loads(text)

        cp = float(data["cp_J_kgK"])
        rho = float(data["density_kg_m3"])
        mu = float(data["viscosity_Pa_s"])
        k = float(data["k_W_mK"])
        confidence = float(data.get("confidence", 0.5))
        reasoning = str(data.get("reasoning", "AI-estimated"))

        # Sanity checks — reject obviously wrong values
        if cp <= 0 or rho <= 0 or mu <= 0 or k <= 0:
            logger.warning(
                "AI returned non-positive property values for '%s' — rejecting",
                fluid_name,
            )
            return None

        if confidence < _MIN_CONFIDENCE:
            logger.info(
                "AI confidence %.2f for '%s' is below threshold %.2f — not caching",
                confidence, fluid_name, _MIN_CONFIDENCE,
            )
            # Still return the properties but don't cache
            Pr = mu * cp / k
            return FluidProperties(
                density_kg_m3=rho,
                viscosity_Pa_s=mu,
                cp_J_kgK=cp,
                k_W_mK=k,
                Pr=Pr,
                property_source="llm_estimated_low_confidence",
                property_confidence=confidence,
            )

        # Cache in MongoDB
        await save_fluid_properties(
            fluid_name=fluid_name,
            temperature_C=temperature_C,
            density_kg_m3=rho,
            viscosity_Pa_s=mu,
            cp_J_kgK=cp,
            k_W_mK=k,
            confidence=confidence,
            reasoning=reasoning,
        )

        Pr = mu * cp / k
        return FluidProperties(
            density_kg_m3=rho,
            viscosity_Pa_s=mu,
            cp_J_kgK=cp,
            k_W_mK=k,
            Pr=Pr,
            property_source="llm_estimated",
            property_confidence=confidence,
        )

    except json.JSONDecodeError:
        logger.warning("AI returned non-JSON response for fluid '%s'", fluid_name)
        return None
    except Exception:
        logger.warning(
            "AI fluid property lookup failed for '%s'", fluid_name, exc_info=True,
        )
        return None
