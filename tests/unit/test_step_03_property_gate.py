"""EPIC-XSTACK-2026-007-S1: Fluid Property Confidence Gate — unit tests.

Tests:
  TC-S1-01  Unknown fluid, AI confidence 0.45 → step_escalated (ESCALATE) with
            event_subtype="property_request"; DesignState unchanged.
  TC-S1-02  AI estimate confidence 0.75 ≥ threshold → pipeline continues; no
            escalation; property_source = "llm_estimated".
  TC-S1-03  Engineer approves AI estimate → property_source = "user_approved_estimate",
            approval_timestamp set; pipeline re-run of step 3 succeeds.
  TC-S1-04  Water → property_source = "iapws" (deterministic tier 1); no escalation.
  TC-S1-05  ENV threshold = 0.85, AI confidence = 0.80 → gate fires.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

import pytest

from hx_engine.app.core.exceptions import PropertyResolutionRequired
from hx_engine.app.models.design_state import DesignState, FluidProperties
from hx_engine.app.models.step_result import AIDecisionEnum
from hx_engine.app.steps.step_03_fluid_props import Step03FluidProperties


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_state(**kwargs) -> DesignState:
    defaults = dict(
        hot_fluid_name="mystery oil",
        cold_fluid_name="water",
        T_hot_in_C=120.0,
        T_hot_out_C=80.0,
        T_cold_in_C=25.0,
        T_cold_out_C=50.0,
    )
    defaults.update(kwargs)
    return DesignState(**defaults)


def _water_props(**kwargs) -> FluidProperties:
    base = dict(
        density_kg_m3=995.0,
        viscosity_Pa_s=7.0e-4,
        cp_J_kgK=4178.0,
        k_W_mK=0.62,
        Pr=4.7,
        property_source="iapws",
        property_confidence=None,  # deterministic: no confidence needed
    )
    base.update(kwargs)
    return FluidProperties(**base)


def _ai_props(confidence: float, source: str = "llm_estimated") -> FluidProperties:
    return FluidProperties(
        density_kg_m3=870.0,
        viscosity_Pa_s=2.5e-3,
        cp_J_kgK=2100.0,
        k_W_mK=0.14,
        Pr=37.5,
        property_source=source,
        property_confidence=confidence,
    )


# ---------------------------------------------------------------------------
# TC-S1-01: Low-confidence AI estimate → ESCALATE
# ---------------------------------------------------------------------------

class TestTC_S1_01_LowConfidenceEscalates:
    """AI confidence (0.45) below threshold (0.70) → Step 3 returns ESCALATE."""

    async def test_escalation_decision(self):
        state = _make_state()
        step = Step03FluidProperties()

        low_conf = _ai_props(confidence=0.45)

        def _side_effect(fluid_name, T, pressure_Pa=None):
            name = fluid_name.strip().lower()
            if name in ("water", "cooling water"):
                return _water_props()
            raise PropertyResolutionRequired(
                fluid_name=fluid_name,
                temperature_C=T,
                ai_estimate=low_conf,
                confidence=0.45,
                threshold=0.70,
            )

        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            new_callable=AsyncMock,
            side_effect=_side_effect,
        ):
            result = await step.execute(state)

        assert result.ai_review is not None
        assert result.ai_review.decision == AIDecisionEnum.ESCALATE
        assert result.ai_review.event_subtype == "property_request"
        payload = result.ai_review.property_request_payload
        assert payload is not None
        assert len(payload["fluids"]) == 1
        assert payload["fluids"][0]["side"] == "hot"
        assert payload["fluids"][0]["confidence"] == pytest.approx(0.45)

    async def test_state_not_mutated_on_escalation(self):
        """State is NOT modified when an escalation fires."""
        state = _make_state()
        original_hot = state.hot_fluid_props  # None

        step = Step03FluidProperties()
        low_conf = _ai_props(confidence=0.45)

        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            new_callable=AsyncMock,
            side_effect=PropertyResolutionRequired(
                fluid_name="mystery oil",
                temperature_C=100.0,
                ai_estimate=low_conf,
                confidence=0.45,
                threshold=0.70,
            ),
        ):
            await step.execute(state)

        assert state.hot_fluid_props is original_hot, (
            "execute() must NOT write to state — that is the runner's job"
        )


# ---------------------------------------------------------------------------
# TC-S1-02: High-confidence AI estimate → no escalation
# ---------------------------------------------------------------------------

class TestTC_S1_02_HighConfidencePasses:
    """AI confidence 0.75 ≥ 0.70 threshold → step returns SUCCESS with the props."""

    async def test_no_escalation(self):
        state = _make_state()
        step = Step03FluidProperties()

        hi_conf = _ai_props(confidence=0.75)

        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            new_callable=AsyncMock,
            return_value=hi_conf,
        ):
            result = await step.execute(state)

        assert result.ai_review is None or result.ai_review.decision != AIDecisionEnum.ESCALATE
        assert result.validation_passed is True
        assert "hot_fluid_props" in result.outputs

    async def test_property_source_preserved(self):
        state = _make_state()
        step = Step03FluidProperties()

        hi_conf = _ai_props(confidence=0.75, source="llm_estimated")

        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            new_callable=AsyncMock,
            return_value=hi_conf,
        ):
            result = await step.execute(state)

        hot = result.outputs.get("hot_fluid_props")
        assert hot is not None
        assert hot.property_source == "llm_estimated"


# ---------------------------------------------------------------------------
# TC-S1-03: Engineer approves AI estimate → state stamped, re-run succeeds
# ---------------------------------------------------------------------------

class TestTC_S1_03_EngineerApproval:
    """apply_user_override(option_index=0) stamps approval and step re-runs."""

    async def test_apply_approval_stamps_state(self):
        state = _make_state()
        step = Step03FluidProperties()

        low_conf = _ai_props(confidence=0.45)
        step._pending_hot_request = PropertyResolutionRequired(
            fluid_name="mystery oil",
            temperature_C=100.0,
            ai_estimate=low_conf,
            confidence=0.45,
            threshold=0.70,
        )
        step._pending_cold_request = None

        result = step.apply_user_override(state, option_index=0, text="approve")

        assert result is None  # signal: re-run this step
        assert state.hot_fluid_props is not None
        assert state.hot_fluid_props.property_source == "user_approved_estimate"
        assert state.hot_fluid_props.approval_timestamp is not None
        # timestamp must be parseable ISO-8601
        dt = datetime.fromisoformat(state.hot_fluid_props.approval_timestamp)
        assert dt.tzinfo is not None

    async def test_rerun_after_approval_succeeds(self):
        """After apply_user_override, execute() detects the approved props and skips adapter."""
        state = _make_state()
        step = Step03FluidProperties()

        # Simulate a prior approval
        approved = _ai_props(confidence=0.45)
        approved = approved.model_copy(update={
            "property_source": "user_approved_estimate",
            "approval_timestamp": datetime.now(tz=timezone.utc).isoformat(),
        })
        state.hot_fluid_props = approved

        cold_props = _water_props()

        def _side_effect(fluid_name, T, pressure_Pa=None):
            name = fluid_name.strip().lower()
            if name in ("water", "cooling water"):
                return cold_props
            # adapter should NOT be called for hot side — approved already
            raise AssertionError(
                f"get_fluid_properties called for '{fluid_name}' after approval"
            )

        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            new_callable=AsyncMock,
            side_effect=_side_effect,
        ):
            result = await step.execute(state)

        assert result.validation_passed is True
        hot = result.outputs.get("hot_fluid_props")
        assert hot is not None
        assert hot.property_source == "user_approved_estimate"


# ---------------------------------------------------------------------------
# TC-S1-04: Water → deterministic iapws tier, no escalation
# ---------------------------------------------------------------------------

class TestTC_S1_04_WaterNoEscalation:
    """Water resolves via iapws (tier 1) — no confidence gate, no escalation."""

    async def test_water_iapws(self):
        state = _make_state(
            hot_fluid_name="water",
            cold_fluid_name="water",
        )
        step = Step03FluidProperties()

        iapws_props = _water_props(property_source="iapws", property_confidence=None)

        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            new_callable=AsyncMock,
            return_value=iapws_props,
        ):
            result = await step.execute(state)

        assert result.validation_passed is True
        assert result.ai_review is None or result.ai_review.decision != AIDecisionEnum.ESCALATE
        hot = result.outputs.get("hot_fluid_props")
        assert hot is not None
        assert hot.property_source == "iapws"


# ---------------------------------------------------------------------------
# TC-S1-05: ENV threshold override — higher threshold gates more
# ---------------------------------------------------------------------------

class TestTC_S1_05_EnvThreshold:
    """With threshold=0.85, an AI confidence of 0.80 must trigger escalation."""

    async def test_higher_threshold_fires(self):
        state = _make_state()
        step = Step03FluidProperties()

        # AI estimate with confidence 0.80 (above default 0.70 but below 0.85)
        hi_conf = _ai_props(confidence=0.80)

        def _side_effect(fluid_name, T, pressure_Pa=None):
            name = fluid_name.strip().lower()
            if name in ("water", "cooling water"):
                return _water_props()
            raise PropertyResolutionRequired(
                fluid_name=fluid_name,
                temperature_C=T,
                ai_estimate=hi_conf,
                confidence=0.80,
                threshold=0.85,   # escalated because threshold is higher
            )

        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            new_callable=AsyncMock,
            side_effect=_side_effect,
        ):
            result = await step.execute(state)

        assert result.ai_review is not None
        assert result.ai_review.decision == AIDecisionEnum.ESCALATE
        payload = result.ai_review.property_request_payload
        assert payload["threshold"] == pytest.approx(0.85)
