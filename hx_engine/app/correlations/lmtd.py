"""Pure math functions for LMTD and F-factor calculations.

No side effects, no model imports. All functions are independently testable.

Reference: Bowman, Mueller & Nagle (1940) — "Mean Temperature Difference
in Design", Trans. ASME, 62, 283–294.
"""

from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# LMTD
# ---------------------------------------------------------------------------

def compute_lmtd(
    T_hot_in: float,
    T_hot_out: float,
    T_cold_in: float,
    T_cold_out: float,
) -> float:
    """Log Mean Temperature Difference for counter-current flow.

    Args:
        T_hot_in, T_hot_out: Hot stream inlet/outlet (°C or K).
        T_cold_in, T_cold_out: Cold stream inlet/outlet (°C or K).

    Returns:
        LMTD in same units as input temperatures (°C difference = K difference).

    Raises:
        ValueError: Temperature cross (ΔT₁ ≤ 0 or ΔT₂ ≤ 0).
    """
    dT1 = T_hot_in - T_cold_out   # hot end
    dT2 = T_hot_out - T_cold_in   # cold end

    if dT1 < 1e-10 or dT2 < 1e-10:
        raise ValueError(
            f"Temperature cross or zero ΔT: ΔT₁={dT1:.4f}, ΔT₂={dT2:.4f}. "
            f"Both must be > 0 for valid heat exchange."
        )

    # Equal ΔT corner case — avoid 0/ln(1) = 0/0
    if abs(dT1 - dT2) < 1e-6:
        return (dT1 + dT2) / 2.0

    return (dT1 - dT2) / math.log(dT1 / dT2)


# ---------------------------------------------------------------------------
# R — heat capacity ratio
# ---------------------------------------------------------------------------

def compute_R(
    T_hot_in: float,
    T_hot_out: float,
    T_cold_in: float,
    T_cold_out: float,
) -> float:
    """Dimensionless heat capacity ratio.

    R = (T_hot_in - T_hot_out) / (T_cold_out - T_cold_in)

    R > 0 always for valid designs. R = 1.0 means equal heat capacity rates.

    Raises:
        ValueError: Cold-side ΔT is zero.
    """
    dT_cold = T_cold_out - T_cold_in
    if abs(dT_cold) < 1e-10:
        raise ValueError("Cold side ΔT is zero — cannot compute R")
    return (T_hot_in - T_hot_out) / dT_cold


# ---------------------------------------------------------------------------
# P — thermal effectiveness
# ---------------------------------------------------------------------------

def compute_P(
    T_hot_in: float,
    T_hot_out: float,
    T_cold_in: float,
    T_cold_out: float,
) -> float:
    """Dimensionless thermal effectiveness.

    P = (T_cold_out - T_cold_in) / (T_hot_in - T_cold_in)

    P ∈ (0, 1) for all physically valid cases. P = 0 means no heat
    transferred; P ≥ 1 violates the second law.

    Raises:
        ValueError: No initial temperature difference (T_hot_in == T_cold_in).
    """
    dT_max = T_hot_in - T_cold_in
    if abs(dT_max) < 1e-10:
        raise ValueError(
            "T_hot_in ≈ T_cold_in — no driving force, cannot compute P"
        )
    return (T_cold_out - T_cold_in) / dT_max


# ---------------------------------------------------------------------------
# F-factor — Bowman analytical formula
# ---------------------------------------------------------------------------

def _equivalent_P1(R: float, P: float, N: int) -> float:
    """Convert overall effectiveness P to single-shell equivalent P₁.

    For N shell passes in series, compute the P that a single 1-2
    exchanger would need to achieve the same overall effectiveness.
    """
    if abs(R - 1.0) < 1e-6:
        denom = N - (N - 1) * P
        if abs(denom) < 1e-15:
            return 0.0
        return P / denom

    ratio_base = (1 - R * P) / (1 - P)
    if ratio_base <= 0:
        return 0.0  # Infeasible — RP ≥ 1
    ratio = ratio_base ** (1.0 / N)
    denom = R - ratio
    if abs(denom) < 1e-15:
        return 0.0
    return (1 - ratio) / denom


def _f_factor_R_equals_1(P: float) -> float:
    """F-factor when R = 1.0 (L'Hôpital limit of the Bowman formula)."""
    sqrt2 = math.sqrt(2)
    numer = sqrt2 * P / (1 - P)

    A = 2 - P * (2 - sqrt2)
    B = 2 - P * (2 + sqrt2)
    if B == 0 or A / B <= 0:
        return 0.0
    denom = math.log(A / B)

    if abs(denom) < 1e-15:
        return 0.0
    F = numer / denom
    return max(0.0, min(1.0, F))


def compute_f_factor(R: float, P: float, n_shell_passes: int = 1) -> float:
    """F-factor correction for multi-pass shell-and-tube exchangers.

    Uses the Bowman (1940) analytical formula. Works for any even number
    of tube passes (2, 4, 6, 8). F depends only on R, P, and
    n_shell_passes — tube pass count does not affect F.

    Args:
        R: Heat capacity ratio (> 0).
        P: Thermal effectiveness (0 < P < 1).
        n_shell_passes: Number of shell passes (1 or 2).

    Returns:
        F in range [0.0, 1.0]. Returns 0.0 for infeasible configurations.
    """
    if P <= 0 or P >= 1:
        return 0.0
    if R <= 0:
        return 0.0

    # --- Multi-shell: convert P to equivalent single-shell P₁ ---
    if n_shell_passes > 1:
        P = _equivalent_P1(R, P, n_shell_passes)
        if P <= 0 or P >= 1:
            return 0.0

    # --- R ≈ 1.0: L'Hôpital limit ---
    if abs(R - 1.0) < 1e-6:
        return _f_factor_R_equals_1(P)

    # --- General Bowman formula ---
    sqrt_term = math.sqrt(R**2 + 1)

    # Numerator: √(R²+1) · ln((1-P)/(1-RP))
    num_ln_arg = (1 - P) / (1 - R * P)
    if num_ln_arg <= 0:
        return 0.0  # RP ≥ 1 → infeasible
    numerator = sqrt_term * math.log(num_ln_arg)

    # Denominator: (R-1) · ln((2 - P(R+1-√(R²+1))) / (2 - P(R+1+√(R²+1))))
    A = 2 - P * (R + 1 - sqrt_term)
    B = 2 - P * (R + 1 + sqrt_term)
    if B == 0 or A / B <= 0:
        return 0.0  # Domain violation
    denominator = (R - 1) * math.log(A / B)

    if abs(denominator) < 1e-15:
        return 0.0  # Degenerate

    F = numerator / denominator

    # Clamp to valid range
    return max(0.0, min(1.0, F))
