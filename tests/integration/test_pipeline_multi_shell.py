"""Cross-step propagation tests for P0-1: Step 11 multi-shell
`area_provided_m2` must flow through to Steps 12 (convergence),
15 (cost), and 16 (final validation / confidence).

Each test invokes the real step implementations (no hand-computed
ratios) so that any future regression in the area formula or in the
downstream consumers is caught immediately.

Step 16 finding (recorded per implementation plan Phase 2):
    `step_16_final_validation.py` does not reference `area_provided_m2`,
    `A_provided`, or `n_shells` — confirmed by repository-wide grep on
    20 April 2026. The bug-checklist item for Step 16 is therefore
    closed with justification, and a guard test below pins this fact
    so that any future Step 16 read of the area field is flagged.
"""

from __future__ import annotations

import inspect

import pytest

from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.steps import step_16_final_validation as step_16_module
from hx_engine.app.steps.step_11_area_overdesign import Step11AreaOverdesign
from hx_engine.app.steps.step_12_convergence import Step12Convergence
from hx_engine.app.steps.step_15_cost import Step15CostEstimate


def _state_for_n_shells(n_shells: int) -> DesignState:
    """Build a post-Step-10 DesignState parametrised by n_shells.

    Per-shell geometry is identical across calls — only n_shells varies —
    so any cost difference can only come from the corrected area formula.
    """
    hot = FluidProperties(
        density_kg_m3=850.0,
        viscosity_Pa_s=0.0012,
        specific_heat_J_kgK=2200.0,
        thermal_conductivity_W_mK=0.13,
        Pr=20.3,
    )
    cold = FluidProperties(
        density_kg_m3=995.0,
        viscosity_Pa_s=0.0008,
        specific_heat_J_kgK=4180.0,
        thermal_conductivity_W_mK=0.62,
        Pr=5.4,
    )
    return DesignState(
        T_hot_in_C=180.0,
        T_hot_out_C=80.0,
        T_cold_in_C=30.0,
        T_cold_out_C=45.0,
        hot_fluid_name="crude oil",
        cold_fluid_name="cooling water",
        m_dot_hot_kg_s=120.0,
        m_dot_cold_kg_s=400.0,
        hot_fluid_props=hot,
        cold_fluid_props=cold,
        shell_side_fluid="hot",
        P_hot_Pa=1_101_325.0,
        P_cold_Pa=501_325.0,
        tema_type="AES",
        tube_material="carbon_steel",
        shell_material="carbon_steel",
        convergence_converged=True,
        geometry=GeometrySpec(
            shell_diameter_m=0.737,
            tube_od_m=0.01905,
            tube_id_m=0.01483,
            tube_length_m=6.0,
            n_tubes=400,
            n_shells=n_shells,
            tube_pitch_m=0.02381,
            pitch_ratio=1.25,
            pitch_layout="triangular",
            n_passes=2,
            baffle_spacing_m=0.20,
            baffle_cut=0.25,
            n_baffles=25,
        ),
        Q_W=8_000_000.0,
        LMTD_K=40.0,
        F_factor=0.85,
        U_dirty_W_m2K=500.0,
    )


@pytest.mark.asyncio
async def test_step11_to_step15_cost_scales_with_n_shells():
    """Multi-shell area from Step 11 must drive a higher Step 15 cost."""
    state_1 = _state_for_n_shells(1)
    state_2 = _state_for_n_shells(2)

    await Step11AreaOverdesign().execute(state_1)
    await Step11AreaOverdesign().execute(state_2)

    cost_1 = (await Step15CostEstimate().execute(state_1)).outputs["cost_usd"]
    cost_2 = (await Step15CostEstimate().execute(state_2)).outputs["cost_usd"]

    assert state_2.area_provided_m2 == pytest.approx(2.0 * state_1.area_provided_m2, rel=1e-9)
    assert cost_2 > cost_1


@pytest.mark.asyncio
async def test_step11_area_propagates_into_state_for_step15():
    """Step 15 must consume the exact `area_provided_m2` Step 11 wrote."""
    state = _state_for_n_shells(3)

    await Step11AreaOverdesign().execute(state)
    cost_result = await Step15CostEstimate().execute(state)

    assert cost_result.outputs["cost_breakdown"]["area_m2"] == pytest.approx(
        state.area_provided_m2, rel=1e-12
    )


# ══════════════════════════════════════════════════════════════════════
# Step 12 — Convergence loop reads corrected `area_provided_m2`
# ══════════════════════════════════════════════════════════════════════

class TestStep12ConsumesMultiShellArea:
    """Step 12 reads `state.area_provided_m2` in two paths:
       (a) `_check_convergence` — via `state.overdesign_pct`, which Step 11
           computes from the corrected multi-shell area.
       (b) `_proportional_adjustment` — direct ratio
           `area_required_m2 / area_provided_m2` to scale `n_tubes`.

    These tests pin both paths against the post-Step-11 corrected value.
    """

    @pytest.mark.asyncio
    async def test_check_convergence_passes_with_multi_shell_corrected_overdesign(self):
        """After Step 11 with n_shells=2, overdesign lands in band → converges."""
        # 2-shell A_provided = π·0.01905·6.0·400·2 ≈ 287.3 m². Target ~17% overdesign
        # → A_required ≈ 245 m² → Q = 245 × 500 × 0.85 × 40 ≈ 4.17 MW.
        state = _state_for_n_shells(2)
        state.Q_W = 4_170_000.0
        state.U_dirty_W_m2K = 500.0
        state.F_factor = 0.85
        state.LMTD_K = 40.0
        # Other Step-12 convergence inputs (set deterministically).
        state.dP_tube_Pa = 45_000.0
        state.dP_shell_Pa = 95_000.0
        state.tube_velocity_m_s = 1.4

        await Step11AreaOverdesign().execute(state)

        assert 10.0 <= state.overdesign_pct <= 25.0
        assert Step12Convergence()._check_convergence(state, delta_U_pct=0.5) is True

    @pytest.mark.asyncio
    async def test_proportional_adjustment_uses_corrected_area_provided(self):
        """Same `area_required` against single- vs multi-shell `area_provided`
        must produce different `n_tubes` adjustments — proving Step 12 reads
        the corrected field, not a stale recomputation.
        """
        state_1 = _state_for_n_shells(1)
        state_2 = _state_for_n_shells(2)
        # Force underdesign on single-shell, comfort on multi-shell.
        for s in (state_1, state_2):
            s.Q_W = 20_000_000.0
            s.U_dirty_W_m2K = 500.0
            s.F_factor = 0.85
            s.LMTD_K = 40.0

        await Step11AreaOverdesign().execute(state_1)
        await Step11AreaOverdesign().execute(state_2)

        step12 = Step12Convergence()
        changes_1, _ = step12._compute_adjustment(
            state_1, iteration=1, violations=["underdesign"], last_direction={},
        )
        changes_2, _ = step12._compute_adjustment(
            state_2, iteration=1, violations=["underdesign"], last_direction={},
        )

        # _proportional_adjustment must emit n_tubes for an underdesign violation;
        # asserting presence prevents the forgiving fallback from masking a regression.
        assert "n_tubes" in changes_1 and "n_tubes" in changes_2
        # Single-shell sees larger A_required/A_provided ratio → larger n_tubes bump.
        assert changes_1["n_tubes"] > changes_2["n_tubes"]


# ══════════════════════════════════════════════════════════════════════
# Step 16 — does NOT consume `area_provided_m2` (documented finding)
# ══════════════════════════════════════════════════════════════════════

def test_step_16_module_does_not_reference_area_provided():
    """Guard test: Step 16 source code must not read `area_provided_m2` /
    `A_provided` / `n_shells`. If this assertion fails in the future,
    the cross-step propagation contract for area must be re-validated
    and a Step 16 propagation test added.
    """
    source = inspect.getsource(step_16_module)
    forbidden = ("area_provided_m2", "A_provided", "n_shells")
    leaked = [token for token in forbidden if token in source]
    assert leaked == [], (
        f"Step 16 now references {leaked} — add a propagation test that "
        f"covers Step 11 → Step 16 area accounting and update bug doc."
    )


# ══════════════════════════════════════════════════════════════════════
# Phase 3 — Multi-shell pipeline smoke (Steps 11 → 15)
# ══════════════════════════════════════════════════════════════════════

class TestMultiShellPipelineSmoke:
    """End-to-end smoke through the area-consuming half of the pipeline.

    The full 1→16 pipeline requires AI engineer + SSE manager scaffolding
    (see `core/pipeline_runner.py`). This smoke focuses on the steps that
    actually consume `area_provided_m2` — Steps 11 (writer), 12 (convergence
    check), and 15 (cost) — driven by the synthesised multi-shell repro
    from `bug_p0_1_step11_multishell_area_provided_wrong.md`.
    """

    @pytest.mark.asyncio
    async def test_multi_shell_repro_lands_in_overdesign_band(self):
        """Multi-shell crude-cooler repro lands `overdesign_pct` in 10–25%."""
        state = _state_for_n_shells(2)
        # See sibling test for the Q sizing rationale.
        state.Q_W = 4_170_000.0

        await Step11AreaOverdesign().execute(state)

        assert state.geometry.n_shells == 2
        assert 10.0 <= state.overdesign_pct <= 25.0

    @pytest.mark.asyncio
    async def test_multi_shell_repro_step11_layer2_passes_and_cost_completes(self):
        """Step 11 emits a Layer-2-passing result and Step 15 produces a cost."""
        # Importing step_11_rules triggers Layer-2 rule auto-registration.
        import hx_engine.app.steps.step_11_rules  # noqa: F401
        from hx_engine.app.core.validation_rules import check

        state = _state_for_n_shells(2)
        state.Q_W = 4_170_000.0

        step_11_result = await Step11AreaOverdesign().execute(state)
        layer2 = check(11, step_11_result)
        cost_result = await Step15CostEstimate().execute(state)

        assert layer2.passed is True
        assert cost_result.outputs["cost_usd"] > 0
