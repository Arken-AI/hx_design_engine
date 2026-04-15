"""Shah (1979) correlation for condensation inside horizontal tubes.

Shah, M.M. (1979). "A general correlation for heat transfer during film
condensation inside pipes." International Journal of Heat and Mass Transfer,
22(4), 547–556.

Valid for:
  - Horizontal tubes, film condensation
  - 10.8 < Re_l < 63000
  - 0.002 < P_r (reduced pressure) < 0.44
  - 0.01 ≤ x ≤ 0.99 (quality)
  - All flow regimes (stratified to annular)

No side effects, no model imports. All functions are independently testable.
"""

from __future__ import annotations

import math


def shah_condensation_h(
    x: float,
    G: float,
    D_i: float,
    rho_l: float,
    rho_g: float,
    mu_l: float,
    mu_g: float,
    k_l: float,
    cp_l: float,
    h_fg: float,
    P_sat: float,
    P_crit: float,
) -> dict:
    """Compute local condensation HTC using Shah (1979) correlation.

    Args:
        x: Local vapor quality (0.0–1.0).
        G: Mass flux (kg/m²·s) = m_dot / A_cross.
        D_i: Tube inner diameter (m).
        rho_l: Saturated liquid density (kg/m³).
        rho_g: Saturated vapor density (kg/m³).
        mu_l: Saturated liquid viscosity (Pa·s).
        mu_g: Saturated vapor viscosity (Pa·s).
        k_l: Saturated liquid thermal conductivity (W/m·K).
        cp_l: Saturated liquid specific heat (J/kg·K).
        h_fg: Latent heat of vaporisation (J/kg).
        P_sat: Saturation pressure (Pa).
        P_crit: Critical pressure (Pa).

    Returns:
        Dict with:
          h_cond: local condensation HTC (W/m²·K)
          h_lo: liquid-only HTC (W/m²·K)
          Re_lo: liquid-only Reynolds number
          Pr_l: liquid Prandtl number
          method: "shah_condensation"
          warnings: list of warning strings
    """
    warnings: list[str] = []

    x = max(0.01, min(0.99, x))

    # Reduced pressure
    P_r = P_sat / P_crit if P_crit > 0 else 0.01
    P_r = max(0.001, min(0.95, P_r))

    # Liquid-only Reynolds number (entire mass flow as liquid)
    Re_lo = G * D_i / mu_l

    # Liquid Prandtl number
    Pr_l = mu_l * cp_l / k_l

    # Liquid-only Nusselt (Dittus-Boelter)
    Nu_lo = 0.023 * Re_lo ** 0.8 * Pr_l ** 0.4

    # Liquid-only HTC
    h_lo = Nu_lo * k_l / D_i

    # Shah correlation multiplier
    # h_TP / h_lo = (1-x)^0.8 + (3.8 × x^0.76 × (1-x)^0.04) / P_r^0.38
    shah_mult = (1.0 - x) ** 0.8 + (
        3.8 * x ** 0.76 * (1.0 - x) ** 0.04
    ) / P_r ** 0.38

    h_cond = h_lo * shah_mult

    # Validity checks
    if Re_lo < 10.8:
        warnings.append(
            f"Re_lo={Re_lo:.1f} below Shah correlation minimum (10.8)"
        )
    if Re_lo > 63000:
        warnings.append(
            f"Re_lo={Re_lo:.0f} above Shah correlation maximum (63000)"
        )
    if P_r < 0.002 or P_r > 0.44:
        warnings.append(
            f"Reduced pressure P_r={P_r:.4f} outside Shah validity "
            f"range [0.002, 0.44]"
        )

    return {
        "h_cond": h_cond,
        "h_lo": h_lo,
        "Re_lo": Re_lo,
        "Pr_l": Pr_l,
        "shah_multiplier": shah_mult,
        "method": "shah_condensation",
        "warnings": warnings,
    }


def shah_condensation_average_h(
    G: float,
    D_i: float,
    rho_l: float,
    rho_g: float,
    mu_l: float,
    mu_g: float,
    k_l: float,
    cp_l: float,
    h_fg: float,
    P_sat: float,
    P_crit: float,
    x_in: float = 1.0,
    x_out: float = 0.0,
    n_points: int = 20,
) -> dict:
    """Compute average condensation HTC by integrating over quality range.

    Integrates Shah local HTC from x_in to x_out using trapezoidal rule.

    Args:
        Same as shah_condensation_h plus:
        x_in: Inlet quality (default 1.0 = saturated vapor).
        x_out: Outlet quality (default 0.0 = saturated liquid).
        n_points: Number of integration points.

    Returns:
        Dict with h_avg, method, warnings.
    """
    warnings: list[str] = []

    if x_in <= x_out:
        x_in, x_out = max(x_in, x_out), min(x_in, x_out)

    dx = (x_in - x_out) / n_points
    h_sum = 0.0

    for i in range(n_points + 1):
        x = x_in - i * dx
        x = max(0.01, min(0.99, x))
        result = shah_condensation_h(
            x=x, G=G, D_i=D_i,
            rho_l=rho_l, rho_g=rho_g,
            mu_l=mu_l, mu_g=mu_g,
            k_l=k_l, cp_l=cp_l,
            h_fg=h_fg, P_sat=P_sat, P_crit=P_crit,
        )
        weight = 0.5 if (i == 0 or i == n_points) else 1.0
        h_sum += result["h_cond"] * weight
        warnings.extend(result["warnings"])

    h_avg = h_sum / n_points

    # Deduplicate warnings
    seen = set()
    unique_warnings = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            unique_warnings.append(w)

    return {
        "h_avg": h_avg,
        "x_in": x_in,
        "x_out": x_out,
        "method": "shah_condensation_avg",
        "warnings": unique_warnings,
    }


# ── Critical pressure data for common fluids ─────────────────────────────────

_CRITICAL_PRESSURES_PA: dict[str, float] = {
    "water": 22.064e6,
    "steam": 22.064e6,
    "ammonia": 11.333e6,
    "ethanol": 6.148e6,
    "methanol": 8.084e6,
    "toluene": 4.109e6,
    "benzene": 4.895e6,
    "acetone": 4.700e6,
    "hexane": 3.025e6,
    "heptane": 2.740e6,
    "pentane": 3.370e6,
    "nitrogen": 3.396e6,
    "oxygen": 5.043e6,
    "hydrogen": 1.296e6,
    "r134a": 4.059e6,
    "r22": 4.990e6,
    "r410a": 4.901e6,
    "propane": 4.248e6,
    "butane": 3.796e6,
    "isobutane": 3.640e6,
}


def get_critical_pressure(fluid_name: str) -> float | None:
    """Return critical pressure (Pa) for a fluid, or None if unknown."""
    normalised = fluid_name.strip().lower()
    return _CRITICAL_PRESSURES_PA.get(normalised)
