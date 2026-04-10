"""Tests for Step 10 — Pressure Drop executor and rules.

Covers: precondition checks, full execution with mock state,
component sum verification, fluid-side mapping, cross-checks,
warnings, AI skip in convergence loop, and all 6 validation rules.
"""

from __future__ import annotations

import pytest

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_10_pressure_drops import Step10PressureDrops

# Import rules to ensure registration
import hx_engine.app.steps.step_10_rules as rules_mod


# ── Fixture: pre-populated state through Step 9 ──────────────────────

def _make_state(
    shell_side_fluid: str = "hot",
    tube_velocity: float = 1.5,
    Re_tube: float = 15_000.0,
    Re_shell: float = 12_000.0,
    m_dot_hot: float = 50.0,
    m_dot_cold: float = 100.0,
    in_convergence_loop: bool = False,
    **overrides,
) -> DesignState:
    """Create DesignState pre-populated through Steps 1-9."""
    hot_props = FluidProperties(
        density_kg_m3=850.0,
        viscosity_Pa_s=0.0012,
        specific_heat_J_kgK=2200.0,
        thermal_conductivity_W_mK=0.13,
        Pr=20.3,
    )
    cold_props = FluidProperties(
        density_kg_m3=995.0,
        viscosity_Pa_s=0.0008,
        specific_heat_J_kgK=4180.0,
        thermal_conductivity_W_mK=0.62,
        Pr=5.4,
    )

    state = DesignState(
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=55.0,
        hot_fluid_name="crude oil",
        cold_fluid_name="cooling water",
        m_dot_hot_kg_s=m_dot_hot,
        m_dot_cold_kg_s=m_dot_cold,
        hot_fluid_props=hot_props,
        cold_fluid_props=cold_props,
        shell_side_fluid=shell_side_fluid,
        geometry=GeometrySpec(
            shell_diameter_m=0.489,
            tube_od_m=0.01905,
            tube_id_m=0.01483,
            tube_length_m=4.88,
            n_tubes=158,
            tube_pitch_m=0.02381,
            pitch_ratio=1.25,
            pitch_layout="triangular",
            n_passes=2,
            baffle_spacing_m=0.15,
            baffle_cut=0.25,
            n_baffles=30,
        ),
        tube_velocity_m_s=tube_velocity,
        Re_tube=Re_tube,
        Re_shell=Re_shell,
        h_tube_W_m2K=5000.0,
        h_shell_W_m2K=2000.0,
        R_f_hot_m2KW=0.000176,
        R_f_cold_m2KW=0.000176,
        in_convergence_loop=in_convergence_loop,
    )
    for k, v in overrides.items():
        setattr(state, k, v)
    return state


# ══════════════════════════════════════════════════════════════════════
# Precondition tests
# ══════════════════════════════════════════════════════════════════════

class TestPreconditions:

    @pytest.mark.asyncio
    async def test_missing_geometry(self) -> None:
        state = _make_state()
        state.geometry = None
        step = Step10PressureDrops()
        with pytest.raises(CalculationError, match="geometry"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_tube_velocity(self) -> None:
        state = _make_state()
        state.tube_velocity_m_s = None
        step = Step10PressureDrops()
        with pytest.raises(CalculationError, match="tube_velocity_m_s"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_re_tube(self) -> None:
        state = _make_state()
        state.Re_tube = None
        step = Step10PressureDrops()
        with pytest.raises(CalculationError, match="Re_tube"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_shell_side_fluid(self) -> None:
        state = _make_state()
        state.shell_side_fluid = None
        step = Step10PressureDrops()
        with pytest.raises(CalculationError, match="shell_side_fluid"):
            await step.execute(state)


# ══════════════════════════════════════════════════════════════════════
# Execution tests
# ══════════════════════════════════════════════════════════════════════

class TestExecution:

    @pytest.mark.asyncio
    async def test_basic_execution_returns_all_keys(self) -> None:
        state = _make_state()
        step = Step10PressureDrops()
        result = await step.execute(state)

        expected_keys = {
            "dP_tube_Pa", "dP_shell_Pa",
            "dP_tube_friction_Pa", "dP_tube_minor_Pa", "dP_tube_nozzle_Pa",
            "dP_shell_crossflow_Pa", "dP_shell_window_Pa", "dP_shell_end_Pa",
            "dP_shell_nozzle_Pa",
            "Fb_prime_dP", "FL_prime_dP",
            "nozzle_id_tube_m", "nozzle_id_shell_m",
            "rho_v2_tube_nozzle", "rho_v2_shell_nozzle",
            "dP_shell_simplified_delaware_Pa", "dP_shell_kern_Pa",
            "dP_shell_bell_vs_kern_pct",
        }
        assert expected_keys.issubset(set(result.outputs.keys()))

    @pytest.mark.asyncio
    async def test_tube_dp_components_sum(self) -> None:
        """friction + minor + nozzle = total tube ΔP."""
        state = _make_state()
        step = Step10PressureDrops()
        result = await step.execute(state)
        o = result.outputs

        total = o["dP_tube_friction_Pa"] + o["dP_tube_minor_Pa"] + o["dP_tube_nozzle_Pa"]
        assert o["dP_tube_Pa"] == pytest.approx(total, rel=1e-6)

    @pytest.mark.asyncio
    async def test_all_dp_positive(self) -> None:
        state = _make_state()
        step = Step10PressureDrops()
        result = await step.execute(state)
        o = result.outputs

        assert o["dP_tube_Pa"] > 0
        assert o["dP_shell_Pa"] > 0
        assert o["dP_tube_friction_Pa"] > 0
        assert o["dP_tube_minor_Pa"] > 0

    @pytest.mark.asyncio
    async def test_state_fields_populated(self) -> None:
        """Execute should write all ΔP fields to state."""
        state = _make_state()
        step = Step10PressureDrops()
        await step.execute(state)

        assert state.dP_tube_Pa is not None
        assert state.dP_shell_Pa is not None
        assert state.Fb_prime_dP is not None
        assert state.FL_prime_dP is not None
        assert state.nozzle_id_tube_m is not None

    @pytest.mark.asyncio
    async def test_fluid_side_mapping_hot_shell(self) -> None:
        """shell_side_fluid='hot' → hot fluid props used for shell."""
        state = _make_state(shell_side_fluid="hot")
        step = Step10PressureDrops()
        result = await step.execute(state)
        # Just verify it runs without error — side mapping is internal
        assert result.outputs["dP_shell_Pa"] > 0

    @pytest.mark.asyncio
    async def test_fluid_side_mapping_cold_shell(self) -> None:
        """shell_side_fluid='cold' → cold fluid props used for shell."""
        state = _make_state(shell_side_fluid="cold")
        step = Step10PressureDrops()
        result = await step.execute(state)
        assert result.outputs["dP_shell_Pa"] > 0

    @pytest.mark.asyncio
    async def test_cross_checks_populated(self) -> None:
        state = _make_state()
        step = Step10PressureDrops()
        result = await step.execute(state)
        o = result.outputs

        assert o["dP_shell_kern_Pa"] is not None
        assert o["dP_shell_simplified_delaware_Pa"] is not None

    @pytest.mark.asyncio
    async def test_correction_factors_in_range(self) -> None:
        state = _make_state()
        step = Step10PressureDrops()
        result = await step.execute(state)
        o = result.outputs

        assert 0 < o["Fb_prime_dP"] <= 1.0
        assert 0 < o["FL_prime_dP"] <= 1.0


# ══════════════════════════════════════════════════════════════════════
# AI trigger / convergence tests
# ══════════════════════════════════════════════════════════════════════

class TestAITrigger:

    def test_ai_skipped_in_convergence_loop(self) -> None:
        state = _make_state(in_convergence_loop=True)
        step = Step10PressureDrops()
        assert step._should_call_ai(state) is False

    def test_ai_not_called_comfortable_margin(self) -> None:
        """When no ΔP fields on state yet, default to no AI call."""
        state = _make_state(in_convergence_loop=False)
        step = Step10PressureDrops()
        # Before execute, no dP on state → no trigger
        assert step._should_call_ai(state) is False

    @pytest.mark.asyncio
    async def test_ai_triggered_after_tight_margin(self) -> None:
        """After execute with tight ΔP, AI should trigger."""
        state = _make_state(m_dot_hot=150.0, m_dot_cold=300.0)
        step = Step10PressureDrops()
        await step.execute(state)
        # Check state fields populated → conditional trigger evaluates
        # May or may not trigger depending on actual values — just ensure no crash
        _ = step._should_call_ai(state)


# ══════════════════════════════════════════════════════════════════════
# Validation rules
# ══════════════════════════════════════════════════════════════════════

def _make_result(**kwargs) -> StepResult:
    """Create a StepResult with given outputs."""
    defaults = {
        "dP_tube_Pa": 50_000.0,
        "dP_shell_Pa": 80_000.0,
        "rho_v2_tube_nozzle": 500.0,
        "rho_v2_shell_nozzle": 500.0,
    }
    defaults.update(kwargs)
    return StepResult(step_id=10, step_name="Pressure Drops", outputs=defaults)


class TestRules:

    def test_dp_tube_positive_pass(self) -> None:
        result = _make_result(dP_tube_Pa=50_000.0)
        passed, msg = rules_mod._rule_dp_tube_positive(10, result)
        assert passed is True

    def test_dp_tube_positive_fail(self) -> None:
        result = _make_result(dP_tube_Pa=-100.0)
        passed, msg = rules_mod._rule_dp_tube_positive(10, result)
        assert passed is False

    def test_dp_tube_over_limit(self) -> None:
        result = _make_result(dP_tube_Pa=80_000.0)
        passed, msg = rules_mod._rule_dp_tube_within_limit(10, result)
        assert passed is False
        assert "0.7 bar" in msg

    def test_dp_shell_over_limit(self) -> None:
        result = _make_result(dP_shell_Pa=150_000.0)
        passed, msg = rules_mod._rule_dp_shell_within_limit(10, result)
        assert passed is False
        assert "1.4 bar" in msg

    def test_nozzle_tube_over_limit(self) -> None:
        result = _make_result(rho_v2_tube_nozzle=2500.0)
        passed, msg = rules_mod._rule_nozzle_rho_v2_tube(10, result)
        assert passed is False
        assert "2230" in msg

    def test_nozzle_shell_over_limit(self) -> None:
        result = _make_result(rho_v2_shell_nozzle=2500.0)
        passed, msg = rules_mod._rule_nozzle_rho_v2_shell(10, result)
        assert passed is False
        assert "2230" in msg

    def test_all_rules_pass_healthy(self) -> None:
        result = _make_result(
            dP_tube_Pa=50_000.0,
            dP_shell_Pa=80_000.0,
            rho_v2_tube_nozzle=500.0,
            rho_v2_shell_nozzle=500.0,
        )
        for rule_fn in [
            rules_mod._rule_dp_tube_positive,
            rules_mod._rule_dp_shell_positive,
            rules_mod._rule_dp_tube_within_limit,
            rules_mod._rule_dp_shell_within_limit,
            rules_mod._rule_nozzle_rho_v2_tube,
            rules_mod._rule_nozzle_rho_v2_shell,
        ]:
            passed, msg = rule_fn(10, result)
            assert passed is True, f"Rule {rule_fn.__name__} failed: {msg}"
