"""Tests for the RedesignDriver constraint-violation loop.

Covers: DesignConstraintViolation shape, apply_lever for each canonical
lever, and the driver's happy-path / fallback / budget-exhaustion / AI-
auth-disabled flows.
"""

from __future__ import annotations

from typing import Any

import pytest

from hx_engine.app.core import redesign_loop as redesign_mod
from hx_engine.app.core.exceptions import DesignConstraintViolation
from hx_engine.app.core.redesign_loop import (
    LEGAL_LEVERS,
    MAX_FALLBACK_ATTEMPTS,
    MAX_REDESIGN_ATTEMPTS,
    RedesignDriver,
    apply_lever,
)
from hx_engine.app.core.session_store import SessionStore
from hx_engine.app.core.sse_manager import SSEManager
from hx_engine.app.models.design_state import DesignState, GeometrySpec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _state_with_geometry(**geom_overrides: Any) -> DesignState:
    base = dict(
        n_passes=2,
        tube_length_m=3.05,
        tube_od_m=0.0254,
        tube_id_m=0.0212,
        pitch_layout="triangular",
        baffle_cut=0.25,
        baffle_spacing_m=0.30,
        n_shells=1,
        shell_passes=1,
    )
    base.update(geom_overrides)
    return DesignState(geometry=GeometrySpec(**base))


class _StubAI:
    """Minimal stand-in for AIEngineer.recommend_redesign."""

    def __init__(
        self,
        *,
        responses: list[dict[str, Any] | None] | None = None,
        is_available: bool = True,
    ) -> None:
        self._responses = list(responses or [])
        self._is_available = is_available
        self.calls: list[dict[str, Any]] = []

    @property
    def is_available(self) -> bool:
        return self._is_available

    async def recommend_redesign(self, **kwargs: Any) -> dict[str, Any] | None:
        self.calls.append(kwargs)
        if not self._responses:
            return None
        return self._responses.pop(0)


class _StubRunner:
    """PipelineRunner stand-in. Raises a queued sequence of outcomes."""

    def __init__(
        self,
        *,
        outcomes: list[Any],
        on_each: callable | None = None,
    ) -> None:
        # Each outcome is either a DesignConstraintViolation (to raise) or
        # a sentinel "OK" string (to return state cleanly).
        self._outcomes = list(outcomes)
        self._on_each = on_each
        self.run_count = 0

    async def run(self, state: DesignState) -> DesignState:
        self.run_count += 1
        if self._on_each is not None:
            self._on_each(state, self.run_count)
        if not self._outcomes:
            return state
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return state


# ---------------------------------------------------------------------------
# DesignConstraintViolation shape
# ---------------------------------------------------------------------------


class TestDesignConstraintViolation:
    def test_basic_construction(self) -> None:
        exc = DesignConstraintViolation(
            step_id=10,
            constraint="nozzle_envelope",
            message="shell too small",
            failing_value=2.0,
            allowed_range=(4.0, 42.0),
            suggested_levers=["n_shells", "shell_passes"],
        )
        assert exc.step_id == 10
        assert exc.constraint == "nozzle_envelope"
        assert exc.failing_value == 2.0
        assert exc.allowed_range == (4.0, 42.0)
        assert "n_shells" in exc.suggested_levers
        assert "shell too small" in str(exc)

    def test_defaults(self) -> None:
        exc = DesignConstraintViolation(
            step_id=11,
            constraint="overdesign_band",
            message="undersized",
        )
        assert exc.suggested_levers == []
        assert exc.allowed_range == (None, None)


# ---------------------------------------------------------------------------
# apply_lever
# ---------------------------------------------------------------------------


class TestApplyLever:
    def test_n_passes_increase(self) -> None:
        s = _state_with_geometry(n_passes=2)
        old, new = apply_lever(s, "n_passes", "increase")
        assert (old, new) == (2, 4)
        assert s.geometry.n_passes == 4

    def test_n_passes_at_cap_returns_none(self) -> None:
        s = _state_with_geometry(n_passes=8)
        assert apply_lever(s, "n_passes", "increase") is None

    def test_tube_length_increase(self) -> None:
        s = _state_with_geometry(tube_length_m=3.05)
        old, new = apply_lever(s, "tube_length_m", "increase")
        assert old == 3.05
        assert new == 3.66

    def test_tube_od_increase_clears_id(self) -> None:
        s = _state_with_geometry(tube_od_m=0.01905, tube_id_m=0.016)
        old, new = apply_lever(s, "tube_od_m", "increase")
        assert old == 0.01905
        assert new == 0.02540
        assert s.geometry.tube_id_m is None

    def test_pitch_layout_swap(self) -> None:
        s = _state_with_geometry(pitch_layout="triangular")
        old, new = apply_lever(s, "pitch_layout", "swap")
        assert (old, new) == ("triangular", "square")
        assert s.geometry.pitch_layout == "square"

    def test_baffle_cut_increase(self) -> None:
        s = _state_with_geometry(baffle_cut=0.25)
        old, new = apply_lever(s, "baffle_cut", "increase")
        assert (old, new) == (0.25, 0.30)

    def test_baffle_spacing_decrease(self) -> None:
        s = _state_with_geometry(baffle_spacing_m=0.30)
        old, new = apply_lever(s, "baffle_spacing_m", "decrease")
        assert old == 0.30
        assert new == pytest.approx(0.30 * 0.7)

    def test_n_shells_increase(self) -> None:
        s = _state_with_geometry(n_shells=1)
        old, new = apply_lever(s, "n_shells", "increase")
        assert (old, new) == (1, 2)

    def test_shell_passes_increase(self) -> None:
        s = _state_with_geometry(shell_passes=1)
        old, new = apply_lever(s, "shell_passes", "increase")
        assert (old, new) == (1, 2)

    def test_multi_shell_arrangement_swap(self) -> None:
        s = _state_with_geometry()
        s.multi_shell_arrangement = "series"
        old, new = apply_lever(s, "multi_shell_arrangement", "swap")
        assert (old, new) == ("series", "parallel")

    def test_unknown_lever_returns_none(self) -> None:
        s = _state_with_geometry()
        assert apply_lever(s, "totally_made_up", "increase") is None


# ---------------------------------------------------------------------------
# RedesignDriver
# ---------------------------------------------------------------------------


def _make_driver(runner: Any, ai: Any) -> RedesignDriver:
    return RedesignDriver(
        runner=runner,
        ai_engineer=ai,
        sse_manager=SSEManager(),
        session_store=SessionStore(None),
    )


@pytest.mark.asyncio
async def test_success_on_first_attempt_no_loop() -> None:
    ai = _StubAI()
    runner = _StubRunner(outcomes=[])  # returns state cleanly
    driver = _make_driver(runner, ai)
    state = _state_with_geometry()

    result = await driver.run(state)

    assert result is state
    assert runner.run_count == 1
    assert state.redesign_attempt_count == 0
    assert state.redesign_history == []


@pytest.mark.asyncio
async def test_violation_then_ai_fix_then_success() -> None:
    violation = DesignConstraintViolation(
        step_id=10,
        constraint="nozzle_envelope",
        message="shell too small",
        failing_value=2.0,
        allowed_range=(4.0, 42.0),
        suggested_levers=["n_shells"],
    )
    ai = _StubAI(
        responses=[
            {
                "lever": "n_shells",
                "direction": "increase",
                "magnitude_hint": "+1",
                "rationale": "raise n_shells to shrink shell ID",
                "ai_response_excerpt": "...",
            }
        ]
    )
    runner = _StubRunner(outcomes=[violation])
    driver = _make_driver(runner, ai)
    state = _state_with_geometry(n_shells=1)

    await driver.run(state)

    assert runner.run_count == 2
    assert state.redesign_attempt_count == 1
    assert len(state.redesign_history) == 1
    attempt = state.redesign_history[0]
    assert attempt.lever == "n_shells"
    assert attempt.old_value == 1
    assert attempt.new_value == 2
    assert attempt.ai_called is True
    assert attempt.fallback_used is False
    assert state.geometry.n_shells == 2


@pytest.mark.asyncio
async def test_ai_unavailable_uses_fallback_and_smaller_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Make the violation persist forever so the budget is what trips us.
    def violation_factory() -> DesignConstraintViolation:
        return DesignConstraintViolation(
            step_id=10,
            constraint="nozzle_envelope",
            message="still too small",
            failing_value=2.0,
            allowed_range=(4.0, 42.0),
            suggested_levers=[],
        )

    ai = _StubAI(is_available=False)
    runner = _StubRunner(
        outcomes=[violation_factory() for _ in range(MAX_REDESIGN_ATTEMPTS + 2)]
    )
    driver = _make_driver(runner, ai)
    state = _state_with_geometry(n_shells=1)

    await driver.run(state)

    # Fallback budget caps at MAX_FALLBACK_ATTEMPTS — driver runs the
    # pipeline at most (cap + 1) times: cap successful redesigns then one
    # final run that hits the budget check.
    assert state.redesign_attempt_count == MAX_FALLBACK_ATTEMPTS
    assert all(a.fallback_used for a in state.redesign_history)
    assert state.pipeline_status == "error"


@pytest.mark.asyncio
async def test_budget_exhausted_emits_step_error() -> None:
    def violation() -> DesignConstraintViolation:
        return DesignConstraintViolation(
            step_id=10,
            constraint="nozzle_envelope",
            message="persistently infeasible",
            failing_value=2.0,
            allowed_range=(4.0, 42.0),
            suggested_levers=[],
        )

    ai = _StubAI()  # available, but never returns a recommendation
    runner = _StubRunner(
        outcomes=[violation() for _ in range(MAX_REDESIGN_ATTEMPTS + 5)]
    )
    sse = SSEManager()
    driver = RedesignDriver(
        runner=runner,
        ai_engineer=ai,
        sse_manager=sse,
        session_store=SessionStore(None),
    )
    state = _state_with_geometry(n_shells=1)

    await driver.run(state)

    assert state.pipeline_status == "error"
    assert state.redesign_attempt_count == MAX_REDESIGN_ATTEMPTS

    # Drain the SSE queue and confirm a step_error came through.
    queue = sse.get_queue(state.session_id)
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    error_events = [e for e in events if e.get("event_type") == "step_error"]
    assert len(error_events) == 1
    assert "Redesign budget" in error_events[0]["message"]


@pytest.mark.asyncio
async def test_ai_repeats_prior_suggestion_falls_back() -> None:
    """If the AI suggests an already-tried lever, the driver must fall back."""
    v = DesignConstraintViolation(
        step_id=10,
        constraint="nozzle_envelope",
        message="still bad",
        failing_value=2.0,
        allowed_range=(4.0, 42.0),
        suggested_levers=["n_shells"],
    )
    # AI suggests n_shells/increase twice in a row.
    ai = _StubAI(
        responses=[
            {"lever": "n_shells", "direction": "increase",
             "rationale": "first try", "ai_response_excerpt": ""},
            {"lever": "n_shells", "direction": "increase",
             "rationale": "repeat", "ai_response_excerpt": ""},
        ]
    )

    # 2 violations then success.
    runner = _StubRunner(outcomes=[v, v])
    driver = _make_driver(runner, ai)
    state = _state_with_geometry(n_shells=1)

    await driver.run(state)

    assert state.redesign_attempt_count == 2
    # First attempt = AI; second = fallback (because AI repeated).
    assert state.redesign_history[0].fallback_used is False
    assert state.redesign_history[1].fallback_used is True
