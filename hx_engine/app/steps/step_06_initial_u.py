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
        # Check if the AI correction loop has overridden the fluid category
        # (e.g. lubricating oil reclassified as heavy_organic). Use the
        # corrected value so the re-run reflects the updated classification.
        _hot_category_override = (
            state.applied_corrections.get("fluid_category")
            if state.applied_corrections else None
        )
        hot_type = _hot_category_override or classify_fluid_type(
            state.hot_fluid_name,
            state.hot_fluid_props,
        )
        cold_type = classify_fluid_type(
            state.cold_fluid_name,
            state.cold_fluid_props,
        )
        # If the hot_type was overridden by a correction, look up the U table
        # directly using the resolved types instead of re-classifying by name.
        if _hot_category_override:
            u_pair_key = (hot_type, cold_type)
            u_low, u_mid, u_high = _U_TABLE.get(u_pair_key, (100, 250, 400))
            u_data = {"U_low": u_low, "U_mid": u_mid, "U_high": u_high}
        else:
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

        # 6. Find standard shell — with multi-shell support
        pitch_layout = state.geometry.pitch_layout
        n_passes = state.geometry.n_passes

        # --- Multi-shell path (set by user response to a prior escalation) ---
        arrangement = state.multi_shell_arrangement  # "series" | "parallel" | None
        n_shells = 1
        at_max_shell = False

        if arrangement == "parallel":
            # Parallel: split flow and duty equally across 2 shells.
            # Each shell sees half the total tube count requirement and half Q.
            n_shells = 2
            N_tubes_per_shell = math.ceil(N_tubes_required / 2)
            Q_per_shell = state.Q_W / 2  # emitted in outputs for downstream steps
        elif arrangement == "series":
            # Series: each shell handles the full flow and the full temperature
            # program, but shell_passes is raised to 2 (two 1-2 shells in
            # series is the standard TEMA multi-shell approach).
            # Each shell transfers roughly half the total duty.
            n_shells = 2
            N_tubes_per_shell = math.ceil(N_tubes_required / 2)
            Q_per_shell = state.Q_W / 2  # emitted in outputs for downstream steps
        else:
            # Single-shell (default) — use full tube count
            N_tubes_per_shell = N_tubes_required
            Q_per_shell = state.Q_W

        shell_diameter_m, actual_n_tubes = find_shell_diameter(
            N_tubes_per_shell, tube_od, pitch_layout, n_passes,
        )

        # Detect if we still hit the largest shell capacity even after splitting
        at_max_shell = actual_n_tubes < N_tubes_per_shell

        # 7. Update geometry
        # Compute provided area: per-shell tubes × n_shells
        total_actual_n_tubes = actual_n_tubes * n_shells
        A_provided = total_actual_n_tubes * math.pi * tube_od * tube_length

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

        # For series arrangement bump shell_passes to 2 so the F-factor step
        # (Step 5) will recalculate correctly when the convergence loop runs.
        new_shell_passes = 2 if arrangement == "series" else (
            state.geometry.shell_passes or 1
        )

        updated_geometry = state.geometry.model_copy(update={
            "n_tubes": actual_n_tubes,          # tubes per shell
            "shell_diameter_m": shell_diameter_m,
            "baffle_spacing_m": baffle_spacing_m,
            "n_shells": n_shells,
            "shell_passes": new_shell_passes,
        })

        # 8. Collect warnings
        if at_max_shell:
            warnings.append(
                f"Required {N_tubes_per_shell} tubes per shell but largest "
                f"standard shell (37\") holds only {actual_n_tubes}. "
                f"Consider increasing the number of shells or a non-standard shell."
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
        self._N_tubes_per_shell = N_tubes_per_shell
        self._at_max_shell = at_max_shell
        self._U_mid = U_mid
        self._n_shells = n_shells
        self._arrangement = arrangement

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
        if at_max_shell and arrangement is None:
            # Only escalate for multi-shell selection when we haven't already
            # been given an arrangement by the user.
            escalation_hints.append({
                "trigger": "exceeds_max_shell",
                "recommendation": (
                    f"Need {N_tubes_required} tubes but max TEMA shell holds "
                    f"{actual_n_tubes}. Multiple shells required."
                ),
            })
        # Note: large_area check uses total A_required (not per-shell) intentionally.
        # The AI sees both A_required and n_shells in context, so it can reason
        # that 306 m² across 2 shells is 153 m² each — an acceptable size.
        if A_required > 200:
            escalation_hints.append({
                "trigger": "large_area",
                "recommendation": (
                    f"Required area = {A_required:.1f} m² total"
                    + (f" ({A_required / n_shells:.1f} m² per shell across {n_shells} shells)" if n_shells > 1 else "")
                    + ". Verify U assumption and consider if U is too conservative."
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
            "n_tubes_per_shell": N_tubes_per_shell,
            "A_provided_m2": A_provided,
            "n_shells": n_shells,
            "multi_shell_arrangement": arrangement,
            "Q_per_shell_W": Q_per_shell,
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
          4. N_tubes_required exceeds largest available shell capacity AND
             no multi_shell_arrangement has been set yet by the user
          5. U_mid outside typical range (< 50 or > 3000 W/m²K)
        """
        is_fallback = getattr(self, "_is_fallback", False)
        A_required = getattr(self, "_A_required", None)
        at_max_shell = getattr(self, "_at_max_shell", False)
        U_mid = getattr(self, "_U_mid", None)
        arrangement = getattr(self, "_arrangement", None)

        if is_fallback:
            return True
        if A_required is not None and A_required > 200:
            return True
        if A_required is not None and A_required < 1:
            return True
        # Only escalate for multi-shell if the user hasn't already chosen an
        # arrangement — once they pick series/parallel, don't re-escalate.
        if at_max_shell and arrangement is None:
            return True
        if U_mid is not None and (U_mid < 50 or U_mid > 3000):
            return True

        return False
