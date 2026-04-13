"""Tests for Layer 2 → AI correction recovery in BaseStep.

Covers the new ``run_with_layer2_recovery`` method and the
``initial_failure_context`` parameter added to ``run_with_review_loop``.

Test matrix:
T1 — Correctable failure → AI receives Layer 2 error context on first call
T2 — AI fixes it → Layer 2 passes on re-run → CORRECT returned
T3 — AI cannot fix after 3 attempts → ESCALATE with diagnosis trail
T4 — Non-correctable (physics violation) → AI NOT called → ESCALATE directly
T5 — initial_failure_context flows through to first AI call
T6 — Rollback on failed correction preserves original state
T7 — Non-correctable ESCALATE review has meaningful options for user
"""

from __future__ import annotations

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
    FailureContext,
    StepResult,
)
from hx_engine.app.steps.base import BaseStep


# ===================================================================
# Test Step Classes
# ===================================================================


class RecoverableStep(BaseStep):
    """Step whose outputs can be controlled for recovery tests."""

    step_id = 77
    step_name = "RecoverableTest"
    ai_mode = AIModeEnum.FULL

    def __init__(self, output_val: float = 42.0):
        self._output_val = output_val

    async def execute(self, state: DesignState) -> StepResult:
        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs={"val": self._output_val},
        )


# ===================================================================
# T1 — Correctable failure → AI gets layer2 error context
# ===================================================================


class TestCorrectableFailurePassesContext:
    """When correctable=True, AI receives the Layer 2 error as FailureContext."""

    @pytest.mark.asyncio
    async def test_ai_receives_layer2_errors_on_first_call(self):
        received_contexts: list[FailureContext | None] = []

        class CapturingAI:
            async def review(self, step, state, result, failure_context=None):
                received_contexts.append(failure_context)
                return AIReview(
                    decision=AIDecisionEnum.PROCEED,
                    confidence=0.9,
                    reasoning="Looks fine now",
                    ai_called=True,
                )

        step = RecoverableStep()
        state = DesignState()
        result = await step.run_with_layer2_recovery(
            state,
            CapturingAI(),
            layer2_errors=["val exceeds hard maximum 40"],
            correctable=True,
        )

        assert len(received_contexts) == 1
        ctx = received_contexts[0]
        assert ctx is not None
        assert ctx.layer2_failed is True
        assert "val exceeds hard maximum 40" in ctx.layer2_rule_description


# ===================================================================
# T2 — AI fixes it → Layer 2 passes on re-run → CORRECT
# ===================================================================


class TestAIFixesCorrectableFailure:
    """AI issues CORRECT, re-execute passes Layer 2 → step succeeds."""

    @pytest.mark.asyncio
    async def test_correction_succeeds_on_layer2_recheck(self):
        class FixingAI:
            async def review(self, step, state, result, failure_context=None):
                return AIReview(
                    decision=AIDecisionEnum.CORRECT,
                    confidence=0.9,
                    corrections=[
                        AICorrection(
                            field="val", old_value=42.0, new_value=35.0,
                            reason="Reduce to pass Layer 2",
                        )
                    ],
                    reasoning="Value too high, adjusting downward",
                    ai_called=True,
                )

        passed_vr = ValidationResult(passed=True)

        step = RecoverableStep()
        state = DesignState()
        with patch(
            "hx_engine.app.steps.base.validation_rules.check",
            return_value=passed_vr,
        ):
            result = await step.run_with_layer2_recovery(
                state,
                FixingAI(),
                layer2_errors=["val exceeds hard maximum 40"],
                correctable=True,
            )

        assert result.ai_review is not None
        assert result.ai_review.decision == AIDecisionEnum.CORRECT
        assert len(result.ai_review.attempts) == 1
        assert result.ai_review.attempts[0].outcome == "success"


# ===================================================================
# T3 — AI cannot fix after 3 attempts → ESCALATE with trail
# ===================================================================


class TestCorrectionExhausted:
    """3 failed correction attempts → ESCALATE with full diagnosis trail."""

    @pytest.mark.asyncio
    async def test_exhausted_corrections_produce_escalation(self):
        class AlwaysCorrectAI:
            async def review(self, step, state, result, failure_context=None):
                return AIReview(
                    decision=AIDecisionEnum.CORRECT,
                    confidence=0.9,
                    corrections=[
                        AICorrection(
                            field="val", old_value=42.0, new_value=35.0,
                            reason="Try again",
                        )
                    ],
                    reasoning="Still too high",
                    ai_called=True,
                )

        failed_vr = ValidationResult(passed=False, errors=["val out of range"])

        step = RecoverableStep()
        state = DesignState()
        with patch(
            "hx_engine.app.steps.base.validation_rules.check",
            return_value=failed_vr,
        ):
            result = await step.run_with_layer2_recovery(
                state,
                AlwaysCorrectAI(),
                layer2_errors=["val out of range"],
                correctable=True,
            )

        assert result.ai_review is not None
        assert result.ai_review.decision == AIDecisionEnum.ESCALATE
        assert len(result.ai_review.attempts) == 3
        assert all(a.outcome == "failed" for a in result.ai_review.attempts)


# ===================================================================
# T4 — Non-correctable → AI NOT called → ESCALATE directly
# ===================================================================


class TestNonCorrectableSkipsAI:
    """Physics violation → AI not invoked, ESCALATE returned immediately."""

    @pytest.mark.asyncio
    async def test_non_correctable_does_not_call_ai(self):
        ai_called = False

        class SpyAI:
            async def review(self, step, state, result, failure_context=None):
                nonlocal ai_called
                ai_called = True
                return AIReview(
                    decision=AIDecisionEnum.PROCEED,
                    confidence=0.9,
                    ai_called=True,
                )

        step = RecoverableStep()
        state = DesignState()
        result = await step.run_with_layer2_recovery(
            state,
            SpyAI(),
            layer2_errors=["Temperature below absolute zero"],
            correctable=False,
        )

        assert ai_called is False
        assert result.ai_review is not None
        assert result.ai_review.decision == AIDecisionEnum.ESCALATE
        assert result.ai_review.ai_called is False
        assert "Physics violation" in result.ai_review.reasoning


# ===================================================================
# T5 — initial_failure_context flows to first AI call
# ===================================================================


class TestInitialFailureContext:
    """initial_failure_context is used on the first AI call, not None."""

    @pytest.mark.asyncio
    async def test_initial_context_seeded_on_first_pass(self):
        received_contexts: list[FailureContext | None] = []

        class CapturingAI:
            async def review(self, step, state, result, failure_context=None):
                received_contexts.append(failure_context)
                return AIReview(
                    decision=AIDecisionEnum.PROCEED,
                    confidence=0.9,
                    reasoning="OK",
                    ai_called=True,
                )

        seed = FailureContext(
            layer2_failed=True,
            layer2_rule_description="dp_shell too high",
            layer1_exception=None,
            previous_attempts=[],
        )

        step = RecoverableStep()
        state = DesignState()
        await step.run_with_review_loop(state, CapturingAI(), initial_failure_context=seed)

        assert len(received_contexts) == 1
        assert received_contexts[0] is seed


# ===================================================================
# T6 — Rollback on failed correction
# ===================================================================


class TestRollbackOnFailedCorrection:
    """State is restored when a correction fails Layer 2."""

    @pytest.mark.asyncio
    async def test_state_restored_after_failed_correction(self):
        call_count = 0

        class CorrectThenEscalateAI:
            async def review(self, step, state, result, failure_context=None):
                nonlocal call_count
                call_count += 1
                if call_count <= 3:
                    return AIReview(
                        decision=AIDecisionEnum.CORRECT,
                        confidence=0.9,
                        corrections=[
                            AICorrection(
                                field="val", old_value=42.0,
                                new_value=99.0, reason="try big",
                            )
                        ],
                        reasoning="Attempt to fix",
                        ai_called=True,
                    )
                return AIReview(
                    decision=AIDecisionEnum.ESCALATE,
                    confidence=0.0,
                    reasoning="Giving up",
                    ai_called=True,
                )

        failed_vr = ValidationResult(passed=False, errors=["val out of range"])

        step = RecoverableStep()
        state = DesignState()
        with patch(
            "hx_engine.app.steps.base.validation_rules.check",
            return_value=failed_vr,
        ):
            result = await step.run_with_layer2_recovery(
                state,
                CorrectThenEscalateAI(),
                layer2_errors=["val out of range"],
                correctable=True,
            )

        # applied_corrections cleaned up after the loop
        assert not state.applied_corrections


# ===================================================================
# T7 — Non-correctable ESCALATE has meaningful user options
# ===================================================================


class TestNonCorrectableOptionsPresent:
    """Non-correctable ESCALATE includes actionable options for the user."""

    @pytest.mark.asyncio
    async def test_escalation_provides_user_options(self):
        step = RecoverableStep()
        state = DesignState()
        result = await step.run_with_layer2_recovery(
            state,
            AIEngineer(stub_mode=True),
            layer2_errors=["Temperature cross — T_cold_out > T_hot_in"],
            correctable=False,
        )

        review = result.ai_review
        assert review.decision == AIDecisionEnum.ESCALATE
        assert len(review.options) >= 2
        assert any("temperature" in o.lower() for o in review.options)
