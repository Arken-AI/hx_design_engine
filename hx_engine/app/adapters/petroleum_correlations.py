"""Petroleum fraction property correlations.

Industry-standard correlations for computing temperature-dependent
thermophysical properties of any petroleum fraction from API gravity.

Correlations
------------
Cp        : Lee–Kesler (1976) — API Technical Data Book §7D4.1
Density   : SG at 60 °F + ASTM D1250 thermal expansion
Viscosity : Beggs–Robinson (1975) dead-oil correlation
Conductivity : Cragoe (1929) — API TDB §12A3.2

Public API
----------
get_petroleum_properties(char, temperature_C)  → FluidProperties
resolve_petroleum_name(name)                   → PetroleumCharacterization | None
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import FluidProperties

_STEP_ID = 2


# ═══════════════════════════════════════════════════════════════════════════════
# Characterization data class
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PetroleumCharacterization:
    """Bulk characterization of a petroleum fraction.

    Only two parameters are needed to compute all thermophysical
    properties via standard correlations.
    """
    api_gravity: float   # °API
    meabp_C: float       # Mean Average Boiling Point (°C) — for future use


# ═══════════════════════════════════════════════════════════════════════════════
# Helper
# ═══════════════════════════════════════════════════════════════════════════════

def _api_to_sg(api: float) -> float:
    """API gravity → specific gravity at 60 °F."""
    return 141.5 / (api + 131.5)


# ═══════════════════════════════════════════════════════════════════════════════
# Individual correlations (pure functions)
# ═══════════════════════════════════════════════════════════════════════════════

def cp_petroleum(api: float, temperature_C: float) -> float:
    """Lee–Kesler Cp for petroleum fractions.

    Returns Cp in J/(kg·K).

    Reference: Lee & Kesler, AIChE J. 22(3), 510–527, 1976.
    Valid range: API 5–95, T 0–400 °C.
    """
    sg = _api_to_sg(api)
    T_F = temperature_C * 1.8 + 32.0
    cp_btu = 0.6811 - 0.308 * sg + (0.000815 - 0.000306 * sg) * T_F
    return cp_btu * 4186.8


def density_petroleum(api: float, temperature_C: float) -> float:
    """Density from SG at 60 °F + thermal expansion (ASTM D1250 simplified).

    Returns density in kg/m³.
    """
    sg = _api_to_sg(api)
    rho_ref = sg * 999.012         # density at 15.56 °C (60 °F)
    beta = 0.000614 + 0.000124 / sg  # thermal expansion coeff, 1/°C
    rho = rho_ref * (1.0 - beta * (temperature_C - 15.56))
    return rho


def viscosity_petroleum(api: float, temperature_C: float) -> float:
    """Beggs–Robinson dead-oil viscosity.

    Returns dynamic viscosity in Pa·s.

    Reference: Beggs & Robinson, JPT 27(9), 1140–1141, 1975.
    Valid range: API 16–58, T 21–146 °C.
    """
    T_F = temperature_C * 1.8 + 32.0
    if T_F <= 0.0:
        raise CalculationError(
            _STEP_ID,
            f"Temperature {temperature_C}°C is below Beggs–Robinson valid range",
        )
    z = 3.0324 - 0.02023 * api
    y = 10.0 ** z
    x = y * (T_F ** -1.163)
    mu_cp = 10.0 ** x - 1.0
    return mu_cp * 1e-3  # centipoise → Pa·s


def conductivity_petroleum(api: float, temperature_C: float) -> float:
    """Cragoe thermal conductivity for petroleum fractions.

    Returns thermal conductivity in W/(m·K).

    Reference: Cragoe, NBS Misc. Pub. No. 97, 1929; API TDB §12A3.2.
    """
    sg = _api_to_sg(api)
    k = (0.11935 / sg) * (1.0 - 0.00054 * temperature_C)
    return k


# ═══════════════════════════════════════════════════════════════════════════════
# Crude oil database
# ═══════════════════════════════════════════════════════════════════════════════
# Published API gravities from public assay data (OPEC, EIA, operator TDS).
# MeABP values are representative mid-range estimates.

CRUDE_DATABASE: dict[str, PetroleumCharacterization] = {
    # ── Middle East ──
    "arab light":       PetroleumCharacterization(33.4, 260),
    "arab heavy":       PetroleumCharacterization(27.4, 290),
    "arab medium":      PetroleumCharacterization(30.4, 275),
    "arab extra light": PetroleumCharacterization(38.5, 240),
    "murban":           PetroleumCharacterization(40.5, 230),
    "abu bukhoosh":     PetroleumCharacterization(31.6, 270),
    "iranian light":    PetroleumCharacterization(33.8, 260),
    "iranian heavy":    PetroleumCharacterization(30.0, 280),
    "kuwait":           PetroleumCharacterization(31.4, 275),
    "basrah light":     PetroleumCharacterization(33.7, 260),
    "kirkuk":           PetroleumCharacterization(36.1, 250),
    "qatar marine":     PetroleumCharacterization(36.0, 250),

    # ── Americas ──
    "wti":                      PetroleumCharacterization(39.6, 235),
    "west texas intermediate":  PetroleumCharacterization(39.6, 235),
    "maya":                     PetroleumCharacterization(22.2, 320),
    "isthmus":                  PetroleumCharacterization(33.7, 260),
    "marlim":                   PetroleumCharacterization(19.2, 340),
    "mars":                     PetroleumCharacterization(28.9, 280),
    "lls":                      PetroleumCharacterization(36.0, 248),
    "louisiana light sweet":    PetroleumCharacterization(36.0, 248),
    "cold lake":                PetroleumCharacterization(13.2, 380),
    "athabasca":                PetroleumCharacterization(8.0,  400),

    # ── Europe / FSU ──
    "brent":    PetroleumCharacterization(38.3, 240),
    "forties":  PetroleumCharacterization(40.5, 230),
    "ekofisk":  PetroleumCharacterization(37.7, 245),
    "ural":     PetroleumCharacterization(31.8, 270),
    "urals":    PetroleumCharacterization(31.8, 270),

    # ── Africa ──
    "bonny light":    PetroleumCharacterization(35.4, 250),
    "forcados":       PetroleumCharacterization(29.7, 285),
    "saharan blend":  PetroleumCharacterization(45.5, 200),
    "cabinda":        PetroleumCharacterization(31.7, 270),
    "girassol":       PetroleumCharacterization(30.8, 275),

    # ── Asia / Oceania ──
    "tapis":   PetroleumCharacterization(44.3, 210),
    "minas":   PetroleumCharacterization(34.5, 255),
    "duri":    PetroleumCharacterization(21.1, 325),
    "cossack": PetroleumCharacterization(48.5, 195),
    "daqing":  PetroleumCharacterization(32.6, 265),
}

# ═══════════════════════════════════════════════════════════════════════════════
# Petroleum fraction database
# ═══════════════════════════════════════════════════════════════════════════════

FRACTION_DATABASE: dict[str, PetroleumCharacterization] = {
    "crude oil":        PetroleumCharacterization(33.0, 270),   # generic medium
    "mineral oil":      PetroleumCharacterization(32.0, 280),
    "naphtha":          PetroleumCharacterization(60.0, 100),
    "light naphtha":    PetroleumCharacterization(70.0, 70),
    "heavy naphtha":    PetroleumCharacterization(50.0, 150),
    "kerosene":         PetroleumCharacterization(43.0, 200),
    "jet fuel":         PetroleumCharacterization(44.0, 195),
    "diesel":           PetroleumCharacterization(35.0, 270),
    "gas oil":          PetroleumCharacterization(30.0, 320),
    "light gas oil":    PetroleumCharacterization(35.0, 280),
    "heavy gas oil":    PetroleumCharacterization(22.0, 370),
    "vacuum gas oil":   PetroleumCharacterization(22.0, 400),
    "gasoline":         PetroleumCharacterization(58.0, 100),
    "fuel oil":         PetroleumCharacterization(15.0, 400),
    "heavy fuel oil":   PetroleumCharacterization(12.0, 420),
    "lubricating oil":  PetroleumCharacterization(28.0, 350),
    # Common engineering aliases
    "diesel fuel":      PetroleumCharacterization(35.0, 270),   # = diesel
    "diesel oil":       PetroleumCharacterization(35.0, 270),   # = diesel
    "lube oil":         PetroleumCharacterization(28.0, 350),   # = lubricating oil
    "heating oil":      PetroleumCharacterization(15.0, 400),   # = fuel oil
    "bunker fuel":      PetroleumCharacterization(12.0, 420),   # = heavy fuel oil
    "bunker oil":       PetroleumCharacterization(12.0, 420),   # = heavy fuel oil
    "hfo":              PetroleumCharacterization(12.0, 420),   # = heavy fuel oil
    "residual fuel":    PetroleumCharacterization(12.0, 420),   # = heavy fuel oil
}


# ═══════════════════════════════════════════════════════════════════════════════
# Name resolution
# ═══════════════════════════════════════════════════════════════════════════════

# Words to strip when matching crude qualifier names.
_STRIP_SUFFIXES = ("crude oil", "crude", "oil")


def resolve_petroleum_name(
    name: str,
) -> Optional[PetroleumCharacterization]:
    """Resolve a user-supplied fluid name to petroleum characterization data.

    Tries progressively stripped forms of the name against the crude
    database first, then the fraction database.

    Returns ``None`` if no match is found.
    """
    normalised = name.strip().lower()

    # Build candidate keys: original, then progressively stripped.
    candidates: list[str] = [normalised]
    for suffix in _STRIP_SUFFIXES:
        if normalised.endswith(suffix):
            stripped = normalised[: -len(suffix)].strip()
            if stripped:
                candidates.append(stripped)

    # Also try stripping leading qualifiers against crude DB.
    # e.g. "light crude oil" → we already have "light" but that isn't a crude
    # so this is mainly for "Maya crude oil" → "maya"

    for key in candidates:
        if key in CRUDE_DATABASE:
            return CRUDE_DATABASE[key]

    for key in candidates:
        if key in FRACTION_DATABASE:
            return FRACTION_DATABASE[key]

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Composite property retrieval
# ═══════════════════════════════════════════════════════════════════════════════

# Physical bounds for pre-validation (matching FluidProperties validators).
_RHO_MIN, _RHO_MAX = 50.0, 2000.0
_MU_MIN, _MU_MAX = 1e-6, 1.0
_CP_MIN, _CP_MAX = 500.0, 10000.0
_K_MIN, _K_MAX = 0.01, 100.0
_PR_MIN, _PR_MAX = 0.5, 1000.0


def get_petroleum_properties(
    char: PetroleumCharacterization,
    temperature_C: float,
) -> FluidProperties:
    """Compute all properties from correlations and return FluidProperties.

    Pre-validates each property against FluidProperties bounds and raises
    a descriptive ``CalculationError`` if any fall outside the range.
    """
    api = char.api_gravity

    cp  = cp_petroleum(api, temperature_C)
    rho = density_petroleum(api, temperature_C)
    mu  = viscosity_petroleum(api, temperature_C)
    k   = conductivity_petroleum(api, temperature_C)
    Pr  = mu * cp / k

    # ── pre-validate before constructing FluidProperties ──────────────
    _validate_range("density", rho, _RHO_MIN, _RHO_MAX, "kg/m³",
                    api, temperature_C)
    _validate_range("viscosity", mu, _MU_MIN, _MU_MAX, "Pa·s",
                    api, temperature_C)
    _validate_range("Cp", cp, _CP_MIN, _CP_MAX, "J/kg·K",
                    api, temperature_C)
    _validate_range("conductivity", k, _K_MIN, _K_MAX, "W/m·K",
                    api, temperature_C)
    _validate_range("Prandtl", Pr, _PR_MIN, _PR_MAX, "–",
                    api, temperature_C)

    return FluidProperties(
        density_kg_m3=rho,
        viscosity_Pa_s=mu,
        cp_J_kgK=cp,
        k_W_mK=k,
        Pr=Pr,
    )


def _validate_range(
    prop_name: str,
    value: float,
    lo: float,
    hi: float,
    unit: str,
    api: float,
    temperature_C: float,
) -> None:
    if value < lo or value > hi:
        raise CalculationError(
            _STEP_ID,
            f"{prop_name} = {value:.4g} {unit} is outside the valid range "
            f"[{lo}, {hi}] for API {api}° at {temperature_C}°C. "
            f"Consider adjusting the operating temperature or providing "
            f"fluid properties directly via DesignState.",
        )
