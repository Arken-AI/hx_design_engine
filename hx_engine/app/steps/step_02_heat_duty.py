"""Step 02 — Heat Duty Calculation.

Computes Q = ṁ × Cp × ΔT for both fluid sides, calculates the missing
4th temperature if only 3 were provided by Step 1, and verifies energy
balance closure.

ai_mode = CONDITIONAL — AI is only called when anomalies are detected.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Optional

from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState

logger = logging.getLogger(__name__)


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
            _hot = await get_fluid_properties(
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
            _cold = await get_fluid_properties(
                state.cold_fluid_name, T_cold_estimate, state.P_cold_Pa
            )
            cp_cold = _cold.cp_J_kgK
        except Exception as exc:
            raise CalculationError(
                2,
                f"Could not get Cp for '{state.cold_fluid_name}' "
                f"at {T_cold_estimate:.1f}°C: {exc}",
            ) from exc

        # --- Vapor-inlet phase-change path -----------------------------------
        # When the hot-fluid name carries a "vapor" / "vapour" / "gas" suffix,
        # sensible Cp alone is thermodynamically wrong: it produces a wildly
        # non-physical T_hot_out (e.g. −471 °C for ethanol at 1 atm).
        # We intercept here and compute a three-segment condenser balance
        # (desuperheat + condense + optional subcool / partial-condense) using
        # saturation properties from the thermo adapter.
        #
        # Guard rail: if vapor inlet detected but P_hot_Pa is None, we MUST
        # escalate — T_sat, h_fg, and all property evaluations are strongly
        # pressure-dependent and the silent 1-atm fallback in the adapter is
        # a hidden trap.
        condenser_extras: dict = {}       # populated when the latent path fires
        _condenser_temp_result: dict | None = None
        _condenser_Q_W: float | None = None

        _vapor_hint = (state.hot_fluid_name or "").strip().lower()
        # Canonical phase signal first (set by Step 03 / upstream parsers); fall
        # back to the trailing phase descriptor on the fluid name. Suffix list
        # mirrors thermo_adapter._PHASE_SUFFIXES so detection here and name
        # normalisation in the adapter stay in lock-step.
        _hot_phase = (getattr(state, "hot_phase", None) or "").strip().lower()
        _vapor_phase_values = {"vapor", "vapour", "gas", "condensing", "superheated"}
        _liquid_phase_values = {"liquid", "subcooled"}
        _is_hot_vapor = (
            _hot_phase in _vapor_phase_values
            or _vapor_hint.endswith(
                (" vapor", " vapour", " gas", " vapors", " vapours", " gases")
            )
        )

        # --- Saturation-temperature heuristic for implicit vapor detection ------
        # When no explicit phase signal is present (hot_phase unset, fluid name
        # has no phase suffix), probe the saturation temperature. If
        # T_hot_in_C >= T_sat − 5 °C and T_hot_out_C is unknown, the stream is
        # at or above its saturation point and should be treated as a condensing
        # service. Skipped when hot_phase is explicitly "liquid"/"subcooled", or
        # when T_hot_out_C is already known (no need to infer outlet conditions).
        if (
            not _is_hot_vapor
            and _hot_phase not in _liquid_phase_values
            and state.T_hot_out_C is None
            and state.P_hot_Pa is not None
            and state.hot_fluid_name
        ):
            try:
                from hx_engine.app.adapters.thermo_adapter import (
                    get_saturation_props as _gsp_probe,
                )
                _sat_probe = _gsp_probe(state.hot_fluid_name, state.P_hot_Pa)
                _T_sat_probe = float(_sat_probe["T_sat_C"])
                # Inlet at or above saturation → condensing service
                if state.T_hot_in_C >= _T_sat_probe - 5.0:
                    _is_hot_vapor = True
                    warnings.append(
                        f"Hot inlet temperature ({state.T_hot_in_C:.1f}°C) is at or "
                        f"above the saturation temperature ({_T_sat_probe:.1f}°C) for "
                        f"'{state.hot_fluid_name}' at {state.P_hot_Pa:.0f} Pa — "
                        "inferred condensing service. Set hot_phase='liquid' explicitly "
                        "to override this detection."
                    )
            except Exception:
                pass  # Saturation lookup failed — fall through to sensible-Cp path

        if _is_hot_vapor and state.T_hot_out_C is None:
            # Pressure is required for saturation-based calculations.
            if state.P_hot_Pa is None:
                raise CalculationError(
                    2,
                    f"Hot inlet '{state.hot_fluid_name}' appears to be a vapor "
                    "but P_hot_Pa (operating pressure) was not supplied. "
                    "Provide P_hot_Pa so the saturation temperature and latent "
                    "heat can be used in the condenser energy balance. "
                    "Example: P_hot_Pa = 101325 for atmospheric pressure.",
                )
            from hx_engine.app.adapters.thermo_adapter import get_saturation_props as _gsp
            # Narrow try-scope: only the saturation lookup itself can fail with a
            # typed CalculationError (e.g. CoolProp not installed). Everything
            # below is pure arithmetic on validated floats — let any error
            # propagate so it is diagnosable rather than relabelled as a
            # "saturation lookup" failure.
            try:
                _sat = _gsp(state.hot_fluid_name, state.P_hot_Pa)
            except CalculationError as _ce:
                raise CalculationError(
                    2,
                    f"Hot inlet '{state.hot_fluid_name}' is a vapor at "
                    f"P_hot_Pa={state.P_hot_Pa:.0f} Pa, but saturation properties "
                    f"could not be retrieved ({_ce.message}). "
                    "Provide T_hot_out_C explicitly (e.g. the saturation temperature "
                    "or desired subcooled outlet) to proceed.",
                ) from _ce

            _T_sat: float = float(_sat["T_sat_C"])
            _h_fg: float = float(_sat["h_fg"])
            _cp_g: float = float(_sat.get("cp_g") or cp_hot)    # vapor Cp at T_sat
            _cp_f: float = float(_sat.get("cp_f") or 2500.0)    # liquid Cp at T_sat

            # Hard pre-conditions for the condenser energy balance. Silently
            # falling through to the sensible-Cp solver here is the very bug
            # this branch exists to prevent — every missing input must surface
            # as a typed CalculationError(2) that names the missing field.
            if state.m_dot_hot_kg_s is None:
                raise CalculationError(
                    2,
                    f"Vapor hot inlet '{state.hot_fluid_name}' requires "
                    "m_dot_hot_kg_s to solve the condenser energy balance.",
                )
            _missing_cold: list[str] = []
            if state.m_dot_cold_kg_s is None:
                _missing_cold.append("m_dot_cold_kg_s")
            if state.T_cold_in_C is None:
                _missing_cold.append("T_cold_in_C")
            if state.T_cold_out_C is None:
                _missing_cold.append("T_cold_out_C")
            if _missing_cold:
                raise CalculationError(
                    2,
                    f"Vapor hot inlet '{state.hot_fluid_name}' requires a fully "
                    "determined cold side to solve the condenser energy balance. "
                    f"Missing: {', '.join(_missing_cold)}.",
                )
            if _h_fg <= 0:
                raise CalculationError(
                    2,
                    f"Saturation lookup for '{state.hot_fluid_name}' at "
                    f"P={state.P_hot_Pa:.0f} Pa returned h_fg={_h_fg} J/kg "
                    "(supercritical or degenerate). Provide T_hot_out_C "
                    "explicitly to bypass the latent-heat balance.",
                )

            _m_hot: float = state.m_dot_hot_kg_s
            _m_cold: float = state.m_dot_cold_kg_s
            _Q_cold: float = _m_cold * cp_cold * (
                state.T_cold_out_C - state.T_cold_in_C  # type: ignore[operator]
            )

            _T_in: float = state.T_hot_in_C  # type: ignore[assignment]

            # Desuperheat segment (only when T_in is meaningfully above T_sat)
            _Q_desup = (
                _m_hot * _cp_g * (_T_in - _T_sat)
                if _T_in > _T_sat + 0.5 else 0.0
            )
            _Q_cond_full = _m_hot * _h_fg
            _Q_no_subcool = _Q_desup + _Q_cond_full

            if _Q_no_subcool >= _Q_cold:
                # Partial condenser — not all vapor condenses
                _Q_cond_used = max(0.0, _Q_cold - _Q_desup)
                _x_out = max(0.0, 1.0 - _Q_cond_used / _Q_cond_full)
                _T_hot_out_sol = _T_sat
                _basis = (
                    "desuperheat+partial_condense"
                    if _Q_desup > 0 else "partial_condense"
                )
                condenser_extras = {
                    "heat_duty_basis": _basis,
                    "T_sat_C": _T_sat,
                    "lambda_J_kg": _h_fg,
                    "cp_vapor_J_kgK": _cp_g,
                    "cp_liquid_J_kgK": _cp_f,
                    "x_out": round(_x_out, 4),
                }
            else:
                # Full condensation + subcooling
                _Q_subcool = _Q_cold - _Q_no_subcool
                _dT_sub = _Q_subcool / (_m_hot * _cp_f) if _cp_f > 0 else 0.0
                _T_hot_out_sol = _T_sat - _dT_sub
                _basis = (
                    "desuperheat+condense+subcool"
                    if _Q_desup > 0 else "condense+subcool"
                )
                condenser_extras = {
                    "heat_duty_basis": _basis,
                    "T_sat_C": _T_sat,
                    "lambda_J_kg": _h_fg,
                    "cp_vapor_J_kgK": _cp_g,
                    "cp_liquid_J_kgK": _cp_f,
                }

            _condenser_Q_W = _Q_cold
            _condenser_temp_result = {
                "calculated_field": "T_hot_out_C",
                "T_hot_out_C": _T_hot_out_sol,
                "T_hot_in_C": state.T_hot_in_C,
                "T_cold_in_C": state.T_cold_in_C,
                "T_cold_out_C": state.T_cold_out_C,
                "Q_known_side_W": _Q_cold,
            }

        # --- Attempt to resolve the missing temperature via energy balance ---
        # This may not always be possible — e.g. if T_cold_out is missing AND
        # m_dot_cold is unknown, the system is underdetermined for that unknown.
        # In that case we skip the back-calculation and compute Q from whichever
        # side is fully determined.
        m_hot_sentinel = state.m_dot_hot_kg_s if state.m_dot_hot_kg_s is not None else 1.0

        if _condenser_temp_result is not None:
            # Latent-heat path succeeded — use its result directly.
            temp_result = _condenser_temp_result
        else:
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

        # --- Physical bounds check on any solved temperature ----------------
        # Catch runaway sensible-Cp solutions (e.g. T = −471 °C for a
        # condensing vapor) before they corrupt the thermo adapter.
        _calc_field = temp_result.get("calculated_field")
        if _calc_field is not None:
            _solved_val = temp_result.get(_calc_field)
            if _solved_val is not None:
                _sv = float(_solved_val)
                if _sv < -100.0 or _sv > 1500.0:
                    raise CalculationError(
                        2,
                        f"Solved {_calc_field} = {_sv:.1f} °C is outside the "
                        f"physical range [−100, 1500] °C — the sensible-Cp energy "
                        f"balance is likely invalid. For vapor condensation, set "
                        f"hot_phase='vapor' or append ' vapor' to the fluid name "
                        f"to activate the latent-heat balance. Alternatively, "
                        f"supply T_hot_out_C directly.",
                    )

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
                cp_hot = (await get_fluid_properties(
                    state.hot_fluid_name, T_hot_mean_new, state.P_hot_Pa
                )).cp_J_kgK
                cp_cold = (await get_fluid_properties(
                    state.cold_fluid_name, T_cold_mean_new, state.P_cold_Pa
                )).cp_J_kgK
            except Exception:
                pass  # Keep original Cp estimates — non-fatal

        # --- Compute Q from each side ---
        m_dot_hot = state.m_dot_hot_kg_s
        m_dot_cold = temp_result.get("m_dot_cold_kg_s") or state.m_dot_cold_kg_s

        Q_hot_sensible: float | None = None
        if m_dot_hot is not None and T_hot_in is not None and T_hot_out is not None:
            Q_hot_sensible = self._compute_Q(m_dot_hot, cp_hot, T_hot_in, T_hot_out)

        Q_cold_sensible: float | None = None
        if m_dot_cold is not None and T_cold_in is not None and T_cold_out is not None:
            Q_cold_sensible = self._compute_Q(m_dot_cold, cp_cold, T_cold_out, T_cold_in)

        # --- Phase-change detection & latent Q override ---
        # Bare Cp·ΔT is silently wrong for condensers and reboilers because
        # ΔT ≈ 0 produces a near-zero sensible duty while the real duty is
        # m_dot · h_fg · Δx. Detect isothermal phase-change sides, query the
        # saturation backend for h_fg, and replace the sensible Q on that
        # side with the latent contribution.
        # Quality endpoints (x_in, x_out) come from applied_corrections so
        # partial condensers / partial reboilers can be modelled correctly.
        # Default is full phase change: hot 1.0 → 0.0, cold 0.0 → 1.0.
        hot_latent = await self._latent_duty_for_side(
            side="hot",
            fluid_name=state.hot_fluid_name,
            T_in_C=T_hot_in, T_out_C=T_hot_out,
            m_dot_kg_s=m_dot_hot, pressure_Pa=state.P_hot_Pa,
            x_in=self._quality_override(state, "hot_quality_in", 1.0),
            x_out=self._quality_override(state, "hot_quality_out", 0.0),
            warnings=warnings,
        )
        cold_latent = await self._latent_duty_for_side(
            side="cold",
            fluid_name=state.cold_fluid_name,
            T_in_C=T_cold_in, T_out_C=T_cold_out,
            m_dot_kg_s=m_dot_cold, pressure_Pa=state.P_cold_Pa,
            x_in=self._quality_override(state, "cold_quality_in", 0.0),
            x_out=self._quality_override(state, "cold_quality_out", 1.0),
            warnings=warnings,
        )

        # When the three-segment condenser solve produced a Q, use it directly
        # for the hot side (sensible Cp would under-count the latent contribution).
        if _condenser_Q_W is not None:
            Q_hot = _condenser_Q_W
            has_phase_change = True
        else:
            Q_hot = hot_latent["Q_W"] if hot_latent else Q_hot_sensible
            has_phase_change = bool(hot_latent or cold_latent)
        Q_cold = cold_latent["Q_W"] if cold_latent else Q_cold_sensible

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

        # Energy balance warning — phase-change streams tolerate slightly
        # wider imbalance because h_fg backends and sensible Cp come from
        # different correlations.
        imbalance_threshold = 10.0 if has_phase_change else 5.0
        if imbalance_pct is not None and imbalance_pct > imbalance_threshold:
            warnings.append(
                f"Energy balance imbalance {imbalance_pct:.1f}% "
                f"(> {imbalance_threshold:.0f}% phase-aware threshold) — "
                "hot and cold Q values differ significantly. "
                "Check flow rates, temperatures, and Cp/h_fg assumptions."
            )

        # Corner case: very small hot-side ΔT is expected for a condenser,
        # so suppress the small-ΔT warning when the hot side went latent.
        if (
            T_hot_in is not None
            and T_hot_out is not None
            and hot_latent is None
        ):
            dT_hot = T_hot_in - T_hot_out
            if 0 < dT_hot < 5.0:
                warnings.append(
                    f"Hot-side ΔT={dT_hot:.1f}°C is very small — "
                    "LMTD will be small; large exchanger area expected."
                )

        # Corner case: tight approach temperature (minimum terminal approach for countercurrent)
        if T_cold_out is not None and T_hot_out is not None and T_hot_in is not None and T_cold_in is not None:
            approach = min(T_hot_in - T_cold_out, T_hot_out - T_cold_in)
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
            # Condenser-path heat_duty_basis takes priority over the latent-duty label
            "heat_duty_basis": (
                condenser_extras.get("heat_duty_basis")
                or self._duty_basis_label(hot_latent, cold_latent)
            ),
        }
        if hot_latent is not None:
            outputs["hot_h_fg_J_kg"] = hot_latent["h_fg"]
            outputs["hot_duty_mode"] = hot_latent["mode"]
        if cold_latent is not None:
            outputs["cold_h_fg_J_kg"] = cold_latent["h_fg"]
            outputs["cold_duty_mode"] = cold_latent["mode"]
        if temp_result["calculated_field"] is not None:
            outputs["calculated_field"] = temp_result["calculated_field"]
        if imbalance_pct is not None:
            outputs["energy_balance_imbalance_pct"] = round(imbalance_pct, 2)
        # Expose solved m_dot_cold if it was back-calculated
        if m_dot_cold is not None and state.m_dot_cold_kg_s is None:
            outputs["m_dot_cold_kg_s"] = m_dot_cold
        # Include condenser-specific fields (T_sat_C, lambda_J_kg, cp_*, x_out)
        if condenser_extras:
            for _k, _v in condenser_extras.items():
                if _k != "heat_duty_basis":   # already set above
                    outputs[_k] = _v

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            validation_passed=True,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Phase-change duty helpers
    # ------------------------------------------------------------------

    _ISOTHERMAL_DT_THRESHOLD_C: float = 0.5
    _T_SAT_TOLERANCE_C: float = 2.0

    @staticmethod
    def _quality_override(
        state: "DesignState", key: str, default: float,
    ) -> float:
        """Read a quality endpoint from applied_corrections, clamped to [0, 1]."""
        corrections = getattr(state, "applied_corrections", None) or {}
        raw = corrections.get(key, default)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return default
        if value < 0.0 or value > 1.0:
            return default
        return value

    @classmethod
    async def _latent_duty_for_side(
        cls,
        *,
        side: str,
        fluid_name: str,
        T_in_C: float | None,
        T_out_C: float | None,
        m_dot_kg_s: float | None,
        pressure_Pa: float | None,
        x_in: float,
        x_out: float,
        warnings: list[str],
    ) -> dict | None:
        """Return latent duty dict ``{Q_W, h_fg, mode, dx}`` when the side is
        undergoing isothermal phase change, else ``None``.

        ``dx`` is the magnitude of the quality change actually used. Total
        condensation/evaporation gives ``dx = 1.0``; partial phase change
        scales the duty linearly: ``Q = ṁ · h_fg · dx``.

        Phase change is detected when:
          * ΔT on the side is ≤ 0.5°C (near-isothermal service), AND
          * the saturation backend yields T_sat close to the operating
            temperature (|T_mean − T_sat| ≤ 2°C), AND
          * a positive h_fg is available, m_dot is known, and dx > 0.

        Missing pressure is fatal for this path (same reasoning as the
        Step 3 gas-pressure rule), so we fall back to sensible Q and
        surface a warning rather than silently mis-sizing.
        """
        if (
            T_in_C is None
            or T_out_C is None
            or m_dot_kg_s is None
            or not fluid_name
        ):
            return None

        dT = abs(T_in_C - T_out_C)
        if dT > cls._ISOTHERMAL_DT_THRESHOLD_C:
            return None

        # Quality direction: condensing (hot) reduces x; evaporating (cold) raises x.
        dx = (x_in - x_out) if side == "hot" else (x_out - x_in)
        if dx <= 0.0:
            return None

        if pressure_Pa is None:
            warnings.append(
                f"{side.capitalize()} side appears isothermal (ΔT={dT:.2f}°C) but "
                f"P_{side}_Pa is None — latent duty cannot be computed. "
                f"Provide the operating pressure for phase-change service."
            )
            return None

        try:
            from hx_engine.app.adapters.thermo_adapter import get_saturation_props

            sat = get_saturation_props(fluid_name, pressure_Pa)
        except Exception:
            return None

        T_sat_C = sat.get("T_sat_C") if isinstance(sat, dict) else None
        h_fg = sat.get("h_fg") if isinstance(sat, dict) else None
        if T_sat_C is None or h_fg is None or h_fg <= 0:
            return None

        T_mean = 0.5 * (T_in_C + T_out_C)
        if abs(T_mean - T_sat_C) > cls._T_SAT_TOLERANCE_C:
            return None

        mode = "condensing" if side == "hot" else "evaporating"
        Q_W = m_dot_kg_s * h_fg * dx
        partial_note = "" if dx >= 0.999 else f" (Δx={dx:.2f}, partial)"
        warnings.append(
            f"{side.capitalize()} side treated as {mode}{partial_note}: "
            f"Q = ṁ·h_fg·Δx = {m_dot_kg_s:.3f} × {h_fg:.0f} × {dx:.2f} "
            f"= {Q_W / 1e3:.1f} kW (T_sat={T_sat_C:.1f}°C, ΔT={dT:.2f}°C)."
        )
        return {
            "Q_W": Q_W,
            "h_fg": h_fg,
            "mode": mode,
            "T_sat_C": T_sat_C,
            "dx": dx,
        }

    @staticmethod
    def _duty_basis_label(
        hot_latent: dict | None, cold_latent: dict | None,
    ) -> str:
        """Classify the Q basis for downstream steps."""
        if hot_latent is None and cold_latent is None:
            return "sensible"
        if hot_latent is not None and cold_latent is not None:
            return "latent_both"
        if hot_latent is not None:
            return "latent_condensing"
        return "latent_evaporating"

    async def apply_user_override(
        self,
        state: "DesignState",
        option_index: int,
        text: str,
    ) -> Optional[int]:
        # Index-based dispatch for button clicks
        if option_index >= 0:
            if option_index == 0:
                logger.info("[Step2-OptionA] User chose to revise — re-run Step 2 with current state")
                return None
            if option_index == 1:
                state.notes.append(
                    "Step 2: User accepted energy-balance anomaly / "
                    "single-phase approximation — proceeding with current Q."
                )
                logger.info("[Step2-OptionB] User chose to proceed with current values")
                return None
            # option_index >= 2: terminate / out-of-scope
            logger.info("[Step2-OptionC] User chose termination / out-of-scope")
            state.notes.append("Step 2: User confirmed design is outside single-phase scope.")
            return None

        # Regex fallback for free-text
        temp_match = re.search(
            r"(?:T_?(hot|cold)_?(in|out))\s*[=:]\s*([0-9]+\.?[0-9]*)",
            text, re.IGNORECASE,
        )
        if temp_match:
            side = temp_match.group(1).lower()
            direction = temp_match.group(2).lower()
            value = float(temp_match.group(3))
            field = f"T_{side}_{direction}_C"
            if hasattr(state, field):
                old_val = getattr(state, field)
                setattr(state, field, value)
                logger.info("[Step2-Override] %s: %r → %r", field, old_val, value)
            return None

        flow_match = re.search(
            r"(?:m_?dot_?(hot|cold)|mass\s*flow\s*(hot|cold))\s*[=:]\s*([0-9]+\.?[0-9]*)",
            text, re.IGNORECASE,
        )
        if flow_match:
            side = (flow_match.group(1) or flow_match.group(2)).lower()
            value = float(flow_match.group(3))
            field = f"m_dot_{side}_kg_s"
            if hasattr(state, field):
                old_val = getattr(state, field)
                setattr(state, field, value)
                logger.info("[Step2-Override] %s: %r → %r", field, old_val, value)
            return None

        if re.search(r"\bproceed\b|\bcontinue\b|\baccept\b|\bgo ahead\b", text, re.IGNORECASE):
            state.notes.append("Step 2: User chose to proceed despite energy-balance anomaly.")
            logger.info("[Step2-Override] User chose to proceed with current values")
            return None

        return None

    def build_ai_context(self, state: "DesignState", result: "StepResult") -> str:
        q_hot = result.outputs.get("Q_hot_W")
        q_cold = result.outputs.get("Q_cold_W")
        q_w = result.outputs.get("Q_W") or state.Q_W
        imbalance = result.outputs.get("energy_imbalance_pct")
        lines = []
        if q_hot is not None:
            lines.append(f"Q_hot  = {q_hot:.0f} W")
        if q_cold is not None:
            lines.append(f"Q_cold = {q_cold:.0f} W")
        if q_w is not None:
            lines.append(f"Q_used = {q_w:.0f} W")
        if imbalance is not None:
            lines.append(f"Imbalance = {imbalance:.1f}%")
        return "\n".join(lines)
