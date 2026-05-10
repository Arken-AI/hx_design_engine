"""Step 11 — Area and Overdesign.

Computes the required heat transfer area (from calculated U) and compares
it to the provided area (from physical geometry) to yield the overdesign
percentage — the primary convergence signal for Step 12.

ai_mode = CONDITIONAL — AI called when overdesign is outside the
service-appropriate band (P2-23). Skipped in convergence loop.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.data.u_assumptions import classify_fluid_type
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

# Import rules module so auto-registration fires when step class is loaded
import hx_engine.app.steps.step_11_rules  # noqa: F401

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState

logger = logging.getLogger(__name__)

_OVERDESIGN_WARN_HIGH = 40.0   # Warning threshold (retained for excessive overdesign)

# ---------------------------------------------------------------------------
# P2-23 — Service-aware overdesign bands
# Maps service classification → (AI_low%, AI_high%)
# ---------------------------------------------------------------------------
_OVERDESIGN_BANDS: dict[str, tuple[float, float]] = {
    "clean_utility":    (5.0,  15.0),
    "phase_change":     (5.0,  20.0),
    "standard_process": (8.0,  25.0),
    "fouling_service":  (10.0, 35.0),
}

_PHASE_CHANGE_TYPES: frozenset[str] = frozenset({
    "condensing_vapor_water", "condensing_vapor_organic",
    "condensing_vapor_refrigerant",
    "boiling_water", "boiling_organic", "boiling_refrigerant",
})

_FOULING_SERVICE_TYPES: frozenset[str] = frozenset({
    "crude", "heavy_organic", "viscous_oil",
})

_CLEAN_UTILITY_TYPES: frozenset[str] = frozenset({
    "water", "steam",
})

# ---------------------------------------------------------------------------
# P2-24 — Low-velocity fouling paradox thresholds
# ---------------------------------------------------------------------------
_OD_FOULING_TRIGGER = 30.0           # overdesign % to trigger WARN
_OD_FOULING_ESCALATE = 50.0          # overdesign % to trigger ESCALATE
_FOULING_VELOCITY_FLOOR_TUBE = 1.0   # m/s — below this with OD≥30% → WARN
_FOULING_VELOCITY_ESCALATE_TUBE = 0.5  # m/s — below this with OD≥50% → ESCALATE
_FOULING_VELOCITY_FLOOR_SHELL = 0.6  # m/s — shell-side equivalent (informational)
_FOULING_R_F_THRESHOLD = 3.5e-4      # m²·K/W — minimum Rf to consider a fouling service


def _classify_service(state: "DesignState") -> str:
    """Classify the heat exchanger service for overdesign band selection (P2-23)."""
    hot_phase = getattr(state, "hot_phase", None)
    cold_phase = getattr(state, "cold_phase", None)
    hot_type = classify_fluid_type(
        state.hot_fluid_name or "",
        getattr(state, "hot_fluid_props", None),
        phase=hot_phase,
    )
    cold_type = classify_fluid_type(
        state.cold_fluid_name or "",
        getattr(state, "cold_fluid_props", None),
        phase=cold_phase,
    )
    if hot_type in _PHASE_CHANGE_TYPES or cold_type in _PHASE_CHANGE_TYPES:
        return "phase_change"
    if hot_type in _FOULING_SERVICE_TYPES or cold_type in _FOULING_SERVICE_TYPES:
        return "fouling_service"
    if hot_type in _CLEAN_UTILITY_TYPES and cold_type in _CLEAN_UTILITY_TYPES:
        return "clean_utility"
    return "standard_process"


def _low_velocity_fouling_paradox(
    state: "DesignState",
    service_classification: str,
) -> tuple[str | None, str]:
    """Return (severity, message) for the low-velocity fouling paradox (P2-24).

    Severity is None, "warn", or "escalate".  The paradox occurs when excess
    area lowers tube velocity in a fouling service, accelerating deposit growth
    and negating the benefit of the extra margin.

    ``service_classification`` is passed explicitly to avoid re-classifying
    fluids and to skip the check for clean / phase-change services where the
    paradox does not apply.
    """
    if service_classification == "clean_utility":
        return None, ""
    if state.overdesign_pct is None:
        return None, ""

    rf_hot = getattr(state, "R_f_hot_m2KW", None) or 0.0
    rf_cold = getattr(state, "R_f_cold_m2KW", None) or 0.0
    rf_max = max(rf_hot, rf_cold)
    if rf_max < _FOULING_R_F_THRESHOLD:
        return None, ""

    tube_vel = getattr(state, "tube_velocity_m_s", None)
    if tube_vel is None:
        return None, ""

    od = state.overdesign_pct

    if tube_vel < _FOULING_VELOCITY_ESCALATE_TUBE and od >= _OD_FOULING_ESCALATE:
        return "escalate", (
            f"Low-velocity fouling paradox: tube velocity {tube_vel:.2f} m/s "
            f"< {_FOULING_VELOCITY_ESCALATE_TUBE} m/s, overdesign {od:.1f}% "
            f"≥ {_OD_FOULING_ESCALATE:.0f}%, Rf = {rf_max:.2e} m²·K/W — "
            f"excess area reduces velocity and accelerates fouling. "
            f"Reduce tube count or split into multiple shells."
        )
    if tube_vel < _FOULING_VELOCITY_FLOOR_TUBE and od >= _OD_FOULING_TRIGGER:
        return "warn", (
            f"Low-velocity fouling paradox: tube velocity {tube_vel:.2f} m/s "
            f"< {_FOULING_VELOCITY_FLOOR_TUBE} m/s with overdesign {od:.1f}% "
            f"≥ {_OD_FOULING_TRIGGER:.0f}% and Rf = {rf_max:.2e} m²·K/W — "
            f"consider reducing tube count to maintain design velocity."
        )
    return None, ""


class Step11AreaOverdesign(BaseStep):
    """Step 11: Area and Overdesign."""

    step_id: int = 11
    step_name: str = "Area and Overdesign"
    ai_mode: AIModeEnum = AIModeEnum.CONDITIONAL

    # ------------------------------------------------------------------
    # AI call decision
    # ------------------------------------------------------------------

    def _should_call_ai(self, state: "DesignState") -> bool:
        if state.in_convergence_loop:
            return False
        return self._conditional_ai_trigger(state)

    def _conditional_ai_trigger(self, state: "DesignState") -> bool:
        """Call AI when overdesign is outside the service-appropriate band (P2-23)."""
        if state.overdesign_pct is None:
            return False
        # Read from state if execute() already classified the service this run;
        # otherwise fall back to classifying now (e.g. standalone trigger checks).
        service = getattr(state, "service_classification", None) or _classify_service(state)
        ai_low, ai_high = _OVERDESIGN_BANDS[service]
        return state.overdesign_pct < ai_low or state.overdesign_pct > ai_high

    # ------------------------------------------------------------------
    # Pre-condition checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        missing: list[str] = []
        if state.Q_W is None:
            missing.append("Q_W (Step 2)")
        if state.LMTD_K is None:
            missing.append("LMTD_K (Step 5)")
        if state.F_factor is None:
            missing.append("F_factor (Step 5)")
        if state.U_dirty_W_m2K is None:
            missing.append("U_dirty_W_m2K (Step 9)")
        if state.geometry is None:
            missing.append("geometry (Step 4/6)")
        else:
            g = state.geometry
            if g.tube_od_m is None:
                missing.append("geometry.tube_od_m")
            if g.tube_length_m is None:
                missing.append("geometry.tube_length_m")
            if g.n_tubes is None:
                missing.append("geometry.n_tubes")
        return missing

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, state: "DesignState") -> StepResult:
        """Layer 1: Pure calculation of area and overdesign."""

        # 1. Precondition check
        missing = self._check_preconditions(state)
        if missing:
            raise CalculationError(
                11,
                f"Step 11 requires: {', '.join(missing)}",
            )

        warnings: list[str] = []
        g = state.geometry

        # P2-23 — resolve service band early so _conditional_ai_trigger is consistent
        service_classification = _classify_service(state)
        od_band_low, od_band_high = _OVERDESIGN_BANDS[service_classification]

        # 2. Guard against near-zero driving force
        effective_driving = state.F_factor * state.LMTD_K
        if effective_driving < 1e-3:
            raise CalculationError(
                11,
                f"Effective temperature driving force (F × LMTD = "
                f"{state.F_factor:.4f} × {state.LMTD_K:.4f} = "
                f"{effective_driving:.6f}) is essentially zero — "
                f"required area would be infinite.",
            )

        # 3. Compute A_required
        #    For condensation with incremental results, use Σ(dA).
        #    Otherwise: A_required = Q / (U_dirty × F × LMTD).
        if state.increment_results and all(
            inc.dA_m2 is not None for inc in state.increment_results
        ):
            A_required = sum(inc.dA_m2 for inc in state.increment_results)
        else:
            A_required = state.Q_W / (
                state.U_dirty_W_m2K * state.F_factor * state.LMTD_K
            )

        # 4. Compute A_provided = π × d_o × L × N_t × n_shells
        #    Defensive fallback: treat None / 0 n_shells as a single shell so
        #    legacy or partial GeometrySpec instances never collapse area to zero.
        n_shells = g.n_shells or 1
        A_provided = math.pi * g.tube_od_m * g.tube_length_m * g.n_tubes * n_shells

        # 5. Compute overdesign %
        overdesign_pct = (A_provided - A_required) / A_required * 100.0

        # 6. Compute Step 6 vs Step 11 deviation diagnostic
        A_est_vs_req_pct = None
        if state.A_m2 is not None and A_required > 0:
            A_est_vs_req_pct = (state.A_m2 - A_required) / A_required * 100.0

        # 7. Generate warnings
        if overdesign_pct < 0:
            warnings.append(
                f"Exchanger is undersized: overdesign = {overdesign_pct:.1f}% "
                f"(A_provided = {A_provided:.2f} m² across {n_shells} shell(s), "
                f"A_required = {A_required:.2f} m²)"
            )

        if overdesign_pct > _OVERDESIGN_WARN_HIGH:
            warnings.append(
                f"Excessive overdesign: {overdesign_pct:.1f}% > {_OVERDESIGN_WARN_HIGH:.0f}% "
                f"— cost concern"
            )

        if (
            A_est_vs_req_pct is not None
            and abs(A_est_vs_req_pct) > 30
        ):
            warnings.append(
                f"Initial U estimate significantly off: "
                f"Step 6 area deviation = {A_est_vs_req_pct:+.1f}%"
            )

        # 8. P2-24 — low-velocity fouling paradox check
        # WARN is emitted inline; ESCALATE is gated by Layer 2 rule in step_11_rules.py.
        paradox_severity, paradox_msg = _low_velocity_fouling_paradox(
            state, service_classification
        )
        if paradox_severity == "warn":
            warnings.append(paradox_msg)

        # 9. Write to state
        state.area_required_m2 = A_required
        state.area_provided_m2 = A_provided
        state.overdesign_pct = overdesign_pct
        state.A_estimated_vs_required_pct = A_est_vs_req_pct
        state.service_classification = service_classification

        # 10. Build outputs dict
        outputs: dict = {
            "area_required_m2": A_required,
            "area_provided_m2": A_provided,
            "overdesign_pct": overdesign_pct,
            "service_classification": service_classification,
            "overdesign_band_low": od_band_low,
            "overdesign_band_high": od_band_high,
        }
        if A_est_vs_req_pct is not None:
            outputs["A_estimated_vs_required_pct"] = A_est_vs_req_pct
        if paradox_severity is not None:
            outputs["fouling_paradox_severity"] = paradox_severity

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            warnings=warnings,
        )

    def build_ai_context(self, state: "DesignState", result: "StepResult") -> str:
        lines = []
        overdesign = result.outputs.get("overdesign_pct")
        a_req = result.outputs.get("area_required_m2")
        a_prov = result.outputs.get("area_provided_m2")
        u_est = state.U_W_m2K
        u_calc = state.U_overall_W_m2K
        if overdesign is not None:
            lines.append(f"Overdesign = {overdesign:.1f}%")
        if a_req is not None and a_prov is not None:
            lines.append(f"A_required = {a_req:.2f} m², A_provided = {a_prov:.2f} m²")
        if u_est is not None and u_calc is not None:
            dev = (u_calc - u_est) / u_est * 100 if u_est else 0
            lines.append(f"U_estimated = {u_est:.1f}, U_calculated = {u_calc:.1f} ({dev:+.1f}%)")
        return "\n".join(lines)
