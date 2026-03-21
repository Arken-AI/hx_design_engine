"""AI Engineer stub — always returns PROCEED.

Real Anthropic API integration happens later. This stub ensures the pipeline
can run end-to-end without an LLM.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hx_engine.app.models.step_result import AIDecisionEnum, AIReview

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState
    from hx_engine.app.models.step_result import StepResult
    from hx_engine.app.steps.base import BaseStep


class AIEngineer:
    """Stub AI engineer — no LLM calls, always approves."""

    def review(
        self,
        step: "BaseStep",
        state: "DesignState",
        result: "StepResult",
    ) -> AIReview:
        return AIReview(
            decision=AIDecisionEnum.PROCEED,
            confidence=0.85,
            corrections=[],
            reasoning="Stub: auto-approved",
            ai_called=False,
        )
