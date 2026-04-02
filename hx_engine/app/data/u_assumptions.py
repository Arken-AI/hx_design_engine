"""Starting-guess overall heat transfer coefficients (U) by fluid pair.

Data source: Coulson & Richardson Table 12.1 / Perry's Table 11-4.
Values in W/(m²·K).
"""

from __future__ import annotations

import re
from typing import Optional

from hx_engine.app.models.design_state import FluidProperties


# ---------------------------------------------------------------------------
# U assumption table: (hot_type, cold_type) → (U_low, U_mid, U_high)
# ---------------------------------------------------------------------------

_U_TABLE: dict[tuple[str, str], tuple[float, float, float]] = {
    # (hot_type, cold_type): (U_low, U_mid, U_high)  W/(m²·K)
    ("water", "water"):                (800,  1200, 1800),
    ("light_organic", "light_organic"):(100,  300,  500),
    ("heavy_organic", "heavy_organic"):(50,   150,  300),
    ("light_organic", "water"):        (200,  500,  800),
    ("water", "light_organic"):        (200,  500,  800),
    ("heavy_organic", "water"):        (100,  300,  500),
    ("water", "heavy_organic"):        (100,  300,  500),
    ("crude", "water"):                (100,  300,  500),
    ("water", "crude"):                (100,  300,  500),
    ("gas", "gas"):                    (5,    25,   50),
    ("gas", "liquid"):                 (15,   50,   150),
    ("liquid", "gas"):                 (15,   50,   150),
    ("gas", "water"):                  (15,   50,   150),
    ("water", "gas"):                  (15,   50,   150),
    ("steam", "water"):                (1000, 2500, 4000),
    ("water", "steam"):                (1000, 2500, 4000),
    ("steam", "light_organic"):        (250,  750,  1200),
    ("light_organic", "steam"):        (250,  750,  1200),
    ("steam", "heavy_organic"):        (100,  400,  700),
    ("heavy_organic", "steam"):        (100,  400,  700),
    ("steam", "crude"):                (100,  300,  500),
    ("crude", "steam"):                (100,  300,  500),
    ("crude", "light_organic"):        (60,   200,  400),
    ("light_organic", "crude"):        (60,   200,  400),
    ("crude", "heavy_organic"):        (40,   120,  250),
    ("heavy_organic", "crude"):        (40,   120,  250),
    ("crude", "crude"):                (40,   120,  250),
}

# Default (liquid-liquid) when pair not found
_DEFAULT_U = (100, 300, 500)


# ---------------------------------------------------------------------------
# Fluid type classification
# ---------------------------------------------------------------------------

_WATER_NAMES = {
    "water", "cooling water", "cooling tower water", "city water",
    "river water", "boiler feedwater", "treated water", "distilled water",
    "brine", "seawater",
}

_STEAM_NAMES = {
    "steam", "steam condensate", "saturated steam", "superheated steam",
}

_CRUDE_NAMES = {
    "crude oil", "crude", "heavy crude", "light crude",
}

_HEAVY_ORGANIC_NAMES = {
    "heavy hydrocarbon", "heavy hydrocarbons", "fuel oil",
    "vegetable oil", "bitumen", "tar", "asphalt",
    "ethylene glycol", "propylene glycol", "thermal oil",
    "lubricating oil", "lube oil", "lubrication oil",
    "hydraulic oil", "mineral oil", "transformer oil",
    "gear oil", "engine oil", "turbine oil",
}

_GAS_NAMES = {
    "air", "nitrogen", "hydrogen", "oxygen", "flue gas",
    "natural gas", "methane", "carbon dioxide", "helium", "argon",
}

_LIGHT_ORGANIC_NAMES = {
    "gasoline", "kerosene", "diesel", "light hydrocarbon",
    "light hydrocarbons", "methanol", "ethanol", "acetone",
    "toluene", "benzene", "xylene", "hexane", "heptane", "pentane",
    "cyclohexane", "ammonia", "refrigerant", "organic solvent",
    "organic solvents",
}


def classify_fluid_type(
    fluid_name: str,
    properties: Optional[FluidProperties] = None,
) -> str:
    """Classify a fluid as 'water', 'steam', 'crude', 'heavy_organic',
    'light_organic', 'gas', or 'liquid' (generic fallback).

    Uses name matching first, then property-based heuristics if available.
    """
    name = re.sub(r"\s+", " ", fluid_name.strip().lower())

    # Name-based classification
    if name in _WATER_NAMES:
        return "water"
    if name in _STEAM_NAMES:
        return "steam"
    if name in _CRUDE_NAMES:
        return "crude"
    if name in _HEAVY_ORGANIC_NAMES:
        return "heavy_organic"
    if name in _GAS_NAMES:
        return "gas"
    if name in _LIGHT_ORGANIC_NAMES:
        return "light_organic"

    # Partial matching
    for key in _WATER_NAMES:
        if key in name or name in key:
            return "water"
    for key in _STEAM_NAMES:
        if key in name or name in key:
            return "steam"
    for key in _CRUDE_NAMES:
        if key in name or name in key:
            return "crude"
    for key in _GAS_NAMES:
        if key in name or name in key:
            return "gas"
    for key in _HEAVY_ORGANIC_NAMES:
        if key in name or name in key:
            return "heavy_organic"
    for key in _LIGHT_ORGANIC_NAMES:
        if key in name or name in key:
            return "light_organic"

    # Property-based heuristics
    if properties is not None:
        rho = properties.density_kg_m3
        if rho is not None:
            if rho < 50:
                return "gas"
            if rho > 900:
                return "heavy_organic"
        mu = properties.viscosity_Pa_s
        if mu is not None and mu > 0.01:
            return "heavy_organic"

    # Generic fallback
    return "liquid"


def get_U_assumption(hot_fluid: str, cold_fluid: str) -> dict[str, float]:
    """Return {"U_low": float, "U_mid": float, "U_high": float} in W/(m²·K).

    Classifies both fluids and looks up the pair. Falls back to a
    conservative liquid-liquid estimate if the pair is unknown.
    """
    hot_type = classify_fluid_type(hot_fluid)
    cold_type = classify_fluid_type(cold_fluid)

    key = (hot_type, cold_type)
    u_low, u_mid, u_high = _U_TABLE.get(key, _DEFAULT_U)

    return {"U_low": u_low, "U_mid": u_mid, "U_high": u_high}
