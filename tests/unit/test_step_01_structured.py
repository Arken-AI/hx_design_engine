"""Tests for Piece 7: Step 1 structured input parser."""

import json

import pytest

from hx_engine.app.models.design_state import DesignState
from hx_engine.app.steps.step_01_requirements import Step01Requirements


async def _run_structured(data: dict) -> tuple:
    """Helper: run Step01 with structured JSON input."""
    state = DesignState(raw_request=json.dumps(data))
    step = Step01Requirements()
    result = await step.execute(state)
    return result, state


class TestStructuredParser:

    async def test_4_temps_2_flows(self):
        result, _ = await _run_structured({
            "hot_fluid": "crude oil",
            "cold_fluid": "cooling water",
            "T_hot_in": 150.0,
            "T_hot_out": 90.0,
            "T_cold_in": 30.0,
            "T_cold_out": 60.0,
            "m_dot_hot": 50.0,
            "m_dot_cold": 80.0,
        })
        assert result.validation_passed
        assert result.outputs["T_hot_in_C"] == 150.0
        assert result.outputs["T_cold_out_C"] == 60.0
        assert result.outputs["m_dot_hot_kg_s"] == 50.0
        assert result.outputs["m_dot_cold_kg_s"] == 80.0

    async def test_3_temps(self):
        result, _ = await _run_structured({
            "hot_fluid": "crude oil",
            "cold_fluid": "cooling water",
            "T_hot_in": 150.0,
            "T_hot_out": 90.0,
            "T_cold_in": 30.0,
            "m_dot_hot": 50.0,
        })
        assert result.validation_passed
        assert result.outputs["missing_T_cold_out"] is True

    async def test_missing_both_fluids(self):
        result, _ = await _run_structured({
            "T_hot_in": 150.0,
            "T_cold_in": 30.0,
            "m_dot_hot": 50.0,
        })
        assert not result.validation_passed

    async def test_temps_in_fahrenheit(self):
        result, _ = await _run_structured({
            "hot_fluid": "crude oil",
            "cold_fluid": "cooling water",
            "T_hot_in": 302.0,
            "T_hot_out": 194.0,
            "T_cold_in": 86.0,
            "m_dot_hot": 50.0,
            "temp_unit": "F",
        })
        assert result.validation_passed
        assert result.outputs["T_hot_in_C"] == pytest.approx(150.0)
        assert result.outputs["T_hot_out_C"] == pytest.approx(90.0)
        assert result.outputs["T_cold_in_C"] == pytest.approx(30.0)

    async def test_negative_flow_rate(self):
        result, _ = await _run_structured({
            "hot_fluid": "crude oil",
            "cold_fluid": "water",
            "T_hot_in": 150.0,
            "T_cold_in": 30.0,
            "m_dot_hot": -5.0,
        })
        assert not result.validation_passed

    async def test_zero_flow_rate(self):
        result, _ = await _run_structured({
            "hot_fluid": "crude oil",
            "cold_fluid": "water",
            "T_hot_in": 150.0,
            "T_cold_in": 30.0,
            "m_dot_hot": 0.0,
        })
        assert not result.validation_passed

    async def test_hot_gaining_heat_warning(self):
        result, _ = await _run_structured({
            "hot_fluid": "crude oil",
            "cold_fluid": "water",
            "T_hot_in": 50.0,
            "T_hot_out": 100.0,
            "T_cold_in": 30.0,
            "m_dot_hot": 50.0,
        })
        assert any("gaining heat" in w for w in result.warnings)

    async def test_cold_losing_heat_warning(self):
        result, _ = await _run_structured({
            "hot_fluid": "crude oil",
            "cold_fluid": "water",
            "T_hot_in": 150.0,
            "T_cold_in": 80.0,
            "T_cold_out": 30.0,
            "m_dot_hot": 50.0,
        })
        assert any("losing heat" in w for w in result.warnings)

    async def test_temperature_cross_warning(self):
        result, _ = await _run_structured({
            "hot_fluid": "crude oil",
            "cold_fluid": "water",
            "T_hot_in": 100.0,
            "T_hot_out": 80.0,
            "T_cold_in": 30.0,
            "T_cold_out": 120.0,
            "m_dot_hot": 50.0,
        })
        assert any("cross" in w.lower() for w in result.warnings)

    async def test_optional_pressure_default(self):
        result, _ = await _run_structured({
            "hot_fluid": "crude oil",
            "cold_fluid": "water",
            "T_hot_in": 150.0,
            "T_cold_in": 30.0,
            "m_dot_hot": 50.0,
        })
        assert result.outputs["P_hot_Pa"] == 101325.0

    async def test_optional_tema_class(self):
        result, _ = await _run_structured({
            "hot_fluid": "crude oil",
            "cold_fluid": "water",
            "T_hot_in": 150.0,
            "T_cold_in": 30.0,
            "m_dot_hot": 50.0,
            "tema_class": "R",
        })
        assert result.outputs["tema_class"] == "R"

    async def test_step_result_has_correct_step_id(self):
        result, _ = await _run_structured({
            "hot_fluid": "crude oil",
            "cold_fluid": "water",
            "T_hot_in": 150.0,
            "T_cold_in": 30.0,
            "m_dot_hot": 50.0,
        })
        assert result.step_id == 1
        assert result.step_name == "Process Requirements"
