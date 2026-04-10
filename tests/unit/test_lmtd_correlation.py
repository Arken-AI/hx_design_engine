"""Tests for Piece 1 — correlations/lmtd.py pure math functions.

All tests verify physics invariants:
  - LMTD is between min(ΔT₁, ΔT₂) and max(ΔT₁, ΔT₂)
  - F ∈ [0, 1.0]
  - R > 0, 0 < P < 1 for valid cases
"""

from __future__ import annotations

import math

import pytest

from hx_engine.app.correlations.lmtd import (
    compute_f_factor,
    compute_lmtd,
    compute_P,
    compute_R,
)


# ===================================================================
# LMTD tests
# ===================================================================


class TestComputeLMTD:

    def test_benchmark_countercurrent(self):
        """Hand-calculated: 150/90 hot, 30/55 cold → LMTD ≈ 76.17°C."""
        lmtd = compute_lmtd(150, 90, 30, 55)
        assert lmtd == pytest.approx(76.17, rel=1e-3)

    def test_equal_delta_t(self):
        """ΔT₁ = ΔT₂ = 60°C → arithmetic mean fallback = 60.0."""
        # ΔT₁ = 120 - 60 = 60, ΔT₂ = 80 - 20 = 60
        lmtd = compute_lmtd(120, 80, 20, 60)
        assert lmtd == pytest.approx(60.0, abs=0.01)

    def test_temperature_cross_raises(self):
        """T_cold_out > T_hot_in → ΔT₁ < 0 → ValueError."""
        with pytest.raises(ValueError, match="Temperature cross"):
            compute_lmtd(100, 80, 30, 110)

    def test_negative_delta_t2_raises(self):
        """T_hot_out < T_cold_in → ΔT₂ < 0 → ValueError."""
        with pytest.raises(ValueError, match="Temperature cross"):
            compute_lmtd(100, 20, 30, 90)

    def test_very_small_valid(self):
        """Small but valid LMTD ≈ 3.47°C."""
        # ΔT₁ = 34 - 30 = 4, ΔT₂ = 33 - 30 = 3
        lmtd = compute_lmtd(34, 33, 30, 30 + 0.0)
        # Actually: ΔT₁ = 34 - 30 = 4, ΔT₂ = 33 - 30 = 3
        lmtd = compute_lmtd(34, 33, 30, 30)
        expected = (4 - 3) / math.log(4 / 3)
        assert lmtd == pytest.approx(expected, rel=0.005)

    def test_lmtd_between_min_max_delta_t(self):
        """LMTD always lies between min(ΔT₁, ΔT₂) and max(ΔT₁, ΔT₂)."""
        test_cases = [
            (150, 90, 30, 55),
            (200, 100, 40, 80),
            (120, 60, 25, 70),
            (80, 50, 20, 40),
        ]
        for Th_in, Th_out, Tc_in, Tc_out in test_cases:
            lmtd = compute_lmtd(Th_in, Th_out, Tc_in, Tc_out)
            dT1 = Th_in - Tc_out
            dT2 = Th_out - Tc_in
            assert min(dT1, dT2) <= lmtd <= max(dT1, dT2), (
                f"LMTD={lmtd} not between [{min(dT1,dT2)}, {max(dT1,dT2)}]"
            )


# ===================================================================
# R and P tests
# ===================================================================


class TestComputeR:

    def test_normal_computation(self):
        """R = (150-90)/(55-30) = 60/25 = 2.4."""
        R = compute_R(150, 90, 30, 55)
        assert R == pytest.approx(2.4, rel=1e-6)

    def test_zero_cold_dt_raises(self):
        """Zero cold-side ΔT raises ValueError."""
        with pytest.raises(ValueError, match="Cold side"):
            compute_R(150, 90, 30, 30)


class TestComputeP:

    def test_normal_computation(self):
        """P = (55-30)/(150-30) = 25/120 ≈ 0.2083."""
        P = compute_P(150, 90, 30, 55)
        assert P == pytest.approx(25 / 120, rel=1e-6)

    def test_P_always_between_0_and_1(self):
        """P ∈ (0, 1) for all valid temperature sets."""
        test_cases = [
            (150, 90, 30, 55),
            (200, 100, 40, 80),
            (120, 60, 25, 70),
        ]
        for Th_in, Th_out, Tc_in, Tc_out in test_cases:
            P = compute_P(Th_in, Th_out, Tc_in, Tc_out)
            assert 0 < P < 1, f"P={P} outside (0, 1)"


# ===================================================================
# F-factor tests
# ===================================================================


class TestComputeFfactor:

    def test_1_shell_normal(self):
        """For R=2.4, P=0.2083, 1 shell → F ≈ 0.955."""
        F = compute_f_factor(2.4, 25 / 120, n_shell_passes=1)
        assert F == pytest.approx(0.955, rel=0.01)

    def test_R_equals_1_no_crash(self):
        """R = 1.0 exactly should not crash (L'Hôpital limit)."""
        F = compute_f_factor(1.0, 0.3, n_shell_passes=1)
        assert 0.75 < F <= 1.0
        assert not math.isnan(F)

    def test_2_shells_improves(self):
        """F(2 shells) ≥ F(1 shell) for same R, P."""
        R, P = 2.0, 0.4
        F1 = compute_f_factor(R, P, n_shell_passes=1)
        F2 = compute_f_factor(R, P, n_shell_passes=2)
        assert F2 >= F1, f"F2={F2} < F1={F1}"

    def test_domain_violation_returns_0(self):
        """Configuration where ln argument goes negative → F = 0.0."""
        # Very high P for this R — infeasible
        F = compute_f_factor(2.0, 0.999, n_shell_passes=1)
        assert F == 0.0

    def test_clamped_to_0_1(self):
        """F is always in [0, 1] regardless of inputs."""
        edge_cases = [
            (0.5, 0.5, 1),
            (1.0, 0.5, 1),
            (3.0, 0.1, 1),
            (5.0, 0.05, 1),
            (1.5, 0.3, 2),
        ]
        for R, P, N in edge_cases:
            F = compute_f_factor(R, P, n_shell_passes=N)
            assert 0.0 <= F <= 1.0, f"F={F} out of range for R={R}, P={P}, N={N}"

    def test_invalid_P_returns_0(self):
        """P <= 0 or P >= 1 returns F = 0.0."""
        assert compute_f_factor(2.0, 0.0) == 0.0
        assert compute_f_factor(2.0, -0.1) == 0.0
        assert compute_f_factor(2.0, 1.0) == 0.0

    def test_invalid_R_returns_0(self):
        """R <= 0 returns F = 0.0."""
        assert compute_f_factor(0.0, 0.3) == 0.0
        assert compute_f_factor(-1.0, 0.3) == 0.0
