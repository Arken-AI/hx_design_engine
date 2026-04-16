"""Tests for Piece 3: StepProtocol + BaseStep."""

import logging
from unittest.mock import patch

import pytest

from hx_engine.app.core.ai_engineer import AIEngineer
from hx_engine.app.core.validation_rules import ValidationResult
from hx_engine.app.models.design_state import DesignState
from hx_engine.app.models.step_result import (
    AICorrection,
    AIDecisionEnum,
    AIModeEnum,
    AIReview,
    StepResult,
)
from hx_engine.app.steps.base import BaseStep, StepProtocol


# --- Concrete test helper ---

class DummyStep(BaseStep):
    step_id = 99
    step_name = "Dummy"
    ai_mode = AIModeEnum.NONE

    async def execute(self, state: DesignState) -> StepResult:
        return StepResult(step_id=self.step_id, step_name=self.step_name, outputs={"val": 42})


class FullAIStep(BaseStep):
    step_id = 88
    step_name = "FullAI"
    ai_mode = AIModeEnum.FULL

    async def execute(self, state: DesignState) -> StepResult:
        return StepResult(step_id=self.step_id, step_name=self.step_name, outputs={"val": 1})


class ConditionalStep(BaseStep):
    step_id = 77
    step_name = "Conditional"
    ai_mode = AIModeEnum.CONDITIONAL

    def _conditional_ai_trigger(self, state: DesignState) -> bool:
        return False

    async def execute(self, state: DesignState) -> StepResult:
        return StepResult(step_id=self.step_id, step_name=self.step_name)


class NoExecuteClass:
    step_id = 1
    step_name = "Broken"


# --- Protocol tests ---

class TestStepProtocol:
    def test_valid_step_is_protocol(self):
        step = DummyStep()
        assert isinstance(step, StepProtocol)

    def test_missing_execute_not_protocol(self):
        obj = NoExecuteClass()
        assert not isinstance(obj, StepProtocol)


# --- AI call decision tests ---

class TestShouldCallAI:
    def test_full_mode_returns_true(self):
        step = FullAIStep()
        state = DesignState()
        assert step._should_call_ai(state) is True

    def test_none_mode_returns_false(self):
        step = DummyStep()
        state = DesignState()
        assert step._should_call_ai(state) is False

    def test_conditional_no_trigger_returns_false(self):
        step = ConditionalStep()
        state = DesignState()
        assert step._should_call_ai(state) is False

    def test_conditional_skipped_in_convergence(self):
        step = ConditionalStep()
        state = DesignState(in_convergence_loop=True)
        assert step._should_call_ai(state) is False


# --- Review loop tests ---

class TestRunWithReviewLoop:
    async def test_proceed(self):
        step = FullAIStep()
        state = DesignState()
        ai = AIEngineer(stub_mode=True)  # stub: always PROCEED
        result = await step.run_with_review_loop(state, ai)
        assert result.ai_review.decision == AIDecisionEnum.PROCEED
        assert len(state.step_records) == 1

    async def test_warn_records_warning(self):
        class WarnAI:
            async def review(self, step, state, result, **kwargs):
                return AIReview(
                    decision=AIDecisionEnum.WARN,
                    confidence=0.9,
                    reasoning="Watch out",
                    ai_called=True,
                )

        step = FullAIStep()
        state = DesignState()
        result = await step.run_with_review_loop(state, WarnAI())
        assert "Watch out" in state.warnings

    async def test_low_confidence_escalates(self):
        class LowConfAI:
            async def review(self, step, state, result, **kwargs):
                return AIReview(
                    decision=AIDecisionEnum.PROCEED,
                    confidence=0.3,
                    ai_called=True,
                )

        step = FullAIStep()
        state = DesignState()
        result = await step.run_with_review_loop(state, LowConfAI())
        assert result.ai_review.decision == AIDecisionEnum.ESCALATE

    async def test_correct_then_proceed(self):
        call_count = 0

        class CorrectOnceAI:
            async def review(self, step, state, result, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return AIReview(
                        decision=AIDecisionEnum.CORRECT,
                        confidence=0.9,
                        corrections=[
                            AICorrection(field="val", old_value=1, new_value=2, reason="fix")
                        ],
                        ai_called=True,
                    )
                return AIReview(
                    decision=AIDecisionEnum.PROCEED,
                    confidence=0.95,
                    ai_called=True,
                )

        step = FullAIStep()
        state = DesignState()
        result = await step.run_with_review_loop(state, CorrectOnceAI())
        # After a successful correction (Layer 2 passes), the loop returns
        # immediately with CORRECT — no confirmation review call (§12.5).
        assert result.ai_review.decision == AIDecisionEnum.CORRECT
        assert len(result.ai_review.attempts) == 1
        assert result.ai_review.attempts[0].outcome == "success"

    async def test_3_corrections_then_escalate(self):
        class AlwaysCorrectAI:
            async def review(self, step, state, result, **kwargs):
                return AIReview(
                    decision=AIDecisionEnum.CORRECT,
                    confidence=0.9,
                    corrections=[
                        AICorrection(field="val", old_value=1, new_value=2, reason="fix")
                    ],
                    ai_called=True,
                )

        # Simulate Layer 2 always failing so the loop exhausts all attempts
        failed_vr = ValidationResult()
        failed_vr.passed = False
        failed_vr.errors = ["val must be < 0"]

        step = FullAIStep()
        state = DesignState()
        with patch("hx_engine.app.steps.base.validation_rules.check", return_value=failed_vr):
            result = await step.run_with_review_loop(state, AlwaysCorrectAI())

        assert result.ai_review.decision == AIDecisionEnum.ESCALATE
        assert len(result.ai_review.attempts) == 3
        assert all(a.outcome == "failed" for a in result.ai_review.attempts)

    async def test_no_ai_when_mode_none(self):
        step = DummyStep()
        state = DesignState()
        ai = AIEngineer(stub_mode=True)
        result = await step.run_with_review_loop(state, ai)
        assert result.ai_review is None  # AI not called


# --- WARN resolution tests ---

class TestWarnResolution:
    async def test_warn_with_corrections_auto_resolves(self):
        """WARN + corrections + Layer 2 passes → upgraded to CORRECT, warning recorded."""
        class WarnWithFixAI:
            async def review(self, step, state, result, **kwargs):
                return AIReview(
                    decision=AIDecisionEnum.WARN,
                    confidence=0.85,
                    reasoning="val looks off",
                    corrections=[
                        AICorrection(field="val", old_value=1, new_value=2, reason="fix")
                    ],
                    ai_called=True,
                )

        passed_vr = ValidationResult()
        passed_vr.passed = True
        passed_vr.errors = []

        step = FullAIStep()
        state = DesignState()
        with patch("hx_engine.app.steps.base.validation_rules.check", return_value=passed_vr):
            result = await step.run_with_review_loop(state, WarnWithFixAI())

        assert result.ai_review.decision == AIDecisionEnum.CORRECT
        assert any("[auto-resolved]" in w for w in state.warnings)

    async def test_warn_with_corrections_rollback_on_fail(self):
        """WARN + corrections + Layer 2 fails → rollback, pass through as informational WARN."""
        class WarnWithFixAI:
            async def review(self, step, state, result, **kwargs):
                return AIReview(
                    decision=AIDecisionEnum.WARN,
                    confidence=0.85,
                    reasoning="val looks off",
                    corrections=[
                        AICorrection(field="val", old_value=1, new_value=2, reason="fix")
                    ],
                    ai_called=True,
                )

        failed_vr = ValidationResult()
        failed_vr.passed = False
        failed_vr.errors = ["val out of range"]

        step = FullAIStep()
        state = DesignState()
        with patch("hx_engine.app.steps.base.validation_rules.check", return_value=failed_vr):
            result = await step.run_with_review_loop(state, WarnWithFixAI())

        # Downgraded to informational WARN — not CORRECT, not ESCALATE
        assert result.ai_review.decision == AIDecisionEnum.WARN
        assert "val looks off" in state.warnings
        # applied_corrections cleared on exit
        assert not state.applied_corrections

    async def test_warn_no_corrections_passes_through(self):
        """WARN with no corrections → informational, recorded immediately, no re-execute."""
        class InformationalWarnAI:
            async def review(self, step, state, result, **kwargs):
                return AIReview(
                    decision=AIDecisionEnum.WARN,
                    confidence=0.9,
                    reasoning="heads up: tight clearance",
                    corrections=[],
                    ai_called=True,
                )

        step = FullAIStep()
        state = DesignState()
        result = await step.run_with_review_loop(state, InformationalWarnAI())

        assert result.ai_review.decision == AIDecisionEnum.WARN
        assert "heads up: tight clearance" in state.warnings
        assert len(state.step_records) == 1


# -----------------------------------------------------------------------
# Confidence log line
# -----------------------------------------------------------------------

class TestRecordLogsConfidence:
    async def test_record_logs_ai_decision_and_confidence(self, caplog):
        """_record() must emit a structured log line when ai_called=True."""
        step = FullAIStep()
        state = DesignState()
        ai = AIEngineer(stub_mode=True)

        with caplog.at_level(logging.INFO, logger="hx_engine.app.steps.base"):
            await step.run_with_review_loop(state, ai)

        assert "confidence=" in caplog.text
        assert "decision=" in caplog.text
