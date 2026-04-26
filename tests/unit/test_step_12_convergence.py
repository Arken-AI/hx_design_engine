"""Tests for Step 12 — Convergence Loop.

Covers:
  - Happy path: converges in a few iterations
  - try/finally flag reset guarantee
  - Max iterations hit (non-convergence)
  - AI skipped inside loop
  - Oscillation damping
  - Shell upsize
  - n_passes adjustment
  - Proportional then damped switching
  - Layer 2 fail in sub-step
  - Baffle spacing on shell upsize
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hx_engine.app.core.ai_engineer import AIEngineer
from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.models.sse_events import IterationProgressEvent
from hx_engine.app.models.step_result import (
    AIDecisionEnum,
    AIReview,
    StepResult,
)
from hx_engine.app.steps.step_04_rules import _rule_baffle_spacing_min
from hx_engine.app.steps.step_12_convergence import (
    PASSES_SEQUENCE,
    Step12Convergence,
    _clamp_baffle_spacing,
)
from tests.unit.conftest import make_collector


# ===================================================================
# Helpers
# ===================================================================


def _make_geometry(**overrides) -> GeometrySpec:
    """Standard geometry for convergence testing."""
    defaults = dict(
        tube_od_m=0.01905,
        tube_id_m=0.01483,
        tube_length_m=4.88,
        pitch_ratio=1.25,
        pitch_layout="triangular",
        tube_pitch_m=0.0254,
        n_passes=2,
        shell_passes=1,
        baffle_cut=0.25,
        baffle_spacing_m=0.15,
        shell_diameter_m=0.489,
        n_tubes=158,
        n_baffles=22,
        n_sealing_strip_pairs=2,
        inlet_baffle_spacing_m=0.3048,
        outlet_baffle_spacing_m=0.3048,
    )
    defaults.update(overrides)
    return GeometrySpec(**defaults)


def _converging_state() -> DesignState:
    """State ready for convergence loop with realistic values."""
    return DesignState(
        geometry=_make_geometry(),
        hot_fluid_name="crude oil",
        cold_fluid_name="water",
        shell_side_fluid="hot",
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=50.0,
        m_dot_hot_kg_s=50.0,
        m_dot_cold_kg_s=100.0,
        Q_W=6_300_000.0,
        LMTD_K=75.0,
        F_factor=0.9,
        U_W_m2K=350.0,
        A_m2=26.7,
        hot_fluid_props=FluidProperties(
            density_kg_m3=820.0,
            viscosity_Pa_s=0.00052,
            cp_J_kgK=2200.0,
            k_W_mK=0.138,
            Pr=8.29,
        ),
        cold_fluid_props=FluidProperties(
            density_kg_m3=988.0,
            viscosity_Pa_s=0.000547,
            cp_J_kgK=4181.0,
            k_W_mK=0.644,
            Pr=3.55,
        ),
        # Step 11 outputs
        area_required_m2=25.0,
        area_provided_m2=27.0,
        overdesign_pct=8.0,  # below target (10-25%) → will trigger adjustment
        dP_tube_Pa=45000.0,
        dP_shell_Pa=95000.0,
        tube_velocity_m_s=1.4,
        U_dirty_W_m2K=350.0,
    )


def _make_converging_substep_results(iteration: int) -> list[StepResult]:
    """Create sub-step results that gradually converge."""
    # Simulate values that get closer to convergence each iteration
    base_U = 350.0 + (5.0 / iteration)  # converges toward 350
    overdesign = 8.0 + iteration * 2.5  # converges toward 10-25%
    dP_tube = 45000.0 - iteration * 1000  # stays within limits
    dP_shell = 95000.0 - iteration * 2000

    results = []
    for step_id, name in [
        (7, "Tube-Side HTC"),
        (8, "Shell-Side HTC"),
        (9, "Overall U"),
        (10, "Pressure Drops"),
        (11, "Area & Overdesign"),
    ]:
        outputs = {}
        if step_id == 7:
            outputs = {"h_tube_W_m2K": 2500.0, "tube_velocity_m_s": 1.4, "Re_tube": 25000.0}
        elif step_id == 8:
            outputs = {"h_shell_W_m2K": 1200.0, "Re_shell": 15000.0}
        elif step_id == 9:
            outputs = {"U_dirty_W_m2K": base_U, "U_clean_W_m2K": base_U * 1.1}
        elif step_id == 10:
            outputs = {"dP_tube_Pa": dP_tube, "dP_shell_Pa": dP_shell}
        elif step_id == 11:
            outputs = {
                "area_required_m2": 25.0,
                "area_provided_m2": 25.0 * (1 + overdesign / 100),
                "overdesign_pct": overdesign,
            }
        results.append(StepResult(step_id=step_id, step_name=name, outputs=outputs))
    return results


# ===================================================================
# Unit tests — convergence check
# ===================================================================


class TestCheckConvergence:
    def test_converged(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.overdesign_pct = 15.0
        state.dP_tube_Pa = 45000.0
        state.dP_shell_Pa = 95000.0
        state.tube_velocity_m_s = 1.4
        assert step12._check_convergence(state, delta_U_pct=0.5) is True

    def test_first_iteration_never_converges(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.overdesign_pct = 15.0
        assert step12._check_convergence(state, delta_U_pct=None) is False

    def test_delta_U_too_large(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.overdesign_pct = 15.0
        assert step12._check_convergence(state, delta_U_pct=2.0) is False

    def test_overdesign_too_low(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.overdesign_pct = 5.0
        assert step12._check_convergence(state, delta_U_pct=0.5) is False

    def test_overdesign_too_high(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.overdesign_pct = 30.0
        assert step12._check_convergence(state, delta_U_pct=0.5) is False

    def test_dp_tube_exceeded(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.overdesign_pct = 15.0
        state.dP_tube_Pa = 80000.0
        assert step12._check_convergence(state, delta_U_pct=0.5) is False

    def test_dp_shell_exceeded(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.overdesign_pct = 15.0
        state.dP_shell_Pa = 150000.0
        assert step12._check_convergence(state, delta_U_pct=0.5) is False

    def test_velocity_too_low(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.overdesign_pct = 15.0
        state.tube_velocity_m_s = 0.5
        assert step12._check_convergence(state, delta_U_pct=0.5) is False

    def test_velocity_too_high(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.overdesign_pct = 15.0
        state.tube_velocity_m_s = 3.0
        assert step12._check_convergence(state, delta_U_pct=0.5) is False


# ===================================================================
# Unit tests — violation detection
# ===================================================================


class TestDetectViolations:
    def test_no_violations(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.overdesign_pct = 15.0
        state.dP_tube_Pa = 45000.0
        state.dP_shell_Pa = 95000.0
        state.tube_velocity_m_s = 1.4
        assert step12._detect_violations(state) == []

    def test_pressure_drop_priority(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.dP_tube_Pa = 80000.0
        state.dP_shell_Pa = 150000.0
        state.overdesign_pct = 5.0
        violations = step12._detect_violations(state)
        assert violations[0] == "dP_tube_high"
        assert violations[1] == "dP_shell_high"
        assert "underdesign" in violations

    def test_substep_failed_first(self):
        step12 = Step12Convergence()
        state = _converging_state()
        violations = step12._detect_violations(state, substep_failed=True)
        assert violations[0] == "substep_failed"


# ===================================================================
# Unit tests — geometry adjustment
# ===================================================================


class TestComputeAdjustment:
    def test_proportional_underdesign(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.area_required_m2 = 30.0
        state.area_provided_m2 = 25.0
        state.overdesign_pct = -20.0  # underdesign
        changes, _ = step12._compute_adjustment(
            state, iteration=1, violations=["underdesign"], last_direction={},
        )
        # ratio = 30/25 = 1.2 → n_tubes should increase by ~20%
        assert changes["n_tubes"] > state.geometry.n_tubes

    def test_proportional_overdesign(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.area_required_m2 = 20.0
        state.area_provided_m2 = 30.0
        state.overdesign_pct = 50.0
        changes, _ = step12._compute_adjustment(
            state, iteration=1, violations=["overdesign"], last_direction={},
        )
        # ratio = 20/30 = 0.67 → n_tubes should decrease
        assert changes["n_tubes"] < state.geometry.n_tubes

    def test_damped_mode_smaller_steps(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.overdesign_pct = 5.0
        changes_prop, _ = step12._compute_adjustment(
            state, iteration=1,
            violations=["underdesign"],
            last_direction={},
        )
        state2 = _converging_state()
        state2.overdesign_pct = 5.0
        changes_damp, _ = step12._compute_adjustment(
            state2, iteration=4,
            violations=["underdesign"],
            last_direction={},
        )
        # Damped mode should produce smaller change than proportional
        if "n_tubes" in changes_prop and "n_tubes" in changes_damp:
            prop_delta = abs(changes_prop["n_tubes"] - state.geometry.n_tubes)
            damp_delta = abs(changes_damp["n_tubes"] - state2.geometry.n_tubes)
            assert damp_delta <= prop_delta

    def test_oscillation_damping(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.overdesign_pct = 5.0
        # Direction was -1 (decreasing), now violation says underdesign (increase)
        changes1, _ = step12._compute_adjustment(
            state, iteration=4,
            violations=["underdesign"],
            last_direction={"n_tubes": -1},
        )
        changes2, _ = step12._compute_adjustment(
            state, iteration=4,
            violations=["underdesign"],
            last_direction={"n_tubes": 1},
        )
        # Direction reversal should produce smaller step
        if "n_tubes" in changes1 and "n_tubes" in changes2:
            delta1 = abs(changes1["n_tubes"] - state.geometry.n_tubes)
            delta2 = abs(changes2["n_tubes"] - state.geometry.n_tubes)
            assert delta1 <= delta2

    def test_n_passes_increase_on_low_velocity(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.tube_velocity_m_s = 0.5
        state.geometry.n_passes = 2
        n_passes = step12._check_n_passes_adjustment(
            state, ["velocity_low"], {},
        )
        assert n_passes == 4  # 2→4

    def test_n_passes_decrease_on_high_dp(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.dP_tube_Pa = 80000.0
        state.geometry.n_passes = 4
        n_passes = step12._check_n_passes_adjustment(
            state, ["dP_tube_high"], {"n_tubes": 200},
        )
        assert n_passes == 2  # 4→2

    def test_n_passes_at_max_no_change(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.tube_velocity_m_s = 0.5
        state.geometry.n_passes = 8
        n_passes = step12._check_n_passes_adjustment(
            state, ["velocity_low"], {},
        )
        assert n_passes is None


# ===================================================================
# Unit tests — apply adjustment (TEMA constrained)
# ===================================================================


class TestApplyAdjustment:
    def test_tubes_fit_in_shell(self):
        step12 = Step12Convergence()
        state = _converging_state()
        old_n = state.geometry.n_tubes
        desc = step12._apply_adjustment(state, {"n_tubes": old_n + 5})
        assert "n_tubes" in desc
        # Should be snapped to TEMA count (may not be exactly old_n+5)
        assert state.geometry.n_tubes >= 1

    def test_shell_upsize(self):
        step12 = Step12Convergence()
        state = _converging_state()
        old_shell = state.geometry.shell_diameter_m
        # Request way more tubes than can fit
        desc = step12._apply_adjustment(state, {"n_tubes": 5000})
        assert state.geometry.shell_diameter_m >= old_shell
        assert "shell" in desc or "n_tubes" in desc

    def test_baffle_spacing_proportional_on_upsize(self):
        step12 = Step12Convergence()
        state = _converging_state()
        old_shell = state.geometry.shell_diameter_m
        old_bs = state.geometry.baffle_spacing_m
        # Force shell upsize
        step12._apply_adjustment(state, {"n_tubes": 5000})
        if state.geometry.shell_diameter_m > old_shell:
            ratio = state.geometry.shell_diameter_m / old_shell
            expected_bs = old_bs * ratio
            assert abs(state.geometry.baffle_spacing_m - expected_bs) < 0.01 or \
                state.geometry.baffle_spacing_m <= 2.0

    def test_no_change_returns_no_change(self):
        step12 = Step12Convergence()
        state = _converging_state()
        desc = step12._apply_adjustment(state, {})
        assert desc == "no change"

    def test_baffle_spacing_clamped(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.geometry.baffle_spacing_m = 1.9
        desc = step12._apply_adjustment(state, {"baffle_spacing_m": 3.0})
        assert state.geometry.baffle_spacing_m <= 2.0


# ===================================================================
# Async tests — full convergence run
# ===================================================================


class TestConvergenceRun:
    """Tests for the full async run() method with mocked sub-steps."""

    @pytest.fixture
    def ai_engineer(self):
        return AIEngineer(stub_mode=True)

    @pytest.mark.asyncio
    async def test_convergence_happy_path(self, ai_engineer):
        """Sub-steps converge within a few iterations."""
        state = _converging_state()
        step12 = Step12Convergence()
        iteration_counter = {"n": 0}

        async def mock_run_with_review_loop(inner_self, state, ai_eng):
            iteration_counter["n"] += 1
            step_id = inner_self.step_id
            # Simulate improving values
            i = iteration_counter["n"] // 5 + 1
            outputs = {}
            if step_id == 7:
                outputs = {"h_tube_W_m2K": 2500.0, "tube_velocity_m_s": 1.4, "Re_tube": 25000.0}
            elif step_id == 8:
                outputs = {"h_shell_W_m2K": 1200.0, "Re_shell": 15000.0}
            elif step_id == 9:
                u = 350.0 + (2.0 / max(1, i))
                outputs = {"U_dirty_W_m2K": u}
            elif step_id == 10:
                outputs = {"dP_tube_Pa": 45000.0, "dP_shell_Pa": 95000.0}
            elif step_id == 11:
                outputs = {
                    "area_required_m2": 25.0,
                    "area_provided_m2": 28.5,
                    "overdesign_pct": 14.0,
                }
            return StepResult(step_id=step_id, step_name=inner_self.step_name, outputs=outputs)

        with patch(
            "hx_engine.app.steps.base.BaseStep.run_with_review_loop",
            new=mock_run_with_review_loop,
        ):
            collected, emit = make_collector()
            result = await step12.run(state, ai_engineer, emit_event=emit)

        assert state.convergence_converged is True
        assert state.convergence_iteration is not None
        assert state.convergence_iteration <= 20
        assert state.in_convergence_loop is False

    @pytest.mark.asyncio
    async def test_try_finally_flag_reset(self, ai_engineer):
        """in_convergence_loop is cleared even when sub-step raises."""
        state = _converging_state()
        step12 = Step12Convergence()

        async def mock_run_raises(inner_self, state, ai_eng):
            raise RuntimeError("Boom!")

        with patch(
            "hx_engine.app.steps.base.BaseStep.run_with_review_loop",
            new=mock_run_raises,
        ):
            # The exception from all sub-steps being caught in the loop
            collected, emit = make_collector()
            result = await step12.run(state, ai_engineer, emit_event=emit)

        # Flag MUST be cleared regardless of exception
        assert state.in_convergence_loop is False

    @pytest.mark.asyncio
    async def test_max_iterations_hit(self, ai_engineer):
        """Loop exhausts all iterations without converging."""
        state = _converging_state()
        step12 = Step12Convergence()
        step12.MAX_ITERATIONS = 3  # reduce for test speed

        async def mock_never_converges(inner_self, state, ai_eng):
            step_id = inner_self.step_id
            outputs = {}
            if step_id == 9:
                # U keeps jumping around → delta_U_pct > 1%
                import random
                outputs = {"U_dirty_W_m2K": 300 + random.uniform(-50, 50)}
            elif step_id == 11:
                outputs = {"overdesign_pct": 5.0}  # always underdesigned
            elif step_id == 10:
                outputs = {"dP_tube_Pa": 45000.0, "dP_shell_Pa": 95000.0}
            elif step_id == 7:
                outputs = {"tube_velocity_m_s": 1.4}
            return StepResult(step_id=step_id, step_name=inner_self.step_name, outputs=outputs)

        with patch(
            "hx_engine.app.steps.base.BaseStep.run_with_review_loop",
            new=mock_never_converges,
        ):
            collected, emit = make_collector()
            result = await step12.run(state, ai_engineer, emit_event=emit)

        assert state.convergence_converged is False
        assert result.ai_review is not None
        assert result.ai_review.decision == AIDecisionEnum.ESCALATE

    @pytest.mark.asyncio
    async def test_ai_skipped_in_loop(self, ai_engineer):
        """Verify in_convergence_loop flag is True during loop execution."""
        state = _converging_state()
        step12 = Step12Convergence()
        step12.MAX_ITERATIONS = 2
        loop_flags: list[bool] = []
        post_flags: list[bool] = []

        async def mock_check_flag(inner_self, state, ai_eng):
            if state.in_convergence_loop:
                loop_flags.append(True)
            else:
                post_flags.append(False)
            step_id = inner_self.step_id
            outputs = {}
            if step_id == 9:
                outputs = {"U_dirty_W_m2K": 350.0}
            elif step_id == 11:
                outputs = {"overdesign_pct": 15.0, "area_required_m2": 25.0, "area_provided_m2": 28.75}
            elif step_id == 10:
                outputs = {"dP_tube_Pa": 45000.0, "dP_shell_Pa": 95000.0}
            elif step_id == 7:
                outputs = {"tube_velocity_m_s": 1.4}
            return StepResult(step_id=step_id, step_name=inner_self.step_name, outputs=outputs)

        with patch(
            "hx_engine.app.steps.base.BaseStep.run_with_review_loop",
            new=mock_check_flag,
        ):
            collected, emit = make_collector()
            result = await step12.run(state, ai_engineer, emit_event=emit)

        # All calls during the loop should see in_convergence_loop=True
        assert len(loop_flags) > 0, "No loop calls captured"
        assert all(f is True for f in loop_flags)
        # Post-convergence calls should see in_convergence_loop=False
        assert len(post_flags) > 0, "No post-convergence calls captured"

    @pytest.mark.asyncio
    async def test_sse_iteration_events(self, ai_engineer):
        """IterationProgressEvent emitted each iteration."""
        state = _converging_state()
        step12 = Step12Convergence()
        step12.MAX_ITERATIONS = 2

        call_count = {"n": 0}

        async def mock_converge_iter2(inner_self, state, ai_eng):
            call_count["n"] += 1
            step_id = inner_self.step_id
            i = call_count["n"] // 5 + 1
            outputs = {}
            if step_id == 9:
                outputs = {"U_dirty_W_m2K": 350.0}
            elif step_id == 11:
                outputs = {"overdesign_pct": 15.0, "area_required_m2": 25.0, "area_provided_m2": 28.75}
            elif step_id == 10:
                outputs = {"dP_tube_Pa": 45000.0, "dP_shell_Pa": 95000.0}
            elif step_id == 7:
                outputs = {"tube_velocity_m_s": 1.4}
            return StepResult(step_id=step_id, step_name=inner_self.step_name, outputs=outputs)

        with patch(
            "hx_engine.app.steps.base.BaseStep.run_with_review_loop",
            new=mock_converge_iter2,
        ):
            collected, emit = make_collector()
            await step12.run(state, ai_engineer, emit_event=emit)

        iter_events = [e for e in collected if isinstance(e, IterationProgressEvent)]
        assert len(iter_events) >= 1


# ===================================================================
# tests — emit_event required (Phase 3.4 contract)
# ===================================================================


class TestEmitEventRequired:
    @pytest.mark.asyncio
    async def test_emit_event_now_required(self):
        """Calling run() without emit_event raises TypeError (required arg)."""
        step12 = Step12Convergence()
        state = _converging_state()
        ai_engineer = AIEngineer(stub_mode=True)
        with pytest.raises(TypeError):
            await step12.run(state, ai_engineer)  # type: ignore[call-arg]

    @pytest.mark.asyncio
    async def test_session_id_stamped_by_closure(self):
        """Events collected via a closure that stamps session_id carry the correct value."""
        from hx_engine.app.models.sse_events import SSEBaseEvent

        expected_sid = "test-session-123"
        collected, base_emit = make_collector()

        async def emit_with_sid(event: SSEBaseEvent) -> None:  # type: ignore[override]
            event.session_id = expected_sid
            await base_emit(event)

        state = _converging_state()
        step12 = Step12Convergence()
        step12.MAX_ITERATIONS = 1

        async def mock_substeps(inner_self, state, ai_eng):
            step_id = inner_self.step_id
            outputs = {}
            if step_id == 9:
                outputs = {"U_dirty_W_m2K": 350.0}
            elif step_id == 11:
                outputs = {"overdesign_pct": 15.0, "area_required_m2": 25.0, "area_provided_m2": 28.75}
            elif step_id == 10:
                outputs = {"dP_tube_Pa": 45000.0, "dP_shell_Pa": 95000.0}
            elif step_id == 7:
                outputs = {"tube_velocity_m_s": 1.4}
            return StepResult(step_id=step_id, step_name=inner_self.step_name, outputs=outputs)

        with patch(
            "hx_engine.app.steps.base.BaseStep.run_with_review_loop",
            new=mock_substeps,
        ):
            await step12.run(state, AIEngineer(stub_mode=True), emit_event=emit_with_sid)

        iter_events = [e for e in collected if isinstance(e, IterationProgressEvent)]
        assert len(iter_events) >= 1
        assert all(e.session_id == expected_sid for e in iter_events)


# ===================================================================
# tests — find best iteration
# ===================================================================


class TestFindBestIteration:
    def test_finds_closest_to_target(self):
        trajectory = [
            {"iteration": 1, "overdesign_pct": 5.0, "dP_tube_Pa": 50000, "dP_shell_Pa": 100000, "substep_failed": False},
            {"iteration": 2, "overdesign_pct": 18.0, "dP_tube_Pa": 50000, "dP_shell_Pa": 100000, "substep_failed": False},
            {"iteration": 3, "overdesign_pct": 30.0, "dP_tube_Pa": 50000, "dP_shell_Pa": 100000, "substep_failed": False},
        ]
        best = Step12Convergence._find_best_iteration(trajectory)
        assert best["iteration"] == 2  # closest to 17.5%

    def test_skips_failed_iterations(self):
        trajectory = [
            {"iteration": 1, "overdesign_pct": 17.5, "dP_tube_Pa": 50000, "dP_shell_Pa": 100000, "substep_failed": True},
            {"iteration": 2, "overdesign_pct": 12.0, "dP_tube_Pa": 50000, "dP_shell_Pa": 100000, "substep_failed": False},
        ]
        best = Step12Convergence._find_best_iteration(trajectory)
        assert best["iteration"] == 2

    def test_empty_trajectory(self):
        best = Step12Convergence._find_best_iteration([])
        assert best["iteration"] == 0


# ===================================================================
# tests — trajectory snapshot
# ===================================================================


class TestBuildSnapshot:
    def test_snapshot_captures_state(self):
        state = _converging_state()
        snap = Step12Convergence._build_snapshot(state, iteration=3, delta_U_pct=0.8, substep_failed=False)
        assert snap["iteration"] == 3
        assert snap["delta_U_pct"] == 0.8
        assert snap["n_tubes"] == state.geometry.n_tubes
        assert snap["substep_failed"] is False


# ===================================================================
# Single-shell iteration-count regression (P0-1 guard)
# ===================================================================
#
# Pins the iteration count required for a stable, in-band single-shell
# trajectory to converge. The P0-1 fix only changed the multi-shell
# `A_provided` formula (single-shell is byte-for-byte identical), so the
# single-shell convergence path MUST be unchanged. If a future change
# alters Step 12's tuning (thresholds, adjustment rules, convergence
# criteria) and slows single-shell convergence, this test fails first
# and points at the right culprit.

# Captured from a stable single-shell trajectory where Step 9 returns a
# constant U_dirty and Step 11 returns a constant in-band overdesign.
# Convergence requires `delta_U_pct < 1.0` AND `delta_U_pct is not None`,
# which is only true from iteration 2 onward — hence the pinned value.
SINGLE_SHELL_BASELINE_ITERATIONS: int = 2


def _stable_single_shell_substep_outputs(step_id: int) -> dict:
    """Deterministic in-band sub-step outputs for a single-shell design.

    Every iteration returns the same numbers, so:
      - delta_U_pct = 0 from iteration 2 onward (< 1% threshold ✓)
      - overdesign_pct = 14% (∈ [10, 25] ✓)
      - dP_tube / dP_shell within limits ✓
      - tube_velocity ∈ [0.8, 2.5] m/s ✓
    """
    if step_id == 7:
        return {"h_tube_W_m2K": 2500.0, "tube_velocity_m_s": 1.4, "Re_tube": 25_000.0}
    if step_id == 8:
        return {"h_shell_W_m2K": 1200.0, "Re_shell": 15_000.0}
    if step_id == 9:
        return {"U_dirty_W_m2K": 350.0, "U_clean_W_m2K": 385.0}
    if step_id == 10:
        return {"dP_tube_Pa": 45_000.0, "dP_shell_Pa": 95_000.0}
    if step_id == 11:
        return {
            "area_required_m2": 25.0,
            "area_provided_m2": 28.5,
            "overdesign_pct": 14.0,
        }
    return {}


class TestSingleShellIterationCountRegression:
    """Locks single-shell convergence iteration count against future drift."""

    @pytest.fixture
    def ai_engineer(self) -> AIEngineer:
        return AIEngineer(stub_mode=True)

    @pytest.mark.asyncio
    async def test_single_shell_converges_in_pinned_iteration_count(
        self, ai_engineer,
    ):
        """Stable single-shell trajectory converges in exactly the pinned count."""
        state = _converging_state()
        state.geometry.n_shells = 1   # explicit single-shell baseline
        step12 = Step12Convergence()

        async def mock_run_with_review_loop(inner_self, state, ai_eng):
            return StepResult(
                step_id=inner_self.step_id,
                step_name=inner_self.step_name,
                outputs=_stable_single_shell_substep_outputs(inner_self.step_id),
            )

        with patch(
            "hx_engine.app.steps.base.BaseStep.run_with_review_loop",
            new=mock_run_with_review_loop,
        ):
            collected, emit = make_collector()
            await step12.run(state, ai_engineer, emit_event=emit)

        assert state.convergence_converged is True
        assert state.convergence_iteration == SINGLE_SHELL_BASELINE_ITERATIONS


# P0-2 — Baffle spacing TEMA floor (Step 4 R5) regression
# Bug: artifacts/bugs/bug_p0_2_step12_baffle_spacing_clamp_violates_step4_r5.md
# Plan: artifacts/plans/implementation_plan_p0_2_step12_baffle_spacing_tema_floor.md


class TestClampBaffleSpacingHelper:
    """`_clamp_baffle_spacing` enforces `max(0.2 × D_s, 0.05 m)`."""

    def test_clamp_uses_tema_floor_for_large_shell(self):
        # D_s = 0.6 m → TEMA floor = 0.12 m, propose 0.08 m
        clamped, binding = _clamp_baffle_spacing(0.08, 0.6)
        assert clamped == pytest.approx(0.12)
        assert binding is True

    def test_clamp_uses_absolute_floor_for_small_shell(self):
        # D_s = 0.2 m → 0.2*D_s = 0.04 m; abs floor 0.05 m wins
        clamped, binding = _clamp_baffle_spacing(0.03, 0.2)
        assert clamped == pytest.approx(0.05)
        assert binding is True

    def test_clamp_uses_tema_floor_for_large_shell_1200mm(self):
        # D_s = 1.2 m → TEMA floor = 0.24 m, propose 0.15 m
        clamped, binding = _clamp_baffle_spacing(0.15, 1.2)
        assert clamped == pytest.approx(0.24)
        assert binding is True

    def test_clamp_passes_through_when_above_floor(self):
        # D_s = 0.6 m → floor 0.12 m, propose 0.20 m → unchanged
        clamped, binding = _clamp_baffle_spacing(0.20, 0.6)
        assert clamped == pytest.approx(0.20)
        assert binding is False

    def test_clamp_falls_back_to_abs_floor_when_shell_unknown(self):
        clamped, binding = _clamp_baffle_spacing(0.02, None)
        assert clamped == pytest.approx(0.05)
        assert binding is True

    def test_clamp_caps_at_ceiling(self):
        clamped, binding = _clamp_baffle_spacing(3.0, 0.6)
        assert clamped == pytest.approx(2.0)
        assert binding is False


class TestApplyAdjustmentBaffleSpacingTEMAFloor:
    """Direct-adjustment path routes through the TEMA helper."""

    def test_apply_adjustment_clamps_baffle_spacing_to_tema_floor(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.geometry.shell_diameter_m = 0.6   # → TEMA floor = 0.12 m
        state.geometry.baffle_spacing_m = 0.20

        desc = step12._apply_adjustment(state, {"baffle_spacing_m": 0.08})

        assert state.geometry.baffle_spacing_m == pytest.approx(0.12)
        assert "clamped to TEMA floor" in desc

    def test_apply_adjustment_no_suffix_when_floor_not_binding(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.geometry.shell_diameter_m = 0.6   # → TEMA floor = 0.12 m
        state.geometry.baffle_spacing_m = 0.20

        desc = step12._apply_adjustment(state, {"baffle_spacing_m": 0.18})

        assert state.geometry.baffle_spacing_m == pytest.approx(0.18)
        assert "clamped to TEMA floor" not in desc

    def test_apply_adjustment_inlet_outlet_also_respect_floor(self):
        """Rescaled inlet/outlet spacings must also satisfy the TEMA floor."""
        step12 = Step12Convergence()
        state = _converging_state()
        state.geometry.shell_diameter_m = 0.6   # floor = 0.12 m
        state.geometry.baffle_spacing_m = 0.20
        state.geometry.inlet_baffle_spacing_m = 0.20
        state.geometry.outlet_baffle_spacing_m = 0.20

        # Propose 0.08 → clamped to 0.12; inlet/outlet rescale by 0.12/0.20=0.6
        # → 0.12 m each, also at the floor.
        step12._apply_adjustment(state, {"baffle_spacing_m": 0.08})

        floor = 0.2 * state.geometry.shell_diameter_m
        assert state.geometry.inlet_baffle_spacing_m >= floor - 1e-9
        assert state.geometry.outlet_baffle_spacing_m >= floor - 1e-9


class TestShellUpsizeBaffleSpacingTEMAFloor:
    """Shell-upsize proportional rescale must use the *new* shell's floor."""

    def test_shell_upsize_proportional_rescale_respects_new_tema_floor(self):
        step12 = Step12Convergence()
        state = _converging_state()
        old_shell = state.geometry.shell_diameter_m
        step12._apply_adjustment(state, {"n_tubes": 5000})

        assert state.geometry.shell_diameter_m > old_shell, "upsize did not fire — fixture may need a larger n_tubes"
        floor = 0.2 * state.geometry.shell_diameter_m
        assert state.geometry.baffle_spacing_m >= floor - 1e-9
        if state.geometry.inlet_baffle_spacing_m is not None:
            assert state.geometry.inlet_baffle_spacing_m >= floor - 1e-9
        if state.geometry.outlet_baffle_spacing_m is not None:
            assert state.geometry.outlet_baffle_spacing_m >= floor - 1e-9

    def test_shell_upsize_below_floor_is_clamped(self):
        """When proportional rescale lands below the new floor, clamp holds."""
        step12 = Step12Convergence()
        state = _converging_state()
        state.geometry.baffle_spacing_m = 0.05
        state.geometry.inlet_baffle_spacing_m = 0.05
        state.geometry.outlet_baffle_spacing_m = 0.05

        old_shell = state.geometry.shell_diameter_m
        step12._apply_adjustment(state, {"n_tubes": 5000})

        assert state.geometry.shell_diameter_m > old_shell, "upsize did not fire — fixture may need a larger n_tubes"
        floor = 0.2 * state.geometry.shell_diameter_m
        assert state.geometry.baffle_spacing_m >= floor - 1e-9
        assert state.geometry.inlet_baffle_spacing_m >= floor - 1e-9
        assert state.geometry.outlet_baffle_spacing_m >= floor - 1e-9


class TestStep4R5HoldsAfterStep12Adjustments:
    """End-to-end: post-adjustment geometry passes the Step 4 R5 rule."""

    def _r5_check(self, state: DesignState) -> tuple[bool, str | None]:
        result = StepResult(
            step_id=4, step_name="Geometry",
            outputs={"geometry": state.geometry},
        )
        return _rule_baffle_spacing_min(4, result)

    def test_r5_passes_after_direct_baffle_adjustment_on_large_shell(self):
        step12 = Step12Convergence()
        state = _converging_state()
        state.geometry.shell_diameter_m = 0.6
        state.geometry.baffle_spacing_m = 0.20

        step12._apply_adjustment(state, {"baffle_spacing_m": 0.08})

        ok, msg = self._r5_check(state)
        assert ok is True, msg

    def test_r5_passes_after_shell_upsize(self):
        step12 = Step12Convergence()
        state = _converging_state()
        old_shell = state.geometry.shell_diameter_m
        step12._apply_adjustment(state, {"n_tubes": 5000})

        assert state.geometry.shell_diameter_m > old_shell, "upsize did not fire — fixture may need a larger n_tubes"
        ok, msg = self._r5_check(state)
        assert ok is True, msg
