"""AI Engineer — permanent stub (Layer 3 bypassed).

The live Anthropic integration has been removed. Every step always
receives PROCEED (confidence 0.85, ai_called=False). Re-enabling live
calls requires restoring the full implementation from git history.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from hx_engine.app.models.step_result import (
    AICorrection,
    AIDecisionEnum,
    AIReview,
    AttemptRecord,
    FailureContext,
)

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState
    from hx_engine.app.models.step_result import StepResult
    from hx_engine.app.steps.base import BaseStep

logger = logging.getLogger(__name__)

# Confidence threshold: >= this → auto-proceed, < this → escalate to user
CONFIDENCE_THRESHOLD = 0.7


class AIEngineer:
    """Permanent stub — always returns PROCEED without calling the API.

    The class shell is preserved so that all 16 step files, base.py,
    pipeline_runner.py, redesign_loop.py, and all integration tests
    compile and pass without modification.
    """

    def __init__(self, *, stub_mode: bool = True):
        self._stub_mode = True
        self._client = None

    @property
    def is_available(self) -> bool:
        """Always False — live API is permanently disabled."""
        return False

    async def review(
        self,
        step: "BaseStep",
        state: "DesignState",
        result: "StepResult",
        failure_context: "FailureContext | None" = None,
    ) -> AIReview:
        """Always returns PROCEED without making an API call."""
        return AIReview(
            decision=AIDecisionEnum.PROCEED,
            confidence=0.85,
            corrections=[],
            reasoning="Stub: auto-approved (AI review permanently disabled)",
            ai_called=False,
        )

    async def recommend_redesign(
        self,
        *,
        state: "DesignState",
        failed_step_id: int,
        constraint: str,
        failure_message: str,
        failing_value: Any = None,
        allowed_range: tuple[Any, Any] = (None, None),
        legal_levers: list[str],
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Always returns None — redesign driver uses deterministic round-robin."""
        return None
