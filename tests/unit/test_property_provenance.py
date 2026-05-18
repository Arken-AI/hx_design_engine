"""Unit tests for PropertyProvenanceBuilder (EPIC-XSTACK-2026-007-S3)."""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import DesignState, FluidProperties
from hx_engine.app.services.property_provenance import (
    PropertyProvenanceBuilder,
    SOURCE_LABELS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iapws_props(**kwargs) -> FluidProperties:
    defaults = dict(
        density_kg_m3=958.4,
        viscosity_Pa_s=2.82e-4,
        cp_J_kgK=4216.0,
        k_W_mK=0.679,
        Pr=1.76,
        property_source="iapws",
        property_confidence=None,
    )
    defaults.update(kwargs)
    return FluidProperties(**defaults)


def _user_props(**kwargs) -> FluidProperties:
    defaults = dict(
        density_kg_m3=880.0,
        viscosity_Pa_s=0.003,
        cp_J_kgK=2100.0,
        k_W_mK=0.145,
        Pr=43.5,
        property_source="user_provided",
        property_confidence=None,
        property_provided_at="2026-05-10T09:00:00Z",
    )
    defaults.update(kwargs)
    return FluidProperties(**defaults)


def _llm_props(**kwargs) -> FluidProperties:
    defaults = dict(
        density_kg_m3=870.0,
        viscosity_Pa_s=0.004,
        cp_J_kgK=1950.0,
        k_W_mK=0.135,
        Pr=57.8,
        property_source="llm_estimated",
        property_confidence=0.75,
        approval_timestamp=None,
    )
    defaults.update(kwargs)
    return FluidProperties(**defaults)


def _approved_llm_props(**kwargs) -> FluidProperties:
    defaults = dict(
        density_kg_m3=870.0,
        viscosity_Pa_s=0.004,
        cp_J_kgK=1950.0,
        k_W_mK=0.135,
        Pr=57.8,
        property_source="user_approved_estimate",
        property_confidence=0.82,
        approval_timestamp="2026-05-11T14:30:00Z",
    )
    defaults.update(kwargs)
    return FluidProperties(**defaults)


def _state_with(hot_props=None, cold_props=None, user_hot=None, user_cold=None) -> DesignState:
    s = DesignState()
    s.hot_fluid_name = "Steam"
    s.cold_fluid_name = "Water"
    if hot_props:
        s.hot_fluid_props = hot_props
    if cold_props:
        s.cold_fluid_props = cold_props
    if user_hot:
        s.user_provided_hot_props = user_hot
    if user_cold:
        s.user_provided_cold_props = user_cold
    return s


# ---------------------------------------------------------------------------
# TC-S3-01: Both fluids database-sourced (iapws)
# ---------------------------------------------------------------------------

class TestTC_S3_01_BothIapws:
    """Both fluids from IAPWS — correct labels, no timestamps, Pr shows derived."""

    def setup_method(self):
        state = _state_with(
            hot_props=_iapws_props(),
            cold_props=_iapws_props(),
        )
        self.result = PropertyProvenanceBuilder.build(state)

    def test_result_not_none(self):
        assert self.result is not None

    def test_hot_fluid_source(self):
        assert self.result["hot_fluid"]["source"] == "iapws"

    def test_hot_fluid_label(self):
        assert self.result["hot_fluid"]["label"] == SOURCE_LABELS["iapws"]

    def test_cold_fluid_source(self):
        assert self.result["cold_fluid"]["source"] == "iapws"

    def test_no_timestamp_on_scalar_props(self):
        for prop in ("density_kg_m3", "viscosity_Pa_s", "cp_J_kgK", "k_W_mK"):
            assert self.result["hot_fluid"]["properties"][prop]["timestamp"] is None

    def test_pr_source_is_derived(self):
        assert self.result["hot_fluid"]["properties"]["Pr"]["source"] == "derived"

    def test_pr_label(self):
        assert self.result["hot_fluid"]["properties"]["Pr"]["label"] == SOURCE_LABELS["derived"]

    def test_pr_note_present(self):
        assert "note" in self.result["hot_fluid"]["properties"]["Pr"]

    def test_no_unapproved_ai_flag(self):
        for prop in ("density_kg_m3", "viscosity_Pa_s", "cp_J_kgK", "k_W_mK", "Pr"):
            assert self.result["hot_fluid"]["properties"][prop]["unapproved_ai"] is False

    def test_fluid_confidence_none_for_iapws(self):
        assert self.result["hot_fluid"]["confidence"] is None


# ---------------------------------------------------------------------------
# TC-S3-02: Hot fluid user_provided, cold fluid iapws
# ---------------------------------------------------------------------------

class TestTC_S3_02_HotUserProvidedColdIapws:
    """Hot = user_provided, cold = iapws — blue badge + timestamp on hot; green on cold."""

    def setup_method(self):
        state = _state_with(
            hot_props=_iapws_props(),   # would be overridden
            cold_props=_iapws_props(),
            user_hot=_user_props(),
        )
        self.result = PropertyProvenanceBuilder.build(state)

    def test_hot_source_is_user_provided(self):
        assert self.result["hot_fluid"]["source"] == "user_provided"

    def test_hot_label(self):
        assert self.result["hot_fluid"]["label"] == SOURCE_LABELS["user_provided"]

    def test_hot_timestamp_present(self):
        for prop in ("density_kg_m3", "viscosity_Pa_s", "cp_J_kgK", "k_W_mK"):
            ts = self.result["hot_fluid"]["properties"][prop]["timestamp"]
            assert ts == "2026-05-10T09:00:00Z"

    def test_cold_source_is_iapws(self):
        assert self.result["cold_fluid"]["source"] == "iapws"

    def test_cold_no_timestamp(self):
        for prop in ("density_kg_m3", "viscosity_Pa_s"):
            assert self.result["cold_fluid"]["properties"][prop]["timestamp"] is None

    def test_hot_pr_user_provided_when_set(self):
        # user_props sets Pr explicitly → source should be user_provided
        assert self.result["hot_fluid"]["properties"]["Pr"]["source"] == "user_provided"

    def test_user_provided_takes_precedence_over_hot_fluid_props(self):
        # hot_fluid_props has iapws — builder must use user_provided_hot_props
        assert self.result["hot_fluid"]["source"] == "user_provided"


# ---------------------------------------------------------------------------
# TC-S3-03: AI estimate approved
# ---------------------------------------------------------------------------

class TestTC_S3_03_ApprovedAiEstimate:
    """Hot fluid = user_approved_estimate with confidence and approval_timestamp."""

    def setup_method(self):
        state = _state_with(
            hot_props=_approved_llm_props(),
            cold_props=_iapws_props(),
        )
        self.result = PropertyProvenanceBuilder.build(state)

    def test_hot_source(self):
        assert self.result["hot_fluid"]["source"] == "user_approved_estimate"

    def test_hot_label(self):
        assert self.result["hot_fluid"]["label"] == SOURCE_LABELS["user_approved_estimate"]

    def test_hot_confidence(self):
        assert self.result["hot_fluid"]["confidence"] == pytest.approx(0.82)

    def test_approval_timestamp_on_props(self):
        for prop in ("density_kg_m3", "viscosity_Pa_s"):
            ts = self.result["hot_fluid"]["properties"][prop]["timestamp"]
            assert ts == "2026-05-11T14:30:00Z"

    def test_unapproved_ai_false(self):
        for prop in ("density_kg_m3", "viscosity_Pa_s", "cp_J_kgK", "k_W_mK"):
            assert self.result["hot_fluid"]["properties"][prop]["unapproved_ai"] is False


# ---------------------------------------------------------------------------
# TC-S3-04: AI estimate auto-applied (no approval)
# ---------------------------------------------------------------------------

class TestTC_S3_04_LlmEstimatedUnapproved:
    """Hot fluid = llm_estimated with no approval_timestamp → unapproved_ai=True."""

    def setup_method(self):
        state = _state_with(
            hot_props=_llm_props(),
            cold_props=_iapws_props(),
        )
        self.result = PropertyProvenanceBuilder.build(state)

    def test_hot_source(self):
        assert self.result["hot_fluid"]["source"] == "llm_estimated"

    def test_hot_label(self):
        assert self.result["hot_fluid"]["label"] == SOURCE_LABELS["llm_estimated"]

    def test_hot_confidence(self):
        assert self.result["hot_fluid"]["confidence"] == pytest.approx(0.75)

    def test_unapproved_ai_true(self):
        for prop in ("density_kg_m3", "viscosity_Pa_s", "cp_J_kgK", "k_W_mK"):
            assert self.result["hot_fluid"]["properties"][prop]["unapproved_ai"] is True

    def test_no_timestamp_for_llm(self):
        # llm_estimated without approval has no timestamp
        for prop in ("density_kg_m3", "viscosity_Pa_s"):
            assert self.result["hot_fluid"]["properties"][prop]["timestamp"] is None


# ---------------------------------------------------------------------------
# TC-S3-10: Pr derivation when fluid sourced from iapws
# ---------------------------------------------------------------------------

class TestTC_S3_10_PrDerivation:
    """Pr row must show source=derived and note regardless of fluid source."""

    def test_pr_derived_iapws(self):
        state = _state_with(hot_props=_iapws_props(), cold_props=_iapws_props())
        result = PropertyProvenanceBuilder.build(state)
        pr = result["hot_fluid"]["properties"]["Pr"]
        assert pr["source"] == "derived"
        assert "note" in pr
        assert "Computed" in pr["note"]

    def test_pr_derived_llm_estimated_without_user_override(self):
        """llm_estimated fluid — Pr not explicitly user-set → derived."""
        props = _llm_props()
        # Pr is set on FluidProperties but it's not user_provided_hot_props
        state = _state_with(hot_props=props, cold_props=_iapws_props())
        result = PropertyProvenanceBuilder.build(state)
        pr = result["hot_fluid"]["properties"]["Pr"]
        assert pr["source"] == "derived"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_user_provided_takes_precedence_both_set(self):
        """user_provided_hot_props takes priority over hot_fluid_props."""
        state = _state_with(
            hot_props=_iapws_props(),
            cold_props=_iapws_props(),
            user_hot=_user_props(),
        )
        result = PropertyProvenanceBuilder.build(state)
        assert result["hot_fluid"]["source"] == "user_provided"

    def test_hot_fluid_props_none_returns_none_for_hot(self):
        """If hot_fluid_props is None and no user_provided, hot entry is None."""
        state = _state_with(cold_props=_iapws_props())
        result = PropertyProvenanceBuilder.build(state)
        assert result is not None  # cold still present
        assert result["hot_fluid"] is None

    def test_both_props_none_returns_none(self):
        """Both props None → build returns None."""
        state = _state_with()
        result = PropertyProvenanceBuilder.build(state)
        assert result is None

    def test_none_property_values_no_crash(self):
        """Partial FluidProperties (only density set) — builder emits None for others."""
        props = FluidProperties(
            density_kg_m3=850.0,
            property_source="user_provided",
            property_provided_at="2026-05-10T09:00:00Z",
        )
        state = _state_with(user_hot=props, cold_props=_iapws_props())
        result = PropertyProvenanceBuilder.build(state)
        assert result is not None
        assert result["hot_fluid"]["properties"]["viscosity_Pa_s"]["value"] is None
        assert result["hot_fluid"]["properties"]["density_kg_m3"]["value"] == pytest.approx(850.0)

    def test_user_provided_pr_none_falls_back_to_derived(self):
        """user_provided_hot_props with Pr=None → Pr entry shows derived."""
        props = FluidProperties(
            density_kg_m3=880.0,
            viscosity_Pa_s=0.003,
            cp_J_kgK=2100.0,
            k_W_mK=0.145,
            Pr=None,  # not explicitly set
            property_source="user_provided",
            property_provided_at="2026-05-10T09:00:00Z",
        )
        state = _state_with(user_hot=props, cold_props=_iapws_props())
        result = PropertyProvenanceBuilder.build(state)
        assert result["hot_fluid"]["properties"]["Pr"]["source"] == "derived"
