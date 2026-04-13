"""Tests for ST-5 — ASME thickness calculations (UG-27, UG-28, expansion)."""

from __future__ import annotations

import pytest

from hx_engine.app.correlations.asme_thickness import (
    design_pressure,
    external_pressure_allowable,
    get_corrosion_allowance,
    shell_internal_pressure_thickness,
    thermal_expansion_differential,
    tube_internal_pressure_thickness,
)


class TestDesignPressure:
    """T5.1–T5.2"""

    def test_low_pressure(self):
        """T5.1: 1 MPa → max(1.1, 1.175) = 1.175 MPa."""
        P = design_pressure(1e6)
        assert abs(P - 1.175e6) < 100

    def test_high_pressure(self):
        """T5.2: 5 MPa → max(5.5, 5.175) = 5.5 MPa."""
        P = design_pressure(5e6)
        assert abs(P - 5.5e6) < 100

    def test_negative_raises(self):
        """T5.15: Negative pressure raises ValueError."""
        with pytest.raises(ValueError):
            design_pressure(-1e6)


class TestTubeInternalPressure:
    """T5.3"""

    def test_typical_tube(self):
        """T5.3: 19.05mm OD, 1 MPa, S=118 MPa → very thin wall."""
        t = tube_internal_pressure_thickness(1e6, 0.01905, 118e6)
        # t_min should be very small (tubes are overbuilt)
        assert 0 < t < 0.001  # less than 1 mm

    def test_zero_pressure(self):
        """T5.14: P=0 → t_min=0."""
        t = tube_internal_pressure_thickness(0, 0.01905, 118e6)
        assert t == 0.0

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            tube_internal_pressure_thickness(-1, 0.01905, 118e6)


class TestShellInternalPressure:
    """T5.4"""

    def test_typical_shell(self):
        """T5.4: NPS 20 shell (R≈254mm), 1 MPa, S=138 MPa → reasonable t_min."""
        t = shell_internal_pressure_thickness(1e6, 0.254, 138e6)
        assert 0.003 < t < 0.015  # 3–15 mm range including CA

    def test_zero_pressure(self):
        """Zero pressure → t_min = CA only."""
        CA = 0.003175
        t = shell_internal_pressure_thickness(0, 0.254, 138e6, CA_m=CA)
        assert abs(t - CA) < 1e-10


class TestExternalPressure:
    """T5.5–T5.8"""

    def test_typical_tube(self):
        """T5.5: Typical tube — P_allowable >> operating pressure."""
        result = external_pressure_allowable(
            0.01905, 0.00211, 0.127, "carbon_steel", 150,
        )
        assert result["P_allowable_Pa"] > 1e6  # > 1 MPa — tube won't buckle

    def test_shell_vacuum(self):
        """T5.6: Shell under vacuum — P_allowable in reasonable range."""
        result = external_pressure_allowable(
            0.610, 0.010, 4.877, "sa516_gr70", 150,
        )
        assert result["P_allowable_Pa"] > 0

    def test_result_structure(self):
        """Verify result dict has all required keys."""
        result = external_pressure_allowable(
            0.01905, 0.00211, 0.127, "carbon_steel", 150,
        )
        for key in ("D_o_t", "L_D_o", "factor_A", "is_elastic", "P_allowable_Pa", "E_Pa"):
            assert key in result


class TestThermalExpansion:
    """T5.9–T5.11"""

    def test_304_vs_cs(self):
        """T5.9: 304 SS tubes + CS shell, ΔT with L=4.877 m."""
        result = thermal_expansion_differential(
            "stainless_304", "carbon_steel", 150, 80, 4.877,
        )
        assert result["differential_mm"] > 0
        # 304 expands more → dL_tube > dL_shell
        assert result["dL_tube_mm"] > result["dL_shell_mm"]

    def test_zero_delta_t(self):
        """T5.10: Same temperature → zero expansion."""
        result = thermal_expansion_differential(
            "carbon_steel", "carbon_steel", 20, 20, 4.877,
        )
        assert result["differential_mm"] == pytest.approx(0, abs=0.01)

    def test_same_material(self):
        """T5.11: Same material, different temps → small differential."""
        result = thermal_expansion_differential(
            "carbon_steel", "carbon_steel", 100, 80, 4.877,
        )
        # Same material, small ΔT → small differential
        assert result["differential_mm"] < 2.0


class TestCorrosionAllowance:
    """T5.12–T5.13"""

    def test_carbon_steel(self):
        """T5.12: CS → 3.175 mm."""
        assert abs(get_corrosion_allowance("carbon_steel") - 0.003175) < 1e-6

    def test_titanium(self):
        """T5.13: Ti → 0."""
        assert get_corrosion_allowance("titanium") == 0.0

    def test_unknown_defaults_to_cs(self):
        """Unknown material defaults to CS corrosion allowance."""
        assert get_corrosion_allowance("unknown") == 0.003175
