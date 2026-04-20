"""P2-12 — Toxic helpers + tube-side allocation + double-tubesheet flag.

Bug ref:  artifacts/bugs/bug_p2_12_step04_toxic_fluids_no_allocation_rule.md
Plan ref: artifacts/plans/implementation_plan_p2_12_step04_toxic_tube_side_allocation.md
"""

from __future__ import annotations

from hx_engine.app.models.design_state import DesignState, FluidProperties
from hx_engine.app.steps.step_04_tema_geometry import (
    _allocate_fluids,
    _is_highly_toxic,
    _is_toxic,
)


def _props() -> FluidProperties:
    return FluidProperties(
        density_kg_m3=1000.0, viscosity_Pa_s=1e-3,
        cp_J_kgK=4180.0, k_W_mK=0.6, Pr=7.0,
    )


def _state(hot_name: str, cold_name: str) -> DesignState:
    return DesignState(
        hot_fluid_name=hot_name, cold_fluid_name=cold_name,
        T_hot_in_C=120.0, T_hot_out_C=60.0,
        T_cold_in_C=30.0, T_cold_out_C=70.0,
        hot_fluid_props=_props(), cold_fluid_props=_props(),
        Q_W=1e6, m_dot_hot_kg_s=10.0, m_dot_cold_kg_s=12.0,
    )


# ── Helper predicates ────────────────────────────────────────────

def test_is_toxic_true_for_h2s_blend():
    assert _is_toxic("sour gas (H2S 5 mol%)")


def test_is_toxic_false_for_water():
    assert not _is_toxic("water")


def test_highly_toxic_phosgene_yes_ammonia_no():
    assert _is_highly_toxic("phosgene")
    assert not _is_highly_toxic("liquid ammonia")


# ── Allocator branch ─────────────────────────────────────────────

def test_toxic_hot_routes_to_tube_side():
    state = _state("sour gas (H2S 5 mol%)", "water")
    shell_side, warns = _allocate_fluids(state)
    assert shell_side == "cold"
    assert any("toxic hot fluid" in w for w in warns)


def test_toxic_cold_routes_to_tube_side():
    state = _state("methane", "liquid ammonia")
    shell_side, _ = _allocate_fluids(state)
    assert shell_side == "hot"


def test_toxic_precedence_over_corrosive():
    """Toxic on one side, corrosive on the other → toxic wins."""
    state = _state("ammonia vapor", "30% sulfuric acid")
    shell_side, warns = _allocate_fluids(state)
    # Ammonia (toxic) goes tube-side regardless of acid (corrosive) on cold.
    assert shell_side == "cold"
    assert any("toxic hot fluid" in w for w in warns)


# ── Double-tubesheet flag ────────────────────────────────────────

def test_phosgene_sets_double_tubesheet_flag():
    state = _state("phosgene", "water")
    _allocate_fluids(state)
    assert state.requires_double_tubesheet_review is True


def test_h2s_does_not_set_double_tubesheet_flag():
    state = _state("sour gas (H2S 5 mol%)", "water")
    _allocate_fluids(state)
    assert state.requires_double_tubesheet_review is False


def test_default_state_flag_is_false():
    state = _state("water", "ethanol")
    _allocate_fluids(state)
    assert state.requires_double_tubesheet_review is False
