"""Step 15 — Cost Estimate (Turton CAPCOST Method).

Post-convergence step that estimates the bare module cost of the heat
exchanger using Turton et al. (2013) Appendix A correlations, adjusted
from 2001 base-year dollars to 2026 via CEPCI.

ai_mode = CONDITIONAL — AI called only if cost/m² falls outside the
per-material typical range, CEPCI is stale (>90 days), area outside
Turton valid range, or material factor was interpolated.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from hx_engine.app.correlations.turton_cost import (
    bare_module_cost,
    cepci_adjust,
    estimate_component_weights,
    interpolated_material_factor,
    pressure_factor,
    purchased_equipment_cost,
)
from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.data.cost_indices import (
    B1,
    B2,
    CEPCI_INDEX,
    CEPCI_STALENESS_THRESHOLD_DAYS,
    MATERIAL_COST_RATIOS,
    PRESSURE_FACTOR_CONSTANTS,
    PRESSURE_FACTOR_MAX_BARG,
    PRESSURE_FACTOR_MIN_BARG,
    get_area_range,
    get_cepci_ratio,
    get_cepci_staleness_days,
    get_cost_per_m2_range,
    get_k_constants,
    get_material_factor,
    get_turton_row,
)
from hx_engine.app.data.material_properties import get_density
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

# Import rules module so auto-registration fires when step class is loaded
import hx_engine.app.steps.step_15_rules  # noqa: F401

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState

logger = logging.getLogger(__name__)

# Atmospheric pressure (Pa)
_ATM_PA = 101_325.0

# Default materials when state fields are not set
_DEFAULT_TUBE_MATERIAL = "carbon_steel"
_DEFAULT_SHELL_MATERIAL = "carbon_steel"

# Default shell wall thickness for weight estimation (8 mm)
_DEFAULT_SHELL_THICKNESS_M = 0.008


class Step15CostEstimate(BaseStep):
    """Step 15: Cost Estimate (Turton CAPCOST Method)."""

    step_id: int = 15
    step_name: str = "Cost Estimate"
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
        if state.cost_breakdown:
            cost_per_m2 = state.cost_breakdown.get("cost_per_m2_usd", 0)
            tube_mat = state.cost_breakdown.get("tube_material", _DEFAULT_TUBE_MATERIAL)
            lo, hi = get_cost_per_m2_range(tube_mat)
            if cost_per_m2 < lo or cost_per_m2 > hi:
                return True
            if state.cost_breakdown.get("cepci_stale", False):
                return True
            if not state.cost_breakdown.get("area_in_valid_range", True):
                return True
            if state.cost_breakdown.get("F_M_interpolated", False):
                return True
        return False

    # ------------------------------------------------------------------
    # Pre-condition checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        missing: list[str] = []
        if state.area_provided_m2 is None:
            missing.append("area_provided_m2 (Step 11)")
        if state.tema_type is None:
            missing.append("tema_type (Step 4)")
        return missing

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Layer 1: Compute bare module cost using Turton correlations."""

        # 1. Precondition check
        missing = self._check_preconditions(state)
        if missing:
            raise CalculationError(
                15,
                f"Step 15 requires: {', '.join(missing)}",
            )

        warnings: list[str] = []

        # 2. Map TEMA type to Turton row
        turton_row = get_turton_row(state.tema_type)
        K1, K2, K3 = get_k_constants(turton_row)

        # 3. Check area validity
        area = state.area_provided_m2
        a_min, a_max = get_area_range(turton_row)
        area_in_valid_range = a_min <= area <= a_max
        if not area_in_valid_range:
            warnings.append(
                f"Area {area:.1f} m² is outside Turton valid range "
                f"({a_min:.0f}–{a_max:.0f} m²) for {turton_row} — "
                f"cost is extrapolated"
            )

        # 4. Compute base purchased cost (C_p^0, 2001 USD)
        Cp0 = purchased_equipment_cost(area, K1, K2, K3)

        # 5. Determine pressures (barg)
        P_shell_Pa = _ATM_PA
        P_tube_Pa = _ATM_PA

        if state.shell_side_fluid == "hot":
            P_shell_Pa = state.P_hot_Pa or _ATM_PA
            P_tube_Pa = state.P_cold_Pa or _ATM_PA
        elif state.shell_side_fluid == "cold":
            P_shell_Pa = state.P_cold_Pa or _ATM_PA
            P_tube_Pa = state.P_hot_Pa or _ATM_PA
        else:
            # Fallback: use whichever pressures are available
            P_shell_Pa = state.P_hot_Pa or _ATM_PA
            P_tube_Pa = state.P_cold_Pa or _ATM_PA

        P_shell_barg = max((P_shell_Pa - _ATM_PA) / 1e5, 0.0)
        P_tube_barg = max((P_tube_Pa - _ATM_PA) / 1e5, 0.0)
        P_design_barg = max(P_shell_barg, P_tube_barg)

        # 6. Pressure factor
        if P_design_barg < PRESSURE_FACTOR_MIN_BARG:
            F_P = 1.0
            pressure_regime = "none"
            C1, C2, C3 = 0.0, 0.0, 0.0
        else:
            # Clamp to 140 barg
            if P_design_barg > PRESSURE_FACTOR_MAX_BARG:
                warnings.append(
                    f"Design pressure {P_design_barg:.1f} barg exceeds "
                    f"Turton maximum ({PRESSURE_FACTOR_MAX_BARG:.0f} barg) "
                    f"— clamped to {PRESSURE_FACTOR_MAX_BARG:.0f}"
                )
                P_design_barg = PRESSURE_FACTOR_MAX_BARG

            # Select regime (D2)
            if P_shell_barg >= PRESSURE_FACTOR_MIN_BARG:
                # Shell pressurized → use "both" (conservative)
                pressure_regime = "both_shell_and_tube"
            else:
                # Only tube side pressurized
                pressure_regime = "tube_only"

            C1, C2, C3 = PRESSURE_FACTOR_CONSTANTS[pressure_regime]
            F_P = pressure_factor(P_design_barg, C1, C2, C3)

        # 7. Material factor
        tube_mat = state.tube_material or _DEFAULT_TUBE_MATERIAL
        shell_mat = state.shell_material or _DEFAULT_SHELL_MATERIAL
        F_M, F_M_interpolated = get_material_factor(shell_mat, tube_mat)

        # If quick lookup was interpolated, try geometry-based interpolation
        if F_M_interpolated and state.geometry is not None:
            g = state.geometry
            shell_thickness = _DEFAULT_SHELL_THICKNESS_M
            if state.mechanical_details:
                shell_info = state.mechanical_details.get("shell", {})
                rec_wall = shell_info.get("recommended_wall_mm")
                if rec_wall:
                    shell_thickness = rec_wall / 1000.0

            try:
                shell_density = get_density(shell_mat)
                tube_density = get_density(tube_mat)
                n_tubes = getattr(g, "n_tubes", None) or 100
                shell_w, tube_w = estimate_component_weights(
                    shell_diameter_m=g.shell_diameter_m,
                    shell_length_m=g.tube_length_m,
                    shell_thickness_m=shell_thickness,
                    shell_density_kg_m3=shell_density,
                    tube_od_m=g.tube_od_m,
                    tube_id_m=g.tube_id_m,
                    tube_length_m=g.tube_length_m,
                    n_tubes=n_tubes,
                    tube_density_kg_m3=tube_density,
                )
                F_M = interpolated_material_factor(
                    shell_mat, tube_mat, shell_w, tube_w, MATERIAL_COST_RATIOS,
                )
            except (KeyError, AttributeError):
                pass  # Fall back to simple average F_M from get_material_factor

            warnings.append(
                f"Material factor F_M={F_M:.2f} is interpolated from cost "
                f"ratios — not from Turton directly "
                f"({shell_mat}/{tube_mat})"
            )

        # 8. Bare module cost (2001 USD)
        bare_module_factor = B1 + B2 * F_M * F_P
        C_BM_2001 = bare_module_cost(Cp0, F_M, F_P, B1, B2)

        # 9. CEPCI adjustment to current year
        cepci_ratio = get_cepci_ratio()
        C_BM_2026 = cepci_adjust(
            C_BM_2001,
            CEPCI_INDEX["current_value"],
            CEPCI_INDEX["base_value"],
        )

        # 10. CEPCI staleness check
        cepci_stale_days = get_cepci_staleness_days()
        cepci_stale = cepci_stale_days > CEPCI_STALENESS_THRESHOLD_DAYS
        if cepci_stale:
            warnings.append(
                f"CEPCI index is {cepci_stale_days} days old "
                f"(threshold: {CEPCI_STALENESS_THRESHOLD_DAYS} days) — "
                f"cost estimate may not reflect current market"
            )

        # 11. Cost per m²
        cost_per_m2 = C_BM_2026 / area

        # 12. Build breakdown
        cost_breakdown = {
            "area_m2": area,
            "turton_row": turton_row,
            "K1": K1,
            "K2": K2,
            "K3": K3,
            "Cp0_2001_usd": round(Cp0, 2),
            "pressure_barg": round(P_design_barg, 2),
            "pressure_regime": pressure_regime,
            "C1": C1,
            "C2": C2,
            "C3": C3,
            "F_P": round(F_P, 4),
            "shell_material": shell_mat,
            "tube_material": tube_mat,
            "F_M": round(F_M, 4),
            "F_M_interpolated": F_M_interpolated,
            "B1": B1,
            "B2": B2,
            "bare_module_factor": round(bare_module_factor, 4),
            "C_BM_2001_usd": round(C_BM_2001, 2),
            "cepci_base_year": CEPCI_INDEX["base_year"],
            "cepci_base_value": CEPCI_INDEX["base_value"],
            "cepci_current_year": CEPCI_INDEX["current_year"],
            "cepci_current_value": CEPCI_INDEX["current_value"],
            "cepci_ratio": round(cepci_ratio, 4),
            "cepci_stale": cepci_stale,
            "cepci_stale_days": cepci_stale_days if cepci_stale else None,
            "C_BM_2026_usd": round(C_BM_2026, 2),
            "cost_per_m2_usd": round(cost_per_m2, 2),
            "area_in_valid_range": area_in_valid_range,
            "warnings": list(warnings),
        }

        # 13. Write to state
        state.cost_usd = round(C_BM_2026, 2)
        state.cost_breakdown = cost_breakdown

        # 14. Build StepResult
        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs={
                "cost_usd": state.cost_usd,
                "cost_breakdown": cost_breakdown,
                "tube_material": tube_mat,
            },
            warnings=warnings,
        )

    def build_ai_context(self, state: "DesignState", result: "StepResult") -> str:
        lines = []
        cost = result.outputs.get("cost_usd")
        bd = result.outputs.get("cost_breakdown") or {}
        if cost is not None:
            lines.append(f"Bare module cost: ${cost:,.0f}")
        cost_m2 = bd.get("cost_per_m2_usd")
        if cost_m2 is not None:
            lines.append(f"Cost/m²: ${cost_m2:,.0f}")
        f_m = bd.get("F_M")
        if f_m is not None:
            lines.append(f"Material factor F_M: {f_m:.4f}")
        f_p = bd.get("F_P")
        if f_p is not None:
            lines.append(f"Pressure factor F_P: {f_p:.4f}")
        if bd.get("cepci_stale"):
            lines.append(f"WARNING: CEPCI index is stale ({bd.get('cepci_stale_days')} days old)")
        if bd.get("F_M_interpolated"):
            lines.append("NOTE: Material factor was interpolated (not directly from Turton)")
        tube_mat = result.outputs.get("tube_material")
        if tube_mat:
            lines.append(f"Tube material: {tube_mat}")
        return "\n".join(lines)
