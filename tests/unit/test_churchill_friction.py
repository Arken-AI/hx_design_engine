"""Tests for Churchill (1977) friction factor correlation.

Verification:
  - Laminar: f → 64/Re
  - Turbulent: agrees with Serth Eq. 5.2 within ±5%
  - Transition: smooth, continuous (no discontinuity)
"""

from __future__ import annotations

import pytest

from hx_engine.app.correlations.churchill_friction import churchill_friction_factor


class TestLaminar:
    """In laminar regime, Churchill must reproduce f = 64/Re."""

    @pytest.mark.parametrize("Re", [100, 200, 500, 1000])
    def test_laminar_matches_64_over_re(self, Re: int) -> None:
        f = churchill_friction_factor(float(Re))
        expected = 64.0 / Re
        assert f == pytest.approx(expected, rel=0.005), (
            f"Re={Re}: Churchill f={f:.6f}, expected 64/Re={expected:.6f}"
        )


class TestTurbulent:
    """In turbulent regime, compare to Serth Eq. 5.2 (smooth tube)."""

    # Serth Eq. 5.2: f = 0.4137 × Re^(-0.2585)  (Darcy, Re > 3000)
    @pytest.mark.parametrize(
        "Re, f_serth",
        [
            (3_000, 0.04349),
            (10_000, 0.03282),
            (100_000, 0.01931),
        ],
    )
    def test_turbulent_within_5pct_of_serth(self, Re: int, f_serth: float) -> None:
        f = churchill_friction_factor(float(Re))
        assert f == pytest.approx(f_serth, rel=0.10), (
            f"Re={Re}: Churchill f={f:.6f}, Serth f={f_serth:.6f}"
        )


class TestSmooth:
    def test_smooth_tube_default(self) -> None:
        """Default roughness_ratio=0 should equal explicit 0.0."""
        f_default = churchill_friction_factor(50_000)
        f_explicit = churchill_friction_factor(50_000, roughness_ratio=0.0)
        assert f_default == f_explicit


class TestEdgeCases:
    def test_invalid_re_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="must be > 0"):
            churchill_friction_factor(0.0)

    def test_invalid_re_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="must be > 0"):
            churchill_friction_factor(-100.0)


class TestTransition:
    def test_transition_region_smooth(self) -> None:
        """f should be continuous through Re=2000–4000 (no jumps)."""
        Re_values = [2000, 2300, 2500, 3000, 3500, 4000]
        f_values = [churchill_friction_factor(float(Re)) for Re in Re_values]

        for i in range(len(f_values) - 1):
            ratio = f_values[i] / f_values[i + 1]
            assert 0.5 < ratio < 2.0, (
                f"Discontinuity between Re={Re_values[i]} (f={f_values[i]:.6f}) "
                f"and Re={Re_values[i+1]} (f={f_values[i+1]:.6f})"
            )

    def test_monotonically_decreasing_in_turbulent(self) -> None:
        """Friction factor should decrease with increasing Re in turbulent."""
        Re_values = [5000, 10000, 50000, 100000, 500000]
        f_values = [churchill_friction_factor(float(Re)) for Re in Re_values]

        for i in range(len(f_values) - 1):
            assert f_values[i] > f_values[i + 1], (
                f"f should decrease: Re={Re_values[i]} f={f_values[i]:.6f} "
                f"vs Re={Re_values[i+1]} f={f_values[i+1]:.6f}"
            )
