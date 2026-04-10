"""Tests for ST-1 & ST-2 — get_allowable_stress() and get_thermal_expansion().

Validates data against ASME BPVC Section II Part D Tables 1A/1B and TE-1–TE-6.
"""

from __future__ import annotations

import pytest

from hx_engine.app.data.material_properties import (
    get_allowable_stress,
    get_thermal_expansion,
)

ALL_MATERIALS = [
    "carbon_steel", "stainless_304", "stainless_316",
    "copper", "admiralty_brass", "titanium",
    "inconel_600", "monel_400", "duplex_2205", "sa516_gr70",
]


# ===================================================================
# ST-1: Allowable Stress
# ===================================================================


class TestAllowableStress:
    """T1.1–T1.7"""

    def test_carbon_steel_100C(self):
        """T1.1: CS at 100°C ≈ 118 MPa."""
        S = get_allowable_stress("carbon_steel", 100.0)
        assert abs(S / 1e6 - 118.0) < 1.0

    def test_stainless_304_interpolation(self):
        """T1.2: 304 SS at 370°C — between 350 and 400 neighbors."""
        S_350 = get_allowable_stress("stainless_304", 350.0)
        S_400 = get_allowable_stress("stainless_304", 400.0)
        S_370 = get_allowable_stress("stainless_304", 370.0)
        assert S_400 < S_370 < S_350

    def test_clamp_below_min(self):
        """T1.3: Temperature below table range clamps to lowest."""
        S_at_0 = get_allowable_stress("carbon_steel", 0.0)
        S_at_40 = get_allowable_stress("carbon_steel", 40.0)
        assert S_at_0 == S_at_40

    def test_clamp_above_max(self):
        """T1.4: Temperature above table range clamps to highest."""
        S_at_900 = get_allowable_stress("stainless_304", 900.0)
        S_at_815 = get_allowable_stress("stainless_304", 815.0)
        assert S_at_900 == S_at_815

    def test_unknown_material_raises(self):
        """T1.5: Unknown material raises KeyError."""
        with pytest.raises(KeyError):
            get_allowable_stress("unobtanium", 100.0)

    def test_all_materials_positive_at_25C(self):
        """T1.6: All 10 materials return positive stress."""
        for mat in ALL_MATERIALS:
            S = get_allowable_stress(mat, 25.0)
            assert S > 0, f"{mat} returned S={S}"

    def test_stress_decreases_with_temperature(self):
        """T1.7: Stress decreases with temperature (general trend)."""
        for mat in ALL_MATERIALS:
            S_100 = get_allowable_stress(mat, 100.0)
            S_high = get_allowable_stress(mat, 400.0)
            # copper/brass max temp is ~205, use appropriate high temp
            if mat in ("copper", "admiralty_brass"):
                S_high = get_allowable_stress(mat, 200.0)
            elif mat in ("titanium", "duplex_2205"):
                S_high = get_allowable_stress(mat, 300.0)
            assert S_high <= S_100, f"{mat}: S(high)={S_high} > S(100)={S_100}"


# ===================================================================
# ST-2: Thermal Expansion
# ===================================================================


class TestThermalExpansion:
    """T2.1–T2.7"""

    def test_carbon_steel_100C(self):
        """T2.1: CS at 100°C ≈ 12.0e-6 1/°C."""
        alpha = get_thermal_expansion("carbon_steel", 100.0)
        assert abs(alpha - 12.0e-6) < 0.5e-6

    def test_stainless_304_interpolation(self):
        """T2.2: 304 SS at 200°C — between 100 and 300°C values."""
        a_100 = get_thermal_expansion("stainless_304", 100.0)
        a_300 = get_thermal_expansion("stainless_304", 300.0)
        a_200 = get_thermal_expansion("stainless_304", 200.0)
        assert a_100 < a_200 < a_300

    def test_returns_dimensionless(self):
        """T2.3: Returns 1/°C (≈ 12e-6), not µm/m·°C (≈ 12.0)."""
        alpha = get_thermal_expansion("carbon_steel", 100.0)
        assert alpha < 1e-3  # must be dimensionless, not µm/m·°C

    def test_expansion_increases_with_temperature(self):
        """T2.4: α(300°C) > α(100°C) for materials with wide temp range."""
        for mat in ["carbon_steel", "stainless_304", "stainless_316",
                     "inconel_600", "monel_400"]:
            a_100 = get_thermal_expansion(mat, 100.0)
            a_300 = get_thermal_expansion(mat, 300.0)
            assert a_300 > a_100, f"{mat}: α(300)={a_300} ≤ α(100)={a_100}"

    def test_stainless_greater_than_cs(self):
        """T2.5: 304 SS has higher expansion than CS at same temp."""
        a_cs = get_thermal_expansion("carbon_steel", 200.0)
        a_304 = get_thermal_expansion("stainless_304", 200.0)
        assert a_304 > a_cs

    def test_titanium_lowest(self):
        """T2.6: Titanium has lowest expansion of all tube materials."""
        a_ti = get_thermal_expansion("titanium", 100.0)
        for mat in ALL_MATERIALS:
            if mat in ("sa516_gr70",):  # shell material, skip
                continue
            a_mat = get_thermal_expansion(mat, 100.0)
            assert a_ti <= a_mat, f"Ti α={a_ti} > {mat} α={a_mat}"

    def test_unknown_material_raises(self):
        """T2.7: Unknown material raises KeyError."""
        with pytest.raises(KeyError):
            get_thermal_expansion("unobtanium", 100.0)
