"""Tests for Piece 8: Step 1 natural-language parser."""

import pytest

from hx_engine.app.models.design_state import DesignState
from hx_engine.app.steps.step_01_requirements import Step01Requirements


async def _run_nl(text: str):
    state = DesignState(raw_request=text)
    step = Step01Requirements()
    return await step.execute(state), state


class TestNLParser:

    async def test_standard_request(self):
        result, _ = await _run_nl(
            "Design a heat exchanger for cooling 50 kg/s of crude oil "
            "from 150°C to 90°C using cooling water at 30°C"
        )
        assert result.validation_passed
        o = result.outputs
        assert o["hot_fluid_name"] == "crude oil"
        assert o["cold_fluid_name"] == "cooling water"
        assert o["T_hot_in_C"] == pytest.approx(150.0)
        assert o["T_hot_out_C"] == pytest.approx(90.0)
        assert o["T_cold_in_C"] == pytest.approx(30.0)
        assert o["m_dot_hot_kg_s"] == pytest.approx(50.0)

    async def test_fahrenheit_temps(self):
        result, _ = await _run_nl(
            "Cool 100 lb/hr of crude oil from 302°F to 194°F "
            "with cooling water entering at 86°F"
        )
        assert result.validation_passed
        o = result.outputs
        assert o["T_hot_in_C"] == pytest.approx(150.0, abs=1.0)
        assert o["T_hot_out_C"] == pytest.approx(90.0, abs=1.0)
        assert o["T_cold_in_C"] == pytest.approx(30.0, abs=1.0)

    async def test_4_temps_given(self):
        result, _ = await _run_nl(
            "Heat water from 20°C to 60°C using steam at 120°C "
            "leaving at 100°C flow rate 10 kg/s"
        )
        assert result.validation_passed
        o = result.outputs
        assert o.get("T_hot_in_C") is not None
        assert o.get("T_cold_in_C") is not None

    async def test_ambiguous_oil(self):
        result, _ = await _run_nl(
            "Cool 50 kg/s of oil from 150°C to 90°C with water at 30°C"
        )
        assert not result.validation_passed
        assert any("ambiguous" in e.lower() for e in result.validation_errors)

    async def test_missing_flow_rate(self):
        result, _ = await _run_nl(
            "Cool crude oil from 150°C to 90°C with cooling water at 30°C"
        )
        assert not result.validation_passed
        assert any("flow rate" in e.lower() for e in result.validation_errors)

    async def test_missing_temps(self):
        result, _ = await _run_nl(
            "Design a heat exchanger for crude oil and cooling water"
        )
        assert not result.validation_passed
        assert any("temperature" in e.lower() for e in result.validation_errors)

    async def test_mixed_units(self):
        result, _ = await _run_nl(
            "Cool 50 kg/s crude oil from 302°F to 194°F "
            "using cooling water at 30°C"
        )
        assert result.validation_passed
        o = result.outputs
        # Hot side temps converted from F
        assert o["T_hot_in_C"] == pytest.approx(150.0, abs=1.0)
        assert o["T_cold_in_C"] == pytest.approx(30.0, abs=1.0)

    async def test_kelvin_temps(self):
        result, _ = await _run_nl(
            "Heat 10 kg/s of water from 293K to 333K using steam at 393K"
        )
        assert result.validation_passed
        # 293K = 19.85°C, 333K = 59.85°C
        assert result.outputs.get("T_cold_in_C") is not None

    async def test_with_pressure(self):
        result, _ = await _run_nl(
            "Cool 50 kg/s of crude oil from 150°C to 90°C "
            "using cooling water at 30°C at 5 bar operating pressure"
        )
        assert result.outputs["P_hot_Pa"] == pytest.approx(500000.0)

    async def test_with_tema_preference(self):
        result, _ = await _run_nl(
            "Cool 50 kg/s of crude oil from 150°C to 90°C "
            "using cooling water at 30°C prefer floating head design"
        )
        assert "floating head" in result.outputs.get("tema_preference", "")

    async def test_heating_not_cooling(self):
        result, _ = await _run_nl(
            "Heat 10 kg/s of water from 20°C to 80°C using steam at 150°C"
        )
        assert result.validation_passed
        # Water is cold side, steam is hot side
        o = result.outputs
        assert o.get("T_hot_in_C") is not None

    async def test_empty_request(self):
        result, _ = await _run_nl("")
        assert not result.validation_passed

    async def test_nonsense_request(self):
        result, _ = await _run_nl("What is the weather today?")
        assert not result.validation_passed
