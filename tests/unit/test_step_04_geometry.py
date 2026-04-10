"""Tests for Piece 6: Initial Geometry Heuristics."""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import DesignState, FluidProperties, GeometrySpec
from hx_engine.app.steps.step_04_tema_geometry import _select_initial_geometry


def _make_state(**overrides) -> DesignState:
    defaults = dict(
        hot_fluid_name="water",
        cold_fluid_name="water",
        T_hot_in_C=90.0,
        T_hot_out_C=60.0,
        T_cold_in_C=30.0,
        T_cold_out_C=50.0,
        P_hot_Pa=101325,
        P_cold_Pa=101325,
        hot_fluid_props=FluidProperties(
            density_kg_m3=1000, viscosity_Pa_s=0.001,
            cp_J_kgK=4186, k_W_mK=0.6, Pr=7.0,
        ),
        cold_fluid_props=FluidProperties(
            density_kg_m3=1000, viscosity_Pa_s=0.001,
            cp_J_kgK=4186, k_W_mK=0.6, Pr=7.0,
        ),
        Q_W=1_000_000,
    )
    defaults.update(overrides)
    return DesignState(**defaults)


class TestInitialGeometry:
    def test_default_tube_od_19mm(self):
        """Standard case → tube_od=0.01905."""
        state = _make_state()
        geom, warnings = _select_initial_geometry(state, "BEM", "cold")
        assert abs(geom.tube_od_m - 0.01905) < 1e-6

    def test_viscous_fluid_25mm_tube(self):
        """Very viscous fluid (μ>0.05) → tube_od=0.0254."""
        state = _make_state(
            hot_fluid_props=FluidProperties(
                density_kg_m3=900, viscosity_Pa_s=0.1,
                cp_J_kgK=2000, k_W_mK=0.15, Pr=500.0,
            ),
        )
        geom, warnings = _select_initial_geometry(state, "AES", "cold")
        assert abs(geom.tube_od_m - 0.0254) < 1e-6

    def test_tube_id_from_bwg(self):
        """OD=0.01905 → ID matches BWG 14 (≈0.01483)."""
        state = _make_state()
        geom, warnings = _select_initial_geometry(state, "BEM", "cold")
        assert abs(geom.tube_id_m - 0.014834) < 0.0001

    def test_fouling_square_pitch(self):
        """Fouling service → pitch_layout='square'."""
        state = _make_state(
            hot_fluid_name="crude oil",
            T_hot_in_C=200, T_hot_out_C=100,
        )
        geom, warnings = _select_initial_geometry(state, "AES", "cold")
        assert geom.pitch_layout == "square"

    def test_clean_triangular_pitch(self):
        """Clean-clean service → pitch_layout='triangular'."""
        state = _make_state()
        geom, warnings = _select_initial_geometry(state, "BEM", "cold")
        assert geom.pitch_layout == "triangular"

    def test_default_tube_length_4877(self):
        """Medium duty → tube_length=4.877m (16 ft)."""
        state = _make_state(Q_W=2_000_000)
        geom, warnings = _select_initial_geometry(state, "BEM", "cold")
        assert abs(geom.tube_length_m - 4.877) < 0.001

    def test_small_duty_shorter_tubes(self):
        """Q < 500 kW → tube_length=3.66m (12 ft)."""
        state = _make_state(Q_W=200_000)
        geom, warnings = _select_initial_geometry(state, "BEM", "cold")
        assert abs(geom.tube_length_m - 3.66) < 0.001

    def test_large_duty_longer_tubes(self):
        """Q > 10 MW → tube_length=6.096m (20 ft)."""
        state = _make_state(Q_W=15_000_000)
        geom, warnings = _select_initial_geometry(state, "AES", "cold")
        assert abs(geom.tube_length_m - 6.096) < 0.001

    def test_default_2_passes(self):
        """Standard case → n_passes=2."""
        state = _make_state()
        geom, warnings = _select_initial_geometry(state, "BEM", "cold")
        assert geom.n_passes == 2

    def test_baffle_cut_025(self):
        """Any case → baffle_cut=0.25."""
        state = _make_state()
        geom, warnings = _select_initial_geometry(state, "BEM", "cold")
        assert abs(geom.baffle_cut - 0.25) < 1e-6

    def test_all_geometry_fields_populated(self):
        """Full run → every GeometrySpec field is not None."""
        state = _make_state()
        geom, warnings = _select_initial_geometry(state, "BEM", "cold")
        assert geom.tube_od_m is not None
        assert geom.tube_id_m is not None
        assert geom.tube_length_m is not None
        assert geom.pitch_ratio is not None
        assert geom.pitch_layout is not None
        assert geom.n_tubes is not None
        assert geom.n_passes is not None
        assert geom.shell_passes is not None
        assert geom.shell_diameter_m is not None
        assert geom.baffle_cut is not None
        assert geom.baffle_spacing_m is not None

    def test_geometry_passes_pydantic_validators(self):
        """Output GeometrySpec passes all CG3A validators."""
        state = _make_state()
        geom, warnings = _select_initial_geometry(state, "BEM", "cold")
        # If it constructed without error, validators passed
        # Double-check by re-validating
        validated = GeometrySpec.model_validate(geom.model_dump())
        assert validated.tube_od_m == geom.tube_od_m
