"""StepProtocol and BaseStep — the contract every pipeline step implements."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, runtime_checkable, Protocol

from hx_engine.app.core import validation_rules
from hx_engine.app.models.step_result import (
    AIDecisionEnum,
    AIModeEnum,
    AIReview,
    StepRecord,
    StepResult,
)

if TYPE_CHECKING:
    from hx_engine.app.core.ai_engineer import AIEngineer
    from hx_engine.app.models.design_state import DesignState


# ---------------------------------------------------------------------------
# Protocol — runtime-checkable structural typing
# ---------------------------------------------------------------------------

@runtime_checkable
class StepProtocol(Protocol):
    step_id: int
    step_name: str

    async def execute(self, state: "DesignState") -> StepResult: ...


# ---------------------------------------------------------------------------
# BaseStep — abstract base implementing the protocol + AI review loop
# ---------------------------------------------------------------------------

MAX_CORRECTIONS = 3
MIN_AI_CONFIDENCE = 0.5


class BaseStep(ABC):
    """Abstract base for all pipeline steps.

    Subclasses must set ``step_id``, ``step_name``, ``ai_mode``
    and implement ``execute()``.
    """

    step_id: int
    step_name: str
    ai_mode: AIModeEnum = AIModeEnum.NONE

    # ------------------------------------------------------------------
    # AI call decision logic
    # ------------------------------------------------------------------

    def _should_call_ai(self, state: "DesignState") -> bool:
        if self.ai_mode == AIModeEnum.FULL:
            return True
        if self.ai_mode == AIModeEnum.NONE:
            return False
        # CONDITIONAL
        if state.in_convergence_loop:
            return False
        return self._conditional_ai_trigger(state)

    def _conditional_ai_trigger(self, state: "DesignState") -> bool:  # noqa: ARG002
        """Override in subclasses to define when CONDITIONAL triggers AI."""
        return False

    # ------------------------------------------------------------------
    # Review loop
    # ------------------------------------------------------------------

    async def run_with_review_loop(
        self,
        state: "DesignState",
        ai_engineer: "AIEngineer",
    ) -> StepResult:
        """Execute the step and optionally loop through AI review."""
        start = time.monotonic()
        result = await self.execute(state)

        if not self._should_call_ai(state):
            self._record(state, result, start)
            return result

        corrections = 0
        while corrections < MAX_CORRECTIONS:
            review: AIReview = await ai_engineer.review(self, state, result)
            result.ai_review = review

            if review.confidence < MIN_AI_CONFIDENCE:
                review.decision = AIDecisionEnum.ESCALATE
                self._record(state, result, start)
                return result

            if review.decision == AIDecisionEnum.PROCEED:
                self._append_review_note(state, review)
                self._record(state, result, start)
                return result

            if review.decision == AIDecisionEnum.WARN:
                state.warnings.append(review.reasoning)
                self._append_review_note(state, review)
                self._record(state, result, start)
                return result

            if review.decision == AIDecisionEnum.ESCALATE:
                self._record(state, result, start)
                return result

            if review.decision == AIDecisionEnum.CORRECT:
                corrections += 1
                # Snapshot fields that will be modified so we can roll back
                # if the corrected values fail Layer 2 validation.
                affected = [c.field for c in review.corrections if hasattr(state, c.field)]
                snapshot = state.snapshot_fields(affected)

                # Apply corrections to both result.outputs AND state so the
                # re-executed step reads the corrected values.
                for c in review.corrections:
                    result.outputs[c.field] = c.new_value
                    if hasattr(state, c.field):
                        setattr(state, c.field, c.new_value)

                # Re-run Layer 1 with corrected state
                result = await self.execute(state)
                result.ai_review = review

                # Layer 2 check: roll back if hard rules still fail
                vr = validation_rules.check(self.step_id, result)
                if not vr.passed:
                    state.restore(snapshot)
                    result.validation_passed = False
                    result.validation_errors = vr.errors
                continue

        # Max corrections exhausted — escalate
        result.ai_review = AIReview(
            decision=AIDecisionEnum.ESCALATE,
            confidence=0.0,
            reasoning=f"Exhausted {MAX_CORRECTIONS} correction attempts",
            ai_called=True,
        )
        self._record(state, result, start)
        return result

    # ------------------------------------------------------------------
    # Audit record
    # ------------------------------------------------------------------

    @staticmethod
    def _append_review_note(state: "DesignState", review: AIReview) -> None:
        """Append the AI's forward-looking observation to state.review_notes.

        Uses the dedicated ``observation`` field when present, falling back to
        ``reasoning``. Only appended when non-empty and ≤ 200 chars so downstream
        prompts stay concise.
        """
        note_text = review.observation or review.reasoning
        if note_text and len(note_text) <= 200:
            note = f"[Step {review.decision.value}] {note_text}"
            state.review_notes.append(note)

    @staticmethod
    def _record(
        state: "DesignState",
        result: StepResult,
        start: float,
    ) -> None:
        rec = StepRecord(
            step_id=result.step_id,
            step_name=result.step_name,
            duration_s=time.monotonic() - start,
            ai_decision=(
                result.ai_review.decision if result.ai_review else None
            ),
            ai_confidence=(
                result.ai_review.confidence if result.ai_review else None
            ),
            ai_called=(
                result.ai_review.ai_called if result.ai_review else False
            ),
            validation_passed=result.validation_passed,
            validation_errors=list(result.validation_errors),
            outputs_snapshot=dict(result.outputs),
        )
        state.step_records.append(rec)

    # ------------------------------------------------------------------
    # Abstract execute
    # ------------------------------------------------------------------

    @abstractmethod
    async def execute(self, state: "DesignState") -> StepResult: ...
