"""Tests for ST-10 — Step 14 integration tests.

End-to-end tests with realistic DesignState values.
"""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.steps.step_14_mechanical import Step14MechanicalCheck


def _serth_state(**overrides) -> DesignState:
    """Serth Example 5.1 – like geometry through Step 13."""
    defaults = dict(
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=55.0,
        T_mean_hot_C=120.0,
        T_mean_cold_C=42.5,
        P_hot_Pa=1_000_000.0,
        P_cold_Pa=500_000.0,
        shell_side_fluid="hot",
        tema_type="BEM",
        tube_material="carbon_steel",
        shell_material="sa516_gr70",
        convergence_converged=True,
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
        hot_fluid_props=FluidProperties(
            density_kg_m3=850.0, viscosity_Pa_s=0.001,
            cp_J_kgK=2100.0, k_W_mK=0.13, Pr=16.1,
        ),
        cold_fluid_props=FluidProperties(
            density_kg_m3=995.0, viscosity_Pa_s=0.0008,
            cp_J_kgK=4180.0, k_W_mK=0.62, Pr=5.4,
        ),
    )
    defaults.update(overrides)
    return DesignState(**defaults)


@pytest.fixture
def step():
    return Step14MechanicalCheck()


class TestSerthExample:
    """T10.1"""

    @pytest.mark.asyncio
    async def test_serth_passes(self, step):
        """T10.1: Serth Example 5.1 geometry passes all three checks."""
        state = _serth_state()
        result = await step.execute(state)
        assert state.tube_thickness_ok is True
        assert state.shell_thickness_ok is True
        assert state.mechanical_details is not None
        assert state.expansion_mm is not None


class TestHighPressure:
    """T10.2"""

    @pytest.mark.asyncio
    async def test_high_pressure_ai_trigger(self, step):
        """T10.2: 50 bar tube-side → AI triggered."""
        state = _serth_state(P_cold_Pa=5e7, shell_side_fluid="hot")
        await step.execute(state)
        assert step._conditional_ai_trigger(state)


class TestVacuumShell:
    """T10.3"""

    @pytest.mark.asyncio
    async def test_vacuum_shell_external_check(self, step):
        """T10.3: Vacuum shell → external pressure result present."""
        state = _serth_state(P_hot_Pa=50_000.0, shell_side_fluid="hot")
        await step.execute(state)
        shell = state.mechanical_details["shell"]
        assert shell["external_pressure"] is not None


class TestExpansionTEMATypes:
    """T10.4, T10.5"""

    @pytest.mark.asyncio
    async def test_bem_high_delta_t(self, step):
        """T10.4: BEM with 304 SS tubes + CS shell, high ΔT."""
        state = _serth_state(
            tube_material="stainless_304",
            shell_material="carbon_steel",
            tema_type="BEM",
            T_mean_hot_C=350.0,
            T_mean_cold_C=50.0,
            shell_side_fluid="cold",
        )
        await step.execute(state)
        # 304 has higher α than CS → significant differential
        assert state.expansion_mm > 1.0

    @pytest.mark.asyncio
    async def test_aes_no_expansion_failure(self, step):
        """T10.5: AES with same conditions → within_tolerance is None."""
        state = _serth_state(
            tube_material="stainless_304",
            shell_material="carbon_steel",
            tema_type="AES",
            T_mean_hot_C=350.0,
            T_mean_cold_C=50.0,
            shell_side_fluid="cold",
        )
        await step.execute(state)
        exp = state.mechanical_details["expansion"]
        assert exp["within_tolerance"] is None


class TestRulesIntegration:
    """T10.6"""

    @pytest.mark.asyncio
    async def test_all_rules_pass(self, step):
        """T10.6: Standard geometry → all rules pass."""
        from hx_engine.app.steps.step_14_rules import (
            _rule_expansion_within_tolerance,
            _rule_mechanical_details_present,
            _rule_shell_t_min_positive,
            _rule_tube_external_adequate,
            _rule_tube_internal_adequate,
            _rule_tube_thickness_present,
            _rule_shell_thickness_present,
        )

        # Use same material for tubes and shell + close mean temperatures
        state = _serth_state(
            tube_material="carbon_steel",
            shell_material="sa516_gr70",
            T_mean_hot_C=90.0,
            T_mean_cold_C=60.0,
        )
        result = await step.execute(state)
        for rule_fn in (
            _rule_tube_thickness_present,
            _rule_shell_thickness_present,
            _rule_mechanical_details_present,
            _rule_tube_internal_adequate,
            _rule_tube_external_adequate,
            _rule_shell_t_min_positive,
            _rule_expansion_within_tolerance,
        ):
            passed, msg = rule_fn(14, result)
            assert passed, f"{rule_fn.__name__} failed: {msg}"


class TestStepResult:
    """T10.7"""

    @pytest.mark.asyncio
    async def test_result_outputs(self, step):
        """T10.7: StepResult has all key fields."""
        state = _serth_state()
        result = await step.execute(state)
        assert result.step_id == 14
        assert result.step_name == "Mechanical Design Check"
        assert "tube_thickness_ok" in result.outputs
        assert "shell_thickness_ok" in result.outputs
        assert "expansion_mm" in result.outputs
        assert "mechanical_details" in result.outputs
