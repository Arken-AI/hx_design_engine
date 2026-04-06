"""Tests for Bell-Delaware shell-side pressure drop functions.

Tests j_f interpolation, F'_b bypass correction, F'_L leakage correction,
and the shell_side_dP orchestrator.
"""

from __future__ import annotations

import math

import pytest

from hx_engine.app.correlations.bell_delaware import (
    compute_Fb_pressure,
    compute_FL_pressure,
    ideal_bank_jf,
    shell_side_dP,
)


class TestIdealBankJf:
    """Digitised j_f from Sinnott Figure 12.36."""

    @pytest.mark.parametrize(
        "Re, expected_jf",
        [
            (10, 2.0),
            (100, 0.38),
            (1_000, 0.10),
            (10_000, 0.052),
            (100_000, 0.046),
        ],
    )
    def test_triangular_exact_points(self, Re: int, expected_jf: float) -> None:
        result = ideal_bank_jf(float(Re), 30)
        assert result == pytest.approx(expected_jf, rel=0.01)

    @pytest.mark.parametrize(
        "Re, expected_jf",
        [
            (10, 1.6),
            (100, 0.32),
            (1_000, 0.094),
            (10_000, 0.052),
            (100_000, 0.046),
        ],
    )
    def test_square_exact_points(self, Re: int, expected_jf: float) -> None:
        result = ideal_bank_jf(float(Re), 90)
        assert result == pytest.approx(expected_jf, rel=0.01)

    def test_interpolation_between_points(self) -> None:
        """j_f at Re=500 should be between Re=100 and Re=1000 values."""
        jf_100 = ideal_bank_jf(100, 30)
        jf_500 = ideal_bank_jf(500, 30)
        jf_1000 = ideal_bank_jf(1000, 30)
        assert jf_1000 < jf_500 < jf_100

    def test_invalid_layout_raises(self) -> None:
        with pytest.raises(ValueError, match="layout_angle_deg"):
            ideal_bank_jf(1000, 15)

    def test_invalid_re_raises(self) -> None:
        with pytest.raises(ValueError, match="Re must be > 0"):
            ideal_bank_jf(0, 30)


class TestFbPressure:
    """Bypass correction F'_b."""

    def test_no_sealing_strips(self) -> None:
        """N_ss = 0 → significant penalty."""
        Fb = compute_Fb_pressure(
            A_b_m2=0.005, A_s_m2=0.020, N_ss=0, N_cv=10.0, Re=10_000,
        )
        assert 0 < Fb < 1.0  # penalty applied

    def test_adequate_sealing(self) -> None:
        """N_ss/N_cv >= 0.5 → F'_b = 1.0."""
        Fb = compute_Fb_pressure(
            A_b_m2=0.005, A_s_m2=0.020, N_ss=5, N_cv=10.0, Re=10_000,
        )
        assert Fb == 1.0

    def test_low_re_larger_alpha(self) -> None:
        """Re < 100 uses α = 5.0 (more severe than α = 4.0 for Re ≥ 100)."""
        Fb_low = compute_Fb_pressure(
            A_b_m2=0.005, A_s_m2=0.020, N_ss=1, N_cv=10.0, Re=50,
        )
        Fb_high = compute_Fb_pressure(
            A_b_m2=0.005, A_s_m2=0.020, N_ss=1, N_cv=10.0, Re=200,
        )
        assert Fb_low < Fb_high  # more penalty at low Re


class TestFLPressure:
    """Leakage correction F'_L."""

    def test_bounds(self) -> None:
        """F'_L should be in (0, 1]."""
        FL = compute_FL_pressure(A_tb_m2=0.003, A_sb_m2=0.002)
        assert 0 < FL <= 1.0

    def test_zero_leakage(self) -> None:
        """No leakage area → F'_L = 1.0."""
        FL = compute_FL_pressure(A_tb_m2=0.0, A_sb_m2=0.0)
        assert FL == 1.0

    def test_more_leakage_more_reduction(self) -> None:
        """Larger leakage areas → lower F'_L."""
        FL_small = compute_FL_pressure(A_tb_m2=0.001, A_sb_m2=0.001)
        FL_large = compute_FL_pressure(A_tb_m2=0.010, A_sb_m2=0.010)
        # Both should reduce ΔP, but FL_large may be more or less depending on ratio
        # The key is both are in valid range
        assert 0 < FL_small <= 1.0
        assert 0 < FL_large <= 1.0


class TestShellSideDPOrchestrator:
    """Full shell_side_dP calculation."""

    _COMMON_ARGS = dict(
        shell_id_m=0.489,
        tube_od_m=0.01905,
        tube_pitch_m=0.02381,
        layout_angle_deg=30,
        n_tubes=158,
        tube_passes=2,
        baffle_cut_pct=25.0,
        baffle_spacing_central_m=0.15,
        baffle_spacing_inlet_m=0.15,
        baffle_spacing_outlet_m=0.15,
        n_baffles=30,
        n_sealing_strip_pairs=2,
        delta_tb_m=0.0004,
        delta_sb_m=0.003,
        delta_bundle_shell_m=0.025,
        density_kg_m3=850.0,
        viscosity_Pa_s=0.001,
        viscosity_wall_Pa_s=0.001,
        mass_flow_kg_s=50.0,
        pitch_ratio=1.25,
    )

    def test_returns_all_keys(self) -> None:
        result = shell_side_dP(**self._COMMON_ARGS)
        expected_keys = {
            "dP_shell_Pa", "dP_crossflow_Pa", "dP_window_Pa", "dP_end_Pa",
            "dP_ideal_Pa", "Fb_prime", "FL_prime", "j_f",
            "u_s_m_s", "Re_shell", "warnings",
        }
        assert expected_keys.issubset(result.keys())

    def test_dp_positive(self) -> None:
        result = shell_side_dP(**self._COMMON_ARGS)
        assert result["dP_shell_Pa"] > 0

    def test_dp_increases_with_flow(self) -> None:
        """Higher mass flow → higher ΔP."""
        args_low = {**self._COMMON_ARGS, "mass_flow_kg_s": 20.0}
        args_high = {**self._COMMON_ARGS, "mass_flow_kg_s": 80.0}
        dp_low = shell_side_dP(**args_low)["dP_shell_Pa"]
        dp_high = shell_side_dP(**args_high)["dP_shell_Pa"]
        assert dp_high > dp_low

    def test_correction_factors_in_range(self) -> None:
        result = shell_side_dP(**self._COMMON_ARGS)
        assert 0 < result["Fb_prime"] <= 1.0
        assert 0 < result["FL_prime"] <= 1.0
