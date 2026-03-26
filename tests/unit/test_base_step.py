"""Tests for Piece 3: StepProtocol + BaseStep."""

import pytest

from hx_engine.app.core.ai_engineer import AIEngineer
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
        ai = AIEngineer()  # stub: always PROCEED
        result = await step.run_with_review_loop(state, ai)
        assert result.ai_review.decision == AIDecisionEnum.PROCEED
        assert len(state.step_records) == 1

    async def test_warn_records_warning(self):
        class WarnAI:
            async def review(self, step, state, result):
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
            async def review(self, step, state, result):
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
            async def review(self, step, state, result):
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
        assert result.ai_review.decision == AIDecisionEnum.PROCEED

    async def test_3_corrections_then_escalate(self):
        class AlwaysCorrectAI:
            async def review(self, step, state, result):
                return AIReview(
                    decision=AIDecisionEnum.CORRECT,
                    confidence=0.9,
                    corrections=[
                        AICorrection(field="val", old_value=1, new_value=2, reason="fix")
                    ],
                    ai_called=True,
                )

        step = FullAIStep()
        state = DesignState()
        result = await step.run_with_review_loop(state, AlwaysCorrectAI())
        assert result.ai_review.decision == AIDecisionEnum.ESCALATE

    async def test_no_ai_when_mode_none(self):
        step = DummyStep()
        state = DesignState()
        ai = AIEngineer()
        result = await step.run_with_review_loop(state, ai)
        assert result.ai_review is None  # AI not called
