"""Unit tests for PipelineRunner._rerun_steps_from() helper.

Covers (Phase 2.1):
  1. Bounded re-run executes only steps in [from_step, to_step]
  2. Unbounded re-run executes all steps from from_step to end of pipeline
  3. Error in any step returns None and sets pipeline_status='error'
  4. clear_state_from_step is invoked exactly once with from_step
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hx_engine.app.core.ai_engineer import AIEngineer
from hx_engine.app.core.exceptions import CalculationError, StepHardFailure
from hx_engine.app.core.pipeline_runner import PIPELINE_STEPS, PipelineRunner
from hx_engine.app.core.session_store import SessionStore
from hx_engine.app.core.sse_manager import SSEManager
from hx_engine.app.models.design_state import DesignState
from hx_engine.app.models.step_result import (
    AIDecisionEnum,
    AIModeEnum,
    AIReview,
    StepResult,
)
from hx_engine.app.steps.base import BaseStep


# ---------------------------------------------------------------------------
# Fixtures
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
def runner(mock_session_store, mock_sse_manager):
    return PipelineRunner(
        session_store=mock_session_store,
        sse_manager=mock_sse_manager,
        ai_engineer=AsyncMock(spec=AIEngineer),
    )


@pytest.fixture
def state():
    return DesignState(
        session_id="rerun-test-session",
        hot_fluid_name="water",
        cold_fluid_name="oil",
        T_hot_in_C=90.0,
        T_hot_out_C=60.0,
        T_cold_in_C=25.0,
        T_cold_out_C=45.0,
    )


SESSION_ID = "rerun-test-session"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _proceed_result(step_id: int, step_name: str) -> StepResult:
    return StepResult(
        step_id=step_id,
        step_name=step_name,
        outputs={},
        ai_review=AIReview(
            decision=AIDecisionEnum.PROCEED,
            confidence=0.9,
            ai_called=True,
        ),
    )


def _make_fake_step(step_id: int, step_name: str):
    """Return a BaseStep subclass that always PROCEEDs."""
    _sid = step_id
    _sname = step_name

    class FakeStep(BaseStep):
        step_id = _sid
        step_name = _sname
        ai_mode = AIModeEnum.NONE

        async def execute(self, s):
            return _proceed_result(_sid, _sname)

        async def run_with_review_loop(self, s, ai):
            return _proceed_result(_sid, _sname)

    return FakeStep


# Fake pipeline: steps 3-7
_FAKE_STEPS = [_make_fake_step(i, f"Step {i}") for i in range(3, 8)]


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestRerunStepsFromBounded:
    """Bounded re-run only executes steps in [from_step, to_step]."""

    @pytest.mark.asyncio
    async def test_bounded_executes_correct_steps(self, runner, state):
        executed = []

        def make_tracking_step(step_id, step_name):
            cls = _make_fake_step(step_id, step_name)
            original = cls.run_with_review_loop

            async def tracking(self, s, ai):
                executed.append(step_id)
                return _proceed_result(step_id, step_name)

            cls.run_with_review_loop = tracking
            return cls

        fake_steps = [make_tracking_step(i, f"Step {i}") for i in range(3, 8)]

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            fake_steps,
        ), patch(
            "hx_engine.app.core.pipeline_runner.clear_state_from_step",
        ):
            result = await runner._rerun_steps_from(state, SESSION_ID, 4, 6)

        assert result is state
        assert executed == [4, 5, 6]
        # Steps outside [4,6] must not be executed
        assert 3 not in executed
        assert 7 not in executed

    @pytest.mark.asyncio
    async def test_bounded_completes_all_steps_in_range(self, runner, state):
        """All steps in range are in completed_steps after helper returns."""
        fake_steps = [_make_fake_step(i, f"Step {i}") for i in range(3, 8)]

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            fake_steps,
        ), patch(
            "hx_engine.app.core.pipeline_runner.clear_state_from_step",
        ):
            result = await runner._rerun_steps_from(state, SESSION_ID, 3, 7)

        assert result is state
        assert state.completed_steps[-1] == 7
        for sid in (3, 4, 5, 6, 7):
            assert sid in state.completed_steps


class TestRerunStepsFromUnbounded:
    """Unbounded re-run executes all steps from from_step to end of pipeline."""

    @pytest.mark.asyncio
    async def test_unbounded_executes_all_from_step(self, runner, state):
        executed = []

        def make_tracking_step(step_id, step_name):
            cls = _make_fake_step(step_id, step_name)

            async def tracking(self, s, ai):
                executed.append(step_id)
                return _proceed_result(step_id, step_name)

            cls.run_with_review_loop = tracking
            return cls

        fake_steps = [make_tracking_step(i, f"Step {i}") for i in range(3, 8)]

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            fake_steps,
        ), patch(
            "hx_engine.app.core.pipeline_runner.clear_state_from_step",
        ):
            result = await runner._rerun_steps_from(state, SESSION_ID, 5, None)

        assert result is state
        expected = [i for i in range(3, 8) if i >= 5]
        assert executed == expected
        for sid in expected:
            assert sid in state.completed_steps

    @pytest.mark.asyncio
    async def test_unbounded_all_fake_pipeline_steps_tracked(self, runner, state):
        """Helper runs all PIPELINE_STEPS when from_step=first, to_step=None."""
        expected_ids = [s.step_id for s in PIPELINE_STEPS]
        executed = []

        original_pipeline = list(PIPELINE_STEPS)

        def make_tracking_step(cls):
            sid = cls.step_id
            sname = cls.step_name

            class Wrapper(cls):
                pass

            async def _run(self, s, ai):
                executed.append(sid)
                return _proceed_result(sid, sname)

            Wrapper.run_with_review_loop = _run
            Wrapper.step_id = sid
            Wrapper.step_name = sname
            return Wrapper

        tracking_steps = [make_tracking_step(cls) for cls in original_pipeline]

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            tracking_steps,
        ), patch(
            "hx_engine.app.core.pipeline_runner.clear_state_from_step",
        ):
            result = await runner._rerun_steps_from(
                state, SESSION_ID, expected_ids[0], None
            )

        assert result is state
        assert executed == expected_ids


class TestRerunStepsFromErrorPropagation:
    """Error in any step returns None and sets pipeline_status='error'."""

    @pytest.mark.asyncio
    async def test_calculation_error_returns_none(self, runner, state):
        def make_erroring_step(step_id):
            cls = _make_fake_step(step_id, f"Step {step_id}")

            async def _fail(self, s, ai):
                raise CalculationError(step_id, "boom")

            cls.run_with_review_loop = _fail
            return cls

        # Steps 3-4 succeed, step 5 raises CalculationError
        ok3 = _make_fake_step(3, "Step 3")
        ok4 = _make_fake_step(4, "Step 4")
        err5 = make_erroring_step(5)
        ok6 = _make_fake_step(6, "Step 6")

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [ok3, ok4, err5, ok6],
        ), patch(
            "hx_engine.app.core.pipeline_runner.clear_state_from_step",
        ):
            result = await runner._rerun_steps_from(state, SESSION_ID, 3, 6)

        assert result is None
        assert state.pipeline_status == "error"

    @pytest.mark.asyncio
    async def test_step_hard_failure_returns_none(self, runner, state):
        def make_hard_fail_step(step_id):
            cls = _make_fake_step(step_id, f"Step {step_id}")

            async def _fail(self, s, ai):
                raise StepHardFailure(step_id, ["constraint violated"])

            cls.run_with_review_loop = _fail
            return cls

        err4 = make_hard_fail_step(4)

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [_make_fake_step(3, "Step 3"), err4],
        ), patch(
            "hx_engine.app.core.pipeline_runner.clear_state_from_step",
        ):
            result = await runner._rerun_steps_from(state, SESSION_ID, 3, 4)

        assert result is None
        assert state.pipeline_status == "error"

    @pytest.mark.asyncio
    async def test_steps_after_error_not_executed(self, runner, state):
        """Steps after the failing one must not run."""
        executed = []

        def make_erroring(step_id):
            cls = _make_fake_step(step_id, f"Step {step_id}")

            async def _fail(self, s, ai):
                raise CalculationError(step_id, "fail")

            cls.run_with_review_loop = _fail
            return cls

        def make_tracking(step_id):
            cls = _make_fake_step(step_id, f"Step {step_id}")

            async def _track(self, s, ai):
                executed.append(step_id)
                return _proceed_result(step_id, f"Step {step_id}")

            cls.run_with_review_loop = _track
            return cls

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [make_erroring(3), make_tracking(4)],
        ), patch(
            "hx_engine.app.core.pipeline_runner.clear_state_from_step",
        ):
            await runner._rerun_steps_from(state, SESSION_ID, 3, 4)

        assert 4 not in executed


class TestRerunStepsFromClearsState:
    """clear_state_from_step is invoked exactly once with from_step."""

    @pytest.mark.asyncio
    async def test_clears_state_exactly_once(self, runner, state, monkeypatch):
        calls = []

        def fake_clear(s, n):
            calls.append(n)

        monkeypatch.setattr(
            "hx_engine.app.core.pipeline_runner.clear_state_from_step",
            fake_clear,
        )

        fake_steps = [_make_fake_step(i, f"Step {i}") for i in (4, 5, 6)]
        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            fake_steps,
        ):
            await runner._rerun_steps_from(state, SESSION_ID, 4, 6)

        assert calls == [4]

    @pytest.mark.asyncio
    async def test_clears_correct_step_number(self, runner, state, monkeypatch):
        calls = []

        def fake_clear(s, n):
            calls.append(n)

        monkeypatch.setattr(
            "hx_engine.app.core.pipeline_runner.clear_state_from_step",
            fake_clear,
        )

        fake_steps = [_make_fake_step(i, f"Step {i}") for i in range(7, 10)]
        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            fake_steps,
        ):
            await runner._rerun_steps_from(state, SESSION_ID, 7)

        assert calls == [7]


class TestRerunStepsFromEdgeCases:
    """to_step < from_step and from_step beyond pipeline are harmless no-ops."""

    @pytest.mark.asyncio
    async def test_empty_range_returns_state_unchanged(self, runner, state):
        """to_step < from_step → no steps executed, state returned."""
        executed = []

        def make_tracking(sid):
            cls = _make_fake_step(sid, f"Step {sid}")

            async def _t(self, s, ai):
                executed.append(sid)
                return _proceed_result(sid, f"Step {sid}")

            cls.run_with_review_loop = _t
            return cls

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [make_tracking(5), make_tracking(6)],
        ), patch(
            "hx_engine.app.core.pipeline_runner.clear_state_from_step",
        ):
            result = await runner._rerun_steps_from(state, SESSION_ID, 6, 5)

        assert result is state
        assert executed == []

    @pytest.mark.asyncio
    async def test_from_step_beyond_pipeline_returns_state(self, runner, state):
        """from_step > max PIPELINE_STEPS id → no-op."""
        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [_make_fake_step(3, "Step 3")],
        ), patch(
            "hx_engine.app.core.pipeline_runner.clear_state_from_step",
        ):
            result = await runner._rerun_steps_from(state, SESSION_ID, 99)

        assert result is state
