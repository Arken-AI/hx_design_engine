"""Tests for Piece 5: AI Engineer stub."""

from hx_engine.app.core.ai_engineer import AIEngineer
from hx_engine.app.models.design_state import DesignState
from hx_engine.app.models.step_result import AIDecisionEnum, AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep


class _DummyStep(BaseStep):
    step_id = 1
    step_name = "Dummy"
    ai_mode = AIModeEnum.NONE

    async def execute(self, state):
        return StepResult(step_id=1, step_name="Dummy")


class TestAIEngineerStub:
    async def test_returns_proceed(self):
        ai = AIEngineer(stub_mode=True)
        review = await ai.review(_DummyStep(), DesignState(), StepResult(step_id=1, step_name="T"))
        assert review.decision == AIDecisionEnum.PROCEED

    async def test_confidence_is_0_85(self):
        ai = AIEngineer(stub_mode=True)
        review = await ai.review(_DummyStep(), DesignState(), StepResult(step_id=1, step_name="T"))
        assert review.confidence == 0.85

    async def test_ai_called_false(self):
        ai = AIEngineer(stub_mode=True)
        review = await ai.review(_DummyStep(), DesignState(), StepResult(step_id=1, step_name="T"))
        assert review.ai_called is False
