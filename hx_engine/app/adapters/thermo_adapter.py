"""Thermophysical property retrieval for heat exchanger fluids.

Priority chain
--------------
1. iapws         — water / steam  (IAPWS-IF97, T/P-dependent)
2. CoolProp      — pure compounds (T/P-dependent, 124 fluids)
3. Petroleum     — crude oils & fractions via Lee–Kesler / Beggs–Robinson /
                   Cragoe correlations parameterised by API gravity (T-dependent)
4. Specialty     — glycols, thermal oil, vegetable oil, molten salt
                   (T-dependent engineering fits)
5. thermo        — broad chemical database (Caleb Bell, thousands of compounds)

Petroleum and specialty backends are checked BEFORE thermo because petroleum
fluids are multi-component mixtures that thermo's Chemical class (pure-compound)
cannot model correctly — it may silently return wrong properties.

Public API
----------
get_fluid_properties(fluid_name, temperature_C, pressure_Pa, phase) → FluidProperties
get_saturation_props(fluid_name, pressure_Pa)                       → dict
get_cp(fluid_name, temperature_C, pressure_Pa)                     → float  (J/kg·K)
"""

from __future__ import annotations

import logging
import math
from typing import Callable, Optional

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import FluidProperties
from hx_engine.app.adapters.petroleum_correlations import (
    get_petroleum_properties,
    pour_point_petroleum_K,
    resolve_petroleum_name,
)

_logger = logging.getLogger(__name__)

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

# ── fluid name normalisation aliases ──────────────────────────────────────────
# Maps common engineering names (as produced by NL parsing / AI) to names
# that the lookup chain already recognises.  Applied once at the top of
# get_fluid_properties() before any backend is tried.

# ── phase suffixes to strip ────────────────────────────────────────────────
# Users / LLMs often append phase descriptors to fluid names
# (e.g. "ethylene vapour").  We strip these before lookup.

_PHASE_SUFFIXES: tuple[str, ...] = (
    " vapour", " vapor", " liquid", " gas",
    " vapours", " vapors", " gases",
)


def _strip_phase_suffix(name: str) -> str:
    """Remove trailing phase descriptors from a fluid name."""
    for suffix in _PHASE_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)].strip()
    return name


_FLUID_ALIAS_MAP: dict[str, str] = {
    # Petroleum compound names → recognised fraction names
    "diesel fuel":      "diesel",
    "diesel oil":       "diesel",
    "lube oil":         "lubricating oil",
    "lube":             "lubricating oil",
    "light oil":        "gas oil",
    "heating oil":      "fuel oil",
    "bunker fuel":      "heavy fuel oil",
    "bunker oil":       "heavy fuel oil",
    "bunker c":         "heavy fuel oil",
    "residual fuel":    "heavy fuel oil",
    "hfo":              "heavy fuel oil",
}

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
        property_source="specialty", property_confidence=0.80,
    )


def _vegetable_oil_props(T: float) -> FluidProperties:
    """Generic vegetable oil."""
    rho = 930.0 - 0.60 * T
    cp = 1900.0 + 3.0 * T
    mu = 0.118 * math.exp(-0.027 * T)
    k = 0.17 - 1.5e-4 * T
    return FluidProperties(
        density_kg_m3=rho, viscosity_Pa_s=mu, cp_J_kgK=cp,
        k_W_mK=k, Pr=mu * cp / k,
        property_source="specialty", property_confidence=0.75,
    )


def _ethylene_glycol_props(T: float) -> FluidProperties:
    """Pure ethylene glycol (not mixtures)."""
    rho = 1130.0 - 0.65 * T
    cp = 2350.0 + 2.0 * T
    mu = 0.032 * math.exp(-0.028 * T)
    k = 0.256 - 1.5e-4 * T
    return FluidProperties(
        density_kg_m3=rho, viscosity_Pa_s=mu, cp_J_kgK=cp,
        k_W_mK=k, Pr=mu * cp / k,
        property_source="specialty", property_confidence=0.80,
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
        property_source="specialty", property_confidence=0.80,
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
        property_source="specialty", property_confidence=0.85,
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
    """Retrieve properties via IAPWS-IF97 (water / steam).

    Includes phase detection and saturation data.
    """
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

    # Determine phase from IAPWS region / quality
    phase = "liquid"
    quality = None
    T_sat_C = None
    P_sat_Pa = None
    latent_heat = None
    enthalpy = None

    try:
        enthalpy = w.h * 1000.0  # kJ/kg → J/kg
    except Exception:
        pass

    try:
        # Get saturation temperature at this pressure
        sat = _iapws.IAPWS97(P=P_MPa, x=0)  # saturated liquid
        T_sat_C = sat.T - 273.15
        P_sat_Pa = pressure_Pa

        # Get latent heat
        sat_v = _iapws.IAPWS97(P=P_MPa, x=1)  # saturated vapor
        latent_heat = (sat_v.h - sat.h) * 1000.0  # kJ/kg → J/kg

        # Phase detection
        if hasattr(w, 'x') and w.x is not None and 0.0 <= w.x <= 1.0:
            if w.x == 0.0:
                phase = "liquid"
            elif w.x == 1.0:
                phase = "vapor"
            else:
                phase = "two_phase"
                quality = w.x
        elif temperature_C > T_sat_C + 0.5:
            phase = "vapor"
        else:
            phase = "liquid"
    except Exception:
        # If saturation lookup fails, infer from density
        if w.rho < 100.0:
            phase = "vapor"

    return FluidProperties(
        density_kg_m3=w.rho,
        viscosity_Pa_s=w.mu,
        cp_J_kgK=w.cp * 1000.0,
        k_W_mK=w.k,
        Pr=w.Prandt,
        phase=phase,
        quality=quality,
        enthalpy_J_kg=enthalpy,
        latent_heat_J_kg=latent_heat,
        T_sat_C=T_sat_C,
        P_sat_Pa=P_sat_Pa,
        property_source="iapws",
        property_confidence=1.0,
    )


# ── CoolProp retrieval ───────────────────────────────────────────────────────


def _get_props_coolprop(
    coolprop_name: str,
    temperature_C: float,
    pressure_Pa: float,
) -> FluidProperties:
    """Retrieve properties via CoolProp, including phase detection."""
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

    # Phase detection
    phase = "liquid"
    quality = None
    enthalpy = None
    latent_heat = None
    T_sat_C = None
    P_sat_Pa = None

    try:
        enthalpy = _CP.PropsSI("H", "T", T_K, "P", pressure_Pa, coolprop_name)
    except Exception:
        pass

    try:
        T_sat_K = _CP.PropsSI("T", "P", pressure_Pa, "Q", 0, coolprop_name)
        T_sat_C = T_sat_K - 273.15
        P_sat_Pa = pressure_Pa

        h_f = _CP.PropsSI("H", "P", pressure_Pa, "Q", 0, coolprop_name)
        h_g = _CP.PropsSI("H", "P", pressure_Pa, "Q", 1, coolprop_name)
        latent_heat = h_g - h_f

        # Determine phase
        if temperature_C > T_sat_C + 0.5:
            phase = "vapor"
        elif temperature_C < T_sat_C - 0.5:
            phase = "liquid"
        else:
            # Near saturation — check quality
            try:
                q = _CP.PropsSI("Q", "T", T_K, "P", pressure_Pa, coolprop_name)
                if 0.0 <= q <= 1.0:
                    phase = "two_phase"
                    quality = q
                elif q < 0:
                    phase = "liquid"
                else:
                    phase = "vapor"
            except Exception:
                phase = "liquid" if rho > 100 else "vapor"
    except Exception:
        # Fluid may not have a saturation curve (e.g. supercritical, or Air)
        # Infer from density
        phase = "vapor" if rho < 50 else "liquid"

    return FluidProperties(
        density_kg_m3=rho,
        viscosity_Pa_s=mu,
        cp_J_kgK=cp,
        k_W_mK=k,
        Pr=Pr,
        phase=phase,
        quality=quality,
        enthalpy_J_kg=enthalpy,
        latent_heat_J_kg=latent_heat,
        T_sat_C=T_sat_C,
        P_sat_Pa=P_sat_Pa,
        property_source="coolprop",
        property_confidence=0.95,
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

    # Phase detection via thermo library
    phase = "liquid"
    try:
        if hasattr(c, 'phase') and c.phase:
            ph = c.phase.lower()
            if 'gas' in ph or 'vapor' in ph:
                phase = "vapor"
            elif 'two' in ph or 'mix' in ph:
                phase = "two_phase"
        elif rho is not None and rho < 50:
            phase = "vapor"
    except Exception:
        pass

    T_sat_C = None
    latent_heat = None
    enthalpy = None
    try:
        if hasattr(c, 'Tb') and c.Tb is not None:
            T_sat_C = c.Tb - 273.15  # normal boiling point as approximation
        if hasattr(c, 'Hvap') and c.Hvap is not None:
            latent_heat = c.Hvap  # J/kg or J/mol — thermo uses J/mol
        if hasattr(c, 'H') and c.H is not None:
            enthalpy = c.H
    except Exception:
        pass

    return FluidProperties(
        density_kg_m3=rho,
        viscosity_Pa_s=mu,
        cp_J_kgK=cp,
        k_W_mK=k,
        Pr=Pr,
        phase=phase,
        enthalpy_J_kg=enthalpy,
        latent_heat_J_kg=latent_heat,
        T_sat_C=T_sat_C,
        property_source="thermo",
        property_confidence=0.90,
    )


# ── public API ────────────────────────────────────────────────────────────────

_DEFAULT_PRESSURE_PA = 101_325.0  # 1 atm


def _try_deterministic_backends(
    normalised: str,
    temperature_C: float,
    pressure_Pa: float,
) -> FluidProperties | None:
    """Try all deterministic backends (1-5).  Returns None if none match."""

    # 1. Water / steam → iapws
    if _is_water_or_steam(normalised):
        try:
            return _get_props_iapws(temperature_C, pressure_Pa)
        except CalculationError:
            if _CP is not None:
                try:
                    return _get_props_coolprop("Water", temperature_C, pressure_Pa)
                except CalculationError:
                    pass
            if _Chemical is not None:
                try:
                    return _get_props_thermo("water", temperature_C, pressure_Pa)
                except CalculationError:
                    pass

    # 2. CoolProp — mapped pure fluids
    cp_name = _COOLPROP_MAP.get(normalised)
    if cp_name is not None and _CP is not None:
        return _get_props_coolprop(cp_name, temperature_C, pressure_Pa)

    # 3. Petroleum correlations
    resolved = resolve_petroleum_name(normalised)
    if resolved is not None:
        char, petro_source = resolved
        return get_petroleum_properties(char, temperature_C, source=petro_source)

    # 4. Specialty fluids
    specialty_fn = _SPECIALTY_FLUIDS.get(normalised)
    if specialty_fn is not None:
        return specialty_fn(temperature_C)

    # 5. thermo — broad chemical database (pure compounds only)
    if _Chemical is not None:
        try:
            return _get_props_thermo(normalised, temperature_C, pressure_Pa)
        except CalculationError:
            pass

    return None


async def get_fluid_properties(
    fluid_name: str,
    temperature_C: float,
    pressure_Pa: Optional[float] = None,
) -> FluidProperties:
    """Return validated thermophysical properties for *fluid_name*.

    Resolution order:
    1. iapws      — water / steam
    2. CoolProp   — pure compounds (fast, 124 fluids)
    3. Petroleum  — crude oils & fractions (correlation-based, T-dependent)
    4. Specialty  — glycols, thermal oil, vegetable oil, molten salt
    5. thermo     — broad chemical database (thousands of compounds)
    6. MongoDB    — cached AI-estimated properties
    7. AI (LLM)   — ask Claude for properties, cache if confidence ≥ 0.6

    Phase suffixes ("vapour", "liquid", "gas") are stripped before lookup.

    Raises ``CalculationError`` if the fluid cannot be resolved.
    """
    from hx_engine.app.core.fluid_property_store import (
        find_cached_properties,
        ask_ai_for_properties,
    )

    if pressure_Pa is None:
        pressure_Pa = _DEFAULT_PRESSURE_PA

    normalised = fluid_name.strip().lower()

    # Apply alias normalisation before any backend lookup
    normalised = _FLUID_ALIAS_MAP.get(normalised, normalised)

    # Strip phase suffixes ("ethylene vapour" → "ethylene")
    normalised = _strip_phase_suffix(normalised)

    # --- Deterministic backends 1-5 ---
    result = _try_deterministic_backends(normalised, temperature_C, pressure_Pa)
    if result is not None:
        return result

    # --- 6. MongoDB cache of previously AI-estimated properties ---
    cached = await find_cached_properties(normalised, temperature_C)
    if cached is not None:
        import logging
        logging.getLogger(__name__).info(
            "Using cached AI properties for '%s' at %.1f°C",
            normalised, temperature_C,
        )
        return cached

    # --- 7. Ask AI for properties ---
    ai_result = await ask_ai_for_properties(
        normalised, temperature_C, pressure_Pa,
    )
    if ai_result is not None:
        import logging
        logging.getLogger(__name__).info(
            "AI provided properties for '%s' at %.1f°C "
            "(confidence=%.2f, source=%s)",
            normalised, temperature_C,
            ai_result.property_confidence or 0,
            ai_result.property_source,
        )
        return ai_result

    # Nothing matched — not even AI could help
    raise CalculationError(
        _STEP_ID,
        f"Unknown fluid '{fluid_name}' — not found in any property source "
        f"(iapws, CoolProp, petroleum database, specialty fluids, thermo, "
        f"MongoDB cache, or AI estimation). "
        f"Provide fluid properties directly via DesignState or specify a "
        f"recognised fluid name.",
    )


async def get_cp(
    fluid_name: str,
    temperature_C: float,
    pressure_Pa: Optional[float] = None,
) -> float:
    """Convenience wrapper: return only Cp (J/kg·K)."""
    props = await get_fluid_properties(fluid_name, temperature_C, pressure_Pa)
    assert props.cp_J_kgK is not None  # guaranteed by all backends
    return props.cp_J_kgK


# ── sync wrappers (for tests and non-async contexts) ─────────────────────────

def get_fluid_properties_sync(
    fluid_name: str,
    temperature_C: float,
    pressure_Pa: Optional[float] = None,
) -> FluidProperties:
    """Synchronous version: tries deterministic backends only (1-5).

    Does NOT check MongoDB cache or AI fallback.  Use the async version
    ``get_fluid_properties()`` in production code for the full 7-tier chain.
    """
    if pressure_Pa is None:
        pressure_Pa = _DEFAULT_PRESSURE_PA

    normalised = fluid_name.strip().lower()
    normalised = _FLUID_ALIAS_MAP.get(normalised, normalised)
    normalised = _strip_phase_suffix(normalised)

    result = _try_deterministic_backends(normalised, temperature_C, pressure_Pa)
    if result is not None:
        return result

    raise CalculationError(
        _STEP_ID,
        f"Unknown fluid '{fluid_name}' — not found in any property source "
        f"(iapws, CoolProp, petroleum database, specialty fluids, or thermo). "
        f"Provide fluid properties directly via DesignState or specify a "
        f"recognised fluid name.",
    )


def get_cp_sync(
    fluid_name: str,
    temperature_C: float,
    pressure_Pa: Optional[float] = None,
) -> float:
    """Synchronous convenience wrapper: return only Cp (J/kg·K)."""
    props = get_fluid_properties_sync(fluid_name, temperature_C, pressure_Pa)
    assert props.cp_J_kgK is not None
    return props.cp_J_kgK


# ── saturation & two-phase helpers ───────────────────────────────────────────

def get_saturation_props(
    fluid_name: str,
    pressure_Pa: float,
) -> dict:
    """Return saturation properties at the given pressure.

    Returns dict with:
      T_sat_C, h_f (J/kg), h_g (J/kg), h_fg (J/kg),
      rho_f (kg/m³), rho_g (kg/m³),
      mu_f (Pa·s), mu_g (Pa·s),
      k_f (W/m·K), k_g (W/m·K),
      cp_f (J/kg·K), cp_g (J/kg·K),
      Pr_f, Pr_g, sigma (N/m surface tension)

    Raises CalculationError if saturation data cannot be obtained.
    """
    normalised = fluid_name.strip().lower()
    normalised = _FLUID_ALIAS_MAP.get(normalised, normalised)
    normalised = _strip_phase_suffix(normalised)

    # Try IAPWS for water/steam
    if _is_water_or_steam(normalised) and _iapws is not None:
        return _get_saturation_iapws(pressure_Pa)

    # Try CoolProp
    cp_name = _COOLPROP_MAP.get(normalised)
    if cp_name is None and _is_water_or_steam(normalised):
        cp_name = "Water"
    if cp_name is not None and _CP is not None:
        return _get_saturation_coolprop(cp_name, pressure_Pa)

    raise CalculationError(
        _STEP_ID,
        f"Cannot obtain saturation properties for '{fluid_name}' — "
        f"requires IAPWS (water) or CoolProp (pure compounds).",
    )


def _get_saturation_iapws(pressure_Pa: float) -> dict:
    """Saturation properties via IAPWS-IF97."""
    P_MPa = pressure_Pa / 1e6

    try:
        sat_l = _iapws.IAPWS97(P=P_MPa, x=0)
        sat_v = _iapws.IAPWS97(P=P_MPa, x=1)
    except Exception as exc:
        raise CalculationError(
            _STEP_ID,
            f"IAPWS saturation lookup failed at P={pressure_Pa} Pa",
            cause=exc,
        ) from exc

    T_sat_C = sat_l.T - 273.15
    h_f = sat_l.h * 1000.0  # kJ/kg → J/kg
    h_g = sat_v.h * 1000.0

    sigma = None
    try:
        sigma = sat_l.sigma
    except Exception:
        pass

    return {
        "T_sat_C": T_sat_C,
        "h_f": h_f,
        "h_g": h_g,
        "h_fg": h_g - h_f,
        "rho_f": sat_l.rho,
        "rho_g": sat_v.rho,
        "mu_f": sat_l.mu,
        "mu_g": sat_v.mu,
        "k_f": sat_l.k,
        "k_g": sat_v.k,
        "cp_f": sat_l.cp * 1000.0,
        "cp_g": sat_v.cp * 1000.0,
        "Pr_f": sat_l.Prandt,
        "Pr_g": sat_v.Prandt,
        "sigma": sigma,
    }


def _get_saturation_coolprop(coolprop_name: str, pressure_Pa: float) -> dict:
    """Saturation properties via CoolProp."""
    try:
        T_sat_K = _CP.PropsSI("T", "P", pressure_Pa, "Q", 0, coolprop_name)
        h_f = _CP.PropsSI("H", "P", pressure_Pa, "Q", 0, coolprop_name)
        h_g = _CP.PropsSI("H", "P", pressure_Pa, "Q", 1, coolprop_name)
        rho_f = _CP.PropsSI("D", "P", pressure_Pa, "Q", 0, coolprop_name)
        rho_g = _CP.PropsSI("D", "P", pressure_Pa, "Q", 1, coolprop_name)
        mu_f = _CP.PropsSI("V", "P", pressure_Pa, "Q", 0, coolprop_name)
        mu_g = _CP.PropsSI("V", "P", pressure_Pa, "Q", 1, coolprop_name)
        k_f = _CP.PropsSI("L", "P", pressure_Pa, "Q", 0, coolprop_name)
        k_g = _CP.PropsSI("L", "P", pressure_Pa, "Q", 1, coolprop_name)
        cp_f = _CP.PropsSI("C", "P", pressure_Pa, "Q", 0, coolprop_name)
        cp_g = _CP.PropsSI("C", "P", pressure_Pa, "Q", 1, coolprop_name)
        Pr_f = _CP.PropsSI("Prandtl", "P", pressure_Pa, "Q", 0, coolprop_name)
        Pr_g = _CP.PropsSI("Prandtl", "P", pressure_Pa, "Q", 1, coolprop_name)
    except Exception as exc:
        raise CalculationError(
            _STEP_ID,
            f"CoolProp saturation lookup failed for '{coolprop_name}' "
            f"at P={pressure_Pa} Pa",
            cause=exc,
        ) from exc

    sigma = None
    try:
        sigma = _CP.PropsSI("I", "P", pressure_Pa, "Q", 0, coolprop_name)
    except Exception:
        pass

    return {
        "T_sat_C": T_sat_K - 273.15,
        "h_f": h_f,
        "h_g": h_g,
        "h_fg": h_g - h_f,
        "rho_f": rho_f,
        "rho_g": rho_g,
        "mu_f": mu_f,
        "mu_g": mu_g,
        "k_f": k_f,
        "k_g": k_g,
        "cp_f": cp_f,
        "cp_g": cp_g,
        "Pr_f": Pr_f,
        "Pr_g": Pr_g,
        "sigma": sigma,
    }


def get_two_phase_props(
    fluid_name: str,
    quality: float,
    pressure_Pa: float,
) -> FluidProperties:
    """Return mixture properties at a given quality (vapor fraction).

    Uses quality-weighted averaging for transport properties:
      ρ = 1 / (x/ρ_g + (1-x)/ρ_f)   (void-fraction weighted)
      μ = μ_f × (1-x) + μ_g × x       (linear mixing)
      k = k_f × (1-x) + k_g × x
      cp = cp_f × (1-x) + cp_g × x
    """
    sat = get_saturation_props(fluid_name, pressure_Pa)
    x = max(0.0, min(1.0, quality))

    rho_f = sat["rho_f"]
    rho_g = sat["rho_g"]
    # Homogeneous void fraction model
    rho = 1.0 / (x / rho_g + (1.0 - x) / rho_f) if (rho_f > 0 and rho_g > 0) else rho_f

    mu = sat["mu_f"] * (1.0 - x) + sat["mu_g"] * x
    k = sat["k_f"] * (1.0 - x) + sat["k_g"] * x
    cp = sat["cp_f"] * (1.0 - x) + sat["cp_g"] * x
    Pr = mu * cp / k if k > 0 else None

    return FluidProperties(
        density_kg_m3=rho,
        viscosity_Pa_s=mu,
        cp_J_kgK=cp,
        k_W_mK=k,
        Pr=Pr,
        phase="two_phase",
        quality=x,
        latent_heat_J_kg=sat["h_fg"],
        T_sat_C=sat["T_sat_C"],
        P_sat_Pa=pressure_Pa,
        property_source="coolprop" if _CP else "iapws",
        property_confidence=0.90,
    )


# ── freezing / pour point resolution ──────────────────────────────────────────

# Water freezes at the IAPWS-IF97 triple point.
_WATER_FREEZE_K = 273.16


def get_freezing_or_pour_point(
    fluid_name: str,
    pressure_Pa: Optional[float] = None,  # noqa: ARG001 — reserved for future use
) -> tuple[Optional[float], str]:
    """Return ``(T_freeze_K, source)`` for a fluid, or ``(None, "unresolved")``.

    Resolution order mirrors :func:`get_fluid_properties`:

    1. Water / steam aliases       → triple point (273.16 K), source ``"iapws"``
    2. CoolProp pure compounds     → ``Tmin`` (often the triple point),
       source ``"coolprop"``
    3. Petroleum cuts              → API-band pour-point estimate via
       :func:`pour_point_petroleum_K`, source ``"petroleum-pour-point"``
    4. Specialty fluids            → ``None`` (out-of-scope), source
       ``"unresolved"``
    5. ``thermo`` Chemical         → ``Tm`` (melting point), source ``"thermo"``

    Returns ``(None, "unresolved")`` when no backend can supply a value.
    Callers (Step 03) emit an INFO/AI-trigger in that case rather than
    silently passing.
    """
    normalised = (fluid_name or "").strip().lower()
    normalised = _FLUID_ALIAS_MAP.get(normalised, normalised)
    normalised = _strip_phase_suffix(normalised)

    if _is_water_or_steam(normalised):
        return _WATER_FREEZE_K, "iapws"

    cp_name = _COOLPROP_MAP.get(normalised)
    if cp_name is not None and _CP is not None:
        try:
            t_min = float(_CP.PropsSI("Tmin", cp_name))
            return t_min, "coolprop"
        except Exception:  # noqa: BLE001 — CoolProp may raise many error types
            pass

    resolved = resolve_petroleum_name(normalised)
    if resolved is not None:
        char, _ = resolved
        return pour_point_petroleum_K(char.api_gravity), "petroleum-pour-point"

    if _Chemical is not None:
        try:
            chem = _Chemical(normalised)
            t_m = getattr(chem, "Tm", None)
            if t_m is not None:
                return float(t_m), "thermo"
        except Exception:  # noqa: BLE001 — thermo may fail for many reasons
            pass

    return None, "unresolved"
