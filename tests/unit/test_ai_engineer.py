"""Tests for AI Engineer — step-wise prompts + parsing."""

import logging

import pytest

from hx_engine.app.core.ai_engineer import (
    AIEngineer,
    _BASE_PROMPT,
    _STEP_PROMPTS,
    _build_system_prompt,
    _build_step_context,
)
from hx_engine.app.models.design_state import DesignState
from hx_engine.app.models.step_result import AIDecisionEnum, AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep


class _DummyStep(BaseStep):
    step_id = 1
    step_name = "Dummy"
    ai_mode = AIModeEnum.NONE

    async def execute(self, state):
        return StepResult(step_id=1, step_name="Dummy")


# -----------------------------------------------------------------------
# Stub-mode tests (original)
# -----------------------------------------------------------------------

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

    async def test_recommendation_defaults_none(self):
        ai = AIEngineer(stub_mode=True)
        review = await ai.review(_DummyStep(), DesignState(), StepResult(step_id=1, step_name="T"))
        assert review.recommendation is None
        assert review.options == []


# -----------------------------------------------------------------------
# Step-wise prompt assembly
# -----------------------------------------------------------------------

class TestBuildSystemPrompt:
    """Verify _build_system_prompt assembles Base + Step correctly."""

    @pytest.mark.parametrize("step_id", [1, 2, 3, 4, 5])
    def test_contains_base_prompt(self, step_id):
        prompt = _build_system_prompt(step_id, f"Step {step_id}")
        assert "senior heat exchanger design engineer" in prompt

    @pytest.mark.parametrize(
        "step_id, expected_fragment",
        [
            (1, "Process Requirements"),
            (2, "Heat Duty Calculation"),
            (3, "Fluid Properties"),
            (4, "TEMA Type"),
            (5, "LMTD"),
        ],
    )
    def test_contains_step_specific_content(self, step_id, expected_fragment):
        prompt = _build_system_prompt(step_id, f"Step {step_id}")
        assert expected_fragment in prompt

    def test_step1_has_fluid_name_rules(self):
        prompt = _build_system_prompt(1, "Process Requirements")
        assert "FLUID NAME RULES" in prompt

    def test_step1_has_scope_check(self):
        prompt = _build_system_prompt(1, "Process Requirements")
        assert "PHASE SCOPE CHECK" in prompt

    def test_step4_has_tema_selection(self):
        prompt = _build_system_prompt(4, "TEMA Geometry")
        assert "TEMA Type Selection" in prompt
        assert "Fouling Factors" in prompt

    def test_step5_has_lmtd_formulas(self):
        prompt = _build_system_prompt(5, "LMTD")
        assert "LMTD" in prompt
        assert "F-FACTOR" in prompt

    def test_step2_no_fluid_name_rules(self):
        """Step 2 should NOT have fluid name rules (Step 1 only)."""
        prompt = _build_system_prompt(2, "Heat Duty")
        assert "FLUID NAME RULES" not in prompt

    def test_step3_no_tema_rules(self):
        """Step 3 should NOT have TEMA rules (Step 4 only)."""
        prompt = _build_system_prompt(3, "Fluid Properties")
        assert "TEMA Type Selection" not in prompt

    def test_unknown_step_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="hx_engine.app.core.ai_engineer"):
            prompt = _build_system_prompt(99, "Unknown Step")
        assert "No step-specific prompt defined for step_id=99" in caplog.text
        # Should still contain the base prompt
        assert "senior heat exchanger design engineer" in prompt

    def test_all_5_steps_registered(self):
        for sid in (1, 2, 3, 4, 5):
            assert sid in _STEP_PROMPTS, f"Step {sid} missing from _STEP_PROMPTS"


# -----------------------------------------------------------------------
# _build_step_context
# -----------------------------------------------------------------------

class TestBuildStepContext:
    def test_step1_returns_empty(self):
        ctx = _build_step_context(1, DesignState(), StepResult(step_id=1, step_name="S1"))
        assert ctx == ""

    def test_step2_energy_balance(self):
        result = StepResult(
            step_id=2, step_name="Heat Duty",
            outputs={
                "Q_hot_W": 1_000_000.0,
                "Q_cold_W": 980_000.0,
                "Q_W": 990_000.0,
                "energy_imbalance_pct": 2.0,
            },
        )
        ctx = _build_step_context(2, DesignState(), result)
        assert "Q_hot" in ctx
        assert "Q_cold" in ctx
        assert "Imbalance" in ctx

    def test_step4_geometry_ratios(self):
        from hx_engine.app.models.design_state import GeometrySpec
        geom = GeometrySpec(
            tube_od_m=0.01905, tube_id_m=0.01483,
            tube_length_m=4.877, pitch_ratio=1.25,
            shell_diameter_m=0.5, baffle_spacing_m=0.2,
            baffle_cut=0.25, n_tubes=100,
        )
        state = DesignState(T_hot_in_C=150, T_hot_out_C=90, T_cold_in_C=30, T_cold_out_C=60)
        result = StepResult(step_id=4, step_name="TEMA", outputs={"geometry": geom})
        ctx = _build_step_context(4, state, result)
        assert "Tube ID < OD check" in ctx
        assert "Pitch ratio" in ctx
        assert "Baffle/shell ratio" in ctx

    def test_step5_lmtd_context(self):
        state = DesignState(
            T_hot_in_C=150, T_hot_out_C=90,
            T_cold_in_C=30, T_cold_out_C=60,
        )
        result = StepResult(
            step_id=5, step_name="LMTD",
            outputs={"R": 2.0, "P": 0.25, "F_factor": 0.92},
        )
        ctx = _build_step_context(5, state, result)
        assert "ΔT₁" in ctx
        assert "ΔT₂" in ctx
        assert "R = 2.000" in ctx
        assert "F = 0.920" in ctx

    def test_context_survives_missing_data(self):
        """_build_step_context must not crash on None fields."""
        state = DesignState()  # all None
        result = StepResult(step_id=4, step_name="TEMA", outputs={})
        ctx = _build_step_context(4, state, result)
        # Should return empty string, not crash
        assert isinstance(ctx, str)


# -----------------------------------------------------------------------
# _parse_review — recommendation + options
# -----------------------------------------------------------------------

class TestParseReview:
    def _parse(self, text):
        ai = AIEngineer(stub_mode=True)
        return ai._parse_review(text)

    def test_escalation_with_recommendation(self):
        import json
        data = {
            "decision": "escalate",
            "confidence": 0.3,
            "reasoning": "Cannot proceed",
            "corrections": [],
            "recommendation": "Please provide the correct fouling factor",
            "options": ["Use R_f=0.0003", "Provide your own value"],
        }
        review = self._parse(json.dumps(data))
        assert review.decision == AIDecisionEnum.ESCALATE
        assert review.recommendation == "Please provide the correct fouling factor"
        assert len(review.options) == 2
        assert "Use R_f=0.0003" in review.options

    def test_proceed_no_recommendation(self):
        import json
        data = {
            "decision": "proceed",
            "confidence": 0.95,
            "reasoning": "All good",
            "corrections": [],
        }
        review = self._parse(json.dumps(data))
        assert review.decision == AIDecisionEnum.PROCEED
        assert review.recommendation is None
        assert review.options == []

    def test_options_wrong_type_handled(self):
        import json
        data = {
            "decision": "escalate",
            "confidence": 0.4,
            "reasoning": "Bad",
            "corrections": [],
            "recommendation": "Fix it",
            "options": "not a list",
        }
        review = self._parse(json.dumps(data))
        assert review.options == []

    def test_unparseable_response(self):
        review = self._parse("This is not JSON at all")
        assert review.decision == AIDecisionEnum.WARN
        assert review.ai_called is True
