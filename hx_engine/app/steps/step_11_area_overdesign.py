"""Step 11 — Area and Overdesign.

Computes the required heat transfer area (from calculated U) and compares
it to the provided area (from physical geometry) to yield the overdesign
percentage — the primary convergence signal for Step 12.

ai_mode = CONDITIONAL — AI called only when overdesign < 8% or > 30%.
Skipped in convergence loop.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

# Import rules module so auto-registration fires when step class is loaded
import hx_engine.app.steps.step_11_rules  # noqa: F401

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState

logger = logging.getLogger(__name__)

# Overdesign thresholds (%)
_OVERDESIGN_AI_LOW = 8.0       # AI trigger below this
_OVERDESIGN_AI_HIGH = 30.0     # AI trigger above this
_OVERDESIGN_WARN_HIGH = 40.0   # Warning threshold


class Step11AreaOverdesign(BaseStep):
    """Step 11: Area and Overdesign."""

    step_id: int = 11
    step_name: str = "Area and Overdesign"
    ai_mode: AIModeEnum = AIModeEnum.CONDITIONAL

    # ------------------------------------------------------------------
    # AI call decision
    # ------------------------------------------------------------------

    def _should_call_ai(self, state: "DesignState") -> bool:
        if state.in_convergence_loop:
            return False
        return self._conditional_ai_trigger(state)

    def _conditional_ai_trigger(self, state: "DesignState") -> bool:
        """Call AI when overdesign is outside the 8–30% comfort zone."""
        if state.overdesign_pct is None:
            return False
        if state.overdesign_pct < _OVERDESIGN_AI_LOW:
            return True
        if state.overdesign_pct > _OVERDESIGN_AI_HIGH:
            return True
        return False

    # ------------------------------------------------------------------
    # Pre-condition checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        missing: list[str] = []
        if state.Q_W is None:
            missing.append("Q_W (Step 2)")
        if state.LMTD_K is None:
            missing.append("LMTD_K (Step 5)")
        if state.F_factor is None:
            missing.append("F_factor (Step 5)")
        if state.U_dirty_W_m2K is None:
            missing.append("U_dirty_W_m2K (Step 9)")
        if state.geometry is None:
            missing.append("geometry (Step 4/6)")
        else:
            g = state.geometry
            if g.tube_od_m is None:
                missing.append("geometry.tube_od_m")
            if g.tube_length_m is None:
                missing.append("geometry.tube_length_m")
            if g.n_tubes is None:
                missing.append("geometry.n_tubes")
        return missing

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Layer 1: Pure calculation of area and overdesign."""

        # 1. Precondition check
        missing = self._check_preconditions(state)
        if missing:
            raise CalculationError(
                11,
                f"Step 11 requires: {', '.join(missing)}",
            )

        warnings: list[str] = []
        g = state.geometry

        # 2. Guard against near-zero driving force
        effective_driving = state.F_factor * state.LMTD_K
        if effective_driving < 1e-3:
            raise CalculationError(
                11,
                f"Effective temperature driving force (F × LMTD = "
                f"{state.F_factor:.4f} × {state.LMTD_K:.4f} = "
                f"{effective_driving:.6f}) is essentially zero — "
                f"required area would be infinite.",
            )

        # 3. Compute A_required = Q / (U_dirty × F × LMTD)
        A_required = state.Q_W / (
            state.U_dirty_W_m2K * state.F_factor * state.LMTD_K
        )

        # 4. Compute A_provided = π × d_o × L × N_t
        A_provided = math.pi * g.tube_od_m * g.tube_length_m * g.n_tubes

        # 5. Compute overdesign %
        overdesign_pct = (A_provided - A_required) / A_required * 100.0

        # 6. Compute Step 6 vs Step 11 deviation diagnostic
        A_est_vs_req_pct = None
        if state.A_m2 is not None and A_required > 0:
            A_est_vs_req_pct = (state.A_m2 - A_required) / A_required * 100.0

        # 7. Generate warnings
        if overdesign_pct < 0:
            warnings.append(
                f"Exchanger is undersized: overdesign = {overdesign_pct:.1f}% "
                f"(A_provided = {A_provided:.2f} m², "
                f"A_required = {A_required:.2f} m²)"
            )

        if overdesign_pct > _OVERDESIGN_WARN_HIGH:
            warnings.append(
                f"Excessive overdesign: {overdesign_pct:.1f}% > {_OVERDESIGN_WARN_HIGH:.0f}% "
                f"— cost concern"
            )

        if (
            A_est_vs_req_pct is not None
            and abs(A_est_vs_req_pct) > 30
        ):
            warnings.append(
                f"Initial U estimate significantly off: "
                f"Step 6 area deviation = {A_est_vs_req_pct:+.1f}%"
            )

        # 8. Write to state
        state.area_required_m2 = A_required
        state.area_provided_m2 = A_provided
        state.overdesign_pct = overdesign_pct
        state.A_estimated_vs_required_pct = A_est_vs_req_pct

        # 9. Build outputs dict
        outputs: dict = {
            "area_required_m2": A_required,
            "area_provided_m2": A_provided,
            "overdesign_pct": overdesign_pct,
        }
        if A_est_vs_req_pct is not None:
            outputs["A_estimated_vs_required_pct"] = A_est_vs_req_pct

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            warnings=warnings,
        )
