"""Step 12: Convergence Loop — iterates Steps 7→11 until geometry converges.

NOT a BaseStep subclass. This is a special orchestrator that:
  - Runs Steps 7→8→9→10→11 in a tight loop
  - Adjusts geometry between iterations (hybrid proportional→damped)
  - Checks four convergence criteria simultaneously
  - Calls AI only on convergence failure (post-loop)
  - Emits IterationProgressEvent per iteration (no sub-step events)
"""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Final

from pydantic import BaseModel

from hx_engine.app.core.state_utils import apply_outputs
from hx_engine.app.data.tema_tables import find_shell_diameter, get_tube_count
from hx_engine.app.models.sse_events import (
    IterationProgressEvent,
    StepApprovedEvent,
    StepStartedEvent,
)
from hx_engine.app.models.step_result import (
    AIDecisionEnum,
    AIReview,
    StepResult,
)

if TYPE_CHECKING:
    from hx_engine.app.core.ai_engineer import AIEngineer
    from hx_engine.app.models.design_state import DesignState
    from hx_engine.app.models.design_state import GeometrySpec

logger = logging.getLogger(__name__)


# Sub-step classes — imported lazily inside run() to avoid circular imports.
_SUB_STEP_CLASSES: list[str] = [
    "Step07TubeSideH",
    "Step08ShellSideH",
    "Step09OverallU",
    "Step10PressureDrops",
    "Step11AreaOverdesign",
]

PASSES_SEQUENCE: list[int] = [1, 2, 4, 6, 8]


# Step 4 R5: baffle_spacing_m >= max(0.2 × D_s, 0.05 m)
_BAFFLE_SPACING_ABS_FLOOR_M: Final[float] = 0.05   # TEMA absolute minimum (50 mm)
_BAFFLE_SPACING_MAX_M: Final[float] = 2.0          # TEMA absolute maximum
_BAFFLE_SPACING_TEMA_RATIO: Final[float] = 0.20    # Step 4 R5: B_min >= 0.2 × D_s

# P2-15 — L/D recheck thresholds (mirror Step 4 module constants).
# Re-imported locally to avoid a Step-12 → Step-04 import cycle on
# module load; keep in sync with `step_04_tema_geometry.LD_RATIO_*`.
_LD_RATIO_LOW_WARN: Final[float] = 5.0
_LD_RATIO_HIGH_WARN: Final[float] = 10.0

# P2-17 — Pitch-ratio layout floors (mirror step_04_rules constants).
# Same cycle-avoidance reason as above.
_SQUARE_LAYOUTS: frozenset[str] = frozenset({
    "square", "square_90", "rotated_square", "rotated_square_45",
})
_SQUARE_MIN_PITCH_RATIO: Final[float] = 1.25
_TRIANGULAR_MIN_PITCH_RATIO: Final[float] = 1.20


def _check_pitch_layout_after_adjustment(
    geometry: "GeometrySpec | None",
) -> str | None:
    """Return a WARN string if the pitch ratio violates the layout floor.

    Returns ``None`` when geometry is incomplete or the ratio is valid.
    The correctable=True rule in Step 4 handles auto-correction on the
    next full pipeline pass; this function only surfaces the warning
    inside the convergence-loop iteration record.
    """
    if geometry is None or geometry.pitch_layout is None or geometry.pitch_ratio is None:
        return None
    pr = geometry.pitch_ratio
    layout = geometry.pitch_layout
    if layout in _SQUARE_LAYOUTS and pr < _SQUARE_MIN_PITCH_RATIO:
        return (
            f"pitch_ratio={pr:.3f} now below {_SQUARE_MIN_PITCH_RATIO} "
            f"for {layout} layout after geometry adjustment"
        )
    if layout not in _SQUARE_LAYOUTS and pr < _TRIANGULAR_MIN_PITCH_RATIO:
        return (
            f"pitch_ratio={pr:.3f} now below {_TRIANGULAR_MIN_PITCH_RATIO} "
            f"for {layout} layout after geometry adjustment"
        )
    return None


def _check_ld_band_after_adjustment(
    geometry: "GeometrySpec | None",
) -> str | None:
    """Return a WARN string if a Step-12 adjustment pushed L/D out of band.

    Returns ``None`` when geometry is incomplete or L/D is inside the
    recommended band ``[5, 10]``.  The ESCALATE band ``[3, 15]`` is
    enforced separately by the Step 4 Layer 2 rule.
    """
    if (
        geometry is None
        or geometry.tube_length_m is None
        or geometry.shell_diameter_m is None
        or geometry.shell_diameter_m <= 0
    ):
        return None
    ld = geometry.tube_length_m / geometry.shell_diameter_m
    if ld < _LD_RATIO_LOW_WARN:
        return f"L/D={ld:.2f} now below {_LD_RATIO_LOW_WARN} after geometry adjustment"
    if ld > _LD_RATIO_HIGH_WARN:
        return f"L/D={ld:.2f} now above {_LD_RATIO_HIGH_WARN} after geometry adjustment"
    return None


def _clamp_baffle_spacing(
    spacing_m: float, shell_diameter_m: float | None,
) -> tuple[float, bool]:
    """Returns (clamped_spacing_m, floor_binding); falls back to 50 mm floor when shell_diameter_m is None."""
    floor = _BAFFLE_SPACING_ABS_FLOOR_M
    if shell_diameter_m is not None and shell_diameter_m > 0:
        floor = max(floor, _BAFFLE_SPACING_TEMA_RATIO * shell_diameter_m)
    ceiling = _BAFFLE_SPACING_MAX_M
    clamped = max(floor, min(spacing_m, ceiling))
    floor_binding = spacing_m < floor
    return clamped, floor_binding


def _rescale_secondary_baffles(
    geometry: "GeometrySpec", ratio: float, shell_diameter_m: float | None,
) -> None:
    """Rescale inlet/outlet baffle spacings by ``ratio`` and clamp to TEMA.

    Mutates ``geometry`` in place. Skips fields that are unset. Used by both
    the direct-adjustment branch and the shell-upsize branch so the TEMA
    floor is enforced identically in both paths (single source of truth).
    """
    if geometry.inlet_baffle_spacing_m is not None:
        geometry.inlet_baffle_spacing_m, _ = _clamp_baffle_spacing(
            geometry.inlet_baffle_spacing_m * ratio, shell_diameter_m,
        )
    if geometry.outlet_baffle_spacing_m is not None:
        geometry.outlet_baffle_spacing_m, _ = _clamp_baffle_spacing(
            geometry.outlet_baffle_spacing_m * ratio, shell_diameter_m,
        )


def _format_baffle_change_description(
    old_bs: float | None, new_bs: float, floor_binding: bool,
) -> str:
    """Trajectory string for a baffle-spacing change (e.g. ``150mm→120mm``)."""
    suffix = " (clamped to TEMA floor)" if floor_binding else ""
    if old_bs:
        return f"baffle_spacing {old_bs*1000:.0f}mm→{new_bs*1000:.0f}mm{suffix}"
    return f"baffle_spacing→{new_bs*1000:.0f}mm{suffix}"


def _load_sub_steps() -> list[type]:
    """Lazy-import sub-step classes to break circular imports."""
    from hx_engine.app.steps.step_07_tube_side_h import Step07TubeSideH
    from hx_engine.app.steps.step_08_shell_side_h import Step08ShellSideH
    from hx_engine.app.steps.step_09_overall_u import Step09OverallU
    from hx_engine.app.steps.step_10_pressure_drops import Step10PressureDrops
    from hx_engine.app.steps.step_11_area_overdesign import Step11AreaOverdesign

    return [
        Step07TubeSideH,
        Step08ShellSideH,
        Step09OverallU,
        Step10PressureDrops,
        Step11AreaOverdesign,
    ]


class Step12Convergence:
    """Step 12: Convergence Loop — iterates Steps 7→11 until geometry converges."""

    step_id: int = 12
    step_name: str = "Convergence Loop"

    # --- Convergence thresholds ---
    MAX_ITERATIONS: int = 20
    DELTA_U_THRESHOLD: float = 1.0       # % change in U_dirty between iterations
    OVERDESIGN_LOW: float = 10.0         # % minimum overdesign
    OVERDESIGN_HIGH: float = 25.0        # % maximum overdesign
    DP_TUBE_LIMIT: float = 70_000.0      # Pa (0.7 bar)
    DP_SHELL_LIMIT: float = 140_000.0    # Pa (1.4 bar)
    VELOCITY_LOW_LIQUID: float = 0.8     # m/s — liquid tube-side
    VELOCITY_HIGH_LIQUID: float = 2.5    # m/s — liquid tube-side
    VELOCITY_LOW_GAS: float = 5.0        # m/s — gas tube-side
    VELOCITY_HIGH_GAS: float = 30.0      # m/s — gas tube-side

    def _velocity_limits(self, state: "DesignState") -> tuple[float, float]:
        """Return (v_low, v_high) based on tube-side phase."""
        shell_side = getattr(state, "shell_side_fluid", None) or "hot"
        tube_side = "cold" if shell_side == "hot" else "hot"
        tube_phase = (
            getattr(state, "hot_phase", None) if tube_side == "hot"
            else getattr(state, "cold_phase", None)
        ) or "liquid"
        if tube_phase == "vapor":
            return self.VELOCITY_LOW_GAS, self.VELOCITY_HIGH_GAS
        return self.VELOCITY_LOW_LIQUID, self.VELOCITY_HIGH_LIQUID

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        state: "DesignState",
        ai_engineer: "AIEngineer",
        emit_event: Callable[[BaseModel], Awaitable[None]],
    ) -> StepResult:
        """Run the convergence loop.

        Returns a StepResult whose ``outputs`` contain either:
        - A converged summary (normal case)
        - ``convergence_action: "restart"`` with ``restart_from_step`` (structural change)
        """
        sub_steps = _load_sub_steps()
        prev_U: float | None = None
        last_direction: dict[str, int] = {}
        converged = False

        state.in_convergence_loop = True
        try:
            for iteration in range(1, self.MAX_ITERATIONS + 1):
                # --- run Steps 7→11 ---
                substep_failed = False
                for step_cls in sub_steps:
                    step = step_cls()
                    try:
                        result = await step.run_with_review_loop(state, ai_engineer)
                    except Exception:
                        logger.exception(
                            "Step 12 iteration %d: sub-step %s raised",
                            iteration, step_cls.__name__,
                        )
                        substep_failed = True
                        break
                    apply_outputs(state, result)

                    if not result.validation_passed:
                        logger.warning(
                            "Step 12 iteration %d: sub-step %s Layer 2 fail: %s",
                            iteration, step_cls.__name__,
                            result.validation_errors,
                        )
                        substep_failed = True
                        break

                # --- extract metrics ---
                current_U = getattr(state, "U_dirty_W_m2K", None)
                delta_U_pct = self._compute_delta_U(current_U, prev_U)
                prev_U = current_U

                # --- store trajectory snapshot ---
                snapshot = self._build_snapshot(state, iteration, delta_U_pct, substep_failed)
                state.convergence_trajectory.append(snapshot)

                # --- emit SSE event ---
                constraints_met = (
                    not substep_failed
                    and self._check_convergence(state, delta_U_pct)
                )
                adjustment_desc = ""
                await emit_event(
                    IterationProgressEvent(
                        session_id="",
                        iteration_number=iteration,
                        max_iterations=self.MAX_ITERATIONS,
                        current_U=current_U,
                        delta_U_pct=delta_U_pct,
                        constraints_met=constraints_met,
                        overdesign_pct=getattr(state, "overdesign_pct", None),
                        dP_tube_pct_of_limit=(
                            (state.dP_tube_Pa / self.DP_TUBE_LIMIT) * 100
                            if state.dP_tube_Pa is not None
                            else None
                        ),
                        dP_shell_pct_of_limit=(
                            (state.dP_shell_Pa / self.DP_SHELL_LIMIT) * 100
                            if state.dP_shell_Pa is not None
                            else None
                        ),
                        velocity_m_s=getattr(state, "tube_velocity_m_s", None),
                        adjustment_made=None,  # filled after adjustment below
                    )
                )

                # --- check convergence ---
                if constraints_met:
                    converged = True
                    state.convergence_iteration = iteration
                    state.convergence_converged = True
                    break

                # --- compute and apply geometry adjustment ---
                violations = self._detect_violations(state, substep_failed)
                changes, last_direction = self._compute_adjustment(
                    state, iteration, violations, last_direction,
                )
                adjustment_desc = self._apply_adjustment(state, changes)

                # Update the last trajectory entry with adjustment info
                state.convergence_trajectory[-1]["adjustment"] = adjustment_desc

                logger.info(
                    "Step 12 iteration %d: ΔU=%.2f%%, overdesign=%.1f%%, "
                    "dP_tube=%.0f Pa, dP_shell=%.0f Pa, v=%.2f m/s → %s",
                    iteration,
                    delta_U_pct if delta_U_pct is not None else -1,
                    state.overdesign_pct if state.overdesign_pct is not None else -1,
                    state.dP_tube_Pa if state.dP_tube_Pa is not None else -1,
                    state.dP_shell_Pa if state.dP_shell_Pa is not None else -1,
                    state.tube_velocity_m_s if state.tube_velocity_m_s is not None else -1,
                    adjustment_desc,
                )

        finally:
            # CG1A guarantee — flag ALWAYS cleared
            state.in_convergence_loop = False

        # --- post-convergence ---
        if converged:
            # Re-run Steps 7→11 with AI enabled for final review
            await self._post_convergence_ai_pass(state, ai_engineer, emit_event, sub_steps)
            return StepResult(
                step_id=self.step_id,
                step_name=self.step_name,
                outputs={
                    "convergence_iteration": state.convergence_iteration,
                    "convergence_converged": True,
                    "convergence_restart_count": state.convergence_restart_count,
                },
            )

        # --- non-convergence: AI structural suggestion + ESCALATE ---
        state.convergence_converged = False
        state.convergence_iteration = self.MAX_ITERATIONS
        return await self._handle_non_convergence(state, ai_engineer)

    # ------------------------------------------------------------------
    # Convergence criteria
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_delta_U(current_U: float | None, prev_U: float | None) -> float | None:
        """Percentage change in U_dirty between iterations."""
        if current_U is None or prev_U is None or prev_U == 0:
            return None
        return abs(current_U - prev_U) / prev_U * 100

    def _check_convergence(self, state: "DesignState", delta_U_pct: float | None) -> bool:
        """Return True when ALL four criteria are met simultaneously.

        Minimum 2 iterations required (delta_U_pct is None on first iter).
        """
        if delta_U_pct is None:
            return False
        if delta_U_pct >= self.DELTA_U_THRESHOLD:
            return False
        if state.overdesign_pct is None:
            return False
        if not (self.OVERDESIGN_LOW <= state.overdesign_pct <= self.OVERDESIGN_HIGH):
            return False
        if state.dP_tube_Pa is None or state.dP_tube_Pa > self.DP_TUBE_LIMIT:
            return False
        if state.dP_shell_Pa is None or state.dP_shell_Pa > self.DP_SHELL_LIMIT:
            return False
        if state.tube_velocity_m_s is None:
            return False
        v_low, v_high = self._velocity_limits(state)
        if not (v_low <= state.tube_velocity_m_s <= v_high):
            return False
        return True

    # ------------------------------------------------------------------
    # Violation detection (priority order)
    # ------------------------------------------------------------------

    def _detect_violations(
        self,
        state: "DesignState",
        substep_failed: bool = False,
    ) -> list[str]:
        """Return violation types in priority order."""
        violations: list[str] = []

        if substep_failed:
            violations.append("substep_failed")

        # Priority 1: Pressure drop violations (hard constraint)
        if state.dP_tube_Pa is not None and state.dP_tube_Pa > self.DP_TUBE_LIMIT:
            violations.append("dP_tube_high")
        if state.dP_shell_Pa is not None and state.dP_shell_Pa > self.DP_SHELL_LIMIT:
            violations.append("dP_shell_high")

        # Priority 2: Overdesign (primary convergence signal)
        if state.overdesign_pct is not None:
            if state.overdesign_pct < self.OVERDESIGN_LOW:
                violations.append("underdesign")
            elif state.overdesign_pct > self.OVERDESIGN_HIGH:
                violations.append("overdesign")

        # Priority 3: Velocity (phase-aware thresholds)
        if state.tube_velocity_m_s is not None:
            v_low, v_high = self._velocity_limits(state)
            if state.tube_velocity_m_s < v_low:
                violations.append("velocity_low")
            elif state.tube_velocity_m_s > v_high:
                violations.append("velocity_high")

        return violations

    # ------------------------------------------------------------------
    # Geometry adjustment algorithm (hybrid proportional → damped)
    # ------------------------------------------------------------------

    def _compute_adjustment(
        self,
        state: "DesignState",
        iteration: int,
        violations: list[str],
        last_direction: dict[str, int],
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """Return (changes_dict, updated_last_direction).

        Iterations 1-2: proportional scaling (fast convergence).
        Iterations 3+:  damped steps (stability, oscillation damping).
        """
        changes: dict[str, Any] = {}
        new_direction: dict[str, int] = dict(last_direction)
        g = state.geometry

        if not violations or g is None:
            return changes, new_direction

        primary = violations[0]

        # Skip substep_failed — use conservative damped step
        if primary == "substep_failed":
            primary = violations[1] if len(violations) > 1 else "underdesign"

        # --- PROPORTIONAL MODE (iterations 1-2) ---
        if iteration <= 2:
            changes, new_direction = self._proportional_adjustment(
                state, primary, new_direction,
            )
        # --- DAMPED MODE (iterations 3+) ---
        else:
            changes, new_direction = self._damped_adjustment(
                state, primary, last_direction, new_direction,
            )

        # --- n_passes adjustment (discrete) ---
        n_passes_change = self._check_n_passes_adjustment(state, violations, changes)
        if n_passes_change is not None:
            changes["n_passes"] = n_passes_change

        return changes, new_direction

    def _proportional_adjustment(
        self,
        state: "DesignState",
        primary: str,
        new_direction: dict[str, int],
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """Proportional scaling for iterations 1-2."""
        changes: dict[str, Any] = {}
        g = state.geometry
        assert g is not None

        if primary in ("underdesign", "overdesign"):
            if (
                state.area_required_m2 is not None
                and state.area_provided_m2 is not None
                and state.area_provided_m2 > 0
            ):
                ratio = state.area_required_m2 / state.area_provided_m2
                new_n = int(round(g.n_tubes * ratio))
                changes["n_tubes"] = max(1, new_n)
                new_direction["n_tubes"] = 1 if ratio > 1 else -1

        elif primary == "dP_tube_high":
            if state.dP_tube_Pa is not None and state.dP_tube_Pa > 0:
                ratio = math.sqrt(state.dP_tube_Pa / self.DP_TUBE_LIMIT)
                new_n = int(round(g.n_tubes * ratio))
                changes["n_tubes"] = max(1, new_n)
                new_direction["n_tubes"] = 1

        elif primary == "dP_shell_high":
            if (
                g.baffle_spacing_m is not None
                and g.shell_diameter_m is not None
                and state.dP_shell_Pa is not None
                and state.dP_shell_Pa > 0
            ):
                ratio = math.sqrt(state.dP_shell_Pa / self.DP_SHELL_LIMIT)
                new_spacing = g.baffle_spacing_m * ratio
                max_spacing = g.shell_diameter_m * 1.0
                changes["baffle_spacing_m"] = min(new_spacing, max_spacing)
                new_direction["baffle_spacing_m"] = 1

        elif primary == "velocity_low":
            # Need higher velocity → fewer tubes or more passes
            if g.n_tubes is not None and g.n_tubes > 1:
                new_n = max(1, int(round(g.n_tubes * 0.85)))
                changes["n_tubes"] = new_n
                new_direction["n_tubes"] = -1

        elif primary == "velocity_high":
            # Need lower velocity → more tubes
            if g.n_tubes is not None:
                new_n = int(round(g.n_tubes * 1.15))
                changes["n_tubes"] = max(1, new_n)
                new_direction["n_tubes"] = 1

        return changes, new_direction

    def _damped_adjustment(
        self,
        state: "DesignState",
        primary: str,
        last_direction: dict[str, int],
        new_direction: dict[str, int],
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """Damped 5% steps for iterations 3+, with oscillation damping."""
        changes: dict[str, Any] = {}
        g = state.geometry
        assert g is not None

        step_pct = 0.05  # 5% base step

        if primary in ("underdesign", "dP_tube_high", "velocity_high"):
            direction = 1
        elif primary in ("overdesign", "velocity_low"):
            direction = -1
        elif primary == "dP_shell_high":
            # Increase baffle spacing
            if g.baffle_spacing_m is not None and g.shell_diameter_m is not None:
                d_step = step_pct
                if (
                    "baffle_spacing_m" in last_direction
                    and last_direction["baffle_spacing_m"] != 1
                ):
                    d_step *= 0.5
                new_spacing = g.baffle_spacing_m * (1 + d_step)
                max_spacing = g.shell_diameter_m * 1.0
                changes["baffle_spacing_m"] = min(new_spacing, max_spacing)
                new_direction["baffle_spacing_m"] = 1
            return changes, new_direction
        else:
            direction = 1

        # Oscillation damping for n_tubes
        if "n_tubes" in last_direction and last_direction["n_tubes"] != direction:
            step_pct *= 0.5

        if g.n_tubes is not None:
            delta = max(1, int(round(g.n_tubes * step_pct)))
            new_n = g.n_tubes + direction * delta
            changes["n_tubes"] = max(1, new_n)
            new_direction["n_tubes"] = direction

        return changes, new_direction

    def _check_n_passes_adjustment(
        self,
        state: "DesignState",
        violations: list[str],
        changes: dict[str, Any],
    ) -> int | None:
        """Check if n_passes should be adjusted (discrete: 1,2,4,6,8)."""
        g = state.geometry
        if g is None or g.n_passes is None:
            return None

        current_idx = (
            PASSES_SEQUENCE.index(g.n_passes)
            if g.n_passes in PASSES_SEQUENCE
            else None
        )
        if current_idx is None:
            return None

        # Velocity too low AND n_tubes already being decreased → increase passes
        if "velocity_low" in violations:
            if current_idx < len(PASSES_SEQUENCE) - 1:
                return PASSES_SEQUENCE[current_idx + 1]

        # dP_tube too high AND n_tubes already being increased → decrease passes
        if "dP_tube_high" in violations and "n_tubes" in changes:
            if current_idx > 0:
                return PASSES_SEQUENCE[current_idx - 1]

        return None

    # ------------------------------------------------------------------
    # Apply geometry changes (TEMA-constrained)
    # ------------------------------------------------------------------

    def _apply_adjustment(self, state: "DesignState", changes: dict[str, Any]) -> str:
        """Apply geometry changes to state. Returns description string.

        n_tubes is ALWAYS snapped to valid TEMA table values.
        Shell upsizes trigger proportional baffle spacing recalculation.
        """
        g = state.geometry
        if g is None or not changes:
            return "no change"

        description_parts: list[str] = []

        new_n_tubes = changes.get("n_tubes", g.n_tubes)
        new_n_passes = changes.get("n_passes", g.n_passes)

        # Apply baffle spacing change (independent of tube changes)
        if "baffle_spacing_m" in changes:
            old_bs = g.baffle_spacing_m
            new_bs, floor_binding = _clamp_baffle_spacing(
                changes["baffle_spacing_m"], g.shell_diameter_m,
            )
            g.baffle_spacing_m = new_bs
            if old_bs and old_bs > 0:
                _rescale_secondary_baffles(g, new_bs / old_bs, g.shell_diameter_m)
            if g.tube_length_m and g.baffle_spacing_m:
                g.n_baffles = max(1, int(g.tube_length_m / g.baffle_spacing_m) - 1)
            description_parts.append(
                _format_baffle_change_description(old_bs, new_bs, floor_binding),
            )

        # Handle tube count / shell changes
        if new_n_tubes != g.n_tubes or new_n_passes != g.n_passes:
            if (
                g.shell_diameter_m is not None
                and g.tube_od_m is not None
                and g.pitch_layout is not None
            ):
                try:
                    max_in_shell = get_tube_count(
                        g.shell_diameter_m, g.tube_od_m, g.pitch_layout, new_n_passes,
                    )
                except (ValueError, KeyError):
                    max_in_shell = 0

                if new_n_tubes is not None and new_n_tubes > max_in_shell:
                    # Must upsize shell
                    try:
                        new_shell_m, actual_n_tubes = find_shell_diameter(
                            new_n_tubes, g.tube_od_m, g.pitch_layout, new_n_passes,
                        )
                    except ValueError:
                        # Largest shell can't fit — use largest available
                        new_shell_m = g.shell_diameter_m
                        actual_n_tubes = max_in_shell if max_in_shell > 0 else g.n_tubes

                    old_shell = g.shell_diameter_m
                    g.shell_diameter_m = new_shell_m
                    g.n_tubes = actual_n_tubes

                    # Recalculate baffle spacing proportionally on shell upsize
                    if g.baffle_spacing_m is not None and old_shell > 0:
                        ratio = new_shell_m / old_shell
                        g.baffle_spacing_m, _ = _clamp_baffle_spacing(
                            g.baffle_spacing_m * ratio, new_shell_m,
                        )
                        _rescale_secondary_baffles(g, ratio, new_shell_m)

                    # Recalculate n_baffles
                    if g.tube_length_m and g.baffle_spacing_m:
                        g.n_baffles = max(1, int(g.tube_length_m / g.baffle_spacing_m) - 1)

                    description_parts.append(
                        f"shell {old_shell*1000:.0f}mm→{new_shell_m*1000:.0f}mm, "
                        f"n_tubes→{actual_n_tubes}"
                    )
                else:
                    # Tubes fit in current shell — snap to TEMA count
                    if new_n_tubes != g.n_tubes and new_n_tubes is not None:
                        actual = min(new_n_tubes, max_in_shell) if max_in_shell > 0 else new_n_tubes
                        old_n = g.n_tubes
                        g.n_tubes = max(1, actual)
                        description_parts.append(f"n_tubes {old_n}→{g.n_tubes}")

            if new_n_passes != g.n_passes:
                old_passes = g.n_passes
                g.n_passes = new_n_passes
                description_parts.append(f"n_passes {old_passes}→{new_n_passes}")

        # P2-15 — Re-check L/D after geometry change.  WARN-only here;
        # the ESCALATE band [3, 15] is enforced by the Step 4 Layer 2
        # rule re-running on the next pipeline iteration if needed.
        ld_warning = _check_ld_band_after_adjustment(g)
        if ld_warning is not None:
            description_parts.append(ld_warning)
            state.warnings.append(ld_warning)

        # P2-17 — Re-check pitch-ratio vs layout floor after geometry change.
        pitch_warning = _check_pitch_layout_after_adjustment(g)
        if pitch_warning is not None:
            description_parts.append(pitch_warning)
            state.warnings.append(pitch_warning)

        return ", ".join(description_parts) or "no change"

    # ------------------------------------------------------------------
    # Trajectory snapshot
    # ------------------------------------------------------------------

    @staticmethod
    def _build_snapshot(
        state: "DesignState",
        iteration: int,
        delta_U_pct: float | None,
        substep_failed: bool,
    ) -> dict[str, Any]:
        g = state.geometry
        return {
            "iteration": iteration,
            "U_dirty": getattr(state, "U_dirty_W_m2K", None),
            "delta_U_pct": delta_U_pct,
            "overdesign_pct": getattr(state, "overdesign_pct", None),
            "dP_tube_Pa": getattr(state, "dP_tube_Pa", None),
            "dP_shell_Pa": getattr(state, "dP_shell_Pa", None),
            "velocity_m_s": getattr(state, "tube_velocity_m_s", None),
            "n_tubes": g.n_tubes if g else None,
            "n_passes": g.n_passes if g else None,
            "shell_diameter_m": g.shell_diameter_m if g else None,
            "baffle_spacing_m": g.baffle_spacing_m if g else None,
            "substep_failed": substep_failed,
            "adjustment": None,  # filled after adjustment
        }

    # ------------------------------------------------------------------
    # Post-convergence AI re-review
    # ------------------------------------------------------------------

    async def _post_convergence_ai_pass(
        self,
        state: "DesignState",
        ai_engineer: "AIEngineer",
        emit_event: Callable[[BaseModel], Awaitable[None]],
        sub_steps: list[type],
    ) -> None:
        """Re-run Steps 7→11 with AI enabled on the final converged geometry."""
        # in_convergence_loop is already False (cleared in finally block)
        for step_cls in sub_steps:
            step = step_cls()

            await emit_event(
                StepStartedEvent(
                    session_id="",
                    step_id=step.step_id,
                    step_name=step.step_name,
                )
            )

            result = await step.run_with_review_loop(state, ai_engineer)
            apply_outputs(state, result)

            # Record on state for audit trail
            state.current_step = step.step_id

            # Emit decision event
            await self._emit_sub_step_decision(
                emit_event, step, result,
            )

    @staticmethod
    async def _emit_sub_step_decision(
        emit_event: Callable[[BaseModel], Awaitable[None]],
        step: Any,
        result: "StepResult",
    ) -> None:
        """Emit the appropriate SSE event for a post-convergence sub-step."""
        await emit_event(
            StepApprovedEvent(
                session_id="",
                step_id=step.step_id,
                step_name=step.step_name,
                confidence=(
                    result.ai_review.confidence if result.ai_review else 0.0
                ),
                reasoning=(
                    result.ai_review.reasoning if result.ai_review else ""
                ),
                outputs={},
            )
        )

    # ------------------------------------------------------------------
    # Non-convergence handling
    # ------------------------------------------------------------------

    async def _handle_non_convergence(
        self,
        state: "DesignState",
        ai_engineer: "AIEngineer",
    ) -> StepResult:
        """Call AI once for structural suggestion, return ESCALATE result."""
        trajectory = state.convergence_trajectory

        # Find best iteration (lowest overdesign within acceptable range, or closest to target)
        best_iter = self._find_best_iteration(trajectory)

        prompt = (
            f"Convergence failed after {self.MAX_ITERATIONS} iterations.\n"
            f"Last 5 iterations: {json.dumps(trajectory[-5:], default=str)}\n"
            f"Current geometry: {state.geometry.model_dump() if state.geometry else '{}'}\n"
            f"Best iteration: #{best_iter['iteration']} "
            f"(overdesign={best_iter.get('overdesign_pct', 'N/A')}%, "
            f"ΔU={best_iter.get('delta_U_pct', 'N/A')}%)\n\n"
            "What structural change would resolve this? Options:\n"
            "A) Increase shell passes (1→2) — restart from Step 5\n"
            "B) Switch TEMA type — restart from Step 4\n"
            "C) Multi-shell configuration — restart from Step 6\n"
            "D) Swap tube allocation — restart from Step 4\n"
            "E) Change pitch layout — restart from Step 4\n"
            "F) No structural change possible — accept best result\n"
        )

        # Build a minimal StepResult wrapper for the AI call
        dummy_result = StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs={"convergence_prompt": prompt},
        )

        try:
            # Use a simple class with step_id/step_name for the AI review call
            review = await ai_engineer.review(self, state, dummy_result)
        except Exception:
            logger.exception("Step 12: AI review for non-convergence failed")
            review = AIReview(
                decision=AIDecisionEnum.ESCALATE,
                confidence=0.0,
                reasoning="AI review failed — manual intervention required.",
                recommendation="Accept best iteration result or modify design parameters.",
                options=[
                    "Accept best iteration result",
                    "Modify design parameters manually",
                ],
                ai_called=False,
            )

        # Map AI suggestion to restart step
        suggestion_map: dict[str, int] = {
            "A": 5,  # shell passes → restart from Step 5
            "B": 4,  # TEMA type → restart from Step 4
            "C": 6,  # multi-shell → restart from Step 6
            "D": 4,  # swap allocation → restart from Step 4
            "E": 4,  # pitch layout → restart from Step 4
        }

        # Parse AI suggestion from reasoning
        restart_step: int | None = None
        suggestion = "F"
        for key in suggestion_map:
            if key in (review.reasoning or ""):
                suggestion = key
                restart_step = suggestion_map[key]
                break

        options = [
            f"Accept AI recommendation: {review.reasoning}",
            "Keep best iteration result (accept current design)",
            "Modify design parameters manually",
        ]

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs={
                "convergence_action": "restart" if restart_step else "accept_best",
                "restart_from_step": restart_step,
                "structural_suggestion": suggestion,
                "best_iteration": best_iter,
                "convergence_iteration": self.MAX_ITERATIONS,
                "convergence_converged": False,
                "convergence_restart_count": state.convergence_restart_count,
            },
            warnings=[
                f"Convergence not achieved after {self.MAX_ITERATIONS} iterations. "
                f"AI suggests: {review.reasoning}"
            ],
            ai_review=AIReview(
                decision=AIDecisionEnum.ESCALATE,
                confidence=review.confidence,
                reasoning=review.reasoning,
                recommendation=review.recommendation or "Structural change recommended",
                options=options,
                ai_called=True,
            ),
        )

    @staticmethod
    def _find_best_iteration(trajectory: list[dict]) -> dict:
        """Find the iteration closest to convergence targets."""
        if not trajectory:
            return {"iteration": 0}

        best = trajectory[0]
        best_score = float("inf")

        for snap in trajectory:
            if snap.get("substep_failed"):
                continue
            od = snap.get("overdesign_pct")
            if od is None:
                continue
            # Score: distance from 17.5% overdesign (midpoint of 10-25%)
            score = abs(od - 17.5)
            # Penalise pressure drop violations
            if snap.get("dP_tube_Pa") and snap["dP_tube_Pa"] > 70_000:
                score += (snap["dP_tube_Pa"] - 70_000) / 10_000
            if snap.get("dP_shell_Pa") and snap["dP_shell_Pa"] > 140_000:
                score += (snap["dP_shell_Pa"] - 140_000) / 10_000
            if score < best_score:
                best_score = score
                best = snap

        return best

    def build_ai_context(self, state: "DesignState", result: "StepResult") -> str:
        lines = []
        n_iter = result.outputs.get("convergence_iteration")
        converged = result.outputs.get("convergence_converged")
        restart = result.outputs.get("convergence_restart_count")
        if n_iter is not None:
            lines.append(f"Iterations: {n_iter}")
        if converged is not None:
            lines.append(f"Converged: {converged}")
        if restart is not None:
            lines.append(f"Geometry restarts: {restart}")
        return "\n".join(lines)
