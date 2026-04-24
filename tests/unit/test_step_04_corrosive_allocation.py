"""P2-11 — Corrosive helpers + tube-side allocation.

Bug ref:  artifacts/bugs/bug_p2_11_step04_corrosive_fluids_not_allocated_tube_side.md
Plan ref: artifacts/plans/implementation_plan_p2_11_step04_corrosive_tube_side_allocation.md
"""

from __future__ import annotations

from hx_engine.app.models.design_state import DesignState, FluidProperties
from hx_engine.app.steps.step_04_tema_geometry import (
    _CORROSIVE_KEYWORDS,
    _CORROSIVE_SEVERITY_GROUPS,
    _allocate_fluids,
    _corrosive_severity_rank,
    _is_corrosive,
)


def _props(mu: float = 0.001) -> FluidProperties:
    return FluidProperties(
        density_kg_m3=1000.0,
        viscosity_Pa_s=mu,
        cp_J_kgK=4180.0,
        k_W_mK=0.6,
        Pr=mu * 4180.0 / 0.6,
    )


def _state(hot_name: str, cold_name: str, **kw) -> DesignState:
    return DesignState(
        hot_fluid_name=hot_name,
        cold_fluid_name=cold_name,
        T_hot_in_C=120.0, T_hot_out_C=60.0,
        T_cold_in_C=30.0, T_cold_out_C=70.0,
        hot_fluid_props=_props(), cold_fluid_props=_props(),
        Q_W=1e6, m_dot_hot_kg_s=10.0, m_dot_cold_kg_s=12.0,
        **kw,
    )


# ── Helper predicates ────────────────────────────────────────────

def test_is_corrosive_true_for_acid():
    assert _is_corrosive("30% sulfuric acid")


def test_is_corrosive_false_for_water():
    assert not _is_corrosive("water")


def test_is_corrosive_handles_none_defensively():
    assert not _is_corrosive(None)


def test_severity_hf_more_aggressive_than_h2so4():
    assert _corrosive_severity_rank("anhydrous HF") < _corrosive_severity_rank("H2SO4")


def test_severity_h2so4_more_aggressive_than_caustic():
    assert _corrosive_severity_rank("H2SO4") < _corrosive_severity_rank("caustic soda")


def test_severity_unknown_returns_max_index():
    assert _corrosive_severity_rank("water") == len(_CORROSIVE_SEVERITY_GROUPS)


def test_keyword_set_is_immutable_frozenset():
    assert isinstance(_CORROSIVE_KEYWORDS, frozenset)


# ── Allocator branch ─────────────────────────────────────────────

def test_corrosive_hot_routes_to_tube_side():
    state = _state("30% sulfuric acid", "water")
    shell_side, warns = _allocate_fluids(state)
    assert shell_side == "cold"  # cold on shell ⇒ acid on tube
    assert any("corrosive hot fluid" in w for w in warns)


def test_corrosive_cold_routes_to_tube_side():
    state = _state("hydrocarbon vapor", "caustic soda")
    shell_side, _ = _allocate_fluids(state)
    assert shell_side == "hot"  # hot on shell ⇒ caustic on tube


def test_both_corrosive_routes_more_aggressive_to_tubes():
    # 'sulfuric' (rank 6) is more aggressive than 'caustic' (rank 10).
    # Both non-toxic, so the corrosive branch (not the toxic branch) decides.
    state = _state("30% sulfuric acid", "caustic soda")
    shell_side, warns = _allocate_fluids(state)
    assert shell_side == "cold"  # sulfuric (more aggressive) on tube
    assert any("more" in w.lower() and "aggressive" in w.lower() for w in warns)
