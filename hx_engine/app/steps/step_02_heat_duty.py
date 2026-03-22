"""Step 02 — Heat Duty Calculation.

Computes Q = ṁ × Cp × ΔT for both fluid sides, calculates the missing
4th temperature if only 3 were provided by Step 1, and verifies energy
balance closure.

ai_mode = CONDITIONAL — AI is only called when anomalies are detected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState


class Step02HeatDuty(BaseStep):
    step_id: int = 2
    step_name: str = "Heat Duty"
    ai_mode: AIModeEnum = AIModeEnum.CONDITIONAL

    # ------------------------------------------------------------------
    # Piece 2: Pure heat-duty computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_Q(
        m_dot_kg_s: float,
        cp_J_kgK: float,
        T_in_C: float,
        T_out_C: float,
    ) -> float:
        """Compute heat duty Q = ṁ × Cp × (T_in − T_out) for one fluid side.

        For the **hot** side, T_in > T_out ⇒ Q > 0 (heat released).
        For the **cold** side, call with (T_out, T_in) so Q > 0 means heat absorbed,
        or use (T_in, T_out) and expect a negative value when cold gains heat.

        Returns Q in watts (W).  The caller decides sign convention.
        """
        return m_dot_kg_s * cp_J_kgK * (T_in_C - T_out_C)

    # ------------------------------------------------------------------
    # Placeholder — later pieces will fill these in
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Full execute — wired in Piece 7."""
        raise NotImplementedError("Step02 execute() not yet assembled (Piece 7)")
