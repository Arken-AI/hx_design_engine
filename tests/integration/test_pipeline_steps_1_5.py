"""Integration test: Steps 1–5 run sequentially with stubbed AI (always PROCEED).

Verifies that the five steps chain correctly — each step can read the state
written by the previous step — and that all key DesignState fields are
populated by the time the pipeline completes.
"""

from __future__ import annotations

import pytest

from hx_engine.app.core.ai_engineer import AIEngineer
from hx_engine.app.models.design_state import DesignState, FluidProperties, GeometrySpec
from hx_engine.app.steps.step_01_requirements import Step01Requirements
from hx_engine.app.steps.step_02_heat_duty import Step02HeatDuty
from hx_engine.app.steps.step_03_fluid_props import Step03FluidProperties
from hx_engine.app.steps.step_04_tema_geometry import Step04TEMAGeometry
from hx_engine.app.steps.step_05_lmtd import Step05LMTD

# Importing rule modules triggers auto-registration at module level
import hx_engine.app.steps.step_01_rules  # noqa: F401
import hx_engine.app.steps.step_03_rules  # noqa: F401
import hx_engine.app.steps.step_04_rules  # noqa: F401
import hx_engine.app.steps.step_05_rules  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

STUB_AI = AIEngineer(stub_mode=True)

# A fully-specified crude oil / cooling water design request used across all tests.
# Four temperatures + hot flow rate supplied so the energy balance is determined
# (Step 2 can compute Q from the hot side; T_cold_out is explicitly stated so
# Step 3 can compute mean temperatures for property lookups).
CRUDE_OIL_REQUEST = (
    "Design a heat exchanger to cool 10 kg/s of crude oil from 150°C to 80°C "
    "using cooling water entering at 25°C and leaving at 45°C. "
    "Operating pressure 5 bar."
)


def _make_state(raw_request: str = CRUDE_OIL_REQUEST) -> DesignState:
    """Create a pre-populated DesignState matching the crude-oil request.

    Step 1 is a passthrough — it expects structured fields to already be
    populated (NL parsing is done by POST /requirements before the pipeline).
    """
    return DesignState(
        raw_request=raw_request,
        user_id="integration-test",
        hot_fluid_name="crude oil",
        cold_fluid_name="water",
        T_hot_in_C=150.0,
        T_hot_out_C=80.0,
        T_cold_in_C=25.0,
        T_cold_out_C=45.0,
        m_dot_hot_kg_s=10.0,
        P_hot_Pa=500_000.0,
    )


def _apply_outputs(state: DesignState, outputs: dict) -> None:
    """Apply step outputs to DesignState — mirrors pipeline_runner._apply_outputs."""
    scalar_fields = {
        "Q_W", "LMTD_K", "F_factor", "U_W_m2K", "A_m2",
        "T_hot_in_C", "T_hot_out_C", "T_cold_in_C", "T_cold_out_C",
        "m_dot_hot_kg_s", "m_dot_cold_kg_s",
        "hot_fluid_name", "cold_fluid_name",
        "P_hot_Pa", "P_cold_Pa",
        "tema_type", "shell_side_fluid",
    }
    for key in scalar_fields:
        if key in outputs:
            setattr(state, key, outputs[key])

    if "hot_fluid_props" in outputs:
        v = outputs["hot_fluid_props"]
        state.hot_fluid_props = v if isinstance(v, FluidProperties) else FluidProperties(**v)

    if "cold_fluid_props" in outputs:
        v = outputs["cold_fluid_props"]
        state.cold_fluid_props = v if isinstance(v, FluidProperties) else FluidProperties(**v)

    if "geometry" in outputs:
        v = outputs["geometry"]
        state.geometry = v if isinstance(v, GeometrySpec) else GeometrySpec(**v)


async def _run_step(step, state: DesignState, ai: AIEngineer = STUB_AI) -> None:
    """Run one step and apply its outputs to state."""
    result = await step.run_with_review_loop(state, ai)
    _apply_outputs(state, result.outputs)
    state.current_step = step.step_id
    if step.step_id not in state.completed_steps:
        state.completed_steps.append(step.step_id)


async def _run_pipeline(
    state: DesignState,
    steps: list | None = None,
    ai: AIEngineer = STUB_AI,
) -> None:
    """Run all five steps in sequence."""
    if steps is None:
        steps = [
            Step01Requirements(),
            Step02HeatDuty(),
            Step03FluidProperties(),
            Step04TEMAGeometry(),
            Step05LMTD(),
        ]
    for step in steps:
        await _run_step(step, state, ai)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPipelineSteps1Through5:

    async def test_step1_populates_fluid_names_and_temperatures(self):
        state = _make_state()
        await _run_step(Step01Requirements(), state)
        assert state.hot_fluid_name is not None
        assert state.cold_fluid_name is not None
        assert state.T_hot_in_C is not None

    async def test_step2_computes_positive_heat_duty(self):
        state = _make_state()
        await _run_step(Step01Requirements(), state)
        await _run_step(Step02HeatDuty(), state)
        assert state.Q_W is not None
        assert state.Q_W > 0

    async def test_step2_all_four_temperatures_populated(self):
        state = _make_state()
        await _run_step(Step01Requirements(), state)
        await _run_step(Step02HeatDuty(), state)
        assert state.T_hot_in_C is not None
        assert state.T_hot_out_C is not None
        assert state.T_cold_in_C is not None
        assert state.T_cold_out_C is not None

    async def test_step3_populates_fluid_properties(self):
        state = _make_state()
        await _run_step(Step01Requirements(), state)
        await _run_step(Step02HeatDuty(), state)
        await _run_step(Step03FluidProperties(), state)
        assert state.hot_fluid_props is not None
        assert state.cold_fluid_props is not None
        assert state.hot_fluid_props.cp_J_kgK is not None
        assert state.hot_fluid_props.cp_J_kgK > 0

    async def test_step4_selects_tema_type_and_geometry(self):
        state = _make_state()
        await _run_step(Step01Requirements(), state)
        await _run_step(Step02HeatDuty(), state)
        await _run_step(Step03FluidProperties(), state)
        await _run_step(Step04TEMAGeometry(), state)
        assert state.tema_type is not None
        assert state.geometry is not None
        assert state.geometry.n_tubes is not None and state.geometry.n_tubes > 0

    async def test_step5_computes_lmtd_and_f_factor(self):
        state = _make_state()
        await _run_pipeline(state)
        assert state.LMTD_K is not None
        assert state.LMTD_K > 0
        assert state.F_factor is not None
        assert 0.75 <= state.F_factor <= 1.0

    async def test_full_pipeline_all_thermal_fields_populated(self):
        state = _make_state()
        await _run_pipeline(state)
        assert state.Q_W is not None and state.Q_W > 0
        assert state.LMTD_K is not None and state.LMTD_K > 0
        assert state.F_factor is not None and state.F_factor >= 0.75
        assert state.hot_fluid_props is not None
        assert state.cold_fluid_props is not None
        assert state.tema_type is not None
        assert state.geometry is not None

    async def test_full_pipeline_five_step_records(self):
        state = _make_state()
        await _run_pipeline(state)
        assert len(state.step_records) == 5

    async def test_full_pipeline_completed_steps_in_order(self):
        state = _make_state()
        await _run_pipeline(state)
        assert state.completed_steps == [1, 2, 3, 4, 5]

    async def test_full_pipeline_hot_side_cools_down(self):
        state = _make_state()
        await _run_pipeline(state)
        assert state.T_hot_in_C > state.T_hot_out_C  # type: ignore[operator]

    async def test_full_pipeline_cold_side_heats_up(self):
        state = _make_state()
        await _run_pipeline(state)
        assert state.T_cold_out_C > state.T_cold_in_C  # type: ignore[operator]

    async def test_full_pipeline_lmtd_between_end_delta_ts(self):
        """LMTD must lie between the two terminal temperature differences."""
        state = _make_state()
        await _run_pipeline(state)
        dT1 = state.T_hot_in_C - state.T_cold_out_C  # type: ignore[operator]
        dT2 = state.T_hot_out_C - state.T_cold_in_C  # type: ignore[operator]
        lo, hi = sorted([dT1, dT2])
        assert lo <= state.LMTD_K <= hi + 1e-6  # type: ignore[operator]

    async def test_step_records_have_ai_called_flag(self):
        state = _make_state()
        await _run_pipeline(state)
        for rec in state.step_records:
            assert hasattr(rec, "ai_called")

    async def test_review_notes_field_exists_on_state(self):
        state = _make_state()
        await _run_pipeline(state)
        # review_notes is a list (may be empty with stub AI that returns no observation)
        assert isinstance(state.review_notes, list)
