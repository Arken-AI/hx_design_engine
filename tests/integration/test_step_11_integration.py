"""Integration tests for Step 11 — Area and Overdesign.

End-to-end tests with a realistic Serth Example 5.1–like DesignState
pre-populated through Step 10. Verifies that Step11AreaOverdesign correctly
computes area, overdesign %, and writes to state.
"""

from __future__ import annotations

import math

import pytest

from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_11_area_overdesign import Step11AreaOverdesign


# ---------------------------------------------------------------------------
# Serth-style state through Step 10
# ---------------------------------------------------------------------------

def _serth_state(**overrides) -> DesignState:
    """Serth Example 5.1–like geometry pre-populated through Step 10.

    Geometry: 158 tubes, 3/4 in. OD, 4.877 m long → A_provided ≈ 46.11 m²
    Thermal: Q=650 kW, U_dirty=280 W/m²K, F=0.90, LMTD=64 K
    → A_required ≈ 40.3 m²  → overdesign ≈ 14.4%  (in 8–25% standard band)
    """
    defaults = dict(
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=55.0,
        T_mean_hot_C=120.0,
        T_mean_cold_C=42.5,
        shell_side_fluid="hot",
        hot_fluid_name="crude oil",
        cold_fluid_name="water",
        # Step 2 outputs
        Q_W=650_000.0,
        m_dot_hot_kg_s=2.6,
        m_dot_cold_kg_s=6.2,
        # Step 5 outputs
        LMTD_K=64.0,
        F_factor=0.90,
        A_m2=42.0,            # Step 6 preliminary area estimate
        # Step 9 output
        U_dirty_W_m2K=280.0,
        U_W_m2K=310.0,
        # Step 10 outputs
        dP_tube_Pa=35_000.0,
        dP_shell_Pa=55_000.0,
        tube_velocity_m_s=1.5,
        # Fluid properties (Step 3)
        hot_fluid_props=FluidProperties(
            density_kg_m3=850.0,
            viscosity_Pa_s=0.001,
            cp_J_kgK=2100.0,
            k_W_mK=0.13,
            Pr=16.1,
        ),
        cold_fluid_props=FluidProperties(
            density_kg_m3=995.0,
            viscosity_Pa_s=0.0008,
            cp_J_kgK=4180.0,
            k_W_mK=0.62,
            Pr=5.4,
        ),
        # Geometry (Step 4/6)
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
    )
    defaults.update(overrides)
    return DesignState(**defaults)


@pytest.fixture
def step():
    return Step11AreaOverdesign()


# ---------------------------------------------------------------------------
# T11.1 — Happy path
# ---------------------------------------------------------------------------

class TestSerthHappyPath:
    """T11.1 — Serth state yields overdesign in the standard_process band."""

    @pytest.mark.asyncio
    async def test_execute_returns_step_result(self, step):
        state = _serth_state()
        result = await step.execute(state)
        assert isinstance(result, StepResult)
        assert result.step_id == 11

    @pytest.mark.asyncio
    async def test_overdesign_in_standard_process_band(self, step):
        """A_provided ≈ 46.1 m², A_required ≈ 40.3 m² → overdesign ≈ 14.4%."""
        state = _serth_state()
        await step.execute(state)
        assert state.overdesign_pct is not None
        assert 8.0 <= state.overdesign_pct <= 25.0, (
            f"Expected overdesign in 8–25% band, got {state.overdesign_pct:.1f}%"
        )

    @pytest.mark.asyncio
    async def test_area_fields_populated(self, step):
        """State gets area_required_m2, area_provided_m2, overdesign_pct."""
        state = _serth_state()
        await step.execute(state)
        assert state.area_required_m2 is not None
        assert state.area_provided_m2 is not None
        assert state.overdesign_pct is not None

    @pytest.mark.asyncio
    async def test_area_arithmetic_consistent(self, step):
        """Overdesign = (A_provided - A_required) / A_required * 100."""
        state = _serth_state()
        await step.execute(state)
        expected_od = (
            (state.area_provided_m2 - state.area_required_m2)
            / state.area_required_m2 * 100.0
        )
        assert abs(state.overdesign_pct - expected_od) < 1e-6

    @pytest.mark.asyncio
    async def test_a_provided_matches_geometry(self, step):
        """A_provided = π × d_o × L × N_t."""
        state = _serth_state()
        g = state.geometry
        expected_A = math.pi * g.tube_od_m * g.tube_length_m * g.n_tubes
        await step.execute(state)
        assert abs(state.area_provided_m2 - expected_A) < 1e-3

    @pytest.mark.asyncio
    async def test_service_classification_set(self, step):
        state = _serth_state()
        await step.execute(state)
        assert state.service_classification is not None


# ---------------------------------------------------------------------------
# T11.2 — Output dict matches state
# ---------------------------------------------------------------------------

class TestOutputDict:
    """T11.2 — StepResult.outputs mirrors state mutations."""

    @pytest.mark.asyncio
    async def test_output_keys_present(self, step):
        state = _serth_state()
        result = await step.execute(state)
        for key in ("area_required_m2", "area_provided_m2", "overdesign_pct"):
            assert key in result.outputs, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_output_values_match_state(self, step):
        state = _serth_state()
        result = await step.execute(state)
        assert result.outputs["area_required_m2"] == pytest.approx(state.area_required_m2)
        assert result.outputs["area_provided_m2"] == pytest.approx(state.area_provided_m2)
        assert result.outputs["overdesign_pct"] == pytest.approx(state.overdesign_pct)
