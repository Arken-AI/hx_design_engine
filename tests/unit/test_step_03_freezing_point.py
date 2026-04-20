"""Tests for Step 03 P2-19 — freezing / pour point check.

Covers the adapter wrapper, per-side helper, soft margin WARN, and the
``correctable=False`` ESCALATE rule.
"""

from __future__ import annotations

import pytest

from hx_engine.app.adapters.thermo_adapter import get_freezing_or_pour_point
from hx_engine.app.adapters.petroleum_correlations import pour_point_petroleum_K
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_03_fluid_props import (
    Step03FluidProperties,
    _FREEZE_MARGIN_WARN_K,
)
from hx_engine.app.steps.step_03_rules import _rule_above_freezing_point


# ---------------------------------------------------------------------------
# pour_point_petroleum_K — banded API-gravity heuristic
# ---------------------------------------------------------------------------


class TestPourPointBands:
    def test_very_heavy_crude_above_zero(self):
        assert pour_point_petroleum_K(8.0) > 273.15  # Athabasca-like

    def test_heavy_crude_above_zero(self):
        assert pour_point_petroleum_K(20.0) > 273.15

    def test_medium_crude_below_zero(self):
        assert pour_point_petroleum_K(33.0) < 273.15

    def test_light_crude_well_below_zero(self):
        assert pour_point_petroleum_K(40.0) < 273.15 - 25.0


# ---------------------------------------------------------------------------
# get_freezing_or_pour_point — backend dispatch
# ---------------------------------------------------------------------------


class TestGetFreezingOrPourPoint:
    def test_water_returns_triple_point(self):
        T, source = get_freezing_or_pour_point("water")
        assert T == pytest.approx(273.16, abs=0.01)
        assert source == "iapws"

    def test_seawater_alias_resolves_via_water(self):
        T, source = get_freezing_or_pour_point("seawater")
        assert T is not None
        assert source == "iapws"

    def test_petroleum_returns_pour_point(self):
        T, source = get_freezing_or_pour_point("crude oil")
        assert T is not None
        assert source == "petroleum-pour-point"

    def test_unknown_fluid_returns_unresolved(self):
        T, source = get_freezing_or_pour_point("definitely_not_a_real_fluid_xyz")
        assert T is None
        assert source == "unresolved"


# ---------------------------------------------------------------------------
# _check_freezing_points — per-side margin computation
# ---------------------------------------------------------------------------


class _FakeState:
    def __init__(
        self,
        hot_name, T_hot_in, T_hot_out,
        cold_name, T_cold_in, T_cold_out,
    ):
        self.hot_fluid_name = hot_name
        self.cold_fluid_name = cold_name
        self.T_hot_in_C = T_hot_in
        self.T_hot_out_C = T_hot_out
        self.T_cold_in_C = T_cold_in
        self.T_cold_out_C = T_cold_out
        self.P_hot_Pa = 101325.0
        self.P_cold_Pa = 101325.0


class TestCheckFreezingPoints:
    def test_water_well_above_freezing_emits_no_warning(self):
        warnings: list[str] = []
        state = _FakeState("water", 80, 60, "water", 30, 50)
        result = Step03FluidProperties._check_freezing_points(state, warnings)
        assert result["cold"]["margin_K"] > _FREEZE_MARGIN_WARN_K
        assert warnings == []

    def test_water_below_freezing_emits_layer2_warning(self):
        warnings: list[str] = []
        state = _FakeState("water", 80, 60, "water", 5, -2)
        result = Step03FluidProperties._check_freezing_points(state, warnings)
        assert result["cold"]["margin_K"] <= 0
        assert any("escalate" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# _rule_above_freezing_point
# ---------------------------------------------------------------------------


def _result(freezing_check):
    return StepResult(
        step_id=3,
        step_name="Fluid Properties",
        outputs={"freezing_check": freezing_check},
    )


class TestRuleAboveFreezingPoint:
    def test_passes_when_field_missing(self):
        passed, _ = _rule_above_freezing_point(
            3, StepResult(step_id=3, step_name="Fluid Properties", outputs={}),
        )
        assert passed is True

    def test_passes_when_unresolved_freeze(self):
        passed, _ = _rule_above_freezing_point(3, _result({
            "hot": {"T_min_K": 350.0, "T_freeze_K": None,
                    "freeze_property_source": "unresolved"},
            "cold": {"T_min_K": 300.0, "T_freeze_K": None,
                     "freeze_property_source": "unresolved"},
        }))
        # Unresolved → no rule failure (AI-trigger path handles it).
        assert passed is True

    def test_passes_when_above_freeze(self):
        passed, _ = _rule_above_freezing_point(3, _result({
            "cold": {"T_min_K": 278.15, "T_freeze_K": 273.16,
                     "freeze_property_source": "iapws"},
        }))
        assert passed is True

    def test_fails_when_min_at_or_below_freeze(self):
        passed, msg = _rule_above_freezing_point(3, _result({
            "cold": {"T_min_K": 271.15, "T_freeze_K": 273.16,
                     "freeze_property_source": "iapws"},
        }))
        assert passed is False
        assert "freezing" in msg.lower() or "pour" in msg.lower()
