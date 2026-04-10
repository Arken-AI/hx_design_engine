"""Tests for Piece 4: Fluid Allocation Logic."""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import DesignState, FluidProperties
from hx_engine.app.steps.step_04_tema_geometry import _allocate_fluids


def _make_state(**overrides) -> DesignState:
    """Build a minimal state for allocation tests."""
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


class TestFluidAllocation:
    def test_high_pressure_to_tube(self):
        """P_hot=50 bar, P_cold=2 bar → hot fluid tube-side → shell_side='cold'."""
        state = _make_state(P_hot_Pa=50e5, P_cold_Pa=2e5)
        shell_side, warnings = _allocate_fluids(state)
        assert shell_side == "cold"  # hot goes tube-side

    def test_fouling_to_tube(self):
        """Hot=crude oil, Cold=water → crude shell-side (AES cleaning access)."""
        state = _make_state(
            hot_fluid_name="crude oil",
            T_hot_in_C=200, T_hot_out_C=100,
        )
        shell_side, warnings = _allocate_fluids(state)
        # Crude/heavy oil → shell-side for AES bundle removal (Rule 2.5)
        assert shell_side == "hot"

    def test_viscous_to_shell(self):
        """Hot μ=0.001, Cold μ=0.5 Pa·s → cold shell-side (for baffles)."""
        state = _make_state(
            hot_fluid_name="gasoline",
            cold_fluid_name="ethylene glycol",
            cold_fluid_props=FluidProperties(
                density_kg_m3=1100, viscosity_Pa_s=0.5,
                cp_J_kgK=2400, k_W_mK=0.25, Pr=50.0,
            ),
        )
        shell_side, warnings = _allocate_fluids(state)
        # Cold is very viscous → shell-side for baffle turbulence
        assert shell_side == "cold"

    def test_fouling_overrides_viscosity(self):
        """Hot=crude(fouling+viscous), Cold=water → crude shell-side (AES cleaning)."""
        state = _make_state(
            hot_fluid_name="crude oil",
            T_hot_in_C=200, T_hot_out_C=100,
            hot_fluid_props=FluidProperties(
                density_kg_m3=850, viscosity_Pa_s=0.05,
                cp_J_kgK=2000, k_W_mK=0.13, Pr=770.0,
            ),
        )
        shell_side, warnings = _allocate_fluids(state)
        # Crude/heavy oil → shell-side (AES cleaning, Rule 2.5 overrides viscosity)
        assert shell_side == "hot"

    def test_high_pressure_overrides_fouling(self):
        """Hot: 100 bar+clean, Cold: 2 bar+fouling → hot tube-side."""
        state = _make_state(
            hot_fluid_name="water",
            cold_fluid_name="crude oil",
            P_hot_Pa=100e5,
            P_cold_Pa=2e5,
            T_cold_in_C=100, T_cold_out_C=50,
        )
        shell_side, warnings = _allocate_fluids(state)
        assert shell_side == "cold"  # hot goes tube-side (pressure wins)

    def test_both_clean_low_pressure_hot_tube(self):
        """Both clean, similar pressure → hot fluid tube-side (default)."""
        state = _make_state()
        shell_side, warnings = _allocate_fluids(state)
        assert shell_side == "cold"  # default: hot on tube

    def test_symmetric_case(self):
        """Same fluid both sides → default hot tube-side (deterministic)."""
        state = _make_state()
        shell_side, warnings = _allocate_fluids(state)
        assert shell_side == "cold"

    def test_user_preference_respected(self):
        """User specifies allocation via tema_preference."""
        state = _make_state(
            tema_preference="hot fluid tube-side",
        )
        shell_side, warnings = _allocate_fluids(state)
        assert shell_side == "cold"

    def test_returns_warnings_for_conflicts(self):
        """Fouling fluid (non-crude) + viscous → conflict warning.

        Use a non-crude heavy-fouling fluid so Rule 2.5 (crude→shell) does
        not pre-empt Rule 3.  The fluid must be viscous enough (>0.01 Pa·s)
        AND classified as heavy/severe fouling so the conflict path fires.
        """
        state = _make_state(
            hot_fluid_name="vegetable oil",
            cold_fluid_name="water",
            T_hot_in_C=200, T_hot_out_C=100,
            hot_fluid_props=FluidProperties(
                density_kg_m3=920, viscosity_Pa_s=0.05,
                cp_J_kgK=2000, k_W_mK=0.17, Pr=590.0,
            ),
        )
        _shell_side, warnings = _allocate_fluids(state)
        conflict_warnings = [w for w in warnings if "Conflict" in w or "conflict" in w]
        assert len(conflict_warnings) >= 1

    def test_extreme_pressure_difference(self):
        """P_hot=200 bar, P_cold=1 bar → hot tube-side."""
        state = _make_state(P_hot_Pa=200e5, P_cold_Pa=1e5)
        shell_side, warnings = _allocate_fluids(state)
        assert shell_side == "cold"
