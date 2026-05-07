"""Integration tests for Step 13 — Vibration Check.

End-to-end tests with a Serth Example 5.1–like DesignState with converged
geometry and liquid shell-side fluid. Verifies:
  - All 4 vibration mechanism scores present per span
  - 3 spans (inlet / central / outlet)
  - Acoustic resonance N/A for liquid service
  - vibration_safe written to state
"""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_13_vibration import Step13VibrationCheck


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _serth_converged_state(**overrides) -> DesignState:
    """Serth Example 5.1–like geometry that has passed Step 12 convergence.

    Shell-side fluid is crude oil (liquid) so acoustic resonance is N/A.
    """
    defaults = dict(
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=55.0,
        T_mean_hot_C=120.0,
        T_mean_cold_C=42.5,
        shell_side_fluid="hot",
        hot_fluid_name="crude oil",
        cold_fluid_name="water",
        m_dot_hot_kg_s=10.0,
        m_dot_cold_kg_s=12.0,
        convergence_converged=True,
        convergence_iteration=5,
        tube_material="carbon_steel",
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
            density_kg_m3=850.0,
            viscosity_Pa_s=0.001,
            cp_J_kgK=2100.0,
            k_W_mK=0.13,
            Pr=16.1,
        ),
        cold_fluid_props=FluidProperties(
            density_kg_m3=995.0,
            viscosity_Pa_s=0.0008,
            cp_J_kgK=4180.0,
            k_W_mK=0.62,
            Pr=5.4,
        ),
    )
    defaults.update(overrides)
    return DesignState(**defaults)


@pytest.fixture
def step():
    return Step13VibrationCheck()


@pytest.fixture
def converged_state():
    return _serth_converged_state()


# ---------------------------------------------------------------------------
# T13.1 — Basic execution
# ---------------------------------------------------------------------------

class TestBasicExecution:
    """T13.1 — Step executes and populates state."""

    @pytest.mark.asyncio
    async def test_returns_step_result(self, step, converged_state):
        result = await step.execute(converged_state)
        assert isinstance(result, StepResult)
        assert result.step_id == 13

    @pytest.mark.asyncio
    async def test_vibration_safe_written_to_state(self, step, converged_state):
        assert converged_state.vibration_safe is None
        await step.execute(converged_state)
        assert converged_state.vibration_safe is not None

    @pytest.mark.asyncio
    async def test_vibration_details_written_to_state(self, step, converged_state):
        assert converged_state.vibration_details is None
        await step.execute(converged_state)
        assert converged_state.vibration_details is not None


# ---------------------------------------------------------------------------
# T13.2 — Span structure
# ---------------------------------------------------------------------------

class TestSpanStructure:
    """T13.2 — vibration_details.spans covers 3 baffle spans."""

    @pytest.mark.asyncio
    async def test_three_spans_present(self, step, converged_state):
        await step.execute(converged_state)
        spans = converged_state.vibration_details.get("spans", {})
        assert len(spans) == 3, f"Expected 3 spans, got {len(spans)}: {list(spans.keys())}"

    @pytest.mark.asyncio
    async def test_span_names_are_inlet_central_outlet(self, step, converged_state):
        await step.execute(converged_state)
        span_keys = set(converged_state.vibration_details.get("spans", {}).keys())
        assert span_keys == {"inlet", "central", "outlet"}

    @pytest.mark.asyncio
    async def test_each_span_has_four_mechanism_scores(self, step, converged_state):
        """Every span must carry fluidelastic, vortex, turbulent, acoustic."""
        await step.execute(converged_state)
        spans = converged_state.vibration_details["spans"]
        required = {"fluidelastic", "vortex_shedding", "turbulent_buffeting", "acoustic_resonance"}
        for span_name, span_data in spans.items():
            present = set(span_data.keys())
            missing = required - present
            assert not missing, (
                f"Span '{span_name}' missing mechanism keys: {missing}"
            )


# ---------------------------------------------------------------------------
# T13.3 — Liquid service acoustic resonance
# ---------------------------------------------------------------------------

class TestLiquidServiceAcoustic:
    """T13.3 — Acoustic resonance is N/A (not applicable) for liquid shell side."""

    @pytest.mark.asyncio
    async def test_acoustic_resonance_not_applicable_for_liquid(self, step, converged_state):
        await step.execute(converged_state)
        details = converged_state.vibration_details
        # Top-level acoustic_resonance field
        acoustic = details.get("acoustic_resonance")
        assert acoustic is not None
        # For liquid service the acoustic check should report not-applicable
        applicable = acoustic.get("applicable", True)
        assert applicable is False, (
            f"Expected acoustic resonance not applicable for liquid service, "
            f"got applicable={applicable}"
        )


# ---------------------------------------------------------------------------
# T13.4 — Output dict
# ---------------------------------------------------------------------------

class TestOutputDict:
    """T13.4 — StepResult.outputs mirrors state."""

    @pytest.mark.asyncio
    async def test_vibration_safe_in_outputs(self, step, converged_state):
        result = await step.execute(converged_state)
        assert "vibration_safe" in result.outputs

    @pytest.mark.asyncio
    async def test_vibration_details_in_outputs(self, step, converged_state):
        result = await step.execute(converged_state)
        assert "vibration_details" in result.outputs
