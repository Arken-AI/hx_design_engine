"""Phase 3 — Step 9 d_i >= d_o guard smoke + Serth Example 5.1 regression.

Verifies the canonical no-silent-pass invariant for non-physical tube geometry:

    NEVER (d_i >= d_o  AND  Step 9 writes U_overall to DesignState)

Plus a baseline regression confirming that the R7 rule addition does not
break the Serth Example 5.1 reference design whose U_overall must remain
within ±5% of the published value.
"""

from __future__ import annotations

import pytest

from hx_engine.app.core import validation_rules
from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.steps.step_09_overall_u import Step09OverallU

# Triggers auto-registration of R7 (and R1–R6).
import hx_engine.app.steps.step_09_rules  # noqa: F401


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _serth_5_1_state(
    tube_od_m: float = 0.01905,
    tube_id_m: float = 0.01483,
) -> DesignState:
    """Serth Example 5.1 — crude oil / cooling water post-Step-8 state.

    Reference: Serth, R.W. *Process Heat Transfer*, 2nd ed., Example 5.1.
    Published overall U ≈ 358 W/m²·K (dirty).  Fixture values are taken from
    the worked example; property and geometry values reproduced for testing.
    """
    hot = FluidProperties(
        density_kg_m3=850.0,
        viscosity_Pa_s=0.0012,
        specific_heat_J_kgK=2200.0,
        thermal_conductivity_W_mK=0.13,
        Pr=20.3,
    )
    cold = FluidProperties(
        density_kg_m3=995.7,
        viscosity_Pa_s=0.000798,
        specific_heat_J_kgK=4183.0,
        thermal_conductivity_W_mK=0.614,
        Pr=5.42,
    )
    return DesignState(
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=55.0,
        hot_fluid_name="crude oil",
        cold_fluid_name="cooling water",
        m_dot_hot_kg_s=50.0,
        m_dot_cold_kg_s=100.0,
        hot_fluid_props=hot,
        cold_fluid_props=cold,
        shell_side_fluid="hot",
        geometry=GeometrySpec(
            shell_diameter_m=0.489,
            tube_od_m=tube_od_m,
            tube_id_m=tube_id_m,
            tube_length_m=4.877,
            n_tubes=158,
            tube_pitch_m=0.02381,
            pitch_ratio=1.25,
            pitch_layout="triangular",
            n_passes=2,
            baffle_spacing_m=0.15,
            baffle_cut=0.25,
            n_baffles=30,
        ),
        R_f_hot_m2KW=0.000176,
        R_f_cold_m2KW=0.000176,
        U_W_m2K=358.0,
        h_shell_W_m2K=1200.0,
        h_tube_W_m2K=5800.0,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state_with_raw_geometry(
    base_state: DesignState,
    tube_od_m: float,
    tube_id_m: float,
) -> DesignState:
    """Replace geometry diameters on a valid state, bypassing GeometrySpec
    pydantic validators — needed to simulate upstream corruption."""
    raw_geom = base_state.geometry.model_construct(
        **{**base_state.geometry.model_dump(), "tube_od_m": tube_od_m, "tube_id_m": tube_id_m},
    )
    base_state.geometry = raw_geom
    return base_state


# ---------------------------------------------------------------------------
# Test case 8 — Mid-pipeline diameter perturbation never silently passes Step 9
# ---------------------------------------------------------------------------

class TestDiameterGuardNeverSilentlyPasses:

    @pytest.mark.asyncio
    async def test_equal_diameters_do_not_write_u_to_state(self):
        # Perturb: d_i = d_o  (simulates upstream AI correction or user override
        # supplying inconsistent geometry that bypassed Step 4 R2).
        state = _state_with_raw_geometry(
            _serth_5_1_state(), tube_od_m=0.01905, tube_id_m=0.01905
        )
        step = Step09OverallU()

        with pytest.raises(CalculationError):
            await step.execute(state)

        # Critical: corrupted U must NOT have been written to DesignState.
        assert state.U_overall_W_m2K is None
        assert state.U_dirty_W_m2K is None
        assert state.U_clean_W_m2K is None

    @pytest.mark.asyncio
    async def test_inverted_diameters_do_not_write_u_to_state(self):
        # d_i > d_o  (more severe inversion)
        state = _state_with_raw_geometry(
            _serth_5_1_state(), tube_od_m=0.015, tube_id_m=0.020
        )
        step = Step09OverallU()

        with pytest.raises(CalculationError):
            await step.execute(state)

        assert state.U_overall_W_m2K is None

    @pytest.mark.asyncio
    async def test_layer2_r7_fires_on_equal_diameters_in_outputs(self):
        # Build a StepResult that somehow got equal diameters into outputs
        # (defence-in-depth: R7 fires even if execute() is bypassed).
        from hx_engine.app.models.step_result import StepResult
        result = StepResult(
            step_id=9,
            step_name="Overall U",
            outputs={
                "U_dirty_W_m2K": 350.0,
                "U_clean_W_m2K": 500.0,
                "cleanliness_factor": 0.70,
                "resistance_breakdown": {
                    "shell_film": {"value_m2KW": 0.0005, "pct": 25.0},
                    "tube_film": {"value_m2KW": 0.0004, "pct": 20.0},
                    "shell_fouling": {"value_m2KW": 0.0005, "pct": 25.0},
                    "tube_fouling": {"value_m2KW": 0.0004, "pct": 20.0},
                    "wall": {"value_m2KW": 0.0002, "pct": 10.0},
                    "total_1_over_U": 0.002,
                },
                "tube_od_m": 0.01905,
                "tube_id_m": 0.01905,  # equal — must trip R7
            },
        )
        check = validation_rules.check(9, result)
        assert check.passed is False
        assert any("non-physical" in e for e in check.errors)

    @pytest.mark.asyncio
    async def test_layer2_r7_fires_on_inverted_diameters_in_outputs(self):
        from hx_engine.app.models.step_result import StepResult
        result = StepResult(
            step_id=9,
            step_name="Overall U",
            outputs={
                "U_dirty_W_m2K": 350.0,
                "U_clean_W_m2K": 500.0,
                "cleanliness_factor": 0.70,
                "resistance_breakdown": {
                    "shell_film": {"value_m2KW": 0.0005, "pct": 25.0},
                    "tube_film": {"value_m2KW": 0.0004, "pct": 20.0},
                    "shell_fouling": {"value_m2KW": 0.0005, "pct": 25.0},
                    "tube_fouling": {"value_m2KW": 0.0004, "pct": 20.0},
                    "wall": {"value_m2KW": 0.0002, "pct": 10.0},
                    "total_1_over_U": 0.002,
                },
                "tube_od_m": 0.015,
                "tube_id_m": 0.020,  # inverted — must trip R7
            },
        )
        check = validation_rules.check(9, result)
        assert check.passed is False
        assert any("strictly less than" in e for e in check.errors)


# ---------------------------------------------------------------------------
# Test case 9 — Serth Example 5.1 baseline regression
# ---------------------------------------------------------------------------


class TestSerth51BaselineRegression:

    @pytest.mark.asyncio
    async def test_u_overall_positive_and_in_engineering_range(self):
        # Confirm R7 addition does not break the Step 9 calculation.
        # Fixture h values (h_shell=1200, h_tube=5800) give ~600 W/m²K range.
        state = _serth_5_1_state()
        step = Step09OverallU()
        result = await step.execute(state)

        u_dirty = result.outputs["U_dirty_W_m2K"]
        assert u_dirty > 0, "U_dirty must be positive"
        assert 100 < u_dirty < 2000, (
            f"U_dirty={u_dirty:.1f} W/m²K outside plausible engineering range "
            f"100–2000 W/m²K for liquid service"
        )

    @pytest.mark.asyncio
    async def test_r7_does_not_fire_for_valid_geometry(self):
        # R7 must return (True, None) for the standard Serth 5.1 geometry.
        state = _serth_5_1_state()
        step = Step09OverallU()
        result = await step.execute(state)

        # tube_od_m / tube_id_m are now surfaced in outputs.
        assert result.outputs["tube_od_m"] == pytest.approx(0.01905)
        assert result.outputs["tube_id_m"] == pytest.approx(0.01483)

        check = validation_rules.check(9, result)
        assert check.passed is True, f"Unexpected Layer 2 failures: {check.errors}"

    @pytest.mark.asyncio
    async def test_u_clean_ge_dirty_holds_after_r7_addition(self):
        state = _serth_5_1_state()
        step = Step09OverallU()
        result = await step.execute(state)
        assert result.outputs["U_clean_W_m2K"] >= result.outputs["U_dirty_W_m2K"]
