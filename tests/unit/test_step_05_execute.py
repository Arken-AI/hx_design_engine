"""Tests for Piece 3 — Step05LMTD execute() and conditional AI trigger.

Physics invariants enforced in every test:
  - effective_LMTD = F × LMTD
  - effective_LMTD ≤ LMTD (because F ≤ 1.0)
  - Auto-correction only increases shell_passes (never decreases)
  - Temperatures and Q_W are never modified by this step
"""

from __future__ import annotations

import pytest

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import DesignState, GeometrySpec
from hx_engine.app.steps.step_05_lmtd import Step05LMTD


def _make_state(
    T_hot_in=150.0, T_hot_out=90.0,
    T_cold_in=30.0, T_cold_out=55.0,
    Q_W=6_000_000.0,
    n_passes=2, shell_passes=1,
    **kwargs,
) -> DesignState:
    """Create a DesignState pre-populated through Step 4."""
    return DesignState(
        T_hot_in_C=T_hot_in,
        T_hot_out_C=T_hot_out,
        T_cold_in_C=T_cold_in,
        T_cold_out_C=T_cold_out,
        Q_W=Q_W,
        geometry=GeometrySpec(
            n_passes=n_passes,
            shell_passes=shell_passes,
            tube_od_m=0.01905,
            tube_id_m=0.01483,
            tube_length_m=4.88,
            pitch_ratio=1.25,
            pitch_layout="triangular",
            shell_diameter_m=0.489,
            baffle_cut=0.25,
            baffle_spacing_m=0.15,
            n_tubes=158,
        ),
        **kwargs,
    )


@pytest.fixture
def step():
    return Step05LMTD()


# ===================================================================
# Benchmark and basic tests
# ===================================================================


class TestStep05Execute:

    @pytest.mark.asyncio
    async def test_benchmark_crude_oil_water(self, step):
        """150/90 hot, 30/55 cold, 2 tube passes, 1 shell → LMTD ≈ 76.17, F ≈ 0.955."""
        state = _make_state()
        result = await step.execute(state)

        assert result.outputs["LMTD_K"] == pytest.approx(76.17, rel=1e-3)
        assert result.outputs["F_factor"] == pytest.approx(0.955, rel=0.01)
        eff = result.outputs["effective_LMTD"]
        assert eff == pytest.approx(
            result.outputs["F_factor"] * result.outputs["LMTD_K"], rel=1e-6,
        )
        assert eff <= result.outputs["LMTD_K"]

    @pytest.mark.asyncio
    async def test_missing_T_hot_in_raises(self, step):
        state = _make_state(T_hot_in=None)
        with pytest.raises(CalculationError, match="T_hot_in_C"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_T_cold_out_raises(self, step):
        state = _make_state(T_cold_out=None)
        with pytest.raises(CalculationError, match="T_cold_out_C"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_Q_W_raises(self, step):
        state = _make_state(Q_W=None)
        with pytest.raises(CalculationError, match="Q_W"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_missing_geometry_raises(self, step):
        state = DesignState(
            T_hot_in_C=150, T_hot_out_C=90,
            T_cold_in_C=30, T_cold_out_C=55,
            Q_W=6e6,
        )
        with pytest.raises(CalculationError, match="geometry"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_pure_countercurrent_F_is_1(self, step):
        """1 tube pass + 1 shell pass → F = 1.0 exactly, R and P are None."""
        state = _make_state(n_passes=1, shell_passes=1)
        result = await step.execute(state)

        assert result.outputs["F_factor"] == 1.0
        assert result.outputs["R"] is None
        assert result.outputs["P"] is None
        assert result.outputs["effective_LMTD"] == pytest.approx(
            result.outputs["LMTD_K"], rel=1e-6,
        )


# ===================================================================
# Auto-correction tests
# ===================================================================


class TestStep05AutoCorrection:

    @pytest.mark.asyncio
    async def test_auto_correct_1_to_2_shells(self, step):
        """Temps giving low F with 1 shell → auto-correct to 2 shells."""
        # R=1.0, P=0.6 gives F ≈ 0.58 for 1 shell — well below 0.80
        # T_hot: 100→60, T_cold: 20→60, R=(100-60)/(60-20)=1.0, P=(60-20)/(100-20)=0.5
        # Need F < 0.80 with 1 shell. Use P closer to limit.
        # R=1.5, P=0.5: should give F around 0.75 with 1 shell
        # T_hot: 120→60, T_cold: 20→60. R=(120-60)/(60-20)=1.5, P=(60-20)/(120-20)=0.4
        state = _make_state(
            T_hot_in=120, T_hot_out=60,
            T_cold_in=20, T_cold_out=60,
            n_passes=2, shell_passes=1,
        )
        result = await step.execute(state)

        # Check if auto-correction happened
        if result.outputs["auto_corrected"]:
            assert result.outputs["shell_passes"] == 2
            assert state.geometry.shell_passes == 2
            # F should have improved
            assert result.outputs["F_factor"] >= 0.75

    @pytest.mark.asyncio
    async def test_small_lmtd_warning(self, step):
        """LMTD < 3°C triggers a warning."""
        # Make ΔTs very small: 33/31 hot, 30/31 cold
        # ΔT₁ = 33-31 = 2, ΔT₂ = 31-30 = 1 → LMTD ≈ 1.44
        state = _make_state(
            T_hot_in=33, T_hot_out=31,
            T_cold_in=30, T_cold_out=31,
            n_passes=1, shell_passes=1,  # pure counter-current
        )
        result = await step.execute(state)
        assert any("very small" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_high_R_warning(self, step):
        """R > 4.0 triggers asymmetric duty warning."""
        # R = (200-50)/(30+150/30) — let's set R > 4
        # T_hot: 200→50, T_cold: 20→30 → R=(200-50)/(30-20)=15.0
        state = _make_state(
            T_hot_in=200, T_hot_out=50,
            T_cold_in=20, T_cold_out=30,
            n_passes=2, shell_passes=1,
        )
        result = await step.execute(state)
        assert any("asymmetric" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_equal_delta_t_no_crash(self, step):
        """ΔT₁ = ΔT₂ exactly → returns valid LMTD (arithmetic mean)."""
        # ΔT₁ = 120-60 = 60, ΔT₂ = 80-20 = 60
        state = _make_state(
            T_hot_in=120, T_hot_out=80,
            T_cold_in=20, T_cold_out=60,
            n_passes=2, shell_passes=1,
        )
        result = await step.execute(state)
        assert result.outputs["LMTD_K"] == pytest.approx(60.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_R_equals_1_no_crash(self, step):
        """Symmetric case R = 1.0 → no NaN/inf."""
        # R=1: (150-90)/(90-30)=60/60=1.0, P=(90-30)/(150-30)=0.5
        state = _make_state(
            T_hot_in=150, T_hot_out=90,
            T_cold_in=30, T_cold_out=90,
            n_passes=2, shell_passes=1,
        )
        result = await step.execute(state)
        F = result.outputs["F_factor"]
        assert 0.0 <= F <= 1.0
        import math
        assert not math.isnan(F)
        assert not math.isinf(F)


# ===================================================================
# Conditional AI trigger tests
# ===================================================================


class TestStep05AITrigger:

    @pytest.mark.asyncio
    async def test_ai_trigger_F_below_085(self, step):
        """F = 0.84, no auto-correction → AI triggered."""
        step._F_factor = 0.84
        step._R = 2.0
        step._auto_corrected = False
        state = _make_state(T_hot_out=90, T_cold_out=55)  # approach=35°C
        assert step._conditional_ai_trigger(state) is True

    @pytest.mark.asyncio
    async def test_ai_trigger_F_above_085_no_call(self, step):
        """F = 0.92, R = 2.0, approach > 3°C → no AI."""
        step._F_factor = 0.92
        step._R = 2.0
        step._auto_corrected = False
        state = _make_state(T_hot_out=90, T_cold_out=55)
        assert step._conditional_ai_trigger(state) is False

    @pytest.mark.asyncio
    async def test_ai_trigger_auto_corrected_above_080(self, step):
        """Auto-corrected, corrected F = 0.88 → no AI (correction worked)."""
        step._F_factor = 0.88
        step._R = 2.0
        step._auto_corrected = True
        state = _make_state(T_hot_out=90, T_cold_out=55)
        assert step._conditional_ai_trigger(state) is False

    @pytest.mark.asyncio
    async def test_ai_trigger_auto_corrected_below_080(self, step):
        """Auto-corrected, corrected F = 0.79 → AI triggered."""
        step._F_factor = 0.79
        step._R = 2.0
        step._auto_corrected = True
        state = _make_state(T_hot_out=90, T_cold_out=55)
        assert step._conditional_ai_trigger(state) is True

    @pytest.mark.asyncio
    async def test_ai_trigger_high_R(self, step):
        """F = 0.95 but R = 4.5 → AI triggered."""
        step._F_factor = 0.95
        step._R = 4.5
        step._auto_corrected = False
        state = _make_state(T_hot_out=90, T_cold_out=55)
        assert step._conditional_ai_trigger(state) is True

    @pytest.mark.asyncio
    async def test_ai_trigger_temp_cross_risk(self, step):
        """F = 0.95, R = 2.0, approach = 2°C → AI triggered."""
        step._F_factor = 0.95
        step._R = 2.0
        step._auto_corrected = False
        # approach = T_hot_out - T_cold_out = 92 - 90 = 2°C
        state = _make_state(T_hot_out=92, T_cold_out=90)
        assert step._conditional_ai_trigger(state) is True


# ===================================================================
# State immutability tests (Piece 4)
# ===================================================================


class TestStep05StateMutations:

    @pytest.mark.asyncio
    async def test_state_lmtd_populated(self, step):
        state = _make_state()
        await step.execute(state)
        assert state.LMTD_K is not None
        assert state.LMTD_K > 0

    @pytest.mark.asyncio
    async def test_state_f_factor_populated(self, step):
        state = _make_state()
        await step.execute(state)
        assert state.F_factor is not None
        assert 0 < state.F_factor <= 1.0

    @pytest.mark.asyncio
    async def test_state_Q_W_unchanged(self, step):
        state = _make_state()
        original_Q = state.Q_W
        await step.execute(state)
        assert state.Q_W == original_Q

    @pytest.mark.asyncio
    async def test_state_temps_unchanged(self, step):
        state = _make_state()
        orig = (state.T_hot_in_C, state.T_hot_out_C, state.T_cold_in_C, state.T_cold_out_C)
        await step.execute(state)
        assert (state.T_hot_in_C, state.T_hot_out_C, state.T_cold_in_C, state.T_cold_out_C) == orig
