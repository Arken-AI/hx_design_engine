"""Tests for Step 09 Layer 2 validation rules."""

from __future__ import annotations

import pytest

from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_09_rules import (
    _rule_cleanliness_factor_bounds,
    _rule_pct_sum,
    _rule_resistances_positive,
    _rule_u_clean_ge_dirty,
    _rule_u_clean_positive,
    _rule_u_dirty_positive,
)


def _make_result(**overrides) -> StepResult:
    """Build a passing Step 9 StepResult."""
    outputs = {
        "U_dirty_W_m2K": 350.0,
        "U_clean_W_m2K": 500.0,
        "cleanliness_factor": 0.70,
        "resistance_breakdown": {
            "shell_film": {"value_m2KW": 0.0005, "pct": 25.0},
            "tube_film": {"value_m2KW": 0.0004, "pct": 20.0},
            "shell_fouling": {"value_m2KW": 0.0005, "pct": 25.0},
            "tube_fouling": {"value_m2KW": 0.0004, "pct": 20.0},
            "wall": {"value_m2KW": 0.0002, "pct": 10.0},
            "total_1_over_U": 0.002,
        },
    }
    outputs.update(overrides)
    return StepResult(step_id=9, step_name="Overall U", outputs=outputs)


class TestRuleUDirtyPositive:

    def test_pass(self):
        r = _make_result(U_dirty_W_m2K=350.0)
        ok, msg = _rule_u_dirty_positive(9, r)
        assert ok is True

    def test_fail_negative(self):
        r = _make_result(U_dirty_W_m2K=-10.0)
        ok, msg = _rule_u_dirty_positive(9, r)
        assert ok is False
        assert "positive" in msg

    def test_fail_zero(self):
        r = _make_result(U_dirty_W_m2K=0.0)
        ok, msg = _rule_u_dirty_positive(9, r)
        assert ok is False

    def test_fail_missing(self):
        r = _make_result()
        r.outputs.pop("U_dirty_W_m2K", None)
        ok, msg = _rule_u_dirty_positive(9, r)
        assert ok is False


class TestRuleUCleanPositive:

    def test_pass(self):
        r = _make_result(U_clean_W_m2K=500.0)
        ok, msg = _rule_u_clean_positive(9, r)
        assert ok is True

    def test_fail(self):
        r = _make_result(U_clean_W_m2K=-5.0)
        ok, msg = _rule_u_clean_positive(9, r)
        assert ok is False


class TestRuleUCleanGeDirty:

    def test_pass(self):
        r = _make_result(U_clean_W_m2K=500.0, U_dirty_W_m2K=350.0)
        ok, msg = _rule_u_clean_ge_dirty(9, r)
        assert ok is True

    def test_pass_equal(self):
        """No fouling → U_clean == U_dirty."""
        r = _make_result(U_clean_W_m2K=350.0, U_dirty_W_m2K=350.0)
        ok, msg = _rule_u_clean_ge_dirty(9, r)
        assert ok is True

    def test_fail(self):
        r = _make_result(U_clean_W_m2K=300.0, U_dirty_W_m2K=350.0)
        ok, msg = _rule_u_clean_ge_dirty(9, r)
        assert ok is False
        assert "fouling" in msg


class TestRuleCFBounds:

    def test_pass_typical(self):
        r = _make_result(cleanliness_factor=0.80)
        ok, msg = _rule_cleanliness_factor_bounds(9, r)
        assert ok is True

    def test_pass_boundary_low(self):
        r = _make_result(cleanliness_factor=0.50)
        ok, msg = _rule_cleanliness_factor_bounds(9, r)
        assert ok is True

    def test_pass_boundary_high(self):
        r = _make_result(cleanliness_factor=1.0)
        ok, msg = _rule_cleanliness_factor_bounds(9, r)
        assert ok is True

    def test_fail_low(self):
        r = _make_result(cleanliness_factor=0.40)
        ok, msg = _rule_cleanliness_factor_bounds(9, r)
        assert ok is False

    def test_fail_high(self):
        r = _make_result(cleanliness_factor=1.05)
        ok, msg = _rule_cleanliness_factor_bounds(9, r)
        assert ok is False


class TestRuleResistancesPositive:

    def test_pass(self):
        r = _make_result()
        ok, msg = _rule_resistances_positive(9, r)
        assert ok is True

    def test_fail_negative(self):
        r = _make_result()
        r.outputs["resistance_breakdown"]["wall"]["value_m2KW"] = -0.001
        ok, msg = _rule_resistances_positive(9, r)
        assert ok is False
        assert "wall" in msg


class TestRulePctSum:

    def test_pass(self):
        r = _make_result()
        ok, msg = _rule_pct_sum(9, r)
        assert ok is True

    def test_fail(self):
        r = _make_result()
        r.outputs["resistance_breakdown"]["wall"]["pct"] = 0.0  # breaks sum
        ok, msg = _rule_pct_sum(9, r)
        assert ok is False
        assert "90" in msg  # should be 90% now
