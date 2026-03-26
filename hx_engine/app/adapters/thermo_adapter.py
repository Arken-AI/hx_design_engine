"""Thermophysical property retrieval for heat exchanger fluids.

Priority chain
--------------
1. iapws         — water / steam  (IAPWS-IF97, T/P-dependent)
2. CoolProp      — pure compounds (T/P-dependent, 124 fluids)
3. thermo        — broad chemical database (Caleb Bell, thousands of compounds)
4. Petroleum     — crude oils & fractions via Lee–Kesler / Beggs–Robinson /
                   Cragoe correlations parameterised by API gravity (T-dependent)
5. Specialty     — glycols, thermal oil, vegetable oil, molten salt
                   (T-dependent engineering fits)

Public API
----------
get_fluid_properties(fluid_name, temperature_C, pressure_Pa) → FluidProperties
get_cp(fluid_name, temperature_C, pressure_Pa)               → float  (J/kg·K)
"""

from __future__ import annotations

import math
from typing import Callable, Optional

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import FluidProperties
from hx_engine.app.adapters.petroleum_correlations import (
    get_petroleum_properties,
    resolve_petroleum_name,
)

# ── optional library imports ──────────────────────────────────────────────────

try:
    import iapws as _iapws          # water / steam  (IAPWS-IF97)
except ImportError:                  # pragma: no cover
    _iapws = None

try:
    import CoolProp.CoolProp as _CP  # pure-component fluids
except ImportError:                   # pragma: no cover
    _CP = None

try:
    from thermo import Chemical as _Chemical  # broad chemical DB
except ImportError:                            # pragma: no cover
    _Chemical = None

_STEP_ID = 2  # used in CalculationError

# ── water / steam name detection ──────────────────────────────────────────────

_WATER_ALIASES: frozenset[str] = frozenset({
    "water", "cooling water", "chilled water", "hot water",
    "boiler water", "sea water", "seawater", "condensate",
    "brine",  # approximate as water — user can override
})

_STEAM_ALIASES: frozenset[str] = frozenset({
    "steam",
})


def _is_water_or_steam(name: str) -> bool:
    return name in _WATER_ALIASES or name in _STEAM_ALIASES


# ── CoolProp fluid-name mapping ──────────────────────────────────────────────
# Maps user-friendly names to CoolProp canonical names.

_COOLPROP_MAP: dict[str, str] = {
    "ethanol": "Ethanol",
    "methanol": "Methanol",
    "ammonia": "Ammonia",
    "toluene": "Toluene",
    "benzene": "Benzene",
    "acetone": "Acetone",
    "hexane": "n-Hexane",
    "heptane": "n-Heptane",
    "pentane": "n-Pentane",
    "nitrogen": "Nitrogen",
    "air": "Air",
    "hydrogen": "Hydrogen",
    "oxygen": "Oxygen",
    "xylene": "o-Xylene",
    "cyclohexane": "CycloHexane",
}


# ── specialty fluid T-dependent models ────────────────────────────────────────
# For non-petroleum, non-CoolProp fluids.  Each function takes temperature in
# °C and returns FluidProperties.  Fits are from manufacturer datasheets and
# engineering handbooks (Perry's, Yaws, GPSA).

def _thermal_oil_props(T: float) -> FluidProperties:
    """Therminol-66-representative synthetic heat-transfer oil."""
    rho = 1020.0 - 0.58 * T
    cp = 1500.0 + 3.3 * T
    mu = 0.037 * math.exp(-0.018 * T)
    k = 0.118 - 1.5e-4 * T
    return FluidProperties(
        density_kg_m3=rho, viscosity_Pa_s=mu, cp_J_kgK=cp,
        k_W_mK=k, Pr=mu * cp / k,
    )


def _vegetable_oil_props(T: float) -> FluidProperties:
    """Generic vegetable oil (soybean-representative)."""
    rho = 930.0 - 0.60 * T
    cp = 1900.0 + 3.0 * T
    mu = 0.118 * math.exp(-0.027 * T)
    k = 0.17 - 1.5e-4 * T
    return FluidProperties(
        density_kg_m3=rho, viscosity_Pa_s=mu, cp_J_kgK=cp,
        k_W_mK=k, Pr=mu * cp / k,
    )


def _ethylene_glycol_props(T: float) -> FluidProperties:
    """Pure ethylene glycol."""
    rho = 1130.0 - 0.65 * T
    cp = 2350.0 + 2.0 * T
    mu = 0.032 * math.exp(-0.028 * T)
    k = 0.256 - 1.5e-4 * T
    return FluidProperties(
        density_kg_m3=rho, viscosity_Pa_s=mu, cp_J_kgK=cp,
        k_W_mK=k, Pr=mu * cp / k,
    )


def _propylene_glycol_props(T: float) -> FluidProperties:
    """Pure propylene glycol."""
    rho = 1050.0 - 0.60 * T
    cp = 2480.0 + 2.5 * T
    mu = 0.095 * math.exp(-0.034 * T)
    k = 0.20 - 1.5e-4 * T
    return FluidProperties(
        density_kg_m3=rho, viscosity_Pa_s=mu, cp_J_kgK=cp,
        k_W_mK=k, Pr=mu * cp / k,
    )


def _molten_salt_props(T: float) -> FluidProperties:
    """Solar salt (60 % NaNO₃ / 40 % KNO₃), valid ≈ 220–600 °C."""
    rho = 2000.0 - 0.636 * (T - 260.0)
    cp = 1550.0
    mu = max(0.006 - 1.0e-5 * T, 1e-5)
    k = 0.52 + 2.7e-4 * (T - 220.0)
    return FluidProperties(
        density_kg_m3=rho, viscosity_Pa_s=mu, cp_J_kgK=cp,
        k_W_mK=k, Pr=mu * cp / k,
    )


_SPECIALTY_FLUIDS: dict[str, Callable[[float], FluidProperties]] = {
    "thermal oil":      _thermal_oil_props,
    "vegetable oil":    _vegetable_oil_props,
    "glycol":           _ethylene_glycol_props,
    "ethylene glycol":  _ethylene_glycol_props,
    "propylene glycol": _propylene_glycol_props,
    "molten salt":      _molten_salt_props,
}

# ── iapws water/steam retrieval ───────────────────────────────────────────────


def _get_props_iapws(
    temperature_C: float,
    pressure_Pa: float,
) -> FluidProperties:
    """Retrieve properties via IAPWS-IF97 (water / steam)."""
    if _iapws is None:
        raise CalculationError(
            _STEP_ID, "iapws library not installed — cannot compute water properties"
        )

    T_K = temperature_C + 273.15
    P_MPa = pressure_Pa / 1e6

    try:
        w = _iapws.IAPWS97(T=T_K, P=P_MPa)
    except Exception as exc:
        raise CalculationError(
            _STEP_ID,
            f"iapws lookup failed at T={temperature_C}°C, P={pressure_Pa} Pa",
            cause=exc,
        ) from exc

    # iapws returns cp in kJ/(kg·K) → multiply by 1000
    return FluidProperties(
        density_kg_m3=w.rho,
        viscosity_Pa_s=w.mu,
        cp_J_kgK=w.cp * 1000.0,
        k_W_mK=w.k,
        Pr=w.Prandt,
    )


# ── CoolProp retrieval ───────────────────────────────────────────────────────


def _get_props_coolprop(
    coolprop_name: str,
    temperature_C: float,
    pressure_Pa: float,
) -> FluidProperties:
    """Retrieve properties via CoolProp."""
    if _CP is None:
        raise CalculationError(
            _STEP_ID,
            "CoolProp library not installed — cannot compute fluid properties",
        )

    T_K = temperature_C + 273.15

    try:
        cp = _CP.PropsSI("C", "T", T_K, "P", pressure_Pa, coolprop_name)
        rho = _CP.PropsSI("D", "T", T_K, "P", pressure_Pa, coolprop_name)
        mu = _CP.PropsSI("V", "T", T_K, "P", pressure_Pa, coolprop_name)
        k = _CP.PropsSI("L", "T", T_K, "P", pressure_Pa, coolprop_name)
        Pr = _CP.PropsSI("Prandtl", "T", T_K, "P", pressure_Pa, coolprop_name)
    except Exception as exc:
        raise CalculationError(
            _STEP_ID,
            f"CoolProp lookup failed for '{coolprop_name}' at "
            f"T={temperature_C}°C, P={pressure_Pa} Pa",
            cause=exc,
        ) from exc

    return FluidProperties(
        density_kg_m3=rho,
        viscosity_Pa_s=mu,
        cp_J_kgK=cp,
        k_W_mK=k,
        Pr=Pr,
    )


# ── thermo (Caleb Bell) retrieval ─────────────────────────────────────────────


def _get_props_thermo(
    fluid_name: str,
    temperature_C: float,
    pressure_Pa: float,
) -> FluidProperties:
    """Retrieve properties via the *thermo* library (Chemical class).

    Covers thousands of compounds by name or CAS number.  Returns all
    five FluidProperties fields; raises ``CalculationError`` if any
    property is ``None`` (incomplete database coverage).
    """
    if _Chemical is None:
        raise CalculationError(
            _STEP_ID,
            "thermo library not installed — cannot compute fluid properties",
        )

    T_K = temperature_C + 273.15

    try:
        c = _Chemical(fluid_name, T=T_K, P=pressure_Pa)
    except Exception as exc:
        raise CalculationError(
            _STEP_ID,
            f"thermo lookup failed for '{fluid_name}' at "
            f"T={temperature_C}°C, P={pressure_Pa} Pa",
            cause=exc,
        ) from exc

    # thermo returns None for properties it cannot compute
    cp = c.Cp     # J/(kg·K)
    rho = c.rho   # kg/m³
    mu = c.mu     # Pa·s
    k = c.k       # W/(m·K)

    if any(v is None for v in (cp, rho, mu, k)):
        missing = [n for n, v in
                   (("Cp", cp), ("rho", rho), ("mu", mu), ("k", k))
                   if v is None]
        raise CalculationError(
            _STEP_ID,
            f"thermo returned incomplete properties for '{fluid_name}': "
            f"missing {', '.join(missing)}",
        )

    Pr = mu * cp / k  # compute Prandtl from the three transport props

    return FluidProperties(
        density_kg_m3=rho,
        viscosity_Pa_s=mu,
        cp_J_kgK=cp,
        k_W_mK=k,
        Pr=Pr,
    )


# ── public API ────────────────────────────────────────────────────────────────

_DEFAULT_PRESSURE_PA = 101_325.0  # 1 atm


def get_fluid_properties(
    fluid_name: str,
    temperature_C: float,
    pressure_Pa: Optional[float] = None,
) -> FluidProperties:
    """Return validated thermophysical properties for *fluid_name*.

    Resolution order:
    1. iapws      — water / steam
    2. CoolProp   — pure compounds (fast, 124 fluids)
    3. thermo     — broad chemical database (thousands of compounds)
    4. Petroleum  — crude oils & fractions (correlation-based, T-dependent)
    5. Specialty  — glycols, thermal oil, vegetable oil, molten salt

    Raises ``CalculationError`` if the fluid cannot be resolved.
    """
    if pressure_Pa is None:
        pressure_Pa = _DEFAULT_PRESSURE_PA

    normalised = fluid_name.strip().lower()

    # 1. Water / steam → iapws
    if _is_water_or_steam(normalised):
        try:
            return _get_props_iapws(temperature_C, pressure_Pa)
        except CalculationError:
            # iapws unavailable — try CoolProp Water as backup
            if _CP is not None:
                try:
                    return _get_props_coolprop("Water", temperature_C, pressure_Pa)
                except CalculationError:
                    pass
            # Fall through to thermo / other backends

    # 2. CoolProp — mapped pure fluids
    cp_name = _COOLPROP_MAP.get(normalised)
    if cp_name is not None and _CP is not None:
        return _get_props_coolprop(cp_name, temperature_C, pressure_Pa)

    # 3. thermo — broad chemical database
    if _Chemical is not None:
        try:
            return _get_props_thermo(normalised, temperature_C, pressure_Pa)
        except CalculationError:
            pass  # fall through to petroleum / specialty

    # 4. Petroleum correlations — crude oils & fractions
    char = resolve_petroleum_name(normalised)
    if char is not None:
        return get_petroleum_properties(char, temperature_C)

    # 5. Specialty fluids — T-dependent fits
    specialty_fn = _SPECIALTY_FLUIDS.get(normalised)
    if specialty_fn is not None:
        return specialty_fn(temperature_C)

    # Nothing matched
    raise CalculationError(
        _STEP_ID,
        f"Unknown fluid '{fluid_name}' — not found in any property source "
        f"(iapws, CoolProp, thermo, petroleum database, or specialty fluids). "
        f"Provide fluid properties directly via DesignState or specify a "
        f"recognised fluid name.",
    )


def get_cp(
    fluid_name: str,
    temperature_C: float,
    pressure_Pa: Optional[float] = None,
) -> float:
    """Convenience wrapper: return only Cp (J/kg·K)."""
    props = get_fluid_properties(fluid_name, temperature_C, pressure_Pa)
    assert props.cp_J_kgK is not None  # guaranteed by all backends
    return props.cp_J_kgK
