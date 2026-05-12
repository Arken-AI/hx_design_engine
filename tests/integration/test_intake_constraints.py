"""Integration tests for engineering intake constraints flowing through the pipeline.

Covers:
1. dP limits remapped from hot/cold to tube/shell by Step 4 (hot-on-tube path)
2. dP limits remapped from hot/cold to tube/shell by Step 4 (hot-on-shell path)
3. Fouling override supplied at intake is preserved through Step 4 without TEMA overwrite
4. AlternativeGenerator returns 3 structured options in stub mode
5. propose_budget_exhausted_options returns 3 items in stub mode
"""

from __future__ import annotations

import pytest

from hx_engine.app.core.ai_engineer import AIEngineer, AlternativeGenerator
from hx_engine.app.models.design_state import DesignState, FluidProperties, GeometrySpec
from hx_engine.app.steps.step_01_requirements import Step01Requirements
from hx_engine.app.steps.step_02_heat_duty import Step02HeatDuty
from hx_engine.app.steps.step_03_fluid_props import Step03FluidProperties
from hx_engine.app.steps.step_04_tema_geometry import Step04TEMAGeometry

# Trigger rule registration
import hx_engine.app.steps.step_01_rules  # noqa: F401
import hx_engine.app.steps.step_03_rules  # noqa: F401
import hx_engine.app.steps.step_04_rules  # noqa: F401

STUB_AI = AIEngineer(stub_mode=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**overrides) -> DesignState:
    """Crude-oil / water design with high-viscosity hot fluid (usually → tube side)."""
    state = DesignState(
        raw_request="Cool crude oil with cooling water",
        user_id="intake-test",
        hot_fluid_name="crude oil",
        cold_fluid_name="water",
        T_hot_in_C=150.0,
        T_hot_out_C=80.0,
        T_cold_in_C=25.0,
        T_cold_out_C=45.0,
        m_dot_hot_kg_s=10.0,
        P_hot_Pa=500_000.0,
        P_cold_Pa=300_000.0,
        pipeline_status="running",
    )
    for k, v in overrides.items():
        object.__setattr__(state, k, v)
    return state


def _apply_outputs(state: DesignState, outputs: dict) -> None:
    for k, v in outputs.items():
        if k == "hot_fluid_props":
            state.hot_fluid_props = v if isinstance(v, FluidProperties) else FluidProperties(**v)
        elif k == "cold_fluid_props":
            state.cold_fluid_props = v if isinstance(v, FluidProperties) else FluidProperties(**v)
        elif k == "geometry":
            state.geometry = v if isinstance(v, GeometrySpec) else GeometrySpec(**v)
        elif hasattr(state, k):
            object.__setattr__(state, k, v)


async def _run_step(step, state: DesignState) -> None:
    result = await step.run_with_review_loop(state, STUB_AI)
    _apply_outputs(state, result.outputs)
    state.current_step = step.step_id
    if step.step_id not in (state.completed_steps or []):
        cs = list(state.completed_steps or [])
        cs.append(step.step_id)
        object.__setattr__(state, "completed_steps", cs)


async def _run_through_step4(state: DesignState) -> None:
    for step in [
        Step01Requirements(),
        Step02HeatDuty(),
        Step03FluidProperties(),
        Step04TEMAGeometry(),
    ]:
        await _run_step(step, state)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestIntakeConstraintsPropagation:

    async def test_dp_limits_remapped_after_step4(self):
        """dP limits supplied at intake appear in dP_tube_max_Pa / dP_shell_max_Pa after Step 4."""
        state = _make_state(
            dP_hot_max_Pa=150_000.0,
            dP_cold_max_Pa=100_000.0,
        )
        await _run_through_step4(state)

        # After Step 4 the limits must be in the side-aware fields
        assert state.dP_tube_max_Pa is not None or state.dP_shell_max_Pa is not None, (
            "Step 4 must remap dP limits to tube/shell fields"
        )

        # Original hot/cold limits must still equal the intake values
        assert state.dP_hot_max_Pa == 150_000.0
        assert state.dP_cold_max_Pa == 100_000.0

    async def test_dp_limits_total_is_conserved_after_remap(self):
        """After remap, the sum of tube+shell limits equals hot+cold limits."""
        state = _make_state(
            dP_hot_max_Pa=200_000.0,
            dP_cold_max_Pa=80_000.0,
        )
        await _run_through_step4(state)

        tube_lim = state.dP_tube_max_Pa or 0.0
        shell_lim = state.dP_shell_max_Pa or 0.0
        hot_lim = state.dP_hot_max_Pa or 0.0
        cold_lim = state.dP_cold_max_Pa or 0.0

        # One side gets the hot limit, the other the cold limit
        assert {tube_lim, shell_lim} == {hot_lim, cold_lim} or (
            tube_lim + shell_lim == hot_lim + cold_lim
        ), "Remap must not lose or duplicate any limit value"

    async def test_fouling_override_preserved_through_step4(self):
        """User-supplied fouling resistances are not overwritten by Step 4's TEMA lookup."""
        custom_fouling = 0.0009  # very high — won't match any TEMA default

        state = _make_state(
            fouling_hot_m2K_W=custom_fouling,
            fouling_cold_m2K_W=custom_fouling,
        )
        # Pre-set the R_f fields just as design.py does
        object.__setattr__(state, "R_f_hot_m2KW", custom_fouling)
        object.__setattr__(state, "R_f_cold_m2KW", custom_fouling)

        await _run_through_step4(state)

        assert state.R_f_hot_m2KW == custom_fouling, (
            "Step 4 must not overwrite hot fouling when user supplied it at intake"
        )
        assert state.R_f_cold_m2KW == custom_fouling, (
            "Step 4 must not overwrite cold fouling when user supplied it at intake"
        )

    async def test_no_dp_limits_at_intake_leaves_side_fields_none(self):
        """When no dP limits are supplied, the side-aware fields stay None after Step 4."""
        state = _make_state()
        # Confirm no intake limits set
        assert state.dP_hot_max_Pa is None
        assert state.dP_cold_max_Pa is None

        await _run_through_step4(state)

        assert state.dP_tube_max_Pa is None
        assert state.dP_shell_max_Pa is None


@pytest.mark.asyncio
class TestAlternativeGeneratorAndProposeBudgetOptions:

    async def test_alternative_generator_returns_up_to_3_recipes(self):
        state = _make_state()
        gen = AlternativeGenerator()
        options = gen.generate(state, violation="dP_tube exceeded 250 kPa", n=3)
        assert 1 <= len(options) <= 3
        for o in options:
            assert "description" in o
            assert "rating" in o
            assert isinstance(o["rating"], int)
            assert 1 <= o["rating"] <= 10

    async def test_propose_budget_exhausted_options_stub_returns_3(self):
        """propose_budget_exhausted_options in stub mode always returns 3 items."""
        ai = AIEngineer(stub_mode=True)
        state = _make_state()
        options = await ai.propose_budget_exhausted_options(
            state, "dP_tube exceeded 250 kPa after 5 redesign attempts"
        )
        assert len(options) == 3
        for o in options:
            assert "description" in o and o["description"]
            assert "rating" in o
            assert isinstance(o["rating"], int)

    async def test_propose_budget_exhausted_options_no_api_key_returns_3(self):
        """AIEngineer with no key should fall back to stub mode and return 3 options."""
        # Instantiating without stub_mode=True but with empty env key → auto-stub
        ai = AIEngineer()  # reads settings.anthropic_api_key; expected empty in CI
        state = _make_state()
        options = await ai.propose_budget_exhausted_options(
            state, "shell-side ΔP 95 kPa exceeds limit 80 kPa"
        )
        # In CI there is no HX_ANTHROPIC_API_KEY, so stub mode activates automatically
        assert len(options) == 3
