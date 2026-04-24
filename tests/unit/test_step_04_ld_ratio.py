"""P2-15 — L/D ratio computation, WARN bands, and ESCALATE rule.

Bug ref:  artifacts/bugs/bug_p2_15_step04_no_ld_ratio_check.md
Plan ref: artifacts/plans/implementation_plan_p2_15_step04_ld_ratio_check.md
"""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_04_rules import (
    LD_RATIO_HIGH_ESCALATE,
    LD_RATIO_LOW_ESCALATE,
    _rule_ld_ratio_within_extremes,
)
from hx_engine.app.steps.step_04_tema_geometry import (
    LD_RATIO_HIGH_WARN,
    LD_RATIO_LOW_WARN,
    Step04TEMAGeometry,
)
from hx_engine.app.steps.step_12_convergence import _check_ld_band_after_adjustment


def _props() -> FluidProperties:
    return FluidProperties(
        density_kg_m3=1000.0, viscosity_Pa_s=1e-3,
        cp_J_kgK=4180.0, k_W_mK=0.6, Pr=7.0,
    )


def _state(**overrides) -> DesignState:
    base = dict(
        hot_fluid_name="water", cold_fluid_name="water",
        T_hot_in_C=80, T_hot_out_C=60,
        T_cold_in_C=30, T_cold_out_C=50,
        hot_fluid_props=_props(), cold_fluid_props=_props(),
        Q_W=1e6, m_dot_hot_kg_s=10.0, m_dot_cold_kg_s=12.0,
    )
    base.update(overrides)
    return DesignState(**base)


# ── Constants sanity ────────────────────────────────────────────

def test_warn_band_inside_escalate_band():
    assert LD_RATIO_LOW_ESCALATE < LD_RATIO_LOW_WARN
    assert LD_RATIO_HIGH_WARN < LD_RATIO_HIGH_ESCALATE


# ── Step 4 execute() exposes LD_ratio ───────────────────────────

@pytest.mark.asyncio
async def test_execute_emits_ld_ratio_in_outputs():
    step = Step04TEMAGeometry()
    state = _state()
    result = await step.execute(state)
    assert "LD_ratio" in result.outputs
    ld = result.outputs["LD_ratio"]
    assert ld is not None
    assert ld > 0


# ── Layer-2 rule: ESCALATE band [3, 15] ─────────────────────────

def _result_with_ld(ld: float | None) -> StepResult:
    geom = GeometrySpec(
        tube_od_m=0.0254, tube_id_m=0.0212,
        tube_length_m=4.0, pitch_ratio=1.25,
        n_tubes=100, n_passes=2, shell_passes=1,
        shell_diameter_m=0.4, baffle_cut=0.25,
        baffle_spacing_m=0.2, pitch_layout="triangular",
    )
    return StepResult(
        step_id=4, step_name="x",
        outputs={"geometry": geom, "tema_type": "BEM", "LD_ratio": ld},
    )


def test_ld_rule_passes_inside_band():
    ok, msg = _rule_ld_ratio_within_extremes(4, _result_with_ld(9.0))
    assert ok and msg is None


def test_ld_rule_fails_below_low_extreme():
    ok, msg = _rule_ld_ratio_within_extremes(4, _result_with_ld(2.5))
    assert not ok
    assert "outside" in msg


def test_ld_rule_fails_above_high_extreme():
    ok, msg = _rule_ld_ratio_within_extremes(4, _result_with_ld(18.0))
    assert not ok
    assert "outside" in msg


def test_ld_rule_defensive_pass_when_field_missing():
    ok, msg = _rule_ld_ratio_within_extremes(4, _result_with_ld(None))
    assert ok and msg is None


# ── Step 12 re-check helper ─────────────────────────────────────

def test_step12_recheck_returns_none_inside_band():
    geom = GeometrySpec(tube_length_m=4.0, shell_diameter_m=0.5)
    assert _check_ld_band_after_adjustment(geom) is None


def test_step12_recheck_warns_below_low_band():
    geom = GeometrySpec(tube_length_m=2.0, shell_diameter_m=0.6)  # L/D ≈ 3.3
    msg = _check_ld_band_after_adjustment(geom)
    assert msg is not None and "below" in msg


def test_step12_recheck_warns_above_high_band():
    geom = GeometrySpec(tube_length_m=6.0, shell_diameter_m=0.4)  # L/D = 15
    msg = _check_ld_band_after_adjustment(geom)
    assert msg is not None and "above" in msg


def test_step12_recheck_handles_incomplete_geometry():
    assert _check_ld_band_after_adjustment(None) is None
    assert _check_ld_band_after_adjustment(GeometrySpec(tube_length_m=4.0)) is None
