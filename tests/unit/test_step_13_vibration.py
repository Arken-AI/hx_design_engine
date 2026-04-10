"""Integration tests for Step 13 — Vibration Check.

Tests the full Step 13 execute path using a realistic DesignState with
converged geometry, verifying:
  - Precondition checks
  - Full vibration analysis with real fluid properties
  - Output structure and state mutation
  - Validation rules (Layer 2)
  - Gas service acoustic resonance
  - Edge cases (unknown material, tight margin)
"""

from __future__ import annotations

import math
import pytest

from hx_engine.app.core.validation_rules import check as check_rules, clear_rules
from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_13_vibration import Step13VibrationCheck


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def water_props() -> FluidProperties:
    """Typical water properties at ~80°C."""
    return FluidProperties(
        density_kg_m3=972.0,
        viscosity_Pa_s=3.54e-4,
        specific_heat_J_kgK=4195.0,
        thermal_conductivity_W_mK=0.668,
        prandtl=2.22,
    )


@pytest.fixture
def geometry() -> GeometrySpec:
    """Typical 19" (489 mm) shell with 3/4" tubes, 30° triangular pitch."""
    return GeometrySpec(
        shell_diameter_m=0.489,
        tube_od_m=0.01905,
        tube_id_m=0.01483,
        tube_length_m=4.877,
        n_tubes=229,
        tube_pitch_m=0.02381,
        pitch_ratio=1.25,
        pitch_layout="triangular",
        n_passes=2,
        baffle_spacing_m=0.200,
        baffle_cut=0.25,
        n_baffles=20,
        tema_type="AES",
    )


@pytest.fixture
def converged_state(water_props, geometry) -> DesignState:
    """A fully converged state ready for Step 13."""
    state = DesignState(session_id="test-vib-001")
    state.geometry = geometry
    state.hot_fluid_props = water_props
    state.cold_fluid_props = water_props
    state.shell_side_fluid = "hot"
    state.m_dot_hot_kg_s = 10.0
    state.m_dot_cold_kg_s = 8.0
    state.T_mean_hot_C = 80.0
    state.T_mean_cold_C = 40.0
    state.tube_material = "carbon_steel"
    state.convergence_converged = True
    state.convergence_iteration = 5
    return state


# ═══════════════════════════════════════════════════════════════════════════
# Precondition tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPreconditions:
    def test_missing_convergence(self, converged_state):
        converged_state.convergence_converged = None
        missing = Step13VibrationCheck._check_preconditions(converged_state)
        assert any("convergence" in m.lower() for m in missing)

    def test_missing_geometry(self, converged_state):
        converged_state.geometry = None
        missing = Step13VibrationCheck._check_preconditions(converged_state)
        assert any("geometry" in m.lower() for m in missing)

    def test_missing_fluid_props(self, converged_state):
        converged_state.hot_fluid_props = None
        missing = Step13VibrationCheck._check_preconditions(converged_state)
        assert any("hot_fluid" in m.lower() for m in missing)

    def test_missing_flow_rate(self, converged_state):
        converged_state.m_dot_hot_kg_s = None
        missing = Step13VibrationCheck._check_preconditions(converged_state)
        assert any("m_dot_hot" in m.lower() for m in missing)

    def test_no_missing_when_complete(self, converged_state):
        missing = Step13VibrationCheck._check_preconditions(converged_state)
        assert missing == []


# ═══════════════════════════════════════════════════════════════════════════
# Execute tests
# ═══════════════════════════════════════════════════════════════════════════

class TestExecute:
    @pytest.mark.asyncio
    async def test_basic_execution(self, converged_state):
        step = Step13VibrationCheck()
        result = await step.execute(converged_state)
        assert isinstance(result, StepResult)
        assert result.step_id == 13
        assert result.step_name == "Vibration Check"

    @pytest.mark.asyncio
    async def test_outputs_structure(self, converged_state):
        step = Step13VibrationCheck()
        result = await step.execute(converged_state)
        assert "vibration_safe" in result.outputs
        assert "vibration_details" in result.outputs
        assert isinstance(result.outputs["vibration_safe"], bool)

    @pytest.mark.asyncio
    async def test_state_mutation(self, converged_state):
        step = Step13VibrationCheck()
        assert converged_state.vibration_safe is None
        assert converged_state.vibration_details is None

        await step.execute(converged_state)

        assert converged_state.vibration_safe is not None
        assert converged_state.vibration_details is not None

    @pytest.mark.asyncio
    async def test_vibration_details_keys(self, converged_state):
        step = Step13VibrationCheck()
        await step.execute(converged_state)

        details = converged_state.vibration_details
        expected_keys = {
            "controlling_mechanism", "critical_span",
            "worst_velocity_ratio", "worst_amplitude_ratio",
            "velocity_margin_pct", "amplitude_margin_pct",
            "tube_material", "E_Pa",
            "spans", "tube_properties", "crossflow_velocity",
            "acoustic_resonance",
        }
        assert expected_keys.issubset(set(details.keys()))

    @pytest.mark.asyncio
    async def test_three_spans(self, converged_state):
        step = Step13VibrationCheck()
        await step.execute(converged_state)

        spans = converged_state.vibration_details["spans"]
        assert len(spans) == 3
        assert [s["location"] for s in spans] == ["inlet", "central", "outlet"]

    @pytest.mark.asyncio
    async def test_shell_side_cold(self, converged_state):
        converged_state.shell_side_fluid = "cold"
        step = Step13VibrationCheck()
        result = await step.execute(converged_state)
        assert "vibration_safe" in result.outputs

    @pytest.mark.asyncio
    async def test_unknown_material_fallback(self, converged_state):
        converged_state.tube_material = "unobtainium"
        step = Step13VibrationCheck()
        result = await step.execute(converged_state)
        assert any("Unknown" in w or "carbon steel" in w for w in result.warnings)
        assert "vibration_safe" in result.outputs

    @pytest.mark.asyncio
    async def test_90_deg_layout(self, converged_state):
        converged_state.geometry.pitch_layout = "square"
        converged_state.geometry.pitch_angle_deg = 90
        step = Step13VibrationCheck()
        result = await step.execute(converged_state)
        assert "vibration_safe" in result.outputs

    @pytest.mark.asyncio
    async def test_missing_precondition_raises(self, converged_state):
        converged_state.geometry = None
        step = Step13VibrationCheck()
        with pytest.raises(Exception):
            await step.execute(converged_state)


# ═══════════════════════════════════════════════════════════════════════════
# Validation rules tests
# ═══════════════════════════════════════════════════════════════════════════

class TestValidationRules:
    @pytest.mark.asyncio
    async def test_rules_pass_on_safe(self, converged_state):
        step = Step13VibrationCheck()
        result = await step.execute(converged_state)

        vr = check_rules(13, result)
        if converged_state.vibration_safe:
            assert vr.passed, f"Rules should pass for safe design: {vr.errors}"

    @pytest.mark.asyncio
    async def test_rules_catch_missing_vibration_safe(self):
        # Re-register rules in case clear_rules() was called by another test
        from hx_engine.app.steps.step_13_rules import register_step13_rules
        register_step13_rules()

        result = StepResult(
            step_id=13,
            step_name="Vibration Check",
            outputs={},
        )
        vr = check_rules(13, result)
        assert not vr.passed
        assert any("vibration_safe" in e for e in vr.errors)


# ═══════════════════════════════════════════════════════════════════════════
# Gas service
# ═══════════════════════════════════════════════════════════════════════════

class TestGasService:
    @pytest.fixture
    def gas_props(self) -> FluidProperties:
        """Typical nitrogen at ~200°C, 5 bar.

        Uses model_construct to bypass the density validator which
        currently enforces a liquid range [50, 2000]. Gas densities
        are typically 0.1–20 kg/m³.
        """
        return FluidProperties.model_construct(
            density_kg_m3=4.5,
            viscosity_Pa_s=2.5e-5,
            specific_heat_J_kgK=1042.0,
            thermal_conductivity_W_mK=0.035,
            prandtl=0.72,
        )

    @pytest.mark.asyncio
    async def test_gas_triggers_acoustic_check(self, converged_state, gas_props):
        converged_state.hot_fluid_props = gas_props
        converged_state.shell_side_fluid = "hot"
        step = Step13VibrationCheck()
        result = await step.execute(converged_state)

        details = result.outputs["vibration_details"]
        acoustic = details["acoustic_resonance"]
        # Acoustic check should be attempted (may or may not be applicable
        # depending on whether P_shell_Pa and gamma are set)
        assert isinstance(acoustic, dict)

    @pytest.mark.asyncio
    async def test_gas_with_pressure_info(self, converged_state, gas_props):
        """When P_shell_Pa and gamma_shell are available, acoustic check is applicable.

        Note: DesignState doesn't yet have these fields — this test uses
        object.__setattr__ to simulate them for future compatibility.
        """
        converged_state.hot_fluid_props = gas_props
        converged_state.shell_side_fluid = "hot"
        # Bypass Pydantic's field checking for fields not yet on DesignState
        object.__setattr__(converged_state, "P_shell_Pa", 500000.0)
        object.__setattr__(converged_state, "gamma_shell", 1.4)
        step = Step13VibrationCheck()
        result = await step.execute(converged_state)
        details = result.outputs["vibration_details"]
        assert details["acoustic_resonance"]["applicable"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Step metadata
# ═══════════════════════════════════════════════════════════════════════════

class TestStepMetadata:
    def test_step_id(self):
        step = Step13VibrationCheck()
        assert step.step_id == 13

    def test_step_name(self):
        step = Step13VibrationCheck()
        assert step.step_name == "Vibration Check"

    def test_ai_mode_full(self):
        from hx_engine.app.models.step_result import AIModeEnum
        step = Step13VibrationCheck()
        assert step.ai_mode == AIModeEnum.FULL

    def test_should_call_ai_true(self, converged_state):
        step = Step13VibrationCheck()
        assert step._should_call_ai(converged_state) is True

    def test_should_call_ai_false_in_convergence(self, converged_state):
        converged_state.in_convergence_loop = True
        step = Step13VibrationCheck()
        assert step._should_call_ai(converged_state) is False
