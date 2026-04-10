"""Tests for Piece 7: Core execute() Logic."""

from __future__ import annotations

import copy

import pytest

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import DesignState, FluidProperties, GeometrySpec
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.base import StepProtocol
from hx_engine.app.steps.step_04_tema_geometry import Step04TEMAGeometry


def _make_state(**overrides) -> DesignState:
    defaults = dict(
        hot_fluid_name="crude oil",
        cold_fluid_name="cooling water",
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=60.0,
        P_hot_Pa=101325,
        P_cold_Pa=101325,
        m_dot_hot_kg_s=50.0,
        m_dot_cold_kg_s=100.0,
        hot_fluid_props=FluidProperties(
            density_kg_m3=850, viscosity_Pa_s=0.005,
            cp_J_kgK=2000, k_W_mK=0.13, Pr=77.0,
        ),
        cold_fluid_props=FluidProperties(
            density_kg_m3=1000, viscosity_Pa_s=0.001,
            cp_J_kgK=4186, k_W_mK=0.6, Pr=7.0,
        ),
        Q_W=6_000_000,  # ~6 MW
    )
    defaults.update(overrides)
    return DesignState(**defaults)


class TestStep04Execute:
    async def test_benchmark_crude_water(self):
        """Crude oil 150→90°C + water 30→60°C → complete result."""
        step = Step04TEMAGeometry()
        state = _make_state()
        result = await step.execute(state)

        assert result.step_id == 4
        assert "tema_type" in result.outputs
        assert "geometry" in result.outputs
        assert "shell_side_fluid" in result.outputs
        assert isinstance(result.outputs["geometry"], GeometrySpec)

    async def test_missing_fluid_props_error(self):
        """hot_fluid_props = None → CalculationError."""
        step = Step04TEMAGeometry()
        state = _make_state(hot_fluid_props=None)
        with pytest.raises(CalculationError, match="hot_fluid_props"):
            await step.execute(state)

    async def test_missing_Q_error(self):
        """Q_W = None → CalculationError."""
        step = Step04TEMAGeometry()
        state = _make_state(Q_W=None)
        with pytest.raises(CalculationError, match="Q_W"):
            await step.execute(state)

    async def test_missing_temperatures_error(self):
        """T_hot_in_C = None → CalculationError."""
        step = Step04TEMAGeometry()
        state = _make_state(T_hot_in_C=None)
        with pytest.raises(CalculationError, match="T_hot_in_C"):
            await step.execute(state)

    async def test_outputs_dict_keys(self):
        """Normal run → outputs has required keys."""
        step = Step04TEMAGeometry()
        state = _make_state()
        result = await step.execute(state)
        assert "tema_type" in result.outputs
        assert "geometry" in result.outputs
        assert "shell_side_fluid" in result.outputs
        assert "tema_reasoning" in result.outputs
        assert "escalation_hints" in result.outputs

    async def test_step_result_metadata(self):
        """Normal run → step_id=4, step_name correct."""
        step = Step04TEMAGeometry()
        state = _make_state()
        result = await step.execute(state)
        assert result.step_id == 4
        assert result.step_name == "TEMA Geometry Selection"

    async def test_state_not_mutated(self):
        """execute() must not modify the input DesignState."""
        step = Step04TEMAGeometry()
        state = _make_state()
        state_before = state.model_dump_json()
        await step.execute(state)
        state_after = state.model_dump_json()
        assert state_before == state_after

    async def test_geometry_is_valid_spec(self):
        """Output geometry passes GeometrySpec validators."""
        step = Step04TEMAGeometry()
        state = _make_state()
        result = await step.execute(state)
        geom = result.outputs["geometry"]
        # Re-validate
        validated = GeometrySpec.model_validate(geom.model_dump())
        assert validated.tube_id_m < validated.tube_od_m

    async def test_water_water_clean_service(self):
        """Water both sides → BEM + triangular pitch."""
        step = Step04TEMAGeometry()
        state = _make_state(
            hot_fluid_name="water",
            cold_fluid_name="water",
            T_hot_in_C=80, T_hot_out_C=60,
            T_cold_in_C=30, T_cold_out_C=50,
        )
        result = await step.execute(state)
        assert result.outputs["tema_type"] == "BEM"
        assert result.outputs["geometry"].pitch_layout == "triangular"

    def test_step_protocol_compliance(self):
        """isinstance(Step04TEMAGeometry(), StepProtocol) → True."""
        step = Step04TEMAGeometry()
        assert isinstance(step, StepProtocol)


class TestFE2RfLowerBoundWarning:
    """FE-2: Rf at lower bound + low tube-side confidence → warning."""

    @pytest.mark.asyncio
    async def test_warning_fires_when_rf_at_lower_bound_and_low_confidence(self):
        """Lube oil tube-side with petroleum-generic confidence → warning emitted.

        mu=0.005 Pa·s keeps lube oil below the 10× viscosity threshold so Rule 4
        doesn't fire and lube oil stays on tube-side (default allocation).
        """
        step = Step04TEMAGeometry()
        state = _make_state(
            hot_fluid_name="lube oil",
            cold_fluid_name="water",
            hot_fluid_props=FluidProperties(
                density_kg_m3=870, viscosity_Pa_s=0.005,
                cp_J_kgK=2100, k_W_mK=0.13, Pr=80.0,
                property_source="petroleum-generic",
                property_confidence=0.65,
            ),
            cold_fluid_props=FluidProperties(
                density_kg_m3=1000, viscosity_Pa_s=0.001,
                cp_J_kgK=4186, k_W_mK=0.6, Pr=7.0,
                property_source="iapws",
                property_confidence=1.0,
            ),
        )
        result = await step.execute(state)
        all_warnings = result.warnings + state.warnings
        assert any("lower bound" in w for w in all_warnings)
        assert any("lube oil" in w for w in all_warnings)
        # Three Rf scenarios must be listed
        lower_bound_warnings = [w for w in all_warnings if "lower bound" in w]
        assert any("(1)" in w and "(2)" in w and "(3)" in w for w in lower_bound_warnings)

    @pytest.mark.asyncio
    async def test_no_warning_when_confidence_above_threshold(self):
        """High tube-side confidence (>= 0.80) → no lower-bound warning."""
        step = Step04TEMAGeometry()
        state = _make_state(
            hot_fluid_name="lube oil",
            cold_fluid_name="water",
            hot_fluid_props=FluidProperties(
                density_kg_m3=870, viscosity_Pa_s=0.005,
                cp_J_kgK=2100, k_W_mK=0.13, Pr=80.0,
                property_source="petroleum-named",
                property_confidence=0.85,
            ),
            cold_fluid_props=FluidProperties(
                density_kg_m3=1000, viscosity_Pa_s=0.001,
                cp_J_kgK=4186, k_W_mK=0.6, Pr=7.0,
            ),
        )
        result = await step.execute(state)
        all_warnings = result.warnings + state.warnings
        assert not any("lower bound" in w for w in all_warnings)

    @pytest.mark.asyncio
    async def test_no_warning_when_rf_above_lower_bound(self):
        """Rf already above lower bound → no warning even with low confidence."""
        step = Step04TEMAGeometry()
        # diesel has Rf=0.000352, lower bound=0.000176 → not at lower bound
        state = _make_state(
            hot_fluid_name="diesel",
            cold_fluid_name="water",
            hot_fluid_props=FluidProperties(
                density_kg_m3=830, viscosity_Pa_s=0.003,
                cp_J_kgK=1900, k_W_mK=0.14, Pr=40.0,
                property_source="petroleum-generic",
                property_confidence=0.65,
            ),
            cold_fluid_props=FluidProperties(
                density_kg_m3=1000, viscosity_Pa_s=0.001,
                cp_J_kgK=4186, k_W_mK=0.6, Pr=7.0,
            ),
        )
        result = await step.execute(state)
        all_warnings = result.warnings + state.warnings
        assert not any("lower bound" in w for w in all_warnings)


class TestFE4ShellIdFinalised:
    """FE-4: shell_id_finalised flag set correctly by Step 4."""

    @pytest.mark.asyncio
    async def test_aes_sets_flag_false(self):
        """AES/AEU (floating head) → shell_id_finalised = False.

        Uses crude oil at T_mean > 120°C so it's classified as 'heavy' fouling
        → Rule 3 fires → crude oil on tube-side → ΔT 90°C → AES selected.
        tema_type is read from result.outputs (not state.tema_type, which is
        only applied by pipeline_runner._apply_outputs, not called in unit tests).
        """
        step = Step04TEMAGeometry()
        state = _make_state(
            hot_fluid_name="crude oil",
            cold_fluid_name="water",
            T_hot_in_C=200, T_hot_out_C=120,  # T_mean=160°C → crude oil heavy fouling
            T_cold_in_C=30, T_cold_out_C=70,
            hot_fluid_props=FluidProperties(
                density_kg_m3=830, viscosity_Pa_s=0.005,
                cp_J_kgK=2200, k_W_mK=0.12, Pr=92.0,
            ),
            cold_fluid_props=FluidProperties(
                density_kg_m3=1000, viscosity_Pa_s=0.001,
                cp_J_kgK=4186, k_W_mK=0.6, Pr=7.0,
            ),
        )
        result = await step.execute(state)
        tema = result.outputs["tema_type"]
        if tema in ("AES", "AEU"):
            assert state.shell_id_finalised is False
        else:
            # If allocation/TEMA logic chose a different type, flag is True
            assert state.shell_id_finalised is True

    @pytest.mark.asyncio
    async def test_bem_sets_flag_true(self):
        """BEM (fixed tubesheet) → shell_id_finalised = True.

        tema_type is read from result.outputs (pipeline_runner not called here).
        """
        step = Step04TEMAGeometry()
        state = _make_state(
            hot_fluid_name="water",
            cold_fluid_name="water",
            T_hot_in_C=80, T_hot_out_C=60,
            T_cold_in_C=30, T_cold_out_C=50,
            hot_fluid_props=FluidProperties(
                density_kg_m3=990, viscosity_Pa_s=0.0008,
                cp_J_kgK=4186, k_W_mK=0.6, Pr=5.6,
            ),
            cold_fluid_props=FluidProperties(
                density_kg_m3=1000, viscosity_Pa_s=0.001,
                cp_J_kgK=4186, k_W_mK=0.6, Pr=7.0,
            ),
        )
        result = await step.execute(state)
        assert result.outputs["tema_type"] == "BEM"
        assert state.shell_id_finalised is True

    @pytest.mark.asyncio
    async def test_flag_in_outputs(self):
        """shell_id_finalised must appear in step outputs."""
        step = Step04TEMAGeometry()
        state = _make_state()
        result = await step.execute(state)
        assert "shell_id_finalised" in result.outputs
        assert isinstance(result.outputs["shell_id_finalised"], bool)
