"""P2-16 — Bundle-to-shell clearance applied in Step 4; flag and outputs.

Bug ref:  artifacts/bugs/bug_p2_16_step04_bundle_to_shell_clearance_never_applied.md
Plan ref: artifacts/plans/implementation_plan_p2_16_step04_bundle_to_shell_clearance.md
"""

from __future__ import annotations

import pytest

from hx_engine.app.data.tema_tables import (
    BUNDLE_TO_SHELL_CLEARANCE_M,
    get_bundle_to_shell_clearance_m,
)
from hx_engine.app.models.design_state import DesignState, FluidProperties
from hx_engine.app.steps.step_04_tema_geometry import (
    VALID_TEMA_TYPES,
    Step04TEMAGeometry,
)


def _props() -> FluidProperties:
    return FluidProperties(
        density_kg_m3=1000.0, viscosity_Pa_s=1e-3,
        cp_J_kgK=4180.0, k_W_mK=0.6, Pr=7.0,
    )


# ── Lookup table ────────────────────────────────────────────────

def test_all_valid_tema_types_have_clearance_entry():
    missing = VALID_TEMA_TYPES - BUNDLE_TO_SHELL_CLEARANCE_M.keys()
    assert not missing, f"missing clearance entries for {missing}"


def test_unknown_tema_type_raises_keyerror():
    with pytest.raises(KeyError):
        get_bundle_to_shell_clearance_m("AEL")


def test_clearance_ordering_floating_heads_largest():
    # Fixed tubesheet (BEM) = 0; AEW (externally sealed) is the largest.
    assert BUNDLE_TO_SHELL_CLEARANCE_M["BEM"] == 0.0
    assert BUNDLE_TO_SHELL_CLEARANCE_M["AEW"] >= BUNDLE_TO_SHELL_CLEARANCE_M["AES"]
    assert BUNDLE_TO_SHELL_CLEARANCE_M["AES"] >= BUNDLE_TO_SHELL_CLEARANCE_M["AEU"]


# ── Step 4 finalisation ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_bem_zero_clearance_shell_unchanged():
    step = Step04TEMAGeometry()
    state = DesignState(
        hot_fluid_name="water", cold_fluid_name="water",
        T_hot_in_C=80, T_hot_out_C=60,
        T_cold_in_C=30, T_cold_out_C=50,
        hot_fluid_props=_props(), cold_fluid_props=_props(),
        Q_W=1e6, m_dot_hot_kg_s=10.0, m_dot_cold_kg_s=12.0,
    )
    result = await step.execute(state)
    assert result.outputs["tema_type"] == "BEM"
    assert result.outputs["bundle_to_shell_clearance_m"] == 0.0
    assert result.outputs["shell_id_initial_m"] == result.outputs["shell_id_final_m"]
    assert state.shell_id_finalised is True


@pytest.mark.asyncio
async def test_aes_thirty_mm_clearance_grows_shell():
    step = Step04TEMAGeometry()
    state = DesignState(
        hot_fluid_name="crude oil", cold_fluid_name="water",
        T_hot_in_C=200, T_hot_out_C=120,
        T_cold_in_C=30, T_cold_out_C=70,
        hot_fluid_props=FluidProperties(
            density_kg_m3=830, viscosity_Pa_s=0.005,
            cp_J_kgK=2200, k_W_mK=0.12, Pr=92.0,
        ),
        cold_fluid_props=_props(),
        Q_W=2e6, m_dot_hot_kg_s=10.0, m_dot_cold_kg_s=12.0,
    )
    result = await step.execute(state)
    if result.outputs["tema_type"] != "AES":
        pytest.skip(f"deterministic selector picked {result.outputs['tema_type']}")
    assert result.outputs["bundle_to_shell_clearance_m"] == 0.030
    assert (
        result.outputs["shell_id_final_m"]
        - result.outputs["shell_id_initial_m"]
        == pytest.approx(0.030, abs=1e-9)
    )
    assert state.shell_id_finalised is True


@pytest.mark.asyncio
async def test_audit_trail_fields_always_populated():
    step = Step04TEMAGeometry()
    state = DesignState(
        hot_fluid_name="water", cold_fluid_name="water",
        T_hot_in_C=80, T_hot_out_C=60,
        T_cold_in_C=30, T_cold_out_C=50,
        hot_fluid_props=_props(), cold_fluid_props=_props(),
        Q_W=1e6, m_dot_hot_kg_s=10.0, m_dot_cold_kg_s=12.0,
    )
    result = await step.execute(state)
    for field in (
        "shell_id_initial_m",
        "bundle_to_shell_clearance_m",
        "shell_id_final_m",
        "shell_id_finalised",
    ):
        assert field in result.outputs


@pytest.mark.asyncio
async def test_geometry_shell_diameter_matches_final():
    step = Step04TEMAGeometry()
    state = DesignState(
        hot_fluid_name="water", cold_fluid_name="water",
        T_hot_in_C=80, T_hot_out_C=60,
        T_cold_in_C=30, T_cold_out_C=50,
        hot_fluid_props=_props(), cold_fluid_props=_props(),
        Q_W=1e6, m_dot_hot_kg_s=10.0, m_dot_cold_kg_s=12.0,
    )
    result = await step.execute(state)
    geom = result.outputs["geometry"]
    assert geom.shell_diameter_m == result.outputs["shell_id_final_m"]
