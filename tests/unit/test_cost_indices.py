"""Tests for hx_engine.app.data.cost_indices — CEPCI + Turton constants + cost ratios."""

from __future__ import annotations

import pytest
from datetime import date

from hx_engine.app.data.cost_indices import (
    B1, B2,
    CEPCI_INDEX,
    COST_PER_M2_DEFAULT_RANGE,
    COST_PER_M2_RANGES,
    MATERIAL_COST_RATIOS,
    TURTON_K_CONSTANTS,
    TURTON_MATERIAL_FACTORS,
    get_area_range,
    get_cepci_ratio,
    get_cepci_staleness_days,
    get_cost_per_m2_range,
    get_k_constants,
    get_material_factor,
    get_turton_row,
)


# ─── T1.1: CEPCI ratio ──────────────────────────────────────────────

def test_cepci_ratio_value():
    """T1.1: get_cepci_ratio() returns 816/397 ≈ 2.0554."""
    expected = 816.0 / 397.0
    assert abs(get_cepci_ratio() - expected) < 0.001


# ─── T1.2: CEPCI staleness ──────────────────────────────────────────

def test_cepci_staleness_days_non_negative():
    """T1.2: get_cepci_staleness_days() returns a non-negative integer."""
    result = get_cepci_staleness_days()
    assert isinstance(result, int)
    assert result >= 0


# ─── T1.3–T1.7: TEMA → Turton row mapping ───────────────────────────

def test_turton_row_bem():
    """T1.3: BEM → fixed_tube."""
    assert get_turton_row("BEM") == "fixed_tube"


def test_turton_row_aes():
    """T1.4: AES → floating_head."""
    assert get_turton_row("AES") == "floating_head"


def test_turton_row_aeu():
    """T1.5: AEU → u_tube."""
    assert get_turton_row("AEU") == "u_tube"


def test_turton_row_ael():
    """T1.6: AEL → fixed_tube (L maps to fixed)."""
    assert get_turton_row("AEL") == "fixed_tube"


def test_turton_row_aew():
    """T1.7: AEW → floating_head (W maps to floating)."""
    assert get_turton_row("AEW") == "floating_head"


def test_turton_row_aep():
    """Extra: AEP → floating_head."""
    assert get_turton_row("AEP") == "floating_head"


# ─── T1.8: Unknown TEMA type ────────────────────────────────────────

def test_turton_row_unknown_raises():
    """T1.8: get_turton_row('XYZ') raises KeyError."""
    with pytest.raises(KeyError):
        get_turton_row("XYZ")


def test_turton_row_short_code_raises():
    """Extra: get_turton_row with <3 letters raises KeyError."""
    with pytest.raises(KeyError):
        get_turton_row("BE")


# ─── T1.9–T1.10: K-constants ────────────────────────────────────────

def test_k_constants_fixed_tube():
    """T1.9: K-constants for fixed_tube match Turton Table A.1."""
    k1, k2, k3 = get_k_constants("fixed_tube")
    assert k1 == pytest.approx(4.3247)
    assert k2 == pytest.approx(-0.3030)
    assert k3 == pytest.approx(0.1634)


def test_k_constants_floating_head():
    """T1.10: K-constants for floating_head match Turton Table A.1."""
    k1, k2, k3 = get_k_constants("floating_head")
    assert k1 == pytest.approx(4.8306)
    assert k2 == pytest.approx(-0.8509)
    assert k3 == pytest.approx(0.3187)


def test_k_constants_unknown_raises():
    """Extra: Unknown row raises KeyError."""
    with pytest.raises(KeyError):
        get_k_constants("unknown_row")


# ─── T1.11: Area ranges ─────────────────────────────────────────────

def test_area_range_kettle():
    """T1.11: Kettle reboiler has narrower range (10–100 m²)."""
    a_min, a_max = get_area_range("kettle_reboiler")
    assert a_min == 10.0
    assert a_max == 100.0


def test_area_range_fixed_tube():
    """Extra: Fixed tube has standard range (10–1000 m²)."""
    a_min, a_max = get_area_range("fixed_tube")
    assert a_min == 10.0
    assert a_max == 1000.0


# ─── T1.12–T1.15: Material factor (known combos) ────────────────────

def test_material_factor_cs_cs():
    """T1.12: CS/CS → (1.0, False)."""
    f_m, interp = get_material_factor("carbon_steel", "carbon_steel")
    assert f_m == pytest.approx(1.0)
    assert interp is False


def test_material_factor_cs_ss304():
    """T1.13: CS/SS304 → (1.7, False)."""
    f_m, interp = get_material_factor("carbon_steel", "stainless_304")
    assert f_m == pytest.approx(1.7)
    assert interp is False


def test_material_factor_ti_ti():
    """T1.14: Ti/Ti → (11.4, False)."""
    f_m, interp = get_material_factor("titanium", "titanium")
    assert f_m == pytest.approx(11.4)
    assert interp is False


def test_material_factor_sa516_ss316():
    """T1.15: sa516_gr70/SS316 → (1.9, False) — sa516 treated as CS."""
    f_m, interp = get_material_factor("sa516_gr70", "stainless_316")
    assert f_m == pytest.approx(1.9)
    assert interp is False


# ─── T1.16–T1.17: Material factor (interpolated) ────────────────────

def test_material_factor_duplex_ss316_interpolated():
    """T1.16: duplex/SS316 → interpolated, F_M > 1.0."""
    f_m, interp = get_material_factor("duplex_2205", "stainless_316")
    assert f_m > 1.0
    assert interp is True


def test_material_factor_ss316_ss316_interpolated():
    """T1.17: SS316/SS316 → not in Turton, interpolated."""
    f_m, interp = get_material_factor("stainless_316", "stainless_316")
    assert f_m > 1.0
    assert interp is True


# ─── T1.18–T1.20: Cost/m² ranges ────────────────────────────────────

def test_cost_per_m2_range_cs():
    """T1.18: CS range covers small-to-large HX."""
    lo, hi = get_cost_per_m2_range("carbon_steel")
    assert lo == 50.0
    assert hi == 15_000.0


def test_cost_per_m2_range_titanium():
    """T1.19: Ti range covers small-to-large HX."""
    lo, hi = get_cost_per_m2_range("titanium")
    assert lo == 400.0
    assert hi == 80_000.0


def test_cost_per_m2_range_unknown_material():
    """T1.20: Unknown material → default range (50, 6000)."""
    lo, hi = get_cost_per_m2_range("unknown_material")
    assert lo == COST_PER_M2_DEFAULT_RANGE[0]
    assert hi == COST_PER_M2_DEFAULT_RANGE[1]


# ─── T1.21–T1.22: All materials present ─────────────────────────────

_EXPECTED_MATERIALS = {
    "carbon_steel", "sa516_gr70", "copper", "admiralty_brass",
    "stainless_304", "stainless_316", "monel_400", "inconel_600",
    "titanium", "duplex_2205",
}


def test_all_materials_in_cost_ratios():
    """T1.21: All 10 materials present in MATERIAL_COST_RATIOS."""
    for mat in _EXPECTED_MATERIALS:
        assert mat in MATERIAL_COST_RATIOS, f"{mat} missing from MATERIAL_COST_RATIOS"


def test_all_materials_in_cost_per_m2_ranges():
    """T1.22: All 10 materials present in COST_PER_M2_RANGES."""
    for mat in _EXPECTED_MATERIALS:
        assert mat in COST_PER_M2_RANGES, f"{mat} missing from COST_PER_M2_RANGES"


# ─── T1.23: CEPCI base value ────────────────────────────────────────

def test_cepci_base_value():
    """T1.23: CEPCI_INDEX base_value is 397.0."""
    assert CEPCI_INDEX["base_value"] == 397.0


# ─── Extra: bare module constants ────────────────────────────────────

def test_bare_module_constants():
    """B1 = 1.63, B2 = 1.66."""
    assert B1 == pytest.approx(1.63)
    assert B2 == pytest.approx(1.66)
