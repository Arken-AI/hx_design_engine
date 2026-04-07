"""Tests for BaseStep convergence flag behaviour.

Validates:
  - FULL-mode steps skip AI when in_convergence_loop=True
  - FULL-mode steps call AI when in_convergence_loop=False
"""

from __future__ import annotations

import pytest

from hx_engine.app.core.ai_engineer import AIEngineer
from hx_engine.app.models.design_state import DesignState
from hx_engine.app.models.step_result import (
    AIDecisionEnum,
    AIModeEnum,
    StepResult,
)
from hx_engine.app.steps.base import BaseStep


class FullModeStep(BaseStep):
    step_id = 88
    step_name = "FullModeTest"
    ai_mode = AIModeEnum.FULL

    async def execute(self, state: DesignState) -> StepResult:
        return StepResult(step_id=self.step_id, step_name=self.step_name, outputs={"val": 1})


class TestFullModeConvergenceFlag:
    def test_full_mode_skips_ai_in_loop(self):
        step = FullModeStep()
        state = DesignState(in_convergence_loop=True)
        assert step._should_call_ai(state) is False

    def test_full_mode_calls_ai_outside_loop(self):
        step = FullModeStep()
        state = DesignState(in_convergence_loop=False)
        assert step._should_call_ai(state) is True

    @pytest.mark.asyncio
    async def test_no_ai_review_in_convergence_loop(self):
        """run_with_review_loop should skip AI when in_convergence_loop=True."""
        step = FullModeStep()
        state = DesignState(in_convergence_loop=True)
        ai = AIEngineer(stub_mode=True)
        result = await step.run_with_review_loop(state, ai)
        # Should not have an AI review attached
        assert result.ai_review is None

    @pytest.mark.asyncio
    async def test_ai_review_outside_convergence_loop(self):
        """run_with_review_loop should call AI when in_convergence_loop=False."""
        step = FullModeStep()
        state = DesignState(in_convergence_loop=False)
        ai = AIEngineer(stub_mode=True)
        result = await step.run_with_review_loop(state, ai)
        # Should have an AI review (stub returns PROCEED)
        assert result.ai_review is not None
        assert result.ai_review.decision == AIDecisionEnum.PROCEED
