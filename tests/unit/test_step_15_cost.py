"""Tests for hx_engine.app.steps.step_15_cost — Step 15 executor."""

from __future__ import annotations

import pytest

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import DesignState, GeometrySpec
from hx_engine.app.models.step_result import AIModeEnum
from hx_engine.app.steps.step_15_cost import Step15CostEstimate


# ─── Helpers ─────────────────────────────────────────────────────────

def _base_state(**overrides) -> DesignState:
    """Return a DesignState with minimum fields for Step 15."""
    defaults = dict(
        area_provided_m2=100.0,
        tema_type="BEM",
        P_hot_Pa=1_101_325.0,   # 10 barg + 1 atm
        P_cold_Pa=101_325.0,    # atmospheric
        shell_side_fluid="hot",
        tube_material="carbon_steel",
        shell_material="carbon_steel",
        convergence_converged=True,
        geometry=GeometrySpec(
            shell_diameter_m=0.508,
            tube_od_m=0.01905,
            tube_id_m=0.01575,
            tube_length_m=4.877,
            baffle_spacing_m=0.127,
            n_tubes=324,
        ),
    )
    defaults.update(overrides)
    return DesignState(**defaults)


async def _run(state: DesignState):
    step = Step15CostEstimate()
    return await step.execute(state)


# ═══════════════════════════════════════════════════════════════════
# Basic execution
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_basic_execution():
    """T5.1: Basic execution: 100 m², BEM, CS/CS, 10 barg."""
    state = _base_state()
    result = await _run(state)
    assert state.cost_usd > 0
    assert result.outputs["cost_usd"] > 0
    bd = result.outputs["cost_breakdown"]
    assert bd["area_m2"] == 100.0
    assert bd["turton_row"] == "fixed_tube"
    assert bd["F_M"] > 0
    assert bd["F_P"] >= 1.0
    assert bd["C_BM_2026_usd"] > 0
    assert bd["cost_per_m2_usd"] > 0


@pytest.mark.asyncio
async def test_cost_increases_with_area():
    """T5.2: Cost increases with area: 200 m² > 100 m²."""
    state_100 = _base_state(area_provided_m2=100.0)
    state_200 = _base_state(area_provided_m2=200.0)
    r_100 = await _run(state_100)
    r_200 = await _run(state_200)
    assert r_200.outputs["cost_usd"] > r_100.outputs["cost_usd"]


@pytest.mark.asyncio
async def test_floating_head_more_expensive():
    """T5.3: Floating head more expensive than fixed tube."""
    state_bem = _base_state(tema_type="BEM")
    state_aes = _base_state(tema_type="AES")
    r_bem = await _run(state_bem)
    r_aes = await _run(state_aes)
    assert r_aes.outputs["cost_usd"] > r_bem.outputs["cost_usd"]


@pytest.mark.asyncio
async def test_utube_cost_valid():
    """T5.4: U-tube produces valid cost."""
    state = _base_state(tema_type="AEU")
    result = await _run(state)
    assert result.outputs["cost_usd"] > 0


@pytest.mark.asyncio
async def test_higher_pressure_higher_cost():
    """T5.5: Higher pressure → higher cost."""
    # 3 barg (below threshold)
    state_low = _base_state(P_hot_Pa=101_325.0 + 3e5)
    # 50 barg
    state_mid = _base_state(P_hot_Pa=101_325.0 + 50e5)
    r_low = await _run(state_low)
    r_mid = await _run(state_mid)
    assert r_mid.outputs["cost_usd"] > r_low.outputs["cost_usd"]


@pytest.mark.asyncio
async def test_exotic_material_higher_cost():
    """T5.6: CS/Ti > CS/SS304 > CS/CS."""
    state_cs = _base_state()
    state_ss = _base_state(tube_material="stainless_304")
    state_ti = _base_state(tube_material="titanium")
    r_cs = await _run(state_cs)
    r_ss = await _run(state_ss)
    r_ti = await _run(state_ti)
    assert r_ti.outputs["cost_usd"] > r_ss.outputs["cost_usd"] > r_cs.outputs["cost_usd"]


@pytest.mark.asyncio
async def test_atmospheric_fp_is_one():
    """T5.7: Atmospheric pressure → F_P = 1.0."""
    state = _base_state(P_hot_Pa=101_325.0, P_cold_Pa=101_325.0)
    result = await _run(state)
    assert result.outputs["cost_breakdown"]["F_P"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_aes_maps_to_floating():
    """T5.8: AES maps to floating_head K-constants."""
    state = _base_state(tema_type="AES")
    result = await _run(state)
    assert result.outputs["cost_breakdown"]["turton_row"] == "floating_head"


@pytest.mark.asyncio
async def test_ael_maps_to_fixed():
    """T5.9: AEL maps to fixed_tube."""
    state = _base_state(tema_type="AEL")
    result = await _run(state)
    assert result.outputs["cost_breakdown"]["turton_row"] == "fixed_tube"


@pytest.mark.asyncio
async def test_aew_maps_to_floating():
    """T5.10: AEW maps to floating_head."""
    state = _base_state(tema_type="AEW")
    result = await _run(state)
    assert result.outputs["cost_breakdown"]["turton_row"] == "floating_head"


# ═══════════════════════════════════════════════════════════════════
# Precondition failures
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_missing_area_raises():
    """T5.11: Missing area_provided_m2 → CalculationError."""
    state = _base_state(area_provided_m2=None)
    with pytest.raises(CalculationError):
        await _run(state)


@pytest.mark.asyncio
async def test_missing_tema_raises():
    """T5.12: Missing tema_type → CalculationError."""
    state = _base_state(tema_type=None)
    with pytest.raises(CalculationError):
        await _run(state)


@pytest.mark.asyncio
async def test_none_pressures_fallback():
    """T5.13: None pressures → defaults to atmospheric; F_P = 1.0."""
    state = _base_state(P_hot_Pa=None, P_cold_Pa=None)
    result = await _run(state)
    assert result.outputs["cost_breakdown"]["F_P"] == pytest.approx(1.0)
    assert result.outputs["cost_usd"] > 0


@pytest.mark.asyncio
async def test_missing_shell_material_default():
    """T5.14: Missing shell_material → defaults to carbon_steel."""
    state = _base_state(shell_material=None)
    result = await _run(state)
    assert result.outputs["cost_breakdown"]["shell_material"] == "carbon_steel"


@pytest.mark.asyncio
async def test_missing_tube_material_default():
    """T5.15: Missing tube_material → defaults to carbon_steel."""
    state = _base_state(tube_material=None)
    result = await _run(state)
    assert result.outputs["cost_breakdown"]["tube_material"] == "carbon_steel"


# ═══════════════════════════════════════════════════════════════════
# Warnings and edge cases
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_area_below_turton_min():
    """T5.16: Area = 5 m² → warning, cost still calculated."""
    state = _base_state(area_provided_m2=5.0)
    result = await _run(state)
    assert result.outputs["cost_usd"] > 0
    assert not result.outputs["cost_breakdown"]["area_in_valid_range"]
    assert any("outside Turton" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_area_above_turton_max():
    """T5.17: Area = 2000 m² → warning, cost still calculated."""
    state = _base_state(area_provided_m2=2000.0)
    result = await _run(state)
    assert result.outputs["cost_usd"] > 0
    assert not result.outputs["cost_breakdown"]["area_in_valid_range"]


@pytest.mark.asyncio
async def test_pressure_above_140_clamped():
    """T5.18: P = 200 barg → clamped to 140, warning emitted."""
    state = _base_state(P_hot_Pa=101_325.0 + 200e5)  # 200 barg
    result = await _run(state)
    assert any("exceeds" in w or "clamped" in w for w in result.warnings)
    # F_P should be computed at 140 barg (not 200)
    assert result.outputs["cost_breakdown"]["pressure_barg"] == pytest.approx(140.0)


@pytest.mark.asyncio
async def test_unknown_material_combo_interpolated():
    """T5.19: Unknown combo → interpolated F_M + warning."""
    state = _base_state(
        shell_material="duplex_2205",
        tube_material="duplex_2205",
    )
    result = await _run(state)
    bd = result.outputs["cost_breakdown"]
    assert bd["F_M_interpolated"] is True
    assert any("interpolated" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_cepci_staleness_detection():
    """T5.20: CEPCI staleness is detected (if > 90 days since update)."""
    state = _base_state()
    result = await _run(state)
    bd = result.outputs["cost_breakdown"]
    # We can't control the date, but the field should be present
    assert "cepci_stale" in bd
    assert isinstance(bd["cepci_stale"], bool)


# ═══════════════════════════════════════════════════════════════════
# AI trigger conditions
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ai_trigger_cost_per_m2_out_of_range():
    """T5.21: _conditional_ai_trigger True when cost/m² out of range."""
    step = Step15CostEstimate()
    state = _base_state()
    state.cost_breakdown = {"cost_per_m2_usd": 10.0, "tube_material": "carbon_steel"}
    assert step._conditional_ai_trigger(state) is True


@pytest.mark.asyncio
async def test_ai_trigger_cepci_stale():
    """T5.22: _conditional_ai_trigger True when CEPCI stale."""
    step = Step15CostEstimate()
    state = _base_state()
    state.cost_breakdown = {
        "cost_per_m2_usd": 500.0,
        "tube_material": "carbon_steel",
        "cepci_stale": True,
    }
    assert step._conditional_ai_trigger(state) is True


@pytest.mark.asyncio
async def test_ai_trigger_area_out_of_range():
    """T5.23: _conditional_ai_trigger True when area out of range."""
    step = Step15CostEstimate()
    state = _base_state()
    state.cost_breakdown = {
        "cost_per_m2_usd": 500.0,
        "tube_material": "carbon_steel",
        "area_in_valid_range": False,
    }
    assert step._conditional_ai_trigger(state) is True


@pytest.mark.asyncio
async def test_ai_trigger_fm_interpolated():
    """T5.24: _conditional_ai_trigger True when F_M interpolated."""
    step = Step15CostEstimate()
    state = _base_state()
    state.cost_breakdown = {
        "cost_per_m2_usd": 500.0,
        "tube_material": "carbon_steel",
        "F_M_interpolated": True,
    }
    assert step._conditional_ai_trigger(state) is True


@pytest.mark.asyncio
async def test_ai_trigger_false_when_normal():
    """T5.25: _conditional_ai_trigger False when everything normal."""
    step = Step15CostEstimate()
    state = _base_state()
    state.cost_breakdown = {
        "cost_per_m2_usd": 500.0,
        "tube_material": "carbon_steel",
        "cepci_stale": False,
        "area_in_valid_range": True,
        "F_M_interpolated": False,
    }
    assert step._conditional_ai_trigger(state) is False


# ═══════════════════════════════════════════════════════════════════
# Step metadata
# ═══════════════════════════════════════════════════════════════════

def test_step_metadata():
    """T5.26: Step metadata correct."""
    step = Step15CostEstimate()
    assert step.step_id == 15
    assert step.step_name == "Cost Estimate"
    assert step.ai_mode == AIModeEnum.CONDITIONAL


def test_convergence_loop_skips_ai():
    """T5.27: In convergence loop → AI skipped."""
    step = Step15CostEstimate()
    state = _base_state(in_convergence_loop=True)
    assert step._should_call_ai(state) is False


# ═══════════════════════════════════════════════════════════════════
# Breakdown schema validation
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_breakdown_has_all_keys():
    """T5.28: cost_breakdown has all expected keys."""
    state = _base_state()
    result = await _run(state)
    bd = result.outputs["cost_breakdown"]
    expected_keys = {
        "area_m2", "turton_row", "K1", "K2", "K3", "Cp0_2001_usd",
        "pressure_barg", "pressure_regime", "C1", "C2", "C3", "F_P",
        "shell_material", "tube_material", "F_M", "F_M_interpolated",
        "B1", "B2", "bare_module_factor", "C_BM_2001_usd",
        "cepci_base_year", "cepci_base_value", "cepci_current_year",
        "cepci_current_value", "cepci_ratio", "cepci_stale",
        "cepci_stale_days", "C_BM_2026_usd", "cost_per_m2_usd",
        "area_in_valid_range", "warnings",
    }
    assert set(bd.keys()) == expected_keys


# ═══════════════════════════════════════════════════════════════════
# Pressure regime selection
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_pressure_regime_tube_only():
    """T5.29: Shell near atmospheric, tube high → 'tube_only' regime."""
    state = _base_state(
        P_hot_Pa=101_325.0,         # Shell at atmospheric (hot side on shell)
        P_cold_Pa=101_325.0 + 20e5, # Tube at 20 barg
    )
    result = await _run(state)
    assert result.outputs["cost_breakdown"]["pressure_regime"] == "tube_only"


@pytest.mark.asyncio
async def test_sa516_treated_as_cs():
    """T5.30: sa516_gr70 shell + SS316 tubes → F_M = 1.9 (not interpolated)."""
    state = _base_state(
        shell_material="sa516_gr70",
        tube_material="stainless_316",
    )
    result = await _run(state)
    bd = result.outputs["cost_breakdown"]
    assert bd["F_M"] == pytest.approx(1.9)
    assert bd["F_M_interpolated"] is False
