"""Integration tests for Step 12 — Convergence Loop.

End-to-end tests that run Step12Convergence.run() with mocked sub-steps.
Verifies convergence detection, state mutation, and iteration budget.
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
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_12_convergence import Step12Convergence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_geometry(**overrides) -> GeometrySpec:
    defaults = dict(
        tube_od_m=0.01905,
        tube_id_m=0.01483,
        tube_length_m=4.877,
        pitch_ratio=1.25,
        pitch_layout="triangular",
        tube_pitch_m=0.0238,
        n_passes=2,
        shell_passes=1,
        baffle_cut=0.25,
        baffle_spacing_m=0.150,
        shell_diameter_m=0.489,
        n_tubes=158,
        n_baffles=22,
        n_sealing_strip_pairs=2,
        inlet_baffle_spacing_m=0.300,
        outlet_baffle_spacing_m=0.300,
    )
    defaults.update(overrides)
    return GeometrySpec(**defaults)


def _pre_convergence_state() -> DesignState:
    """State ready for Step 12 — includes intentional U mismatch to force
    at least a few iterations before settling."""
    return DesignState(
        geometry=_make_geometry(),
        hot_fluid_name="crude oil",
        cold_fluid_name="water",
        shell_side_fluid="hot",
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=50.0,
        T_mean_hot_C=120.0,
        T_mean_cold_C=40.0,
        m_dot_hot_kg_s=50.0,
        m_dot_cold_kg_s=100.0,
        Q_W=6_300_000.0,
        LMTD_K=75.0,
        F_factor=0.90,
        # Intentional mismatch: U_W_m2K ≠ U_dirty_W_m2K to force iterations
        U_W_m2K=380.0,
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
        # Step 11 seed (intentional mismatch — overdesign below target to force loop)
        area_required_m2=27.0,
        area_provided_m2=26.7,
        overdesign_pct=5.0,
        dP_tube_Pa=45_000.0,
        dP_shell_Pa=95_000.0,
        tube_velocity_m_s=1.4,
        U_dirty_W_m2K=360.0,   # intentionally high to drive convergence
    )


class MockSSEManager:
    """Minimal SSE manager that silently absorbs all events."""

    async def emit(self, session_id: str, event) -> None:  # noqa: ARG002
        pass


def _make_converging_mock():
    """Return a run_with_review_loop mock that converges in ~4 iterations."""
    call_count = {"n": 0}

    async def mock_run(inner_self, state, ai_eng):
        call_count["n"] += 1
        step_id = inner_self.step_id
        # After 4 full sub-step passes (4 × 5 calls = 20 individual calls),
        # report values that satisfy _check_convergence.
        pass_number = (call_count["n"] - 1) // 5 + 1

        outputs: dict = {}
        if step_id == 7:
            outputs = {
                "h_tube_W_m2K": 2500.0,
                "tube_velocity_m_s": 1.4,
                "Re_tube": 25_000.0,
            }
        elif step_id == 8:
            outputs = {"h_shell_W_m2K": 1200.0, "Re_shell": 15_000.0}
        elif step_id == 9:
            # U converges toward 350 — delta_U_pct drops below 1 % by pass 4
            u = 355.0 - pass_number * 1.5
            outputs = {"U_dirty_W_m2K": u, "U_clean_W_m2K": u * 1.1}
        elif step_id == 10:
            outputs = {"dP_tube_Pa": 45_000.0, "dP_shell_Pa": 95_000.0}
        elif step_id == 11:
            outputs = {
                "area_required_m2": 25.0,
                "area_provided_m2": 28.75,
                "overdesign_pct": 15.0,   # inside 10–25% target
                "service_classification": "standard_process",
            }
        return StepResult(
            step_id=step_id,
            step_name=inner_self.step_name,
            outputs=outputs,
        )

    return mock_run


# ---------------------------------------------------------------------------
# T12.1 — Convergence happy path
# ---------------------------------------------------------------------------

class TestConvergenceHappyPath:
    """T12.1 — Loop converges within budget."""

    @pytest.fixture
    def sse(self):
        return MockSSEManager()

    @pytest.fixture
    def ai(self):
        return AIEngineer(stub_mode=True)

    @pytest.mark.asyncio
    async def test_converges_within_ten_iterations(self, sse, ai):
        state = _pre_convergence_state()
        step12 = Step12Convergence()
        with patch(
            "hx_engine.app.steps.base.BaseStep.run_with_review_loop",
            new=_make_converging_mock(),
        ):
            await step12.run(state, ai, sse, "int-test-12-01")

        assert state.convergence_converged is True
        assert state.convergence_iteration is not None
        assert state.convergence_iteration <= 10, (
            f"Expected convergence in ≤10 iterations, "
            f"got {state.convergence_iteration}"
        )

    @pytest.mark.asyncio
    async def test_in_convergence_loop_reset_on_exit(self, sse, ai):
        """in_convergence_loop is False after a successful run."""
        state = _pre_convergence_state()
        step12 = Step12Convergence()
        with patch(
            "hx_engine.app.steps.base.BaseStep.run_with_review_loop",
            new=_make_converging_mock(),
        ):
            await step12.run(state, ai, sse, "int-test-12-02")

        assert state.in_convergence_loop is False

    @pytest.mark.asyncio
    async def test_convergence_trajectory_populated(self, sse, ai):
        """At least one trajectory snapshot written per iteration."""
        state = _pre_convergence_state()
        step12 = Step12Convergence()
        with patch(
            "hx_engine.app.steps.base.BaseStep.run_with_review_loop",
            new=_make_converging_mock(),
        ):
            await step12.run(state, ai, sse, "int-test-12-03")

        assert len(state.convergence_trajectory) > 0

    @pytest.mark.asyncio
    async def test_in_convergence_loop_reset_even_on_substep_exception(self, sse, ai):
        """try/finally guarantees in_convergence_loop is cleared on error."""
        state = _pre_convergence_state()
        step12 = Step12Convergence()

        async def exploding_mock(inner_self, state, ai_eng):
            raise RuntimeError("Simulated sub-step failure")

        with patch(
            "hx_engine.app.steps.base.BaseStep.run_with_review_loop",
            new=exploding_mock,
        ):
            await step12.run(state, ai, sse, "int-test-12-04")

        assert state.in_convergence_loop is False
