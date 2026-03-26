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
    # Piece 3: Missing 4th temperature back-calculation
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_missing_temp(
        *,
        T_hot_in_C: float | None,
        T_hot_out_C: float | None,
        T_cold_in_C: float | None,
        T_cold_out_C: float | None,
        m_dot_hot_kg_s: float,
        m_dot_cold_kg_s: float | None,
        cp_hot_J_kgK: float,
        cp_cold_J_kgK: float,
    ) -> dict:
        """Back-calculate the single missing temperature from energy balance.

        If all 4 temperatures are known but ``m_dot_cold_kg_s`` is ``None``,
        solve for the cold-side mass flow rate instead.

        Returns a dict with:
          - ``calculated_field``: name of the field that was solved
          - the solved value keyed by its field name
          - ``Q_known_side_W``: heat duty from the known side
          - all input temperatures echoed back (using solved values)

        Raises ``CalculationError(2, ...)`` when the system is
        underdetermined (more than one unknown temperature on the same
        side).
        """
        from hx_engine.app.core.exceptions import CalculationError

        temps = {
            "T_hot_in_C": T_hot_in_C,
            "T_hot_out_C": T_hot_out_C,
            "T_cold_in_C": T_cold_in_C,
            "T_cold_out_C": T_cold_out_C,
        }
        missing = [k for k, v in temps.items() if v is None]

        # --- All 4 temps known: solve for m_dot_cold if needed ----------
        if len(missing) == 0:
            if m_dot_cold_kg_s is None:
                Q_hot = m_dot_hot_kg_s * cp_hot_J_kgK * (T_hot_in_C - T_hot_out_C)  # type: ignore[operator]
                delta_T_cold = T_cold_out_C - T_cold_in_C  # type: ignore[operator]
                if abs(delta_T_cold) < 1e-10:
                    raise CalculationError(
                        2, "Cold-side ΔT is zero — cannot solve for m_dot_cold"
                    )
                m_dot_cold = Q_hot / (cp_cold_J_kgK * delta_T_cold)
                return {
                    "calculated_field": "m_dot_cold_kg_s",
                    "m_dot_cold_kg_s": m_dot_cold,
                    "Q_known_side_W": Q_hot,
                    "T_hot_in_C": T_hot_in_C,
                    "T_hot_out_C": T_hot_out_C,
                    "T_cold_in_C": T_cold_in_C,
                    "T_cold_out_C": T_cold_out_C,
                }
            # Nothing to solve — all known
            Q_hot = m_dot_hot_kg_s * cp_hot_J_kgK * (T_hot_in_C - T_hot_out_C)  # type: ignore[operator]
            return {
                "calculated_field": None,
                "Q_known_side_W": Q_hot,
                **temps,
            }

        # --- More than one missing temperature → underdetermined ---------
        if len(missing) > 1:
            raise CalculationError(
                2,
                f"Multiple temperatures missing ({', '.join(missing)}) "
                "— system is underdetermined, cannot solve.",
            )

        field = missing[0]

        # Compute Q from the side that has both temperatures known
        if field.startswith("T_cold"):
            # Hot side is fully known → compute Q_hot
            Q = m_dot_hot_kg_s * cp_hot_J_kgK * (T_hot_in_C - T_hot_out_C)  # type: ignore[operator]
        else:
            # Cold side is fully known → compute Q_cold
            if m_dot_cold_kg_s is None:
                raise CalculationError(
                    2,
                    "Cannot solve for a hot-side temperature when "
                    "m_dot_cold is also unknown.",
                )
            Q = m_dot_cold_kg_s * cp_cold_J_kgK * (T_cold_out_C - T_cold_in_C)  # type: ignore[operator]

        # Solve the single unknown
        if field == "T_cold_out_C":
            if m_dot_cold_kg_s is None or abs(m_dot_cold_kg_s * cp_cold_J_kgK) < 1e-10:
                raise CalculationError(2, "m_dot_cold or Cp_cold is zero — cannot solve T_cold_out")
            solved = T_cold_in_C + Q / (m_dot_cold_kg_s * cp_cold_J_kgK)  # type: ignore[operator]
        elif field == "T_cold_in_C":
            if m_dot_cold_kg_s is None or abs(m_dot_cold_kg_s * cp_cold_J_kgK) < 1e-10:
                raise CalculationError(2, "m_dot_cold or Cp_cold is zero — cannot solve T_cold_in")
            solved = T_cold_out_C - Q / (m_dot_cold_kg_s * cp_cold_J_kgK)  # type: ignore[operator]
        elif field == "T_hot_out_C":
            if abs(m_dot_hot_kg_s * cp_hot_J_kgK) < 1e-10:
                raise CalculationError(2, "m_dot_hot or Cp_hot is zero — cannot solve T_hot_out")
            solved = T_hot_in_C - Q / (m_dot_hot_kg_s * cp_hot_J_kgK)  # type: ignore[operator]
        else:  # T_hot_in_C
            if abs(m_dot_hot_kg_s * cp_hot_J_kgK) < 1e-10:
                raise CalculationError(2, "m_dot_hot or Cp_hot is zero — cannot solve T_hot_in")
            solved = T_hot_out_C + Q / (m_dot_hot_kg_s * cp_hot_J_kgK)  # type: ignore[operator]

        result = {
            "calculated_field": field,
            field: solved,
            "Q_known_side_W": Q,
            "T_hot_in_C": T_hot_in_C if field != "T_hot_in_C" else solved,
            "T_hot_out_C": T_hot_out_C if field != "T_hot_out_C" else solved,
            "T_cold_in_C": T_cold_in_C if field != "T_cold_in_C" else solved,
            "T_cold_out_C": T_cold_out_C if field != "T_cold_out_C" else solved,
        }
        return result

    # ------------------------------------------------------------------
    # Placeholder — later pieces will fill these in
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Full execute — wired in Piece 7."""
        raise NotImplementedError("Step02 execute() not yet assembled (Piece 7)")
