"""Tests for Piece 9: AI Escalation Logic."""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import DesignState, FluidProperties
from hx_engine.app.steps.step_04_tema_geometry import (
    Step04TEMAGeometry,
    _build_escalation_hints,
)


def _make_state(**overrides) -> DesignState:
    defaults = dict(
        hot_fluid_name="water",
        cold_fluid_name="water",
        T_hot_in_C=80.0,
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


class TestEscalationHints:
    def test_no_escalation_clear_choice(self):
        """Clear-cut BEM case → no escalation hints."""
        state = _make_state()
        hints = _build_escalation_hints(state, "BEM", "cold", "test")
        assert len(hints) == 0

    def test_escalation_user_conflict(self):
        """User wants BEM but ΔT=80°C → hint set."""
        state = _make_state(
            tema_class="BEM",
            T_hot_in_C=150, T_hot_out_C=90,
            T_cold_in_C=30, T_cold_out_C=70,
        )
        hints = _build_escalation_hints(state, "BEM", "cold", "test")
        triggers = [h["trigger"] for h in hints]
        assert "user_preference_conflict" in triggers

    def test_escalation_both_fouling(self):
        """Both fluids foul → hint set."""
        state = _make_state(
            hot_fluid_name="crude oil",
            cold_fluid_name="fuel oil",
            T_hot_in_C=200, T_hot_out_C=100,
            T_cold_in_C=30, T_cold_out_C=60,
        )
        hints = _build_escalation_hints(state, "AES", "cold", "test")
        triggers = [h["trigger"] for h in hints]
        assert "both_fluids_fouling" in triggers

    def test_escalation_extreme_pressure(self):
        """P_hot=150 bar → hint set."""
        state = _make_state(P_hot_Pa=150e5)
        hints = _build_escalation_hints(state, "AEW", "cold", "test")
        triggers = [h["trigger"] for h in hints]
        assert "extreme_pressure" in triggers

    def test_escalation_small_duty(self):
        """Q=20 kW → hint about double-pipe."""
        state = _make_state(Q_W=20_000)
        hints = _build_escalation_hints(state, "BEM", "cold", "test")
        triggers = [h["trigger"] for h in hints]
        assert "small_duty" in triggers

    def test_escalation_large_duty(self):
        """Q=100 MW → hint about multi-shell."""
        state = _make_state(Q_W=100_000_000)
        hints = _build_escalation_hints(state, "AES", "cold", "test")
        triggers = [h["trigger"] for h in hints]
        assert "large_duty" in triggers

    def test_hints_are_list_of_dicts(self):
        """Any escalation → hints is a list of dicts with correct keys."""
        state = _make_state(Q_W=20_000)
        hints = _build_escalation_hints(state, "BEM", "cold", "test")
        assert isinstance(hints, list)
        for hint in hints:
            assert isinstance(hint, dict)
            assert "trigger" in hint
            assert "recommendation" in hint

    async def test_escalation_via_execute(self):
        """Escalation hints populated through full execute()."""
        step = Step04TEMAGeometry()
        state = _make_state(
            tema_class="BEM",
            T_hot_in_C=150, T_hot_out_C=90,
            T_cold_in_C=30, T_cold_out_C=70,
        )
        result = await step.execute(state)
        hints = result.outputs.get("escalation_hints", [])
        assert isinstance(hints, list)

    # ---- Fouling-factor uncertainty escalation ----

    def test_escalation_unknown_fluid(self):
        """Unknown fluid → fouling_factor_uncertain hint."""
        state = _make_state(
            hot_fluid_name="phosphoric acid solution",
            cold_fluid_name="water",
        )
        hints = _build_escalation_hints(state, "BEM", "cold", "test")
        triggers = [h["trigger"] for h in hints]
        assert "fouling_factor_uncertain" in triggers
        # The hint should mention the unknown fluid
        uncertain = [h for h in hints if h["trigger"] == "fouling_factor_uncertain"]
        assert any("phosphoric acid" in h["recommendation"] for h in uncertain)

    def test_escalation_location_dependent_fluid(self):
        """River water → fouling_factor_uncertain (location-dependent)."""
        state = _make_state(
            hot_fluid_name="water",
            cold_fluid_name="river water",
        )
        hints = _build_escalation_hints(state, "BEM", "cold", "test")
        triggers = [h["trigger"] for h in hints]
        assert "fouling_factor_uncertain" in triggers

    def test_no_fouling_escalation_for_known_stable(self):
        """Gasoline + methanol → no fouling_factor_uncertain hint."""
        state = _make_state(
            hot_fluid_name="gasoline",
            cold_fluid_name="methanol",
        )
        hints = _build_escalation_hints(state, "BEM", "cold", "test")
        triggers = [h["trigger"] for h in hints]
        assert "fouling_factor_uncertain" not in triggers

    async def test_fouling_metadata_in_execute_output(self):
        """execute() includes fouling_metadata in outputs."""
        step = Step04TEMAGeometry()
        state = _make_state()
        result = await step.execute(state)
        meta = result.outputs.get("fouling_metadata")
        assert meta is not None
        assert "hot" in meta
        assert "cold" in meta
        assert "rf" in meta["hot"]
        assert "needs_ai" in meta["hot"]

    async def test_fouling_metadata_flags_unknown(self):
        """Unknown fluid in execute → fouling_metadata flags uncertainty.

        When the AI is available, the 3-tier resolver succeeds with
        source='ai' and needs_ai=False but needs_user_confirmation=True
        (confidence < 0.7). When the AI is NOT available, the fallback
        preserves needs_ai=True from the table lookup.
        Either way, the metadata must indicate uncertainty.
        """
        step = Step04TEMAGeometry()
        state = _make_state(hot_fluid_name="molten polymer resin")
        result = await step.execute(state)
        meta = result.outputs["fouling_metadata"]
        hot_meta = meta["hot"]
        # The fluid is unknown — uncertainty must be flagged one way or another
        is_uncertain = (
            hot_meta.get("needs_ai") is True
            or hot_meta.get("needs_user_confirmation") is True
        )
        assert is_uncertain, (
            f"Expected uncertainty flag for unknown fluid, got: {hot_meta}"
        )
        # Source should be either 'ai_recommended' (no API) or 'ai' (API worked)
        assert hot_meta["source"] in ("ai_recommended", "ai")
