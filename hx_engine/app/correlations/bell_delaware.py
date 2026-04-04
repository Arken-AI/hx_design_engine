"""Pure-math correlations for shell-side heat transfer coefficient.

Bell-Delaware method (Taborek, 1983 — HEDH correlations):
  - Ideal tube-bank j-factor (Žukauskas)
  - Five correction factors: J_c, J_l, J_b, J_s, J_r
  - Geometry computation (crossflow areas, leakage areas, bypass areas)

Kern / Simplified Delaware method (cross-check only):
  - Equivalent diameter, crossflow area, j_H correlation

No side effects, no model imports. All functions are independently testable.
"""

from __future__ import annotations

import math


# ═══════════════════════════════════════════════════════════════════════════
# TABOREK TABLE 10 — Ideal bank j_i coefficients
# ═══════════════════════════════════════════════════════════════════════════
# Format: (Re_lo, Re_hi, a1, a2, a3, a4)
# j_i = a1 * (1.33/PR)^a * Re^a2, where a = a3 / (1 + 0.14 * Re^a4)

_JI_COEFFS: dict[int, list[tuple[float, float, float, float, float, float]]] = {
    30: [  # 30° triangular
        (1e0, 1e1, 1.40, -0.667, 1.450, 0.519),
        (1e1, 1e2, 0.321, -0.388, 1.450, 0.519),
        (1e2, 1e3, 0.321, -0.388, 1.450, 0.519),
        (1e3, 1e4, 0.321, -0.388, 1.450, 0.519),
        (1e4, 1e5, 0.321, -0.388, 1.450, 0.519),
    ],
    45: [  # 45° rotated square
        (1e0, 1e1, 1.550, -0.667, 1.930, 0.500),
        (1e1, 1e2, 0.498, -0.656, 1.930, 0.500),
        (1e2, 1e3, 0.730, -0.500, 1.930, 0.500),
        (1e3, 1e4, 0.370, -0.396, 1.930, 0.500),
        (1e4, 1e5, 0.370, -0.396, 1.930, 0.500),
    ],
    60: [  # 60° rotated triangular (same coefficients as 30°)
        (1e0, 1e1, 1.40, -0.667, 1.450, 0.519),
        (1e1, 1e2, 0.321, -0.388, 1.450, 0.519),
        (1e2, 1e3, 0.321, -0.388, 1.450, 0.519),
        (1e3, 1e4, 0.321, -0.388, 1.450, 0.519),
        (1e4, 1e5, 0.321, -0.388, 1.450, 0.519),
    ],
    90: [  # 90° square (inline)
        (1e0, 1e1, 0.970, -0.667, 1.187, 0.370),
        (1e1, 1e2, 0.900, -0.631, 1.187, 0.370),
        (1e2, 1e3, 0.408, -0.460, 1.187, 0.370),
        (1e3, 1e4, 0.107, -0.266, 1.187, 0.370),
        (1e4, 1e5, 0.370, -0.395, 1.187, 0.370),
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# ideal_bank_ji — Taborek Table 10
# ═══════════════════════════════════════════════════════════════════════════

def ideal_bank_ji(Re: float, layout_angle_deg: int, pitch_ratio: float) -> float:
    """Taborek (1983) HEDH Table 10 — ideal Colburn j-factor.

    j_i = a1 × (1.33/PR)^a × Re^a2
    where a = a3 / (1 + 0.14 × Re^a4)

    Args:
        Re: Shell-side Reynolds number (based on tube OD and crossflow G_s).
        layout_angle_deg: Tube layout angle (30, 45, 60, or 90 degrees).
        pitch_ratio: Tube pitch / tube OD (dimensionless).

    Returns:
        Ideal Colburn j-factor (dimensionless).

    Raises:
        ValueError: Invalid layout angle or Re <= 0.
    """
    if Re <= 0:
        raise ValueError(f"Re must be > 0, got {Re}")
    if layout_angle_deg not in _JI_COEFFS:
        raise ValueError(
            f"layout_angle_deg={layout_angle_deg} not in {{30, 45, 60, 90}}"
        )

    coeffs = _JI_COEFFS[layout_angle_deg]

    # Find the matching Re range
    for Re_lo, Re_hi, a1, a2, a3, a4 in coeffs:
        if Re_lo <= Re < Re_hi:
            a = a3 / (1.0 + 0.14 * Re ** a4)
            return a1 * (1.33 / pitch_ratio) ** a * Re ** a2

    # Re >= 1e5: use last range coefficients
    _, _, a1, a2, a3, a4 = coeffs[-1]
    a = a3 / (1.0 + 0.14 * Re ** a4)
    return a1 * (1.33 / pitch_ratio) ** a * Re ** a2


# ═══════════════════════════════════════════════════════════════════════════
# J-factor functions
# ═══════════════════════════════════════════════════════════════════════════

def compute_J_c(F_c: float) -> float:
    """Taborek Eq 3.3.10-1: baffle cut correction.

    J_c = 0.55 + 0.72 × F_c
    """
    return 0.55 + 0.72 * F_c


def compute_J_l(
    S_tb: float, S_sb: float, S_m: float,
) -> float:
    """Taborek Eq 3.3.10-2: leakage correction.

    r_lm = (S_tb + S_sb) / S_m
    r_s  = S_sb / (S_tb + S_sb)
    J_l  = 0.44(1 - r_s) + [1 - 0.44(1 - r_s)] × exp(-2.2 × r_lm)
    """
    r_lm = (S_tb + S_sb) / S_m
    r_s = S_sb / (S_tb + S_sb) if (S_tb + S_sb) > 0 else 0.0
    return 0.44 * (1.0 - r_s) + (1.0 - 0.44 * (1.0 - r_s)) * math.exp(-2.2 * r_lm)


def compute_J_b(F_bp: float, N_ss: int, N_c: float, Re: float) -> float:
    """Taborek Eq 3.3.10-3: bypass correction with sealing strips.

    C_bh = 1.35 for Re < 100, 1.25 for Re >= 100
    r_ss = N_ss / N_c
    If r_ss >= 0.5: J_b = 1.0
    Else: J_b = exp(-C_bh × F_bp × [1 - (2 × r_ss)^(1/3)])
    """
    C_bh = 1.25 if Re >= 100.0 else 1.35
    r_ss = N_ss / N_c if N_c > 0 else 0.0
    if r_ss >= 0.5:
        return 1.0
    return math.exp(-C_bh * F_bp * (1.0 - (2.0 * r_ss) ** (1.0 / 3.0)))


def compute_J_s(
    N_b: int, L_i: float, L_o: float, L_c: float,
) -> float:
    """Taborek Eq 3.3.10-4: unequal baffle spacing correction.

    n = 0.6 (turbulent exponent for heat transfer)
    J_s = (N_b - 1 + (L_i/L_c)^(1-n) + (L_o/L_c)^(1-n))
        / (N_b - 1 + (L_i/L_c) + (L_o/L_c))

    When L_i == L_o == L_c → J_s = 1.0.
    """
    n = 0.6
    ratio_i = L_i / L_c
    ratio_o = L_o / L_c
    numerator = (N_b - 1) + ratio_i ** (1.0 - n) + ratio_o ** (1.0 - n)
    denominator = (N_b - 1) + ratio_i + ratio_o
    return numerator / denominator


def compute_J_r(Re: float, N_c: float) -> float:
    """Taborek Eq 3.3.10-5: adverse temperature gradient (laminar only).

    For Re >= 100:  J_r = 1.0
    For Re >= 20:   J_r = (10/N_c)^0.18
    For Re < 20:    J_r = (10/N_c)^0.18 × (Re/20)^0.5
    """
    if Re >= 100.0:
        return 1.0
    if Re >= 20.0:
        return (10.0 / N_c) ** 0.18
    return (10.0 / N_c) ** 0.18 * (Re / 20.0) ** 0.5


# ═══════════════════════════════════════════════════════════════════════════
# compute_geometry — all intermediate areas and counts
# ═══════════════════════════════════════════════════════════════════════════

def compute_geometry(
    shell_id_m: float,
    tube_od_m: float,
    tube_pitch_m: float,
    layout_angle_deg: int,
    n_tubes: int,
    tube_passes: int,
    baffle_cut_pct: float,
    baffle_spacing_central_m: float,
    baffle_spacing_inlet_m: float,
    baffle_spacing_outlet_m: float,
    n_baffles: int,
    n_sealing_strip_pairs: int,
    delta_tb_m: float,
    delta_sb_m: float,
    delta_bundle_shell_m: float,
    mass_flow_kg_s: float,
    viscosity_Pa_s: float,
) -> dict:
    """Compute all Bell-Delaware intermediate geometry values.

    Returns a dict with keys:
        D_otl, theta_ctl, theta_ds, F_c, F_w, N_tw,
        S_m, S_w, S_tb, S_sb, S_b,
        r_lm, r_s, F_bp, P_p,
        N_c, N_cw, G_s, Re_shell
    """
    D_s = shell_id_m
    d_o = tube_od_m
    P_t = tube_pitch_m
    B_c = baffle_cut_pct
    B = baffle_spacing_central_m
    N_t = n_tubes
    delta_tb = delta_tb_m
    delta_sb = delta_sb_m
    delta_bs = delta_bundle_shell_m
    mu = viscosity_Pa_s
    m_dot = mass_flow_kg_s

    # Outer tube limit diameter
    D_otl = D_s - delta_bs

    # Baffle cut geometry angles
    cut_ratio = D_s * (1.0 - 2.0 * B_c / 100.0) / D_otl
    # Clamp to [-1, 1] for numerical safety
    cut_ratio = max(-1.0, min(1.0, cut_ratio))
    theta_ctl = 2.0 * math.acos(cut_ratio)

    theta_ds = 2.0 * math.acos(1.0 - 2.0 * B_c / 100.0)

    # Fraction of tubes in crossflow (F_c)
    sin_half_theta = math.sin(theta_ctl / 2.0)
    F_c = (1.0 / math.pi) * (math.pi + 2.0 * cut_ratio * sin_half_theta - theta_ctl)

    # Fraction of tubes in window (F_w) — from angle geometry
    F_w = (theta_ctl - math.sin(theta_ctl)) / (2.0 * math.pi)
    N_tw = F_w * N_t  # tubes in one window

    # Crossflow area at bundle centerline (S_m)
    S_m = B * (D_s - D_otl + D_otl * (P_t - d_o) / P_t)

    # Window flow area (S_w)
    S_wg = (D_s ** 2 / 8.0) * (theta_ds - math.sin(theta_ds))
    A_tubes_window = N_tw * math.pi * d_o ** 2 / 4.0
    S_w = S_wg - A_tubes_window

    # Tube-to-baffle leakage area (S_tb)
    gap_per_tube = (math.pi / 4.0) * ((d_o + delta_tb) ** 2 - d_o ** 2)
    N_tubes_through_baffle = N_t * (1.0 + F_c) / 2.0
    S_tb = gap_per_tube * N_tubes_through_baffle

    # Shell-to-baffle leakage area (S_sb)
    S_sb = math.pi * D_s * (delta_sb / 2.0) * (1.0 - theta_ds / (2.0 * math.pi))

    # Bundle bypass area (S_b)
    S_b = B * (D_s - D_otl)

    # Leakage and bypass ratios
    r_lm = (S_tb + S_sb) / S_m
    r_s = S_sb / (S_tb + S_sb) if (S_tb + S_sb) > 0 else 0.0
    F_bp = S_b / S_m

    # Row pitch and crossflow row counts
    if layout_angle_deg in (30, 60):
        P_p = P_t * math.cos(math.radians(30))  # triangular: √3/2 * P_t
    elif layout_angle_deg == 45:
        P_p = P_t * math.cos(math.radians(45))  # rotated square: √2/2 * P_t
    else:  # 90°
        P_p = P_t  # inline

    N_c = D_s * (1.0 - 2.0 * B_c / 100.0) / P_p  # crossflow rows
    N_cw = 0.8 * (D_s * B_c / 100.0) / P_p         # window rows

    # Shell-side mass velocity and Reynolds number
    G_s = m_dot / S_m
    Re_shell = d_o * G_s / mu

    return {
        "D_otl_m": D_otl,
        "theta_ctl_rad": theta_ctl,
        "theta_ds_rad": theta_ds,
        "F_c": F_c,
        "F_w": F_w,
        "N_tw": N_tw,
        "S_m_m2": S_m,
        "S_w_m2": S_w,
        "S_tb_m2": S_tb,
        "S_sb_m2": S_sb,
        "S_b_m2": S_b,
        "r_lm": r_lm,
        "r_s": r_s,
        "F_bp": F_bp,
        "P_p_m": P_p,
        "N_c": N_c,
        "N_cw": N_cw,
        "G_s_kg_m2s": G_s,
        "Re_shell": Re_shell,
    }


# ═══════════════════════════════════════════════════════════════════════════
# shell_side_htc — main orchestrator
# ═══════════════════════════════════════════════════════════════════════════

def shell_side_htc(
    # Geometry
    shell_id_m: float,
    tube_od_m: float,
    tube_pitch_m: float,
    layout_angle_deg: int,
    n_tubes: int,
    tube_passes: int,
    baffle_cut_pct: float,
    baffle_spacing_central_m: float,
    baffle_spacing_inlet_m: float,
    baffle_spacing_outlet_m: float,
    n_baffles: int,
    n_sealing_strip_pairs: int,
    # Clearances
    delta_tb_m: float,
    delta_sb_m: float,
    delta_bundle_shell_m: float,
    # Fluid props
    density_kg_m3: float,
    viscosity_Pa_s: float,
    viscosity_wall_Pa_s: float,
    Cp_J_kgK: float,
    k_W_mK: float,
    Pr: float,
    mass_flow_kg_s: float,
    # Pitch ratio (convenience — could be computed from pitch/OD)
    pitch_ratio: float,
) -> dict:
    """Compute shell-side HTC using the full Bell-Delaware method.

    Returns a dict with keys:
        h_ideal_W_m2K, h_o_W_m2K, j_i,
        J_c, J_l, J_b, J_s, J_r, J_product,
        Re_shell, geometry (sub-dict), warnings
    """
    warnings: list[str] = []

    # 1. Geometry computation
    geom = compute_geometry(
        shell_id_m=shell_id_m,
        tube_od_m=tube_od_m,
        tube_pitch_m=tube_pitch_m,
        layout_angle_deg=layout_angle_deg,
        n_tubes=n_tubes,
        tube_passes=tube_passes,
        baffle_cut_pct=baffle_cut_pct,
        baffle_spacing_central_m=baffle_spacing_central_m,
        baffle_spacing_inlet_m=baffle_spacing_inlet_m,
        baffle_spacing_outlet_m=baffle_spacing_outlet_m,
        n_baffles=n_baffles,
        n_sealing_strip_pairs=n_sealing_strip_pairs,
        delta_tb_m=delta_tb_m,
        delta_sb_m=delta_sb_m,
        delta_bundle_shell_m=delta_bundle_shell_m,
        mass_flow_kg_s=mass_flow_kg_s,
        viscosity_Pa_s=viscosity_Pa_s,
    )

    Re = geom["Re_shell"]
    G_s = geom["G_s_kg_m2s"]

    # 2. Ideal j-factor
    j_i = ideal_bank_ji(Re, layout_angle_deg, pitch_ratio)

    # 3. Viscosity correction
    if viscosity_wall_Pa_s > 0:
        visc_correction = (viscosity_Pa_s / viscosity_wall_Pa_s) ** 0.14
    else:
        visc_correction = 1.0
        warnings.append("μ_wall ≤ 0 — viscosity correction skipped")

    # 4. Ideal h
    h_ideal = j_i * Cp_J_kgK * G_s * Pr ** (-2.0 / 3.0) * visc_correction

    # 5. J-factors
    J_c = compute_J_c(geom["F_c"])
    J_l = compute_J_l(geom["S_tb_m2"], geom["S_sb_m2"], geom["S_m_m2"])
    J_b = compute_J_b(geom["F_bp"], n_sealing_strip_pairs, geom["N_c"], Re)
    J_s = compute_J_s(
        n_baffles,
        baffle_spacing_inlet_m,
        baffle_spacing_outlet_m,
        baffle_spacing_central_m,
    )
    J_r = compute_J_r(Re, geom["N_c"])

    # 6. Product and final h_o
    J_product = J_c * J_l * J_b * J_s * J_r
    h_o = h_ideal * J_product

    # 7. Warnings
    if J_product < 0.30:
        warnings.append(
            f"J-factor product = {J_product:.3f} is very low — "
            f"geometry may have excessive leakage/bypass"
        )
    if h_o < 50.0:
        warnings.append(f"h_o = {h_o:.1f} W/m²K is unusually low")
    if h_o > 15000.0:
        warnings.append(f"h_o = {h_o:.1f} W/m²K is unusually high — verify inputs")

    return {
        "h_ideal_W_m2K": h_ideal,
        "h_o_W_m2K": h_o,
        "j_i": j_i,
        "visc_correction": visc_correction,
        "J_c": J_c,
        "J_l": J_l,
        "J_b": J_b,
        "J_s": J_s,
        "J_r": J_r,
        "J_product": J_product,
        "Re_shell": Re,
        "G_s_kg_m2s": G_s,
        "geometry": geom,
        "warnings": warnings,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Kern / Simplified Delaware — cross-check only
# ═══════════════════════════════════════════════════════════════════════════

def kern_shell_side_htc(
    shell_id_m: float,
    tube_od_m: float,
    tube_pitch_m: float,
    pitch_layout: str,
    baffle_spacing_m: float,
    viscosity_Pa_s: float,
    viscosity_wall_Pa_s: float,
    Cp_J_kgK: float,
    k_W_mK: float,
    mass_flow_kg_s: float,
) -> dict:
    """Kern method shell-side HTC (cross-check only).

    Uses equivalent diameter and j_H correlation from Kern (1950).
    NOT the primary method — only for divergence checks.

    Returns dict with h_o_kern, Re_kern, De, G_s, j_H.
    """
    D_s = shell_id_m
    d_o = tube_od_m
    P_t = tube_pitch_m
    B = baffle_spacing_m
    mu = viscosity_Pa_s

    # Equivalent diameter (hydraulic)
    if pitch_layout == "square":
        # D_e = 4 × (P_t² - π*d_o²/4) / (π*d_o)
        De = 4.0 * (P_t ** 2 - math.pi * d_o ** 2 / 4.0) / (math.pi * d_o)
    else:
        # Triangular: D_e = 4 × (P_t²*√3/4 - π*d_o²/8) / (π*d_o/2)
        De = 4.0 * (P_t ** 2 * math.sqrt(3) / 4.0 - math.pi * d_o ** 2 / 8.0) / (math.pi * d_o / 2.0)

    # Crossflow area
    C_prime = P_t - d_o  # clearance between tubes
    A_s = D_s * B * C_prime / P_t

    # Mass velocity and Reynolds number
    G_s = mass_flow_kg_s / A_s
    Re_kern = De * G_s / mu

    # Kern j_H correlation (power-law fit from Coulson & Richardson Fig 12.29)
    # j_H = 0.36 × Re^(-0.55) for Re in [2×10³, 1×10⁶] (25% baffle cut)
    if Re_kern < 10:
        j_H = 1.0  # placeholder for very low Re
    else:
        j_H = 0.36 * Re_kern ** (-0.55)

    # Prandtl number from Cp, mu, k
    Pr = mu * Cp_J_kgK / k_W_mK

    # Viscosity correction
    if viscosity_wall_Pa_s > 0:
        visc_corr = (mu / viscosity_wall_Pa_s) ** 0.14
    else:
        visc_corr = 1.0

    # h_o_kern = j_H × (k/De) × Re × Pr^(1/3) × (μ/μ_w)^0.14
    h_o_kern = j_H * (k_W_mK / De) * Re_kern * Pr ** (1.0 / 3.0) * visc_corr

    return {
        "h_o_kern_W_m2K": h_o_kern,
        "Re_kern": Re_kern,
        "De_m": De,
        "G_s_kg_m2s": G_s,
        "j_H": j_H,
        "Pr_kern": Pr,
    }
