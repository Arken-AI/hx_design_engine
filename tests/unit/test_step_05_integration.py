"""Tests for Piece 5 — Step 5 integration with pipeline state.

These tests verify Step 5 produces consistent results using realistic
pre-populated states, and that all physics invariants hold.
"""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.steps.step_05_lmtd import Step05LMTD


def _make_full_state() -> DesignState:
    """Build a fully-populated state as if Steps 1–4 had run.

    Benchmark: 50 kg/s crude oil 150→90°C, water 30→55°C
    """
    return DesignState(
        raw_request=(
            "Design a heat exchanger for cooling 50 kg/s of crude oil "
            "from 150°C to 90°C using cooling water at 30°C"
        ),
        hot_fluid_name="crude oil",
        cold_fluid_name="cooling water",
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=55.0,
        m_dot_hot_kg_s=50.0,
        m_dot_cold_kg_s=57.4,
        P_hot_Pa=101325.0,
        P_cold_Pa=101325.0,
        Q_W=6_000_000.0,
        hot_fluid_props=FluidProperties(
            density_kg_m3=830.0, viscosity_Pa_s=0.004,
            cp_J_kgK=2000.0, k_W_mK=0.13, Pr=61.5,
        ),
        cold_fluid_props=FluidProperties(
            density_kg_m3=993.0, viscosity_Pa_s=7.97e-4,
            cp_J_kgK=4180.0, k_W_mK=0.617, Pr=5.4,
        ),
        geometry=GeometrySpec(
            tube_od_m=0.01905,
            tube_id_m=0.01483,
            tube_length_m=4.88,
            pitch_ratio=1.25,
            pitch_layout="triangular",
            shell_diameter_m=0.489,
            baffle_cut=0.25,
            baffle_spacing_m=0.15,
            n_tubes=158,
            n_passes=2,
            shell_passes=1,
        ),
        tema_type="AES",
        shell_side_fluid="cold",
        current_step=4,
        completed_steps=[1, 2, 3, 4],
    )


@pytest.fixture
def step():
    return Step05LMTD()


class TestStep05Integration:

    @pytest.mark.asyncio
    async def test_pipeline_1_through_5_benchmark_completes(self, step):
        """All 5 steps' output should be present — Step 5 runs without exception."""
        state = _make_full_state()
        result = await step.execute(state)

        # All key outputs present
        for key in ("LMTD_K", "F_factor", "effective_LMTD"):
            assert key in result.outputs, f"Missing output: {key}"

        # Extended physics checks
        assert state.LMTD_K > 0
        assert 0 < state.F_factor <= 1.0
        assert state.Q_W > 0
        assert state.hot_fluid_props is not None
        assert state.cold_fluid_props is not None
        assert state.geometry is not None
        assert state.tema_type in {"BEM", "AES", "AEP", "AEU", "AEW"}

    @pytest.mark.asyncio
    async def test_pipeline_all_thermal_fields_populated(self, step):
        """Q_W, LMTD_K, F_factor all set after Step 5."""
        state = _make_full_state()
        await step.execute(state)

        assert state.Q_W is not None
        assert state.LMTD_K is not None
        assert state.F_factor is not None

    @pytest.mark.asyncio
    async def test_pipeline_lmtd_between_delta_ts(self, step):
        """LMTD is between min(ΔT₁, ΔT₂) and max(ΔT₁, ΔT₂)."""
        state = _make_full_state()
        result = await step.execute(state)

        dT1 = state.T_hot_in_C - state.T_cold_out_C   # 150 - 55 = 95
        dT2 = state.T_hot_out_C - state.T_cold_in_C    # 90 - 30 = 60
        LMTD = result.outputs["LMTD_K"]

        assert min(dT1, dT2) <= LMTD <= max(dT1, dT2)

    @pytest.mark.asyncio
    async def test_pipeline_effective_lmtd_le_lmtd(self, step):
        """F × LMTD ≤ LMTD because F ≤ 1.0."""
        state = _make_full_state()
        result = await step.execute(state)

        eff = result.outputs["effective_LMTD"]
        lmtd = result.outputs["LMTD_K"]
        assert eff <= lmtd + 1e-10

    @pytest.mark.asyncio
    async def test_pipeline_no_regression_steps_1_4(self, step):
        """Step 5 doesn't mutate anything from Steps 1–4."""
        state = _make_full_state()
        orig_Q = state.Q_W
        orig_temps = (
            state.T_hot_in_C, state.T_hot_out_C,
            state.T_cold_in_C, state.T_cold_out_C,
        )
        orig_hot_fluid = state.hot_fluid_name
        orig_cold_fluid = state.cold_fluid_name
        orig_tema = state.tema_type
        orig_tube_od = state.geometry.tube_od_m
        orig_n_tubes = state.geometry.n_tubes

        await step.execute(state)

        assert state.Q_W == orig_Q
        assert (
            state.T_hot_in_C, state.T_hot_out_C,
            state.T_cold_in_C, state.T_cold_out_C,
        ) == orig_temps
        assert state.hot_fluid_name == orig_hot_fluid
        assert state.cold_fluid_name == orig_cold_fluid
        assert state.tema_type == orig_tema
        assert state.geometry.tube_od_m == orig_tube_od
        assert state.geometry.n_tubes == orig_n_tubes

    @pytest.mark.asyncio
    async def test_pipeline_effective_lmtd_equals_f_times_lmtd(self, step):
        """effective_LMTD = F_factor × LMTD_K exactly."""
        state = _make_full_state()
        result = await step.execute(state)

        expected = result.outputs["F_factor"] * result.outputs["LMTD_K"]
        assert result.outputs["effective_LMTD"] == pytest.approx(expected, rel=1e-10)
