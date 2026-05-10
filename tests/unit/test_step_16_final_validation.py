"""Unit tests for Step 16 — Final Validation & Confidence Score.

Tests the deterministic helper functions independently of the full step
execution. This complements test_step_16_integration.py (which tests the
full execute path) by locking in the score-formula behaviour at the unit level.
"""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import DesignState
from hx_engine.app.models.step_result import (
    AIDecisionEnum,
    StepRecord,
)
from hx_engine.app.steps.step_16_final_validation import (
    CONFIDENCE_WEIGHTS,
    Step16FinalValidation,
    _compute_ai_agreement_rate,
    _compute_confidence_score,
    _compute_geometry_convergence,
    _compute_validation_pass_rate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record(
    step_id: int = 1,
    ai_called: bool = False,
    ai_decision: AIDecisionEnum | None = None,
    validation_passed: bool = True,
) -> StepRecord:
    return StepRecord(
        step_id=step_id,
        step_name=f"Step {step_id}",
        ai_called=ai_called,
        ai_decision=ai_decision,
        validation_passed=validation_passed,
    )


# ---------------------------------------------------------------------------
# T16-U1 — _compute_geometry_convergence
# ---------------------------------------------------------------------------

class TestGeometryConvergenceScore:
    """T16-U1: Convergence quality scoring (Step 16 D5)."""

    def test_converged_at_5_returns_1_0(self):
        assert _compute_geometry_convergence(True, 5) == pytest.approx(1.0)

    def test_converged_at_10_returns_1_0(self):
        assert _compute_geometry_convergence(True, 10) == pytest.approx(1.0)

    def test_converged_at_15_returns_0_75(self):
        # Linear: 1.0 - 0.5 * (15 - 10) / 10 = 0.75
        assert _compute_geometry_convergence(True, 15) == pytest.approx(0.75)

    def test_converged_at_20_returns_0_5(self):
        # Linear floor: 1.0 - 0.5 * (20 - 10) / 10 = 0.5
        assert _compute_geometry_convergence(True, 20) == pytest.approx(0.5)

    def test_converged_beyond_20_returns_0_5(self):
        # Clamped to floor 0.5
        assert _compute_geometry_convergence(True, 25) == pytest.approx(0.5)

    def test_not_converged_returns_0_0(self):
        assert _compute_geometry_convergence(False, 5) == pytest.approx(0.0)

    def test_none_converged_returns_0_0(self):
        assert _compute_geometry_convergence(None, 5) == pytest.approx(0.0)

    def test_converged_none_iteration_returns_1_0(self):
        # converged=True but no iteration → assume clean
        assert _compute_geometry_convergence(True, None) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# T16-U2 — _compute_ai_agreement_rate
# ---------------------------------------------------------------------------

class TestAIAgreementRate:
    """T16-U2: AI agreement rate (Step 16 D7)."""

    def test_empty_records_returns_0_5(self):
        """No AI calls → neutral default 0.5."""
        assert _compute_ai_agreement_rate([]) == pytest.approx(0.5)

    def test_no_ai_called_returns_0_5(self):
        """Records where ai_called=False → neutral default."""
        records = [_record(i, ai_called=False) for i in range(1, 6)]
        assert _compute_ai_agreement_rate(records) == pytest.approx(0.5)

    def test_all_proceed_returns_1_0(self):
        records = [
            _record(i, ai_called=True, ai_decision=AIDecisionEnum.PROCEED)
            for i in range(1, 6)
        ]
        assert _compute_ai_agreement_rate(records) == pytest.approx(1.0)

    def test_three_proceed_one_correct_one_escalate_returns_0_6(self):
        """3 PROCEED, 1 CORRECT, 1 ESCALATE → 3/5 = 0.6."""
        records = [
            _record(1, ai_called=True, ai_decision=AIDecisionEnum.PROCEED),
            _record(2, ai_called=True, ai_decision=AIDecisionEnum.PROCEED),
            _record(3, ai_called=True, ai_decision=AIDecisionEnum.PROCEED),
            _record(4, ai_called=True, ai_decision=AIDecisionEnum.CORRECT),
            _record(5, ai_called=True, ai_decision=AIDecisionEnum.ESCALATE),
        ]
        assert _compute_ai_agreement_rate(records) == pytest.approx(0.6)

    def test_all_escalate_returns_0_0(self):
        records = [
            _record(i, ai_called=True, ai_decision=AIDecisionEnum.ESCALATE)
            for i in range(1, 4)
        ]
        assert _compute_ai_agreement_rate(records) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# T16-U3 — _compute_validation_pass_rate
# ---------------------------------------------------------------------------

class TestValidationPassRate:
    """T16-U3: First-attempt validation pass rate (Step 16 D4)."""

    def test_empty_records_returns_0_5(self):
        assert _compute_validation_pass_rate([]) == pytest.approx(0.5)

    def test_all_pass_no_ai_returns_1_0(self):
        records = [_record(i, ai_called=False, validation_passed=True) for i in range(1, 6)]
        assert _compute_validation_pass_rate(records) == pytest.approx(1.0)

    def test_ai_proceed_counts_as_first_attempt_pass(self):
        """Step passed validation and AI returned PROCEED → first attempt."""
        records = [
            _record(1, ai_called=True, ai_decision=AIDecisionEnum.PROCEED, validation_passed=True),
        ]
        assert _compute_validation_pass_rate(records) == pytest.approx(1.0)

    def test_ai_correct_counts_as_not_first_attempt(self):
        """AI returned CORRECT → AI had to intervene → not a clean first-attempt pass."""
        records = [
            _record(1, ai_called=True, ai_decision=AIDecisionEnum.CORRECT, validation_passed=True),
        ]
        rate = _compute_validation_pass_rate(records)
        assert rate == pytest.approx(0.0)

    def test_mixed_returns_correct_fraction(self):
        """4 clean passes out of 5 steps → 0.8."""
        records = [
            _record(1, ai_called=False, validation_passed=True),
            _record(2, ai_called=False, validation_passed=True),
            _record(3, ai_called=True, ai_decision=AIDecisionEnum.PROCEED, validation_passed=True),
            _record(4, ai_called=False, validation_passed=True),
            _record(5, ai_called=True, ai_decision=AIDecisionEnum.CORRECT, validation_passed=True),
        ]
        assert _compute_validation_pass_rate(records) == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# T16-U4 — _compute_confidence_score
# ---------------------------------------------------------------------------

class TestConfidenceScoreWeighting:
    """T16-U4: Weighted confidence score formula."""

    def test_weights_sum_to_one(self):
        total = sum(CONFIDENCE_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_all_ones_returns_1_0(self):
        breakdown = {k: 1.0 for k in CONFIDENCE_WEIGHTS}
        score = _compute_confidence_score(breakdown, CONFIDENCE_WEIGHTS)
        assert score == pytest.approx(1.0)

    def test_all_zeros_returns_0_0(self):
        breakdown = {k: 0.0 for k in CONFIDENCE_WEIGHTS}
        score = _compute_confidence_score(breakdown, CONFIDENCE_WEIGHTS)
        assert score == pytest.approx(0.0)

    def test_clamped_above_1(self):
        breakdown = {k: 2.0 for k in CONFIDENCE_WEIGHTS}
        score = _compute_confidence_score(breakdown, CONFIDENCE_WEIGHTS)
        assert score == pytest.approx(1.0)

    def test_clamped_below_0(self):
        breakdown = {k: -1.0 for k in CONFIDENCE_WEIGHTS}
        score = _compute_confidence_score(breakdown, CONFIDENCE_WEIGHTS)
        assert score == pytest.approx(0.0)

    def test_mixed_components(self):
        """Verify the weighted sum is computed correctly."""
        breakdown = {k: 0.0 for k in CONFIDENCE_WEIGHTS}
        # Set only the first component to 1.0 and check the contribution
        first_key = next(iter(CONFIDENCE_WEIGHTS))
        breakdown[first_key] = 1.0
        expected = CONFIDENCE_WEIGHTS[first_key]
        score = _compute_confidence_score(breakdown, CONFIDENCE_WEIGHTS)
        assert score == pytest.approx(expected)


# ---------------------------------------------------------------------------
# T16-U5 — Step16FinalValidation._conditional_ai_trigger
# ---------------------------------------------------------------------------

class TestFullModeAlwaysCallsAI:
    """T16-U5: FULL ai_mode → _conditional_ai_trigger always True (Step 16 D10)."""

    def test_always_returns_true(self):
        step = Step16FinalValidation()
        state = DesignState()
        # Should return True regardless of state
        assert step._conditional_ai_trigger(state) is True

    def test_true_when_convergence_is_none(self):
        step = Step16FinalValidation()
        state = DesignState(convergence_converged=None)
        assert step._conditional_ai_trigger(state) is True

    def test_true_when_confidence_score_already_set(self):
        step = Step16FinalValidation()
        state = DesignState(confidence_score=0.95)
        assert step._conditional_ai_trigger(state) is True
