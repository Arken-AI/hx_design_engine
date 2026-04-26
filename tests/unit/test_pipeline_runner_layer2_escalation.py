"""Tests for Layer 2 → Escalation routing fix in PipelineRunner.

Covers the bug where Layer 2 failure discards AI escalation:
- Layer 2 fails + AI ESCALATE present → step_escalated emitted (not step_error)
- Layer 2 fails + NO AI escalation → hard-stop preserved (step_error)
- Layer 2 fails + AI decision is PROCEED → hard-stop preserved
- Layer 2 passes → normal flow (no regression)
- Escalation count exhausted → step_error with full history
- CalculationError / StepHardFailure → hard-stop preserved (exception paths)

Reference: bug_draft_step7_velocity_hard_fail_no_escalation.md
           bug_draft_pipeline_layer2_discards_ai_escalation.md
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hx_engine.app.core.ai_engineer import AIEngineer
from hx_engine.app.core.exceptions import CalculationError, StepHardFailure
from hx_engine.app.core.pipeline_runner import PipelineRunner
from hx_engine.app.core.session_store import SessionStore
from hx_engine.app.core.sse_manager import SSEManager
from hx_engine.app.core.validation_rules import ValidationResult
from hx_engine.app.models.design_state import DesignState, FluidProperties, GeometrySpec
from hx_engine.app.models.step_result import (
    AIDecisionEnum,
    AIModeEnum,
    AIReview,
    AttemptRecord,
    StepResult,
)
from hx_engine.app.steps.base import BaseStep
from hx_engine.app.core.design_intent import is_termination_intent


# ===================================================================
# Test Fixtures
# ===================================================================

@pytest.fixture
def mock_sse_manager():
    """Mock SSEManager that captures emitted events."""
    manager = AsyncMock(spec=SSEManager)
    manager.emitted_events = []

    async def capture_emit(session_id, event):
        manager.emitted_events.append(event)

    manager.emit = capture_emit
    return manager


@pytest.fixture
def mock_session_store():
    """Mock SessionStore with basic save/heartbeat/orphan check."""
    store = AsyncMock(spec=SessionStore)
    store.is_orphaned = AsyncMock(return_value=False)
    store.heartbeat = AsyncMock()
    store.save = AsyncMock()
    return store


@pytest.fixture
def mock_ai_engineer():
    """Mock AIEngineer (not used in these tests — we mock step results directly)."""
    return AsyncMock(spec=AIEngineer)


@pytest.fixture
def pipeline_runner(mock_session_store, mock_sse_manager, mock_ai_engineer):
    """PipelineRunner with mocked dependencies."""
    return PipelineRunner(
        session_store=mock_session_store,
        sse_manager=mock_sse_manager,
        ai_engineer=mock_ai_engineer,
    )


@pytest.fixture
def base_state():
    """Minimal DesignState for pipeline tests."""
    return DesignState(
        session_id="test-session-123",
        hot_fluid_name="water",
        cold_fluid_name="water",
        T_hot_in_C=90.0,
        T_hot_out_C=60.0,
        T_cold_in_C=25.0,
        T_cold_out_C=45.0,
    )


# ===================================================================
# Test Step Classes
# ===================================================================

class MockStep(BaseStep):
    """A mock step that returns a pre-configured result from run_with_review_loop."""

    step_id = 7
    step_name = "Tube-Side H"
    ai_mode = AIModeEnum.FULL

    def __init__(self, result: StepResult):
        self._result = result

    async def execute(self, state: DesignState) -> StepResult:
        return self._result

    async def run_with_review_loop(self, state, ai_engineer) -> StepResult:
        """Override to return pre-configured result directly, bypassing AI calls."""
        return self._result


# ===================================================================
# Helper Functions
# ===================================================================

def _make_escalate_review(
    reasoning: str = "Velocity critically low — geometry undersized",
    recommendation: str = "Swap fluid allocation or restart with higher U",
    options: list[str] | None = None,
    attempts: list[AttemptRecord] | None = None,
) -> AIReview:
    """Create an ESCALATE AIReview with diagnosis and options."""
    return AIReview(
        decision=AIDecisionEnum.ESCALATE,
        confidence=0.0,
        reasoning=reasoning,
        recommendation=recommendation,
        options=options or ["Swap oil to shell-side", "Restart with U=150"],
        attempts=attempts or [],
        ai_called=True,
    )


def _make_proceed_review(confidence: float = 0.9) -> AIReview:
    """Create a PROCEED AIReview."""
    return AIReview(
        decision=AIDecisionEnum.PROCEED,
        confidence=confidence,
        reasoning="Values within acceptable range",
        ai_called=True,
    )


def _make_validation_result(
    passed: bool,
    errors: list[str] | None = None,
    *,
    correctable: bool = True,
) -> ValidationResult:
    """Create a ValidationResult for mocking."""
    vr = ValidationResult()
    vr.passed = passed
    vr.errors = errors or []
    if not passed:
        if correctable:
            vr.has_correctable_failure = True
        else:
            vr.has_uncorrectable_failure = True
    return vr


def _get_emitted_event_types(mock_sse_manager) -> list[str]:
    """Extract event type strings from emitted SSE events."""
    types = []
    for event in mock_sse_manager.emitted_events:
        if isinstance(event, dict):
            # SSE events use "event_type" field
            event_type = event.get("event_type") or event.get("type")
            if event_type:
                types.append(event_type)
    return types


# ===================================================================
# Phase 1 Tests: Layer 2 Failure Routing
# ===================================================================

class TestLayer2FailureWithAIEscalation:
    """Layer 2 fails + AI ESCALATE present → step_escalated emitted, NOT step_error."""

    @pytest.mark.asyncio
    async def test_layer2_fail_with_ai_escalation_routes_to_escalation(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """When Layer 2 fails but AI already produced ESCALATE, emit step_escalated."""
        # Arrange: result with ESCALATE decision
        escalate_review = _make_escalate_review()
        result_with_escalate = StepResult(
            step_id=7,
            step_name="Tube-Side H",
            outputs={"tube_velocity_m_s": 0.122, "h_tube_W_m2K": 500.0},
            ai_review=escalate_review,
        )
        mock_step = MockStep(result_with_escalate)

        # Mock Layer 2 to fail
        failed_vr = _make_validation_result(
            passed=False,
            errors=["Tube velocity 0.122 m/s below hard minimum 0.3 m/s"],
        )

        # Create a future that resolves immediately with user response
        user_response_future = asyncio.Future()
        user_response_future.set_result({"type": "skip", "values": {}})
        mock_sse_manager.create_user_response_future = MagicMock(
            return_value=user_response_future
        )

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [lambda: mock_step],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=failed_vr,
        ):
            await pipeline_runner.run(base_state)

        # Assert: step_escalated was emitted, not step_error
        event_types = _get_emitted_event_types(mock_sse_manager)
        assert "step_escalated" in event_types, f"Expected step_escalated, got: {event_types}"
        # step_error should NOT appear for the initial escalation
        # (it may appear later if escalation is exhausted)


class TestLayer2FailureWithoutAIEscalation:
    """Layer 2 fails + NO AI escalation → recovery attempted."""

    @pytest.mark.asyncio
    async def test_layer2_fail_non_correctable_escalates_to_user(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """Non-correctable Layer 2 failure → ESCALATE to user (not hard-stop)."""
        result_no_ai = StepResult(
            step_id=7,
            step_name="Tube-Side H",
            outputs={"tube_velocity_m_s": 0.122},
            ai_review=None,
        )
        mock_step = MockStep(result_no_ai)

        failed_vr = _make_validation_result(
            passed=False,
            errors=["Tube velocity 0.122 m/s below hard minimum 0.3 m/s"],
            correctable=False,
        )

        # Create a future that resolves immediately with user response
        user_response_future = asyncio.Future()
        user_response_future.set_result({"type": "skip", "values": {}})
        mock_sse_manager.create_user_response_future = MagicMock(
            return_value=user_response_future
        )

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [lambda: mock_step],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=failed_vr,
        ):
            await pipeline_runner.run(base_state)

        # Assert: recovery produces ESCALATE, not immediate step_error
        event_types = _get_emitted_event_types(mock_sse_manager)
        assert "step_escalated" in event_types

    @pytest.mark.asyncio
    async def test_layer2_fail_correctable_triggers_ai_recovery(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """Correctable Layer 2 failure → AI recovery loop entered."""
        # The MockStep.run_with_review_loop returns the pre-set result.
        # After recovery, Layer 2 still fails → hard-stop.
        result_no_ai = StepResult(
            step_id=7,
            step_name="Tube-Side H",
            outputs={"tube_velocity_m_s": 0.122},
            ai_review=None,
        )
        mock_step = MockStep(result_no_ai)

        failed_vr = _make_validation_result(
            passed=False,
            errors=["Tube velocity 0.122 m/s below hard minimum 0.3 m/s"],
            correctable=True,
        )

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [lambda: mock_step],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=failed_vr,
        ):
            state = await pipeline_runner.run(base_state)

        # Recovery loop runs but MockStep still returns same bad result,
        # so Layer 2 re-check fails and pipeline errors.
        assert state.pipeline_status == "error"
        event_types = _get_emitted_event_types(mock_sse_manager)
        assert "step_error" in event_types


class TestLayer2FailureWithNonEscalateAI:
    """Layer 2 fails + AI said PROCEED → recovery attempted."""

    @pytest.mark.asyncio
    async def test_layer2_fail_with_proceed_correctable_triggers_recovery(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """When Layer 2 fails and AI said PROCEED, recovery loop runs.

        MockStep always returns the same bad result, so after recovery
        the re-check still fails and the pipeline errors.
        """
        proceed_review = _make_proceed_review(confidence=0.85)
        result_proceed = StepResult(
            step_id=7,
            step_name="Tube-Side H",
            outputs={"tube_velocity_m_s": 0.122},
            ai_review=proceed_review,
        )
        mock_step = MockStep(result_proceed)

        failed_vr = _make_validation_result(
            passed=False,
            errors=["Tube velocity 0.122 m/s below hard minimum 0.3 m/s"],
            correctable=True,
        )

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [lambda: mock_step],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=failed_vr,
        ):
            state = await pipeline_runner.run(base_state)

        # Recovery tried but MockStep still returns bad value → hard-stop
        event_types = _get_emitted_event_types(mock_sse_manager)
        assert "step_error" in event_types
        assert state.pipeline_status == "error"


class TestLayer2PassesNormalFlow:
    """Layer 2 passes → escalation routing code is not reached (no regression)."""

    @pytest.mark.asyncio
    async def test_layer2_passes_normal_flow_not_affected(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """When Layer 2 passes, step proceeds normally without escalation detour."""
        proceed_review = _make_proceed_review(confidence=0.9)
        result_ok = StepResult(
            step_id=7,
            step_name="Tube-Side H",
            outputs={"tube_velocity_m_s": 1.2, "h_tube_W_m2K": 5000.0},
            ai_review=proceed_review,
        )
        mock_step = MockStep(result_ok)

        passed_vr = _make_validation_result(passed=True)

        async def _noop_post(state, session_id, step):
            return state

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [lambda: mock_step],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=passed_vr,
        ), patch.object(
            # Skip the convergence loop so we test only Layer 2 routing
            pipeline_runner, "_run_convergence_loop",
            return_value=base_state,
        ), patch.object(
            pipeline_runner, "_run_post_convergence_step",
            side_effect=_noop_post,
        ):
            state = await pipeline_runner.run(base_state)

        event_types = _get_emitted_event_types(mock_sse_manager)
        assert "step_approved" in event_types
        assert "step_error" not in event_types
        assert "step_escalated" not in event_types
        # Pipeline completes when convergence + post-convergence are skipped
        assert state.pipeline_status == "completed"


# ===================================================================
# Phase 3 Tests: Exception Paths and Non-Regression
# ===================================================================

class TestExceptionPathsPreserved:
    """CalculationError and StepHardFailure still hard-stop regardless."""

    @pytest.mark.asyncio
    async def test_calculation_error_still_hard_stops(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """CalculationError from step still hard-stops with step_error."""

        class RaisingStep(BaseStep):
            step_id = 7
            step_name = "Tube-Side H"
            ai_mode = AIModeEnum.FULL

            async def execute(self, state: DesignState) -> StepResult:
                raise CalculationError("Missing geometry data")

            async def run_with_review_loop(self, state, ai_engineer) -> StepResult:
                raise CalculationError("Missing geometry data")

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [RaisingStep],
        ):
            state = await pipeline_runner.run(base_state)

        event_types = _get_emitted_event_types(mock_sse_manager)
        assert "step_error" in event_types
        assert "step_escalated" not in event_types
        assert state.pipeline_status == "error"

    @pytest.mark.asyncio
    async def test_step_hard_failure_still_hard_stops(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """StepHardFailure from step still hard-stops with step_error."""

        class HardFailStep(BaseStep):
            step_id = 7
            step_name = "Tube-Side H"
            ai_mode = AIModeEnum.FULL

            async def execute(self, state: DesignState) -> StepResult:
                raise StepHardFailure(["Hard rule violated inside loop"])

            async def run_with_review_loop(self, state, ai_engineer) -> StepResult:
                raise StepHardFailure(["Hard rule violated inside loop"])

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [HardFailStep],
        ):
            state = await pipeline_runner.run(base_state)

        event_types = _get_emitted_event_types(mock_sse_manager)
        assert "step_error" in event_types
        assert "step_escalated" not in event_types
        assert state.pipeline_status == "error"


class TestNormalEscalateNotRegressed:
    """Normal ESCALATE (Layer 2 passes, AI ESCALATE) still routes to escalation loop."""

    @pytest.mark.asyncio
    async def test_normal_escalate_layer2_passes_still_works(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """When Layer 2 passes but AI returns ESCALATE, step_escalated is emitted."""
        escalate_review = _make_escalate_review(
            reasoning="Ambiguous TEMA type for this service",
            options=["Use AES", "Use AEP"],
        )
        result = StepResult(
            step_id=4,
            step_name="TEMA Geometry",
            outputs={},
            ai_review=escalate_review,
        )
        mock_step = MockStep(result)
        mock_step.step_id = 4
        mock_step.step_name = "TEMA Geometry"

        passed_vr = _make_validation_result(passed=True)

        # Create a future that resolves immediately with user response
        user_response_future = asyncio.Future()
        user_response_future.set_result({"type": "skip", "values": {}})
        mock_sse_manager.create_user_response_future = MagicMock(
            return_value=user_response_future
        )

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [lambda: mock_step],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=passed_vr,
        ):
            await pipeline_runner.run(base_state)

        event_types = _get_emitted_event_types(mock_sse_manager)
        assert "step_escalated" in event_types


class TestEscalationExhausted:
    """Layer 2 fail + persistent ESCALATE → max_escalations reached → step_error."""

    @pytest.mark.asyncio
    async def test_escalation_exhausted_after_max_responses_emits_error(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """When Layer 2 fail + ESCALATE persists past max_escalations, emit step_error.

        Drives the new fall-through path (Layer 2 fail + ai_has_escalation) through
        the full escalation loop until exhaustion. Guards against regressions in the
        max_escalations guard at pipeline_runner.py:253-257 — which the plan flagged
        as the safeguard against an infinite escalation loop.
        """
        # Arrange: step always returns ESCALATE; Layer 2 always fails
        escalate_review = _make_escalate_review()
        persistent_escalate = StepResult(
            step_id=7,
            step_name="Tube-Side H",
            outputs={"tube_velocity_m_s": 0.122, "h_tube_W_m2K": 500.0},
            ai_review=escalate_review,
        )
        mock_step = MockStep(persistent_escalate)
        failed_vr = _make_validation_result(
            passed=False,
            errors=["Tube velocity 0.122 m/s below hard minimum 0.3 m/s"],
        )

        # Each await on a Future consumes it, so create_user_response_future
        # must hand out a fresh resolved future per call.
        def _fresh_future(_session_id):
            fut = asyncio.Future()
            fut.set_result({"type": "skip", "values": {}})
            return fut

        mock_sse_manager.create_user_response_future = MagicMock(side_effect=_fresh_future)

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [lambda: mock_step],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=failed_vr,
        ):
            state = await pipeline_runner.run(base_state)

        # Assert: legitimate escalation exhaustion, not an internal pipeline crash.
        # step_escalated fires 3 times (iterations 1, 2, 3 each emit via
        # _emit_decision_event), then the exhaustion block emits step_error.
        event_types = _get_emitted_event_types(mock_sse_manager)
        assert event_types.count("step_escalated") == 3
        assert event_types[-1] == "step_error"
        # Verify the step_error is the real exhaustion message, not the
        # broad except handler's "Internal pipeline error".
        last_error = next(
            e for e in reversed(mock_sse_manager.emitted_events)
            if isinstance(e, dict) and e.get("event_type") == "step_error"
        )
        assert "max escalation" in last_error.get("message", "")


class TestStep7EscalationOptionHandling:
    """Tests for Step 7 velocity escalation option handlers — via step.apply_user_override()."""

    async def test_step7_option_a_swaps_fluid_allocation(self, base_state):
        from hx_engine.app.steps.step_07_tube_side_h import Step07TubeSideH
        base_state.shell_side_fluid = "hot"
        result = await Step07TubeSideH().apply_user_override(base_state, option_index=0, text="")
        assert result == 3
        assert base_state.shell_side_fluid == "cold"

    async def test_step7_option_b_modifies_geometry(self, base_state):
        from hx_engine.app.models.design_state import GeometrySpec
        from hx_engine.app.steps.step_07_tube_side_h import Step07TubeSideH
        base_state.geometry = GeometrySpec(
            n_tubes=200, n_passes=1, shell_diameter_m=0.5,
            tube_od_m=0.02, tube_id_m=0.016, tube_length_m=3.0,
            baffle_spacing_m=0.2, pitch_ratio=1.25, baffle_cut=0.25,
        )
        result = await Step07TubeSideH().apply_user_override(base_state, option_index=1, text="")
        assert result is None
        assert base_state.geometry.n_tubes == 100
        assert base_state.geometry.n_passes == 2

    async def test_step7_option_b_respects_n_passes_limit(self, base_state):
        from hx_engine.app.models.design_state import GeometrySpec
        from hx_engine.app.steps.step_07_tube_side_h import Step07TubeSideH
        base_state.geometry = GeometrySpec(
            n_tubes=100, n_passes=6, shell_diameter_m=0.5,
            tube_od_m=0.02, tube_id_m=0.016, tube_length_m=3.0,
            baffle_spacing_m=0.2, pitch_ratio=1.25, baffle_cut=0.25,
        )
        await Step07TubeSideH().apply_user_override(base_state, option_index=1, text="")
        assert base_state.geometry.n_passes == 8

    async def test_step7_regex_fallback_for_velocity_increase(self, base_state):
        from hx_engine.app.models.design_state import GeometrySpec
        from hx_engine.app.steps.step_07_tube_side_h import Step07TubeSideH
        base_state.geometry = GeometrySpec(
            n_tubes=200, n_passes=1, shell_diameter_m=0.5,
            tube_od_m=0.02, tube_id_m=0.016, tube_length_m=3.0,
            baffle_spacing_m=0.2, pitch_ratio=1.25, baffle_cut=0.25,
        )
        await Step07TubeSideH().apply_user_override(
            base_state, option_index=-1, text="Please reduce n_tubes and increase velocity",
        )
        assert base_state.geometry.n_tubes == 100
        assert base_state.geometry.n_passes == 2


# ===================================================================
# Phase 4 Tests: Termination Intent Detection
# ===================================================================

class TestTerminationIntentDetection:
    """Unit tests for is_termination_intent — phrase matching logic."""

    def test_flag_design_as_impractical(self):
        """Option text 'Flag design as impractical...' triggers termination."""
        text = "Flag design as impractical and recommend plate or double-pipe exchanger to the user"
        assert is_termination_intent(text) is True

    def test_terminate_keyword(self):
        """Text containing 'terminate' triggers termination."""
        assert is_termination_intent("Terminate this shell-and-tube design path entirely") is True

    def test_not_viable(self):
        """Text containing 'not viable' triggers termination."""
        assert is_termination_intent("This design is not viable for S&T") is True

    def test_recommend_plate(self):
        """Text containing 'recommend plate' triggers termination."""
        assert is_termination_intent("Recommend plate exchanger for this duty") is True

    def test_recommend_double_pipe(self):
        """Text containing 'recommend double-pipe' triggers termination."""
        assert is_termination_intent("recommend double-pipe exchanger instead") is True

    def test_abort_design(self):
        """Text containing 'abort design' triggers termination."""
        assert is_termination_intent("abort design and start over") is True

    def test_no_further_steps(self):
        """Text containing 'no further steps' triggers termination."""
        text = "no further steps possible"
        assert is_termination_intent(text) is True

    def test_case_insensitive(self):
        """Termination detection is case-insensitive."""
        assert is_termination_intent("FLAG DESIGN AS IMPRACTICAL") is True
        assert is_termination_intent("Terminate This Design") is True

    def test_normal_override_not_termination(self):
        """Normal override text like 'swap fluid' is NOT termination."""
        assert is_termination_intent("swap fluid allocation") is False

    def test_proceed_not_termination(self):
        """Text like 'proceed with minimum TEMA' is NOT termination."""
        assert is_termination_intent("proceed with minimum TEMA shell geometry") is False

    def test_empty_string_not_termination(self):
        """Empty string is NOT termination."""
        assert is_termination_intent("") is False

    def test_accept_not_termination(self):
        """Acceptance phrases are NOT termination."""
        assert is_termination_intent("yes, go ahead") is False
        assert is_termination_intent("accept") is False


# ===================================================================
# Phase 5 Tests: Pipeline Termination via Escalation Response
# ===================================================================

class TestEscalationTerminatesDesign:
    """User picks a termination option during ESCALATE → pipeline stops."""

    @pytest.mark.asyncio
    async def test_escalation_response_terminates_pipeline(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """When user responds with 'flag as impractical', pipeline terminates."""
        # Arrange: step always returns ESCALATE
        escalate_review = _make_escalate_review(
            reasoning="Duty too small for S&T — only 292 W",
            options=[
                "Flag design as impractical and recommend plate or double-pipe exchanger",
                "Proceed with minimum TEMA shell geometry",
            ],
        )
        result_escalated = StepResult(
            step_id=6, step_name="Initial U",
            outputs={"U_W_m2K": 500},
            ai_review=escalate_review,
        )
        mock_step = MockStep(result_escalated)
        mock_step.step_id = 6
        mock_step.step_name = "Initial U"

        passed_vr = _make_validation_result(passed=True)

        # User selects option A: "Flag design as impractical..."
        def _termination_future(_sid):
            fut = asyncio.Future()
            fut.set_result({
                "type": "override",
                "values": {
                    "user_input": "Flag design as impractical and recommend plate or double-pipe exchanger",
                    "option_index": 0,
                },
            })
            return fut

        mock_sse_manager.create_user_response_future = MagicMock(side_effect=_termination_future)

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [lambda: mock_step],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=passed_vr,
        ):
            state = await pipeline_runner.run(base_state)

        # Assert: pipeline terminated, NOT error
        assert state.pipeline_status == "terminated"
        assert state.termination_reason is not None
        assert "Step 6" in state.termination_reason

    @pytest.mark.asyncio
    async def test_termination_emits_step_error_event(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """Termination emits step_error SSE event with the reason."""
        escalate_review = _make_escalate_review(
            reasoning="292 W duty is impractical for S&T",
            options=["Terminate this design path entirely", "Proceed anyway"],
        )
        result_escalated = StepResult(
            step_id=6, step_name="Initial U",
            outputs={},
            ai_review=escalate_review,
        )
        mock_step = MockStep(result_escalated)
        mock_step.step_id = 6
        mock_step.step_name = "Initial U"

        passed_vr = _make_validation_result(passed=True)

        def _termination_future(_sid):
            fut = asyncio.Future()
            fut.set_result({
                "type": "override",
                "values": {
                    "user_input": "Terminate this design path entirely",
                    "option_index": 0,
                },
            })
            return fut

        mock_sse_manager.create_user_response_future = MagicMock(side_effect=_termination_future)

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [lambda: mock_step],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=passed_vr,
        ):
            await pipeline_runner.run(base_state)

        event_types = _get_emitted_event_types(mock_sse_manager)
        assert "step_error" in event_types
        # The step_error should contain termination details
        error_events = [
            e for e in mock_sse_manager.emitted_events
            if isinstance(e, dict) and e.get("event_type") == "step_error"
        ]
        assert len(error_events) == 1
        assert "terminated" in error_events[0].get("message", "").lower()

    @pytest.mark.asyncio
    async def test_non_termination_response_continues_pipeline(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """When user picks a non-termination option, pipeline re-runs the step."""
        # First call: ESCALATE; second call after user response: PROCEED
        call_count = 0
        proceed_review = _make_proceed_review(confidence=0.85)
        escalate_review = _make_escalate_review(
            options=["Proceed with minimum geometry", "Swap fluids"],
        )

        class FlipStep(BaseStep):
            step_id = 6
            step_name = "Initial U"
            ai_mode = AIModeEnum.FULL

            async def execute(self, state):
                return StepResult(step_id=6, step_name="Initial U", outputs={})

            async def run_with_review_loop(self, state, ai_engineer):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return StepResult(
                        step_id=6, step_name="Initial U",
                        outputs={}, ai_review=escalate_review,
                    )
                return StepResult(
                    step_id=6, step_name="Initial U",
                    outputs={}, ai_review=proceed_review,
                )

        passed_vr = _make_validation_result(passed=True)

        def _non_termination_future(_sid):
            fut = asyncio.Future()
            fut.set_result({
                "type": "override",
                "values": {
                    "user_input": "Proceed with minimum geometry",
                    "option_index": 0,
                },
            })
            return fut

        mock_sse_manager.create_user_response_future = MagicMock(
            side_effect=_non_termination_future,
        )

        async def _noop_post(state, session_id, step=None):
            return state

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [FlipStep],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=passed_vr,
        ), patch.object(
            pipeline_runner, "_run_convergence_loop", return_value=base_state,
        ), patch.object(
            pipeline_runner, "_run_post_convergence_step", side_effect=_noop_post,
        ):
            state = await pipeline_runner.run(base_state)

        # Pipeline should NOT be terminated — it should complete
        assert state.pipeline_status == "completed"
        assert state.termination_reason is None
        assert call_count == 2  # step ran twice: escalate then proceed


class TestWarningTerminatesDesign:
    """User picks a termination option during actionable WARNING → pipeline stops."""

    @pytest.mark.asyncio
    async def test_warning_response_terminates_pipeline(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """When user responds with 'impractical' to a warning, pipeline terminates."""
        warn_review = AIReview(
            decision=AIDecisionEnum.WARN,
            confidence=0.6,
            reasoning="292 W duty is grossly overdesigned for smallest TEMA shell",
            options=[
                "Flag design as impractical and recommend plate exchanger",
                "Proceed with minimum TEMA shell geometry and document overdesign",
            ],
            ai_called=True,
        )
        result_warned = StepResult(
            step_id=6, step_name="Tube Layout",
            outputs={"U_W_m2K": 500},
            ai_review=warn_review,
        )
        mock_step = MockStep(result_warned)
        mock_step.step_id = 6
        mock_step.step_name = "Tube Layout"

        passed_vr = _make_validation_result(passed=True)

        # User selects the impractical option
        def _termination_future(_sid):
            fut = asyncio.Future()
            fut.set_result({
                "type": "override",
                "values": {
                    "user_input": "Flag design as impractical and recommend plate exchanger",
                    "option_index": 0,
                },
            })
            return fut

        mock_sse_manager.create_user_response_future = MagicMock(side_effect=_termination_future)

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [lambda: mock_step],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=passed_vr,
        ):
            state = await pipeline_runner.run(base_state)

        assert state.pipeline_status == "terminated"
        assert state.termination_reason is not None
        assert "Step 6" in state.termination_reason

    @pytest.mark.asyncio
    async def test_warning_non_termination_continues(
        self, pipeline_runner, mock_sse_manager, mock_session_store, base_state
    ):
        """When user picks a non-termination warning option, step re-runs."""
        call_count = 0
        proceed_review = _make_proceed_review(confidence=0.85)
        warn_review = AIReview(
            decision=AIDecisionEnum.WARN,
            confidence=0.6,
            reasoning="Overdesigned but acceptable",
            options=["Proceed with overdesign noted", "Try smaller geometry"],
            ai_called=True,
        )

        class FlipWarnStep(BaseStep):
            step_id = 6
            step_name = "Tube Layout"
            ai_mode = AIModeEnum.FULL

            async def execute(self, state):
                return StepResult(step_id=6, step_name="Tube Layout", outputs={})

            async def run_with_review_loop(self, state, ai_engineer):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return StepResult(
                        step_id=6, step_name="Tube Layout",
                        outputs={}, ai_review=warn_review,
                    )
                return StepResult(
                    step_id=6, step_name="Tube Layout",
                    outputs={}, ai_review=proceed_review,
                )

        passed_vr = _make_validation_result(passed=True)

        def _non_termination_future(_sid):
            fut = asyncio.Future()
            fut.set_result({
                "type": "override",
                "values": {
                    "user_input": "Proceed with overdesign noted",
                    "option_index": 0,
                },
            })
            return fut

        mock_sse_manager.create_user_response_future = MagicMock(
            side_effect=_non_termination_future,
        )

        async def _noop_post(state, session_id, step=None):
            return state

        with patch(
            "hx_engine.app.core.pipeline_runner.PIPELINE_STEPS",
            [FlipWarnStep],
        ), patch(
            "hx_engine.app.core.pipeline_runner.check_validation_rules",
            return_value=passed_vr,
        ), patch.object(
            pipeline_runner, "_run_convergence_loop", return_value=base_state,
        ), patch.object(
            pipeline_runner, "_run_post_convergence_step", side_effect=_noop_post,
        ):
            state = await pipeline_runner.run(base_state)

        assert state.pipeline_status == "completed"
        assert state.termination_reason is None
        assert call_count == 2


class TestDesignStateTerminationField:
    """Verify the termination_reason field on DesignState."""

    def test_default_termination_reason_is_none(self):
        """DesignState.termination_reason defaults to None."""
        state = DesignState(session_id="test-123")
        assert state.termination_reason is None

    def test_terminated_status_is_valid(self):
        """'terminated' is an acceptable pipeline_status value."""
        state = DesignState(session_id="test-123")
        state.pipeline_status = "terminated"
        state.termination_reason = "User chose to abandon S&T design"
        assert state.pipeline_status == "terminated"
        assert state.termination_reason is not None
