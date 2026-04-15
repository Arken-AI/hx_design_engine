"""Tests for Piece 1: DesignState, FluidProperties, GeometrySpec."""

import pytest
from pydantic import ValidationError

from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)


# ===== GeometrySpec CG3A tests =====

class TestGeometrySpec:

    def test_baffle_spacing_valid(self):
        g = GeometrySpec(baffle_spacing_m=0.127)
        assert g.baffle_spacing_m == 0.127

    def test_baffle_spacing_below_min(self):
        with pytest.raises(ValidationError, match="baffle_spacing_m"):
            GeometrySpec(baffle_spacing_m=0.02)

    def test_baffle_spacing_above_max(self):
        with pytest.raises(ValidationError, match="baffle_spacing_m"):
            GeometrySpec(baffle_spacing_m=3.0)

    def test_baffle_spacing_none_accepted(self):
        g = GeometrySpec(baffle_spacing_m=None)
        assert g.baffle_spacing_m is None

    def test_pitch_ratio_valid(self):
        g = GeometrySpec(pitch_ratio=1.333)
        assert g.pitch_ratio == 1.333

    def test_pitch_ratio_below_min(self):
        with pytest.raises(ValidationError, match="pitch_ratio"):
            GeometrySpec(pitch_ratio=1.1)

    def test_pitch_ratio_above_max(self):
        with pytest.raises(ValidationError, match="pitch_ratio"):
            GeometrySpec(pitch_ratio=1.6)

    def test_shell_diameter_valid(self):
        g = GeometrySpec(shell_diameter_m=0.59)
        assert g.shell_diameter_m == 0.59

    def test_shell_diameter_below_min(self):
        with pytest.raises(ValidationError, match="shell_diameter_m"):
            GeometrySpec(shell_diameter_m=0.01)

    def test_tube_od_valid(self):
        g = GeometrySpec(tube_od_m=0.019)
        assert g.tube_od_m == 0.019

    def test_tube_od_below_min(self):
        with pytest.raises(ValidationError, match="tube_od_m"):
            GeometrySpec(tube_od_m=0.001)

    def test_baffle_cut_valid(self):
        g = GeometrySpec(baffle_cut=0.25)
        assert g.baffle_cut == 0.25

    def test_baffle_cut_below_min(self):
        with pytest.raises(ValidationError, match="baffle_cut"):
            GeometrySpec(baffle_cut=0.10)

    def test_baffle_cut_above_max(self):
        with pytest.raises(ValidationError, match="baffle_cut"):
            GeometrySpec(baffle_cut=0.50)

    def test_tube_id_less_than_od(self):
        g = GeometrySpec(tube_od_m=0.019, tube_id_m=0.015)
        assert g.tube_id_m < g.tube_od_m

    def test_tube_id_ge_od_rejected(self):
        with pytest.raises(ValidationError, match="tube_id_m"):
            GeometrySpec(tube_od_m=0.019, tube_id_m=0.020)


# ===== FluidProperties tests =====

class TestFluidProperties:

    def test_valid_properties(self):
        fp = FluidProperties(
            density_kg_m3=998.0,
            viscosity_Pa_s=0.001,
            cp_J_kgK=4181.0,
            k_W_mK=0.6,
            Pr=7.0,
        )
        assert fp.density_kg_m3 == 998.0

    def test_negative_density_rejected(self):
        with pytest.raises(ValidationError, match="density_kg_m3"):
            FluidProperties(density_kg_m3=-100)

    def test_density_below_range(self):
        with pytest.raises(ValidationError, match="density_kg_m3"):
            FluidProperties(density_kg_m3=0.001)

    def test_viscosity_above_range(self):
        with pytest.raises(ValidationError, match="viscosity_Pa_s"):
            FluidProperties(viscosity_Pa_s=5.0)

    def test_all_none_accepted(self):
        fp = FluidProperties()
        assert fp.density_kg_m3 is None


# ===== DesignState tests =====

class TestDesignState:

    def test_session_id_auto_generated(self):
        s = DesignState()
        assert s.session_id  # non-empty UUID string
        assert len(s.session_id) == 36  # UUID4 format

    def test_default_factory_isolation(self):
        s1 = DesignState()
        s2 = DesignState()
        assert s1.step_records is not s2.step_records
        assert s1.warnings is not s2.warnings
        assert s1.completed_steps is not s2.completed_steps

    def test_round_trip_json(self):
        s = DesignState(
            raw_request="test",
            T_hot_in_C=150.0,
            T_hot_out_C=90.0,
            T_cold_in_C=30.0,
            m_dot_hot_kg_s=50.0,
            hot_fluid_name="crude oil",
            cold_fluid_name="water",
        )
        json_str = s.model_dump_json()
        s2 = DesignState.model_validate_json(json_str)
        assert s2.T_hot_in_C == 150.0
        assert s2.hot_fluid_name == "crude oil"
        assert s2.session_id == s.session_id

    def test_shell_id_finalised_defaults_false(self):
        s = DesignState()
        assert s.shell_id_finalised is False

    def test_shell_id_finalised_round_trip(self):
        s = DesignState(shell_id_finalised=True)
        assert s.shell_id_finalised is True
        s2 = DesignState.model_validate_json(s.model_dump_json())
        assert s2.shell_id_finalised is True

    def test_area_uncertainty_fields_default_none(self):
        s = DesignState()
        assert s.A_required_low_m2 is None
        assert s.A_required_high_m2 is None

    def test_design_strengths_risks_default_empty(self):
        s = DesignState()
        assert s.design_strengths == []
        assert s.design_risks == []
