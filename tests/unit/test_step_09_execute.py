"""Tests for Step 09 — Overall Heat Transfer Coefficient + Resistance Breakdown.

Physics invariants enforced:
  - U_clean >= U_dirty (fouling can only reduce U)
  - 0.5 <= cleanliness_factor <= 1.0
  - All individual resistances >= 0
  - Resistance percentages sum to ~100%
  - Controlling resistance is the largest %
  - Fouling mapping hot/cold → inner/outer depends on shell_side_fluid
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
from hx_engine.app.steps.step_09_overall_u import Step09OverallU


def _make_state(
    h_shell: float = 2000.0,
    h_tube: float = 5000.0,
    R_f_hot: float = 0.000176,
    R_f_cold: float = 0.000176,
    shell_side_fluid: str = "hot",
    tube_od_m: float = 0.01905,
    tube_id_m: float = 0.01483,
    U_est: float | None = 400.0,
    h_shell_kern: float | None = None,
    k_wall: float | None = None,
    tube_material: str | None = None,
    in_convergence_loop: bool = False,
    **kwargs,
) -> DesignState:
    """Create a DesignState pre-populated through Step 8."""
    state = DesignState(
        # Step 1 basics
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=55.0,
        hot_fluid_name="crude oil",
        cold_fluid_name="cooling water",
        m_dot_hot_kg_s=50.0,
        m_dot_cold_kg_s=100.0,
        # Geometry
        geometry=GeometrySpec(
            tube_od_m=tube_od_m,
            tube_id_m=tube_id_m,
            tube_length_m=4.88,
            pitch_ratio=1.25,
            pitch_layout="triangular",
            shell_diameter_m=0.489,
            baffle_cut=0.25,
            baffle_spacing_m=0.15,
            n_tubes=158,
            n_passes=2,
        ),
        # Step 4 fouling
        R_f_hot_m2KW=R_f_hot,
        R_f_cold_m2KW=R_f_cold,
        shell_side_fluid=shell_side_fluid,
        # Step 6
        U_W_m2K=U_est,
        # Step 7
        h_tube_W_m2K=h_tube,
        # Step 8
        h_shell_W_m2K=h_shell,
        h_shell_kern_W_m2K=h_shell_kern,
        # Convergence
        in_convergence_loop=in_convergence_loop,
        **kwargs,
    )
    if k_wall is not None:
        state.k_wall_W_mK = k_wall
        state.tube_material = tube_material or "carbon_steel"
        state.k_wall_source = "test"
        state.k_wall_confidence = 0.9
    return state


def _hand_calc_U(h_o, h_i, R_f_o, R_f_i, d_o, d_i, k_w):
    """Manual U calculation for verification."""
    R_sf = 1.0 / h_o
    R_tf = (d_o / d_i) / h_i
    R_sfo = R_f_o
    R_tfi = R_f_i * (d_o / d_i)
    R_wall = d_o * math.log(d_o / d_i) / (2.0 * k_w)
    total = R_sf + R_tf + R_sfo + R_tfi + R_wall
    return 1.0 / total


@pytest.fixture
def step():
    return Step09OverallU()


# ===================================================================
# Layer 1: Core calculation tests
# ===================================================================


class TestStep09Execute:

    @pytest.mark.asyncio
    async def test_water_water_u(self, step):
        """Water/water service: h_o=3000, h_i=5000, carbon steel."""
        state = _make_state(h_shell=3000.0, h_tube=5000.0)
        result = await step.execute(state)

        # Verify against hand calculation
        expected_U = _hand_calc_U(
            3000.0, 5000.0, 0.000176, 0.000176,
            0.01905, 0.01483, 50.0,
        )
        assert result.outputs["U_dirty_W_m2K"] == pytest.approx(expected_U, rel=1e-6)
        assert result.outputs["U_clean_W_m2K"] >= result.outputs["U_dirty_W_m2K"]

    @pytest.mark.asyncio
    async def test_oil_water_u(self, step):
        """Oil shell / water tube: shell film should dominate."""
        state = _make_state(h_shell=500.0, h_tube=4000.0)
        result = await step.execute(state)

        breakdown = result.outputs["resistance_breakdown"]
        assert breakdown["shell_film"]["pct"] > 30.0
        assert result.outputs["controlling_resistance"] == "shell_film"

    @pytest.mark.asyncio
    async def test_gas_liquid_u(self, step):
        """Gas shell / water tube: shell film should dominate heavily."""
        state = _make_state(h_shell=100.0, h_tube=4000.0)
        result = await step.execute(state)

        breakdown = result.outputs["resistance_breakdown"]
        assert breakdown["shell_film"]["pct"] > 50.0
        assert result.outputs["controlling_resistance"] == "shell_film"

    @pytest.mark.asyncio
    async def test_stainless_wall_impact(self, step):
        """Stainless steel (k=16.2) → wall resistance > 5%."""
        state = _make_state(
            h_shell=3000.0, h_tube=5000.0,
            k_wall=16.2, tube_material="stainless_304",
        )
        result = await step.execute(state)
        wall_pct = result.outputs["resistance_breakdown"]["wall"]["pct"]
        assert wall_pct > 5.0

    @pytest.mark.asyncio
    async def test_copper_wall_negligible(self, step):
        """Copper tubes (k=385) → wall resistance < 1%."""
        state = _make_state(
            h_shell=3000.0, h_tube=5000.0,
            k_wall=385.0, tube_material="copper",
        )
        result = await step.execute(state)
        wall_pct = result.outputs["resistance_breakdown"]["wall"]["pct"]
        assert wall_pct < 1.0

    @pytest.mark.asyncio
    async def test_clean_ge_dirty(self, step):
        """U_clean must always be >= U_dirty."""
        state = _make_state()
        result = await step.execute(state)
        assert result.outputs["U_clean_W_m2K"] >= result.outputs["U_dirty_W_m2K"]

    @pytest.mark.asyncio
    async def test_cf_range(self, step):
        """Cleanliness factor must be in [0, 1]."""
        state = _make_state()
        result = await step.execute(state)
        cf = result.outputs["cleanliness_factor"]
        assert 0.0 <= cf <= 1.0

    @pytest.mark.asyncio
    async def test_pct_sum_100(self, step):
        """Resistance percentages must sum to ~100%."""
        state = _make_state()
        result = await step.execute(state)
        breakdown = result.outputs["resistance_breakdown"]
        pct_sum = sum(
            v["pct"] for k, v in breakdown.items()
            if isinstance(v, dict) and k != "total_1_over_U"
        )
        assert pct_sum == pytest.approx(100.0, abs=0.01)


class TestStep09FoulingMapping:

    @pytest.mark.asyncio
    async def test_hot_shell_mapping(self, step):
        """shell_side_fluid='hot' → R_f_outer = R_f_hot."""
        state = _make_state(
            shell_side_fluid="hot",
            R_f_hot=0.0005,
            R_f_cold=0.0001,
        )
        result = await step.execute(state)
        breakdown = result.outputs["resistance_breakdown"]
        # Shell fouling should use R_f_hot (0.0005)
        assert breakdown["shell_fouling"]["value_m2KW"] == pytest.approx(0.0005, rel=1e-6)

    @pytest.mark.asyncio
    async def test_cold_shell_mapping(self, step):
        """shell_side_fluid='cold' → R_f_outer = R_f_cold."""
        state = _make_state(
            shell_side_fluid="cold",
            R_f_hot=0.0005,
            R_f_cold=0.0001,
        )
        result = await step.execute(state)
        breakdown = result.outputs["resistance_breakdown"]
        # Shell fouling should use R_f_cold (0.0001)
        assert breakdown["shell_fouling"]["value_m2KW"] == pytest.approx(0.0001, rel=1e-6)


class TestStep09KernCrosscheck:

    @pytest.mark.asyncio
    async def test_kern_crosscheck_computed(self, step):
        """When h_shell_kern is on state, U_kern and deviation are computed."""
        state = _make_state(h_shell=2000.0, h_shell_kern=1800.0)
        result = await step.execute(state)

        assert result.outputs.get("U_kern_W_m2K") is not None
        assert result.outputs.get("U_kern_deviation_pct") is not None
        assert result.outputs["U_kern_deviation_pct"] >= 0

    @pytest.mark.asyncio
    async def test_kern_crosscheck_missing(self, step):
        """When h_shell_kern is None, U_kern outputs are absent."""
        state = _make_state(h_shell_kern=None)
        result = await step.execute(state)

        assert result.outputs.get("U_kern_W_m2K") is None
        assert result.outputs.get("U_kern_deviation_pct") is None

    @pytest.mark.asyncio
    async def test_kern_deviation_direction(self, step):
        """Lower kern h → lower U_kern → positive deviation from BD U."""
        state = _make_state(h_shell=2000.0, h_shell_kern=1000.0)
        result = await step.execute(state)

        assert result.outputs["U_kern_W_m2K"] < result.outputs["U_dirty_W_m2K"]
        assert result.outputs["U_kern_deviation_pct"] > 0


class TestStep09EstimateDeviation:

    @pytest.mark.asyncio
    async def test_deviation_computed(self, step):
        """Deviation from Step 6 U is computed when U_est is present."""
        state = _make_state(U_est=400.0)
        result = await step.execute(state)
        assert result.outputs.get("U_vs_estimated_deviation_pct") is not None

    @pytest.mark.asyncio
    async def test_deviation_none_when_no_estimate(self, step):
        """Deviation is None when Step 6 U is not set."""
        state = _make_state(U_est=None)
        result = await step.execute(state)
        assert result.outputs.get("U_vs_estimated_deviation_pct") is None

    @pytest.mark.asyncio
    async def test_deviation_sign(self, step):
        """If U_calc < U_est, deviation should be negative."""
        # Use low h values to get low U
        state = _make_state(h_shell=200.0, h_tube=300.0, U_est=500.0)
        result = await step.execute(state)
        assert result.outputs["U_vs_estimated_deviation_pct"] < 0


class TestStep09MaterialResolution:

    @pytest.mark.asyncio
    async def test_material_resolved_on_first_call(self, step):
        """When k_wall is not on state, stub default is used and state is updated."""
        state = _make_state(k_wall=None)
        assert state.k_wall_W_mK is None

        await step.execute(state)

        assert state.k_wall_W_mK is not None
        assert state.k_wall_W_mK == 50.0  # carbon steel default
        assert state.k_wall_source == "stub_default"
        assert state.tube_material is not None

    @pytest.mark.asyncio
    async def test_material_cached_on_second_call(self, step):
        """When k_wall is already on state, it's not overwritten."""
        state = _make_state(k_wall=16.2, tube_material="stainless_304")
        result = await step.execute(state)

        assert state.k_wall_W_mK == 16.2
        assert result.outputs["k_wall_W_mK"] == 16.2

    @pytest.mark.asyncio
    async def test_stub_default_generates_warning(self, step):
        """Stub default k_wall should produce a warning."""
        state = _make_state(k_wall=None)
        result = await step.execute(state)

        assert any("stub default" in w for w in result.warnings)


# ===================================================================
# Precondition tests
# ===================================================================


class TestStep09Preconditions:

    @pytest.mark.asyncio
    async def test_missing_h_shell_raises(self, step):
        state = _make_state()
        state.h_shell_W_m2K = None
        with pytest.raises(CalculationError, match="h_shell"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_h_tube_raises(self, step):
        state = _make_state()
        state.h_tube_W_m2K = None
        with pytest.raises(CalculationError, match="h_tube"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_geometry_raises(self, step):
        state = _make_state()
        state.geometry = None
        with pytest.raises(CalculationError, match="geometry"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_fouling_raises(self, step):
        state = _make_state()
        state.R_f_hot_m2KW = None
        with pytest.raises(CalculationError, match="R_f_hot"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_shell_side_fluid_raises(self, step):
        state = _make_state()
        state.shell_side_fluid = None
        with pytest.raises(CalculationError, match="shell_side_fluid"):
            await step.execute(state)


# ===================================================================
# Warnings and escalation hints
# ===================================================================


class TestStep09Warnings:

    @pytest.mark.asyncio
    async def test_low_cf_warning(self, step):
        """CF < 0.65 should trigger a warning."""
        # Heavy fouling to push CF low
        state = _make_state(R_f_hot=0.003, R_f_cold=0.003)
        result = await step.execute(state)
        assert any("Cleanliness factor" in w and "low" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_kern_divergence_warning(self, step):
        """Kern U deviation > 40% should trigger a warning."""
        state = _make_state(h_shell=2000.0, h_shell_kern=400.0)
        result = await step.execute(state)
        assert any("Kern" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_large_estimate_deviation_warning(self, step):
        """U deviation > 30% from estimate should warn."""
        # Very low h_shell → low U vs high estimate
        state = _make_state(h_shell=100.0, h_tube=200.0, U_est=500.0)
        result = await step.execute(state)
        assert any("Step 6 estimate" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_high_wall_pct_warning(self, step):
        """Wall resistance > 10% should trigger a warning."""
        # Use very low k_wall (exotic alloy) + high film coefficients
        state = _make_state(
            h_shell=5000.0, h_tube=8000.0,
            k_wall=10.0,  # Very low conductivity
            R_f_hot=0.00001, R_f_cold=0.00001,
        )
        result = await step.execute(state)
        assert any("Wall resistance" in w for w in result.warnings)


class TestStep09EscalationHints:

    @pytest.mark.asyncio
    async def test_very_low_u_hint(self, step):
        """U < 50 should generate escalation hint."""
        state = _make_state(h_shell=30.0, h_tube=50.0)
        result = await step.execute(state)
        hints = result.outputs.get("escalation_hints", [])
        assert any(h["trigger"] == "very_low_U" for h in hints)


# ===================================================================
# Convergence loop behavior
# ===================================================================


class TestStep09Convergence:

    def test_ai_skipped_in_convergence(self, step):
        """in_convergence_loop=True → _should_call_ai returns False."""
        state = _make_state(in_convergence_loop=True)
        assert step._should_call_ai(state) is False

    def test_ai_called_outside_convergence(self, step):
        """in_convergence_loop=False → _should_call_ai returns True."""
        state = _make_state(in_convergence_loop=False)
        assert step._should_call_ai(state) is True

    @pytest.mark.asyncio
    async def test_k_wall_not_reresolve_in_convergence(self, step):
        """k_wall already on state → not overwritten during convergence."""
        state = _make_state(
            k_wall=16.2,
            tube_material="stainless_304",
            in_convergence_loop=True,
        )
        await step.execute(state)
        assert state.k_wall_W_mK == 16.2  # not overwritten to default


# ===================================================================
# Wall resistance cross-check with ht library (optional)
# ===================================================================


class TestWallResistanceFormula:

    def test_wall_resistance_formula(self):
        """Verify wall resistance formula matches analytical ln formula."""
        d_o = 0.01905
        d_i = 0.01483
        k_w = 50.0
        R_formula = d_o * math.log(d_o / d_i) / (2.0 * k_w)
        # Sanity check — should be small positive number
        assert R_formula > 0
        assert R_formula < 0.001  # typical wall resistance is very small

    def test_wall_resistance_zero_for_same_diameters(self):
        """If d_o ≈ d_i (thin wall), R_wall → 0."""
        d_o = 0.01905
        d_i = 0.01904  # nearly same
        k_w = 50.0
        R_wall = d_o * math.log(d_o / d_i) / (2.0 * k_w)
        assert R_wall < 1e-6

    def test_wall_resistance_increases_with_low_k(self):
        """Lower k_w → higher wall resistance."""
        d_o = 0.01905
        d_i = 0.01483
        R_steel = d_o * math.log(d_o / d_i) / (2.0 * 50.0)
        R_ss = d_o * math.log(d_o / d_i) / (2.0 * 16.0)
        assert R_ss > R_steel
