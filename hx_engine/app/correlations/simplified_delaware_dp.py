"""Simplified Delaware shell-side pressure drop (cross-check).

Serth, R.W. & Lestina, T. (2014). *Process Heat Transfer*, 2nd ed.
Uses Eqs. 5.6–5.11 for friction factor, Eq. 5.A.5 for SI pressure drop.

This is intentionally an *independent* method (no shared Bell-Delaware
correction factors) so it provides a genuine second opinion.
"""

from __future__ import annotations

import math

_M_TO_IN = 39.3701  # metres → inches


def simplified_delaware_shell_dP(
    shell_id_m: float,
    tube_od_m: float,
    tube_pitch_m: float,
    layout_angle_deg: int,
    baffle_spacing_m: float,
    n_baffles: int,
    mass_flow_kg_s: float,
    density_kg_m3: float,
    viscosity_Pa_s: float,
    viscosity_wall_Pa_s: float,
) -> dict:
    """Serth Simplified Delaware shell-side pressure drop.

    Returns dict with keys:
        dP_shell_Pa, f_serth, f1, f2, B_over_ds, Re_shell,
        method ("simplified_delaware")
    """
    d_o = tube_od_m
    P_t = tube_pitch_m
    D_s = shell_id_m
    B = baffle_spacing_m

    # Shell ID in inches (for friction factor correlations)
    d_s_in = D_s * _M_TO_IN

    # Equivalent diameter (hydraulic) — same as Kern
    if layout_angle_deg in (45, 90):  # square/rotated-square
        De = 4.0 * (P_t ** 2 - math.pi * d_o ** 2 / 4.0) / (math.pi * d_o)
    else:  # triangular 30/60
        De = (4.0 * (P_t ** 2 * math.sqrt(3) / 4.0 - math.pi * d_o ** 2 / 8.0)
              / (math.pi * d_o / 2.0))

    # Crossflow area
    C_prime = P_t - d_o
    A_s = D_s * B * C_prime / P_t

    # Mass velocity and Reynolds
    G_s = mass_flow_kg_s / A_s
    Re = De * G_s / viscosity_Pa_s

    # B/d_s ratio
    B_over_ds = B / D_s

    # Friction factor components (Serth Eqs. 5.8–5.11)
    if Re >= 1000:
        f1 = (0.0076 + 0.000166 * d_s_in) * Re ** (-0.125)
        f2 = (0.0016 + 5.8e-5 * d_s_in) * Re ** (-0.157)
    else:
        ln_Re = math.log(max(Re, 1.0))
        d_s_capped = min(d_s_in, 23.25)
        f1 = math.exp(
            -0.092 * ln_Re ** 2 - 1.48 * ln_Re
            - 0.000526 * d_s_in ** 2 + 0.0478 * d_s_in - 0.338
        )
        f2 = math.exp(
            -0.123 * ln_Re ** 2 - 1.78 * ln_Re
            - 0.00132 * d_s_capped ** 2 + 0.0678 * d_s_capped - 1.34
        )

    # Interpolated friction factor (Eq. 5.7)
    # f = 144 × { f1 - 1.25 × (1 - B/d_s) × (f1 - f2) }
    f = 144.0 * (f1 - 1.25 * (1.0 - B_over_ds) * (f1 - f2))

    # Viscosity correction (φ = (μ/μ_w)^0.14)
    if viscosity_wall_Pa_s > 0:
        phi = (viscosity_Pa_s / viscosity_wall_Pa_s) ** 0.14
    else:
        phi = 1.0

    # Specific gravity relative to water
    s = density_kg_m3 / 1000.0

    # ΔP (Eq. 5.A.5 — SI)
    # ΔP_f = f × G² × d_s(m) × (n_b + 1) / (2000 × D_e(m) × s × φ)
    # where G is in kg/(m²·s), result in kPa → convert to Pa
    dP_kPa = (f * G_s ** 2 * D_s * (n_baffles + 1)
              / (2000.0 * De * s * phi))
    dP_Pa = dP_kPa * 1000.0

    return {
        "dP_shell_Pa": dP_Pa,
        "f_serth": f,
        "f1": f1,
        "f2": f2,
        "B_over_ds": B_over_ds,
        "Re_shell": Re,
        "method": "simplified_delaware",
    }
