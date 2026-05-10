"""Tests for escalation restart-from-step mechanism.

Validates:
  - clear_state_from_step nulls correct fields and clears records
  - _apply_user_text_override returns correct restart targets
  - Restart does not affect steps before the restart point
  - Pipeline-level restart flow: correct SSE events, state clearing, counter reset
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hx_engine.app.core.ai_engineer import AIEngineer
from hx_engine.app.core.pipeline_runner import PipelineRunner
from hx_engine.app.core.session_store import SessionStore
from hx_engine.app.core.sse_manager import SSEManager
from hx_engine.app.core.state_utils import clear_state_from_step
from hx_engine.app.core.validation_rules import ValidationResult
from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.models.step_result import (
    AIDecisionEnum,
    AIModeEnum,
    AIReview,
    StepRecord,
    StepResult,
)
from hx_engine.app.steps.base import BaseStep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _populated_state() -> DesignState:
    """Return a DesignState with fields populated as if Steps 1-11 ran."""
    state = DesignState()
    # Step 3 fields
    state.hot_fluid_props = FluidProperties(
        density_kg_m3=820.0, viscosity_Pa_s=0.00052,
        cp_J_kgK=2200.0, k_W_mK=0.138, Pr=8.29,
    )
    state.cold_fluid_props = FluidProperties(
        density_kg_m3=988.0, viscosity_Pa_s=0.000547,
        cp_J_kgK=4181.0, k_W_mK=0.644, Pr=3.55,
    )
    state.hot_phase = "liquid"
    state.cold_phase = "liquid"
    # Step 4 fields
    state.geometry = GeometrySpec(
        tube_od_m=0.01905, tube_id_m=0.01483,
        n_tubes=158, n_passes=2,
        pitch_layout="triangular",
        shell_diameter_m=0.489, baffle_spacing_m=0.15,
    )
    # Step 5 fields
    state.Q_W = 6_300_000.0
    state.LMTD_K = 75.0
    state.F_factor = 0.87
    state.U_W_m2K = 350.0
    state.A_m2 = 24.0
    # Step 6 fields
    state.A_required_low_m2 = 20.0
    state.A_required_high_m2 = 28.0
    # Step 7 fields
    state.h_tube_W_m2K = 1200.0
    state.tube_velocity_m_s = 1.5
    state.Re_tube = 25000.0
    state.flow_regime_tube = "turbulent"
    # Step 8 fields
    state.h_shell_W_m2K = 800.0
    # Step 9 fields
    state.U_dirty_W_m2K = 320.0
    # Step 10 fields
    state.dP_tube_Pa = 45000.0
    state.dP_shell_Pa = 95000.0
    # Step 11 fields
    state.overdesign_pct = 12.0

    # Step records and completed_steps
    for sid in range(1, 12):
        state.step_records.append(
            StepRecord(step_id=sid, step_name=f"Step {sid}")
        )
        state.completed_steps.append(sid)

    state.escalation_history = {
        "7": [{"attempt": 1, "options": ["A", "B"], "user_chose": "A"}],
    }
    return state


# ---------------------------------------------------------------------------
# Tests: clear_state_from_step
# ---------------------------------------------------------------------------

class TestClearStateFromStep:
    def test_clears_from_step_3_onward(self):
        state = _populated_state()
        clear_state_from_step(state, 3)

        # Steps 1-2 records preserved
        assert all(r.step_id < 3 for r in state.step_records)
        assert state.completed_steps == [1, 2]

        # Step 3 fields nulled
        assert state.hot_fluid_props is None
        assert state.cold_fluid_props is None
        assert state.hot_phase is None
        assert state.cold_phase is None

        # Step 4 fields nulled
        assert state.geometry is None

        # Step 2 field preserved (Step 2 is before the restart point)
        assert state.Q_W == 6_300_000.0

        # Step 5 fields nulled
        assert state.LMTD_K is None

        # Step 7+ fields nulled
        assert state.h_tube_W_m2K is None
        assert state.h_shell_W_m2K is None
        assert state.U_dirty_W_m2K is None
        assert state.dP_tube_Pa is None
        assert state.overdesign_pct is None

    def test_clears_from_step_7_preserves_earlier(self):
        state = _populated_state()
        clear_state_from_step(state, 7)

        # Steps 1-6 preserved
        assert state.completed_steps == [1, 2, 3, 4, 5, 6]
        assert state.hot_fluid_props is not None
        assert state.geometry is not None
        assert state.Q_W == 6_300_000.0
        assert state.A_required_high_m2 == 28.0

        # Step 7+ nulled
        assert state.h_tube_W_m2K is None
        assert state.tube_velocity_m_s is None
        assert state.h_shell_W_m2K is None
        assert state.U_dirty_W_m2K is None
        assert state.dP_tube_Pa is None
        assert state.overdesign_pct is None

    def test_clears_escalation_history(self):
        state = _populated_state()
        clear_state_from_step(state, 7)
        assert "7" not in state.escalation_history

    def test_preserves_escalation_history_for_earlier_steps(self):
        state = _populated_state()
        state.escalation_history["4"] = [{"attempt": 1}]
        clear_state_from_step(state, 7)
        assert "4" in state.escalation_history

    def test_clears_step_records(self):
        state = _populated_state()
        clear_state_from_step(state, 5)
        remaining_ids = {r.step_id for r in state.step_records}
        assert remaining_ids == {1, 2, 3, 4}

    def test_clear_from_step_1_clears_everything(self):
        state = _populated_state()
        clear_state_from_step(state, 1)
        assert state.completed_steps == []
        assert state.step_records == []


# ---------------------------------------------------------------------------
# Tests: step.apply_user_override() return values
# ---------------------------------------------------------------------------

class TestApplyUserOverrideRestart:
    @pytest.mark.asyncio
    async def test_step7_option_a_returns_restart_3(self):
        from hx_engine.app.steps.step_07_tube_side_h import Step07TubeSideH
        state = _populated_state()
        state.shell_side_fluid = "hot"
        result = await Step07TubeSideH().apply_user_override(state, option_index=0, text="")
        assert result == 3
        assert state.shell_side_fluid == "cold"

    @pytest.mark.asyncio
    async def test_step7_option_b_returns_none(self):
        from hx_engine.app.steps.step_07_tube_side_h import Step07TubeSideH
        state = _populated_state()
        result = await Step07TubeSideH().apply_user_override(state, option_index=1, text="")
        assert result is None

    @pytest.mark.asyncio
    async def test_step8_option_a_returns_none(self):
        from hx_engine.app.steps.step_08_shell_side_h import Step08ShellSideH
        state = _populated_state()
        result = await Step08ShellSideH().apply_user_override(state, option_index=0, text="")
        assert result is None

    @pytest.mark.asyncio
    async def test_step8_option_b_returns_restart_3(self):
        from hx_engine.app.steps.step_08_shell_side_h import Step08ShellSideH
        state = _populated_state()
        state.shell_side_fluid = "hot"
        result = await Step08ShellSideH().apply_user_override(state, option_index=1, text="")
        assert result == 3

    @pytest.mark.asyncio
    async def test_step7_regex_fluid_swap_returns_restart_3(self):
        from hx_engine.app.steps.step_07_tube_side_h import Step07TubeSideH
        state = _populated_state()
        state.shell_side_fluid = "hot"
        result = await Step07TubeSideH().apply_user_override(state, option_index=-1, text="swap fluid allocation")
        assert result == 3
        assert state.shell_side_fluid == "cold"

    @pytest.mark.asyncio
    async def test_step7_regex_velocity_adjustment_returns_none(self):
        from hx_engine.app.steps.step_07_tube_side_h import Step07TubeSideH
        state = _populated_state()
        result = await Step07TubeSideH().apply_user_override(state, option_index=-1, text="reduce n_tubes")
        assert result is None

    @pytest.mark.asyncio
    async def test_pipeline_runner_tema_preference_returns_none(self):
        from hx_engine.app.core.pipeline_runner import PipelineRunner
        state = _populated_state()
        result = await PipelineRunner._apply_user_text_override(state, "use BEM type")
        assert result is None
        assert state.tema_preference == "BEM"


# ---------------------------------------------------------------------------
# Integration tests: full restart-from-step flow through PipelineRunner
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_sse_manager():
    manager = AsyncMock(spec=SSEManager)
    manager.emitted_events = []

    async def capture_emit(session_id, event):
        manager.emitted_events.append(event)

    manager.emit = capture_emit
    return manager


@pytest.fixture
def mock_session_store():
    store = AsyncMock(spec=SessionStore)
    store.is_orphaned = AsyncMock(return_value=False)
    store.heartbeat = AsyncMock()
    store.save = AsyncMock()
    return store


@pytest.fixture
def pipeline_runner(mock_session_store, mock_sse_manager):
    return PipelineRunner(
        session_store=mock_session_store,
        sse_manager=mock_sse_manager,
        ai_engineer=AsyncMock(spec=AIEngineer),
    )


@pytest.fixture
def base_state():
    return DesignState(
        session_id="restart-test-session",
        hot_fluid_name="ethylene",
        cold_fluid_name="water",
        T_hot_in_C=80.0,
        T_hot_out_C=40.0,
        T_cold_in_C=20.0,
        T_cold_out_C=35.0,
    )


def _get_event_types(manager) -> list[str]:
    return [
        e.get("event_type") or e.get("type")
        for e in manager.emitted_events
        if isinstance(e, dict) and (e.get("event_type") or e.get("type"))
    ]


def _passed_vr() -> ValidationResult:
    vr = ValidationResult()
    vr.passed = True
    vr.errors = []
    return vr


def _proceed_result(step_id: int, step_name: str, outputs: dict | None = None) -> StepResult:
    return StepResult(
        step_id=step_id,
        step_name=step_name,
        outputs=outputs or {},
        ai_review=AIReview(
            decision=AIDecisionEnum.PROCEED, confidence=0.9, ai_called=True,
        ),
    )


class TestRestartFromStepFlow:
    """Integration tests for the general escalation restart path."""

    @pytest.mark.asyncio
    async def test_step7_option_a_clears_state_and_reruns_from_step3(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """Step 7 escalates with Option A → state cleared from Step 3, Steps 3-7 re-execute."""

        # Step 3, 4, 5, 6 always PROCEED
        class Step3(BaseStep):
            step_id = 3; step_name = "Fluid Properties"; ai_mode = AIModeEnum.NONE
            async def execute(self, state): return _proceed_result(3, self.step_name)
            async def run_with_review_loop(self, state, ai): return _proceed_result(3, self.step_name)

        class Step4(BaseStep):
            step_id = 4; step_name = "TEMA Geometry"; ai_mode = AIModeEnum.NONE
            async def execute(self, state): return _proceed_result(4, self.step_name)
            async def run_with_review_loop(self, state, ai): return _proceed_result(4, self.step_name)

        class Step5(BaseStep):
            step_id = 5; step_name = "LMTD"; ai_mode = AIModeEnum.NONE
            async def execute(self, state): return _proceed_result(5, self.step_name)
            async def run_with_review_loop(self, state, ai): return _proceed_result(5, self.step_name)

        class Step6(BaseStep):
            step_id = 6; step_name = "Initial U"; ai_mode = AIModeEnum.NONE
            async def execute(self, state): return _proceed_result(6, self.step_name)
            async def run_with_review_loop(self, state, ai): return _proceed_result(6, self.step_name)

        # Step 7 escalates on first call, then proceeds after restart
        step7_calls = []

        class Step7(BaseStep):
            step_id = 7; step_name = "Tube-Side H"; ai_mode = AIModeEnum.FULL
            async def execute(self, state): return _proceed_result(7, self.step_name)
            async def run_with_review_loop(self, state, ai):
                step7_calls.append(1)
                if len(step7_calls) == 1:
                    # First call: escalate with low velocity
                    return StepResult(
                        step_id=7, step_name="Tube-Side H",
                        outputs={"tube_velocity_m_s": 0.087, "h_tube_W_m2K": 320.0},
                        ai_review=AIReview(
                            decision=AIDecisionEnum.ESCALATE, confidence=0.0,
                            reasoning="Tube-side velocity 0.087 m/s — too low",
                            recommendation="Swap fluid allocation and restart from Step 3",
                            options=[
                                "Swap fluid allocation and restart from Step 3",
                                "Reduce n_tubes to increase velocity",
                            ],
                            ai_called=True,
                        ),
                    )
                # Subsequent calls (after restart): proceed
                return _proceed_result(7, "Tube-Side H", {"tube_velocity_m_s": 1.4})
            async def apply_user_override(self, state, option_index, text):
                if option_index == 0:
                    state.shell_side_fluid = "cold" if state.shell_side_fluid == "hot" else "hot"
                    return 3
                return None

        # Pre-populate state as if Steps 3-7 ran once (stale)
        base_state.hot_fluid_props = FluidProperties(density_kg_m3=1.2)
        base_state.geometry = GeometrySpec(
            n_tubes=200, n_passes=2, shell_diameter_m=0.5,
            tube_od_m=0.02, tube_id_m=0.016, tube_length_m=3.0,
            baffle_spacing_m=0.2,
        )
        base_state.LMTD_K = 30.0
        base_state.shell_side_fluid = "hot"

        # User clicks Option A (index 0) → swap + restart from 3
        def _option_a_future(_sid):
            fut = asyncio.Future()
            fut.set_result({
                "type": "override",
                "values": {"user_input": "swap fluid allocation", "option_index": 0},
            })
            return fut

        mock_sse_manager.create_user_response_future = MagicMock(side_effect=_option_a_future)

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [Step3, Step4, Step5, Step6, Step7],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=_passed_vr(),
        ), patch.object(
            pipeline_runner, "_run_convergence_loop", return_value=base_state,
        ), patch.object(
            pipeline_runner, "_run_post_convergence_step",
            side_effect=lambda state, sid, step=None: state,
        ):
            final_state = await pipeline_runner.run(base_state)

        # Pipeline should complete, not error
        assert final_state.pipeline_status == "completed"

        # Step 7 ran twice: once to escalate, once after restart
        assert len(step7_calls) == 2

        # Fluid swap was applied
        assert final_state.shell_side_fluid == "cold"

    @pytest.mark.asyncio
    async def test_restart_emits_step_started_for_each_restarted_step(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """SSE stream includes step_started for every step in the restart chain."""

        class Step3(BaseStep):
            step_id = 3; step_name = "Fluid Properties"; ai_mode = AIModeEnum.NONE
            async def execute(self, state): return _proceed_result(3, self.step_name)
            async def run_with_review_loop(self, state, ai): return _proceed_result(3, self.step_name)

        class Step4(BaseStep):
            step_id = 4; step_name = "TEMA Geometry"; ai_mode = AIModeEnum.NONE
            async def execute(self, state): return _proceed_result(4, self.step_name)
            async def run_with_review_loop(self, state, ai): return _proceed_result(4, self.step_name)

        step7_calls = []

        class Step7(BaseStep):
            step_id = 7; step_name = "Tube-Side H"; ai_mode = AIModeEnum.FULL
            async def execute(self, state): return _proceed_result(7, self.step_name)
            async def run_with_review_loop(self, state, ai):
                step7_calls.append(1)
                if len(step7_calls) == 1:
                    return StepResult(
                        step_id=7, step_name="Tube-Side H", outputs={},
                        ai_review=AIReview(
                            decision=AIDecisionEnum.ESCALATE, confidence=0.0,
                            recommendation="Swap fluids",
                            options=["Swap fluids and restart from Step 3", "Option B"],
                            ai_called=True,
                        ),
                    )
                return _proceed_result(7, "Tube-Side H")
            async def apply_user_override(self, state, option_index, text):
                if option_index == 0:
                    return 3
                return None

        base_state.shell_side_fluid = "hot"

        def _option_a_future(_sid):
            fut = asyncio.Future()
            fut.set_result({
                "type": "override",
                "values": {"user_input": "swap fluid allocation", "option_index": 0},
            })
            return fut

        mock_sse_manager.create_user_response_future = MagicMock(side_effect=_option_a_future)

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [Step3, Step4, Step7],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=_passed_vr(),
        ), patch.object(
            pipeline_runner, "_run_convergence_loop", return_value=base_state,
        ), patch.object(
            pipeline_runner, "_run_post_convergence_step",
            side_effect=lambda state, sid, step=None: state,
        ):
            await pipeline_runner.run(base_state)

        event_types = _get_event_types(mock_sse_manager)

        # Initial run: step_started for 3, 4, 7 (first pass)
        # Restart chain: step_started again for 3, 4, 7
        # Total step_started events should be at least 6 (3 initial + 3 restart)
        assert event_types.count("step_started") >= 6, (
            f"Expected ≥6 step_started events, got {event_types.count('step_started')}. "
            f"Full event stream: {event_types}"
        )

    @pytest.mark.asyncio
    async def test_restart_emits_decision_events_for_restarted_steps(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """Frontend receives step_approved (not just step_started) for all restarted steps."""

        class Step3(BaseStep):
            step_id = 3; step_name = "Fluid Properties"; ai_mode = AIModeEnum.NONE
            async def execute(self, state): return _proceed_result(3, self.step_name)
            async def run_with_review_loop(self, state, ai): return _proceed_result(3, self.step_name)

        step7_calls = []

        class Step7(BaseStep):
            step_id = 7; step_name = "Tube-Side H"; ai_mode = AIModeEnum.FULL
            async def execute(self, state): return _proceed_result(7, self.step_name)
            async def run_with_review_loop(self, state, ai):
                step7_calls.append(1)
                if len(step7_calls) == 1:
                    return StepResult(
                        step_id=7, step_name="Tube-Side H", outputs={},
                        ai_review=AIReview(
                            decision=AIDecisionEnum.ESCALATE, confidence=0.0,
                            recommendation="Swap", options=["Swap and restart", "Option B"],
                            ai_called=True,
                        ),
                    )
                return _proceed_result(7, "Tube-Side H")

        base_state.shell_side_fluid = "hot"

        def _option_a_future(_sid):
            fut = asyncio.Future()
            fut.set_result({
                "type": "override",
                "values": {"user_input": "swap fluid allocation", "option_index": 0},
            })
            return fut

        mock_sse_manager.create_user_response_future = MagicMock(side_effect=_option_a_future)

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [Step3, Step7],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=_passed_vr(),
        ), patch.object(
            pipeline_runner, "_run_convergence_loop", return_value=base_state,
        ), patch.object(
            pipeline_runner, "_run_post_convergence_step",
            side_effect=lambda state, sid, step=None: state,
        ):
            await pipeline_runner.run(base_state)

        event_types = _get_event_types(mock_sse_manager)

        # Each restarted step should emit step_approved (not stay stuck in RUNNING)
        assert "step_approved" in event_types, (
            f"Expected step_approved in restart chain. Full stream: {event_types}"
        )
        # No step_error from the restart path
        assert "step_error" not in event_types

    @pytest.mark.asyncio
    async def test_option_b_no_restart_reruns_current_step_only(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """Step 7 Option B (geometry change) re-runs only Step 7, not earlier steps."""

        step3_calls = []
        step7_calls = []

        class Step3(BaseStep):
            step_id = 3; step_name = "Fluid Properties"; ai_mode = AIModeEnum.NONE
            async def execute(self, state): return _proceed_result(3, self.step_name)
            async def run_with_review_loop(self, state, ai):
                step3_calls.append(1)
                return _proceed_result(3, self.step_name)

        class Step7(BaseStep):
            step_id = 7; step_name = "Tube-Side H"; ai_mode = AIModeEnum.FULL
            async def execute(self, state): return _proceed_result(7, self.step_name)
            async def run_with_review_loop(self, state, ai):
                step7_calls.append(1)
                if len(step7_calls) == 1:
                    return StepResult(
                        step_id=7, step_name="Tube-Side H", outputs={},
                        ai_review=AIReview(
                            decision=AIDecisionEnum.ESCALATE, confidence=0.0,
                            recommendation="Adjust geometry",
                            options=["Swap fluids", "Reduce n_tubes"],
                            ai_called=True,
                        ),
                    )
                return _proceed_result(7, "Tube-Side H")

        base_state.geometry = GeometrySpec(
            n_tubes=200, n_passes=1, shell_diameter_m=0.5,
            tube_od_m=0.02, tube_id_m=0.016, tube_length_m=3.0, baffle_spacing_m=0.2,
        )

        # User clicks Option B (index 1) → geometry adjust, no restart
        def _option_b_future(_sid):
            fut = asyncio.Future()
            fut.set_result({
                "type": "override",
                "values": {"user_input": "reduce n_tubes", "option_index": 1},
            })
            return fut

        mock_sse_manager.create_user_response_future = MagicMock(side_effect=_option_b_future)

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [Step3, Step7],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=_passed_vr(),
        ), patch.object(
            pipeline_runner, "_run_convergence_loop", return_value=base_state,
        ), patch.object(
            pipeline_runner, "_run_post_convergence_step",
            side_effect=lambda state, sid, step=None: state,
        ):
            await pipeline_runner.run(base_state)

        # Step 3 ran exactly once (initial pass) — restart did NOT re-run it
        assert step3_calls == [1], (
            f"Step 3 should have run exactly once; ran {len(step3_calls)} times"
        )
        # Step 7 ran twice: once escalating, once after Option B
        assert len(step7_calls) == 2
