"""Fouling resistance (R_f) lookup by fluid type.

Data source: TEMA Standards Table RGP-T-2.4 / Perry's Table 11-10.
Values in m²·K/W.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fouling data
# ---------------------------------------------------------------------------

# (fluid_key, optional_temp_range) → R_f in m²·K/W
# For temperature-independent fluids, temp range is None.
# For temperature-dependent fluids, entries are (T_min_C, T_max_C, R_f).

_FOULING_SIMPLE: dict[str, float] = {
    "water":               0.000176,
    "cooling tower water": 0.000352,
    "cooling water":       0.000176,
    "river water":         0.000528,
    "city water":          0.000176,
    "boiler feedwater":    0.000088,
    "treated water":       0.000088,
    "distilled water":     0.000088,
    "steam":               0.000088,
    "steam condensate":    0.000088,
    "light hydrocarbon":   0.000176,
    "light hydrocarbons":  0.000176,
    "lube oil":            0.000176,
    "lubricating oil":     0.000176,
    "gasoline":            0.000176,
    "kerosene":            0.000176,
    "diesel":              0.000352,
    "fuel oil":            0.000528,
    "refrigerant":         0.000176,
    "refrigerant liquid":  0.000176,
    "organic solvent":     0.000176,
    "organic solvents":    0.000176,
    "vegetable oil":       0.000528,
    "methanol":            0.000176,
    "ethanol":             0.000176,
    "ethylene glycol":     0.000352,
    "propylene glycol":    0.000352,
    "thermal oil":         0.000176,
    "air":                 0.000352,
    "flue gas":            0.000528,
    "hydrogen":            0.000088,
    "nitrogen":            0.000088,
    "natural gas":         0.000176,
    "ammonia":             0.000176,
    "brine":               0.000352,
    "molten salt":         0.000088,
}

# Temperature-dependent fluids: list of (T_min_C, T_max_C, R_f)
_FOULING_TEMP_DEPENDENT: dict[str, list[tuple[float, float, float]]] = {
    "seawater": [
        (-50, 50, 0.000088),
        (50, 500, 0.000352),
    ],
    "crude oil": [
        (-50, 120, 0.000352),
        (120, 175, 0.000528),
        (175, 500, 0.000704),
    ],
    "crude": [
        (-50, 120, 0.000352),
        (120, 175, 0.000528),
        (175, 500, 0.000704),
    ],
    "heavy hydrocarbon": [
        (-50, 200, 0.000352),
        (200, 500, 0.000528),
    ],
    "heavy hydrocarbons": [
        (-50, 200, 0.000352),
        (200, 500, 0.000528),
    ],
}

# Classification thresholds
_CLEAN_THRESHOLD = 0.000176      # ≤ this → clean
_MODERATE_THRESHOLD = 0.000352   # ≤ this → moderate
_HEAVY_THRESHOLD = 0.000704      # ≤ this → heavy
# > _HEAVY_THRESHOLD → severe

# Default for unknown fluids (conservative)
_DEFAULT_RF = 0.000352

# ---------------------------------------------------------------------------
# Lower bounds per fluid class (TEMA minimum expected value for the service)
# Used by FE-2 to detect when a resolved Rf is at the TEMA minimum, which
# signals that actual service conditions may push it significantly higher.
# ---------------------------------------------------------------------------
_FOULING_LOWER_BOUNDS: dict[str, float] = {
    "lube oil":            0.000176,
    "lubricating oil":     0.000176,
    "light hydrocarbon":   0.000176,
    "light hydrocarbons":  0.000176,
    "gasoline":            0.000176,
    "kerosene":            0.000176,
    "diesel":              0.000176,
    "fuel oil":            0.000352,
    "heavy hydrocarbon":   0.000352,
    "heavy hydrocarbons":  0.000352,
    "crude oil":           0.000176,  # lowest range value (clean crude, T < 120°C)
    "crude":               0.000176,
    "thermal oil":         0.000176,
    "organic solvent":     0.000176,
    "organic solvents":    0.000176,
}

# ---------------------------------------------------------------------------
# Location / condition-dependent fluids
# ---------------------------------------------------------------------------
# These fluids have R_f values that vary significantly depending on
# geographic location, water quality, seasonal conditions, or process
# specifics.  The table values are TEMA mid-range defaults.  AI should
# always be asked to refine these.
_LOCATION_DEPENDENT: set[str] = {
    "river water",
    "seawater",
    "cooling tower water",
    "cooling water",
    "city water",
    "brine",
    "crude oil",
    "crude",
}


def _normalize_name(fluid_name: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return re.sub(r"\s+", " ", fluid_name.strip().lower())


def _lookup(
    fluid_name: str, temperature_C: float | None,
) -> tuple[float | None, str]:
    """Internal lookup returning (R_f, source) or (None, 'unknown').

    source is one of:
      'exact'          – direct key match in the simple table
      'temp_dependent' – matched in the temperature-dependent table
      'partial_match'  – substring match against table keys
      'unknown'        – no match found
    """
    name = _normalize_name(fluid_name)

    # Check temperature-dependent first
    if name in _FOULING_TEMP_DEPENDENT:
        ranges = _FOULING_TEMP_DEPENDENT[name]
        if temperature_C is not None:
            for t_min, t_max, rf in ranges:
                if t_min <= temperature_C <= t_max:
                    return rf, "temp_dependent"
        # No temperature given or out of range: return the first range
        return ranges[0][2], "temp_dependent"

    # Check simple table
    if name in _FOULING_SIMPLE:
        return _FOULING_SIMPLE[name], "exact"

    # Try partial matching
    for key, rf in _FOULING_SIMPLE.items():
        if key in name or name in key:
            return rf, "partial_match"

    for key in _FOULING_TEMP_DEPENDENT:
        if key in name or name in key:
            ranges = _FOULING_TEMP_DEPENDENT[key]
            if temperature_C is not None:
                for t_min, t_max, rf in ranges:
                    if t_min <= temperature_C <= t_max:
                        return rf, "partial_match"
            return ranges[0][2], "partial_match"

    return None, "unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_fouling_factor(
    fluid_name: str, temperature_C: float | None = None,
) -> float:
    """Return R_f in m²·K/W for a fluid.

    For temperature-dependent fluids (e.g. crude oil, seawater),
    *temperature_C* selects the appropriate range.
    Unknown fluids return a conservative default (0.000352) with a warning.
    """
    rf, _source = _lookup(fluid_name, temperature_C)
    if rf is not None:
        return rf

    logger.warning(
        "Unknown fluid '%s' for fouling lookup; using default R_f=%.6f",
        fluid_name, _DEFAULT_RF,
    )
    return _DEFAULT_RF


def get_fouling_factor_with_source(
    fluid_name: str, temperature_C: float | None = None,
) -> dict:
    """Return fouling factor with metadata about how it was determined.

    Returns a dict with:
      rf            – R_f value in m²·K/W
      source        – 'exact', 'temp_dependent', 'partial_match', or 'ai_recommended'
      needs_ai      – True if the value is uncertain and AI should refine it
      reason        – human-readable explanation
    """
    rf, source = _lookup(fluid_name, temperature_C)
    name = _normalize_name(fluid_name)

    if rf is None:
        return {
            "rf": _DEFAULT_RF,
            "source": "ai_recommended",
            "needs_ai": True,
            "reason": (
                f"Fluid '{fluid_name}' is not in the standard fouling tables. "
                f"Using conservative default R_f={_DEFAULT_RF:.6f} m²·K/W. "
                f"AI should determine the correct fouling resistance based on "
                f"the fluid's properties, service conditions, and industry data."
            ),
        }

    # Check if this is a location/condition-dependent fluid
    loc_dep = name in _LOCATION_DEPENDENT
    # Also check partial-match keys
    if not loc_dep and source == "partial_match":
        for key in _LOCATION_DEPENDENT:
            if key in name or name in key:
                loc_dep = True
                break

    if loc_dep:
        return {
            "rf": rf,
            "source": source,
            "needs_ai": True,
            "reason": (
                f"Fluid '{fluid_name}' has a table value R_f={rf:.6f} m²·K/W, "
                f"but fouling varies significantly by location, water quality, "
                f"and operating conditions. AI should confirm or adjust this value "
                f"based on the specific service conditions."
            ),
        }

    return {
        "rf": rf,
        "source": source,
        "needs_ai": False,
        "reason": f"Standard table lookup: R_f={rf:.6f} m²·K/W.",
    }


def is_location_dependent(fluid_name: str) -> bool:
    """True if this fluid's fouling factor varies by location/conditions.

    Only matches when a known location-dependent key appears *within* the
    fluid name (e.g. 'dirty river water' matches 'river water') — not the
    other way around, to avoid 'water' matching 'cooling water'.
    """
    name = _normalize_name(fluid_name)
    if name in _LOCATION_DEPENDENT:
        return True
    for key in _LOCATION_DEPENDENT:
        if key in name:
            return True
    return False


def classify_fouling(
    fluid_name: str, temperature_C: float | None = None,
) -> str:
    """Return 'clean', 'moderate', 'heavy', or 'severe'.

    Uses the table lookup R_f value (or conservative default for unknown
    fluids).  For location-dependent or unknown fluids, the *classification*
    is based on the best-available value; the step layer is responsible for
    escalating uncertain values to AI.
    """
    rf = get_fouling_factor(fluid_name, temperature_C)
    if rf <= _CLEAN_THRESHOLD:
        return "clean"
    if rf <= _MODERATE_THRESHOLD:
        return "moderate"
    if rf <= _HEAVY_THRESHOLD:
        return "heavy"
    return "severe"


def is_fouling_fluid(
    fluid_name: str, temperature_C: float | None = None,
) -> bool:
    """True if R_f > 0.000352 (moderate-heavy or worse)."""
    rf = get_fouling_factor(fluid_name, temperature_C)
    return rf > _MODERATE_THRESHOLD


def get_fouling_lower_bound(
    fluid_name: str, temperature_C: float | None = None,
) -> float | None:
    """Return the TEMA lower-bound R_f for a fluid class, or None if unknown.

    Used by FE-2 to check whether a resolved Rf is at the TEMA minimum —
    if so, actual service may push it higher, warranting a warning.
    """
    name = _normalize_name(fluid_name)
    if name in _FOULING_LOWER_BOUNDS:
        return _FOULING_LOWER_BOUNDS[name]
    for key, lb in _FOULING_LOWER_BOUNDS.items():
        if key in name or name in key:
            return lb
    return None


# ---------------------------------------------------------------------------
# 3-Tier Async Lookup: Table → MongoDB → Claude AI
# ---------------------------------------------------------------------------

async def resolve_fouling_factor(
    fluid_name: str,
    temperature_C: float | None = None,
    additional_context: str | None = None,
) -> dict:
    """3-tier fouling factor resolution.

    Tier 1: Hardcoded TEMA tables (instant, no I/O)
    Tier 2: MongoDB cache of previous AI/user values
    Tier 3: Claude AI call (slow, costs money)

    Returns:
        {
            "rf": float,
            "confidence": float,        # 1.0 for table, 0.0-1.0 for AI
            "source": str,              # "table", "mongodb_cache", "ai", "fallback"
            "needs_user_confirmation": bool,  # True if confidence < THRESHOLD
            "reasoning": str,
            "ai_suggestion": dict|None, # Full AI response if AI was called
        }
    """
    from hx_engine.app.core.fouling_store import find_cached_fouling, save_fouling_factor
    from hx_engine.app.core.fouling_ai import get_fouling_from_ai

    CONFIDENCE_THRESHOLD = 0.7

    # --- Tier 1: Table lookup ---
    info = get_fouling_factor_with_source(fluid_name, temperature_C)
    if not info["needs_ai"]:
        return {
            "rf": info["rf"],
            "confidence": 1.0,
            "source": "table",
            "needs_user_confirmation": False,
            "reasoning": info["reason"],
            "ai_suggestion": None,
        }

    # --- Tier 2: MongoDB cache ---
    cached = await find_cached_fouling(fluid_name, temperature_C)
    if cached is not None:
        rf_val = cached.get("user_override") or cached["rf_value"]
        return {
            "rf": rf_val,
            "confidence": cached.get("confidence", 0.8),
            "source": "mongodb_cache",
            "needs_user_confirmation": False,
            "reasoning": (
                f"Cached value from {cached.get('accepted_by', 'ai')} "
                f"(saved {cached.get('created_at', 'unknown')}): "
                f"{cached.get('reasoning', 'N/A')}"
            ),
            "ai_suggestion": None,
        }

    # --- Tier 3: Claude AI ---
    ai_result = await get_fouling_from_ai(
        fluid_name, temperature_C, additional_context,
    )

    if ai_result.get("error"):
        # AI failed — use table default, flag for user
        return {
            "rf": info["rf"],
            "confidence": 0.0,
            "source": "fallback",
            "needs_user_confirmation": True,
            "reasoning": (
                f"AI call failed: {ai_result['error']}. "
                f"Using table default R_f={info['rf']:.6f}."
            ),
            "ai_suggestion": ai_result,
        }

    # AI succeeded — check confidence
    ai_confidence = ai_result["confidence"]
    needs_confirmation = ai_confidence < CONFIDENCE_THRESHOLD

    if not needs_confirmation:
        # High confidence — save to MongoDB and use
        await save_fouling_factor(
            fluid_name=fluid_name,
            temperature_C=temperature_C,
            rf_value=ai_result["rf_value"],
            confidence=ai_confidence,
            reasoning=ai_result["reasoning"],
            source=ai_result["source"],
            accepted_by="ai",
        )

    return {
        "rf": ai_result["rf_value"],
        "confidence": ai_confidence,
        "source": "ai",
        "needs_user_confirmation": needs_confirmation,
        "reasoning": ai_result["reasoning"],
        "ai_suggestion": ai_result,
    }
