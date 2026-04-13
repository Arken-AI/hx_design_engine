"""StepProtocol and BaseStep — the contract every pipeline step implements."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, runtime_checkable, Protocol

logger = logging.getLogger(__name__)

from hx_engine.app.core import validation_rules
from hx_engine.app.models.step_result import (
    AIDecisionEnum,
    AIModeEnum,
    AIReview,
    AttemptRecord,
    FailureContext,
    StepRecord,
    StepResult,
)

if TYPE_CHECKING:
    from hx_engine.app.core.ai_engineer import AIEngineer
    from hx_engine.app.models.design_state import DesignState


def _serialize_outputs(outputs: dict) -> dict:
    """Convert any Pydantic BaseModel values in outputs to plain dicts.

    Ensures FluidProperties, GeometrySpec, etc. are JSON-serializable
    when stored in StepRecord.outputs or passed to SSE events.
    """
    from pydantic import BaseModel as _BM

    serialized: dict = {}
    for key, val in outputs.items():
        if isinstance(val, _BM):
            serialized[key] = val.model_dump()
        elif isinstance(val, list):
            serialized[key] = [
                item.model_dump() if isinstance(item, _BM) else item
                for item in val
            ]
        else:
            serialized[key] = val
    return serialized


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
MIN_AI_CONFIDENCE = 0.70


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
        # Convergence loop suppresses ALL AI calls — even FULL-mode steps.
        # Layer 1 deterministic math + Layer 2 hard rules still run.
        if state.in_convergence_loop:
            return False
        if self.ai_mode == AIModeEnum.FULL:
            return True
        if self.ai_mode == AIModeEnum.NONE:
            return False
        # CONDITIONAL
        return self._conditional_ai_trigger(state)

    def _conditional_ai_trigger(self, state: "DesignState") -> bool:  # noqa: ARG002
        """Override in subclasses to define when CONDITIONAL triggers AI."""
        return False

    # ------------------------------------------------------------------
    # Review loop
    # ------------------------------------------------------------------

    async def run_with_layer2_recovery(
        self,
        state: "DesignState",
        ai_engineer: "AIEngineer",
        layer2_errors: list[str],
        *,
        correctable: bool,
    ) -> StepResult:
        """Recover from a Layer 2 failure detected by the pipeline runner.

        Called when the pipeline-level Layer 2 check fails *after*
        ``run_with_review_loop`` returned.  Two paths:

        * **correctable=True** — build a ``FailureContext`` describing the
          Layer 2 violation and re-enter the normal AI correction loop.
        * **correctable=False** — physics violation the AI cannot fix;
          build an ESCALATE result directly for the user.
        """
        if not correctable:
            result = await self.execute(state)
            result.ai_review = AIReview(
                decision=AIDecisionEnum.ESCALATE,
                confidence=0.0,
                reasoning=(
                    f"Physics violation detected by Layer 2: "
                    f"{'; '.join(layer2_errors)}. "
                    f"This cannot be fixed by geometry correction. "
                    f"Please review your input temperatures and flow rates."
                ),
                options=[
                    "Revise inlet/outlet temperatures",
                    "Check fluid assignments (hot vs cold side)",
                    "Review flow rates",
                ],
                ai_called=False,
            )
            return result

        initial_failure = FailureContext(
            layer2_failed=True,
            layer2_rule_description="; ".join(layer2_errors),
            layer1_exception=None,
            previous_attempts=[],
        )
        return await self.run_with_review_loop(
            state, ai_engineer, initial_failure_context=initial_failure,
        )

    async def run_with_review_loop(
        self,
        state: "DesignState",
        ai_engineer: "AIEngineer",
        initial_failure_context: FailureContext | None = None,
    ) -> StepResult:
        """Execute the step and optionally loop through AI review.

        Layer sequence per iteration:
        1. Layer 1 (calculate) — ``execute()``
        2. Layer 2 (hard validation) — ``validation_rules.check()``
        3. Layer 3 (AI review) — AI sees Layer 2 failures via ``FailureContext``
        4. Layer 4 (accumulate) — outputs written to DesignState

        Diagnostic loop behaviour:
        - PROCEED / WARN (informational): return immediately
        - WARN (resolvable, corrections present): attempt fix; upgrade to CORRECT
          on Layer 2 pass, rollback to informational WARN on fail
        - CORRECT: apply corrections, re-run, track AttemptRecord; retry with
          failure context if Layer 2 still fails
        - ESCALATE / confidence gate: attach attempt trail and return
        - Exhausted: build escalation with full diagnosis trail
        """
        start = time.monotonic()
        result = await self.execute(state)

        if not self._should_call_ai(state):
            self._record(state, result, start)
            return result

        attempts: list[AttemptRecord] = []

        try:
            for attempt_num in range(1, MAX_CORRECTIONS + 1):

                # Build failure context: from previous failed attempt, from
                # an initial Layer 2 failure passed in, or None on first pass.
                failure_ctx: FailureContext | None = None
                if attempts:
                    last = attempts[-1]
                    failure_ctx = FailureContext(
                        layer2_failed=last.outcome == "failed",
                        layer2_rule_description=last.layer2_rule_failed,
                        layer1_exception=last.layer1_exception,
                        previous_attempts=list(attempts),
                    )
                elif initial_failure_context is not None:
                    failure_ctx = initial_failure_context

                review: AIReview = await ai_engineer.review(
                    self, state, result, failure_context=failure_ctx
                )

                # Confidence gate — low confidence overrides any decision
                if review.confidence < MIN_AI_CONFIDENCE:
                    review = review.model_copy(update={
                        "decision": AIDecisionEnum.ESCALATE,
                        "attempts": attempts,
                    })
                    result.ai_review = review
                    self._record(state, result, start)
                    return result

                if review.decision == AIDecisionEnum.PROCEED:
                    review = review.model_copy(update={"attempts": attempts})
                    result.ai_review = review
                    if review.observation:
                        state.notes.append(review.observation)
                    self._append_review_note(state, review)
                    self._record(state, result, start)
                    return result

                if review.decision == AIDecisionEnum.WARN:
                    if review.corrections:
                        # Resolvable WARN — attempt the fix before passing through
                        affected = [c.field for c in review.corrections if hasattr(state, c.field)]
                        snapshot = state.snapshot_fields(affected)

                        for c in review.corrections:
                            state.applied_corrections[c.field] = c.new_value
                            if hasattr(state, c.field):
                                setattr(state, c.field, c.new_value)

                        try:
                            new_result = await self.execute(state)
                            vr = validation_rules.check(self.step_id, new_result)
                            layer2_passed = vr.passed
                        except Exception:
                            logger.warning(
                                "WARN resolution re-execute failed for step %s (attempt %d)",
                                self.step_name, attempt_num, exc_info=True,
                            )
                            new_result = result
                            layer2_passed = False

                        if layer2_passed:
                            result = new_result
                            state.warnings.append(f"[auto-resolved] {review.reasoning}")
                            resolved = review.model_copy(update={
                                "decision": AIDecisionEnum.CORRECT,
                                "reasoning": f"[auto-resolved] {review.reasoning}",
                                "attempts": attempts,
                            })
                            result.ai_review = resolved
                            self._append_review_note(state, resolved)
                            self._record(state, result, start)
                            return result

                        # Fix failed — rollback and fall through to informational WARN
                        state.restore(snapshot)
                        for c in review.corrections:
                            state.applied_corrections.pop(c.field, None)

                    # Informational WARN (or rollback) — pass through, pipeline continues
                    # All WARN decisions record reasoning in state.warnings
                    review = review.model_copy(update={"attempts": attempts})
                    result.ai_review = review
                    state.warnings.append(review.reasoning)
                    self._append_review_note(state, review)
                    self._record(state, result, start)
                    return result

                if review.decision == AIDecisionEnum.ESCALATE:
                    review = review.model_copy(update={"attempts": attempts})
                    result.ai_review = review
                    self._record(state, result, start)
                    return result

                if review.decision == AIDecisionEnum.CORRECT:
                    affected = [c.field for c in review.corrections if hasattr(state, c.field)]
                    snapshot = state.snapshot_fields(affected)

                    # Write corrections — applied_corrections lets deterministic
                    # step logic (e.g. TEMA selection) respect the AI's choice
                    # instead of re-running its decision tree and overriding it.
                    for c in review.corrections:
                        # result.outputs is intentionally NOT rolled back on Layer 2 fail:
                        # if the loop retries, result = new_result on the next iteration
                        # replaces this object entirely, so the mutation is irrelevant.
                        result.outputs[c.field] = c.new_value
                        state.applied_corrections[c.field] = c.new_value
                        if hasattr(state, c.field):
                            setattr(state, c.field, c.new_value)

                    layer1_exc: str | None = None
                    try:
                        new_result = await self.execute(state)
                        vr = validation_rules.check(self.step_id, new_result)
                        layer2_passed = vr.passed
                        rule_failed = vr.errors[0] if vr.errors else None
                    except Exception as exc:
                        logger.warning(
                            "CORRECT re-execute failed for step %s (attempt %d): %s",
                            self.step_name, attempt_num, exc, exc_info=True,
                        )
                        new_result = result
                        layer2_passed = False
                        rule_failed = None
                        layer1_exc = str(exc)

                    approach = ", ".join(
                        f"{c.field}: {c.old_value!r}→{c.new_value!r}"
                        for c in review.corrections
                    )
                    record = AttemptRecord(
                        attempt_number=attempt_num,
                        diagnosis=review.reasoning,
                        approach=approach,
                        corrections=list(review.corrections),
                        layer2_outcome="pass" if layer2_passed else "fail",
                        layer2_rule_failed=rule_failed,
                        layer1_exception=layer1_exc,
                        outcome="success" if layer2_passed else "failed",
                        confidence=review.confidence,
                    )
                    attempts.append(record)

                    if layer2_passed:
                        result = new_result
                        review = review.model_copy(update={"attempts": attempts})
                        result.ai_review = review
                        self._append_review_note(state, review)
                        self._record(state, result, start)
                        return result

                    # Layer 2 still failing — rollback and loop with failure context
                    state.restore(snapshot)
                    for c in review.corrections:
                        state.applied_corrections.pop(c.field, None)
                    result = new_result

            # Exhausted all attempts — escalate with full diagnosis trail
            approach_summary = "; ".join(
                f"#{a.attempt_number} {a.approach} → {a.outcome}" for a in attempts
            )
            exhaustion = AIReview(
                decision=AIDecisionEnum.ESCALATE,
                confidence=0.0,
                reasoning=(
                    f"Exhausted {MAX_CORRECTIONS} diagnostic attempts. "
                    f"Trail: {approach_summary}"
                ),
                recommendation=(
                    "All automatic correction strategies have been exhausted. "
                    "Please review the attempt trail and correct the inputs manually."
                ),
                options=["Review inputs and correct manually", "Accept result with warnings"],
                attempts=attempts,
                ai_called=True,
            )
            result.ai_review = exhaustion
            self._record(state, result, start)
            return result

        finally:
            # Always clear correction overrides so they don't bleed into the next step
            state.applied_corrections.clear()

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
            outputs=_serialize_outputs(result.outputs),
            warnings=list(result.warnings) if result.warnings else [],
            ai_review=result.ai_review,
        )
        state.step_records.append(rec)

    # ------------------------------------------------------------------
    # Abstract execute
    # ------------------------------------------------------------------

    @abstractmethod
    async def execute(self, state: "DesignState") -> StepResult: ...
