"""Tests for ST-7 — Step 14 hard validation rules."""

from __future__ import annotations

import pytest

from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_14_rules import (
    _rule_expansion_within_tolerance,
    _rule_mechanical_details_present,
    _rule_shell_t_min_positive,
    _rule_tube_external_adequate,
    _rule_tube_internal_adequate,
    _rule_tube_thickness_present,
    _rule_shell_thickness_present,
)


def _make_result(**overrides) -> StepResult:
    """Build a valid Step 14 StepResult with all expected outputs."""
    details = {
        "design_pressure_tube_Pa": 1.175e6,
        "design_pressure_shell_Pa": 1.175e6,
        "tube": {
            "t_actual_mm": 2.108,
            "t_min_internal_mm": 0.08,
            "margin_internal_pct": 2535.0,
            "external_pressure": {
                "P_allowable_Pa": 17.31e6,
                "P_applied_Pa": 1e6,
                "adequate": True,
            },
        },
        "shell": {
            "t_min_internal_mm": 5.72,
            "recommended_schedule": 10,
        },
        "expansion": {
            "differential_mm": 2.0,
            "tolerance_mm": 3.0,
            "tema_type": "BEM",
            "within_tolerance": True,
        },
        "limitations": [],
    }
    outputs = {
        "tube_thickness_ok": True,
        "shell_thickness_ok": True,
        "expansion_mm": 2.0,
        "mechanical_details": details,
        **overrides,
    }
    return StepResult(step_id=14, step_name="Mechanical Design Check", outputs=outputs)


class TestAllRulesPass:
    """T7.1"""

    def test_valid_result(self):
        result = _make_result()
        for rule_fn in (
            _rule_tube_thickness_present,
            _rule_shell_thickness_present,
            _rule_mechanical_details_present,
            _rule_tube_internal_adequate,
            _rule_tube_external_adequate,
            _rule_shell_t_min_positive,
            _rule_expansion_within_tolerance,
        ):
            passed, msg = rule_fn(14, result)
            assert passed, f"{rule_fn.__name__} failed: {msg}"


class TestPresenceRules:
    """T7.2, T7.7"""

    def test_missing_tube_thickness(self):
        """T7.2: R1 fails if tube_thickness_ok is None."""
        result = _make_result(tube_thickness_ok=None)
        passed, msg = _rule_tube_thickness_present(14, result)
        assert not passed

    def test_missing_mechanical_details(self):
        """T7.7: R3 fails if mechanical_details is None."""
        result = _make_result(mechanical_details=None)
        passed, msg = _rule_mechanical_details_present(14, result)
        assert not passed


class TestTubeRules:
    """T7.3, T7.4"""

    def test_tube_too_thin(self):
        """T7.3: R4 fails if t_actual < t_min_internal."""
        result = _make_result()
        result.outputs["mechanical_details"]["tube"]["t_actual_mm"] = 0.05
        result.outputs["mechanical_details"]["tube"]["t_min_internal_mm"] = 0.08
        passed, msg = _rule_tube_internal_adequate(14, result)
        assert not passed

    def test_tube_external_pressure_too_high(self):
        """T7.4: R5 fails if P_applied > P_allowable."""
        result = _make_result()
        ext = result.outputs["mechanical_details"]["tube"]["external_pressure"]
        ext["P_applied_Pa"] = 20e6
        ext["P_allowable_Pa"] = 17e6
        passed, msg = _rule_tube_external_adequate(14, result)
        assert not passed


class TestExpansionRules:
    """T7.5, T7.6"""

    def test_fixed_tubesheet_expansion_fails(self):
        """T7.5: R7 fails if expansion > tolerance for BEM."""
        result = _make_result()
        exp = result.outputs["mechanical_details"]["expansion"]
        exp["differential_mm"] = 5.0
        exp["tolerance_mm"] = 3.0
        exp["within_tolerance"] = False
        passed, msg = _rule_expansion_within_tolerance(14, result)
        assert not passed

    def test_floating_head_expansion_passes(self):
        """T7.6: R7 passes for AES even with large expansion (tolerance is None)."""
        result = _make_result()
        exp = result.outputs["mechanical_details"]["expansion"]
        exp["differential_mm"] = 10.0
        exp["tolerance_mm"] = None
        exp["tema_type"] = "AES"
        exp["within_tolerance"] = None  # floating head — not checked
        passed, msg = _rule_expansion_within_tolerance(14, result)
        assert passed
