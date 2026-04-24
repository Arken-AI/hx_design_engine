"""Tests for Piece 5: TEMA Type Selection Logic."""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import DesignState, FluidProperties
from hx_engine.app.steps.step_04_tema_geometry import _select_tema_type


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


class TestTEMATypeSelection:
    def test_clean_clean_low_dt_BEM(self):
        """Water(40→55) + water(70→55), ΔT=30°C → BEM."""
        state = _make_state(
            T_hot_in_C=70, T_hot_out_C=55,
            T_cold_in_C=40, T_cold_out_C=55,
        )
        tema, reasoning, warnings = _select_tema_type(state, "cold")
        assert tema == "BEM"

    def test_high_dt_clean_tube_AEU(self):
        """ΔT=80°C, tube-side fluid clean → AEU."""
        state = _make_state(
            T_hot_in_C=150, T_hot_out_C=90,
            T_cold_in_C=30, T_cold_out_C=70,
        )
        # shell_side="cold" means hot goes tube-side (water = clean)
        tema, reasoning, warnings = _select_tema_type(state, "cold")
        assert tema == "AEU"

    def test_high_dt_fouling_tube_AES(self):
        """ΔT=80°C, tube-side fluid fouls → AES."""
        state = _make_state(
            hot_fluid_name="crude oil",
            T_hot_in_C=200, T_hot_out_C=100,
            T_cold_in_C=30, T_cold_out_C=70,
        )
        # shell_side="cold" means hot (crude) goes tube-side → fouls
        tema, reasoning, warnings = _select_tema_type(state, "cold")
        assert tema == "AES"

    def test_low_dt_one_fouling_AES_or_AEP(self):
        """ΔT=30°C, one fluid fouls heavily → AES or AEP."""
        state = _make_state(
            hot_fluid_name="crude oil",
            T_hot_in_C=200, T_hot_out_C=180,
            T_cold_in_C=170, T_cold_out_C=190,
        )
        tema, reasoning, warnings = _select_tema_type(state, "cold")
        assert tema in ("AES", "AEP")

    def test_very_high_pressure_AEW(self):
        """P=150 bar, ΔT=80°C → AEW."""
        state = _make_state(
            T_hot_in_C=150, T_hot_out_C=90,
            T_cold_in_C=30, T_cold_out_C=70,
            P_hot_Pa=150e5,
        )
        tema, reasoning, warnings = _select_tema_type(state, "cold")
        assert tema == "AEW"

    def test_user_preference_respected(self):
        """User says 'BEM' for low ΔT → BEM selected."""
        state = _make_state(
            tema_class="BEM",
            T_hot_in_C=80, T_hot_out_C=65,
            T_cold_in_C=30, T_cold_out_C=50,
        )
        tema, reasoning, warnings = _select_tema_type(state, "cold")
        assert tema == "BEM"

    def test_user_preference_conflict_warns(self):
        """User says 'BEM' but ΔT=80°C → BEM + warning."""
        state = _make_state(
            tema_class="BEM",
            T_hot_in_C=150, T_hot_out_C=90,
            T_cold_in_C=30, T_cold_out_C=70,
        )
        tema, reasoning, warnings = _select_tema_type(state, "cold")
        assert tema == "BEM"
        assert any("BEM" in w and "ΔT" in w for w in warnings)

    def test_small_duty_warns(self):
        """Q=20 kW → TEMA type + 'consider double-pipe' warning."""
        state = _make_state(Q_W=20_000)
        tema, reasoning, warnings = _select_tema_type(state, "cold")
        assert any("double-pipe" in w for w in warnings)

    def test_large_duty_warns(self):
        """Q=100 MW → TEMA type + 'multi-shell' warning."""
        state = _make_state(Q_W=100_000_000)
        tema, reasoning, warnings = _select_tema_type(state, "cold")
        assert any("multiple shells" in w.lower() or "multi-shell" in w.lower()
                    for w in warnings)

    def test_both_fouling_heavy_AES_square(self):
        """Both fluids foul heavily → AES + square pitch note."""
        state = _make_state(
            hot_fluid_name="crude oil",
            cold_fluid_name="fuel oil",
            T_hot_in_C=220, T_hot_out_C=180,
            T_cold_in_C=130, T_cold_out_C=170,
        )
        tema, reasoning, warnings = _select_tema_type(state, "cold")
        assert tema == "AES"
        assert any("square" in w.lower() for w in warnings)

    def test_delta_T_exactly_50_boundary(self):
        """Tubesheet ΔT = 50°C → BEM (boundary exclusive).  P2-14 semantics:
        decision is driven by |T_shell_mean − T_tube_mean|, not stream span."""
        # Hot mean = 110, cold mean = 60 → |110−60| = 50 K
        state = _make_state(
            T_hot_in_C=115, T_hot_out_C=105,
            T_cold_in_C=50, T_cold_out_C=70,
        )
        tema, reasoning, warnings = _select_tema_type(state, "cold")
        assert tema == "BEM"

    def test_delta_T_51_requires_floating(self):
        """Tubesheet ΔT = 51°C → not BEM (just above threshold).  P2-14 semantics."""
        # Hot mean = 110, cold mean = 59 → |110−59| = 51 K
        state = _make_state(
            T_hot_in_C=115, T_hot_out_C=105,
            T_cold_in_C=50, T_cold_out_C=68,
        )
        tema, reasoning, warnings = _select_tema_type(state, "cold")
        assert tema != "BEM"

    def test_reasoning_is_populated(self):
        """Any valid case → reasoning string non-empty."""
        state = _make_state()
        tema, reasoning, warnings = _select_tema_type(state, "cold")
        assert len(reasoning) > 0

    def test_corrosive_fluid_notes_material(self):
        """Corrosive fluid → warning about material selection."""
        state = _make_state(hot_fluid_name="hydrochloric acid")
        tema, reasoning, warnings = _select_tema_type(state, "cold")
        assert any("corrosive" in w.lower() or "material" in w.lower()
                    for w in warnings)
