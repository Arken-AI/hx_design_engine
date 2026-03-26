"""Tests for Piece 10: Step 1 full execute() integration."""

import copy
import json

import pytest

from hx_engine.app.models.design_state import DesignState
from hx_engine.app.steps.base import StepProtocol
from hx_engine.app.steps.step_01_requirements import Step01Requirements


class TestStep01Integration:

    async def test_execute_structured_json(self):
        data = json.dumps({
            "hot_fluid": "crude oil",
            "cold_fluid": "cooling water",
            "T_hot_in": 150.0,
            "T_hot_out": 90.0,
            "T_cold_in": 30.0,
            "m_dot_hot": 50.0,
        })
        state = DesignState(raw_request=data)
        step = Step01Requirements()
        result = await step.execute(state)
        assert result.validation_passed
        assert result.outputs["T_hot_in_C"] == 150.0

    async def test_execute_natural_language(self):
        state = DesignState(
            raw_request=(
                "Design a heat exchanger for cooling 50 kg/s of crude oil "
                "from 150°C to 90°C using cooling water at 30°C"
            )
        )
        step = Step01Requirements()
        result = await step.execute(state)
        assert result.validation_passed
        assert result.outputs["m_dot_hot_kg_s"] == pytest.approx(50.0)

    async def test_execute_invalid_json_falls_to_nl(self):
        state = DesignState(
            raw_request=(
                "{broken json} cooling 50 kg/s of crude oil "
                "from 150°C to 90°C using cooling water at 30°C"
            )
        )
        step = Step01Requirements()
        result = await step.execute(state)
        # Falls through to NL parser — may or may not succeed,
        # but should NOT crash
        assert result is not None

    async def test_execute_3_temps_marks_missing(self):
        data = json.dumps({
            "hot_fluid": "crude oil",
            "cold_fluid": "cooling water",
            "T_hot_in": 150.0,
            "T_hot_out": 90.0,
            "T_cold_in": 30.0,
            "m_dot_hot": 50.0,
        })
        state = DesignState(raw_request=data)
        step = Step01Requirements()
        result = await step.execute(state)
        assert result.outputs["missing_T_cold_out"] is True

    async def test_execute_output_fields_match_design_state(self):
        data = json.dumps({
            "hot_fluid": "crude oil",
            "cold_fluid": "cooling water",
            "T_hot_in": 150.0,
            "T_hot_out": 90.0,
            "T_cold_in": 30.0,
            "m_dot_hot": 50.0,
        })
        state = DesignState(raw_request=data)
        step = Step01Requirements()
        result = await step.execute(state)
        # All output keys that map to DesignState fields
        state_fields = set(DesignState.model_fields.keys())
        for key in result.outputs:
            if key.startswith("missing_"):
                continue
            assert key in state_fields, f"Output key '{key}' not in DesignState"

    async def test_execute_does_not_mutate_input_state(self):
        data = json.dumps({
            "hot_fluid": "crude oil",
            "cold_fluid": "cooling water",
            "T_hot_in": 150.0,
            "T_hot_out": 90.0,
            "T_cold_in": 30.0,
            "m_dot_hot": 50.0,
        })
        state = DesignState(raw_request=data)
        state_before = state.model_dump()
        step = Step01Requirements()
        await step.execute(state)
        state_after = state.model_dump()
        assert state_before == state_after

    def test_step_01_is_step_protocol(self):
        step = Step01Requirements()
        assert isinstance(step, StepProtocol)

    async def test_execute_benchmark_request(self):
        state = DesignState(
            raw_request=(
                "Design a heat exchanger for cooling 50 kg/s of crude oil "
                "from 150°C to 90°C using cooling water at 30°C"
            )
        )
        step = Step01Requirements()
        result = await step.execute(state)
        assert result.validation_passed
        o = result.outputs
        assert o["hot_fluid_name"] == "crude oil"
        assert o["cold_fluid_name"] == "cooling water"
        assert o["T_hot_in_C"] == pytest.approx(150.0)
        assert o["m_dot_hot_kg_s"] == pytest.approx(50.0)
