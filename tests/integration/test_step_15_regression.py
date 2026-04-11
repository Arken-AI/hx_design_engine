"""Tests for ST-8 — Step 15 regression / backward compatibility.

Ensures Step 15 additions don't break existing functionality.
"""

from __future__ import annotations

import pytest

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import DesignState, GeometrySpec
from hx_engine.app.steps.step_15_cost import Step15CostEstimate


def _serth_state(**overrides) -> DesignState:
    """Serth Example 5.1–like geometry through Step 14."""
    defaults = dict(
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=55.0,
        T_mean_hot_C=120.0,
        T_mean_cold_C=42.5,
        P_hot_Pa=1_101_325.0,
        P_cold_Pa=601_325.0,
        shell_side_fluid="hot",
        tema_type="BEM",
        tube_material="carbon_steel",
        shell_material="sa516_gr70",
        convergence_converged=True,
        area_provided_m2=47.0,
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
        tube_thickness_ok=True,
        shell_thickness_ok=True,
        mechanical_details={
            "tube": {"t_actual_mm": 2.11},
            "shell": {"recommended_wall_mm": 7.04},
        },
    )
    defaults.update(overrides)
    return DesignState(**defaults)


class TestExistingStepsUnbroken:
    """T8.1 / T8.6: Existing Step 14 still works after Step 15 additions."""

    @pytest.mark.asyncio
    async def test_step_14_still_runs(self):
        """T8.1: Step 14 executes without regression."""
        from hx_engine.app.steps.step_14_mechanical import Step14MechanicalCheck

        state = _serth_state()
        step14 = Step14MechanicalCheck()
        result = await step14.execute(state)
        assert state.tube_thickness_ok is not None
        assert state.shell_thickness_ok is not None

    def test_pipeline_imports_all_steps(self):
        """T8.6: Pipeline runner imports without errors."""
        from hx_engine.app.core.pipeline_runner import PipelineRunner
        assert PipelineRunner is not None


class TestDesignStateSerialization:
    """T8.2: DesignState serialization with new cost fields."""

    def test_json_roundtrip_with_cost(self):
        """T8.2: Serialize + deserialize with cost fields."""
        state = _serth_state()
        state.cost_usd = 168_000.50
        state.cost_breakdown = {
            "area_m2": 47.0,
            "turton_row": "fixed_tube",
            "F_M": 1.0,
            "F_P": 1.0,
            "C_BM_2026_usd": 168_000.50,
        }
        json_str = state.model_dump_json()
        restored = DesignState.model_validate_json(json_str)

        assert restored.cost_usd == pytest.approx(168_000.50)
        assert restored.cost_breakdown["turton_row"] == "fixed_tube"
        # Original fields still intact
        assert restored.T_hot_in_C == 150.0
        assert restored.tema_type == "BEM"
        assert restored.tube_thickness_ok is True


class TestGracefulFailures:
    """T8.3–T8.5: Graceful error handling."""

    @pytest.mark.asyncio
    async def test_missing_area_raises_calculation_error(self):
        """T8.3: Missing area → CalculationError (not crash)."""
        state = _serth_state(area_provided_m2=None)
        step = Step15CostEstimate()
        with pytest.raises(CalculationError, match="area_provided_m2"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_tema_raises_calculation_error(self):
        """T8.4: Missing tema_type → CalculationError (not crash)."""
        state = _serth_state(tema_type=None)
        step = Step15CostEstimate()
        with pytest.raises(CalculationError, match="tema_type"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_none_pressures_graceful(self):
        """T8.5: None pressures → graceful fallback to atmospheric."""
        state = _serth_state(P_hot_Pa=None, P_cold_Pa=None)
        step = Step15CostEstimate()
        result = await step.execute(state)
        assert result.outputs["cost_usd"] > 0
        assert result.outputs["cost_breakdown"]["F_P"] == pytest.approx(1.0)
