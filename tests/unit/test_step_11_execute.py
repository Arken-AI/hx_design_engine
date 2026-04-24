"""Tests for Step 11 — Area and Overdesign executor and rules.

Covers: precondition checks, core arithmetic, overdesign ranges,
AI trigger logic, convergence loop skip, diagnostic field,
warnings, state mutation, and all 3 validation rules.
"""

from __future__ import annotations

import math

import pytest

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_11_area_overdesign import Step11AreaOverdesign

# Import rules to ensure registration
import hx_engine.app.steps.step_11_rules as rules_mod


# ── Fixture: pre-populated state through Step 10 ─────────────────────

def _make_state(
    Q_W: float = 500_000.0,
    LMTD_K: float = 30.0,
    F_factor: float = 0.9,
    U_dirty: float = 300.0,
    n_tubes: int = 200,
    tube_od_m: float = 0.01905,
    tube_length_m: float = 6.0,
    A_m2: float | None = 65.0,
    in_convergence_loop: bool = False,
    **overrides,
) -> DesignState:
    """Create DesignState pre-populated through Steps 1-10."""
    hot_props = FluidProperties(
        density_kg_m3=850.0,
        viscosity_Pa_s=0.0012,
        specific_heat_J_kgK=2200.0,
        thermal_conductivity_W_mK=0.13,
        Pr=20.3,
    )
    cold_props = FluidProperties(
        density_kg_m3=995.0,
        viscosity_Pa_s=0.0008,
        specific_heat_J_kgK=4180.0,
        thermal_conductivity_W_mK=0.62,
        Pr=5.4,
    )

    state = DesignState(
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=55.0,
        hot_fluid_name="crude oil",
        cold_fluid_name="cooling water",
        m_dot_hot_kg_s=50.0,
        m_dot_cold_kg_s=100.0,
        hot_fluid_props=hot_props,
        cold_fluid_props=cold_props,
        shell_side_fluid="hot",
        geometry=GeometrySpec(
            shell_diameter_m=0.489,
            tube_od_m=tube_od_m,
            tube_id_m=0.01483,
            tube_length_m=tube_length_m,
            n_tubes=n_tubes,
            tube_pitch_m=0.02381,
            pitch_ratio=1.25,
            pitch_layout="triangular",
            n_passes=2,
            baffle_spacing_m=0.15,
            baffle_cut=0.25,
            n_baffles=30,
        ),
        Q_W=Q_W,
        LMTD_K=LMTD_K,
        F_factor=F_factor,
        U_dirty_W_m2K=U_dirty,
        A_m2=A_m2,
        in_convergence_loop=in_convergence_loop,
    )
    for k, v in overrides.items():
        setattr(state, k, v)
    return state


# ══════════════════════════════════════════════════════════════════════
# Precondition tests
# ══════════════════════════════════════════════════════════════════════

class TestPreconditions:

    @pytest.mark.asyncio
    async def test_missing_q_w(self) -> None:
        state = _make_state(Q_W=None)
        step = Step11AreaOverdesign()
        with pytest.raises(CalculationError, match="Q_W"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_lmtd(self) -> None:
        state = _make_state(LMTD_K=None)
        step = Step11AreaOverdesign()
        with pytest.raises(CalculationError, match="LMTD_K"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_f_factor(self) -> None:
        state = _make_state(F_factor=None)
        step = Step11AreaOverdesign()
        with pytest.raises(CalculationError, match="F_factor"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_u_dirty(self) -> None:
        state = _make_state(U_dirty=None)
        step = Step11AreaOverdesign()
        with pytest.raises(CalculationError, match="U_dirty_W_m2K"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_geometry(self) -> None:
        state = _make_state()
        state.geometry = None
        step = Step11AreaOverdesign()
        with pytest.raises(CalculationError, match="geometry"):
            await step.execute(state)


# ══════════════════════════════════════════════════════════════════════
# Core arithmetic tests
# ══════════════════════════════════════════════════════════════════════

class TestExecution:

    @pytest.mark.asyncio
    async def test_basic_overdesign_calculation(self) -> None:
        """Worked example from impl plan:
        Q=500kW, LMTD=30K, F=0.9, U_dirty=300, 200 tubes, d_o=19.05mm, L=6m
        A_req = 500000/(300×0.9×30) = 61.728 m²
        A_prov = π×0.01905×6.0×200 = 71.816 m²
        overdesign = (71.816-61.728)/61.728 × 100 = 16.34%
        """
        state = _make_state()
        step = Step11AreaOverdesign()
        result = await step.execute(state)
        o = result.outputs

        expected_A_req = 500_000.0 / (300.0 * 0.9 * 30.0)
        expected_A_prov = math.pi * 0.01905 * 6.0 * 200
        expected_od = (expected_A_prov - expected_A_req) / expected_A_req * 100.0

        assert o["area_required_m2"] == pytest.approx(expected_A_req, rel=1e-6)
        assert o["area_provided_m2"] == pytest.approx(expected_A_prov, rel=1e-6)
        assert o["overdesign_pct"] == pytest.approx(expected_od, rel=1e-3)
        # Overdesign should be ~16%
        assert 15 < o["overdesign_pct"] < 18

    @pytest.mark.asyncio
    async def test_undersized_exchanger_negative_overdesign(self) -> None:
        """Geometry too small → negative overdesign."""
        state = _make_state(n_tubes=100)  # half the tubes → A_prov ≈ 35.9
        step = Step11AreaOverdesign()
        result = await step.execute(state)
        assert result.outputs["overdesign_pct"] < 0

    @pytest.mark.asyncio
    async def test_perfect_sizing_zero_overdesign(self) -> None:
        """A_provided exactly equals A_required → overdesign = 0."""
        # A_required = Q/(U*F*LMTD) = 500000/(300*0.9*30) = 61.728 m²
        # Need n_tubes s.t. π×d_o×L×n = 61.728
        # n = 61.728 / (π × 0.01905 × 6.0) = 171.88
        # Use Q=500000, U=300, F=0.9, LMTD=30, exact n_tubes won't give 0 easily
        # So set Q such that A_req = A_prov for 200 tubes
        A_prov = math.pi * 0.01905 * 6.0 * 200  # 71.816
        Q_exact = A_prov * 300.0 * 0.9 * 30.0
        state = _make_state(Q_W=Q_exact)
        step = Step11AreaOverdesign()
        result = await step.execute(state)
        assert result.outputs["overdesign_pct"] == pytest.approx(0.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_excessive_overdesign_warning(self) -> None:
        """Overdesign > 40% → warning generated."""
        # Use low U so A_required is small relative to A_provided
        state = _make_state(U_dirty=150.0)  # A_req ≈ 123.5 → won't work
        # Actually need high A_prov / low A_req
        # A_req = 500000/(150*0.9*30) = 123.46, A_prov = 71.8 → negative
        # Need many tubes or low Q
        state = _make_state(Q_W=100_000.0)  # A_req = 100000/(300*0.9*30) = 12.35
        step = Step11AreaOverdesign()
        result = await step.execute(state)
        # A_prov ≈ 71.8, A_req ≈ 12.35 → overdesign ≈ 481% → warning
        assert result.outputs["overdesign_pct"] > 40
        assert any("Excessive overdesign" in w for w in result.warnings)


# ══════════════════════════════════════════════════════════════════════
# Diagnostic field tests
# ══════════════════════════════════════════════════════════════════════

class TestDiagnostic:

    @pytest.mark.asyncio
    async def test_a_estimated_vs_required(self) -> None:
        """Step 6 estimate (A_m2=65) vs Step 11 required area."""
        state = _make_state(A_m2=50.0)
        step = Step11AreaOverdesign()
        result = await step.execute(state)
        A_req = result.outputs["area_required_m2"]
        expected = (50.0 - A_req) / A_req * 100.0
        assert result.outputs["A_estimated_vs_required_pct"] == pytest.approx(
            expected, rel=1e-4
        )

    @pytest.mark.asyncio
    async def test_a_estimated_none_when_step6_missing(self) -> None:
        """When A_m2 is None, diagnostic field is absent from outputs."""
        state = _make_state(A_m2=None)
        step = Step11AreaOverdesign()
        result = await step.execute(state)
        assert "A_estimated_vs_required_pct" not in result.outputs

    @pytest.mark.asyncio
    async def test_large_a_estimate_deviation_warning(self) -> None:
        """When Step 6 estimate is > 30% off, generate warning."""
        # A_req ≈ 61.7, set A_m2 = 100 → deviation ≈ +62%
        state = _make_state(A_m2=100.0)
        step = Step11AreaOverdesign()
        result = await step.execute(state)
        assert any("Initial U estimate" in w for w in result.warnings)


# ══════════════════════════════════════════════════════════════════════
# AI trigger / convergence tests
# ══════════════════════════════════════════════════════════════════════

class TestAITrigger:

    @pytest.mark.asyncio
    async def test_ai_triggered_low_overdesign(self) -> None:
        """Overdesign ~5% → AI should trigger."""
        # Need A_prov/A_req ≈ 1.05 → A_prov = 71.8, A_req ≈ 68.4
        # A_req = Q/(U*F*LMTD), solve Q = 68.4 * 300 * 0.9 * 30 = 554,040
        A_prov = math.pi * 0.01905 * 6.0 * 200
        target_A_req = A_prov / 1.05
        Q = target_A_req * 300.0 * 0.9 * 30.0
        state = _make_state(Q_W=Q)
        step = Step11AreaOverdesign()
        await step.execute(state)
        assert step._should_call_ai(state) is True

    @pytest.mark.asyncio
    async def test_ai_triggered_high_overdesign(self) -> None:
        """Overdesign ~35% → AI should trigger."""
        A_prov = math.pi * 0.01905 * 6.0 * 200
        target_A_req = A_prov / 1.35
        Q = target_A_req * 300.0 * 0.9 * 30.0
        state = _make_state(Q_W=Q)
        step = Step11AreaOverdesign()
        await step.execute(state)
        assert step._should_call_ai(state) is True

    @pytest.mark.asyncio
    async def test_ai_skipped_in_convergence_loop(self) -> None:
        """Even with low overdesign, AI skipped during convergence."""
        A_prov = math.pi * 0.01905 * 6.0 * 200
        target_A_req = A_prov / 1.05
        Q = target_A_req * 300.0 * 0.9 * 30.0
        state = _make_state(Q_W=Q, in_convergence_loop=True)
        step = Step11AreaOverdesign()
        await step.execute(state)
        assert step._should_call_ai(state) is False

    @pytest.mark.asyncio
    async def test_ai_not_triggered_ideal_range(self) -> None:
        """Overdesign ~18% → no AI needed."""
        A_prov = math.pi * 0.01905 * 6.0 * 200
        target_A_req = A_prov / 1.18
        Q = target_A_req * 300.0 * 0.9 * 30.0
        state = _make_state(Q_W=Q)
        step = Step11AreaOverdesign()
        await step.execute(state)
        assert step._should_call_ai(state) is False


# ══════════════════════════════════════════════════════════════════════
# Edge cases
# ══════════════════════════════════════════════════════════════════════

class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_near_zero_driving_force_guard(self) -> None:
        """F × LMTD near zero → CalculationError."""
        state = _make_state(F_factor=0.75, LMTD_K=0.0001)
        step = Step11AreaOverdesign()
        with pytest.raises(CalculationError, match="zero"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_outputs_written_to_state(self) -> None:
        """Execute populates all 4 state fields."""
        state = _make_state()
        step = Step11AreaOverdesign()
        await step.execute(state)

        assert state.area_required_m2 is not None
        assert state.area_required_m2 > 0
        assert state.area_provided_m2 is not None
        assert state.area_provided_m2 > 0
        assert state.overdesign_pct is not None
        assert state.A_estimated_vs_required_pct is not None

    @pytest.mark.asyncio
    async def test_output_keys(self) -> None:
        """All expected keys present in result."""
        state = _make_state()
        step = Step11AreaOverdesign()
        result = await step.execute(state)
        assert "area_required_m2" in result.outputs
        assert "area_provided_m2" in result.outputs
        assert "overdesign_pct" in result.outputs
        assert "A_estimated_vs_required_pct" in result.outputs

    @pytest.mark.asyncio
    async def test_undersized_warning(self) -> None:
        """Negative overdesign generates undersized warning."""
        state = _make_state(n_tubes=100)
        step = Step11AreaOverdesign()
        result = await step.execute(state)
        assert any("undersized" in w for w in result.warnings)


# ══════════════════════════════════════════════════════════════════════
# Validation rules
# ══════════════════════════════════════════════════════════════════════

def _make_result(**kwargs) -> StepResult:
    """Create a StepResult with given outputs."""
    defaults = {
        "area_required_m2": 61.7,
        "area_provided_m2": 71.8,
        "overdesign_pct": 16.4,
    }
    defaults.update(kwargs)
    return StepResult(step_id=11, step_name="Area and Overdesign", outputs=defaults)


class TestRules:

    def test_rule_area_required_positive_pass(self) -> None:
        result = _make_result(area_required_m2=50.0)
        passed, msg = rules_mod._rule_area_required_positive(11, result)
        assert passed is True

    def test_rule_area_required_zero_fail(self) -> None:
        result = _make_result(area_required_m2=0.0)
        passed, msg = rules_mod._rule_area_required_positive(11, result)
        assert passed is False

    def test_rule_area_required_missing_fail(self) -> None:
        result = StepResult(step_id=11, step_name="Area and Overdesign", outputs={})
        passed, msg = rules_mod._rule_area_required_positive(11, result)
        assert passed is False
        assert "missing" in msg

    def test_rule_area_provided_positive_pass(self) -> None:
        result = _make_result(area_provided_m2=60.0)
        passed, msg = rules_mod._rule_area_provided_positive(11, result)
        assert passed is True

    def test_rule_area_provided_zero_fail(self) -> None:
        result = _make_result(area_provided_m2=0.0)
        passed, msg = rules_mod._rule_area_provided_positive(11, result)
        assert passed is False

    def test_rule_overdesign_positive_pass(self) -> None:
        result = _make_result(overdesign_pct=15.0)
        passed, msg = rules_mod._rule_overdesign_not_negative(11, result)
        assert passed is True

    def test_rule_overdesign_negative_fail(self) -> None:
        result = _make_result(overdesign_pct=-5.0)
        passed, msg = rules_mod._rule_overdesign_not_negative(11, result)
        assert passed is False
        assert "undersized" in msg

    def test_rule_overdesign_zero_pass(self) -> None:
        result = _make_result(overdesign_pct=0.0)
        passed, msg = rules_mod._rule_overdesign_not_negative(11, result)
        assert passed is True

    def test_rule_overdesign_missing_fail(self) -> None:
        result = StepResult(step_id=11, step_name="Area and Overdesign", outputs={})
        passed, msg = rules_mod._rule_overdesign_not_negative(11, result)
        assert passed is False
        assert "missing" in msg


# ══════════════════════════════════════════════════════════════════════
# Multi-shell area accounting (P0-1 fix)
# ══════════════════════════════════════════════════════════════════════

class TestMultiShellAreaProvided:
    """Regression tests for P0-1: A_provided must include n_shells multiplier."""

    @pytest.mark.asyncio
    async def test_single_shell_area_unchanged(self) -> None:
        """n_shells=1 preserves the historical single-shell area exactly."""
        state = _make_state(
            tube_od_m=0.0254, tube_length_m=6.0, n_tubes=200,
            Q_W=1_000_000, U_dirty=500, F_factor=0.9, LMTD_K=40,
        )
        state.geometry.n_shells = 1

        result = await Step11AreaOverdesign().execute(state)

        expected = math.pi * 0.0254 * 6.0 * 200 * 1
        assert result.outputs["area_provided_m2"] == pytest.approx(expected, rel=1e-9)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("n_shells", [2, 3])
    async def test_multi_shell_area_includes_n_shells(self, n_shells: int) -> None:
        """A_provided scales linearly with n_shells for n_shells in {2, 3}."""
        state = _make_state(
            tube_od_m=0.0254, tube_length_m=6.0, n_tubes=200,
            Q_W=1_000_000, U_dirty=500, F_factor=0.85, LMTD_K=40,
        )
        state.geometry.n_shells = n_shells

        result = await Step11AreaOverdesign().execute(state)

        expected = math.pi * 0.0254 * 6.0 * 200 * n_shells
        assert result.outputs["area_provided_m2"] == pytest.approx(expected, rel=1e-9)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("n_shells_input", [None, 0])
    async def test_n_shells_defensive_fallback(self, n_shells_input) -> None:
        """n_shells = None or 0 falls back to 1; never zero, never NaN."""
        state = _make_state(
            tube_od_m=0.0254, tube_length_m=6.0, n_tubes=200,
            Q_W=1_000_000, U_dirty=500, F_factor=0.9, LMTD_K=40,
        )
        state.geometry.n_shells = n_shells_input

        result = await Step11AreaOverdesign().execute(state)

        expected = math.pi * 0.0254 * 6.0 * 200
        assert result.outputs["area_provided_m2"] == pytest.approx(expected, rel=1e-9)

    @pytest.mark.asyncio
    async def test_undersized_warning_surfaces_n_shells(self) -> None:
        """Undersized warning string mentions the shell count for audit clarity."""
        state = _make_state(n_tubes=50, Q_W=2_000_000, U_dirty=300)
        state.geometry.n_shells = 2

        result = await Step11AreaOverdesign().execute(state)

        assert any("2 shell(s)" in w for w in result.warnings)
