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


class IterationProgressEvent(SSEBaseEvent):
    event_type: str = "iteration_progress"
    iteration_number: int
    max_iterations: int = 20
    current_U: Optional[float] = None
    delta_U_pct: Optional[float] = None
    constraints_met: bool = False


class StepApprovedEvent(SSEBaseEvent):
    event_type: str = "step_approved"
    step_id: int
    step_name: str
    confidence: float = 0.0
    reasoning: str = ""
    user_summary: str = ""
    duration_ms: int = 0
    outputs: dict[str, Any] = Field(default_factory=dict)


class StepErrorEvent(SSEBaseEvent):
    event_type: str = "step_error"
    step_id: int
    step_name: str
    message: str = ""
    observation: Optional[str] = None
    recommendation: Optional[str] = None
    options: Optional[list[str]] = None


class StepEscalatedEvent(SSEBaseEvent):
    event_type: str = "step_escalated"
    step_id: int
    step_name: str
    message: str = ""
    options: list[str] = Field(default_factory=list)


class StepCorrectedEvent(SSEBaseEvent):
    event_type: str = "step_corrected"
    step_id: int
    step_name: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    user_summary: str = ""
    correction: dict[str, Any] = Field(default_factory=dict)
    before: dict[str, Any] = Field(default_factory=dict)
    after: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0
    outputs: dict[str, Any] = Field(default_factory=dict)


class StepWarningEvent(SSEBaseEvent):
    event_type: str = "step_warning"
    step_id: int
    step_name: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    user_summary: str = ""
    warning_message: str = ""
    severity: str = "warning"  # "warning" = actionable | "note" = informational
    duration_ms: int = 0
    outputs: dict[str, Any] = Field(default_factory=dict)


class DesignCompleteEvent(SSEBaseEvent):
    event_type: str = "design_complete"
    summary: dict[str, Any] = Field(default_factory=dict)


# All 8 SSE event types for contract testing
SSE_EVENT_TYPES = [
    "step_started",
    "step_approved",
    "step_corrected",
    "step_warning",
    "step_escalated",
    "step_error",
    "iteration_progress",
    "design_complete",
]
