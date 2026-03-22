"""Tests for Piece 1: _compute_mean_temp() — arithmetic mean temperature."""

from __future__ import annotations

import pytest

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.steps.step_03_fluid_props import Step03FluidProperties


class TestComputeMeanTemp:
    """Five tests guarding T_mean = (T_in + T_out) / 2 correctness."""

    def test_symmetric_hot_side(self):
        """Hot side 150→90°C → mean = 120°C (arithmetic midpoint)."""
        T_mean = Step03FluidProperties._compute_mean_temp(150.0, 90.0)
        assert T_mean == pytest.approx(120.0)

    def test_symmetric_cold_side(self):
        """Cold side 30→60°C → mean = 45°C (same formula both sides)."""
        T_mean = Step03FluidProperties._compute_mean_temp(30.0, 60.0)
        assert T_mean == pytest.approx(45.0)

    def test_identical_temps(self):
        """ΔT = 0 (degenerate case): 80→80°C → mean = 80°C."""
        T_mean = Step03FluidProperties._compute_mean_temp(80.0, 80.0)
        assert T_mean == pytest.approx(80.0)

    def test_missing_T_in_raises(self):
        """T_in is None → CalculationError (can't compute without both temps)."""
        with pytest.raises(CalculationError, match="T_in is missing") as exc_info:
            Step03FluidProperties._compute_mean_temp(None, 90.0)
        assert exc_info.value.step_id == 3

    def test_missing_T_out_raises(self):
        """T_out is None → CalculationError (same guard)."""
        with pytest.raises(CalculationError, match="T_out is missing") as exc_info:
            Step03FluidProperties._compute_mean_temp(150.0, None)
        assert exc_info.value.step_id == 3
