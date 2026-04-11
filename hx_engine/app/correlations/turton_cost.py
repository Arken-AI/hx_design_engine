"""Turton cost correlation functions for shell-and-tube heat exchangers.

Pure calculation functions — no state, no I/O, no side effects.

Sources:
  - Turton et al. (2013), Appendix A
  - Equations referenced in Step15ImplPlan.md

Used by:
  - Step 15 (cost estimate): step_15_cost.py
"""

from __future__ import annotations

import math


def purchased_equipment_cost(
    area_m2: float,
    K1: float,
    K2: float,
    K3: float,
) -> float:
    """Calculate base purchased equipment cost (C_p^0) in 2001 USD.

    .. math::

        \\log_{10} C_p^0 = K_1 + K_2 \\log_{10}(A) + K_3 [\\log_{10}(A)]^2

    Parameters
    ----------
    area_m2 : float
        Heat transfer area in m².
    K1, K2, K3 : float
        Turton Table A.1 constants for the HX type.

    Returns
    -------
    float
        Base purchased cost in 2001 USD.

    Raises
    ------
    ValueError
        If *area_m2* ≤ 0.
    """
    if area_m2 <= 0:
        raise ValueError(f"area_m2 must be > 0, got {area_m2}")
    log_a = math.log10(area_m2)
    log_cp0 = K1 + K2 * log_a + K3 * log_a ** 2
    return 10.0 ** log_cp0


def pressure_factor(
    pressure_barg: float,
    C1: float,
    C2: float,
    C3: float,
) -> float:
    """Calculate pressure correction factor F_P.

    .. math::

        \\log_{10} F_P = C_1 + C_2 \\log_{10}(P) + C_3 [\\log_{10}(P)]^2

    Returns 1.0 if *pressure_barg* < 5 (below correction threshold).

    Parameters
    ----------
    pressure_barg : float
        Design pressure in barg (gauge).
    C1, C2, C3 : float
        Turton Table A.2 constants for the pressure regime.

    Returns
    -------
    float
        Pressure correction factor (≥ 1.0).

    Raises
    ------
    ValueError
        If *pressure_barg* < 0.
    """
    if pressure_barg < 0:
        raise ValueError(f"pressure_barg must be >= 0, got {pressure_barg}")
    if pressure_barg < 5.0:
        return 1.0
    log_p = math.log10(pressure_barg)
    log_fp = C1 + C2 * log_p + C3 * log_p ** 2
    fp = 10.0 ** log_fp
    # F_P should never be below 1.0 (no discount for pressure)
    return max(fp, 1.0)


def bare_module_cost(
    Cp0: float,
    F_M: float,
    F_P: float,
    B1: float = 1.63,
    B2: float = 1.66,
) -> float:
    """Calculate bare module cost in base-year USD.

    .. math::

        C_{BM} = C_p^0 \\times (B_1 + B_2 \\cdot F_M \\cdot F_P)

    Parameters
    ----------
    Cp0 : float
        Base purchased equipment cost (2001 USD).
    F_M : float
        Material correction factor.
    F_P : float
        Pressure correction factor.
    B1, B2 : float
        Bare module factor constants (default: Table A.4 values).

    Returns
    -------
    float
        Bare module cost in base-year USD.

    Raises
    ------
    ValueError
        If any input is negative.
    """
    if Cp0 < 0 or F_M < 0 or F_P < 0:
        raise ValueError(
            f"All inputs must be >= 0: Cp0={Cp0}, F_M={F_M}, F_P={F_P}"
        )
    return Cp0 * (B1 + B2 * F_M * F_P)


def cepci_adjust(
    cost_base_year: float,
    cepci_current: float,
    cepci_base: float,
) -> float:
    """Adjust cost from base year to current year using CEPCI ratio.

    .. math::

        C_{current} = C_{base} \\times \\frac{CEPCI_{current}}{CEPCI_{base}}

    Raises
    ------
    ValueError
        If *cepci_base* ≤ 0.
    """
    if cepci_base <= 0:
        raise ValueError(f"cepci_base must be > 0, got {cepci_base}")
    return cost_base_year * (cepci_current / cepci_base)


def interpolated_material_factor(
    shell_material: str,
    tube_material: str,
    shell_weight_kg: float,
    tube_weight_kg: float,
    cost_ratios: dict[str, float],
) -> float:
    """Estimate F_M from material cost ratios when Turton lookup fails.

    .. math::

        F_M \\approx \\frac{w_{shell} \\cdot c_{shell} + w_{tubes} \\cdot c_{tubes}}
                          {w_{shell} \\cdot c_{CS} + w_{tubes} \\cdot c_{CS}}

    Parameters
    ----------
    shell_material, tube_material : str
        Internal material names.
    shell_weight_kg, tube_weight_kg : float
        Estimated component weights in kg.
    cost_ratios : dict[str, float]
        Material cost ratios relative to carbon steel (= 1.0).

    Returns
    -------
    float
        Estimated material factor (always ≥ 1.0).

    Raises
    ------
    KeyError
        If a material is not in *cost_ratios*.
    """
    c_shell = cost_ratios[shell_material]
    c_tube = cost_ratios[tube_material]
    c_cs = cost_ratios.get("carbon_steel", 1.0)

    total_weight = shell_weight_kg + tube_weight_kg
    if total_weight <= 0:
        # Fallback: equal weighting
        return max((c_shell + c_tube) / (2.0 * c_cs), 1.0)

    weighted_cost = shell_weight_kg * c_shell + tube_weight_kg * c_tube
    baseline_cost = total_weight * c_cs
    return max(weighted_cost / baseline_cost, 1.0)


def estimate_component_weights(
    shell_diameter_m: float,
    shell_length_m: float,
    shell_thickness_m: float,
    shell_density_kg_m3: float,
    tube_od_m: float,
    tube_id_m: float,
    tube_length_m: float,
    n_tubes: int,
    tube_density_kg_m3: float,
) -> tuple[float, float]:
    """Estimate shell and tube weights in kg.

    Shell = π × D × L × t × ρ  (cylindrical shell, no heads)
    Tubes = n × π/4 × (d_o² − d_i²) × L × ρ

    Returns
    -------
    (shell_weight_kg, tube_weight_kg)
    """
    shell_weight = (
        math.pi * shell_diameter_m * shell_length_m
        * shell_thickness_m * shell_density_kg_m3
    )
    tube_cross_section = math.pi / 4.0 * (tube_od_m ** 2 - tube_id_m ** 2)
    tube_weight = n_tubes * tube_cross_section * tube_length_m * tube_density_kg_m3

    return shell_weight, tube_weight
