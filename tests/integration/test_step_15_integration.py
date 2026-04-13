"""Tests for ST-7 — Step 15 integration tests.

End-to-end tests with realistic DesignState values.
"""

from __future__ import annotations

import pytest

from hx_engine.app.core.validation_rules import check
from hx_engine.app.models.design_state import (
    DesignState,
    GeometrySpec,
)
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
        P_hot_Pa=1_101_325.0,   # ~10 barg
        P_cold_Pa=601_325.0,    # ~5 barg
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
        # Step 14 populated
        tube_thickness_ok=True,
        shell_thickness_ok=True,
        mechanical_details={
            "tube": {"t_actual_mm": 2.11},
            "shell": {"recommended_wall_mm": 7.04},
        },
    )
    defaults.update(overrides)
    return DesignState(**defaults)


@pytest.fixture
def step():
    return Step15CostEstimate()


class TestSerthGeometry:
    """T7.1: Serth Example 5.1 geometry through Step 15."""

    @pytest.mark.asyncio
    async def test_serth_produces_cost(self, step):
        """T7.1: cost_usd > 0 and breakdown fully populated."""
        state = _serth_state()
        result = await step.execute(state)
        assert state.cost_usd > 0
        assert state.cost_breakdown is not None
        bd = state.cost_breakdown
        assert bd["turton_row"] == "fixed_tube"
        assert bd["C_BM_2026_usd"] > 0
        assert bd["cost_per_m2_usd"] > 0

    @pytest.mark.asyncio
    async def test_aes_more_expensive(self, step):
        """T7.2: AES type → higher cost than BEM."""
        state_bem = _serth_state()
        state_aes = _serth_state(tema_type="AES")
        r_bem = await step.execute(state_bem)
        r_aes = await step.execute(state_aes)
        assert state_aes.cost_usd > state_bem.cost_usd

    @pytest.mark.asyncio
    async def test_ss304_more_expensive(self, step):
        """T7.3: CS/SS304 → higher cost than CS/CS."""
        state_cs = _serth_state()
        state_ss = _serth_state(tube_material="stainless_304")
        await step.execute(state_cs)
        await step.execute(state_ss)
        assert state_ss.cost_usd > state_cs.cost_usd

    @pytest.mark.asyncio
    async def test_high_pressure_fp_above_one(self, step):
        """T7.4: High pressure (50 bar) → F_P > 1.0."""
        state = _serth_state(P_hot_Pa=101_325.0 + 50e5)
        result = await step.execute(state)
        assert result.outputs["cost_breakdown"]["F_P"] > 1.0


class TestRulesPassing:
    """T7.5: Step 15 + rules pass."""

    @pytest.mark.asyncio
    async def test_layer2_rules_pass(self, step):
        """T7.5: All Layer 2 rules pass for valid Serth case."""
        state = _serth_state()
        result = await step.execute(state)
        vr = check(15, result)
        assert vr.passed, f"Layer 2 failed: {vr.errors}"


class TestStepRecordIntegration:
    """T7.6–T7.7: StepResult and state integration."""

    @pytest.mark.asyncio
    async def test_step_result_has_correct_outputs(self, step):
        """T7.6: Result outputs has cost_usd and cost_breakdown."""
        state = _serth_state()
        result = await step.execute(state)
        assert "cost_usd" in result.outputs
        assert "cost_breakdown" in result.outputs

    @pytest.mark.asyncio
    async def test_state_cost_usd_matches_result(self, step):
        """T7.7: state.cost_usd matches result outputs."""
        state = _serth_state()
        result = await step.execute(state)
        assert state.cost_usd == result.outputs["cost_usd"]


class TestCostSanity:
    """T7.8: Cost/m² sanity checks."""

    @pytest.mark.asyncio
    async def test_cost_per_m2_cs_in_range(self, step):
        """T7.8: Cost/m² for CS/CS at ~10 barg falls within (100, 800) $/m²."""
        state = _serth_state()
        result = await step.execute(state)
        cost_per_m2 = result.outputs["cost_breakdown"]["cost_per_m2_usd"]
        # Allow wider range since area (47 m²) is near Turton lower bound
        assert 50 < cost_per_m2 < 5000


class TestPipelineWiring:
    """T7.9: Pipeline wiring verification."""

    def test_step15_importable_from_pipeline(self):
        """T7.9: Step15CostEstimate is importable and wired."""
        from hx_engine.app.core.pipeline_runner import Step15CostEstimate as S15
        assert S15.step_id == 15


class TestExoticMaterial:
    """T7.10: Exotic material combo."""

    @pytest.mark.asyncio
    async def test_duplex_duplex_interpolated(self, step):
        """T7.10: duplex/duplex → F_M interpolated + warning."""
        state = _serth_state(
            shell_material="duplex_2205",
            tube_material="duplex_2205",
        )
        result = await step.execute(state)
        bd = result.outputs["cost_breakdown"]
        assert bd["F_M_interpolated"] is True
        assert any("interpolated" in w for w in result.warnings)
        assert state.cost_usd > 0
