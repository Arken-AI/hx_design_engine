"""Tests for Piece 2: StepResult, StepRecord, AIReview, SSE events."""

import pytest

from hx_engine.app.models.step_result import (
    AIDecisionEnum,
    AIModeEnum,
    AIReview,
    StepRecord,
    StepResult,
)
from hx_engine.app.models.sse_events import (
    SSE_EVENT_TYPES,
    DesignCompleteEvent,
    StepCompletedEvent,
    StepEscalatedEvent,
    StepFailedEvent,
    StepStartedEvent,
)


class TestStepResult:
    def test_creation(self):
        r = StepResult(step_id=1, step_name="Test", outputs={"x": 1})
        assert r.step_id == 1
        assert r.outputs["x"] == 1

    def test_validation_errors_default_empty(self):
        r = StepResult(step_id=1, step_name="Test")
        assert r.validation_errors == []

    def test_warnings_default_empty(self):
        r = StepResult(step_id=1, step_name="Test")
        assert r.warnings == []


class TestAIReview:
    def test_confidence_range(self):
        review = AIReview(confidence=0.85)
        assert review.confidence == 0.85

    def test_default_decision(self):
        review = AIReview()
        assert review.decision == AIDecisionEnum.PROCEED


class TestAIDecisionEnum:
    def test_all_values(self):
        assert AIDecisionEnum.PROCEED.value == "PROCEED"
        assert AIDecisionEnum.CORRECT.value == "CORRECT"
        assert AIDecisionEnum.WARN.value == "WARN"
        assert AIDecisionEnum.ESCALATE.value == "ESCALATE"


class TestAIModeEnum:
    def test_all_values(self):
        assert AIModeEnum.FULL.value == "FULL"
        assert AIModeEnum.CONDITIONAL.value == "CONDITIONAL"
        assert AIModeEnum.NONE.value == "NONE"


class TestStepRecord:
    def test_serialization_round_trip(self):
        rec = StepRecord(
            step_id=1,
            step_name="Test",
            ai_decision=AIDecisionEnum.PROCEED,
            ai_confidence=0.9,
            ai_called=True,
            outputs_snapshot={"T_hot_in_C": 150.0},
        )
        data = rec.model_dump()
        rec2 = StepRecord(**data)
        assert rec2.step_id == 1
        assert rec2.ai_decision == AIDecisionEnum.PROCEED


class TestSSEEvents:
    def test_event_types_count(self):
        assert len(SSE_EVENT_TYPES) == 8

    def test_event_types_match_frontend(self):
        expected = {
            "step_started", "step_progress", "step_completed",
            "step_failed", "step_escalated", "ai_review",
            "warning", "design_complete",
        }
        assert set(SSE_EVENT_TYPES) == expected

    def test_escalated_event_has_options(self):
        evt = StepEscalatedEvent(
            session_id="s1", step_id=1, step_name="Test",
            options=["A", "B"],
        )
        assert isinstance(evt.options, list)
        assert len(evt.options) == 2

    def test_step_started_event(self):
        evt = StepStartedEvent(
            session_id="s1", step_id=1, step_name="Process Requirements"
        )
        assert evt.event_type == "step_started"
