"""Volumetric → mass flow conversion (P2-20).

The validator and design routers accept either ``m_dot_*_kg_s`` or a
``{value, unit}`` flow object per side. This module owns:

* The closed-set unit conversion table (``SUPPORTED_VOLUMETRIC_UNITS``).
* The async resolver (:func:`resolve_mass_flow`) that consults the
  property backend for inlet density and returns a mass flow plus an
  audit record.

Conventions
-----------
* US gallons-per-minute (1 gal = 3.785 411 784 L).
* US oil barrel (1 bbl = 0.158 987 294 928 m³).
* ``sm3_h`` reference: 15 °C, 101 325 Pa.
* ``Nm3_h`` reference: 0 °C, 101 325 Pa.

Gas streams require an explicit operating pressure — silent 1 atm
fallback is unsafe (P1-6). When ``P_in_Pa`` is missing for a gas-basis
unit, the resolver raises a :class:`CalculationError` rather than
guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from hx_engine.app.adapters.thermo_adapter import get_fluid_properties
from hx_engine.app.core.exceptions import CalculationError

# ---------------------------------------------------------------------------
# Conversion table — value × factor → m³/s (or kg/s for the mass alias).
# ---------------------------------------------------------------------------

# (basis, factor_to_SI). Basis tags drive the resolver's branching.
_LIQUID_VOL = "liquid_vol"
_GAS_STD_15C = "gas_std_15C_1atm"
_GAS_STD_0C = "gas_std_0C_1atm"
_MASS = "mass"

SUPPORTED_VOLUMETRIC_UNITS: dict[str, tuple[str, float]] = {
    "kg_s":  (_MASS,        1.0),
    "m3_s":  (_LIQUID_VOL,  1.0),
    "m3_h":  (_LIQUID_VOL,  1.0 / 3600.0),
    "gpm":   (_LIQUID_VOL,  3.785_411_784e-3 / 60.0),   # US gpm
    "bbl_d": (_LIQUID_VOL,  0.158_987_294_928 / 86400.0),  # US oil bbl
    "sm3_h": (_GAS_STD_15C, 1.0 / 3600.0),
    "Nm3_h": (_GAS_STD_0C,  1.0 / 3600.0),
}

# Gas reference conditions (per ISO 13443 / DIN 1343 conventions).
_P_REF_PA = 101_325.0
_T_STD_15C_K = 288.15
_T_STD_0C_K = 273.15

_STEP_ID = 2  # validator runs as a Step-2 precondition


@dataclass(frozen=True)
class FlowResolution:
    """Result of :func:`resolve_mass_flow` — mass flow + full audit trail."""

    m_dot_kg_s: float
    basis: str               # "mass" | "liquid_vol" | "gas_std_15C_1atm" | "gas_std_0C_1atm"
    input_value: float
    input_unit: str
    density_kg_m3: Optional[float]    # None for the mass passthrough
    density_source: Optional[str]     # property backend tag, or "ideal_gas", or None


def _is_gas_basis(basis: str) -> bool:
    return basis in (_GAS_STD_15C, _GAS_STD_0C)


def _gas_std_temperature_K(basis: str) -> float:
    return _T_STD_15C_K if basis == _GAS_STD_15C else _T_STD_0C_K


async def resolve_mass_flow(
    value: float,
    unit: str,
    fluid_name: str,
    T_in_C: Optional[float],
    P_in_Pa: Optional[float],
) -> FlowResolution:
    """Convert a ``(value, unit)`` flow input into a mass flow (kg/s).

    Branches:

    * ``mass``        → passthrough (``m_dot = value``).
    * ``liquid_vol``  → ``m_dot = ρ(T_in, P_in) × Q``  where ρ comes from
      :func:`get_fluid_properties` at inlet conditions.
    * ``gas_std_*``   → ``ρ_actual = ρ_std × (P/P_std) × (T_std/T)``,
      ``m_dot = ρ_actual × Q_std``. Requires ``P_in_Pa`` (P1-6) and
      ``T_in_C`` (otherwise the conversion is undefined).

    Raises :class:`CalculationError` with ``step_id=2`` for unknown
    units, missing density, missing gas pressure, or missing inlet
    temperature on a gas basis.
    """
    if unit not in SUPPORTED_VOLUMETRIC_UNITS:
        supported = ", ".join(sorted(SUPPORTED_VOLUMETRIC_UNITS))
        raise CalculationError(
            _STEP_ID,
            f"Unknown flow unit '{unit}'. Supported units: {supported}.",
        )

    basis, factor = SUPPORTED_VOLUMETRIC_UNITS[unit]

    if value is None or value <= 0:
        raise CalculationError(
            _STEP_ID,
            f"Flow value must be positive, got {value} {unit}.",
        )

    if basis == _MASS:
        return FlowResolution(
            m_dot_kg_s=float(value) * factor,
            basis=basis,
            input_value=float(value),
            input_unit=unit,
            density_kg_m3=None,
            density_source=None,
        )

    if basis == _LIQUID_VOL:
        if T_in_C is None:
            raise CalculationError(
                _STEP_ID,
                f"Liquid volumetric flow ({unit}) requires inlet temperature "
                f"to look up density for '{fluid_name}'.",
            )
        props = await get_fluid_properties(fluid_name, T_in_C, P_in_Pa)
        rho = props.density_kg_m3
        if rho is None or rho <= 0:
            raise CalculationError(
                _STEP_ID,
                f"Cannot convert {unit} → kg/s: property backend did not "
                f"return a positive density for '{fluid_name}' at {T_in_C}°C.",
            )
        q_si = float(value) * factor  # m³/s
        return FlowResolution(
            m_dot_kg_s=rho * q_si,
            basis=basis,
            input_value=float(value),
            input_unit=unit,
            density_kg_m3=rho,
            density_source=props.property_source,
        )

    # gas standard-volumetric branch
    if P_in_Pa is None:
        raise CalculationError(
            _STEP_ID,
            f"Gas volumetric flow ({unit}) requires an explicit operating "
            "pressure — silent 1 atm fallback is unsafe (would mis-size by "
            "the actual P/1 atm ratio).",
        )
    if T_in_C is None:
        raise CalculationError(
            _STEP_ID,
            f"Gas volumetric flow ({unit}) requires inlet temperature to "
            "convert standard volume to actual volume.",
        )

    # Look up standard-condition density from the property backend so the
    # audit trail reflects real-gas behaviour where applicable (Z ≠ 1 at
    # high pressure). Mass flow conserves across reference frames:
    #   m_dot = ρ_std × Q_std = ρ_actual × Q_actual
    T_std_K = _gas_std_temperature_K(basis)
    rho_std_props = await get_fluid_properties(
        fluid_name, T_std_K - 273.15, _P_REF_PA,
    )
    rho_std = rho_std_props.density_kg_m3
    if rho_std is None or rho_std <= 0:
        raise CalculationError(
            _STEP_ID,
            f"Cannot convert {unit} → kg/s: property backend did not return "
            f"a standard-condition density for '{fluid_name}'.",
        )

    # ρ_actual / ρ_std = (P_actual/P_std) × (T_std/T_actual) — for audit only.
    T_actual_K = T_in_C + 273.15
    rho_actual = rho_std * (P_in_Pa / _P_REF_PA) * (T_std_K / T_actual_K)

    q_std_si = float(value) * factor  # std m³/s
    m_dot = rho_std * q_std_si
    return FlowResolution(
        m_dot_kg_s=m_dot,
        basis=basis,
        input_value=float(value),
        input_unit=unit,
        density_kg_m3=rho_actual,
        density_source=rho_std_props.property_source,
    )


# ---------------------------------------------------------------------------
# Step 3 density-drift threshold (P2-20 Phase 4)
# ---------------------------------------------------------------------------

# When the validator computes m_dot from a volumetric flow at inlet
# conditions, but Step 3 later refines density using the bulk-mean
# temperature, a > 2 % discrepancy is worth surfacing — it usually means
# the operating range spans a regime where density variation matters
# (heavy crudes, near-critical fluids).
DENSITY_DRIFT_WARN_PCT = 2.0


# ---------------------------------------------------------------------------
# Router-side helper: apply DesignRequest.{hot,cold}_flow before validation.
# ---------------------------------------------------------------------------

async def apply_flow_inputs(
    validation_dict: dict,
    hot_flow: Optional[dict],
    cold_flow: Optional[dict],
    hot_fluid_name: Optional[str],
    cold_fluid_name: Optional[str],
) -> tuple[dict, Optional[FlowResolution], Optional[FlowResolution]]:
    """Resolve volumetric flow inputs to mass flow (kg/s).

    Mutates a copy of ``validation_dict`` so:

    * ``hot_flow``/``cold_flow`` keys are removed (kept out of the canonical
      token payload).
    * ``m_dot_hot_kg_s``/``m_dot_cold_kg_s`` are populated from the
      resolver. An explicit scalar already present is **overridden** by the
      resolved value when a flow object was supplied.

    Returns ``(updated_dict, hot_resolution, cold_resolution)``. The
    resolutions are ``None`` when no flow object was provided for that
    side; callers attach them to ``DesignState`` for the audit trail.
    """
    out = dict(validation_dict)
    out.pop("hot_flow", None)
    out.pop("cold_flow", None)

    hot_res = await _resolve_side(
        hot_flow, hot_fluid_name,
        T_in_C=out.get("T_hot_in_C"),
        P_in_Pa=out.get("P_hot_Pa"),
    )
    if hot_res is not None:
        out["m_dot_hot_kg_s"] = hot_res.m_dot_kg_s

    cold_res = await _resolve_side(
        cold_flow, cold_fluid_name,
        T_in_C=out.get("T_cold_in_C"),
        P_in_Pa=out.get("P_cold_Pa"),
    )
    if cold_res is not None:
        out["m_dot_cold_kg_s"] = cold_res.m_dot_kg_s

    return out, hot_res, cold_res


async def _resolve_side(
    flow: Optional[dict],
    fluid_name: Optional[str],
    T_in_C: Optional[float],
    P_in_Pa: Optional[float],
) -> Optional[FlowResolution]:
    if flow is None:
        return None
    if not fluid_name:
        raise CalculationError(
            _STEP_ID,
            f"Cannot resolve {flow.get('unit')} flow: fluid name is missing.",
        )
    return await resolve_mass_flow(
        value=flow["value"],
        unit=flow["unit"],
        fluid_name=fluid_name,
        T_in_C=T_in_C,
        P_in_Pa=P_in_Pa,
    )
