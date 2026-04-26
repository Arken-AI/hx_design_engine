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
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.data.material_properties import resolve_material_key
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

import hx_engine.app.steps.step_09_rules  # noqa: F401

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Material property defaults (stub until MaterialPropertyAdapter exists)
# ---------------------------------------------------------------------------

_DEFAULT_MATERIAL_K: dict[str, tuple[float, str]] = {
    "carbon_steel":    (50.0,  "Carbon Steel (SA-179/SA-214)"),
    "stainless_304":   (16.2,  "Stainless Steel 304"),
    "stainless_316":   (14.6,  "Stainless Steel 316"),
    "copper":          (385.0, "Copper"),
    "admiralty_brass": (111.0, "Admiralty Brass"),
    "titanium":        (21.9,  "Titanium Gr. 2"),
    "inconel_600":     (14.9,  "Inconel 600"),
    "monel_400":       (21.8,  "Monel 400"),
    "duplex_2205":     (19.0,  "Duplex SS 2205"),
}

_STUB_MATERIAL = "carbon_steel"
_STUB_K_W_MK = 50.0

# ---------------------------------------------------------------------------
# Decision thresholds
# ---------------------------------------------------------------------------

_MIN_CF_WARN = 0.65
_MIN_CF_ESCALATE = 0.50
_MIN_U_ESCALATE_W_M2K = 50.0
_MAX_U_ESTIMATE_DEVIATION_PCT = 30.0
_MAX_KERN_DEVIATION_WARN_PCT = 40.0
_MAX_KERN_DEVIATION_ESCALATE_PCT = 50.0
_MAX_WALL_RESISTANCE_WARN_PCT = 10.0
_WALL_RESISTANCE_DENOMINATOR = 2.0  # log-mean wall resistance: d_o * ln(d_o/d_i) / (2k)

# P2-18 — when μ varies ≥ 5× across ΔT on either side, both Bell-Delaware and
# Kern are weakest as mutual calibration signals. Penalise the cross-method
# agreement weight so Step 16 (and reviewers) see reduced confidence.
_MU_VARIATION_AI_THRESHOLD = 5.0          # mirrors step_03_fluid_props._MU_VARIATION_AI
_CROSS_METHOD_VISCOUS_PENALTY = 0.85      # ×0.85 reliability factor

# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _MaterialProps:
    key: str
    k_wall: float
    source: str
    confidence: float

    @property
    def is_stub(self) -> bool:
        return self.source == "stub_default"


@dataclass
class _Resistances:
    shell_film: float
    tube_film: float
    shell_fouling: float
    tube_fouling: float
    wall: float

    @property
    def total_dirty(self) -> float:
        return (
            self.shell_film + self.tube_film
            + self.shell_fouling + self.tube_fouling
            + self.wall
        )

    @property
    def total_clean(self) -> float:
        return self.shell_film + self.tube_film + self.wall

    def as_breakdown_dict(self) -> dict:
        total = self.total_dirty
        return {
            "shell_film":    {"value_m2KW": self.shell_film,    "pct": self.shell_film    / total * 100.0},
            "tube_film":     {"value_m2KW": self.tube_film,     "pct": self.tube_film     / total * 100.0},
            "shell_fouling": {"value_m2KW": self.shell_fouling, "pct": self.shell_fouling / total * 100.0},
            "tube_fouling":  {"value_m2KW": self.tube_fouling,  "pct": self.tube_fouling  / total * 100.0},
            "wall":          {"value_m2KW": self.wall,          "pct": self.wall          / total * 100.0},
            "total_1_over_U": total,
        }

    def controlling_resistance(self) -> str:
        values = {
            "shell_film": self.shell_film,
            "tube_film": self.tube_film,
            "shell_fouling": self.shell_fouling,
            "tube_fouling": self.tube_fouling,
            "wall": self.wall,
        }
        return max(values, key=values.get)


@dataclass(frozen=True)
class _KernResult:
    u_kern: float | None
    deviation_pct: float | None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _resolve_material(state: "DesignState") -> _MaterialProps:
    """Resolve tube wall material and conductivity from state, falling back to stub defaults."""
    if state.k_wall_W_mK is not None:
        try:
            key = resolve_material_key(state.tube_material or _STUB_MATERIAL)
        except KeyError:
            key = _STUB_MATERIAL
        return _MaterialProps(
            key=key,
            k_wall=state.k_wall_W_mK,
            source=state.k_wall_source or "prior_iteration",
            confidence=state.k_wall_confidence or 0.8,
        )

    mat_key = state.tube_material or _STUB_MATERIAL
    if mat_key in _DEFAULT_MATERIAL_K:
        k_w, _ = _DEFAULT_MATERIAL_K[mat_key]
        return _MaterialProps(key=mat_key, k_wall=k_w, source="stub_default", confidence=0.7)

    return _MaterialProps(key=_STUB_MATERIAL, k_wall=_STUB_K_W_MK, source="stub_default", confidence=0.5)


def _validate_tube_diameters(geometry) -> list[str]:
    """Return precondition errors for tube OD/ID before log(d_o/d_i) is evaluated."""
    errors: list[str] = []
    d_o = geometry.tube_od_m
    d_i = geometry.tube_id_m

    if d_o is None:
        errors.append("geometry.tube_od_m")
    elif d_o <= 0:
        errors.append(f"geometry.tube_od_m must be > 0 (got {d_o:.6f} m)")

    if d_i is None:
        errors.append("geometry.tube_id_m")
    elif d_i <= 0:
        errors.append(f"geometry.tube_id_m must be > 0 (got {d_i:.6f} m)")

    if d_o and d_i and d_o > 0 and d_i > 0 and d_i >= d_o:
        errors.append(
            f"geometry.tube_id_m ({d_i:.6f} m) must be strictly less than "
            f"tube_od_m ({d_o:.6f} m); ln(d_o/d_i) would be <= 0"
        )
    return errors


def _map_fouling_resistances(state: "DesignState") -> tuple[float, float]:
    """Return (R_f_outer, R_f_inner) based on hot/cold shell-side allocation."""
    if state.shell_side_fluid == "hot":
        return state.R_f_hot_m2KW, state.R_f_cold_m2KW
    return state.R_f_cold_m2KW, state.R_f_hot_m2KW


def _compute_resistances(state: "DesignState", mat: _MaterialProps) -> _Resistances:
    """Compute all individual thermal resistances (outer-area reference, m²·K/W)."""
    d_o = state.geometry.tube_od_m
    d_i = state.geometry.tube_id_m
    R_f_outer, R_f_inner = _map_fouling_resistances(state)
    return _Resistances(
        shell_film=1.0 / state.h_shell_W_m2K,
        tube_film=(d_o / d_i) / state.h_tube_W_m2K,
        shell_fouling=R_f_outer,
        tube_fouling=R_f_inner * (d_o / d_i),
        wall=d_o * math.log(d_o / d_i) / (_WALL_RESISTANCE_DENOMINATOR * mat.k_wall),
    )


def _compute_u_and_cf(resistances: _Resistances) -> tuple[float, float, float]:
    """Return (U_dirty, U_clean, cleanliness_factor)."""
    u_dirty = 1.0 / resistances.total_dirty
    u_clean = 1.0 / resistances.total_clean
    cf = u_dirty / u_clean if u_clean > 0 else 0.0
    return u_dirty, u_clean, cf


def _kern_cross_check(
    state: "DesignState", resistances: _Resistances, u_dirty: float
) -> _KernResult:
    """Compute Kern cross-check U and BD/Kern deviation if h_shell_kern is available."""
    if state.h_shell_kern_W_m2K is None:
        return _KernResult(u_kern=None, deviation_pct=None)

    total_kern = (
        1.0 / state.h_shell_kern_W_m2K
        + resistances.tube_film
        + resistances.shell_fouling
        + resistances.tube_fouling
        + resistances.wall
    )
    u_kern = 1.0 / total_kern
    deviation_pct = abs(u_dirty - u_kern) / u_dirty * 100.0 if u_dirty > 0 else None
    return _KernResult(u_kern=u_kern, deviation_pct=deviation_pct)


def _u_vs_estimated_deviation(state: "DesignState", u_dirty: float) -> float | None:
    """Return % deviation of computed U_dirty from the Step 6 initial estimate."""
    if state.U_W_m2K and state.U_W_m2K > 0:
        return (u_dirty - state.U_W_m2K) / state.U_W_m2K * 100.0
    return None


def _update_segment_u_locals(state: "DesignState", resistances: _Resistances) -> None:
    """Compute per-segment U_local and dA for incremental condensation segments."""
    if not state.increment_results:
        return

    d_o = state.geometry.tube_od_m
    d_i = state.geometry.tube_id_m
    for inc in state.increment_results:
        h_shell_seg = inc.h_shell_W_m2K or state.h_shell_W_m2K
        h_tube_seg = inc.h_tube_W_m2K or state.h_tube_W_m2K
        total_seg = (
            1.0 / h_shell_seg
            + (d_o / d_i) / h_tube_seg
            + resistances.shell_fouling
            + resistances.tube_fouling
            + resistances.wall
        )
        inc.U_local_W_m2K = 1.0 / total_seg
        if inc.dQ_W and inc.LMTD_local_K and inc.LMTD_local_K > 0:
            inc.dA_m2 = inc.dQ_W / (inc.U_local_W_m2K * inc.LMTD_local_K)


def _write_results_to_state(
    state: "DesignState",
    u_dirty: float,
    u_clean: float,
    cf: float,
    resistances: _Resistances,
    kern: _KernResult,
    u_vs_estimated: float | None,
) -> None:
    state.U_clean_W_m2K = u_clean
    state.U_dirty_W_m2K = u_dirty
    state.U_overall_W_m2K = u_dirty
    state.cleanliness_factor = cf
    state.resistance_breakdown = resistances.as_breakdown_dict()
    state.controlling_resistance = resistances.controlling_resistance()
    state.U_kern_W_m2K = kern.u_kern
    state.U_kern_deviation_pct = kern.deviation_pct
    state.U_vs_estimated_deviation_pct = u_vs_estimated


def _collect_warnings(
    u_dirty: float,
    cf: float,
    kern: _KernResult,
    u_vs_estimated: float | None,
    resistances: _Resistances,
    mat: _MaterialProps,
) -> list[str]:
    warnings: list[str] = []
    if mat.is_stub:
        warnings.append(
            f"Tube wall conductivity from stub default ({mat.k_wall} W/m·K for "
            f"{mat.key}) — ASME data unavailable, verify material"
        )
    if cf < _MIN_CF_WARN:
        warnings.append(f"Cleanliness factor {cf:.2f} is low — fouling dominates design")
    if kern.deviation_pct is not None and kern.deviation_pct > _MAX_KERN_DEVIATION_WARN_PCT:
        warnings.append(
            f"Bell-Delaware/Kern U deviation: {kern.deviation_pct:.1f}% — "
            "Kern underpredicts h_shell by 40-60% for turbulent liquid flows "
            "(expected); check geometry only if deviation > 40%"
        )
    if u_vs_estimated is not None and abs(u_vs_estimated) > _MAX_U_ESTIMATE_DEVIATION_PCT:
        warnings.append(
            f"Calculated U deviates {u_vs_estimated:.1f}% from "
            "Step 6 estimate — geometry iteration likely needed"
        )
    wall_pct = resistances.wall / resistances.total_dirty * 100.0
    if wall_pct > _MAX_WALL_RESISTANCE_WARN_PCT:
        warnings.append(
            f"Wall resistance is {wall_pct:.1f}% of total — verify tube material selection"
        )
    return warnings


def _escalation_hints(u_dirty: float, cf: float, kern: _KernResult) -> list[dict]:
    hints: list[dict] = []
    if u_dirty < _MIN_U_ESCALATE_W_M2K:
        hints.append({
            "trigger": "very_low_U",
            "recommendation": (
                f"U = {u_dirty:.1f} W/m²K — extremely low for liquid service. "
                "Check fluid properties (viscosity, k) and film coefficients from Steps 7-8."
            ),
        })
    if kern.deviation_pct is not None and kern.deviation_pct > _MAX_KERN_DEVIATION_ESCALATE_PCT:
        hints.append({
            "trigger": "kern_u_divergence",
            "recommendation": (
                f"BD/Kern U deviation {kern.deviation_pct:.1f}% > 50% — "
                "extreme divergence, review geometry inputs"
            ),
        })
    if cf < _MIN_CF_ESCALATE:
        hints.append({
            "trigger": "extreme_fouling",
            "recommendation": (
                f"CF = {cf:.2f} — fouling resistance exceeds all other "
                "resistances combined, review fouling assumptions"
            ),
        })
    return hints


def _build_outputs(
    u_dirty: float,
    u_clean: float,
    cf: float,
    resistances: _Resistances,
    kern: _KernResult,
    u_vs_estimated: float | None,
    mat: _MaterialProps,
    state: "DesignState",
    hints: list[dict],
) -> dict:
    outputs: dict = {
        "U_clean_W_m2K": u_clean,
        "U_dirty_W_m2K": u_dirty,
        "U_overall_W_m2K": u_dirty,
        "cleanliness_factor": cf,
        "resistance_breakdown": resistances.as_breakdown_dict(),
        "controlling_resistance": resistances.controlling_resistance(),
        "tube_material": mat.key,
        "k_wall_W_mK": mat.k_wall,
        "k_wall_source": mat.source,
        "k_wall_confidence": mat.confidence,
        "U_vs_estimated_deviation_pct": u_vs_estimated,
        "tube_od_m": state.geometry.tube_od_m,
        "tube_id_m": state.geometry.tube_id_m,
    }
    if kern.u_kern is not None:
        outputs["U_kern_W_m2K"] = kern.u_kern
        outputs["U_kern_deviation_pct"] = kern.deviation_pct
    if hints:
        outputs["escalation_hints"] = hints
    outputs["cross_method_agreement_weight"] = getattr(state, "cross_method_agreement_weight", 1.0)
    return outputs


def _cross_method_agreement_weight(state: "DesignState") -> float:
    """Return cross-method agreement reliability weight (P2-18).

    Normal services → 1.0. When any side's μ varies ≥ 5× across ΔT,
    BD and Kern are both weakest as calibration signals → 0.85.
    """
    mu_var = getattr(state, "viscosity_variation", None) or {}
    for side_info in mu_var.values():
        if not side_info:
            continue
        if (side_info.get("mu_ratio") or 0.0) >= _MU_VARIATION_AI_THRESHOLD:
            return _CROSS_METHOD_VISCOUS_PENALTY
    return 1.0


class Step09OverallU(BaseStep):
    """Step 9: Overall heat transfer coefficient + resistance breakdown."""

    step_id: int = 9
    step_name: str = "Overall Heat Transfer Coefficient"
    ai_mode: AIModeEnum = AIModeEnum.FULL

    def _should_call_ai(self, state: "DesignState") -> bool:
        return not state.in_convergence_loop

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        missing: list[str] = []
        if state.h_shell_W_m2K is None:
            missing.append("h_shell_W_m2K (Step 8)")
        if state.h_tube_W_m2K is None:
            missing.append("h_tube_W_m2K (Step 7)")
        if state.geometry is None:
            missing.append("geometry (Step 4/6)")
        else:
            missing.extend(_validate_tube_diameters(state.geometry))
        if state.R_f_hot_m2KW is None:
            missing.append("R_f_hot_m2KW (Step 4)")
        if state.R_f_cold_m2KW is None:
            missing.append("R_f_cold_m2KW (Step 4)")
        if state.shell_side_fluid is None:
            missing.append("shell_side_fluid (Step 4)")
        return missing

    @staticmethod
    def _resolve_and_cache_material(state: "DesignState") -> _MaterialProps:
        mat = _resolve_material(state)
        if state.k_wall_W_mK is None:
            state.tube_material = mat.key
            state.k_wall_W_mK = mat.k_wall
            state.k_wall_source = mat.source
            state.k_wall_confidence = mat.confidence
        return mat

    async def execute(self, state: "DesignState") -> StepResult:
        missing = self._check_preconditions(state)
        if missing:
            raise CalculationError(
                9,
                f"Step 9 requires the following from Steps 1-8: {', '.join(missing)}",
            )

        mat = self._resolve_and_cache_material(state)
        resistances = _compute_resistances(state, mat)
        u_dirty, u_clean, cf = _compute_u_and_cf(resistances)
        kern = _kern_cross_check(state, resistances, u_dirty)
        u_vs_estimated = _u_vs_estimated_deviation(state, u_dirty)
        _update_segment_u_locals(state, resistances)
        _write_results_to_state(state, u_dirty, u_clean, cf, resistances, kern, u_vs_estimated)
        warnings = _collect_warnings(u_dirty, cf, kern, u_vs_estimated, resistances, mat)
        hints = _escalation_hints(u_dirty, cf, kern)

        # P2-18 — cross-method reliability penalty for viscous services
        cm_weight = _cross_method_agreement_weight(state)
        state.cross_method_agreement_weight = cm_weight
        if cm_weight < 1.0:
            warnings.append(
                f"Viscous service (μ ratio ≥ {_MU_VARIATION_AI_THRESHOLD:.0f}× on at "
                f"least one side) — Bell-Delaware/Kern cross-method agreement is less "
                f"reliable; cross_method_agreement_weight={cm_weight:.2f}."
            )

        outputs = _build_outputs(u_dirty, u_clean, cf, resistances, kern, u_vs_estimated, mat, state, hints)

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            warnings=warnings,
        )

    def build_ai_context(self, state: "DesignState", result: "StepResult") -> str:
        lines = []
        u_est = state.U_W_m2K
        u_calc = result.outputs.get("U_dirty_W_m2K")
        if u_est is not None and u_calc is not None:
            dev = (u_calc - u_est) / u_est * 100
            lines.append(f"Step 6 estimated U: {u_est:.1f} W/m²K")
            lines.append(f"Calculated U (dirty): {u_calc:.1f} W/m²K")
            lines.append(f"Deviation from estimate: {dev:+.1f}%")
        cf = result.outputs.get("cleanliness_factor")
        if cf is not None:
            lines.append(f"Cleanliness factor: {cf:.3f}")
        ctrl = result.outputs.get("controlling_resistance")
        if ctrl:
            lines.append(f"Controlling resistance: {ctrl}")
        k_src = result.outputs.get("k_wall_source")
        if k_src:
            lines.append(f"Wall conductivity source: {k_src}")
        k_w = result.outputs.get("k_wall_W_mK")
        mat = result.outputs.get("tube_material")
        if k_w is not None and mat:
            lines.append(f"Tube material: {mat} (k_w = {k_w:.1f} W/m·K)")
        return "\n".join(lines)
