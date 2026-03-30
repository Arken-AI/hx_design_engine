"""Step 06 — Initial U + Size Estimate.

Takes a starting-guess U (overall heat transfer coefficient) for the
fluid pair, calculates the required heat transfer area, and maps that
area to a real TEMA-standard shell + tube count.

Core formula:
    A = Q / (U_mid × F × LMTD)
    N_tubes = A / (π × d_o × L)
    → find smallest standard shell that fits N_tubes

ai_mode = CONDITIONAL — AI is only called when:
  1. U_mid came from the default fallback (fluid pair not in table)
  2. Required area > 200 m² (unusually large)
  3. Required area < 1 m² (unusually small)
  4. N_tubes_required exceeds largest available shell capacity
  5. U_mid outside typical range (< 50 or > 3000 W/m²K)
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.data.tema_tables import find_shell_diameter
from hx_engine.app.data.u_assumptions import (
    _U_TABLE,
    classify_fluid_type,
    get_U_assumption,
)
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

# Import rules module so auto-registration fires when step class is loaded
import hx_engine.app.steps.step_06_rules  # noqa: F401

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState


class Step06InitialU(BaseStep):
    """Step 6: Initial U assumption and heat exchanger size estimate."""

    step_id: int = 6
    step_name: str = "Initial U + Size Estimate"
    ai_mode: AIModeEnum = AIModeEnum.CONDITIONAL

    # ------------------------------------------------------------------
    # Pre-condition checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        """Return list of missing fields required from Steps 1–5."""
        missing: list[str] = []
        for field in ("Q_W", "LMTD_K", "F_factor"):
            if getattr(state, field) is None:
                missing.append(field)
        if state.hot_fluid_name is None:
            missing.append("hot_fluid_name")
        if state.cold_fluid_name is None:
            missing.append("cold_fluid_name")
        if state.geometry is None:
            missing.append("geometry")
        else:
            if state.geometry.tube_od_m is None:
                missing.append("geometry.tube_od_m")
            if state.geometry.tube_length_m is None:
                missing.append("geometry.tube_length_m")
            if state.geometry.pitch_layout is None:
                missing.append("geometry.pitch_layout")
            if state.geometry.n_passes is None:
                missing.append("geometry.n_passes")
        return missing

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Compute initial U, required area, and map to TEMA shell + tube count."""

        # 1. Pre-condition checks
        missing = self._check_preconditions(state)
        if missing:
            raise CalculationError(
                6, f"Step 6 requires the following from Steps 1-5: "
                   f"{', '.join(missing)}",
            )

        warnings: list[str] = []

        # 2. Compute effective LMTD
        eff_LMTD = state.F_factor * state.LMTD_K
        if eff_LMTD <= 0:
            raise CalculationError(
                6, f"Effective LMTD = F × LMTD = {state.F_factor} × "
                   f"{state.LMTD_K} = {eff_LMTD:.4f} ≤ 0. "
                   f"Cannot proceed with sizing.",
            )

        # 3. Lookup U assumption
        hot_type = classify_fluid_type(
            state.hot_fluid_name,
            state.hot_fluid_props,
        )
        cold_type = classify_fluid_type(
            state.cold_fluid_name,
            state.cold_fluid_props,
        )
        u_data = get_U_assumption(state.hot_fluid_name, state.cold_fluid_name)
        U_low = u_data["U_low"]
        U_mid = u_data["U_mid"]
        U_high = u_data["U_high"]

        # Detect whether U came from the default fallback
        u_pair_key = (hot_type, cold_type)
        is_fallback = u_pair_key not in _U_TABLE

        if is_fallback:
            warnings.append(
                f"Fluid pair ({hot_type}, {cold_type}) not in U assumption "
                f"table. Using generic liquid-liquid fallback U = {U_mid} W/m²K."
            )

        # 4. Calculate required area
        A_required = state.Q_W / (U_mid * eff_LMTD)

        # 5. Calculate required tube count
        tube_od = state.geometry.tube_od_m
        tube_length = state.geometry.tube_length_m
        N_tubes_required = math.ceil(
            A_required / (math.pi * tube_od * tube_length)
        )

        # 6. Find standard shell
        pitch_layout = state.geometry.pitch_layout
        n_passes = state.geometry.n_passes

        shell_diameter_m, actual_n_tubes = find_shell_diameter(
            N_tubes_required, tube_od, pitch_layout, n_passes,
        )

        # Detect if we hit the largest shell capacity
        at_max_shell = actual_n_tubes < N_tubes_required

        # 7. Update geometry
        # Compute provided area with actual TEMA tube count
        A_provided = actual_n_tubes * math.pi * tube_od * tube_length

        # Recalculate baffle spacing using Step 4's heuristic:
        # 0.5× shell_diameter for viscous shell-side, 0.4× otherwise
        shell_side = state.shell_side_fluid
        shell_mu = None
        if shell_side == "hot" and state.hot_fluid_props is not None:
            shell_mu = state.hot_fluid_props.viscosity_Pa_s
        elif shell_side == "cold" and state.cold_fluid_props is not None:
            shell_mu = state.cold_fluid_props.viscosity_Pa_s

        if shell_mu is not None and shell_mu > 0.001:
            baffle_spacing_m = 0.5 * shell_diameter_m
        else:
            baffle_spacing_m = 0.4 * shell_diameter_m
        baffle_spacing_m = max(0.05, min(2.0, baffle_spacing_m))

        # Build updated geometry (preserve existing fields, override sizing)
        from hx_engine.app.models.design_state import GeometrySpec

        updated_geometry = state.geometry.model_copy(update={
            "n_tubes": actual_n_tubes,
            "shell_diameter_m": shell_diameter_m,
            "baffle_spacing_m": baffle_spacing_m,
        })

        # 8. Collect warnings
        if at_max_shell:
            warnings.append(
                f"Required {N_tubes_required} tubes but largest standard shell "
                f"(37\") holds only {actual_n_tubes}. Consider multiple shells "
                f"in series/parallel."
            )
        if A_required > 500:
            warnings.append(
                f"Very large heat transfer area: {A_required:.1f} m². "
                f"Consider multiple exchangers or different technology."
            )
        elif A_required < 0.5:
            warnings.append(
                f"Very small heat transfer area: {A_required:.4f} m². "
                f"A compact or plate exchanger may be more suitable."
            )

        # 9. Cache values for _conditional_ai_trigger
        self._is_fallback = is_fallback
        self._A_required = A_required
        self._N_tubes_required = N_tubes_required
        self._at_max_shell = at_max_shell
        self._U_mid = U_mid

        # 10. Build escalation hints for AI context
        escalation_hints: list[dict] = []
        if is_fallback:
            escalation_hints.append({
                "trigger": "unclassified_fluid_pair",
                "recommendation": (
                    f"Fluid pair ({hot_type}, {cold_type}) not in U table. "
                    f"Verify U = {U_mid} W/m²K is reasonable for this service."
                ),
            })
        if at_max_shell:
            escalation_hints.append({
                "trigger": "exceeds_max_shell",
                "recommendation": (
                    f"Need {N_tubes_required} tubes but max TEMA shell holds "
                    f"{actual_n_tubes}. Multiple shells may be required."
                ),
            })
        if A_required > 200:
            escalation_hints.append({
                "trigger": "large_area",
                "recommendation": (
                    f"Required area = {A_required:.1f} m² is large. "
                    f"Verify U assumption and consider if U is too conservative."
                ),
            })
        if A_required < 1:
            escalation_hints.append({
                "trigger": "small_area",
                "recommendation": (
                    f"Required area = {A_required:.4f} m² is very small. "
                    f"Verify U assumption is not too aggressive."
                ),
            })

        # 11. Apply results to state
        state.U_W_m2K = U_mid
        state.A_m2 = A_required
        state.geometry = updated_geometry

        # 12. Build result
        outputs: dict = {
            "U_W_m2K": U_mid,
            "A_m2": A_required,
            "U_range": {"U_low": U_low, "U_mid": U_mid, "U_high": U_high},
            "hot_fluid_type": hot_type,
            "cold_fluid_type": cold_type,
            "n_tubes_required": N_tubes_required,
            "A_provided_m2": A_provided,
            "geometry": updated_geometry,
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
    # Conditional AI trigger
    # ------------------------------------------------------------------

    def _conditional_ai_trigger(self, state: "DesignState") -> bool:
        """Trigger AI review for edge cases in U assumption or sizing.

        Returns True if ANY of:
          1. U_mid came from the default fallback (fluid pair not in table)
          2. Required area > 200 m² (unusually large)
          3. Required area < 1 m² (unusually small)
          4. N_tubes_required exceeds largest available shell capacity
          5. U_mid outside typical range (< 50 or > 3000 W/m²K)
        """
        is_fallback = getattr(self, "_is_fallback", False)
        A_required = getattr(self, "_A_required", None)
        at_max_shell = getattr(self, "_at_max_shell", False)
        U_mid = getattr(self, "_U_mid", None)

        if is_fallback:
            return True
        if A_required is not None and A_required > 200:
            return True
        if A_required is not None and A_required < 1:
            return True
        if at_max_shell:
            return True
        if U_mid is not None and (U_mid < 50 or U_mid > 3000):
            return True

        return False
