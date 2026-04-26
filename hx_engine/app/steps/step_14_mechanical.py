"""Step 14 — Mechanical Design Check (ASME BPVC Section VIII Div 1).

Post-convergence check that verifies converged geometry can withstand
operating pressures and thermal stresses. Three independent sub-checks:

  1. Tube wall adequacy — UG-27 (internal) + UG-28 (external / shell-side collapse)
  2. Shell wall adequacy — UG-27 (internal) + pipe schedule lookup + optional UG-28 (vacuum)
  3. Thermal expansion differential — tubes vs shell, checked against TEMA type tolerance

ai_mode = CONDITIONAL — AI called only if P > 30 bar, thickness margin < 20%,
or expansion differential exceeds tolerance for fixed-tubesheet type.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hx_engine.app.correlations.asme_thickness import (
    design_pressure,
    external_pressure_allowable,
    get_corrosion_allowance,
    shell_internal_pressure_thickness,
    thermal_expansion_differential,
    tube_internal_pressure_thickness,
)
from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.data.bwg_gauge import get_wall_thickness
from hx_engine.app.data.material_properties import get_allowable_stress
from hx_engine.app.data.pipe_schedules import find_minimum_schedule, find_nps_for_shell
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

# Import rules module so auto-registration fires when step class is loaded
import hx_engine.app.steps.step_14_rules  # noqa: F401

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState

logger = logging.getLogger(__name__)

# Default materials when state fields are not set
_DEFAULT_TUBE_MATERIAL = "carbon_steel"
_DEFAULT_SHELL_MATERIAL = "sa516_gr70"

# Atmospheric pressure (Pa)
_ATM_PA = 101_325.0

# Weld joint efficiencies (decisions D4)
_E_TUBE = 1.0    # seamless tubes
_E_SHELL = 0.85  # spot-examined longitudinal weld

# Expansion tolerance for fixed tubesheet types (D10)
_FIXED_TUBESHEET_TYPES = {"BEM", "NEN", "BEU"}
_FLOATING_HEAD_TYPES = {"AES", "AEU", "AET", "AEP", "AEW"}
_U_TUBE_TYPES = {"BEU"}
_EXPANSION_TOLERANCE_MM = 3.0


class Step14MechanicalCheck(BaseStep):
    """Step 14: Mechanical Design Check."""

    step_id: int = 14
    step_name: str = "Mechanical Design Check"
    ai_mode: AIModeEnum = AIModeEnum.CONDITIONAL

    # ------------------------------------------------------------------
    # AI call decision
    # ------------------------------------------------------------------

    def _should_call_ai(self, state: "DesignState") -> bool:
        if state.in_convergence_loop:
            return False
        return self._conditional_ai_trigger(state)

    def _conditional_ai_trigger(self, state: "DesignState") -> bool:
        """Return True if AI review is warranted."""
        P_max = max(state.P_hot_Pa or 0, state.P_cold_Pa or 0)
        if P_max > 3e6:  # > 30 bar
            return True
        if state.mechanical_details:
            margin = (
                state.mechanical_details
                .get("tube", {})
                .get("margin_internal_pct", 100)
            )
            if margin < 20:
                return True
            expansion = state.mechanical_details.get("expansion", {})
            if expansion.get("within_tolerance") is False:
                return True
        return False

    # ------------------------------------------------------------------
    # Pre-condition checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        missing: list[str] = []

        # Must have converged geometry
        if state.convergence_converged is None:
            missing.append("convergence_converged (Step 12)")

        if state.geometry is None:
            missing.append("geometry (Step 4/6)")
        else:
            g = state.geometry
            for attr in (
                "tube_od_m", "tube_id_m", "shell_diameter_m",
                "tube_length_m", "baffle_spacing_m",
            ):
                if getattr(g, attr, None) is None:
                    missing.append(f"geometry.{attr}")

        if state.shell_side_fluid is None:
            missing.append("shell_side_fluid (Step 4)")

        return missing

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Layer 1: Run ASME BPVC Section VIII Div 1 mechanical checks."""

        # 1. Precondition check
        missing = self._check_preconditions(state)
        if missing:
            raise CalculationError(
                14,
                f"Step 14 requires: {', '.join(missing)}",
            )

        g = state.geometry
        warnings: list[str] = []

        # 2. Resolve materials
        tube_mat = state.tube_material or _DEFAULT_TUBE_MATERIAL
        shell_mat = state.shell_material or _DEFAULT_SHELL_MATERIAL

        # 3. Determine tube-side vs shell-side pressures
        if state.shell_side_fluid == "hot":
            P_shell_operating = state.P_hot_Pa or _ATM_PA
            P_tube_operating = state.P_cold_Pa or _ATM_PA
            T_mean_shell_C = state.T_mean_hot_C or _mean_temp(
                state.T_hot_in_C, state.T_hot_out_C
            )
            T_mean_tube_C = state.T_mean_cold_C or _mean_temp(
                state.T_cold_in_C, state.T_cold_out_C
            )
        else:
            P_shell_operating = state.P_cold_Pa or _ATM_PA
            P_tube_operating = state.P_hot_Pa or _ATM_PA
            T_mean_shell_C = state.T_mean_cold_C or _mean_temp(
                state.T_cold_in_C, state.T_cold_out_C
            )
            T_mean_tube_C = state.T_mean_hot_C or _mean_temp(
                state.T_hot_in_C, state.T_hot_out_C
            )

        # 4. Design pressures (UG-21)
        P_design_tube = design_pressure(P_tube_operating)
        P_design_shell = design_pressure(P_shell_operating)

        # ============================================================
        # 5. TUBE WALL CHECK
        # ============================================================

        # 5a. Resolve tube wall thickness from BWG gauge
        t_tube_actual_m = (g.tube_od_m - g.tube_id_m) / 2.0
        try:
            t_bwg = get_wall_thickness(g.tube_od_m)
            # Use BWG value if it matches geometry (within 0.1mm tolerance)
            if abs(t_bwg - t_tube_actual_m) < 0.0001:
                t_tube_actual_m = t_bwg
        except (ValueError, KeyError):
            pass  # non-standard tube — use computed wall

        # 5b. Internal pressure (UG-27) — tube-side pressure pushes outward
        S_tube = get_allowable_stress(tube_mat, T_mean_tube_C)
        t_min_tube_int_m = tube_internal_pressure_thickness(
            P_design_tube, g.tube_od_m, S_tube, _E_TUBE,
        )
        tube_margin_int_pct = (
            (t_tube_actual_m - t_min_tube_int_m) / t_min_tube_int_m * 100.0
            if t_min_tube_int_m > 0
            else float("inf")
        )

        # 5c. External pressure (UG-28) — shell-side pressure on tube exterior
        # Unsupported length = baffle spacing (D6)
        L_tube_unsupported = g.baffle_spacing_m
        tube_ext_result = external_pressure_allowable(
            D_o_m=g.tube_od_m,
            t_m=t_tube_actual_m,
            L_m=L_tube_unsupported,
            material=tube_mat,
            temperature_C=T_mean_tube_C,
        )
        # External pressure on tube = shell-side operating pressure
        P_tube_external_applied = P_shell_operating

        tube_ext_adequate = tube_ext_result["P_allowable_Pa"] >= P_tube_external_applied
        tube_thickness_ok = (
            t_tube_actual_m >= t_min_tube_int_m and tube_ext_adequate
        )

        if not tube_thickness_ok:
            if t_tube_actual_m < t_min_tube_int_m:
                warnings.append(
                    f"TUBE WALL INADEQUATE — t_actual={t_tube_actual_m*1000:.2f} mm "
                    f"< t_min={t_min_tube_int_m*1000:.2f} mm (UG-27 internal)"
                )
            if not tube_ext_adequate:
                warnings.append(
                    f"TUBE EXTERNAL PRESSURE INADEQUATE — "
                    f"P_applied={P_tube_external_applied/1e6:.3f} MPa > "
                    f"P_allowable={tube_ext_result['P_allowable_Pa']/1e6:.3f} MPa (UG-28)"
                )
        elif tube_margin_int_pct < 20:
            warnings.append(
                f"Tube wall margin is tight: {tube_margin_int_pct:.1f}% "
                f"(t_actual={t_tube_actual_m*1000:.2f} mm, "
                f"t_min={t_min_tube_int_m*1000:.2f} mm)"
            )

        # ============================================================
        # 6. SHELL WALL CHECK
        # ============================================================

        # 6a. Internal pressure (UG-27)
        S_shell = get_allowable_stress(shell_mat, T_mean_shell_C)
        CA_shell = get_corrosion_allowance(shell_mat)
        R_shell_i = g.shell_diameter_m / 2.0

        t_min_shell_int_m = shell_internal_pressure_thickness(
            P_design_shell, R_shell_i, S_shell, _E_SHELL, CA_shell,
        )

        # 6b. Pipe schedule lookup (D9)
        nps_inches, od_mm = find_nps_for_shell(g.shell_diameter_m)
        t_min_shell_mm = t_min_shell_int_m * 1000.0
        recommended_sch, recommended_wall_mm = find_minimum_schedule(
            nps_inches, t_min_shell_mm,
        )

        shell_thickness_ok = recommended_sch is not None
        if not shell_thickness_ok and nps_inches <= 24:
            warnings.append(
                f"SHELL WALL INADEQUATE — no standard pipe schedule for NPS {nps_inches} "
                f"provides wall ≥ {t_min_shell_mm:.1f} mm (UG-27)"
            )
        elif nps_inches > 24:
            warnings.append(
                f"Shell NPS {nps_inches} > 24 — rolled plate territory. "
                f"Minimum wall = {t_min_shell_mm:.1f} mm per UG-27."
            )
            # For rolled plate, only report t_min; mark as OK if t_min is reasonable
            shell_thickness_ok = t_min_shell_int_m > 0

        # 6c. External pressure (UG-28) — if vacuum detected (D8)
        shell_ext_result = None
        is_vacuum_shell = P_shell_operating < _ATM_PA

        if is_vacuum_shell and recommended_wall_mm is not None:
            # L = tangent-to-tangent ≈ tube length (D7)
            L_shell = g.tube_length_m
            D_o_shell_m = od_mm / 1000.0
            t_shell_m = recommended_wall_mm / 1000.0

            shell_ext_result_raw = external_pressure_allowable(
                D_o_m=D_o_shell_m,
                t_m=t_shell_m,
                L_m=L_shell,
                material=shell_mat,
                temperature_C=T_mean_shell_C,
            )
            P_external_shell = _ATM_PA - P_shell_operating
            shell_ext_adequate = (
                shell_ext_result_raw["P_allowable_Pa"] >= P_external_shell
            )
            shell_ext_result = {
                **shell_ext_result_raw,
                "P_applied_Pa": P_external_shell,
                "adequate": shell_ext_adequate,
            }
            if not shell_ext_adequate:
                shell_thickness_ok = False
                warnings.append(
                    f"SHELL EXTERNAL PRESSURE INADEQUATE — "
                    f"P_applied={P_external_shell/1e6:.3f} MPa > "
                    f"P_allowable={shell_ext_result_raw['P_allowable_Pa']/1e6:.3f} MPa "
                    f"(UG-28 vacuum service)"
                )

        # ============================================================
        # 7. THERMAL EXPANSION CHECK
        # ============================================================

        expansion_result = thermal_expansion_differential(
            tube_material=tube_mat,
            shell_material=shell_mat,
            T_mean_tube_C=T_mean_tube_C,
            T_mean_shell_C=T_mean_shell_C,
            tube_length_m=g.tube_length_m,
        )
        expansion_mm = expansion_result["differential_mm"]

        # Determine tolerance based on TEMA type (D10)
        tema_type = state.tema_type or "BEM"
        tema_upper = tema_type.upper()

        if tema_upper in _U_TUBE_TYPES:
            # U-tube: expansion accommodated by design — skip check
            tolerance_mm = None
            within_tolerance = None
        elif tema_upper in _FLOATING_HEAD_TYPES:
            # Floating head: expansion accommodated — informational only
            tolerance_mm = None
            within_tolerance = None
        elif tema_upper in _FIXED_TUBESHEET_TYPES:
            tolerance_mm = _EXPANSION_TOLERANCE_MM
            within_tolerance = expansion_mm <= tolerance_mm
            if not within_tolerance:
                warnings.append(
                    f"EXPANSION EXCEEDS TOLERANCE — differential={expansion_mm:.2f} mm > "
                    f"tolerance={tolerance_mm:.1f} mm for fixed tubesheet ({tema_type}). "
                    f"Consider switching to floating head (AES) design."
                )
        else:
            # Unknown TEMA type — treat as fixed (conservative)
            tolerance_mm = _EXPANSION_TOLERANCE_MM
            within_tolerance = expansion_mm <= tolerance_mm
            if not within_tolerance:
                warnings.append(
                    f"EXPANSION EXCEEDS TOLERANCE \u2014 differential={expansion_mm:.2f} mm > "
                    f"tolerance={tolerance_mm:.1f} mm for TEMA type {tema_type}"
                )

        # P2-12 — Highly toxic service: remind the engineer to evaluate
        # double-tubesheet construction (set by Step 4 allocator).
        if getattr(state, "requires_double_tubesheet_review", False):
            warnings.append(
                "Double-tubesheet construction recommended for highly toxic "
                "service \u2014 a single tubesheet leak would breach "
                "containment of the toxic stream."
            )

        # P2-16 — Hard guard: Step 4 must finalise the shell ID before
        # mechanical sizing. Without the bundle-to-shell clearance the
        # vessel wall calculations are based on an undersized shell ID.
        if not getattr(state, "shell_id_finalised", False):
            raise CalculationError(
                14,
                "Shell ID was not finalised by Step 4 (bundle-to-shell "
                "clearance not applied) — re-run Step 4 before Step 14.",
            )

        # ============================================================
        # 8. BUILD MECHANICAL DETAILS
        # ============================================================

        mechanical_details = {
            "design_pressure_tube_Pa": P_design_tube,
            "design_pressure_shell_Pa": P_design_shell,
            "tube": {
                "material": tube_mat,
                "t_actual_mm": t_tube_actual_m * 1000.0,
                "t_min_internal_mm": t_min_tube_int_m * 1000.0,
                "margin_internal_pct": round(tube_margin_int_pct, 1),
                "S_Pa": S_tube,
                "E_weld": _E_TUBE,
                "external_pressure": {
                    "D_o_t": tube_ext_result["D_o_t"],
                    "L_D_o": tube_ext_result["L_D_o"],
                    "factor_A": tube_ext_result["factor_A"],
                    "factor_B_MPa": tube_ext_result.get("factor_B_MPa"),
                    "is_elastic": tube_ext_result["is_elastic"],
                    "P_allowable_Pa": tube_ext_result["P_allowable_Pa"],
                    "P_applied_Pa": P_tube_external_applied,
                    "adequate": tube_ext_adequate,
                },
            },
            "shell": {
                "material": shell_mat,
                "nps_inches": nps_inches,
                "od_mm": od_mm,
                "t_min_internal_mm": t_min_shell_mm,
                "recommended_schedule": recommended_sch,
                "recommended_wall_mm": recommended_wall_mm,
                "corrosion_allowance_mm": CA_shell * 1000.0,
                "S_Pa": S_shell,
                "E_weld": _E_SHELL,
                "external_pressure": shell_ext_result,
            },
            "expansion": {
                "dL_tube_mm": expansion_result["dL_tube_mm"],
                "dL_shell_mm": expansion_result["dL_shell_mm"],
                "differential_mm": expansion_mm,
                "tolerance_mm": tolerance_mm,
                "tema_type": tema_type,
                "within_tolerance": within_tolerance,
            },
            "limitations": ["Tubesheet thickness not checked (Phase 1)"],
        }

        # ============================================================
        # 9. WRITE TO STATE
        # ============================================================

        state.tube_thickness_ok = tube_thickness_ok
        state.shell_thickness_ok = shell_thickness_ok
        state.expansion_mm = expansion_mm
        state.mechanical_details = mechanical_details
        if state.shell_material is None:
            state.shell_material = shell_mat

        # ============================================================
        # 10. BUILD STEP RESULT
        # ============================================================

        outputs = {
            "tube_thickness_ok": tube_thickness_ok,
            "shell_thickness_ok": shell_thickness_ok,
            "expansion_mm": round(expansion_mm, 2),
            "mechanical_details": mechanical_details,
        }

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            warnings=warnings,
        )

    def build_ai_context(self, state: "DesignState", result: "StepResult") -> str:
        lines = []
        tube_ok = result.outputs.get("tube_thickness_ok")
        shell_ok = result.outputs.get("shell_thickness_ok")
        expansion = result.outputs.get("expansion_mm")
        mech = result.outputs.get("mechanical_details")
        if tube_ok is not None:
            lines.append(f"Tube thickness OK: {tube_ok}")
        if shell_ok is not None:
            lines.append(f"Shell thickness OK: {shell_ok}")
        if expansion is not None:
            lines.append(f"Thermal expansion: {expansion:.2f} mm")
        if isinstance(mech, dict):
            for comp in ("tube", "shell"):
                info = mech.get(comp, {})
                if isinstance(info, dict):
                    t_act = info.get("actual_wall_mm")
                    t_min = info.get("min_wall_mm")
                    if t_act is not None and t_min is not None:
                        margin = (t_act - t_min) / t_min * 100 if t_min else 0
                        lines.append(
                            f"  {comp}: t_actual={t_act:.2f}mm, "
                            f"t_min={t_min:.2f}mm, margin={margin:.0f}%"
                        )
        if state.tema_type:
            lines.append(f"TEMA type: {state.tema_type}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _mean_temp(T_in: float | None, T_out: float | None) -> float:
    """Return arithmetic mean temperature, defaulting to 100°C if both None."""
    if T_in is not None and T_out is not None:
        return (T_in + T_out) / 2.0
    if T_in is not None:
        return T_in
    if T_out is not None:
        return T_out
    return 100.0
