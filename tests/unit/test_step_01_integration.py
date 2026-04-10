"""Integration tests for Step01Requirements — hydration-only step.

Step 1 no longer parses NL or validates physics. It simply reads values
from DesignState (which are pre-validated by POST /requirements) and
emits them as outputs for the pipeline audit trail.
"""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import DesignState
from hx_engine.app.models.step_result import AIModeEnum
from hx_engine.app.steps.base import StepProtocol
from hx_engine.app.steps.step_01_requirements import Step01Requirements


def _state(**kwargs) -> DesignState:
    defaults = {
        "hot_fluid_name": "crude oil",
        "cold_fluid_name": "water",
        "T_hot_in_C": 150.0,
        "T_hot_out_C": 80.0,
        "T_cold_in_C": 25.0,
        "T_cold_out_C": 50.0,
        "m_dot_hot_kg_s": 10.0,
        "P_hot_Pa": 500_000.0,
        "P_cold_Pa": 300_000.0,
    }
    defaults.update(kwargs)
    return DesignState(**defaults)


class TestStep01Integration:

    def test_step_01_is_step_protocol(self):
        step = Step01Requirements()
        assert isinstance(step, StepProtocol)

    def test_step_01_ai_mode_is_none(self):
        step = Step01Requirements()
        assert step.ai_mode == AIModeEnum.NONE

    @pytest.mark.asyncio
    async def test_execute_emits_all_required_fields(self):
        state = _state()
        step = Step01Requirements()
        result = await step.execute(state)

        assert result.step_id == 1
        assert result.step_name == "Process Requirements"
        assert result.validation_passed is True
        assert result.outputs["hot_fluid_name"] == "crude oil"
        assert result.outputs["cold_fluid_name"] == "water"
        assert result.outputs["T_hot_in_C"] == 150.0
        assert result.outputs["T_hot_out_C"] == 80.0
        assert result.outputs["T_cold_in_C"] == 25.0
        assert result.outputs["T_cold_out_C"] == 50.0
        assert result.outputs["m_dot_hot_kg_s"] == 10.0

    @pytest.mark.asyncio
    async def test_pressures_passed_through_correctly(self):
        """Step 1 must NOT overwrite explicit pressures from DesignState."""
        state = _state(P_hot_Pa=500_000.0, P_cold_Pa=300_000.0)
        step = Step01Requirements()
        result = await step.execute(state)

        assert result.outputs["P_hot_Pa"] == 500_000.0
        assert result.outputs["P_cold_Pa"] == 300_000.0

    @pytest.mark.asyncio
    async def test_missing_optional_temps_flagged(self):
        state = _state(T_hot_out_C=None, m_dot_cold_kg_s=None, T_cold_out_C=None)
        step = Step01Requirements()
        result = await step.execute(state)

        assert result.outputs["missing_T_cold_out"] is True
        assert result.outputs["missing_m_dot_cold"] is True

    @pytest.mark.asyncio
    async def test_all_temps_present_flags_false(self):
        state = _state(T_cold_out_C=50.0, m_dot_cold_kg_s=8.0)
        step = Step01Requirements()
        result = await step.execute(state)

        assert result.outputs["missing_T_cold_out"] is False
        assert result.outputs["missing_m_dot_cold"] is False

    @pytest.mark.asyncio
    async def test_tema_preference_passed_through(self):
        state = _state(tema_preference="AES")
        step = Step01Requirements()
        result = await step.execute(state)

        assert result.outputs["tema_preference"] == "AES"

    @pytest.mark.asyncio
    async def test_no_mutations_to_state(self):
        """Step 1 must be read-only — it never modifies DesignState."""
        state = _state()
        state_before = state.model_dump()

        step = Step01Requirements()
        await step.execute(state)

        assert state.model_dump() == state_before

    @pytest.mark.asyncio
    async def test_output_fields_present_in_design_state(self):
        """All non-missing_ outputs must correspond to DesignState fields."""
        state = _state()
        step = Step01Requirements()
        result = await step.execute(state)

        state_fields = set(DesignState.model_fields.keys())
        for key in result.outputs:
            if key.startswith("missing_"):
                continue
            assert key in state_fields, f"Output key '{key}' not in DesignState"
