"""Tests for hx_engine.app.steps.step_15_rules — hard validation rules."""

from __future__ import annotations

import pytest

from hx_engine.app.models.step_result import StepResult


# Import the rule functions directly for unit testing
from hx_engine.app.steps.step_15_rules import (
    _rule_cost_computed,
    _rule_cost_positive,
    _rule_breakdown_present,
    _rule_material_factor_positive,
    _rule_pressure_factor_valid,
    _rule_cost_per_m2_range,
)


def _make_result(**outputs) -> StepResult:
    """Build a minimal StepResult with given outputs."""
    return StepResult(step_id=15, step_name="Cost Estimate", outputs=outputs)


# ─── Valid baseline ──────────────────────────────────────────────────

_VALID_BREAKDOWN = {
    "F_M": 1.0,
    "F_P": 1.0,
    "cost_per_m2_usd": 500.0,
}

_VALID_OUTPUTS = {
    "cost_usd": 168_000.0,
    "cost_breakdown": _VALID_BREAKDOWN,
    "tube_material": "carbon_steel",
}


def test_all_rules_pass_valid():
    """T4.1: All rules pass with valid outputs."""
    result = _make_result(**_VALID_OUTPUTS)
    for rule in (
        _rule_cost_computed,
        _rule_cost_positive,
        _rule_breakdown_present,
        _rule_material_factor_positive,
        _rule_pressure_factor_valid,
        _rule_cost_per_m2_range,
    ):
        passed, msg = rule(15, result)
        assert passed, f"Rule {rule.__name__} unexpectedly failed: {msg}"


# ─── R1: cost_usd present ───────────────────────────────────────────

def test_r1_missing_cost_usd():
    """T4.2: Missing cost_usd → R1 fails."""
    result = _make_result(cost_breakdown=_VALID_BREAKDOWN)
    passed, msg = _rule_cost_computed(15, result)
    assert not passed
    assert "cost_usd" in msg


# ─── R2: cost_usd > 0 ───────────────────────────────────────────────

def test_r2_cost_zero():
    """T4.3: cost_usd = 0 → R2 fails."""
    result = _make_result(cost_usd=0.0)
    passed, msg = _rule_cost_positive(15, result)
    assert not passed


def test_r2_cost_negative():
    """T4.4: cost_usd = -1000 → R2 fails."""
    result = _make_result(cost_usd=-1000.0)
    passed, msg = _rule_cost_positive(15, result)
    assert not passed


# ─── R3: cost_breakdown present ──────────────────────────────────────

def test_r3_null_breakdown():
    """T4.5: Null cost_breakdown → R3 fails."""
    result = _make_result(cost_usd=168_000.0)
    passed, msg = _rule_breakdown_present(15, result)
    assert not passed
    assert "cost_breakdown" in msg


# ─── R4: F_M > 0 ────────────────────────────────────────────────────

def test_r4_fm_zero():
    """T4.6: F_M = 0 → R4 fails."""
    bd = {**_VALID_BREAKDOWN, "F_M": 0.0}
    result = _make_result(cost_usd=168_000.0, cost_breakdown=bd)
    passed, msg = _rule_material_factor_positive(15, result)
    assert not passed


# ─── R5: F_P >= 1.0 ─────────────────────────────────────────────────

def test_r5_fp_below_one():
    """T4.7: F_P = 0.5 → R5 fails."""
    bd = {**_VALID_BREAKDOWN, "F_P": 0.5}
    result = _make_result(cost_usd=168_000.0, cost_breakdown=bd)
    passed, msg = _rule_pressure_factor_valid(15, result)
    assert not passed


# ─── R6: cost/m² in range ───────────────────────────────────────────

def test_r6_below_cs_range():
    """T4.8: cost_per_m2 = 5 (below CS range of 50) → R6 fails."""
    bd = {**_VALID_BREAKDOWN, "cost_per_m2_usd": 5.0}
    result = _make_result(
        cost_usd=500.0, cost_breakdown=bd, tube_material="carbon_steel",
    )
    passed, msg = _rule_cost_per_m2_range(15, result)
    assert not passed


def test_r6_above_ti_range():
    """T4.9: cost_per_m2 = 100000 (above Ti range of 80000) → R6 fails."""
    bd = {**_VALID_BREAKDOWN, "cost_per_m2_usd": 100_000.0}
    result = _make_result(
        cost_usd=10_000_000.0, cost_breakdown=bd, tube_material="titanium",
    )
    passed, msg = _rule_cost_per_m2_range(15, result)
    assert not passed


def test_r6_passes_within_range():
    """T4.10: cost_per_m2 = 500 with CS tubes → R6 passes."""
    bd = {**_VALID_BREAKDOWN, "cost_per_m2_usd": 500.0}
    result = _make_result(
        cost_usd=50_000.0, cost_breakdown=bd, tube_material="carbon_steel",
    )
    passed, msg = _rule_cost_per_m2_range(15, result)
    assert passed


def test_r6_unknown_material_uses_default():
    """T4.11: Unknown tube material → uses default range (50–6000)."""
    bd = {**_VALID_BREAKDOWN, "cost_per_m2_usd": 200.0}
    result = _make_result(
        cost_usd=20_000.0, cost_breakdown=bd, tube_material="exotic_alloy",
    )
    passed, msg = _rule_cost_per_m2_range(15, result)
    assert passed
