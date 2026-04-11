"""Tests for hx_engine.app.correlations.turton_cost — pure cost calculation functions."""

from __future__ import annotations

import math

import pytest

from hx_engine.app.correlations.turton_cost import (
    bare_module_cost,
    cepci_adjust,
    estimate_component_weights,
    interpolated_material_factor,
    pressure_factor,
    purchased_equipment_cost,
)
from hx_engine.app.data.cost_indices import (
    MATERIAL_COST_RATIOS,
    PRESSURE_FACTOR_CONSTANTS,
    TURTON_K_CONSTANTS,
)


# ─── Fixed-tube K-constants (for convenience) ───────────────────────
_K_FIXED = TURTON_K_CONSTANTS["fixed_tube"][:3]
_K_FLOATING = TURTON_K_CONSTANTS["floating_head"][:3]
_K_UTUBE = TURTON_K_CONSTANTS["u_tube"][:3]

_C_BOTH = PRESSURE_FACTOR_CONSTANTS["both_shell_and_tube"]
_C_TUBE = PRESSURE_FACTOR_CONSTANTS["tube_only"]


# ═══════════════════════════════════════════════════════════════════
# purchased_equipment_cost
# ═══════════════════════════════════════════════════════════════════

def test_pec_fixed_tube_100m2():
    """T2.1: Fixed tube @ 100 m² → reasonable range."""
    cp0 = purchased_equipment_cost(100.0, *_K_FIXED)
    assert 20_000 < cp0 < 40_000  # 2001 USD


def test_pec_floating_head_more_expensive():
    """T2.2: Floating head > fixed tube at same area."""
    cp0_fixed = purchased_equipment_cost(100.0, *_K_FIXED)
    cp0_float = purchased_equipment_cost(100.0, *_K_FLOATING)
    assert cp0_float > cp0_fixed


def test_pec_utube_reasonable():
    """T2.3: U-tube at 100 m² returns a reasonable positive value.

    Note: Turton K-constants produce different curve shapes; relative
    ordering of HX types varies with area.  We verify the correlation
    maths instead of assuming a fixed ordering.
    """
    cp0_utube = purchased_equipment_cost(100.0, *_K_UTUBE)
    # Must be positive and in a reasonable 2001 USD range
    assert 10_000 < cp0_utube < 100_000


def test_pec_monotonically_increasing():
    """T2.4: Cost increases with area."""
    cp0_100 = purchased_equipment_cost(100.0, *_K_FIXED)
    cp0_200 = purchased_equipment_cost(200.0, *_K_FIXED)
    assert cp0_200 > cp0_100


def test_pec_zero_area_raises():
    """T2.5: Zero area raises ValueError."""
    with pytest.raises(ValueError):
        purchased_equipment_cost(0.0, *_K_FIXED)


def test_pec_negative_area_raises():
    """T2.6: Negative area raises ValueError."""
    with pytest.raises(ValueError):
        purchased_equipment_cost(-1.0, *_K_FIXED)


# ═══════════════════════════════════════════════════════════════════
# pressure_factor
# ═══════════════════════════════════════════════════════════════════

def test_fp_below_threshold():
    """T2.7: P < 5 barg → F_P = 1.0."""
    assert pressure_factor(3.0, *_C_BOTH) == 1.0


def test_fp_atmospheric():
    """T2.8: P = 0 → F_P = 1.0."""
    assert pressure_factor(0.0, *_C_BOTH) == 1.0


def test_fp_both_at_100_barg():
    """T2.9: 'Both' at 100 barg → F_P ≈ 1.3–1.5."""
    fp = pressure_factor(100.0, *_C_BOTH)
    assert 1.1 < fp < 2.0


def test_fp_tube_only_less_than_both():
    """T2.10: 'Tube only' F_P < 'both' F_P at same pressure."""
    fp_both = pressure_factor(100.0, *_C_BOTH)
    fp_tube = pressure_factor(100.0, *_C_TUBE)
    assert fp_tube < fp_both


def test_fp_at_threshold():
    """T2.11: P = 5 barg → F_P ≈ 1.0 (just at boundary)."""
    fp = pressure_factor(5.0, *_C_BOTH)
    assert 0.9 < fp < 1.2  # Should be very close to 1.0


def test_fp_monotonically_increasing():
    """T2.12: F_P increases with pressure."""
    fp_10 = pressure_factor(10.0, *_C_BOTH)
    fp_50 = pressure_factor(50.0, *_C_BOTH)
    fp_100 = pressure_factor(100.0, *_C_BOTH)
    assert fp_100 > fp_50 > fp_10


def test_fp_negative_pressure_raises():
    """T2.13: Negative pressure raises ValueError."""
    with pytest.raises(ValueError):
        pressure_factor(-1.0, *_C_BOTH)


# ═══════════════════════════════════════════════════════════════════
# bare_module_cost
# ═══════════════════════════════════════════════════════════════════

def test_bmc_cs_atmospheric():
    """T2.14: CS/CS at atmospheric → C_BM ≈ Cp0 × 3.29."""
    cp0 = 25_000.0
    cbm = bare_module_cost(cp0, F_M=1.0, F_P=1.0)
    expected = cp0 * (1.63 + 1.66 * 1.0 * 1.0)  # ≈ 82,250
    assert cbm == pytest.approx(expected)


def test_bmc_cs_ss304_atmospheric():
    """T2.15: CS/SS304 at atmospheric → C_BM ≈ Cp0 × (1.63 + 1.66×1.7)."""
    cp0 = 25_000.0
    cbm = bare_module_cost(cp0, F_M=1.7, F_P=1.0)
    expected = cp0 * (1.63 + 1.66 * 1.7)
    assert cbm == pytest.approx(expected)


def test_bmc_increases_with_fm():
    """T2.16: C_BM increases with F_M: Ti > SS > CS."""
    cp0 = 25_000.0
    cbm_cs = bare_module_cost(cp0, F_M=1.0, F_P=1.0)
    cbm_ss = bare_module_cost(cp0, F_M=1.7, F_P=1.0)
    cbm_ti = bare_module_cost(cp0, F_M=4.7, F_P=1.0)
    assert cbm_ti > cbm_ss > cbm_cs


# ═══════════════════════════════════════════════════════════════════
# cepci_adjust
# ═══════════════════════════════════════════════════════════════════

def test_cepci_2001_to_2026():
    """T2.17: 2001→2026 adjustment."""
    cost_2001 = 82_250.0
    cost_2026 = cepci_adjust(cost_2001, 816.0, 397.0)
    expected = cost_2001 * (816.0 / 397.0)
    assert cost_2026 == pytest.approx(expected)


def test_cepci_same_year_identity():
    """T2.18: Same CEPCI → no change."""
    cost = 100_000.0
    result = cepci_adjust(cost, 397.0, 397.0)
    assert result == pytest.approx(cost)


# ═══════════════════════════════════════════════════════════════════
# interpolated_material_factor
# ═══════════════════════════════════════════════════════════════════

def test_imf_exotic_combo():
    """T2.19: duplex/duplex with geometry weights → F_M > 1.0."""
    fm = interpolated_material_factor(
        "duplex_2205", "duplex_2205",
        shell_weight_kg=5000.0,
        tube_weight_kg=3000.0,
        cost_ratios=MATERIAL_COST_RATIOS,
    )
    assert fm > 1.0


def test_imf_cs_cs_equals_one():
    """T2.20: CS/CS → F_M = 1.0."""
    fm = interpolated_material_factor(
        "carbon_steel", "carbon_steel",
        shell_weight_kg=5000.0,
        tube_weight_kg=3000.0,
        cost_ratios=MATERIAL_COST_RATIOS,
    )
    assert fm == pytest.approx(1.0)


# ═══════════════════════════════════════════════════════════════════
# estimate_component_weights
# ═══════════════════════════════════════════════════════════════════

def test_estimate_weights_serth_51():
    """T2.21: Approximate Serth Example 5.1 geometry → reasonable weights."""
    shell_w, tube_w = estimate_component_weights(
        shell_diameter_m=0.508,     # ~20" shell
        shell_length_m=4.877,       # ~16' tubes
        shell_thickness_m=0.008,    # ~8 mm wall
        shell_density_kg_m3=7750.0, # carbon steel
        tube_od_m=0.01905,          # 3/4" OD
        tube_id_m=0.01575,          # 16 BWG
        tube_length_m=4.877,
        n_tubes=324,
        tube_density_kg_m3=7750.0,
    )
    # Shell: order of 400-600 kg
    assert 200 < shell_w < 1000
    # Tubes: order of 800-1500 kg
    assert 400 < tube_w < 2000


# ═══════════════════════════════════════════════════════════════════
# Full pipeline sanity check
# ═══════════════════════════════════════════════════════════════════

def test_full_pipeline_sanity():
    """T2.22: Full pipeline: 100 m², fixed, CS/CS, 10 barg, CEPCI 2026."""
    # Step 1: Purchased cost
    cp0 = purchased_equipment_cost(100.0, *_K_FIXED)

    # Step 2: Pressure factor
    fp = pressure_factor(10.0, *_C_BOTH)

    # Step 3: Material factor (CS/CS)
    fm = 1.0

    # Step 4: Bare module cost
    cbm_2001 = bare_module_cost(cp0, fm, fp)

    # Step 5: CEPCI adjust
    cbm_2026 = cepci_adjust(cbm_2001, 816.0, 397.0)

    # Sanity: total cost should be in reasonable range for 100 m² CS HX
    assert 100_000 < cbm_2026 < 300_000
    # Cost per m² should be in CS range
    cost_per_m2 = cbm_2026 / 100.0
    assert 100 < cost_per_m2 < 3000
