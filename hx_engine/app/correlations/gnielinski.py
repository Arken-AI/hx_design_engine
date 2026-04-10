"""Pure-math correlations for tube-side heat transfer coefficient.

Gnielinski (1976)  — turbulent & transition (Re ≥ 2300)
Hausen (1943)      — laminar developing flow (Re < 2300)
Petukhov (1970)    — friction factor paired with Gnielinski
Dittus-Boelter      — crosscheck only

No side effects, no model imports. All functions are independently testable.
"""

from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# Petukhov friction factor
# ---------------------------------------------------------------------------

def petukhov_friction(Re: float) -> float:
    """Petukhov smooth-tube friction factor.

    f = (0.790 × ln(Re) − 1.64)^(−2)

    Valid for Re > 2300 (turbulent / transition).

    Raises:
        ValueError: Re ≤ 0.
    """
    if Re <= 0:
        raise ValueError(f"Re must be > 0, got {Re}")
    return (0.790 * math.log(Re) - 1.64) ** (-2)


# ---------------------------------------------------------------------------
# Hausen — laminar developing flow
# ---------------------------------------------------------------------------

def hausen_nu(Re: float, Pr: float, D: float, L: float) -> float:
    """Hausen correlation for laminar developing flow (Re < 2300).

    Nu = 3.66 + (0.0668 × Gz) / (1 + 0.04 × Gz^(2/3))
    where Gz = Re × Pr × D / L

    Returns max(3.66, Nu) as a defensive floor.

    Raises:
        ValueError: D ≤ 0 or L ≤ 0.
    """
    if D <= 0:
        raise ValueError(f"D must be > 0, got {D}")
    if L <= 0:
        raise ValueError(f"L must be > 0, got {L}")

    Gz = Re * Pr * D / L
    Nu = 3.66 + (0.0668 * Gz) / (1 + 0.04 * Gz ** (2.0 / 3.0))
    return max(3.66, Nu)


# ---------------------------------------------------------------------------
# Gnielinski — turbulent & transition
# ---------------------------------------------------------------------------

def gnielinski_nu(Re: float, Pr: float, f: float) -> float:
    """Gnielinski correlation (Re ≥ 2300, 0.5 ≤ Pr ≤ 2000).

    Nu = ((f/8)(Re − 1000) × Pr) / (1 + 12.7 × √(f/8) × (Pr^(2/3) − 1))

    Raises:
        ValueError: denominator ≤ 0 or invalid inputs.
    """
    f_over_8 = f / 8.0
    numerator = f_over_8 * (Re - 1000.0) * Pr
    denominator = 1.0 + 12.7 * math.sqrt(f_over_8) * (Pr ** (2.0 / 3.0) - 1.0)
    if denominator <= 0:
        raise ValueError(
            f"Gnielinski denominator ≤ 0 (Re={Re}, Pr={Pr}, f={f})"
        )
    return numerator / denominator


# ---------------------------------------------------------------------------
# Dittus-Boelter — crosscheck only
# ---------------------------------------------------------------------------

def dittus_boelter_nu(Re: float, Pr: float) -> float:
    """Dittus-Boelter correlation (crosscheck only).

    Nu = 0.023 × Re^0.8 × Pr^0.4
    """
    return 0.023 * Re ** 0.8 * Pr ** 0.4


# ---------------------------------------------------------------------------
# Main entry point — tube_side_h
# ---------------------------------------------------------------------------

def tube_side_h(
    Re: float,
    Pr: float,
    D_i: float,
    L: float,
    k: float,
    mu_bulk: float,
    mu_wall: float | None,
) -> dict:
    """Compute tube-side heat transfer coefficient.

    Selects correlation based on Re regime, applies viscosity correction,
    and provides a Dittus-Boelter crosscheck for turbulent flow.

    Args:
        Re: Reynolds number.
        Pr: Prandtl number.
        D_i: Tube inner diameter (m).
        L: Tube length (m).
        k: Fluid thermal conductivity (W/m·K).
        mu_bulk: Bulk viscosity (Pa·s).
        mu_wall: Wall viscosity (Pa·s). None → skip correction.

    Returns:
        Dict with h_i, Nu, method, flow_regime, and diagnostics.
    """
    warnings: list[str] = []

    # 1. Determine regime and compute Nu
    f_pet: float | None = None
    if Re < 2300:
        flow_regime = "laminar"
        method = "hausen"
        Nu_raw = hausen_nu(Re, Pr, D_i, L)
    else:
        f_pet = petukhov_friction(Re)
        Nu_raw = gnielinski_nu(Re, Pr, f_pet)
        method = "gnielinski"
        if Re < 10000:
            flow_regime = "transition"
        else:
            flow_regime = "turbulent"

    # 2. Viscosity correction: Nu_corrected = Nu × (μ_bulk / μ_wall)^0.14
    if mu_wall is not None and mu_wall > 0:
        viscosity_ratio = (mu_bulk / mu_wall) ** 0.14
    else:
        viscosity_ratio = 1.0
        warnings.append(
            "μ_wall unavailable or ≤ 0 — viscosity correction skipped"
        )

    Nu_corrected = Nu_raw * viscosity_ratio

    # 3. Compute h_i
    h_i = Nu_corrected * k / D_i

    # 4. Dittus-Boelter crosscheck (turbulent only)
    db_nu: float | None = None
    db_divergence: float | None = None
    if Re >= 10000:
        db_nu = dittus_boelter_nu(Re, Pr)
        if db_nu > 0:
            db_divergence = abs(Nu_corrected - db_nu) / db_nu * 100.0
            if db_divergence > 20.0:
                warnings.append(
                    f"Dittus-Boelter divergence = {db_divergence:.1f}% "
                    f"(Nu_gnielinski={Nu_corrected:.1f}, Nu_DB={db_nu:.1f})"
                )

    return {
        "h_i": h_i,
        "Nu": Nu_corrected,
        "Nu_uncorrected": Nu_raw,
        "f_petukhov": f_pet,
        "method": method,
        "flow_regime": flow_regime,
        "viscosity_correction": viscosity_ratio,
        "dittus_boelter_Nu": db_nu,
        "dittus_boelter_divergence_pct": db_divergence,
        "warnings": warnings,
    }
