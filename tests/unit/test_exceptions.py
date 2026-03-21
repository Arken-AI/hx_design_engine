"""Tests for Piece 4: Exceptions + ValidationRules framework."""

import pytest

from hx_engine.app.core.exceptions import CalculationError, StepHardFailure
from hx_engine.app.core.validation_rules import (
    ValidationResult,
    check,
    clear_rules,
    register_rule,
)
from hx_engine.app.models.step_result import StepResult


# ===== Exception tests =====

class TestCalculationError:
    def test_preserves_step_id(self):
        err = CalculationError(step_id=2, message="Q<0")
        assert err.step_id == 2
        assert "Q<0" in str(err)

    def test_preserves_cause(self):
        cause = ZeroDivisionError("div by zero")
        err = CalculationError(step_id=3, message="math fail", cause=cause)
        assert err.cause is cause


class TestStepHardFailure:
    def test_includes_errors(self):
        err = StepHardFailure(step_id=1, validation_errors=["err1", "err2"])
        assert err.step_id == 1
        assert len(err.validation_errors) == 2
        assert "err1" in str(err)
        assert "err2" in str(err)


# ===== ValidationRules tests =====

class TestValidationRules:
    def setup_method(self):
        clear_rules()

    def test_register_and_check_passing(self):
        def always_pass(step_id, result):
            return True, None

        register_rule(1, always_pass)
        result = StepResult(step_id=1, step_name="Test")
        vr = check(1, result)
        assert vr.passed is True
        assert vr.errors == []

    def test_register_and_check_failing(self):
        def always_fail(step_id, result):
            return False, "something wrong"

        register_rule(1, always_fail)
        result = StepResult(step_id=1, step_name="Test")
        vr = check(1, result)
        assert vr.passed is False
        assert "something wrong" in vr.errors

    def test_no_rules_passes(self):
        result = StepResult(step_id=99, step_name="Test")
        vr = check(99, result)
        assert vr.passed is True

    def test_multiple_rules_all_run(self):
        def rule_pass(step_id, result):
            return True, None

        def rule_fail(step_id, result):
            return False, "failure"

        register_rule(1, rule_pass)
        register_rule(1, rule_fail)
        result = StepResult(step_id=1, step_name="Test")
        vr = check(1, result)
        assert vr.passed is False
        assert len(vr.errors) == 1
