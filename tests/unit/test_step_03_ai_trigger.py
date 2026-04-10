"""Tests for Piece 4: _conditional_ai_trigger() — AI invocation logic."""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import DesignState, FluidProperties
from hx_engine.app.steps.step_03_fluid_props import Step03FluidProperties


def _make_state(in_convergence: bool = False) -> DesignState:
    return DesignState(
        hot_fluid_name="crude oil",
        cold_fluid_name="ethanol",
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=60.0,
        in_convergence_loop=in_convergence,
    )


def _normal_hot() -> FluidProperties:
    return FluidProperties(
        density_kg_m3=850.0, viscosity_Pa_s=0.002,
        cp_J_kgK=2000.0, k_W_mK=0.13, Pr=30.77,
    )


def _normal_cold() -> FluidProperties:
    return FluidProperties(
        density_kg_m3=780.0, viscosity_Pa_s=0.001,
        cp_J_kgK=2500.0, k_W_mK=0.16, Pr=15.63,
    )


class TestConditionalAITrigger:
    """Six tests guarding AI trigger logic for CONDITIONAL mode."""

    def test_normal_fluids_no_trigger(self):
        """Normal crude oil + ethanol (typical Pr) → no AI call."""
        step = Step03FluidProperties()
        step._hot_props = _normal_hot()
        step._cold_props = _normal_cold()

        assert step._conditional_ai_trigger(_make_state()) is False

    def test_low_pr_triggers(self):
        """Hot Pr=0.6 (just above Pydantic min) → triggers AI.

        Liquid metals / extreme gases warrant expert review.
        """
        step = Step03FluidProperties()
        step._hot_props = FluidProperties(
            density_kg_m3=850.0, viscosity_Pa_s=0.001,
            cp_J_kgK=1000.0, k_W_mK=1.67, Pr=0.6,
        )
        step._cold_props = _normal_cold()

        assert step._conditional_ai_trigger(_make_state()) is True

    def test_high_pr_triggers(self):
        """Cold Pr=600 (very viscous fluid) → triggers AI.

        High Pr fluids need careful correlation selection.
        """
        step = Step03FluidProperties()
        step._hot_props = _normal_hot()
        step._cold_props = FluidProperties(
            density_kg_m3=900.0, viscosity_Pa_s=0.5,
            cp_J_kgK=2000.0, k_W_mK=0.13, Pr=600.0,
        )

        assert step._conditional_ai_trigger(_make_state()) is True

    def test_extreme_viscosity_ratio_triggers(self):
        """Hot μ=0.5, cold μ=0.001 → 500:1 ratio triggers AI."""
        step = Step03FluidProperties()
        step._hot_props = FluidProperties(
            density_kg_m3=900.0, viscosity_Pa_s=0.5,
            cp_J_kgK=2000.0, k_W_mK=0.13, Pr=30.0,
        )
        step._cold_props = FluidProperties(
            density_kg_m3=780.0, viscosity_Pa_s=0.001,
            cp_J_kgK=2500.0, k_W_mK=0.16, Pr=15.0,
        )

        assert step._conditional_ai_trigger(_make_state()) is True

    def test_both_sides_normal_no_trigger(self):
        """Both sides in normal range → no AI call."""
        step = Step03FluidProperties()
        step._hot_props = _normal_hot()
        step._cold_props = _normal_cold()

        assert step._conditional_ai_trigger(_make_state()) is False

    def test_convergence_loop_suppresses_trigger(self):
        """Decision 3A: in_convergence_loop = True → skip AI even with anomaly."""
        step = Step03FluidProperties()
        # Set anomalous Pr that would normally trigger
        step._hot_props = FluidProperties(
            density_kg_m3=850.0, viscosity_Pa_s=0.001,
            cp_J_kgK=1000.0, k_W_mK=1.67, Pr=0.6,
        )
        step._cold_props = _normal_cold()

        # BaseStep._should_call_ai checks in_convergence_loop before
        # calling _conditional_ai_trigger, so the trigger won't even run.
        # We test the base class path here.
        state = _make_state(in_convergence=True)
        assert step._should_call_ai(state) is False
