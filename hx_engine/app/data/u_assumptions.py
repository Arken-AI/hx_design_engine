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
    # Viscous oil sub-category: high-viscosity organics in laminar flow.
    # U is dominated by the oil-side film (h_i ~ 50-80 W/m²K).
    # Sources: Perry's Table 11-4, Serth Table 3.5.
    ("viscous_oil", "water"):          (20,   60,   100),
    ("water", "viscous_oil"):          (20,   60,   100),
    ("viscous_oil", "light_organic"):  (15,   40,   80),
    ("light_organic", "viscous_oil"):  (15,   40,   80),
    ("viscous_oil", "viscous_oil"):    (10,   30,   60),
    ("viscous_oil", "heavy_organic"):  (10,   30,   60),
    ("heavy_organic", "viscous_oil"):  (10,   30,   60),
    ("steam", "viscous_oil"):          (30,   80,   150),
    ("viscous_oil", "steam"):          (30,   80,   150),
    ("viscous_oil", "crude"):          (10,   30,   60),
    ("crude", "viscous_oil"):          (10,   30,   60),
    # --- P2-21 Phase-change pairs (Coulson §12.1, Serth §3.5) ---
    # Condensing vapour (shell or tube side) × coolant
    ("condensing_vapor_water",       "water"):          (2000, 2750, 3500),  # steam condenser
    ("condensing_vapor_water",       "light_organic"):  (600,  1000, 1500),
    ("condensing_vapor_water",       "heavy_organic"):  (400,  700,  1000),
    ("condensing_vapor_organic",     "water"):          (600,  900,  1200),  # organic condenser
    ("condensing_vapor_organic",     "light_organic"):  (300,  600,  900),
    ("condensing_vapor_organic",     "heavy_organic"):  (200,  400,  700),
    ("condensing_vapor_refrigerant", "water"):          (600,  1000, 1500),  # refrigerant condenser
    ("condensing_vapor_refrigerant", "light_organic"):  (400,  700,  1000),
    # Boiling / evaporating (tube or shell side) × heating medium
    ("boiling_water",       "steam"):                   (1000, 1400, 2000),  # steam-heated evaporator
    ("boiling_water",       "condensing_vapor_water"):  (1000, 1400, 2000),
    ("boiling_water",       "water"):                   (600,  1000, 1500),
    ("boiling_water",       "light_organic"):           (400,  700,  1000),
    ("boiling_organic",     "steam"):                   (400,  700,  1100),  # kettle reboiler
    ("boiling_organic",     "condensing_vapor_water"):  (400,  700,  1100),
    ("boiling_organic",     "water"):                   (300,  600,  900),
    ("boiling_organic",     "light_organic"):           (200,  450,  700),
    ("boiling_organic",     "heavy_organic"):           (150,  300,  500),
    ("boiling_refrigerant", "water"):                   (700,  1000, 1400),  # DX evaporator
    ("boiling_refrigerant", "light_organic"):           (500,  800,  1100),
    # Reverse pairs (hot label is the coolant, cold label is the evaporant)
    ("water",         "boiling_refrigerant"):           (700,  1000, 1400),
    ("water",         "boiling_organic"):               (300,  600,  900),
    ("water",         "boiling_water"):                 (600,  1000, 1500),
    ("steam",         "boiling_organic"):               (400,  700,  1100),
    ("light_organic", "boiling_refrigerant"):           (500,  800,  1100),
    ("light_organic", "condensing_vapor_organic"):      (300,  600,  900),
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

_VISCOUS_OIL_NAMES = {
    "lubricating oil", "lube oil", "lubrication oil",
    "hydraulic oil", "mineral oil", "transformer oil",
    "gear oil", "engine oil", "turbine oil",
}

_HEAVY_ORGANIC_NAMES = {
    "heavy hydrocarbon", "heavy hydrocarbons", "fuel oil",
    "vegetable oil", "bitumen", "tar", "asphalt",
    "ethylene glycol", "propylene glycol", "thermal oil",
}

_GAS_NAMES = {
    "air", "nitrogen", "hydrogen", "oxygen", "flue gas",
    "natural gas", "methane", "carbon dioxide", "helium", "argon",
}

_LIGHT_ORGANIC_NAMES = {
    "gasoline", "kerosene", "diesel", "light hydrocarbon",
    "light hydrocarbons", "methanol", "ethanol", "acetone",
    "toluene", "benzene", "xylene", "hexane", "heptane", "pentane",
    "cyclohexane", "organic solvent", "organic solvents",
}

_REFRIGERANT_NAMES = {
    "r-134a", "r134a", "r-22", "r22", "r-404a", "r404a",
    "r-410a", "r410a", "r-507", "r507", "r-32", "r32",
    "r-290", "r290", "r-600a", "r600a", "r-717", "r717",
    "refrigerant",
}


# ---------------------------------------------------------------------------
# P2-21 — fluid-class helpers (used by phase-aware classify_fluid_type)
# ---------------------------------------------------------------------------

def _is_water_name(name: str) -> bool:
    return name in _WATER_NAMES or name in _STEAM_NAMES or any(
        k in name or name in k for k in _WATER_NAMES | _STEAM_NAMES
    )


def _is_refrigerant_name(name: str) -> bool:
    return name in _REFRIGERANT_NAMES or any(
        k in name or name in k for k in _REFRIGERANT_NAMES
    )


# ---------------------------------------------------------------------------
# Viscosity threshold for viscous_oil classification (Pa·s).
# Oils above this viscosity are typically in laminar tube-side flow
# (Re < 2300) at normal industrial velocities, producing h_i ~ 50-80 W/m²K.
_VISCOUS_OIL_VISCOSITY_THRESHOLD = 0.005  # 5 cP

# Viscosity threshold for heavy_organic fallback classification (Pa·s).
# Unknown fluids above this viscosity but below the viscous_oil threshold
# are moderate-viscosity organics (e.g. light fuel oils, process liquids).
_HEAVY_ORGANIC_VISCOSITY_THRESHOLD = 0.001  # 1 cP


def classify_fluid_type(
    fluid_name: str,
    properties: Optional[FluidProperties] = None,
    phase: Optional[str] = None,
) -> str:
    """Classify a fluid for U-table lookup.

    When ``phase`` is ``"condensing"`` or ``"evaporating"`` (from Step 3),
    returns a phase-change category before any sensible-service path.
    Otherwise falls through to the existing sensible classification.

    Phase-change categories (P2-21): ``condensing_vapor_water``,
    ``condensing_vapor_organic``, ``condensing_vapor_refrigerant``,
    ``boiling_water``, ``boiling_organic``, ``boiling_refrigerant``.
    """
    name = re.sub(r"\s+", " ", fluid_name.strip().lower())

    # P2-21 — phase-change classification takes priority over sensible path
    if phase == "condensing":
        if _is_water_name(name):
            return "condensing_vapor_water"
        if _is_refrigerant_name(name):
            return "condensing_vapor_refrigerant"
        return "condensing_vapor_organic"
    if phase == "evaporating":
        if _is_water_name(name):
            return "boiling_water"
        if _is_refrigerant_name(name):
            return "boiling_refrigerant"
        return "boiling_organic"

    # Name-based classification — viscous_oil checked before heavy_organic
    if name in _WATER_NAMES:
        return "water"
    if name in _STEAM_NAMES:
        return "steam"
    if name in _CRUDE_NAMES:
        return "crude"
    if name in _VISCOUS_OIL_NAMES:
        return "viscous_oil"
    if name in _HEAVY_ORGANIC_NAMES:
        return "heavy_organic"
    if name in _GAS_NAMES:
        return "gas"
    if name in _LIGHT_ORGANIC_NAMES:
        return "light_organic"

    # Partial matching — viscous_oil checked before heavy_organic
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
    for key in _VISCOUS_OIL_NAMES:
        if key in name or name in key:
            return "viscous_oil"
    for key in _HEAVY_ORGANIC_NAMES:
        if key in name or name in key:
            return "heavy_organic"
    for key in _LIGHT_ORGANIC_NAMES:
        if key in name or name in key:
            return "light_organic"

    # Property-based heuristics
    if properties is not None:
        rho = properties.density_kg_m3
        if rho is not None and rho < 50:
            return "gas"
        mu = properties.viscosity_Pa_s
        if mu is not None and mu >= _VISCOUS_OIL_VISCOSITY_THRESHOLD:
            return "viscous_oil"
        if rho is not None and rho > 900:
            return "heavy_organic"
        if mu is not None and mu > _HEAVY_ORGANIC_VISCOSITY_THRESHOLD:
            return "heavy_organic"

    # Generic fallback
    return "liquid"


def get_U_assumption(
    hot_fluid: str,
    cold_fluid: str,
    hot_properties: Optional[FluidProperties] = None,
    cold_properties: Optional[FluidProperties] = None,
    hot_phase: Optional[str] = None,
    cold_phase: Optional[str] = None,
) -> dict[str, float]:
    """Return {"U_low": float, "U_mid": float, "U_high": float} in W/(m²·K).

    Classifies both fluids and looks up the pair. Falls back to a
    conservative liquid-liquid estimate if the pair is unknown.
    Pass ``hot_phase`` / ``cold_phase`` from Step 3 to activate the
    phase-change U categories (P2-21).
    """
    hot_type = classify_fluid_type(hot_fluid, hot_properties, phase=hot_phase)
    cold_type = classify_fluid_type(cold_fluid, cold_properties, phase=cold_phase)

    key = (hot_type, cold_type)
    u_low, u_mid, u_high = _U_TABLE.get(key, _DEFAULT_U)

    return {"U_low": u_low, "U_mid": u_mid, "U_high": u_high}
