"""Unit tests for P2-23 + P2-24 — service-aware overdesign bands and
low-velocity fouling paradox in Step 11."""

from __future__ import annotations

import pytest

from hx_engine.app.steps.step_11_area_overdesign import (
    _OVERDESIGN_BANDS,
    _classify_service,
    _low_velocity_fouling_paradox,
)


# ---------------------------------------------------------------------------
# Fake DesignState-like objects for isolation testing
# ---------------------------------------------------------------------------

class _FakeGeometry:
    def __init__(self, rf_tube=0.0, rf_shell=0.0):
        self.fouling_factor_tube = rf_tube
        self.fouling_factor_shell = rf_shell


class _FakeState:
    def __init__(
        self,
        hot_fluid_name="water",
        cold_fluid_name="water",
        hot_phase=None,
        cold_phase=None,
        rf_tube=0.0,
        rf_shell=0.0,
        overdesign_pct=None,
        tube_velocity_m_s=None,
        R_f_hot_m2KW=None,
        R_f_cold_m2KW=None,
        service_classification=None,
    ):
        self.hot_fluid_name = hot_fluid_name
        self.cold_fluid_name = cold_fluid_name
        self.hot_phase = hot_phase
        self.cold_phase = cold_phase
        self.geometry = _FakeGeometry(rf_tube, rf_shell)
        self.overdesign_pct = overdesign_pct
        self.tube_velocity_m_s = tube_velocity_m_s
        self.hot_fluid_props = None
        self.cold_fluid_props = None
        self.R_f_hot_m2KW = R_f_hot_m2KW
        self.R_f_cold_m2KW = R_f_cold_m2KW
        self.service_classification = service_classification
        self.increment_results = []


# ---------------------------------------------------------------------------
# P2-23 — _classify_service
# ---------------------------------------------------------------------------

class TestClassifyService:
    def test_steam_condenser_is_phase_change(self):
        state = _FakeState(hot_fluid_name="steam", hot_phase="condensing")
        assert _classify_service(state) == "phase_change"

    def test_boiling_organic_is_phase_change(self):
        state = _FakeState(cold_fluid_name="toluene", cold_phase="evaporating")
        assert _classify_service(state) == "phase_change"

    def test_clean_water_water_is_clean_utility(self):
        state = _FakeState(hot_fluid_name="water", cold_fluid_name="water")
        assert _classify_service(state) == "clean_utility"

    def test_crude_oil_is_fouling_service(self):
        state = _FakeState(hot_fluid_name="crude oil", cold_fluid_name="water")
        assert _classify_service(state) == "fouling_service"

    def test_generic_liquids_are_standard_process(self):
        state = _FakeState(hot_fluid_name="ethanol", cold_fluid_name="methanol")
        assert _classify_service(state) == "standard_process"


class TestOverdesignBandsTable:
    def test_all_four_services_present(self):
        expected = {"clean_utility", "phase_change", "standard_process", "fouling_service"}
        assert set(_OVERDESIGN_BANDS.keys()) == expected

    def test_clean_utility_tighter_than_fouling(self):
        cu_low, cu_high = _OVERDESIGN_BANDS["clean_utility"]
        ff_low, ff_high = _OVERDESIGN_BANDS["fouling_service"]
        assert cu_high < ff_high

    def test_all_bands_have_positive_width(self):
        for service, (low, high) in _OVERDESIGN_BANDS.items():
            assert high > low, f"Band for {service} has zero or negative width"


# ---------------------------------------------------------------------------
# P2-24 — _low_velocity_fouling_paradox
# ---------------------------------------------------------------------------

class TestLowVelocityFoulingParadox:
    def test_clean_service_returns_none(self):
        state = _FakeState(
            overdesign_pct=35.0, tube_velocity_m_s=0.7,
            R_f_hot_m2KW=4e-4, R_f_cold_m2KW=0.0,
        )
        severity, _ = _low_velocity_fouling_paradox(state, "clean_utility")
        assert severity is None

    def test_fouling_service_low_velocity_high_od_returns_warn(self):
        state = _FakeState(
            overdesign_pct=35.0, tube_velocity_m_s=0.7,
            R_f_hot_m2KW=4e-4, R_f_cold_m2KW=0.0,
        )
        severity, msg = _low_velocity_fouling_paradox(state, "fouling_service")
        assert severity == "warn"
        assert "fouling" in msg.lower()

    def test_compound_trigger_returns_escalate(self):
        state = _FakeState(
            overdesign_pct=55.0, tube_velocity_m_s=0.4,
            R_f_hot_m2KW=5e-4, R_f_cold_m2KW=0.0,
        )
        severity, _ = _low_velocity_fouling_paradox(state, "fouling_service")
        assert severity == "escalate"

    def test_velocity_above_floor_returns_none(self):
        state = _FakeState(
            overdesign_pct=35.0, tube_velocity_m_s=1.5,
            R_f_hot_m2KW=4e-4, R_f_cold_m2KW=0.0,
        )
        severity, _ = _low_velocity_fouling_paradox(state, "fouling_service")
        assert severity is None

    def test_low_rf_below_threshold_returns_none(self):
        """No fouling fluid — paradox should not fire even with low velocity."""
        state = _FakeState(
            overdesign_pct=35.0, tube_velocity_m_s=0.7,
            R_f_hot_m2KW=1e-4, R_f_cold_m2KW=0.0,
        )
        severity, _ = _low_velocity_fouling_paradox(state, "fouling_service")
        assert severity is None

    def test_od_below_trigger_returns_none(self):
        state = _FakeState(
            overdesign_pct=20.0, tube_velocity_m_s=0.7,
            R_f_hot_m2KW=4e-4, R_f_cold_m2KW=0.0,
        )
        severity, _ = _low_velocity_fouling_paradox(state, "fouling_service")
        assert severity is None
