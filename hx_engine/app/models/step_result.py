"""StepResult, StepRecord, and supporting enums/models for the pipeline."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field as dc_field
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


class AttemptRecord(BaseModel):
    """Record of a single diagnostic correction attempt."""

    attempt_number: int
    diagnosis: str                          # AI's stated root cause
    approach: str                           # human-readable summary of what was tried
    corrections: list[AICorrection] = Field(default_factory=list)
    layer2_outcome: str                     # "pass" | "fail"
    layer2_rule_failed: Optional[str] = None  # first error message if Layer 2 failed
    layer1_exception: Optional[str] = None    # exception message if Layer 1 threw
    outcome: str                            # "success" | "failed"
    confidence: float


@dataclass
class FailureContext:
    """Transient context passed to the AI on retry calls.

    Not stored on any model — built fresh each loop iteration from the
    previous AttemptRecord. Lives only during the correction loop.
    """

    layer2_failed: bool
    layer2_rule_description: Optional[str]   # str(exception) or first vr.error
    layer1_exception: Optional[str]
    previous_attempts: list[AttemptRecord] = dc_field(default_factory=list)


class AIReview(BaseModel):
    """Result of an AI review of a step's outputs."""

    decision: AIDecisionEnum = AIDecisionEnum.PROCEED
    confidence: float = 0.85
    corrections: list[AICorrection] = Field(default_factory=list)
    reasoning: str = ""
    observation: str = ""
    recommendation: Optional[str] = None  # required when decision == ESCALATE
    options: list[str] = Field(default_factory=list)  # choices for the user
    attempts: list[AttemptRecord] = Field(default_factory=list)  # diagnostic trail
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
    outputs: dict[str, Any] = Field(default_factory=dict, alias="outputs_snapshot")
    warnings: list[str] = Field(default_factory=list)
    # Full AI review stored for audit / frontend restore
    ai_review: Optional[AIReview] = None

    model_config = {"populate_by_name": True}
