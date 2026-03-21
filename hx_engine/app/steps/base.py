"""StepProtocol and BaseStep — the contract every pipeline step implements."""

from __future__ import annotations

import copy
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, runtime_checkable, Protocol

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

    def execute(self, state: "DesignState") -> StepResult: ...


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

    def _conditional_ai_trigger(self, state: "DesignState") -> bool:
        """Override in subclasses to define when CONDITIONAL triggers AI."""
        return False

    # ------------------------------------------------------------------
    # Review loop
    # ------------------------------------------------------------------

    def run_with_review_loop(
        self,
        state: "DesignState",
        ai_engineer: "AIEngineer",
    ) -> StepResult:
        """Execute the step and optionally loop through AI review."""
        start = time.monotonic()
        result = self.execute(state)

        if not self._should_call_ai(state):
            self._record(state, result, start)
            return result

        corrections = 0
        while corrections < MAX_CORRECTIONS:
            review: AIReview = ai_engineer.review(self, state, result)
            result.ai_review = review

            if review.confidence < MIN_AI_CONFIDENCE:
                review.decision = AIDecisionEnum.ESCALATE
                self._record(state, result, start)
                return result

            if review.decision == AIDecisionEnum.PROCEED:
                self._record(state, result, start)
                return result

            if review.decision == AIDecisionEnum.WARN:
                state.warnings.append(review.reasoning)
                self._record(state, result, start)
                return result

            if review.decision == AIDecisionEnum.ESCALATE:
                self._record(state, result, start)
                return result

            if review.decision == AIDecisionEnum.CORRECT:
                corrections += 1
                for c in review.corrections:
                    result.outputs[c.field] = c.new_value
                result = self.execute(state)

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
        state.step_records.append(rec.model_dump())

    # ------------------------------------------------------------------
    # Abstract execute
    # ------------------------------------------------------------------

    @abstractmethod
    def execute(self, state: "DesignState") -> StepResult: ...
