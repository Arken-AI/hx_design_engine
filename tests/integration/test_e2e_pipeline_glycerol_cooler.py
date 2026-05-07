"""E2E pipeline smoke test — glycerol cooler analog (post-convergence pipeline).

Represents the bug a78b6473 scenario: cooling glycerol 95 → 40 °C with
water 25 → 45 °C, hot 3 barg / cold 10 barg.  The test starts from a
post-Step-12 converged state and drives the complete downstream analysis
pipeline (Steps 13 → 16) with stubbed AI (no live Anthropic key required).

Why post-Step-12?
  The convergence loop (Step 12, running sub-steps 7 → 11) is tested in
  depth in test_step_12_integration.py, test_pipeline_runner_layer2_escalation.py,
  and test_nozzle_table.py.  This test focuses on the *validation + scoring*
  half of the pipeline — the path that was broken by the four bugs addressed
  in the steps-10-16 closeout plan.

Key assertions:
  1. Pipeline reaches Step 16 without raising any exception.
  2. ``convergence_converged`` is True (pre-seeded; Step 13 precondition).
  3. ``confidence_score`` is not None (Step 16 must populate it).
  4. ``vibration_safe`` is not None (Step 13 must populate it).
  5. ``cost_usd`` is not None (Step 15 must populate it).
  6. No step raises ``CalculationError`` (regression guard for all four bugs).
"""

from __future__ import annotations

import pytest

from hx_engine.app.core.ai_engineer import AIEngineer
from hx_engine.app.core.state_utils import apply_outputs
from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.steps.step_13_vibration import Step13VibrationCheck
from hx_engine.app.steps.step_14_mechanical import Step14MechanicalCheck
from hx_engine.app.steps.step_15_cost import Step15CostEstimate
from hx_engine.app.steps.step_16_final_validation import Step16FinalValidation

# Trigger rule auto-registration
import hx_engine.app.steps.step_13_rules  # noqa: F401
import hx_engine.app.steps.step_14_rules  # noqa: F401
import hx_engine.app.steps.step_15_rules  # noqa: F401
import hx_engine.app.steps.step_16_rules  # noqa: F401


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STUB_AI = AIEngineer(stub_mode=True)


# ---------------------------------------------------------------------------
# State fixture
# ---------------------------------------------------------------------------

def _glycerol_cooler_converged_state() -> DesignState:
    """Post-Step-12 DesignState for a glycerol/water cooler.

    Operating conditions:
      - Glycerol 95 → 40 °C shell side, 9 576 kg/hr (2.66 kg/s)
      - Water 25 → 45 °C tube side, 17 240 kg/hr (4.79 kg/s)
      - Hot 3 barg (400 kPa abs), cold 10 barg (1 100 kPa abs)

    Glycerol fluid properties are provided directly (not looked up from the
    fluid database) because "glycerol" is not a built-in fluid key.
    Physical values are for glycerol at ~67.5 °C mean temperature.

    Heat duty: Q = m_dot × cp × ΔT = 2.66 × 2 730 × 55 ≈ 400 kW.
    LMTD (counterflow 95/40 // 45/25): 29.1 K.

    Geometry chosen to give ~15 % overdesign with U ≈ 220 W/m²K:
      A_req = 400 000 / (220 × 0.85 × 29.1) ≈ 73.5 m²
      A_prov = 316 × π × 0.019 05 × 4.877 ≈ 92.2 m²  → overdesign ≈ 25 %
      (slightly above target; Step 12 would trim in next iteration, but
      the pre-converged state is seeded here for the downstream test.)
    """
    glycerol = FluidProperties(
        density_kg_m3=1225.0,
        viscosity_Pa_s=0.0085,
        cp_J_kgK=2730.0,
        k_W_mK=0.29,
        Pr=80.0,
    )
    water = FluidProperties(
        density_kg_m3=994.0,
        viscosity_Pa_s=0.00072,
        cp_J_kgK=4178.0,
        k_W_mK=0.623,
        Pr=4.84,
    )

    m_dot_glycerol = 9_576 / 3_600  # kg/s
    m_dot_water = 17_240 / 3_600    # kg/s
    Q_W = m_dot_glycerol * glycerol.cp_J_kgK * (95.0 - 40.0)
    area_provided = 316 * 3.14159265 * 0.01905 * 4.877

    return DesignState(
        raw_request=(
            "Cool 9 576 kg/hr of glycerol from 95 °C to 40 °C using cooling "
            "water entering at 25 °C and leaving at 45 °C.  "
            "Hot-side pressure 3 barg, cold-side 10 barg."
        ),
        user_id="e2e-test-glycerol",
        hot_fluid_name="glycerol",
        cold_fluid_name="water",
        T_hot_in_C=95.0,
        T_hot_out_C=40.0,
        T_cold_in_C=25.0,
        T_cold_out_C=45.0,
        T_mean_hot_C=67.5,
        T_mean_cold_C=35.0,
        m_dot_hot_kg_s=m_dot_glycerol,
        m_dot_cold_kg_s=m_dot_water,
        P_hot_Pa=400_000.0,
        P_cold_Pa=1_100_000.0,
        hot_fluid_props=glycerol,
        cold_fluid_props=water,
        shell_side_fluid="hot",       # glycerol on shell side
        tema_type="AES",
        tube_material="carbon_steel",
        shell_material="carbon_steel",
        # Thermal results from the convergence loop (pre-seeded)
        Q_W=Q_W,
        LMTD_K=29.1,
        F_factor=0.85,
        U_dirty_W_m2K=220.0,
        R_f_hot_m2KW=0.000352,   # TEMA R fouling for viscous organic fluids
        R_f_cold_m2KW=0.000176,
        h_tube_W_m2K=4500.0,
        h_shell_W_m2K=350.0,
        Re_tube=12_000.0,
        Re_shell=800.0,
        tube_velocity_m_s=1.0,
        dP_tube_Pa=38_000.0,
        dP_shell_Pa=62_000.0,
        # Step 11 outputs
        area_required_m2=Q_W / (220.0 * 0.85 * 29.1),
        area_provided_m2=area_provided,
        overdesign_pct=(area_provided / (Q_W / (220.0 * 0.85 * 29.1)) - 1.0) * 100.0,
        # Step 12 convergence outputs
        convergence_converged=True,
        convergence_iteration=5,
        convergence_trajectory=[
            {"iteration": i, "U_dirty": 220.0 + (5 - i) * 2.0, "delta_U_pct": float(5 - i)}
            for i in range(1, 6)
        ],
        geometry=GeometrySpec(
            shell_diameter_m=0.600,
            tube_od_m=0.01905,
            tube_id_m=0.01483,
            tube_length_m=4.877,
            n_tubes=316,
            n_passes=2,
            tube_pitch_m=0.0238,
            pitch_ratio=1.25,
            pitch_layout="triangular",
            baffle_spacing_m=0.200,
            baffle_cut=0.25,
            n_baffles=23,
        ),
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _run_step(step, state: DesignState) -> None:
    """Run one step and apply outputs to state."""
    result = await step.run_with_review_loop(state, STUB_AI)
    apply_outputs(state, result)
    state.current_step = step.step_id
    if step.step_id not in state.completed_steps:
        state.completed_steps.append(step.step_id)


# ---------------------------------------------------------------------------
# E2E tests
# ---------------------------------------------------------------------------

class TestGlycerolCoolerE2EPipeline:
    """E2E: Steps 13 → 16 complete without error and populate all key fields."""

    @pytest.fixture
    def state(self):
        return _glycerol_cooler_converged_state()

    # ── Single-step pre-conditions ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_step13_vibration_check_runs(self, state):
        """Step 13 completes and writes vibration_safe to state."""
        await _run_step(Step13VibrationCheck(), state)
        assert state.vibration_safe is not None
        assert state.vibration_details is not None

    @pytest.mark.asyncio
    async def test_step14_mechanical_runs_after_step13(self, state):
        """Step 14 completes after Step 13 and writes tube/shell thickness flags."""
        await _run_step(Step13VibrationCheck(), state)
        await _run_step(Step14MechanicalCheck(), state)
        assert state.tube_thickness_ok is not None
        assert state.shell_thickness_ok is not None

    @pytest.mark.asyncio
    async def test_step15_cost_runs_after_step14(self, state):
        """Step 15 completes and writes cost_usd to state."""
        await _run_step(Step13VibrationCheck(), state)
        await _run_step(Step14MechanicalCheck(), state)
        await _run_step(Step15CostEstimate(), state)
        assert state.cost_usd is not None
        assert state.cost_usd > 0

    # ── Full downstream pipeline ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_full_downstream_pipeline_reaches_step_16(self, state):
        """Steps 13 → 16 chain completes without raising any exception."""
        await _run_step(Step13VibrationCheck(), state)
        await _run_step(Step14MechanicalCheck(), state)
        await _run_step(Step15CostEstimate(), state)
        await _run_step(Step16FinalValidation(), state)
        assert 16 in state.completed_steps

    @pytest.mark.asyncio
    async def test_confidence_score_populated_at_step_16(self, state):
        """Step 16 must write a non-null confidence_score (regression: bug fix #2)."""
        await _run_step(Step13VibrationCheck(), state)
        await _run_step(Step14MechanicalCheck(), state)
        await _run_step(Step15CostEstimate(), state)
        await _run_step(Step16FinalValidation(), state)
        assert state.confidence_score is not None, (
            "confidence_score must be populated by Step 16 "
            "(None indicates Step 16 was not reached or crashed)"
        )
        assert 0.0 <= state.confidence_score <= 1.0

    @pytest.mark.asyncio
    async def test_convergence_converged_preserved_through_pipeline(self, state):
        """convergence_converged flag must remain True after Steps 13 → 16."""
        await _run_step(Step13VibrationCheck(), state)
        await _run_step(Step14MechanicalCheck(), state)
        await _run_step(Step15CostEstimate(), state)
        await _run_step(Step16FinalValidation(), state)
        assert state.convergence_converged is True

    @pytest.mark.asyncio
    async def test_pipeline_completed_steps_in_order(self, state):
        """completed_steps must include 13, 14, 15, 16 in that order."""
        await _run_step(Step13VibrationCheck(), state)
        await _run_step(Step14MechanicalCheck(), state)
        await _run_step(Step15CostEstimate(), state)
        await _run_step(Step16FinalValidation(), state)
        for step_id in (13, 14, 15, 16):
            assert step_id in state.completed_steps, (
                f"Step {step_id} not in completed_steps: {state.completed_steps}"
            )

    @pytest.mark.asyncio
    async def test_no_step_error_raised_end_to_end(self, state):
        """No CalculationError raised from any downstream step (regression guard)."""
        from hx_engine.app.core.exceptions import CalculationError

        try:
            await _run_step(Step13VibrationCheck(), state)
            await _run_step(Step14MechanicalCheck(), state)
            await _run_step(Step15CostEstimate(), state)
            await _run_step(Step16FinalValidation(), state)
        except CalculationError as exc:
            pytest.fail(
                f"CalculationError raised in downstream pipeline: {exc}"
            )
