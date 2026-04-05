"""Step 09 — Overall Heat Transfer Coefficient + Resistance Breakdown.

Aggregates individual thermal resistances from Steps 4-8 into the overall
U value. Computes clean/dirty U, cleanliness factor, resistance breakdown,
controlling resistance, and Kern cross-check U.

ai_mode = FULL — AI is always called (outside convergence loop).
Overrides _should_call_ai() to skip AI when in_convergence_loop=True.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

# Import rules module so auto-registration fires when step class is loaded
import hx_engine.app.steps.step_09_rules  # noqa: F401

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default tube wall conductivities (stub — until MaterialPropertyAdapter exists)
# ---------------------------------------------------------------------------

_DEFAULT_MATERIAL_K: dict[str, tuple[float, str]] = {
    "carbon_steel": (50.0, "Carbon Steel (SA-179/SA-214)"),
    "stainless_304": (16.2, "Stainless Steel 304"),
    "stainless_316": (14.6, "Stainless Steel 316"),
    "copper": (385.0, "Copper"),
    "admiralty_brass": (111.0, "Admiralty Brass"),
    "titanium": (21.9, "Titanium Gr. 2"),
    "inconel_600": (14.9, "Inconel 600"),
    "monel_400": (21.8, "Monel 400"),
    "duplex_2205": (19.0, "Duplex SS 2205"),
}

_STUB_DEFAULT_K = 50.0  # Carbon steel fallback
_STUB_DEFAULT_MATERIAL = "carbon_steel"
_STUB_DEFAULT_LABEL = "Carbon Steel (SA-179/SA-214)"


def _resolve_material(
    state: "DesignState",
) -> tuple[str, float, str, float]:
    """Resolve tube wall material and thermal conductivity.

    Returns (material_name, k_wall_W_mK, source, confidence).

    If k_wall is already on state (from prior iteration or AI correction),
    returns it without re-resolving. Otherwise falls back to stub defaults.
    """
    if state.k_wall_W_mK is not None:
        return (
            state.tube_material or _STUB_DEFAULT_LABEL,
            state.k_wall_W_mK,
            state.k_wall_source or "prior_iteration",
            state.k_wall_confidence or 0.8,
        )

    # Check if tube_material was set by AI correction or user
    mat_key = state.tube_material or _STUB_DEFAULT_MATERIAL
    if mat_key in _DEFAULT_MATERIAL_K:
        k_w, label = _DEFAULT_MATERIAL_K[mat_key]
        return label, k_w, "stub_default", 0.7
    else:
        # Unknown material — use carbon steel + low confidence
        return _STUB_DEFAULT_LABEL, _STUB_DEFAULT_K, "stub_default", 0.5


class Step09OverallU(BaseStep):
    """Step 9: Overall heat transfer coefficient + resistance breakdown."""

    step_id: int = 9
    step_name: str = "Overall Heat Transfer Coefficient"
    ai_mode: AIModeEnum = AIModeEnum.FULL

    # ------------------------------------------------------------------
    # AI call decision — override to skip during convergence
    # ------------------------------------------------------------------

    def _should_call_ai(self, state: "DesignState") -> bool:
        """AI always called outside convergence; skipped inside."""
        if state.in_convergence_loop:
            return False
        return True

    # ------------------------------------------------------------------
    # Pre-condition checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        """Return list of missing fields required from Steps 1-8."""
        missing: list[str] = []

        if state.h_shell_W_m2K is None:
            missing.append("h_shell_W_m2K (Step 8)")
        if state.h_tube_W_m2K is None:
            missing.append("h_tube_W_m2K (Step 7)")
        if state.geometry is None:
            missing.append("geometry (Step 4/6)")
        else:
            if state.geometry.tube_od_m is None:
                missing.append("geometry.tube_od_m")
            if state.geometry.tube_id_m is None:
                missing.append("geometry.tube_id_m")
        if state.R_f_hot_m2KW is None:
            missing.append("R_f_hot_m2KW (Step 4)")
        if state.R_f_cold_m2KW is None:
            missing.append("R_f_cold_m2KW (Step 4)")
        if state.shell_side_fluid is None:
            missing.append("shell_side_fluid (Step 4)")

        return missing

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Layer 1: Pure calculation of overall U and resistance breakdown."""

        # 1. Precondition check
        missing = self._check_preconditions(state)
        if missing:
            raise CalculationError(
                9,
                f"Step 9 requires the following from Steps 1-8: "
                f"{', '.join(missing)}",
            )

        warnings: list[str] = []

        # 2. Resolve tube material and k_wall
        material_name, k_w, k_source, k_confidence = _resolve_material(state)

        # Write material properties to state (cached for convergence iterations)
        if state.k_wall_W_mK is None:
            state.tube_material = material_name
            state.k_wall_W_mK = k_w
            state.k_wall_source = k_source
            state.k_wall_confidence = k_confidence

        if k_source == "stub_default":
            warnings.append(
                f"Tube wall conductivity from stub default ({k_w} W/m·K for "
                f"{material_name}) — ASME data unavailable, verify material"
            )

        # 3. Map fouling resistances to inner/outer
        if state.shell_side_fluid == "hot":
            R_f_outer = state.R_f_hot_m2KW   # shell = hot
            R_f_inner = state.R_f_cold_m2KW  # tube = cold
        else:
            R_f_outer = state.R_f_cold_m2KW  # shell = cold
            R_f_inner = state.R_f_hot_m2KW   # tube = hot

        # 4. Extract tube dimensions
        d_o = state.geometry.tube_od_m
        d_i = state.geometry.tube_id_m
        h_o = state.h_shell_W_m2K
        h_i = state.h_tube_W_m2K

        # 5. Compute individual resistances (all m²·K/W, outer reference)
        R_shell_film = 1.0 / h_o
        R_tube_film = (d_o / d_i) / h_i
        R_shell_foul = R_f_outer
        R_tube_foul = R_f_inner * (d_o / d_i)
        R_wall = d_o * math.log(d_o / d_i) / (2.0 * k_w)

        # 6. Compute 1/U and U
        total_dirty = R_shell_film + R_tube_film + R_shell_foul + R_tube_foul + R_wall
        total_clean = R_shell_film + R_tube_film + R_wall  # no fouling

        U_dirty = 1.0 / total_dirty
        U_clean = 1.0 / total_clean

        # 7. Cleanliness factor
        CF = U_dirty / U_clean if U_clean > 0 else 0.0

        # 8. Resistance breakdown (each as % of total 1/U_dirty)
        resistance_breakdown = {
            "shell_film": {
                "value_m2KW": R_shell_film,
                "pct": (R_shell_film / total_dirty) * 100.0,
            },
            "tube_film": {
                "value_m2KW": R_tube_film,
                "pct": (R_tube_film / total_dirty) * 100.0,
            },
            "shell_fouling": {
                "value_m2KW": R_shell_foul,
                "pct": (R_shell_foul / total_dirty) * 100.0,
            },
            "tube_fouling": {
                "value_m2KW": R_tube_foul,
                "pct": (R_tube_foul / total_dirty) * 100.0,
            },
            "wall": {
                "value_m2KW": R_wall,
                "pct": (R_wall / total_dirty) * 100.0,
            },
            "total_1_over_U": total_dirty,
        }

        # 9. Controlling resistance (largest %)
        resistance_pcts = {
            "shell_film": resistance_breakdown["shell_film"]["pct"],
            "tube_film": resistance_breakdown["tube_film"]["pct"],
            "shell_fouling": resistance_breakdown["shell_fouling"]["pct"],
            "tube_fouling": resistance_breakdown["tube_fouling"]["pct"],
            "wall": resistance_breakdown["wall"]["pct"],
        }
        controlling_resistance = max(resistance_pcts, key=resistance_pcts.get)

        # 10. Kern cross-check U (if h_shell_kern available)
        U_kern: float | None = None
        U_kern_deviation_pct: float | None = None
        if state.h_shell_kern_W_m2K is not None:
            h_o_kern = state.h_shell_kern_W_m2K
            R_shell_film_kern = 1.0 / h_o_kern
            total_dirty_kern = (
                R_shell_film_kern + R_tube_film + R_shell_foul + R_tube_foul + R_wall
            )
            U_kern = 1.0 / total_dirty_kern
            if U_dirty > 0:
                U_kern_deviation_pct = abs(U_dirty - U_kern) / U_dirty * 100.0

        # 11. Deviation from Step 6 estimate
        U_vs_estimated_deviation_pct: float | None = None
        if state.U_W_m2K is not None and state.U_W_m2K > 0:
            U_vs_estimated_deviation_pct = (
                (U_dirty - state.U_W_m2K) / state.U_W_m2K * 100.0
            )

        # 12. Write results to state
        state.U_clean_W_m2K = U_clean
        state.U_dirty_W_m2K = U_dirty
        state.U_overall_W_m2K = U_dirty  # alias
        state.cleanliness_factor = CF
        state.resistance_breakdown = resistance_breakdown
        state.controlling_resistance = controlling_resistance
        state.U_kern_W_m2K = U_kern
        state.U_kern_deviation_pct = U_kern_deviation_pct
        state.U_vs_estimated_deviation_pct = U_vs_estimated_deviation_pct

        # 13. Generate warnings
        if CF < 0.65:
            warnings.append(
                f"Cleanliness factor {CF:.2f} is low — fouling dominates design"
            )

        if U_kern_deviation_pct is not None and U_kern_deviation_pct > 15:
            warnings.append(
                f"Bell-Delaware/Kern U deviation: {U_kern_deviation_pct:.1f}% — "
                "check geometry assumptions"
            )

        if U_vs_estimated_deviation_pct is not None and abs(U_vs_estimated_deviation_pct) > 30:
            warnings.append(
                f"Calculated U deviates {U_vs_estimated_deviation_pct:.1f}% from "
                f"Step 6 estimate — geometry iteration likely needed"
            )

        wall_pct = resistance_breakdown["wall"]["pct"]
        if wall_pct > 10:
            warnings.append(
                f"Wall resistance is {wall_pct:.1f}% of total — "
                "verify tube material selection"
            )

        # 14. Escalation hints
        escalation_hints: list[dict] = []
        if U_dirty < 50:
            escalation_hints.append({
                "trigger": "very_low_U",
                "recommendation": (
                    f"U = {U_dirty:.1f} W/m²K — extremely low, "
                    "check for gas-side controlling resistance"
                ),
            })
        if U_kern_deviation_pct is not None and U_kern_deviation_pct > 25:
            escalation_hints.append({
                "trigger": "kern_u_divergence",
                "recommendation": (
                    f"BD/Kern U deviation {U_kern_deviation_pct:.1f}% > 25% — "
                    "geometry may have issues"
                ),
            })
        if CF < 0.50:
            escalation_hints.append({
                "trigger": "extreme_fouling",
                "recommendation": (
                    f"CF = {CF:.2f} — fouling resistance exceeds all other "
                    "resistances combined, review fouling assumptions"
                ),
            })

        # 15. Build outputs dict
        outputs: dict = {
            "U_clean_W_m2K": U_clean,
            "U_dirty_W_m2K": U_dirty,
            "U_overall_W_m2K": U_dirty,
            "cleanliness_factor": CF,
            "resistance_breakdown": resistance_breakdown,
            "controlling_resistance": controlling_resistance,
            "tube_material": material_name,
            "k_wall_W_mK": k_w,
            "k_wall_source": k_source,
            "k_wall_confidence": k_confidence,
            "U_vs_estimated_deviation_pct": U_vs_estimated_deviation_pct,
        }

        if U_kern is not None:
            outputs["U_kern_W_m2K"] = U_kern
            outputs["U_kern_deviation_pct"] = U_kern_deviation_pct

        if escalation_hints:
            outputs["escalation_hints"] = escalation_hints

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            warnings=warnings,
        )
