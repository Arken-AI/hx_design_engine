"""Step 02 — Heat Duty Calculation.

Computes Q = ṁ × Cp × ΔT for both fluid sides, calculates the missing
4th temperature if only 3 were provided by Step 1, and verifies energy
balance closure.

ai_mode = CONDITIONAL — AI is only called when anomalies are detected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from hx_engine.app.core.exceptions import CalculationError
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
    # Piece 3: Missing 4th temperature calculation
    # ------------------------------------------------------------------

    @staticmethod
    def _calculate_missing_temp(
        *,
        T_hot_in_C: Optional[float],
        T_hot_out_C: Optional[float],
        T_cold_in_C: Optional[float],
        T_cold_out_C: Optional[float],
        m_dot_hot_kg_s: Optional[float],
        m_dot_cold_kg_s: Optional[float],
        cp_hot_J_kgK: float,
        cp_cold_J_kgK: float,
    ) -> dict:
        """Calculate the missing 4th temperature from energy balance.

        Given at least 3 of 4 temperatures, the known-side Q, and
        both Cp values, solve algebraically for the unknown temperature.

        Also handles the special case where all 4 temperatures are known
        but m_dot_cold is missing — solves for the flow rate.

        Returns a dict with keys:
          - T_hot_in_C, T_hot_out_C, T_cold_in_C, T_cold_out_C (all populated)
          - m_dot_cold_kg_s (if it was calculated)
          - calculated_field: str — which field was back-calculated
          - Q_known_side_W: float — the Q used from the known side

        Raises CalculationError when the system is underdetermined or
        inputs are invalid.
        """
        temps = {
            "T_hot_in_C": T_hot_in_C,
            "T_hot_out_C": T_hot_out_C,
            "T_cold_in_C": T_cold_in_C,
            "T_cold_out_C": T_cold_out_C,
        }
        none_temps = [k for k, v in temps.items() if v is None]

        # --- Special case: all 4 temps known, m_dot_cold missing ---
        if len(none_temps) == 0 and m_dot_cold_kg_s is None:
            if m_dot_hot_kg_s is None:
                raise CalculationError(
                    2,
                    "Both flow rates are missing — system is underdetermined.",
                )
            Q_hot = Step02HeatDuty._compute_Q(
                m_dot_hot_kg_s, cp_hot_J_kgK, T_hot_in_C, T_hot_out_C  # type: ignore[arg-type]
            )
            delta_T_cold = T_cold_out_C - T_cold_in_C  # type: ignore[operator]
            if delta_T_cold == 0:
                raise CalculationError(
                    2,
                    "T_cold_out == T_cold_in — cannot solve for m_dot_cold "
                    "(division by zero).",
                )
            m_dot_cold_calc = Q_hot / (cp_cold_J_kgK * delta_T_cold)
            return {
                "T_hot_in_C": T_hot_in_C,
                "T_hot_out_C": T_hot_out_C,
                "T_cold_in_C": T_cold_in_C,
                "T_cold_out_C": T_cold_out_C,
                "m_dot_cold_kg_s": m_dot_cold_calc,
                "calculated_field": "m_dot_cold_kg_s",
                "Q_known_side_W": Q_hot,
            }

        # --- Exactly 1 missing temperature ---
        if len(none_temps) == 0:
            # All temps known — nothing to calculate
            Q_hot = Step02HeatDuty._compute_Q(
                m_dot_hot_kg_s or 0.0, cp_hot_J_kgK,
                T_hot_in_C, T_hot_out_C,  # type: ignore[arg-type]
            )
            return {
                "T_hot_in_C": T_hot_in_C,
                "T_hot_out_C": T_hot_out_C,
                "T_cold_in_C": T_cold_in_C,
                "T_cold_out_C": T_cold_out_C,
                "calculated_field": None,
                "Q_known_side_W": Q_hot,
            }

        if len(none_temps) > 1:
            raise CalculationError(
                2,
                f"Multiple temperatures missing ({', '.join(none_temps)}) — "
                f"system is underdetermined. Need at least 3 of 4 temps.",
            )

        missing = none_temps[0]

        # Determine Q from the *known* side
        if missing.startswith("T_hot"):
            # Cold side is fully known — compute Q_cold
            if m_dot_cold_kg_s is None:
                raise CalculationError(
                    2,
                    f"{missing} is unknown and m_dot_cold is also missing — "
                    f"cannot compute Q from cold side.",
                )
            Q_known = Step02HeatDuty._compute_Q(
                m_dot_cold_kg_s, cp_cold_J_kgK,
                T_cold_out_C, T_cold_in_C,  # type: ignore[arg-type]
            )
            known_side_label = "cold"
        else:
            # Hot side is fully known — compute Q_hot
            if m_dot_hot_kg_s is None:
                raise CalculationError(
                    2,
                    f"{missing} is unknown and m_dot_hot is also missing — "
                    f"cannot compute Q from hot side.",
                )
            Q_known = Step02HeatDuty._compute_Q(
                m_dot_hot_kg_s, cp_hot_J_kgK,
                T_hot_in_C, T_hot_out_C,  # type: ignore[arg-type]
            )
            known_side_label = "hot"

        # Solve for the missing temperature
        if missing == "T_cold_out_C":
            if m_dot_cold_kg_s is None or m_dot_cold_kg_s == 0:
                raise CalculationError(
                    2,
                    "m_dot_cold is zero or missing — cannot solve for T_cold_out.",
                )
            T_cold_out_C = T_cold_in_C + Q_known / (m_dot_cold_kg_s * cp_cold_J_kgK)  # type: ignore[operator]

        elif missing == "T_cold_in_C":
            if m_dot_cold_kg_s is None or m_dot_cold_kg_s == 0:
                raise CalculationError(
                    2,
                    "m_dot_cold is zero or missing — cannot solve for T_cold_in.",
                )
            T_cold_in_C = T_cold_out_C - Q_known / (m_dot_cold_kg_s * cp_cold_J_kgK)  # type: ignore[operator]

        elif missing == "T_hot_out_C":
            if m_dot_hot_kg_s is None or m_dot_hot_kg_s == 0:
                raise CalculationError(
                    2,
                    "m_dot_hot is zero or missing — cannot solve for T_hot_out.",
                )
            T_hot_out_C = T_hot_in_C - Q_known / (m_dot_hot_kg_s * cp_hot_J_kgK)  # type: ignore[operator]

        elif missing == "T_hot_in_C":
            if m_dot_hot_kg_s is None or m_dot_hot_kg_s == 0:
                raise CalculationError(
                    2,
                    "m_dot_hot is zero or missing — cannot solve for T_hot_in.",
                )
            T_hot_in_C = T_hot_out_C + Q_known / (m_dot_hot_kg_s * cp_hot_J_kgK)  # type: ignore[operator]

        return {
            "T_hot_in_C": T_hot_in_C,
            "T_hot_out_C": T_hot_out_C,
            "T_cold_in_C": T_cold_in_C,
            "T_cold_out_C": T_cold_out_C,
            "calculated_field": missing,
            "Q_known_side_W": Q_known,
        }

    # ------------------------------------------------------------------
    # Placeholder — later pieces will fill these in
    # ------------------------------------------------------------------

    def execute(self, state: "DesignState") -> StepResult:
        """Full execute — wired in Piece 7."""
        raise NotImplementedError("Step02 execute() not yet assembled (Piece 7)")
