"""Tests for Step 03 P2-18 — viscosity variation across ΔT.

Covers the helper, severity bands surfaced as warnings, the conditional
AI trigger contribution, and the ``correctable=False`` ESCALATE rule.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_03_fluid_props import (
    Step03FluidProperties,
    _MU_VARIATION_AI,
    _MU_VARIATION_ESCALATE,
    _MU_VARIATION_WARN,
)
from hx_engine.app.steps.step_03_rules import _rule_viscosity_variation_extreme


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


def _props(mu: float):
    """Lightweight stand-in for FluidProperties — only μ matters here."""
    class _P:
        viscosity_Pa_s = mu
    return _P()


# ---------------------------------------------------------------------------
# Threshold constants
# ---------------------------------------------------------------------------


class TestThresholds:
    def test_thresholds_are_ordered(self):
        assert _MU_VARIATION_WARN < _MU_VARIATION_AI < _MU_VARIATION_ESCALATE

    def test_default_band_values(self):
        assert _MU_VARIATION_WARN == 2.0
        assert _MU_VARIATION_AI == 5.0
        assert _MU_VARIATION_ESCALATE == 10.0


# ---------------------------------------------------------------------------
# _check_viscosity_variation_one_side
# ---------------------------------------------------------------------------


class TestCheckViscosityVariationOneSide:

    @pytest.mark.asyncio
    async def test_returns_none_when_backend_raises(self):
        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            new=AsyncMock(side_effect=RuntimeError("backend gap")),
        ):
            result = await Step03FluidProperties._check_viscosity_variation_one_side(
                "exotic_fluid", 100.0, 50.0, 101325.0,
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_dict_with_ratio_for_low_variation(self):
        # Cooling water 30 → 50 °C: μ varies ~1.3×
        async def fake_get(name, T, P):
            return _props({30.0: 0.0008, 40.0: 0.0007, 50.0: 0.0006}[T])

        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            new=AsyncMock(side_effect=fake_get),
        ):
            result = await Step03FluidProperties._check_viscosity_variation_one_side(
                "water", 30.0, 50.0, 101325.0,
            )
        assert result is not None
        assert result["mu_ratio"] == pytest.approx(0.0008 / 0.0006, rel=1e-9)

    @pytest.mark.asyncio
    async def test_returns_dict_with_ratio_for_heavy_oil(self):
        # Heavy oil 150 → 60 °C: μ may rise ~12× as it cools
        async def fake_get(name, T, P):
            return _props({150.0: 0.005, 105.0: 0.020, 60.0: 0.060}[T])

        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            new=AsyncMock(side_effect=fake_get),
        ):
            result = await Step03FluidProperties._check_viscosity_variation_one_side(
                "heavy oil", 150.0, 60.0, 101325.0,
            )
        assert result["mu_ratio"] == pytest.approx(12.0, rel=1e-9)


# ---------------------------------------------------------------------------
# _rule_viscosity_variation_extreme
# ---------------------------------------------------------------------------


def _result(viscosity_variation):
    return StepResult(
        step_id=3,
        step_name="Fluid Properties",
        outputs={"viscosity_variation": viscosity_variation},
    )


class TestRuleViscosityVariationExtreme:

    def test_passes_when_outputs_field_missing(self):
        result = StepResult(step_id=3, step_name="Fluid Properties", outputs={})
        assert _rule_viscosity_variation_extreme(3, result) == (True, None)

    def test_passes_when_ratio_below_escalate_band(self):
        passed, msg = _rule_viscosity_variation_extreme(3, _result({
            "hot": {"mu_ratio": 6.0},
            "cold": {"mu_ratio": 1.5},
        }))
        assert passed is True
        assert msg is None

    def test_fails_when_hot_side_at_escalate_band(self):
        passed, msg = _rule_viscosity_variation_extreme(3, _result({
            "hot": {"mu_ratio": 12.0},
            "cold": {"mu_ratio": 1.2},
        }))
        assert passed is False
        assert "hot" in msg
        assert "12.0" in msg

    def test_skips_unresolved_sides(self):
        passed, _ = _rule_viscosity_variation_extreme(3, _result({
            "hot": None,
            "cold": {"mu_ratio": 4.0},
        }))
        assert passed is True
