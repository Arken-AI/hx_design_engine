"""Tests for Piece 3: execute() — core Step 03 logic."""

from __future__ import annotations

import copy
from unittest.mock import patch

import pytest

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import DesignState, FluidProperties
from hx_engine.app.steps.step_03_fluid_props import Step03FluidProperties

# Mock water properties for tests where iapws/CoolProp not installed
_WATER_45 = FluidProperties(
    density_kg_m3=990.2,
    viscosity_Pa_s=5.96e-4,
    cp_J_kgK=4180.0,
    k_W_mK=0.637,
    Pr=3.91,
)


def _make_benchmark_state() -> DesignState:
    """Crude oil 150→90°C + ethanol 30→60°C — both resolve without mocks."""
    return DesignState(
        hot_fluid_name="crude oil",
        cold_fluid_name="ethanol",
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=60.0,
        m_dot_hot_kg_s=50.0,
        P_hot_Pa=101325.0,
        P_cold_Pa=101325.0,
    )


class TestExecute:
    """Eight tests guarding Step 03 execute() correctness."""

    async def test_benchmark_both_populated(self):
        """Crude oil + ethanol benchmark populates both FluidProperties."""
        step = Step03FluidProperties()
        state = _make_benchmark_state()
        result = await step.execute(state)

        hot = result.outputs["hot_fluid_props"]
        cold = result.outputs["cold_fluid_props"]

        # Both must have all 5 properties positive
        for props in (hot, cold):
            assert props.density_kg_m3 is not None and props.density_kg_m3 > 0
            assert props.viscosity_Pa_s is not None and props.viscosity_Pa_s > 0
            assert props.cp_J_kgK is not None and props.cp_J_kgK > 0
            assert props.k_W_mK is not None and props.k_W_mK > 0
            assert props.Pr is not None and props.Pr > 0

        assert result.validation_passed is True

    async def test_missing_hot_fluid_name_raises(self):
        """state.hot_fluid_name = None → CalculationError."""
        step = Step03FluidProperties()
        state = _make_benchmark_state()
        state.hot_fluid_name = None

        with pytest.raises(CalculationError, match="hot_fluid_name"):
            await step.execute(state)

    async def test_missing_cold_fluid_name_raises(self):
        """state.cold_fluid_name = None → CalculationError."""
        step = Step03FluidProperties()
        state = _make_benchmark_state()
        state.cold_fluid_name = None

        with pytest.raises(CalculationError, match="cold_fluid_name"):
            await step.execute(state)

    async def test_missing_temperatures_raises(self):
        """state.T_hot_in_C = None → CalculationError."""
        step = Step03FluidProperties()
        state = _make_benchmark_state()
        state.T_hot_in_C = None

        with pytest.raises(CalculationError, match="T_hot_in_C"):
            await step.execute(state)

    async def test_outputs_dict_keys(self):
        """Result outputs contain the expected keys matching DesignState fields."""
        step = Step03FluidProperties()
        state = _make_benchmark_state()
        result = await step.execute(state)

        assert "hot_fluid_props" in result.outputs
        assert "cold_fluid_props" in result.outputs
        assert "T_mean_hot_C" in result.outputs
        assert "T_mean_cold_C" in result.outputs
        assert result.outputs["T_mean_hot_C"] == pytest.approx(120.0)
        assert result.outputs["T_mean_cold_C"] == pytest.approx(45.0)

    async def test_step_result_metadata(self):
        """StepResult carries correct step_id and step_name."""
        step = Step03FluidProperties()
        state = _make_benchmark_state()
        result = await step.execute(state)

        assert result.step_id == 3
        assert result.step_name == "Fluid Properties"

    async def test_state_is_not_mutated(self):
        """execute() is pure — Layer 1 must not mutate the input state."""
        step = Step03FluidProperties()
        state = _make_benchmark_state()
        state_before = copy.deepcopy(state)

        await step.execute(state)

        # State fields should be unchanged
        assert state.hot_fluid_props is None
        assert state.cold_fluid_props is None
        assert state.T_hot_in_C == state_before.T_hot_in_C
        assert state.T_cold_out_C == state_before.T_cold_out_C

    async def test_both_fluids_same_different_temps(self):
        """Water–water at different temperatures → two different FluidProperties.

        Properties are temperature-dependent: Pr(30°C) ≠ Pr(90°C).
        """
        water_cold = FluidProperties(
            density_kg_m3=995.0, viscosity_Pa_s=8.0e-4,
            cp_J_kgK=4179.0, k_W_mK=0.615, Pr=5.43,
        )
        water_hot = FluidProperties(
            density_kg_m3=971.0, viscosity_Pa_s=3.5e-4,
            cp_J_kgK=4195.0, k_W_mK=0.670, Pr=2.19,
        )

        call_count = 0

        def _side_effect(fluid_name, T_mean_C, pressure_Pa=None):
            nonlocal call_count
            call_count += 1
            if T_mean_C > 80:
                return water_hot
            return water_cold

        state = DesignState(
            hot_fluid_name="water",
            cold_fluid_name="water",
            T_hot_in_C=120.0,
            T_hot_out_C=80.0,
            T_cold_in_C=20.0,
            T_cold_out_C=50.0,
        )

        step = Step03FluidProperties()
        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            side_effect=_side_effect,
        ):
            result = await step.execute(state)

        hot = result.outputs["hot_fluid_props"]
        cold = result.outputs["cold_fluid_props"]

        # Properties should differ (different mean temperatures)
        assert hot.Pr != cold.Pr
