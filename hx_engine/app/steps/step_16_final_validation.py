"""Step 16 — Final Validation + Confidence Score.

Meta-analysis step that introspects the pipeline's own telemetry
(all 15 prior StepRecord entries, convergence trajectory, warnings,
corrections) to produce a deterministic confidence score and trigger
an AI final sign-off.

ai_mode = FULL — always called.  This is the final engineering
sign-off on the entire design.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.step_result import (
    AIDecisionEnum,
    AIModeEnum,
    StepResult,
)
from hx_engine.app.steps.base import BaseStep

# Import rules module so auto-registration fires when step class is loaded
import hx_engine.app.steps.step_16_rules  # noqa: F401

if TYPE_CHECKING:
    from hx_engine.app.core.ai_engineer import AIEngineer
    from hx_engine.app.models.design_state import DesignState
    from hx_engine.app.models.step_result import AIReview, StepRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIDENCE_WEIGHTS: dict[str, float] = {
    "geometry_convergence": 0.25,
    "ai_agreement_rate": 0.25,
    "supermemory_similarity": 0.25,
    "validation_passes": 0.25,
}

SUPERMEMORY_SIMILARITY_PLACEHOLDER = 0.5

# Confidence threshold for future Supermemory save (stub/TODO)
SUPERMEMORY_SAVE_THRESHOLD = 0.75

# P2-22: Gnielinski is least accurate in the 2300 < Re < 10 000 band (±15%).
_THERMAL_PENALTY_TRANSITION_ZONE = 0.90

# P2-25: When shell-side μ_wall falls back to bulk, Sieder-Tate correction = 1.0.
# Only applied when the shell fluid is viscous (mirrors step_10 threshold).
_THERMAL_PENALTY_WALL_MU_APPROX = 0.90
_MU_VISCOUS_THRESHOLD_PA_S = 0.01  # 10 cP


# ---------------------------------------------------------------------------
# Helper functions (module-level, testable independently)
# ---------------------------------------------------------------------------

def _compute_geometry_convergence(
    converged: bool | None,
    iteration: int | None,
) -> float:
    """Score convergence quality.  Returns 0.0–1.0.

    - 1.0 if converged in ≤10 iterations
    - Linear degrade from 1.0 to 0.5 between 10 and 20 iterations
    - 0.0 if not converged
    """
    if converged is None or not converged:
        return 0.0
    if iteration is None:
        return 1.0  # converged=True but no iteration count → assume clean
    if iteration <= 10:
        return 1.0
    if iteration <= 20:
        return 1.0 - 0.5 * (iteration - 10) / 10
    # > 20 iterations but still converged → floor at 0.5
    return 0.5


def _compute_ai_agreement_rate(
    step_records: list[StepRecord],
) -> float:
    """Fraction of AI-reviewed steps that returned PROCEED.

    Returns 0.5 (neutral) if no steps called AI.
    """
    ai_called = [r for r in step_records if r.ai_called]
    if not ai_called:
        return 0.5
    n_proceed = sum(
        1 for r in ai_called if r.ai_decision == AIDecisionEnum.PROCEED
    )
    return n_proceed / len(ai_called)


def _compute_validation_pass_rate(
    step_records: list[StepRecord],
) -> float:
    """Fraction of steps that passed validation on first attempt.

    A step passed on first attempt when:
    - validation_passed == True AND
    - ai_decision is None (AI wasn't called) OR ai_decision == PROCEED
      (AI called but no corrections needed)

    Returns 0.5 (neutral) if no step records.
    """
    if not step_records:
        return 0.5
    first_attempt_passes = 0
    for r in step_records:
        if r.validation_passed and (
            r.ai_decision is None or r.ai_decision == AIDecisionEnum.PROCEED
        ):
            first_attempt_passes += 1
    return first_attempt_passes / len(step_records)


def _compute_confidence_score(
    breakdown: dict[str, float],
    weights: dict[str, float],
) -> float:
    """Weighted sum of breakdown components, clamped to [0.0, 1.0]."""
    score = sum(weights[k] * breakdown[k] for k in weights)
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Step class
# ---------------------------------------------------------------------------

class Step16FinalValidation(BaseStep):
    """Step 16: Final Validation + Confidence Score."""

    step_id: int = 16
    step_name: str = "Final Validation"
    ai_mode: AIModeEnum = AIModeEnum.FULL

    # ------------------------------------------------------------------
    # AI call decision
    # ------------------------------------------------------------------

    def _conditional_ai_trigger(self, state: "DesignState") -> bool:
        return True  # FULL mode — always call AI

    # ------------------------------------------------------------------
    # Precondition check
    # ------------------------------------------------------------------

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        """Verify Steps 1–15 data is present."""
        missing: list[str] = []
        if state.convergence_converged is None:
            missing.append("convergence_converged (Step 12)")
        if state.vibration_safe is None:
            missing.append("vibration_safe (Step 13)")
        if state.tube_thickness_ok is None:
            missing.append("tube_thickness_ok (Step 14)")
        if state.shell_thickness_ok is None:
            missing.append("shell_thickness_ok (Step 14)")
        if state.cost_usd is None:
            missing.append("cost_usd (Step 15)")
        return missing

    # ------------------------------------------------------------------
    # Core execute — deterministic confidence computation
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Layer 1: Compute deterministic confidence breakdown.

        AI extras (design_summary, assumptions, strengths, risks) are
        populated by the AI review in Layer 3, not here.
        """
        # 1. Precondition check
        missing = self._check_preconditions(state)
        if missing:
            raise CalculationError(
                16,
                f"Step 16 requires: {', '.join(missing)}",
            )

        warnings: list[str] = []

        # 2. Compute each confidence component
        geometry_convergence = _compute_geometry_convergence(
            state.convergence_converged,
            state.convergence_iteration,
        )
        ai_agreement_rate = _compute_ai_agreement_rate(state.step_records)
        supermemory_similarity = SUPERMEMORY_SIMILARITY_PLACEHOLDER
        validation_passes = _compute_validation_pass_rate(state.step_records)

        # 3. Build breakdown dict
        confidence_breakdown = {
            "geometry_convergence": round(geometry_convergence, 4),
            "ai_agreement_rate": round(ai_agreement_rate, 4),
            "supermemory_similarity": round(supermemory_similarity, 4),
            "validation_passes": round(validation_passes, 4),
        }

        # 4. Compute weighted score
        confidence_score = _compute_confidence_score(
            confidence_breakdown, CONFIDENCE_WEIGHTS,
        )
        confidence_score = round(confidence_score, 4)

        # 4b. Thermal-accuracy penalties (P2-22, P2-25)
        # Applied as multipliers after the weighted sum so each penalty is
        # visible in the breakdown independently of the four base components.
        thermal_penalties: list[str] = []

        # P2-22: transition / low-turbulent zone — Gnielinski ±15%
        if getattr(state, "flow_regime_tube", None) == "transition_low_turbulent":
            confidence_score = round(
                confidence_score * _THERMAL_PENALTY_TRANSITION_ZONE, 4,
            )
            thermal_penalties.append(
                f"transition_zone_Re ×{_THERMAL_PENALTY_TRANSITION_ZONE}: "
                f"Gnielinski accuracy ±15% (2300 < Re < 10000)"
            )

        # P2-25: shell-side μ_wall approximated as bulk on a viscous fluid
        if getattr(state, "mu_s_wall_basis", None) == "approx_bulk":
            shell_mu = 0.0
            if state.shell_side_fluid == "hot" and state.hot_fluid_props:
                shell_mu = state.hot_fluid_props.viscosity_Pa_s or 0.0
            elif state.shell_side_fluid == "cold" and state.cold_fluid_props:
                shell_mu = state.cold_fluid_props.viscosity_Pa_s or 0.0
            if shell_mu > _MU_VISCOUS_THRESHOLD_PA_S:
                confidence_score = round(
                    confidence_score * _THERMAL_PENALTY_WALL_MU_APPROX, 4,
                )
                thermal_penalties.append(
                    f"shell_wall_mu_approx ×{_THERMAL_PENALTY_WALL_MU_APPROX}: "
                    f"Sieder-Tate correction = 1.0 (μ_bulk={shell_mu*1000:.1f} cP)"
                )

        if thermal_penalties:
            confidence_breakdown["thermal_penalties"] = thermal_penalties

        # 5. Score interpretation warnings
        if confidence_score < 0.50:
            warnings.append(
                f"Low confidence score ({confidence_score:.2f}) — "
                f"significant concerns detected. Manual review recommended."
            )
        elif confidence_score < 0.70:
            warnings.append(
                f"Moderate confidence score ({confidence_score:.2f}) — "
                f"review flagged issues. Consider manual review."
            )

        # 6. Supermemory save stub (TODO: integrate when Supermemory is available)
        if confidence_score >= SUPERMEMORY_SAVE_THRESHOLD:
            logger.info(
                "Confidence %.2f ≥ %.2f — design eligible for Supermemory "
                "save (not yet integrated).",
                confidence_score,
                SUPERMEMORY_SAVE_THRESHOLD,
            )

        # 7. Write deterministic results to state
        state.confidence_score = confidence_score
        state.confidence_breakdown = confidence_breakdown

        # 8. Generate fallback summary in case AI is not called
        #    (shouldn't happen for FULL mode, but defensively)
        fallback_summary = (
            f"Heat exchanger design ({state.tema_type or 'unknown TEMA'}, "
            f"TEMA Class {state.tema_class or 'unknown'}) — "
            f"confidence score: {confidence_score:.2f}/1.0."
        )

        # 9. Build StepResult
        outputs: dict = {
            "confidence_score": confidence_score,
            "confidence_breakdown": confidence_breakdown,
            "design_summary": fallback_summary,
            "assumptions": [],
            "design_strengths": [],
            "design_risks": [],
        }
        if thermal_penalties:
            outputs["thermal_penalties"] = thermal_penalties

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Post-AI review hook — extract Step 16 extras from AI response
    # ------------------------------------------------------------------

    async def run_with_review_loop(
        self,
        state: "DesignState",
        ai_engineer: "AIEngineer",
    ) -> StepResult:
        """Override to extract extra fields from AI review response."""
        result = await super().run_with_review_loop(state, ai_engineer)

        # Copy AI-produced extras to state (if AI was called)
        if result.ai_review and result.ai_review.ai_called:
            self._apply_ai_extras(state, result.ai_review, result)

        return result

    @staticmethod
    def _apply_ai_extras(
        state: "DesignState",
        ai_review: "AIReview",
        result: StepResult,
    ) -> None:
        """Extract design_summary, assumptions, strengths, risks from AI.

        Falls back to the deterministic values in result.outputs if the
        AI did not provide them.
        """
        # design_summary — prefer AI, fall back to execute() output
        if getattr(ai_review, "design_summary", None):
            state.design_summary = ai_review.design_summary
            result.outputs["design_summary"] = ai_review.design_summary
        elif not state.design_summary:
            state.design_summary = result.outputs.get("design_summary", "")

        # assumptions
        ai_assumptions = getattr(ai_review, "assumptions", None)
        if ai_assumptions:
            state.assumptions = list(ai_assumptions)
            result.outputs["assumptions"] = list(ai_assumptions)

        # design_strengths
        ai_strengths = getattr(ai_review, "design_strengths", None)
        if ai_strengths:
            state.design_strengths = list(ai_strengths)
            result.outputs["design_strengths"] = list(ai_strengths)

        # design_risks
        ai_risks = getattr(ai_review, "design_risks", None)
        if ai_risks:
            state.design_risks = list(ai_risks)
            result.outputs["design_risks"] = list(ai_risks)
