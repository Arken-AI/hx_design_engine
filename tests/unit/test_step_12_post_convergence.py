"""Tests for Step 12 — Post-Convergence AI Re-Review.

Validates:
  - After convergence loop, Steps 7-11 re-run with in_convergence_loop=False
  - AI is called for FULL-mode steps (8, 9) in the final pass
  - Final values are applied to state
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hx_engine.app.core.ai_engineer import AIEngineer
from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.models.step_result import (
    AIDecisionEnum,
    AIReview,
    StepResult,
)
from hx_engine.app.steps.step_12_convergence import Step12Convergence
from tests.unit.conftest import make_collector as _make_collector


def _make_geometry(**overrides) -> GeometrySpec:
    defaults = dict(
        tube_od_m=0.01905,
        tube_id_m=0.01483,
        tube_length_m=4.88,
        pitch_ratio=1.25,
        pitch_layout="triangular",
        tube_pitch_m=0.0254,
        n_passes=2,
        shell_passes=1,
        baffle_cut=0.25,
        baffle_spacing_m=0.15,
        shell_diameter_m=0.489,
        n_tubes=158,
        n_baffles=22,
        n_sealing_strip_pairs=2,
        inlet_baffle_spacing_m=0.3048,
        outlet_baffle_spacing_m=0.3048,
    )
    defaults.update(overrides)
    return GeometrySpec(**defaults)


def _converging_state() -> DesignState:
    return DesignState(
        geometry=_make_geometry(),
        hot_fluid_name="crude oil",
        cold_fluid_name="water",
        shell_side_fluid="hot",
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=50.0,
        m_dot_hot_kg_s=50.0,
        m_dot_cold_kg_s=100.0,
        Q_W=6_300_000.0,
        LMTD_K=75.0,
        F_factor=0.9,
        U_W_m2K=350.0,
        A_m2=26.7,
        hot_fluid_props=FluidProperties(
            density_kg_m3=820.0,
            viscosity_Pa_s=0.00052,
            cp_J_kgK=2200.0,
            k_W_mK=0.138,
            Pr=8.29,
        ),
        cold_fluid_props=FluidProperties(
            density_kg_m3=988.0,
            viscosity_Pa_s=0.000547,
            cp_J_kgK=4181.0,
            k_W_mK=0.644,
            Pr=3.55,
        ),
        area_required_m2=25.0,
        area_provided_m2=28.75,
        overdesign_pct=15.0,
        dP_tube_Pa=45000.0,
        dP_shell_Pa=95000.0,
        tube_velocity_m_s=1.4,
        U_dirty_W_m2K=350.0,
    )


class TestPostConvergenceAI:
    @pytest.fixture
    def ai_engineer(self):
        return AIEngineer(stub_mode=True)

    @pytest.mark.asyncio
    async def test_post_convergence_ai_runs(self, ai_engineer):
        """After loop converges, Steps 7-11 re-run with AI enabled."""
        state = _converging_state()
        step12 = Step12Convergence()
        loop_flags: list[bool] = []
        post_flags: list[bool] = []
        call_count = {"n": 0, "total_calls": 0}

        async def mock_run(inner_self, state, ai_eng):
            call_count["total_calls"] += 1
            flag = state.in_convergence_loop
            if flag:
                loop_flags.append(flag)
            else:
                post_flags.append(flag)

            step_id = inner_self.step_id
            outputs = {}
            if step_id == 9:
                outputs = {"U_dirty_W_m2K": 350.0}
            elif step_id == 11:
                outputs = {"overdesign_pct": 15.0, "area_required_m2": 25.0, "area_provided_m2": 28.75}
            elif step_id == 10:
                outputs = {"dP_tube_Pa": 45000.0, "dP_shell_Pa": 95000.0}
            elif step_id == 7:
                outputs = {"tube_velocity_m_s": 1.4}
            return StepResult(step_id=step_id, step_name=inner_self.step_name, outputs=outputs)

        with patch(
            "hx_engine.app.steps.base.BaseStep.run_with_review_loop",
            new=mock_run,
        ):
            _, emit = _make_collector()
            result = await step12.run(state, ai_engineer, emit_event=emit)

        # There should be post-convergence calls with in_convergence_loop=False
        assert len(post_flags) > 0, "Post-convergence AI pass did not run"
        assert all(f is False for f in post_flags)
        assert state.convergence_converged is True

    @pytest.mark.asyncio
    async def test_post_convergence_results_applied(self, ai_engineer):
        """Values from the post-convergence pass are applied to state."""
        state = _converging_state()
        step12 = Step12Convergence()
        final_h_shell = 1500.0

        async def mock_run(inner_self, state, ai_eng):
            step_id = inner_self.step_id
            outputs = {}
            if step_id == 7:
                outputs = {"h_tube_W_m2K": 2600.0, "tube_velocity_m_s": 1.4}
            elif step_id == 8:
                outputs = {"h_shell_W_m2K": final_h_shell}
            elif step_id == 9:
                outputs = {"U_dirty_W_m2K": 350.0}
            elif step_id == 10:
                outputs = {"dP_tube_Pa": 45000.0, "dP_shell_Pa": 95000.0}
            elif step_id == 11:
                outputs = {"overdesign_pct": 15.0, "area_required_m2": 25.0, "area_provided_m2": 28.75}
            return StepResult(step_id=step_id, step_name=inner_self.step_name, outputs=outputs)

        with patch(
            "hx_engine.app.steps.base.BaseStep.run_with_review_loop",
            new=mock_run,
        ):
            _, emit = _make_collector()
            await step12.run(state, ai_engineer, emit_event=emit)

        # Post-convergence h_shell should be the final value
        assert state.h_shell_W_m2K == final_h_shell
