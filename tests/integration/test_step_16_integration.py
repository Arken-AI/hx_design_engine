"""Tests for ST-8 — Step 16 integration tests.

End-to-end tests with realistic DesignState values.
"""

from __future__ import annotations

import pytest

from hx_engine.app.core.validation_rules import check
from hx_engine.app.models.design_state import (
    DesignState,
    GeometrySpec,
)
from hx_engine.app.models.step_result import (
    AIDecisionEnum,
    AIReview,
    StepRecord,
)
from hx_engine.app.steps.step_16_final_validation import (
    CONFIDENCE_WEIGHTS,
    Step16FinalValidation,
    _compute_ai_agreement_rate,
    _compute_confidence_score,
    _compute_geometry_convergence,
    _compute_validation_pass_rate,
)


def _make_step_record(
    step_id: int = 1,
    ai_called: bool = False,
    ai_decision: AIDecisionEnum | None = None,
    validation_passed: bool = True,
) -> StepRecord:
    """Create a minimal StepRecord for testing."""
    return StepRecord(
        step_id=step_id,
        step_name=f"Step {step_id}",
        ai_called=ai_called,
        ai_decision=ai_decision,
        validation_passed=validation_passed,
    )


def _full_state(**overrides) -> DesignState:
    """State with all Steps 1-15 data populated."""
    # Build 15 step records — all passed, 6 with AI calls (all PROCEED)
    records = []
    for i in range(1, 16):
        ai_called = i in {2, 3, 4, 7, 8, 9}
        records.append(_make_step_record(
            step_id=i,
            ai_called=ai_called,
            ai_decision=AIDecisionEnum.PROCEED if ai_called else None,
            validation_passed=True,
        ))

    defaults = dict(
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=55.0,
        T_mean_hot_C=120.0,
        T_mean_cold_C=42.5,
        Q_W=1_500_000.0,
        LMTD_K=65.0,
        F_factor=0.92,
        U_W_m2K=350.0,
        U_overall_W_m2K=380.0,
        A_m2=47.0,
        overdesign_pct=18.0,
        dP_tube_Pa=25_000.0,
        dP_shell_Pa=30_000.0,
        tube_velocity_m_s=1.8,
        tema_type="BEM",
        tema_class="R",
        shell_side_fluid="hot",
        hot_fluid_name="crude oil",
        cold_fluid_name="cooling water",
        tube_material="carbon_steel",
        shell_material="sa516_gr70",
        convergence_converged=True,
        convergence_iteration=7,
        vibration_safe=True,
        vibration_details={"fluidelastic": {"safe": True}},
        tube_thickness_ok=True,
        shell_thickness_ok=True,
        expansion_mm=1.5,
        mechanical_details={
            "tube": {"actual_wall_mm": 2.11, "min_wall_mm": 1.65},
            "shell": {"actual_wall_mm": 7.04, "min_wall_mm": 5.2},
        },
        cost_usd=85_000.0,
        cost_breakdown={"cost_per_m2_usd": 1808.0},
        area_provided_m2=47.0,
        step_records=records,
        completed_steps=list(range(1, 16)),
        geometry=GeometrySpec(
            tube_od_m=0.01905,
            tube_id_m=0.01483,
            shell_diameter_m=0.489,
            tube_length_m=4.877,
            baffle_spacing_m=0.127,
            baffle_cut=0.25,
            n_tubes=158,
            n_passes=2,
            tube_pitch_m=0.0238,
            pitch_ratio=1.25,
            n_baffles=37,
        ),
    )
    defaults.update(overrides)
    return DesignState(**defaults)


@pytest.fixture
def step():
    return Step16FinalValidation()


# ======================================================================
# Geometry convergence helper
# ======================================================================

class TestGeometryConvergence:
    """T2.1–T2.7: geometry convergence score."""

    def test_converged_5_iters(self):
        """T2.1: Converged in 5 iterations → 1.0."""
        assert _compute_geometry_convergence(True, 5) == 1.0

    def test_converged_10_iters(self):
        """T2.2: Converged in 10 iterations → 1.0."""
        assert _compute_geometry_convergence(True, 10) == 1.0

    def test_converged_15_iters(self):
        """T2.3: Converged in 15 iterations → 0.75."""
        assert _compute_geometry_convergence(True, 15) == 0.75

    def test_converged_20_iters(self):
        """T2.4: Converged in 20 iterations → 0.5."""
        assert _compute_geometry_convergence(True, 20) == 0.5

    def test_not_converged(self):
        """T2.5: Not converged → 0.0."""
        assert _compute_geometry_convergence(False, 15) == 0.0

    def test_converged_none(self):
        """T2.6: converged=None → 0.0."""
        assert _compute_geometry_convergence(None, 5) == 0.0

    def test_converged_no_iteration(self):
        """T2.7: converged=True, iteration=None → 1.0."""
        assert _compute_geometry_convergence(True, None) == 1.0


# ======================================================================
# AI agreement rate helper
# ======================================================================

class TestAIAgreementRate:
    """T2.8–T2.12: AI agreement rate."""

    def test_all_proceed(self):
        """T2.8: All AI-called steps returned PROCEED → 1.0."""
        records = [
            _make_step_record(i, ai_called=True, ai_decision=AIDecisionEnum.PROCEED)
            for i in range(1, 7)
        ]
        assert _compute_ai_agreement_rate(records) == 1.0

    def test_partial_proceed(self):
        """T2.9: 4/6 PROCEED, 2 CORRECT → 0.667."""
        records = [
            _make_step_record(i, ai_called=True, ai_decision=AIDecisionEnum.PROCEED)
            for i in range(1, 5)
        ] + [
            _make_step_record(i, ai_called=True, ai_decision=AIDecisionEnum.CORRECT)
            for i in range(5, 7)
        ]
        result = _compute_ai_agreement_rate(records)
        assert abs(result - 4/6) < 0.001

    def test_no_ai_called(self):
        """T2.10: No steps called AI → 0.5."""
        records = [_make_step_record(i, ai_called=False) for i in range(1, 16)]
        assert _compute_ai_agreement_rate(records) == 0.5

    def test_mixed_decisions(self):
        """T2.11: 1 PROCEED, 1 WARN, 1 CORRECT → 1/3."""
        records = [
            _make_step_record(1, ai_called=True, ai_decision=AIDecisionEnum.PROCEED),
            _make_step_record(2, ai_called=True, ai_decision=AIDecisionEnum.WARN),
            _make_step_record(3, ai_called=True, ai_decision=AIDecisionEnum.CORRECT),
        ]
        result = _compute_ai_agreement_rate(records)
        assert abs(result - 1/3) < 0.001

    def test_mixed_ai_called(self):
        """T2.12: Some ai_called=False → only count True."""
        records = [
            _make_step_record(1, ai_called=True, ai_decision=AIDecisionEnum.PROCEED),
            _make_step_record(2, ai_called=False),
            _make_step_record(3, ai_called=True, ai_decision=AIDecisionEnum.CORRECT),
        ]
        result = _compute_ai_agreement_rate(records)
        assert result == 0.5  # 1 proceed / 2 ai_called


# ======================================================================
# Validation pass rate helper
# ======================================================================

class TestValidationPassRate:
    """T2.13–T2.18: validation pass rate."""

    def test_all_first_attempt(self):
        """T2.13: All 15 steps passed first attempt → 1.0."""
        records = [
            _make_step_record(i, validation_passed=True) for i in range(1, 16)
        ]
        assert _compute_validation_pass_rate(records) == 1.0

    def test_partial_first_attempt(self):
        """T2.14: 12/15 passed first attempt → 0.8."""
        records = [
            _make_step_record(i, validation_passed=True) for i in range(1, 13)
        ] + [
            _make_step_record(
                i, ai_called=True,
                ai_decision=AIDecisionEnum.CORRECT,
                validation_passed=True,
            )
            for i in range(13, 16)
        ]
        result = _compute_validation_pass_rate(records)
        assert result == 12 / 15

    def test_correct_not_first_attempt(self):
        """T2.15: ai_decision=CORRECT → NOT first attempt."""
        records = [
            _make_step_record(
                1, ai_called=True,
                ai_decision=AIDecisionEnum.CORRECT,
                validation_passed=True,
            ),
        ]
        assert _compute_validation_pass_rate(records) == 0.0

    def test_no_ai_is_first_attempt(self):
        """T2.16: ai_decision=None, validation_passed=True → first attempt."""
        records = [
            _make_step_record(1, validation_passed=True),
        ]
        assert _compute_validation_pass_rate(records) == 1.0

    def test_warn_with_correction_not_first(self):
        """T2.17: WARN (with corrections) → NOT first attempt."""
        records = [
            _make_step_record(
                1, ai_called=True,
                ai_decision=AIDecisionEnum.WARN,
                validation_passed=True,
            ),
        ]
        # WARN != PROCEED and != None, so not first attempt
        assert _compute_validation_pass_rate(records) == 0.0

    def test_empty_records(self):
        """T2.18: Empty step_records → 0.5 default."""
        assert _compute_validation_pass_rate([]) == 0.5


# ======================================================================
# Overall confidence score
# ======================================================================

class TestConfidenceScore:
    """T2.19–T2.22: weighted confidence score."""

    def test_all_ones(self):
        """T2.19: All components 1.0 → score = 1.0."""
        bd = {k: 1.0 for k in CONFIDENCE_WEIGHTS}
        assert _compute_confidence_score(bd, CONFIDENCE_WEIGHTS) == 1.0

    def test_all_zeros(self):
        """T2.20: All components 0.0 → score = 0.0."""
        bd = {k: 0.0 for k in CONFIDENCE_WEIGHTS}
        assert _compute_confidence_score(bd, CONFIDENCE_WEIGHTS) == 0.0

    def test_mixed_components(self):
        """T2.21: [1.0, 0.8, 0.5, 0.6] → 0.725."""
        bd = {
            "geometry_convergence": 1.0,
            "ai_agreement_rate": 0.8,
            "supermemory_similarity": 0.5,
            "validation_passes": 0.6,
        }
        result = _compute_confidence_score(bd, CONFIDENCE_WEIGHTS)
        assert abs(result - 0.725) < 0.001

    def test_weights_sum_to_one(self):
        """T2.22: Weights sum to 1.0."""
        assert abs(sum(CONFIDENCE_WEIGHTS.values()) - 1.0) < 1e-9


# ======================================================================
# Preconditions
# ======================================================================

class TestPreconditions:
    """T2.23–T2.26: precondition checks."""

    def test_missing_convergence(self):
        """T2.23: Missing convergence_converged → precondition error."""
        missing = Step16FinalValidation._check_preconditions(
            _full_state(convergence_converged=None)
        )
        assert any("convergence_converged" in m for m in missing)

    def test_missing_vibration(self):
        """T2.24: Missing vibration_safe → precondition error."""
        missing = Step16FinalValidation._check_preconditions(
            _full_state(vibration_safe=None)
        )
        assert any("vibration_safe" in m for m in missing)

    def test_missing_cost(self):
        """T2.25: Missing cost_usd → precondition error."""
        missing = Step16FinalValidation._check_preconditions(
            _full_state(cost_usd=None)
        )
        assert any("cost_usd" in m for m in missing)

    def test_all_present(self):
        """T2.26: All preconditions met → no errors."""
        missing = Step16FinalValidation._check_preconditions(_full_state())
        assert missing == []


# ======================================================================
# Full execute()
# ======================================================================

class TestExecute:
    """T2.27–T2.29: full execute()."""

    @pytest.mark.asyncio
    async def test_produces_confidence(self, step):
        """T2.27: execute() with complete state → valid confidence."""
        state = _full_state()
        result = await step.execute(state)
        assert "confidence_score" in result.outputs
        assert "confidence_breakdown" in result.outputs
        bd = result.outputs["confidence_breakdown"]
        assert len(bd) == 4
        assert set(bd.keys()) == set(CONFIDENCE_WEIGHTS.keys())

    @pytest.mark.asyncio
    async def test_writes_to_state(self, step):
        """T2.28: execute() writes confidence_score and breakdown to state."""
        state = _full_state()
        await step.execute(state)
        assert state.confidence_score is not None
        assert state.confidence_breakdown is not None
        assert len(state.confidence_breakdown) == 4

    @pytest.mark.asyncio
    async def test_score_clamped(self, step):
        """T2.29: confidence_score always in [0.0, 1.0]."""
        state = _full_state()
        await step.execute(state)
        assert 0.0 <= state.confidence_score <= 1.0

    @pytest.mark.asyncio
    async def test_precondition_raises(self, step):
        """T2.23: Missing precondition → CalculationError."""
        from hx_engine.app.core.exceptions import CalculationError

        state = _full_state(convergence_converged=None)
        with pytest.raises(CalculationError):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_high_confidence_all_proceed(self, step):
        """T8.4: All PROCEED → ai_agreement_rate close to 1.0."""
        state = _full_state()
        await step.execute(state)
        bd = state.confidence_breakdown
        assert bd["ai_agreement_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_mixed_decisions_lower_agreement(self, step):
        """T8.5: Mixed decisions → ai_agreement_rate < 1.0."""
        records = []
        for i in range(1, 16):
            if i <= 3:
                records.append(_make_step_record(
                    i, ai_called=True, ai_decision=AIDecisionEnum.PROCEED,
                ))
            elif i <= 6:
                records.append(_make_step_record(
                    i, ai_called=True, ai_decision=AIDecisionEnum.CORRECT,
                ))
            else:
                records.append(_make_step_record(i, ai_called=False))
        state = _full_state(step_records=records)
        await step.execute(state)
        assert state.confidence_breakdown["ai_agreement_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_converged_5_iters_geo_1(self, step):
        """T8.6: Converged in 5 iterations → geometry_convergence == 1.0."""
        state = _full_state(convergence_iteration=5)
        await step.execute(state)
        assert state.confidence_breakdown["geometry_convergence"] == 1.0

    @pytest.mark.asyncio
    async def test_not_converged_geo_0(self, step):
        """T8.7: Not converged → geometry_convergence == 0.0."""
        state = _full_state(convergence_converged=False)
        await step.execute(state)
        assert state.confidence_breakdown["geometry_convergence"] == 0.0

    @pytest.mark.asyncio
    async def test_all_first_attempt_pass(self, step):
        """T8.8: All passed first attempt → validation_passes == 1.0."""
        # Default _full_state has all PROCEED or None decisions with passed=True
        state = _full_state()
        await step.execute(state)
        assert state.confidence_breakdown["validation_passes"] == 1.0

    @pytest.mark.asyncio
    async def test_corrections_lower_pass_rate(self, step):
        """T8.9: Some corrections → validation_passes < 1.0."""
        records = []
        for i in range(1, 16):
            if i <= 12:
                records.append(_make_step_record(i, validation_passed=True))
            else:
                records.append(_make_step_record(
                    i, ai_called=True,
                    ai_decision=AIDecisionEnum.CORRECT,
                    validation_passed=True,
                ))
        state = _full_state(step_records=records)
        await step.execute(state)
        assert state.confidence_breakdown["validation_passes"] < 1.0

    @pytest.mark.asyncio
    async def test_fallback_summary(self, step):
        """T8.10: Without AI → fallback design_summary."""
        state = _full_state()
        result = await step.execute(state)
        assert result.outputs["design_summary"]
        assert "BEM" in result.outputs["design_summary"]


# ======================================================================
# Layer 2 rules
# ======================================================================

class TestLayer2Rules:
    """T8.11: Layer 2 rules pass on valid output."""

    @pytest.mark.asyncio
    async def test_valid_result_passes_rules(self, step):
        """T8.11: Valid Step 16 output passes all Layer 2 rules."""
        state = _full_state()
        result = await step.execute(state)
        vr = check(16, result)
        assert vr.passed, f"Layer 2 failed: {vr.errors}"


# ======================================================================
# StepRecord
# ======================================================================

class TestStepRecord:
    """T8.12: Step 16 StepRecord."""

    @pytest.mark.asyncio
    async def test_record_stored(self, step):
        """T8.12: StepRecord stored in state.step_records.

        Note: run_with_review_loop() stores the record (via _record()),
        not execute() directly. We test execute() here — the record
        is created by the base class during the full review loop.
        """
        state = _full_state()
        result = await step.execute(state)
        assert result.step_id == 16
        assert result.step_name == "Final Validation"
