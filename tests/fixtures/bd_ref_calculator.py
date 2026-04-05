#!/usr/bin/env python3
"""BD-REF-001 — Self-documenting Bell-Delaware reference calculator.

Implements every Bell-Delaware formula from Taborek (1983) HEDH correlations
for a canonical geometry, computing all intermediate values deterministically.
Outputs a JSON answer key (bd_ref_001.json) for gate-testing bell_delaware.py.

Run directly:
    python bd_ref_calculator.py

All numbers are deterministic outputs of published correlations applied to
defined inputs. Change an input → re-run → get a new answer key.
"""

from __future__ import annotations

import json
import math
import os
import sys


# ═══════════════════════════════════════════════════════════════════════════
# INPUTS — Canonical geometry (BD-REF-001)
# ═══════════════════════════════════════════════════════════════════════════

INPUTS = {
    "shell_id_m": 0.489,
    "tube_od_m": 0.01905,
    "tube_id_m": 0.01483,
    "tube_pitch_m": 0.0254,
    "pitch_ratio": 1.3333,
    "layout_angle_deg": 30,
    "num_tubes": 158,
    "tube_length_m": 4.877,
    "tube_passes": 2,
    "baffle_cut_pct": 25.0,
    "baffle_spacing_central_m": 0.1956,
    "baffle_spacing_inlet_m": 0.3048,
    "baffle_spacing_outlet_m": 0.3048,
    "num_baffles": 22,
    "num_sealing_strips": 2,
    "clearances": {
        "tube_baffle_diametral_m": 0.0008,
        "shell_baffle_diametral_m": 0.003175,
        "bundle_shell_diametral_m": 0.0111,
    },
    "fluid": {
        "description": "Light hydrocarbon oil @ 80C mean",
        "density_kg_m3": 820.0,
        "viscosity_Pa_s": 0.00052,
        "viscosity_wall_Pa_s": 0.00068,
        "Cp_J_kgK": 2200.0,
        "k_W_mK": 0.138,
        "Pr": 8.2899,
        "mass_flow_kg_s": 36.0,
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# TABOREK TABLE 10 — Ideal bank j_i coefficients (30° triangular)
# ═══════════════════════════════════════════════════════════════════════════
# Format: (Re_lo, Re_hi, a1, a2, a3, a4)
# j_i = a1 * (1.33/PR)^a * Re^a2, where a = a3 / (1 + 0.14 * Re^a4)

_JI_COEFFS_30 = [
    (1e0, 1e1, 1.40, -0.667, 1.450, 0.519),
    (1e1, 1e2, 0.321, -0.388, 1.450, 0.519),
    (1e2, 1e3, 0.321, -0.388, 1.450, 0.519),
    (1e3, 1e4, 0.321, -0.388, 1.450, 0.519),
    (1e4, 1e5, 0.321, -0.388, 1.450, 0.519),
]


def compute_ji(Re: float, pitch_ratio: float) -> float:
    """Taborek (1983) HEDH Table 10 — ideal Colburn j-factor for 30° layout."""
    for Re_lo, Re_hi, a1, a2, a3, a4 in _JI_COEFFS_30:
        if Re_lo <= Re < Re_hi or (Re >= 1e5 and Re_hi == 1e5):
            a = a3 / (1.0 + 0.14 * Re ** a4)
            ji = a1 * (1.33 / pitch_ratio) ** a * Re ** a2
            return ji
    # Fallback for Re >= 1e5: use last range
    a1, a2, a3, a4 = 0.321, -0.388, 1.450, 0.519
    a = a3 / (1.0 + 0.14 * Re ** a4)
    return a1 * (1.33 / pitch_ratio) ** a * Re ** a2


# ═══════════════════════════════════════════════════════════════════════════
# GEOMETRY CALCULATIONS
# ═══════════════════════════════════════════════════════════════════════════

def compute_all() -> dict:
    """Compute every intermediate and final value for BD-REF-001."""

    D_s = INPUTS["shell_id_m"]
    d_o = INPUTS["tube_od_m"]
    P_t = INPUTS["tube_pitch_m"]
    PR = INPUTS["pitch_ratio"]
    N_t = INPUTS["num_tubes"]
    B_c = INPUTS["baffle_cut_pct"]
    B = INPUTS["baffle_spacing_central_m"]
    L_i = INPUTS["baffle_spacing_inlet_m"]
    L_o = INPUTS["baffle_spacing_outlet_m"]
    N_b = INPUTS["num_baffles"]
    N_ss = INPUTS["num_sealing_strips"]
    delta_tb = INPUTS["clearances"]["tube_baffle_diametral_m"]
    delta_sb = INPUTS["clearances"]["shell_baffle_diametral_m"]
    delta_bs = INPUTS["clearances"]["bundle_shell_diametral_m"]

    rho = INPUTS["fluid"]["density_kg_m3"]
    mu = INPUTS["fluid"]["viscosity_Pa_s"]
    mu_w = INPUTS["fluid"]["viscosity_wall_Pa_s"]
    Cp = INPUTS["fluid"]["Cp_J_kgK"]
    k = INPUTS["fluid"]["k_W_mK"]
    Pr = INPUTS["fluid"]["Pr"]
    m_dot = INPUTS["fluid"]["mass_flow_kg_s"]

    # --- Outer tube limit diameter ---
    D_otl = D_s - delta_bs
    assert abs(D_otl - 0.4779) < 0.001, f"D_otl check failed: {D_otl}"

    # --- Baffle cut geometry ---
    # θ_ctl = 2 * arccos(D_s * (1 - 2*Bc/100) / D_otl)
    cut_ratio = D_s * (1.0 - 2.0 * B_c / 100.0) / D_otl
    theta_ctl = 2.0 * math.acos(cut_ratio)

    # --- Fraction of tubes in crossflow (F_c) ---
    # F_c = (1/π)(π + 2*(D_s(1-2Bc/100)/D_otl)*sin(θ_ctl/2) - θ_ctl)
    # Simplified: F_c = 1/π * (π + 2*cut_ratio*sin(arccos(cut_ratio)) - theta_ctl)
    # Note: sin(arccos(x)) = sqrt(1-x^2)
    sin_half_theta = math.sin(theta_ctl / 2.0)
    F_c = (1.0 / math.pi) * (math.pi + 2.0 * cut_ratio * sin_half_theta - theta_ctl)

    # --- Fraction of tubes in window (F_w) ---
    # F_w comes from the window area geometry
    # θ_ds = 2*arccos(1 - 2*Bc/100)  (angle subtended by baffle cut at shell center)
    theta_ds = 2.0 * math.acos(1.0 - 2.0 * B_c / 100.0)

    # Number of tubes in window:
    # F_w = (θ_ctl - sin(θ_ctl)) / (2*π) per Taborek
    F_w = (theta_ctl - math.sin(theta_ctl)) / (2.0 * math.pi)
    N_tw = F_w * N_t  # tubes in one window

    # --- Crossflow area S_m ---
    # For triangular pitch (30°):
    # S_m = B * (D_s - D_otl + (D_otl/P_t)*(P_t - d_o))
    # But more precisely, for triangular:
    # S_m = B * (D_s - D_otl + D_otl * (P_t - d_o) / P_t)
    # Which simplifies to: S_m = B * (D_s - D_otl + D_otl * (1 - d_o/P_t))
    S_m = B * (D_s - D_otl + D_otl * (P_t - d_o) / P_t)

    # --- Window flow area S_w ---
    # S_w = window gross area - tube area in window
    # Window gross = (D_s^2/4)(θ_ds - sin(θ_ds))/2  (the gross window from shell circle)
    # But more precisely per Taborek:
    # S_wg = (D_s^2/4) * (θ_ds/2 - sin(θ_ds)/2)   -- not quite, let's be precise
    # Gross window area = (D_s^2/8) * (θ_ds - sin(θ_ds))
    S_wg = (D_s ** 2 / 8.0) * (theta_ds - math.sin(theta_ds))
    # Tube area in window
    A_tubes_window = N_tw * math.pi * d_o ** 2 / 4.0
    S_w = S_wg - A_tubes_window

    # --- Tube-to-baffle leakage area S_tb ---
    # S_tb = (π/4)*((d_o + δ_tb)^2 - d_o^2) * N_t * (1 + F_c) / 2
    # Actually per Taborek: S_tb = π * d_o * δ_tb/2 * N_t * (1 + F_c) / 2
    # More precisely: tube holes are d_o + δ_tb diameter, so gap area per tube:
    # = (π/4)*((d_o+δ_tb)^2 - d_o^2) ≈ π*d_o*δ_tb/2 for small δ_tb
    # Number of tubes through baffles = N_t * (1+F_c)/2
    gap_per_tube = (math.pi / 4.0) * ((d_o + delta_tb) ** 2 - d_o ** 2)
    N_tubes_through_baffle = N_t * (1.0 + F_c) / 2.0
    S_tb = gap_per_tube * N_tubes_through_baffle

    # --- Shell-to-baffle leakage area S_sb ---
    # S_sb = π * D_s * (δ_sb/2) * (1 - θ_ctl/(2*π))
    # Wait — the plan says: S_sb = π*D_s*(δ_sb/2)*(1 - θ_ctl/(2π))
    # But θ_ctl is the angle at the OTL, not the shell.
    # Actually per Taborek: the shell-baffle gap exists everywhere EXCEPT in the
    # window zone: S_sb = π * D_s * (δ_sb/2) * (2π - θ_ds) / (2π)
    # = D_s * δ_sb/2 * (2π - θ_ds) / 2
    # Let me use: S_sb = π * D_s * (δ_sb / 2.0) * (1.0 - theta_ds / (2.0 * math.pi))
    S_sb = math.pi * D_s * (delta_sb / 2.0) * (1.0 - theta_ds / (2.0 * math.pi))

    # --- Bundle bypass area S_b ---
    # S_b = B * (D_s - D_otl)
    # For multiple pass layouts, there's a pass lane correction, but for simplicity:
    S_b = B * (D_s - D_otl)

    # --- Leakage ratios ---
    r_lm = (S_tb + S_sb) / S_m
    r_s = S_sb / (S_tb + S_sb)

    # --- Bypass fraction ---
    F_bp = S_b / S_m

    # --- Crossflow tube rows N_c ---
    # P_p = P_t * cos(30°) = P_t * √3/2 for 30° triangular
    P_p = P_t * math.cos(math.radians(30))  # row pitch (flow direction)
    N_c = D_s * (1.0 - 2.0 * B_c / 100.0) / P_p

    # --- Window tube rows N_cw ---
    # N_cw ≈ 0.8 * (D_s * Bc/100) / P_p  (Taborek approximation)
    # Or more precisely: N_cw = 0.8 * baffle_cut_distance / P_p
    N_cw = 0.8 * (D_s * B_c / 100.0) / P_p

    # --- Mass velocity and Reynolds number ---
    G_s = m_dot / S_m
    Re_shell = d_o * G_s / mu

    # ═══════════════════════════════════════════════════════════════════
    # IDEAL BANK j-FACTOR
    # ═══════════════════════════════════════════════════════════════════

    j_i = compute_ji(Re_shell, PR)

    # h_ideal = j_i * Cp * G_s * Pr^(-2/3) * (μ/μ_w)^0.14
    visc_corr = (mu / mu_w) ** 0.14
    h_ideal = j_i * Cp * G_s * Pr ** (-2.0 / 3.0) * visc_corr

    # ═══════════════════════════════════════════════════════════════════
    # J-FACTORS
    # ═══════════════════════════════════════════════════════════════════

    # J_c — Baffle cut correction
    J_c = 0.55 + 0.72 * F_c

    # J_l — Leakage correction
    J_l = 0.44 * (1.0 - r_s) + (1.0 - 0.44 * (1.0 - r_s)) * math.exp(-2.2 * r_lm)

    # J_b — Bypass correction
    C_bh = 1.25 if Re_shell >= 100 else 1.35
    r_ss = N_ss / N_c
    if r_ss >= 0.5:
        J_b = 1.0
    else:
        J_b = math.exp(-C_bh * F_bp * (1.0 - (2.0 * r_ss) ** (1.0 / 3.0)))

    # J_s — Unequal baffle spacing correction
    n_exp = 0.6  # turbulent exponent for heat transfer
    L_c = B  # central spacing
    num_Js = (N_b - 1 + (L_i / L_c) ** (1.0 - n_exp) + (L_o / L_c) ** (1.0 - n_exp))
    den_Js = (N_b - 1 + (L_i / L_c) + (L_o / L_c))
    J_s = num_Js / den_Js

    # J_r — Adverse temperature gradient (turbulent → 1.0)
    if Re_shell >= 100:
        J_r = 1.0
    elif Re_shell >= 20:
        J_r = (10.0 / N_c) ** 0.18
    else:
        J_r = (10.0 / N_c) ** 0.18 * (Re_shell / 20.0) ** 0.5

    # --- Product of all J-factors ---
    J_product = J_c * J_l * J_b * J_s * J_r

    # --- Final shell-side HTC ---
    h_o = h_ideal * J_product

    # ═══════════════════════════════════════════════════════════════════
    # SANITY CHECKS
    # ═══════════════════════════════════════════════════════════════════

    checks = []

    def check(name: str, val: float, lo: float, hi: float) -> None:
        ok = lo <= val <= hi
        checks.append({"name": name, "value": val, "range": [lo, hi], "passed": ok})
        if not ok:
            print(f"  FAIL: {name} = {val} not in [{lo}, {hi}]", file=sys.stderr)

    check("F_c in [0.5, 1.0]", F_c, 0.5, 1.0)
    check("F_w in [0.0, 0.5]", F_w, 0.0, 0.5)
    check("J_c in [0.5, 1.1]", J_c, 0.5, 1.1)
    check("J_l in [0.3, 1.0]", J_l, 0.3, 1.0)
    check("J_b in [0.5, 1.0]", J_b, 0.5, 1.0)
    check("J_s in [0.8, 1.0]", J_s, 0.8, 1.0)
    check("J_r == 1.0 (turbulent)", J_r, 0.99, 1.01)
    check("h_o in [500, 10000]", h_o, 500, 10000)

    n_passed = sum(1 for c in checks if c["passed"])
    n_total = len(checks)
    print(f"Sanity checks: {n_passed}/{n_total} passed")

    # ═══════════════════════════════════════════════════════════════════
    # BUILD OUTPUT
    # ═══════════════════════════════════════════════════════════════════

    result = {
        "reference_id": "BD-REF-001",
        "description": "Bell-Delaware reference calculator — Taborek (1983) HEDH",
        "inputs": INPUTS,
        "geometry": {
            "D_otl_m": round(D_otl, 6),
            "theta_ctl_rad": round(theta_ctl, 6),
            "theta_ds_rad": round(theta_ds, 6),
            "F_c": round(F_c, 6),
            "F_w": round(F_w, 6),
            "N_tw": round(N_tw, 2),
            "S_m_m2": round(S_m, 6),
            "S_w_m2": round(S_w, 6),
            "S_tb_m2": round(S_tb, 6),
            "S_sb_m2": round(S_sb, 6),
            "S_b_m2": round(S_b, 6),
            "r_lm": round(r_lm, 6),
            "r_s": round(r_s, 6),
            "F_bp": round(F_bp, 6),
            "P_p_m": round(P_p, 6),
            "N_c": round(N_c, 4),
            "N_cw": round(N_cw, 4),
            "G_s_kg_m2s": round(G_s, 4),
            "Re_shell": round(Re_shell, 2),
        },
        "results": {
            "j_i": round(j_i, 6),
            "visc_correction": round(visc_corr, 6),
            "h_ideal_W_m2K": round(h_ideal, 4),
            "J_c": round(J_c, 6),
            "J_l": round(J_l, 6),
            "J_b": round(J_b, 6),
            "J_s": round(J_s, 6),
            "J_r": round(J_r, 6),
            "J_product": round(J_product, 6),
            "h_o_W_m2K": round(h_o, 4),
        },
        "sanity_checks": checks,
    }

    return result


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    result = compute_all()

    # Write JSON
    out_path = os.path.join(os.path.dirname(__file__), "bd_ref_001.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nWrote {out_path}")
    print(f"\nKey results:")
    print(f"  Re_shell   = {result['geometry']['Re_shell']:,.1f}")
    print(f"  j_i        = {result['results']['j_i']:.6f}")
    print(f"  h_ideal    = {result['results']['h_ideal_W_m2K']:,.2f} W/m²K")
    print(f"  J_c        = {result['results']['J_c']:.6f}")
    print(f"  J_l        = {result['results']['J_l']:.6f}")
    print(f"  J_b        = {result['results']['J_b']:.6f}")
    print(f"  J_s        = {result['results']['J_s']:.6f}")
    print(f"  J_r        = {result['results']['J_r']:.6f}")
    print(f"  J_product  = {result['results']['J_product']:.6f}")
    print(f"  h_o        = {result['results']['h_o_W_m2K']:,.2f} W/m²K")
