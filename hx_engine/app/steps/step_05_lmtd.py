"""Step 05 — Determine LMTD and F-Factor.

Takes terminal temperatures from Steps 1/2 and geometry from Step 4 to
compute the Log Mean Temperature Difference (LMTD) and its correction
factor F. The product F × LMTD is the effective driving force used in
all downstream sizing calculations (Steps 6–16).

ai_mode = CONDITIONAL — AI is only called when:
  1. F < 0.85 (or < 0.80 if auto-corrected)
  2. R > 4.0 (highly asymmetric duty)
  3. Approach temperature < 3°C (temperature cross risk)

AI constraint (Option C): Auto-correction handles shell_passes 1→2
within execute(). AI should only WARN or ESCALATE about shell passes —
never CORRECT them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hx_engine.app.correlations.lmtd import (
    compute_f_factor,
    compute_lmtd,
    compute_P,
    compute_R,
)
from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState


class Step05LMTD(BaseStep):
    """Step 5: LMTD & F-Factor computation with auto-correction."""

    step_id: int = 5
    step_name: str = "LMTD & F-Factor"
    ai_mode: AIModeEnum = AIModeEnum.CONDITIONAL

    # ------------------------------------------------------------------
    # Pre-condition checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        """Return list of missing fields required from Steps 1–4."""
        missing: list[str] = []
        for field in (
            "T_hot_in_C", "T_hot_out_C", "T_cold_in_C", "T_cold_out_C", "Q_W",
        ):
            if getattr(state, field) is None:
                missing.append(field)
        if state.geometry is None:
            missing.append("geometry")
        else:
            if state.geometry.n_passes is None:
                missing.append("geometry.n_passes")
            if state.geometry.shell_passes is None:
                missing.append("geometry.shell_passes")
        return missing

    # ------------------------------------------------------------------
    # Result builder
    # ------------------------------------------------------------------

    def _build_result(
        self,
        *,
        LMTD_K: float,
        F_factor: float,
        R: float | None,
        P: float | None,
        shell_passes: int,
        auto_corrected: bool,
        warnings: list[str],
        escalation_hints: list[dict] | None = None,
    ) -> StepResult:
        """Build the StepResult with outputs dict."""
        effective_LMTD = F_factor * LMTD_K

        outputs: dict = {
            "LMTD_K": LMTD_K,
            "F_factor": F_factor,
            "effective_LMTD": effective_LMTD,
            "R": R,
            "P": P,
            "shell_passes": shell_passes,
            "auto_corrected": auto_corrected,
        }
        if escalation_hints:
            outputs["escalation_hints"] = escalation_hints

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Compute LMTD, R, P, and F-factor. Auto-correct shell_passes if needed."""

        # 1. Pre-condition checks
        missing = self._check_preconditions(state)
        if missing:
            raise CalculationError(
                5, f"Step 5 requires the following from Steps 1-4: "
                   f"{', '.join(missing)}",
            )

        warnings: list[str] = []

        # 2. Compute LMTD — wrap ValueError into CalculationError
        try:
            LMTD = compute_lmtd(
                state.T_hot_in_C, state.T_hot_out_C,
                state.T_cold_in_C, state.T_cold_out_C,
            )
        except ValueError as e:
            raise CalculationError(
                5, f"LMTD calculation failed: {e}",
            ) from e

        # 3. Very small LMTD warning
        if LMTD < 3.0:
            warnings.append(
                f"LMTD = {LMTD:.2f}°C is very small (< 3°C). "
                f"This requires a very large heat transfer area. "
                f"May not be economically viable."
            )

        # 4. Pure counter-current short circuit
        n_passes = state.geometry.n_passes
        shell_passes = state.geometry.shell_passes or 1

        if n_passes == 1 and shell_passes == 1:
            # True counter-current — F = 1.0 exactly
            return self._build_result(
                LMTD_K=LMTD, F_factor=1.0, R=None, P=None,
                shell_passes=shell_passes, auto_corrected=False,
                warnings=warnings,
            )

        # 5. Compute R and P
        try:
            R = compute_R(
                state.T_hot_in_C, state.T_hot_out_C,
                state.T_cold_in_C, state.T_cold_out_C,
            )
            P = compute_P(
                state.T_hot_in_C, state.T_hot_out_C,
                state.T_cold_in_C, state.T_cold_out_C,
            )
        except ValueError as e:
            raise CalculationError(
                5, f"R/P computation failed: {e}",
            ) from e

        # 6. Compute F-factor
        F = compute_f_factor(R, P, n_shell_passes=shell_passes)

        # 7. Auto-correction: try 2 shell passes if F is poor
        auto_corrected = False
        if F < 0.80 and shell_passes == 1:
            F_2shell = compute_f_factor(R, P, n_shell_passes=2)
            if F_2shell >= 0.75:  # Improvement worth taking
                warnings.append(
                    f"F-factor with 1 shell pass = {F:.4f} (< 0.80). "
                    f"Increased to 2 shell passes → F = {F_2shell:.4f}."
                )
                F = F_2shell
                shell_passes = 2
                auto_corrected = True
                # Update geometry on state directly (Option A — step handles it)
                state.geometry.shell_passes = 2
            else:
                warnings.append(
                    f"F-factor = {F:.4f} with 1 shell pass, "
                    f"{F_2shell:.4f} with 2 shell passes. "
                    f"Both below 0.80 — design may be infeasible."
                )

        # 8. Highly asymmetric warning
        if R > 4.0:
            warnings.append(
                f"R = {R:.2f} is highly asymmetric. "
                f"Consider if a different exchanger arrangement "
                f"(e.g., multiple shells in series) would be more effective."
            )

        # 9. Cache values for _conditional_ai_trigger (same pattern as Step 3)
        self._F_factor = F
        self._R = R
        self._auto_corrected = auto_corrected

        # 10. Build escalation hints for AI context
        escalation_hints: list[dict] = []
        if F < 0.85:
            escalation_hints.append({
                "trigger": "F_factor_borderline",
                "recommendation": (
                    "Consider 2 shell passes or verify TEMA selection"
                ),
            })
        if R > 4.0:
            escalation_hints.append({
                "trigger": "high_R_sensitivity",
                "recommendation": (
                    "F-factor is sensitive to small P changes at this R. "
                    "Verify temperature spec accuracy."
                ),
            })
        if (
            state.T_hot_in_C is not None
            and state.T_hot_out_C is not None
            and state.T_cold_in_C is not None
            and state.T_cold_out_C is not None
            and min(
                state.T_hot_in_C - state.T_cold_out_C,
                state.T_hot_out_C - state.T_cold_in_C,
            ) < 3.0
        ):
            escalation_hints.append({
                "trigger": "temperature_cross_risk",
                "recommendation": (
                    "Approach temperature < 3°C. May need multiple shells "
                    "in series or revised outlet temperatures."
                ),
            })

        # 11. Apply thermal results to state
        state.LMTD_K = LMTD
        state.F_factor = F

        # 12. Build result
        return self._build_result(
            LMTD_K=LMTD, F_factor=F, R=R, P=P,
            shell_passes=shell_passes, auto_corrected=auto_corrected,
            warnings=warnings, escalation_hints=escalation_hints,
        )

    # ------------------------------------------------------------------
    # Conditional AI trigger
    # ------------------------------------------------------------------

    def _conditional_ai_trigger(self, state: "DesignState") -> bool:
        """Trigger AI review when borderline F, high R, or temperature cross risk.

        Three triggers (any one is sufficient):
          1. F < 0.85 — but if auto-correction happened (1→2 shells),
             only trigger if corrected F is still < 0.80
          2. R > 4.0 — asymmetric duty, steep F-P curve
          3. Approach temperature < 3°C — temperature cross risk

        Values are cached on self during execute() (same pattern as Step 3).
        """
        F = getattr(self, "_F_factor", None)
        R = getattr(self, "_R", None)
        auto_corrected = getattr(self, "_auto_corrected", False)

        # Trigger 1: F-factor borderline
        if F is not None:
            if auto_corrected:
                if F < 0.80:
                    return True
            else:
                if F < 0.85:
                    return True

        # Trigger 2: Highly asymmetric duty (steep F-P curve)
        if R is not None and R > 4.0:
            return True

        # Trigger 3: Temperature cross risk (minimum terminal approach < 3°C)
        if (
            state.T_hot_in_C is not None
            and state.T_hot_out_C is not None
            and state.T_cold_in_C is not None
            and state.T_cold_out_C is not None
        ):
            approach = min(
                state.T_hot_in_C - state.T_cold_out_C,
                state.T_hot_out_C - state.T_cold_in_C,
            )
            if approach < 3.0:
                return True

        return False
