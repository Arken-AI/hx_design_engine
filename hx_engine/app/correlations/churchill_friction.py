"""Churchill (1977) friction factor — all flow regimes in one equation.

Ref: Churchill, S.W. (1977). "Friction-factor equation spans all
     fluid-flow regimes." Chemical Engineering, 84(24), 91–92.

Returns the **Darcy** friction factor.  Verification: f → 64/Re as Re → 0+.
"""

from __future__ import annotations

import math


def churchill_friction_factor(Re: float, roughness_ratio: float = 0.0) -> float:
    """Churchill (1977) — Darcy friction factor for all flow regimes.

    Args:
        Re: Reynolds number (> 0).
        roughness_ratio: ε/D (dimensionless). Default 0.0 = smooth tube.

    Returns:
        Darcy friction factor (dimensionless).

    Raises:
        ValueError: If Re <= 0.
    """
    if Re <= 0:
        raise ValueError(f"Reynolds number must be > 0, got {Re}")

    # A term — turbulent-dominated
    inner = (7.0 / Re) ** 0.9 + 0.27 * roughness_ratio
    if inner <= 0:
        # Should never happen for physical inputs, but guard anyway
        A = 0.0
    else:
        A = (-2.457 * math.log(inner)) ** 16

    # B term — transition-dominated
    B = (37530.0 / Re) ** 16

    # Darcy friction factor
    f = 8.0 * ((8.0 / Re) ** 12 + 1.0 / (A + B) ** 1.5) ** (1.0 / 12.0)
    return f
