"""Tests for AI Engineer — step-wise prompts + parsing."""

import logging

import pytest

from hx_engine.app.core.ai_engineer import (
    AIEngineer,
    _BASE_PROMPT,
    _STEP_FILE_NAMES,
    _load_skill,
    SKILLS_DIR,
    _build_system_prompt,
)
from hx_engine.app.models.design_state import DesignState
from hx_engine.app.models.step_result import AIDecisionEnum, AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep
from hx_engine.app.steps.step_02_heat_duty import Step02HeatDuty
from hx_engine.app.steps.step_04_tema_geometry import Step04TEMAGeometry
from hx_engine.app.steps.step_05_lmtd import Step05LMTD


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
            # Step 1 excluded: ai_mode=NONE, _build_system_prompt never called in production
            (2, "Heat Duty Calculation"),
            (3, "Fluid Properties"),
            (4, "TEMA Type"),
            (5, "LMTD"),
        ],
    )
    def test_contains_step_specific_content(self, step_id, expected_fragment):
        prompt = _build_system_prompt(step_id, f"Step {step_id}")
        assert expected_fragment in prompt

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

    def test_steps_2_to_16_have_skill_file_entries(self):
        """Steps with AI review must have an entry in _STEP_FILE_NAMES.
        Step 1 is excluded: ai_mode=NONE means no skill file is needed.
        """
        for sid in range(2, 17):
            assert sid in _STEP_FILE_NAMES, f"Step {sid} missing from _STEP_FILE_NAMES"
        assert 1 not in _STEP_FILE_NAMES, (
            "Step 1 has ai_mode=NONE and must not have a _STEP_FILE_NAMES entry"
        )

    def test_steps_2_to_16_have_md_skill_files_on_disk(self):
        """Steps 2–16 must have a corresponding .md skill file on disk.
        Step 1 is excluded: ai_mode=NONE means no skill file is needed or expected.
        """
        for sid in range(2, 17):
            filename = _STEP_FILE_NAMES.get(sid)
            assert filename, f"Step {sid} missing from _STEP_FILE_NAMES"
            skill_path = SKILLS_DIR / filename
            assert skill_path.exists(), f"Skill file missing: {skill_path}"
        # The deleted Step 1 skill file must not silently reappear.
        assert not (SKILLS_DIR / "step_01_requirements.md").exists(), (
            "step_01_requirements.md was deliberately removed (ai_mode=NONE) "
            "and must not be reintroduced"
        )


# -----------------------------------------------------------------------
# Skill file loader
# -----------------------------------------------------------------------

class TestSkillLoader:
    def test_missing_file_returns_empty_string(self, tmp_path, caplog):
        """Missing .md file must log WARNING and return empty string."""
        from unittest.mock import patch
        from hx_engine.app.core import ai_engineer
        # Clear cache for this test
        original_cache = ai_engineer._SKILL_CACHE.copy()
        ai_engineer._SKILL_CACHE.clear()
        try:
            with patch.object(ai_engineer, "SKILLS_DIR", tmp_path):
                with caplog.at_level(logging.WARNING):
                    result = _load_skill("nonexistent_step.md")
            assert result == ""
            assert "could not load skill file" in caplog.text.lower()
        finally:
            ai_engineer._SKILL_CACHE.clear()
            ai_engineer._SKILL_CACHE.update(original_cache)

    def test_skill_file_loaded_and_cached(self, tmp_path):
        """Skill file content is loaded and cached."""
        from unittest.mock import patch
        from hx_engine.app.core import ai_engineer
        original_cache = ai_engineer._SKILL_CACHE.copy()
        ai_engineer._SKILL_CACHE.clear()
        try:
            (tmp_path / "test_skill.md").write_text("Test prompt content")
            with patch.object(ai_engineer, "SKILLS_DIR", tmp_path):
                result = _load_skill("test_skill.md")
            assert result == "Test prompt content"
            assert "test_skill.md" in ai_engineer._SKILL_CACHE
        finally:
            ai_engineer._SKILL_CACHE.clear()
            ai_engineer._SKILL_CACHE.update(original_cache)


# -----------------------------------------------------------------------
# _build_step_context
# -----------------------------------------------------------------------

class TestBuildStepContext:
    def test_step1_returns_empty(self):
        # Step 1 has no build_ai_context override — base returns ""
        from hx_engine.app.steps.step_01_requirements import Step01Requirements
        step = Step01Requirements()
        ctx = step.build_ai_context(DesignState(), StepResult(step_id=1, step_name="S1"))
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
        ctx = Step02HeatDuty().build_ai_context(DesignState(), result)
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
        ctx = Step04TEMAGeometry().build_ai_context(state, result)
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
        ctx = Step05LMTD().build_ai_context(state, result)
        assert "ΔT₁" in ctx
        assert "ΔT₂" in ctx
        assert "R = 2.000" in ctx
        assert "F = 0.920" in ctx

    def test_context_survives_missing_data(self):
        """build_ai_context must not crash on None fields."""
        state = DesignState()  # all None
        result = StepResult(step_id=4, step_name="TEMA", outputs={})
        ctx = Step04TEMAGeometry().build_ai_context(state, result)
        # Should return empty string, not crash
        assert isinstance(ctx, str)


# -----------------------------------------------------------------------
# TestBuildAiContextScaffolding
# -----------------------------------------------------------------------

class TestBuildAiContextScaffolding:
    def test_migrated_step_routes_to_hook(self):
        """After Phase 1.17 _build_review_prompt always delegates to step.build_ai_context()."""
        step = Step02HeatDuty()
        state = DesignState()
        result = StepResult(
            step_id=2, step_name="Heat Duty",
            outputs={"Q_hot_W": 1_000_000.0, "Q_cold_W": 980_000.0},
        )
        ai = AIEngineer(stub_mode=True)
        prompt = ai._build_review_prompt(step, state, result)
        assert "Q_hot" in prompt

    def test_hook_exception_swallowed(self, caplog):
        """If build_ai_context() raises, the exception is swallowed and logged at DEBUG."""
        from unittest.mock import patch
        step = Step02HeatDuty()
        state = DesignState()
        result = StepResult(step_id=2, step_name="Heat Duty", outputs={})
        ai = AIEngineer(stub_mode=True)
        with patch.object(step, "build_ai_context", side_effect=ValueError("boom")):
            with caplog.at_level(logging.DEBUG):
                prompt = ai._build_review_prompt(step, state, result)
        assert "### Computed Context" not in prompt
        assert "build_ai_context failed" in caplog.text


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

    def test_nested_json_with_options_array(self):
        """raw_decode must handle nested structures that the old regex missed."""
        raw = 'Here is my review: {"decision":"escalate","confidence":0.5,"reasoning":"x","corrections":[],"options":["a","b"]}'
        review = self._parse(raw)
        assert review.decision == AIDecisionEnum.ESCALATE
        assert review.confidence == 0.5
        assert review.options == ["a", "b"]

    def test_malformed_json_logs_warning(self, caplog):
        """Malformed JSON must log a warning, not silently return empty."""
        import logging
        with caplog.at_level(logging.WARNING):
            review = self._parse("Some preamble {broken json")
        assert review.decision == AIDecisionEnum.WARN
        assert "could not decode" in caplog.text.lower()


# -----------------------------------------------------------------------
# _call_claude — cache_control in system param
# -----------------------------------------------------------------------

class TestCallClaudeCacheControl:
    @pytest.mark.asyncio
    async def test_system_prompt_sent_as_list_with_cache_control(self):
        """system param must be a list with cache_control, not a plain string."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock()
        mock_block = MagicMock()
        mock_block.text = '{"decision":"proceed","confidence":0.95,"reasoning":"ok","corrections":[]}'
        mock_response.content = [mock_block]

        mock_client = AsyncMock()
        mock_client.messages.create.return_value = mock_response

        with patch("hx_engine.app.core.ai_engineer.settings") as mock_settings:
            mock_settings.anthropic_api_key = "test-key"
            engineer = AIEngineer(stub_mode=False)
            engineer._client = mock_client

        state = DesignState()
        step = _DummyStep()
        result = StepResult(step_id=1, step_name="Dummy")

        review = await engineer._call_claude(step, state, result)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert isinstance(call_kwargs["system"], list)
        assert call_kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert review.decision == AIDecisionEnum.PROCEED
