"""Tests for Piece 4: _conditional_ai_trigger() — AI invocation logic for Step 02.

The trigger fires when energy balance imbalance > 2.0%.
Imbalance is stored as self._imbalance_pct by execute() after computing Q
from both sides.
"""

from __future__ import annotations

from hx_engine.app.models.design_state import DesignState
from hx_engine.app.steps.step_02_heat_duty import Step02HeatDuty


def _make_state(in_convergence: bool = False) -> DesignState:
    return DesignState(
        hot_fluid_name="crude oil",
        cold_fluid_name="cooling water",
        T_hot_in_C=150.0,
        T_hot_out_C=80.0,
        T_cold_in_C=25.0,
        T_cold_out_C=45.0,
        m_dot_hot_kg_s=10.0,
        in_convergence_loop=in_convergence,
    )


class TestConditionalAITrigger:
    """Six tests guarding AI trigger logic for Step 02 CONDITIONAL mode."""

    def test_no_imbalance_pct_set_no_trigger(self):
        """Fresh step with no execute() call yet → _imbalance_pct absent → no trigger."""
        step = Step02HeatDuty()
        assert step._conditional_ai_trigger(_make_state()) is False

    def test_zero_imbalance_no_trigger(self):
        """Perfect energy balance (0%) → no AI call."""
        step = Step02HeatDuty()
        step._imbalance_pct = 0.0
        assert step._conditional_ai_trigger(_make_state()) is False

    def test_exactly_two_percent_no_trigger(self):
        """Imbalance = 2.0% exactly → no trigger (threshold is strictly > 2.0)."""
        step = Step02HeatDuty()
        step._imbalance_pct = 2.0
        assert step._conditional_ai_trigger(_make_state()) is False

    def test_just_above_two_percent_triggers(self):
        """Imbalance = 2.1% → triggers AI (just over the 2% threshold)."""
        step = Step02HeatDuty()
        step._imbalance_pct = 2.1
        assert step._conditional_ai_trigger(_make_state()) is True

    def test_large_imbalance_triggers(self):
        """Imbalance = 10% → triggers AI (significant data inconsistency)."""
        step = Step02HeatDuty()
        step._imbalance_pct = 10.0
        assert step._conditional_ai_trigger(_make_state()) is True

    def test_convergence_loop_suppresses_trigger(self):
        """Decision 3A: in_convergence_loop=True → skip AI even with high imbalance.

        BaseStep._should_call_ai() checks in_convergence_loop before calling
        _conditional_ai_trigger, so the trigger is bypassed entirely.
        """
        step = Step02HeatDuty()
        step._imbalance_pct = 10.0
        state = _make_state(in_convergence=True)
        assert step._should_call_ai(state) is False
