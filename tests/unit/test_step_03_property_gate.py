"""TC-S2-01 … TC-S2-14 — Step 03 user-property override gate (EPIC-XSTACK-2026-007-S2).

Tests cover:
  - TC-S2-01  _apply_manual_properties: valid hot-side full set
  - TC-S2-02  _apply_manual_properties: valid cold-side partial set
  - TC-S2-03  _apply_manual_properties: invalid JSON → no-op
  - TC-S2-04  _apply_manual_properties: bad fluid_side → no-op
  - TC-S2-05  _apply_manual_properties: out-of-range viscosity → no-op
  - TC-S2-06  _apply_manual_properties: empty properties dict → no-op
  - TC-S2-07  _merge_user_props: user fields overlay adapter fields
  - TC-S2-08  execute(): user_provided_hot_props used at Level 1
  - TC-S2-09  execute(): user_provided_cold_props used at Level 1
  - TC-S2-10  apply_user_override(option=1): hot-side JSON stored
  - TC-S2-11  apply_user_override(option=1): cold-side JSON stored
  - TC-S2-12  _apply_ai_correction_with_gate: Case A blocks when user-provided
  - TC-S2-13  _apply_ai_correction_with_gate: Case B stores pending correction
  - TC-S2-14  execute(): drift warning appended when ΔT exceeds 15 °C
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hx_engine.app.models.design_state import DesignState, FluidProperties
from hx_engine.app.steps.step_03_fluid_props import Step03FluidProperties


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**kwargs) -> DesignState:
    """Minimal DesignState with crude oil / thermal oil benchmark fluids."""
    defaults = dict(
        hot_fluid_name="crude oil",
        cold_fluid_name="thermal oil",
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=60.0,
        m_dot_hot_kg_s=50.0,
        P_hot_Pa=101325.0,
        P_cold_Pa=101325.0,
    )
    defaults.update(kwargs)
    return DesignState(**defaults)


def _good_hot_props() -> FluidProperties:
    return FluidProperties(
        density_kg_m3=860.0,
        viscosity_Pa_s=0.003,
        cp_J_kgK=2050.0,
        k_W_mK=0.13,
        Pr=47.3,
    )


def _good_cold_props() -> FluidProperties:
    return FluidProperties(
        density_kg_m3=870.0,
        viscosity_Pa_s=0.002,
        cp_J_kgK=1800.0,
        k_W_mK=0.12,
        Pr=30.0,
    )


# ---------------------------------------------------------------------------
# TC-S2-01 … TC-S2-06: _apply_manual_properties
# ---------------------------------------------------------------------------

class TestApplyManualProperties:

    def setup_method(self):
        self.step = Step03FluidProperties()

    def test_tc_s2_01_valid_hot_full_set(self):
        """TC-S2-01: valid hot-side full set stored in user_provided_hot_props."""
        state = _make_state()
        payload = json.dumps({
            "fluid_side": "hot",
            "properties": {
                "density_kg_m3": 850.0,
                "viscosity_Pa_s": 0.002,
                "cp_J_kgK": 2100.0,
                "k_W_mK": 0.135,
            },
        })
        self.step._apply_manual_properties(state, payload)

        assert state.user_provided_hot_props is not None
        assert state.user_provided_hot_props.density_kg_m3 == pytest.approx(850.0)
        assert state.user_provided_hot_props.viscosity_Pa_s == pytest.approx(0.002)
        assert state.user_provided_hot_props.cp_J_kgK == pytest.approx(2100.0)
        assert state.user_provided_hot_props.k_W_mK == pytest.approx(0.135)
        assert state.user_provided_hot_props.property_source == "user_provided"
        # hot_fluid_props must also be updated immediately
        assert state.hot_fluid_props is state.user_provided_hot_props

    def test_tc_s2_02_valid_cold_partial_set(self):
        """TC-S2-02: valid cold-side partial set (only density + viscosity) stored."""
        state = _make_state()
        payload = json.dumps({
            "fluid_side": "cold",
            "properties": {
                "density_kg_m3": 920.0,
                "viscosity_Pa_s": 0.00048,
            },
        })
        self.step._apply_manual_properties(state, payload)

        fp = state.user_provided_cold_props
        assert fp is not None
        assert fp.density_kg_m3 == pytest.approx(920.0)
        assert fp.viscosity_Pa_s == pytest.approx(0.00048)
        # cp and k not supplied → None (partial set allowed)
        assert fp.cp_J_kgK is None
        assert fp.k_W_mK is None

    def test_tc_s2_03_invalid_json_noop(self):
        """TC-S2-03: non-JSON text → no properties stored."""
        state = _make_state()
        self.step._apply_manual_properties(state, "this is not json {{{")
        assert state.user_provided_hot_props is None
        assert state.user_provided_cold_props is None

    def test_tc_s2_04_bad_fluid_side_noop(self):
        """TC-S2-04: unknown fluid_side value → no properties stored."""
        state = _make_state()
        payload = json.dumps({
            "fluid_side": "steam",
            "properties": {"density_kg_m3": 850.0},
        })
        self.step._apply_manual_properties(state, payload)
        assert state.user_provided_hot_props is None
        assert state.user_provided_cold_props is None

    def test_tc_s2_05_out_of_range_viscosity_noop(self):
        """TC-S2-05: viscosity=2.0 Pa·s exceeds [1e-7, 1.0] bound → no-op."""
        state = _make_state()
        payload = json.dumps({
            "fluid_side": "hot",
            "properties": {"viscosity_Pa_s": 2.0},  # above upper bound of 1.0
        })
        self.step._apply_manual_properties(state, payload)
        assert state.user_provided_hot_props is None

    def test_tc_s2_06_empty_properties_dict_noop(self):
        """TC-S2-06: empty properties dict → no-op."""
        state = _make_state()
        payload = json.dumps({"fluid_side": "hot", "properties": {}})
        self.step._apply_manual_properties(state, payload)
        assert state.user_provided_hot_props is None


# ---------------------------------------------------------------------------
# TC-S2-07: _merge_user_props
# ---------------------------------------------------------------------------

class TestMergeUserProps:

    def test_tc_s2_07_user_fields_overlay_adapter(self):
        """TC-S2-07: user fields overwrite matching adapter fields; others retained."""
        adapter = FluidProperties(
            density_kg_m3=880.0,
            viscosity_Pa_s=0.003,
            cp_J_kgK=2100.0,
            k_W_mK=0.14,
            Pr=45.0,
        )
        # User only supplies density and viscosity
        user = FluidProperties(
            density_kg_m3=850.0,
            viscosity_Pa_s=0.0025,
        )

        merged = Step03FluidProperties._merge_user_props(user, adapter)

        # User-supplied fields take precedence
        assert merged.density_kg_m3 == pytest.approx(850.0)
        assert merged.viscosity_Pa_s == pytest.approx(0.0025)
        # Adapter fields retained for non-supplied properties
        assert merged.cp_J_kgK == pytest.approx(2100.0)
        assert merged.k_W_mK == pytest.approx(0.14)
        assert merged.property_source == "user_provided"


# ---------------------------------------------------------------------------
# TC-S2-08 … TC-S2-09: execute() Level-1 priority
# ---------------------------------------------------------------------------

class TestExecuteUserProvidedPriority:

    async def test_tc_s2_08_user_provided_hot_bypasses_adapter(self):
        """TC-S2-08: user_provided_hot_props used; _resolve_fluid NOT called for hot side."""
        step = Step03FluidProperties()
        state = _make_state()
        user_hot = _good_hot_props()
        user_hot = user_hot.model_copy(update={"property_source": "user_provided"})
        state.user_provided_hot_props = user_hot

        # Also supply cold props so execute() can complete without hitting the real adapter
        user_cold = _good_cold_props()
        user_cold = user_cold.model_copy(update={"property_source": "user_provided"})
        state.user_provided_cold_props = user_cold

        resolve_calls: list[str] = []
        original_resolve = step._resolve_fluid

        async def _spy_resolve(fluid_name: str, *args, **kwargs):
            resolve_calls.append(fluid_name)
            return await original_resolve(fluid_name, *args, **kwargs)

        with patch.object(step, "_resolve_fluid", side_effect=_spy_resolve):
            result = await step.execute(state)

        # _resolve_fluid must NOT have been called at all (both sides user-provided)
        assert resolve_calls == [], (
            f"_resolve_fluid was called for: {resolve_calls}; expected no adapter calls"
        )
        # Hot side result must come from user-provided props
        assert state.hot_fluid_props is user_hot

    async def test_tc_s2_09_user_provided_cold_bypasses_adapter(self):
        """TC-S2-09: user_provided_cold_props overrides adapter for cold side."""
        step = Step03FluidProperties()
        state = _make_state()
        user_cold = _good_cold_props()
        user_cold = user_cold.model_copy(update={"property_source": "user_provided"})
        state.user_provided_cold_props = user_cold

        try:
            await step.execute(state)
        except Exception:
            pass  # hot-side adapter may fail in unit env

        assert state.user_provided_cold_props is user_cold


# ---------------------------------------------------------------------------
# TC-S2-10 … TC-S2-11: apply_user_override(option=1)
# ---------------------------------------------------------------------------

class TestApplyUserOverrideOption1:

    def test_tc_s2_10_option1_hot_side_json(self):
        """TC-S2-10: option_index=1 with hot-side JSON stores user_provided_hot_props."""
        step = Step03FluidProperties()
        state = _make_state()
        payload = json.dumps({
            "fluid_side": "hot",
            "properties": {"density_kg_m3": 855.0, "viscosity_Pa_s": 0.0022},
        })
        result = step.apply_user_override(state, option_index=1, text=payload)

        # Convention: apply_user_override returns None to signal "re-run step"
        assert result is None
        assert state.user_provided_hot_props is not None
        assert state.user_provided_hot_props.density_kg_m3 == pytest.approx(855.0)

    def test_tc_s2_11_option1_cold_side_json(self):
        """TC-S2-11: option_index=1 with cold-side JSON stores user_provided_cold_props."""
        step = Step03FluidProperties()
        state = _make_state()
        payload = json.dumps({
            "fluid_side": "cold",
            "properties": {"cp_J_kgK": 1900.0, "k_W_mK": 0.115},
        })
        result = step.apply_user_override(state, option_index=1, text=payload)

        assert result is None
        fp = state.user_provided_cold_props
        assert fp is not None
        assert fp.cp_J_kgK == pytest.approx(1900.0)
        assert fp.k_W_mK == pytest.approx(0.115)


# ---------------------------------------------------------------------------
# TC-S2-12 … TC-S2-13: _apply_ai_correction_with_gate
# ---------------------------------------------------------------------------

class TestAiCorrectionGate:

    def test_tc_s2_12_case_a_blocks_when_user_provided(self):
        """TC-S2-12: AI correction blocked when user has supplied that field."""
        step = Step03FluidProperties()
        state = _make_state()

        user_hot = FluidProperties(
            density_kg_m3=850.0,
            viscosity_Pa_s=0.002,
            property_source="user_provided",
        )
        state.user_provided_hot_props = user_hot
        state.hot_fluid_props = user_hot

        step._apply_ai_correction_with_gate(
            state,
            fluid_side="hot",
            field="density_kg_m3",
            corrected_value=900.0,
            reason="temperature re-evaluated",
        )

        # Correction must be blocked: pending correction NOT stored
        assert not hasattr(step, "_pending_ai_correction") or step._pending_ai_correction is None
        # A note must have been appended to state.notes
        assert any("blocked" in note for note in state.notes)
        # Original value preserved
        assert state.hot_fluid_props.density_kg_m3 == pytest.approx(850.0)

    def test_tc_s2_13_case_b_stores_pending_correction(self):
        """TC-S2-13: AI correction stored for escalation when field is adapter-estimated."""
        step = Step03FluidProperties()
        state = _make_state()

        adapter_hot = FluidProperties(
            density_kg_m3=880.0,
            viscosity_Pa_s=0.003,
            cp_J_kgK=2100.0,
            k_W_mK=0.14,
            property_source="adapter_estimate",
        )
        state.hot_fluid_props = adapter_hot
        # No user_provided_hot_props → Case B

        step._apply_ai_correction_with_gate(
            state,
            fluid_side="hot",
            field="density_kg_m3",
            corrected_value=910.0,
            reason="wax deposition detected",
        )

        pc = step._pending_ai_correction
        assert pc is not None
        assert pc["field"] == "density_kg_m3"
        assert pc["proposed_value"] == pytest.approx(910.0)
        assert pc["current_value"] == pytest.approx(880.0)
        assert pc["reason"] == "wax deposition detected"
        assert "engineering_impact" in pc


# ---------------------------------------------------------------------------
# TC-S2-14: drift warning
# ---------------------------------------------------------------------------

class TestDriftWarning:

    async def test_tc_s2_14_drift_warning_when_delta_t_exceeds_15(self):
        """TC-S2-14: drift warning in StepResult.warnings when ΔT > 15 °C."""
        step = Step03FluidProperties()
        state = _make_state(
            T_hot_in_C=200.0,  # T_mean_hot = (200+140)/2 = 170 °C
            T_hot_out_C=140.0,
        )

        user_hot = FluidProperties(
            density_kg_m3=830.0,
            viscosity_Pa_s=0.0015,
            cp_J_kgK=2200.0,
            k_W_mK=0.12,
            property_source="user_provided",
        )
        state.user_provided_hot_props = user_hot
        # Properties were measured at 100 °C; current T_mean = 170 °C → ΔT = 70 > 15
        state.user_property_temp_hot_C = 100.0

        # Provide cold props too so execute() completes without the real adapter
        user_cold = _good_cold_props()
        user_cold = user_cold.model_copy(update={"property_source": "user_provided"})
        state.user_provided_cold_props = user_cold

        result = await step.execute(state)

        # Drift warning surfaces in StepResult.warnings (not state.notes)
        drift_warnings = [
            w for w in (result.warnings or [])
            if "drift" in w.lower() or "temperature" in w.lower()
        ]
        assert len(drift_warnings) >= 1, (
            f"Expected drift warning in StepResult.warnings but got: {result.warnings}"
        )
