"""Tests for Step06InitialU._conditional_ai_trigger and _should_call_ai."""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import (
    DesignState,
    GeometrySpec,
)
from hx_engine.app.steps.step_06_initial_u import Step06InitialU


def _make_geometry(**overrides) -> GeometrySpec:
    defaults = dict(
        tube_od_m=0.01905,
        tube_id_m=0.01483,
        tube_length_m=4.88,
        pitch_ratio=1.25,
        pitch_layout="triangular",
        n_passes=2,
        shell_passes=1,
        baffle_cut=0.25,
        baffle_spacing_m=0.15,
        shell_diameter_m=0.489,
        n_tubes=158,
    )
    defaults.update(overrides)
    return GeometrySpec(**defaults)


def _make_state(**kwargs) -> DesignState:
    defaults = dict(
        hot_fluid_name="water",
        cold_fluid_name="water",
        Q_W=1_000_000.0,
        LMTD_K=30.0,
        F_factor=0.9,
        geometry=_make_geometry(),
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=55.0,
    )
    defaults.update(kwargs)
    return DesignState(**defaults)


@pytest.fixture
def step():
    return Step06InitialU()


class TestStep06ConditionalTrigger:

    @pytest.mark.asyncio
    async def test_normal_fluid_pair_no_trigger(self, step):
        """Normal water/water pair, normal area → trigger returns False."""
        state = _make_state()
        await step.execute(state)
        assert step._conditional_ai_trigger(state) is False

    @pytest.mark.asyncio
    async def test_unknown_fluid_triggers(self, step):
        """Unknown fluid pair (fallback U) → trigger returns True."""
        state = _make_state(
            hot_fluid_name="exotic_fluid_xyz",
            cold_fluid_name="unknown_coolant",
        )
        await step.execute(state)
        assert step._conditional_ai_trigger(state) is True

    @pytest.mark.asyncio
    async def test_large_area_triggers(self, step):
        """Required area > 200 m² → trigger returns True."""
        # Gas/gas has low U → large area
        state = _make_state(
            hot_fluid_name="air",
            cold_fluid_name="nitrogen",
            Q_W=500_000.0,  # 500 kW with gas/gas U=25 → huge area
        )
        await step.execute(state)
        assert step._A_required > 200
        assert step._conditional_ai_trigger(state) is True

    @pytest.mark.asyncio
    async def test_small_area_triggers(self, step):
        """Required area < 1 m² → trigger returns True."""
        state = _make_state(
            hot_fluid_name="steam",
            cold_fluid_name="water",
            Q_W=10_000.0,  # 10 kW with steam/water U=2500 → tiny area
            LMTD_K=50.0,
            F_factor=1.0,
        )
        await step.execute(state)
        assert step._A_required < 1
        assert step._conditional_ai_trigger(state) is True

    @pytest.mark.asyncio
    async def test_in_convergence_loop_no_ai(self, step):
        """in_convergence_loop = True → _should_call_ai returns False."""
        state = _make_state(in_convergence_loop=True)
        await step.execute(state)
        assert step._should_call_ai(state) is False
