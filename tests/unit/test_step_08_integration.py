"""Integration tests for Step 08 — Shell-Side Heat Transfer Coefficient.

Validates:
  - Step 08 produces valid outputs with realistic inputs
  - All J-factors populated and within physical bounds
  - Kern cross-check computed
  - Layer 2 rules pass
  - Precondition checks work correctly
"""

from __future__ import annotations

import pytest

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.core.validation_rules import check as check_rules
from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_08_shell_side_h import Step08ShellSideH


# ===================================================================
# Helpers
# ===================================================================

def _make_geometry(**overrides) -> GeometrySpec:
    """Standard geometry for Step 8 testing — 3/4" tubes, triangular, 2-pass."""
    defaults = dict(
        tube_od_m=0.01905,
        tube_id_m=0.01483,
        tube_length_m=4.88,
        pitch_ratio=1.333,
        pitch_layout="triangular",
        tube_pitch_m=0.0254,
        n_passes=2,
        shell_passes=1,
        baffle_cut=0.25,
        baffle_spacing_m=0.1956,
        shell_diameter_m=0.489,
        n_tubes=158,
        n_baffles=22,
        n_sealing_strip_pairs=2,
        inlet_baffle_spacing_m=0.3048,
        outlet_baffle_spacing_m=0.3048,
    )
    defaults.update(overrides)
    return GeometrySpec(**defaults)


def _oil_props() -> FluidProperties:
    """Light hydrocarbon oil @ 80°C (match BD-REF-001)."""
    return FluidProperties(
        density_kg_m3=820.0,
        viscosity_Pa_s=0.00052,
        cp_J_kgK=2200.0,
        k_W_mK=0.138,
        Pr=8.29,
    )


def _water_props() -> FluidProperties:
    """Typical water properties near 50°C."""
    return FluidProperties(
        density_kg_m3=988.0,
        viscosity_Pa_s=0.000547,
        cp_J_kgK=4181.0,
        k_W_mK=0.644,
        Pr=3.55,
    )


def _make_state(
    shell_side="hot",
    hot_fluid="light hydrocarbon",
    cold_fluid="water",
    hot_props=None,
    cold_props=None,
    geometry=None,
    m_dot_hot=36.0,
    m_dot_cold=30.0,
    **kwargs,
) -> DesignState:
    """Create a DesignState pre-populated through Steps 1-7."""
    if hot_props is None:
        hot_props = _oil_props()
    if cold_props is None:
        cold_props = _water_props()
    if geometry is None:
        geometry = _make_geometry()

    return DesignState(
        hot_fluid_name=hot_fluid,
        cold_fluid_name=cold_fluid,
        hot_fluid_props=hot_props,
        cold_fluid_props=cold_props,
        geometry=geometry,
        shell_side_fluid=shell_side,
        m_dot_hot_kg_s=m_dot_hot,
        m_dot_cold_kg_s=m_dot_cold,
        T_hot_in_C=120.0,
        T_hot_out_C=60.0,
        T_cold_in_C=30.0,
        T_cold_out_C=55.0,
        Q_W=4_752_000.0,
        LMTD_K=42.0,
        F_factor=0.9,
        U_W_m2K=350.0,
        A_m2=36.0,
        h_tube_W_m2K=850.0,
        tube_velocity_m_s=1.5,
        Re_tube=30000.0,
        Pr_tube=3.55,
        Nu_tube=150.0,
        flow_regime_tube="turbulent",
        **kwargs,
    )


@pytest.fixture
def step():
    return Step08ShellSideH()


# ===================================================================
# 8.1 — Full execution — realistic oil-on-shell case
# ===================================================================

class TestStep08Execute:

    @pytest.mark.asyncio
    async def test_produces_valid_h_shell(self, step: Step08ShellSideH) -> None:
        """Step 8 produces a positive h_shell and populates state."""
        state = _make_state()
        result = await step.execute(state)

        assert isinstance(result, StepResult)
        assert result.step_id == 8

        # h_shell populated and positive
        assert state.h_shell_W_m2K is not None
        assert state.h_shell_W_m2K > 0

        # Re_shell populated and positive
        assert state.Re_shell is not None
        assert state.Re_shell > 0

        # h_ideal populated
        assert state.h_shell_ideal_W_m2K is not None
        assert state.h_shell_ideal_W_m2K > 0

        # h_o <= h_ideal (J-factors always reduce)
        assert state.h_shell_W_m2K <= state.h_shell_ideal_W_m2K

    @pytest.mark.asyncio
    async def test_j_factors_populated(self, step: Step08ShellSideH) -> None:
        """All 5 J-factors are populated and within physical bounds."""
        state = _make_state()
        result = await step.execute(state)

        j_factors = state.shell_side_j_factors
        assert j_factors is not None
        for key in ("J_c", "J_l", "J_b", "J_s", "J_r", "product"):
            assert key in j_factors, f"Missing J-factor: {key}"
            val = j_factors[key]
            assert val is not None, f"{key} is None"
            assert 0.2 <= val <= 1.2, f"{key} = {val} outside [0.2, 1.2]"

        # Product should be consistent
        expected_product = (
            j_factors["J_c"] * j_factors["J_l"] * j_factors["J_b"]
            * j_factors["J_s"] * j_factors["J_r"]
        )
        assert abs(j_factors["product"] - expected_product) < 0.001

    @pytest.mark.asyncio
    async def test_kern_cross_check_computed(self, step: Step08ShellSideH) -> None:
        """Kern cross-check value is populated."""
        state = _make_state()
        result = await step.execute(state)

        assert state.h_shell_kern_W_m2K is not None
        assert state.h_shell_kern_W_m2K > 0

        # Kern divergence is in outputs
        assert "kern_divergence_pct" in result.outputs

    @pytest.mark.asyncio
    async def test_outputs_complete(self, step: Step08ShellSideH) -> None:
        """All expected output keys are present."""
        state = _make_state()
        result = await step.execute(state)

        expected_keys = {
            "h_shell_W_m2K", "h_shell_ideal_W_m2K",
            "Re_shell", "G_s_kg_m2s", "j_i",
            "J_c", "J_l", "J_b", "J_s", "J_r", "J_product",
            "T_wall_estimated_C", "mu_wall_Pa_s",
            "n_baffles_used", "layout_angle_deg", "method",
            "visc_correction",
        }
        for key in expected_keys:
            assert key in result.outputs, f"Missing output key: {key}"


# ===================================================================
# 8.2 — Layer 2 rules pass
# ===================================================================

class TestStep08Rules:

    @pytest.mark.asyncio
    async def test_layer2_passes(self, step: Step08ShellSideH) -> None:
        """Layer 2 rules pass for a normal case."""
        state = _make_state()
        result = await step.execute(state)

        vr = check_rules(8, result)
        assert vr.passed, f"Layer 2 failed: {vr.errors}"

    @pytest.mark.asyncio
    async def test_cold_on_shell(self, step: Step08ShellSideH) -> None:
        """Step 8 works with cold fluid on shell side."""
        state = _make_state(shell_side="cold")
        result = await step.execute(state)

        assert state.h_shell_W_m2K is not None
        assert state.h_shell_W_m2K > 0

        vr = check_rules(8, result)
        assert vr.passed, f"Layer 2 failed: {vr.errors}"


# ===================================================================
# 8.3 — Precondition checks
# ===================================================================

class TestStep08Preconditions:

    @pytest.mark.asyncio
    async def test_missing_shell_side_fluid(self, step: Step08ShellSideH) -> None:
        """Missing shell_side_fluid raises CalculationError."""
        state = _make_state()
        state.shell_side_fluid = None
        with pytest.raises(CalculationError, match="shell_side_fluid"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_geometry(self, step: Step08ShellSideH) -> None:
        """Missing geometry raises CalculationError."""
        state = _make_state()
        state.geometry = None
        with pytest.raises(CalculationError, match="geometry"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_fluid_props(self, step: Step08ShellSideH) -> None:
        """Missing fluid properties raises CalculationError."""
        state = _make_state()
        state.hot_fluid_props = None
        with pytest.raises(CalculationError, match="hot_fluid_props"):
            await step.execute(state)


# ===================================================================
# 8.4 — AI mode is always FULL
# ===================================================================

class TestStep08AIMode:

    def test_ai_mode_full(self, step: Step08ShellSideH) -> None:
        """Step 8 AI mode is always FULL."""
        assert step.ai_mode.value == "FULL"

    def test_should_call_ai_always(self, step: Step08ShellSideH) -> None:
        """_should_call_ai always returns True for FULL mode."""
        state = _make_state()
        assert step._should_call_ai(state) is True

    def test_should_call_ai_even_in_convergence(self, step: Step08ShellSideH) -> None:
        """Convergence loop suppresses AI even for FULL-mode steps (D1 decision)."""
        state = _make_state()
        state.in_convergence_loop = True
        # D1: convergence loop check now comes BEFORE FULL mode check
        assert step._should_call_ai(state) is False


# ===================================================================
# 8.5 — Geometry state propagation (tube_pitch_m, n_baffles)
# ===================================================================

class TestStep08GeometryPropagation:
    """Verify Step 8 persists derived geometry fields back to state.

    Step 4 creates GeometrySpec without tube_pitch_m or n_baffles
    (it only sets pitch_ratio and baffle_spacing_m). Step 8 computes
    these derived values; they MUST be written back to state.geometry
    so Step 10 (pressure drops) and downstream steps can read them.

    Regression test for: step_10_requires_tube_pitch_m_n_baffles.
    """

    @pytest.mark.asyncio
    async def test_tube_pitch_m_persisted_when_none(self, step: Step08ShellSideH) -> None:
        """tube_pitch_m is written back to state.geometry when initially None."""
        geometry = _make_geometry(tube_pitch_m=None)
        assert geometry.tube_pitch_m is None  # precondition

        state = _make_state(geometry=geometry)
        await step.execute(state)

        assert state.geometry.tube_pitch_m is not None
        # Should equal pitch_ratio × tube_od_m
        expected = geometry.pitch_ratio * geometry.tube_od_m
        assert state.geometry.tube_pitch_m == pytest.approx(expected, rel=1e-6)

    @pytest.mark.asyncio
    async def test_n_baffles_persisted_when_none(self, step: Step08ShellSideH) -> None:
        """n_baffles is written back to state.geometry when initially None."""
        geometry = _make_geometry(n_baffles=None)
        assert geometry.n_baffles is None  # precondition

        state = _make_state(geometry=geometry)
        await step.execute(state)

        assert state.geometry.n_baffles is not None
        assert state.geometry.n_baffles >= 1

    @pytest.mark.asyncio
    async def test_both_none_mimics_step4_output(self, step: Step08ShellSideH) -> None:
        """When BOTH tube_pitch_m and n_baffles are None (as Step 4 produces),
        Step 8 persists both so Step 10 preconditions pass."""
        geometry = _make_geometry(tube_pitch_m=None, n_baffles=None)
        assert geometry.tube_pitch_m is None
        assert geometry.n_baffles is None

        state = _make_state(geometry=geometry)
        await step.execute(state)

        assert state.geometry.tube_pitch_m is not None
        assert state.geometry.n_baffles is not None

    @pytest.mark.asyncio
    async def test_explicit_values_not_overwritten(self, step: Step08ShellSideH) -> None:
        """If tube_pitch_m and n_baffles are already set, Step 8 does not overwrite them."""
        original_pitch = 0.0254
        original_baffles = 22
        geometry = _make_geometry(tube_pitch_m=original_pitch, n_baffles=original_baffles)

        state = _make_state(geometry=geometry)
        await step.execute(state)

        assert state.geometry.tube_pitch_m == original_pitch
        assert state.geometry.n_baffles == original_baffles
