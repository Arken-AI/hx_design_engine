"""Server-Sent Event models for the HX design pipeline.

These match the frontend HX_EVENT_TYPES constants exactly.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# SSE event types — must match frontend HX_EVENT_TYPES
# ---------------------------------------------------------------------------

class SSEBaseEvent(BaseModel):
    """Base for all SSE events."""

    session_id: str
    event_type: str


class StepStartedEvent(SSEBaseEvent):
    event_type: str = "step_started"
    step_id: int
    step_name: str


class StepProgressEvent(SSEBaseEvent):
    event_type: str = "step_progress"
    step_id: int
    message: str = ""
    progress_pct: Optional[float] = None


class StepCompletedEvent(SSEBaseEvent):
    event_type: str = "step_completed"
    step_id: int
    step_name: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    validation_passed: bool = True


class StepFailedEvent(SSEBaseEvent):
    event_type: str = "step_failed"
    step_id: int
    step_name: str
    errors: list[str] = Field(default_factory=list)


class StepEscalatedEvent(SSEBaseEvent):
    event_type: str = "step_escalated"
    step_id: int
    step_name: str
    message: str = ""
    options: list[str] = Field(default_factory=list)


class AIReviewEvent(SSEBaseEvent):
    event_type: str = "ai_review"
    step_id: int
    decision: str
    confidence: float
    reasoning: str = ""


class WarningEvent(SSEBaseEvent):
    event_type: str = "warning"
    step_id: int
    message: str


class DesignCompleteEvent(SSEBaseEvent):
    event_type: str = "design_complete"
    summary: dict[str, Any] = Field(default_factory=dict)


# All 8 SSE event types for contract testing
SSE_EVENT_TYPES = [
    "step_started",
    "step_progress",
    "step_completed",
    "step_failed",
    "step_escalated",
    "ai_review",
    "warning",
    "design_complete",
]
