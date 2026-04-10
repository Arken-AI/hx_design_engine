"""ASME BPVC Section VIII Div 1 thickness calculations.

Pure calculation functions for:
  - UG-27: Internal pressure — cylindrical shells
  - UG-28: External pressure — cylindrical shells
  - Thermal expansion differential between tubes and shell

References:
  - ASME BPVC Section VIII Div 1, UG-21, UG-27, UG-28
  - ASME BPVC Section II Part D (material data via material_properties, asme_external_pressure)
  - Serth & Lestina (2014), Process Heat Transfer, Chapter 7

Used by:
  - Step 14 (mechanical design check)
"""

from __future__ import annotations

from hx_engine.app.data.material_properties import (
    get_allowable_stress,
    get_elastic_modulus,
    get_thermal_expansion,
)
from hx_engine.app.data.asme_external_pressure import lookup_factor_A, lookup_factor_B


# ---------------------------------------------------------------------------
# Corrosion allowance (Decision D3)
# ---------------------------------------------------------------------------

_CORROSION_ALLOWANCE_M: dict[str, float] = {
    "carbon_steel": 0.003175,    # 1/8" = 3.175 mm
    "sa516_gr70": 0.003175,      # same as CS
    "stainless_304": 0.0015,     # 1.5 mm alloy
    "stainless_316": 0.0015,
    "duplex_2205": 0.0015,
    "copper": 0.0015,
    "admiralty_brass": 0.0015,
    "inconel_600": 0.0,          # exotic — zero
    "monel_400": 0.0,
    "titanium": 0.0,
}


def get_corrosion_allowance(material: str) -> float:
    """Return corrosion allowance in meters for the given material.

    Defaults to 3.175 mm (carbon steel) if material is unknown.
    """
    return _CORROSION_ALLOWANCE_M.get(material, 0.003175)


# ---------------------------------------------------------------------------
# Design pressure (Decision D2, UG-21)
# ---------------------------------------------------------------------------

def design_pressure(P_operating_Pa: float) -> float:
    """Return design pressure per UG-21 convention.

    P_design = max(1.1 × P_operating, P_operating + 175000)

    Raises
    ------
    ValueError
        If P_operating_Pa is negative.
    """
    if P_operating_Pa < 0:
        raise ValueError(
            f"Operating pressure must be non-negative, got {P_operating_Pa}"
        )
    return max(1.1 * P_operating_Pa, P_operating_Pa + 175_000)


# ---------------------------------------------------------------------------
# UG-27: Internal pressure — tubes
# ---------------------------------------------------------------------------

def tube_internal_pressure_thickness(
    P_Pa: float, d_o_m: float, S_Pa: float, E_weld: float = 1.0
) -> float:
    """UG-27: Minimum tube wall thickness for internal pressure.

    t_min = P × d_o / (2 × S × E + P)

    Parameters
    ----------
    P_Pa : float
        Design pressure in Pa (internal).
    d_o_m : float
        Tube outer diameter in meters.
    S_Pa : float
        Maximum allowable stress in Pa.
    E_weld : float
        Weld joint efficiency (1.0 for seamless tubes).

    Returns
    -------
    float
        Minimum required wall thickness in meters.

    Raises
    ------
    ValueError
        If P_Pa is negative.
    """
    if P_Pa < 0:
        raise ValueError(f"Pressure must be non-negative, got {P_Pa}")
    if P_Pa == 0:
        return 0.0
    return P_Pa * d_o_m / (2.0 * S_Pa * E_weld + P_Pa)


# ---------------------------------------------------------------------------
# UG-27: Internal pressure — shell
# ---------------------------------------------------------------------------

def shell_internal_pressure_thickness(
    P_Pa: float,
    R_i_m: float,
    S_Pa: float,
    E_weld: float = 0.85,
    CA_m: float = 0.003175,
) -> float:
    """UG-27: Minimum shell wall thickness for internal pressure.

    t_min = P × R / (S × E - 0.6 × P) + CA

    Parameters
    ----------
    P_Pa : float
        Design pressure in Pa (internal).
    R_i_m : float
        Shell inner radius in meters.
    S_Pa : float
        Maximum allowable stress in Pa.
    E_weld : float
        Weld joint efficiency (0.85 for spot-examined longitudinal weld).
    CA_m : float
        Corrosion allowance in meters.

    Returns
    -------
    float
        Minimum required wall thickness in meters.

    Raises
    ------
    ValueError
        If P_Pa is negative.
    """
    if P_Pa < 0:
        raise ValueError(f"Pressure must be non-negative, got {P_Pa}")
    if P_Pa == 0:
        return CA_m
    denom = S_Pa * E_weld - 0.6 * P_Pa
    if denom <= 0:
        raise ValueError(
            f"Design pressure {P_Pa/1e6:.2f} MPa exceeds S×E capacity "
            f"({S_Pa/1e6:.1f}×{E_weld}={S_Pa*E_weld/1e6:.1f} MPa). "
            "Increase material strength or weld quality."
        )
    return P_Pa * R_i_m / denom + CA_m


# ---------------------------------------------------------------------------
# UG-28: External pressure — allowable pressure
# ---------------------------------------------------------------------------

def external_pressure_allowable(
    D_o_m: float,
    t_m: float,
    L_m: float,
    material: str,
    temperature_C: float,
) -> dict:
    """UG-28: Maximum allowable external pressure.

    Two-step Factor A/B procedure per ASME VIII Div 1.

    Parameters
    ----------
    D_o_m : float
        Outer diameter in meters.
    t_m : float
        Wall thickness in meters.
    L_m : float
        Unsupported length in meters.
    material : str
        Material key.
    temperature_C : float
        Design temperature in °C.

    Returns
    -------
    dict
        {
            "D_o_t": float,
            "L_D_o": float,
            "factor_A": float,
            "factor_B_MPa": float | None,
            "is_elastic": bool,
            "P_allowable_Pa": float,
            "E_Pa": float,
        }
    """
    D_o_t = D_o_m / t_m
    L_D_o = L_m / D_o_m

    # Step 1: Get Factor A from Table G
    factor_A = lookup_factor_A(D_o_t, L_D_o)

    # Step 2: Get Factor B from material chart
    E_Pa = get_elastic_modulus(material, temperature_C)
    factor_B_MPa, is_elastic = lookup_factor_B(material, temperature_C, factor_A)

    if is_elastic:
        # UG-28(c) Step 5: elastic buckling
        # P_a = 2 × A × E / (3 × (D_o/t))
        P_a_Pa = 2.0 * factor_A * E_Pa / (3.0 * D_o_t)
    else:
        # UG-28(c) Step 6: plastic buckling
        # P_a = 4 × B / (3 × (D_o/t))
        # factor_B is in MPa, convert to Pa
        P_a_Pa = 4.0 * factor_B_MPa * 1e6 / (3.0 * D_o_t)

    return {
        "D_o_t": D_o_t,
        "L_D_o": L_D_o,
        "factor_A": factor_A,
        "factor_B_MPa": factor_B_MPa if not is_elastic else None,
        "is_elastic": is_elastic,
        "P_allowable_Pa": P_a_Pa,
        "E_Pa": E_Pa,
    }


# ---------------------------------------------------------------------------
# Thermal expansion differential
# ---------------------------------------------------------------------------

def thermal_expansion_differential(
    tube_material: str,
    shell_material: str,
    T_mean_tube_C: float,
    T_mean_shell_C: float,
    tube_length_m: float,
    T_ambient_C: float = 20.0,
) -> dict:
    """Calculate differential thermal expansion between tubes and shell.

    Parameters
    ----------
    tube_material : str
        Tube material key.
    shell_material : str
        Shell material key.
    T_mean_tube_C : float
        Mean tube-side temperature in °C.
    T_mean_shell_C : float
        Mean shell-side temperature in °C.
    tube_length_m : float
        Tube length in meters.
    T_ambient_C : float
        Ambient / reference temperature in °C (default 20°C).

    Returns
    -------
    dict
        {
            "dL_tube_mm": float,
            "dL_shell_mm": float,
            "differential_mm": float,
            "alpha_tube": float,
            "alpha_shell": float,
        }
    """
    alpha_tube = get_thermal_expansion(tube_material, T_mean_tube_C)
    alpha_shell = get_thermal_expansion(shell_material, T_mean_shell_C)

    dL_tube = alpha_tube * tube_length_m * (T_mean_tube_C - T_ambient_C)
    dL_shell = alpha_shell * tube_length_m * (T_mean_shell_C - T_ambient_C)

    return {
        "dL_tube_mm": dL_tube * 1000.0,
        "dL_shell_mm": dL_shell * 1000.0,
        "differential_mm": abs(dL_tube - dL_shell) * 1000.0,
        "alpha_tube": alpha_tube,
        "alpha_shell": alpha_shell,
    }
