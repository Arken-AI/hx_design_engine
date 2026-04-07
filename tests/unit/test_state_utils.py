"""Tests for state_utils.apply_outputs — extracted from PipelineRunner.

Validates:
  - Same field mapping behaviour as before extraction
  - Geometry dict → GeometrySpec conversion
  - FluidProperties dict → FluidProperties conversion
"""

from __future__ import annotations

import pytest

from hx_engine.app.core.state_utils import apply_outputs
from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.models.step_result import StepResult


class TestApplyOutputsScalar:
    def test_scalar_fields_applied(self):
        state = DesignState()
        result = StepResult(
            step_id=2,
            step_name="Heat Duty",
            outputs={
                "Q_W": 6_300_000.0,
                "LMTD_K": 75.0,
                "T_hot_in_C": 150.0,
            },
        )
        apply_outputs(state, result)
        assert state.Q_W == 6_300_000.0
        assert state.LMTD_K == 75.0
        assert state.T_hot_in_C == 150.0

    def test_unknown_keys_ignored(self):
        state = DesignState()
        result = StepResult(
            step_id=99,
            step_name="Test",
            outputs={"nonexistent_field": 42},
        )
        # Should not raise
        apply_outputs(state, result)

    def test_step_10_pressure_drops(self):
        state = DesignState()
        result = StepResult(
            step_id=10,
            step_name="Pressure Drops",
            outputs={
                "dP_tube_Pa": 45000.0,
                "dP_shell_Pa": 95000.0,
                "dP_tube_friction_Pa": 30000.0,
            },
        )
        apply_outputs(state, result)
        assert state.dP_tube_Pa == 45000.0
        assert state.dP_shell_Pa == 95000.0
        assert state.dP_tube_friction_Pa == 30000.0

    def test_step_12_convergence_fields(self):
        state = DesignState()
        result = StepResult(
            step_id=12,
            step_name="Convergence",
            outputs={
                "convergence_iteration": 5,
                "convergence_converged": True,
                "convergence_restart_count": 0,
            },
        )
        apply_outputs(state, result)
        assert state.convergence_iteration == 5
        assert state.convergence_converged is True


class TestApplyOutputsGeometry:
    def test_geometry_dict_to_spec(self):
        state = DesignState()
        result = StepResult(
            step_id=4,
            step_name="TEMA",
            outputs={
                "geometry": {
                    "tube_od_m": 0.01905,
                    "tube_id_m": 0.01483,
                    "tube_length_m": 4.88,
                    "pitch_ratio": 1.25,
                    "pitch_layout": "triangular",
                    "n_passes": 2,
                    "shell_passes": 1,
                    "baffle_cut": 0.25,
                    "baffle_spacing_m": 0.15,
                    "shell_diameter_m": 0.489,
                    "n_tubes": 158,
                },
            },
        )
        apply_outputs(state, result)
        assert isinstance(state.geometry, GeometrySpec)
        assert state.geometry.n_tubes == 158
        assert state.geometry.tube_od_m == 0.01905

    def test_geometry_spec_passthrough(self):
        state = DesignState()
        spec = GeometrySpec(
            tube_od_m=0.01905,
            tube_id_m=0.01483,
            n_tubes=100,
            n_passes=2,
            pitch_layout="triangular",
            shell_diameter_m=0.3,
            baffle_spacing_m=0.1,
        )
        result = StepResult(
            step_id=4,
            step_name="TEMA",
            outputs={"geometry": spec},
        )
        apply_outputs(state, result)
        assert state.geometry is spec


class TestApplyOutputsFluidProps:
    def test_fluid_props_dict(self):
        state = DesignState()
        result = StepResult(
            step_id=3,
            step_name="Fluid Props",
            outputs={
                "hot_fluid_props": {
                    "density_kg_m3": 820.0,
                    "viscosity_Pa_s": 0.00052,
                    "cp_J_kgK": 2200.0,
                    "k_W_mK": 0.138,
                    "Pr": 8.29,
                },
            },
        )
        apply_outputs(state, result)
        assert isinstance(state.hot_fluid_props, FluidProperties)
        assert state.hot_fluid_props.density_kg_m3 == 820.0

    def test_fluid_props_object(self):
        state = DesignState()
        props = FluidProperties(
            density_kg_m3=988.0,
            viscosity_Pa_s=0.000547,
            cp_J_kgK=4181.0,
            k_W_mK=0.644,
            Pr=3.55,
        )
        result = StepResult(
            step_id=3,
            step_name="Fluid Props",
            outputs={"cold_fluid_props": props},
        )
        apply_outputs(state, result)
        assert state.cold_fluid_props is props
