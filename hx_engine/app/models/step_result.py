"""StepResult, StepRecord, and supporting enums/models for the pipeline."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AIModeEnum(str, enum.Enum):
    FULL = "FULL"
    CONDITIONAL = "CONDITIONAL"
    NONE = "NONE"


class AIDecisionEnum(str, enum.Enum):
    PROCEED = "PROCEED"
    CORRECT = "CORRECT"
    WARN = "WARN"
    ESCALATE = "ESCALATE"


# ---------------------------------------------------------------------------
# AI structures
# ---------------------------------------------------------------------------

class AICorrection(BaseModel):
    """A single correction made by the AI engineer."""

    field: str
    old_value: Any = None
    new_value: Any = None
    reason: str = ""


class AIReview(BaseModel):
    """Result of an AI review of a step's outputs."""

    decision: AIDecisionEnum = AIDecisionEnum.PROCEED
    confidence: float = 0.85
    corrections: list[AICorrection] = Field(default_factory=list)
    reasoning: str = ""
    observation: str = ""
    recommendation: Optional[str] = None  # required when decision == ESCALATE
    options: list[str] = Field(default_factory=list)  # choices for the user
    ai_called: bool = False


# ---------------------------------------------------------------------------
# StepResult
# ---------------------------------------------------------------------------

class StepResult(BaseModel):
    """Returned by every step's execute() method."""

    step_id: int
    step_name: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    validation_passed: bool = True
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ai_review: Optional[AIReview] = None


# ---------------------------------------------------------------------------
# StepRecord — audit log entry stored in DesignState.step_records
# ---------------------------------------------------------------------------

class StepRecord(BaseModel):
    """Immutable audit record of a step execution."""

    step_id: int
    step_name: str
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    duration_s: Optional[float] = None
    ai_decision: Optional[AIDecisionEnum] = None
    ai_confidence: Optional[float] = None
    ai_called: bool = False
    validation_passed: bool = True
    validation_errors: list[str] = Field(default_factory=list)
    outputs_snapshot: dict[str, Any] = Field(default_factory=dict)
