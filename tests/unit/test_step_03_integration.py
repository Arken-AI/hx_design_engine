"""Tests for Piece 7: Full integration — all pieces wired together."""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hx_engine.app.core import validation_rules
from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import DesignState, FluidProperties
from hx_engine.app.models.step_result import (
    AIDecisionEnum,
    AIModeEnum,
    AIReview,
    StepResult,
)
from hx_engine.app.steps.base import StepProtocol
from hx_engine.app.steps.step_03_fluid_props import Step03FluidProperties
from hx_engine.app.steps.step_03_rules import register_step3_rules


# Mock water properties for tests needing water
_WATER_45 = FluidProperties(
    density_kg_m3=990.2, viscosity_Pa_s=5.96e-4,
    cp_J_kgK=4180.0, k_W_mK=0.637, Pr=3.91,
)

_WATER_100 = FluidProperties(
    density_kg_m3=971.0, viscosity_Pa_s=3.5e-4,
    cp_J_kgK=4195.0, k_W_mK=0.670, Pr=2.19,
)


def _make_benchmark_state() -> DesignState:
    """Crude oil 150→90°C + thermal oil 30→60°C (specialty fluids — no optional deps)."""
    return DesignState(
        hot_fluid_name="crude oil",
        cold_fluid_name="thermal oil",
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=60.0,
        m_dot_hot_kg_s=50.0,
        P_hot_Pa=101325.0,
        P_cold_Pa=101325.0,
    )


class TestIntegration:
    """Eight integration tests — all pieces wired together."""

    async def test_full_benchmark(self):
        """50 kg/s crude oil 150→90°C + ethanol 30→60°C — full pipeline.

        Both FluidProperties populated, validation passes.
        """
        step = Step03FluidProperties()
        state = _make_benchmark_state()
        result = await step.execute(state)

        hot = result.outputs["hot_fluid_props"]
        cold = result.outputs["cold_fluid_props"]

        for props in (hot, cold):
            for field in (
                "density_kg_m3", "viscosity_Pa_s", "cp_J_kgK", "k_W_mK", "Pr",
            ):
                val = getattr(props, field)
                assert val is not None and val > 0, f"{field} must be positive"

        assert result.validation_passed is True
        assert result.step_id == 3

    async def test_water_water_different_temps(self):
        """Water on both sides at different temps → two different FluidProperties."""

        async def _mock(fluid_name, T_mean_C, pressure_Pa=None):
            if T_mean_C > 80:
                return _WATER_100
            return _WATER_45

        state = DesignState(
            hot_fluid_name="water",
            cold_fluid_name="water",
            T_hot_in_C=120.0,
            T_hot_out_C=80.0,
            T_cold_in_C=30.0,
            T_cold_out_C=60.0,
        )
        step = Step03FluidProperties()
        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            side_effect=_mock,
        ):
            result = await step.execute(state)

        hot = result.outputs["hot_fluid_props"]
        cold = result.outputs["cold_fluid_props"]
        assert hot.density_kg_m3 != cold.density_kg_m3

    async def test_ethanol_ethylene_glycol(self):
        """Ethylene glycol 80→40°C + thermal oil 20→55°C — specialty fluid adapter paths."""
        state = DesignState(
            hot_fluid_name="ethylene glycol",
            cold_fluid_name="thermal oil",
            T_hot_in_C=80.0,
            T_hot_out_C=40.0,
            T_cold_in_C=20.0,
            T_cold_out_C=55.0,
        )
        step = Step03FluidProperties()
        result = await step.execute(state)

        hot = result.outputs["hot_fluid_props"]
        cold = result.outputs["cold_fluid_props"]
        assert hot.cp_J_kgK is not None and hot.cp_J_kgK > 0
        assert cold.cp_J_kgK is not None and cold.cp_J_kgK > 0

    async def test_step_result_round_trip(self):
        """Execute, serialize outputs to JSON, verify all fields serialize."""
        step = Step03FluidProperties()
        state = _make_benchmark_state()
        result = await step.execute(state)

        # StepResult is a Pydantic model — should serialize cleanly
        json_data = result.model_dump()
        assert "outputs" in json_data
        assert json_data["step_id"] == 3
        assert json_data["step_name"] == "Fluid Properties"

    async def test_immutability(self):
        """Execute does not mutate the original state."""
        step = Step03FluidProperties()
        state = _make_benchmark_state()

        assert state.hot_fluid_props is None
        assert state.cold_fluid_props is None

        await step.execute(state)

        # State must remain unmodified
        assert state.hot_fluid_props is None
        assert state.cold_fluid_props is None

    def test_step_protocol(self):
        """Step03FluidProperties satisfies StepProtocol structural typing."""
        step = Step03FluidProperties()
        assert isinstance(step, StepProtocol)
        assert step.step_id == 3
        assert step.step_name == "Fluid Properties"

    async def test_run_with_review_loop_proceed(self):
        """run_with_review_loop with AI stub returning PROCEED."""
        step = Step03FluidProperties()
        state = _make_benchmark_state()

        ai_engineer = AsyncMock()
        ai_engineer.review.return_value = AIReview(
            decision=AIDecisionEnum.PROCEED,
            confidence=0.9,
            reasoning="Properties look reasonable",
            ai_called=True,
        )

        # Force AI to be called by temporarily setting ai_mode to FULL
        step.ai_mode = AIModeEnum.FULL
        result = await step.run_with_review_loop(state, ai_engineer)

        assert result.step_id == 3
        assert result.ai_review is not None
        assert result.ai_review.decision == AIDecisionEnum.PROCEED
        assert result.outputs["hot_fluid_props"] is not None

    async def test_validation_rules_pass_on_real_output(self):
        """Step 3 output passes all registered Layer 2 validation rules."""
        step = Step03FluidProperties()
        state = _make_benchmark_state()
        result = await step.execute(state)

        vr = validation_rules.check(3, result)
        assert vr.passed is True, f"Validation errors: {vr.errors}"
