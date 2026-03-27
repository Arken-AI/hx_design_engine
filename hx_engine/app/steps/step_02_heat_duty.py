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
    # Piece 4: Conditional AI trigger
    # ------------------------------------------------------------------

    def _conditional_ai_trigger(self, state: "DesignState") -> bool:
        """Trigger AI review when energy balance imbalance > 2%."""
        imbalance = getattr(self, "_imbalance_pct", None)
        return imbalance is not None and imbalance > 2.0

    # ------------------------------------------------------------------
    # Piece 7: Full execute
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Compute heat duty and resolve any missing 4th temperature.

        Flow:
          1. Pre-condition check — need fluid names, T_hot_in, ≥1 flow rate,
             ≥1 cold-side temperature.
          2. Estimate mean temperatures for initial Cp lookup.
          3. Retrieve Cp via thermo adapter for both fluids.
          4. Resolve the missing temperature (if any) via energy balance.
          5. Refine Cp with corrected mean temperatures.
          6. Compute Q from both sides; verify energy balance closure.
          7. Collect corner-case warnings.
          8. Return StepResult (does NOT mutate state directly).
        """
        from hx_engine.app.adapters.thermo_adapter import get_fluid_properties
        from hx_engine.app.core.exceptions import CalculationError

        warnings: list[str] = []

        # --- Pre-condition check ---
        missing_fields: list[str] = []
        if not state.hot_fluid_name:
            missing_fields.append("hot_fluid_name")
        if not state.cold_fluid_name:
            missing_fields.append("cold_fluid_name")
        if state.T_hot_in_C is None:
            missing_fields.append("T_hot_in_C")
        if state.m_dot_hot_kg_s is None and state.m_dot_cold_kg_s is None:
            missing_fields.append("m_dot_hot_kg_s or m_dot_cold_kg_s")
        if state.T_cold_in_C is None and state.T_cold_out_C is None:
            missing_fields.append("T_cold_in_C or T_cold_out_C")
        if missing_fields:
            raise CalculationError(
                2,
                f"Step 2 requires the following from Step 1: "
                f"{', '.join(missing_fields)}",
            )

        # --- Estimate mean temperatures for initial Cp lookup ---
        T_hot_estimate: float = (
            (state.T_hot_in_C + state.T_hot_out_C) / 2.0
            if state.T_hot_out_C is not None
            else state.T_hot_in_C  # type: ignore[assignment]
        )
        cold_known = [t for t in (state.T_cold_in_C, state.T_cold_out_C) if t is not None]
        T_cold_estimate: float = sum(cold_known) / len(cold_known)

        # --- Get Cp from thermo adapter ---
        try:
            _hot = get_fluid_properties(
                state.hot_fluid_name, T_hot_estimate, state.P_hot_Pa
            )
            cp_hot = _hot.cp_J_kgK
        except Exception as exc:
            raise CalculationError(
                2,
                f"Could not get Cp for '{state.hot_fluid_name}' "
                f"at {T_hot_estimate:.1f}°C: {exc}",
            ) from exc

        try:
            _cold = get_fluid_properties(
                state.cold_fluid_name, T_cold_estimate, state.P_cold_Pa
            )
            cp_cold = _cold.cp_J_kgK
        except Exception as exc:
            raise CalculationError(
                2,
                f"Could not get Cp for '{state.cold_fluid_name}' "
                f"at {T_cold_estimate:.1f}°C: {exc}",
            ) from exc

        # Attempt to resolve the missing temperature via energy balance.
        # This may not always be possible — e.g. if T_cold_out is missing AND
        # m_dot_cold is unknown, the system is underdetermined for that unknown.
        # In that case we skip the back-calculation and compute Q from whichever
        # side is fully determined.
        m_hot_sentinel = state.m_dot_hot_kg_s if state.m_dot_hot_kg_s is not None else 1.0

        try:
            temp_result = self._calculate_missing_temp(
                T_hot_in_C=state.T_hot_in_C,
                T_hot_out_C=state.T_hot_out_C,
                T_cold_in_C=state.T_cold_in_C,
                T_cold_out_C=state.T_cold_out_C,
                m_dot_hot_kg_s=m_hot_sentinel,
                m_dot_cold_kg_s=state.m_dot_cold_kg_s,
                cp_hot_J_kgK=cp_hot,
                cp_cold_J_kgK=cp_cold,
            )
        except CalculationError:
            # Underdetermined — build a minimal temp_result from what we know
            temp_result = {
                "calculated_field": None,
                "T_hot_in_C": state.T_hot_in_C,
                "T_hot_out_C": state.T_hot_out_C,
                "T_cold_in_C": state.T_cold_in_C,
                "T_cold_out_C": state.T_cold_out_C,
                "Q_known_side_W": None,
                "m_dot_cold_kg_s": state.m_dot_cold_kg_s,
            }

        T_hot_in: float = temp_result["T_hot_in_C"]
        T_hot_out: float = temp_result["T_hot_out_C"]
        T_cold_in: float = temp_result["T_cold_in_C"]
        T_cold_out: float = temp_result["T_cold_out_C"]

        # --- Refine Cp with better mean temperatures after solving ---
        if (
            temp_result["calculated_field"] is not None
            and T_hot_out is not None
            and T_cold_in is not None
            and T_cold_out is not None
        ):
            T_hot_mean_new = (T_hot_in + T_hot_out) / 2.0
            T_cold_mean_new = (T_cold_in + T_cold_out) / 2.0
            try:
                cp_hot = get_fluid_properties(
                    state.hot_fluid_name, T_hot_mean_new, state.P_hot_Pa
                ).cp_J_kgK
                cp_cold = get_fluid_properties(
                    state.cold_fluid_name, T_cold_mean_new, state.P_cold_Pa
                ).cp_J_kgK
            except Exception:
                pass  # Keep original Cp estimates — non-fatal

        # --- Compute Q from each side ---
        m_dot_hot = state.m_dot_hot_kg_s
        m_dot_cold = temp_result.get("m_dot_cold_kg_s") or state.m_dot_cold_kg_s

        Q_hot: float | None = None
        if m_dot_hot is not None and T_hot_in is not None and T_hot_out is not None:
            Q_hot = self._compute_Q(m_dot_hot, cp_hot, T_hot_in, T_hot_out)

        Q_cold: float | None = None
        if m_dot_cold is not None and T_cold_in is not None and T_cold_out is not None:
            Q_cold = self._compute_Q(m_dot_cold, cp_cold, T_cold_out, T_cold_in)

        # Determine final Q and imbalance
        imbalance_pct: float | None = None
        if Q_hot is not None and Q_cold is not None:
            Q = (Q_hot + Q_cold) / 2.0
            denom = max(abs(Q_hot), abs(Q_cold))
            imbalance_pct = abs(Q_hot - Q_cold) / denom * 100 if denom > 0 else 0.0
        elif Q_hot is not None:
            Q = Q_hot
        elif Q_cold is not None:
            Q = Q_cold
        else:
            raise CalculationError(
                2,
                "Cannot compute Q — insufficient flow rate and temperature data.",
            )

        # --- Validate Q ---
        if Q <= 0:
            raise CalculationError(
                2,
                f"Q={Q:.1f} W is not positive — "
                "verify that the hot stream cools and the cold stream gains heat.",
            )
        if Q > 500e6:
            warnings.append(
                f"Q={Q / 1e6:.1f} MW is very large — verify flow rates and temperatures."
            )

        # Store for conditional AI trigger
        self._imbalance_pct = imbalance_pct

        # Energy balance warning (> 5% implies a data inconsistency)
        if imbalance_pct is not None and imbalance_pct > 5.0:
            warnings.append(
                f"Energy balance imbalance {imbalance_pct:.1f}% — "
                "hot and cold Q values differ significantly. "
                "Check flow rates, temperatures, and Cp assumptions."
            )

        # Corner case: very small hot-side ΔT → small LMTD ahead
        if T_hot_in is not None and T_hot_out is not None:
            dT_hot = T_hot_in - T_hot_out
            if 0 < dT_hot < 5.0:
                warnings.append(
                    f"Hot-side ΔT={dT_hot:.1f}°C is very small — "
                    "LMTD will be small; large exchanger area expected."
                )

        # Corner case: tight approach temperature
        if T_cold_out is not None and T_hot_out is not None:
            approach = T_hot_out - T_cold_out
            if 0 < approach < 5.0:
                warnings.append(
                    f"Approach temperature={approach:.1f}°C is very small — "
                    "may not be thermodynamically achievable; review temperatures."
                )

        outputs: dict = {
            "Q_W": Q,
            "T_hot_in_C": T_hot_in,
            "T_hot_out_C": T_hot_out,
            "T_cold_in_C": T_cold_in,
            "T_cold_out_C": T_cold_out,
        }
        if temp_result["calculated_field"] is not None:
            outputs["calculated_field"] = temp_result["calculated_field"]
        if imbalance_pct is not None:
            outputs["energy_balance_imbalance_pct"] = round(imbalance_pct, 2)
        # Expose solved m_dot_cold if it was back-calculated
        if m_dot_cold is not None and state.m_dot_cold_kg_s is None:
            outputs["m_dot_cold_kg_s"] = m_dot_cold

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            validation_passed=True,
            warnings=warnings,
        )
