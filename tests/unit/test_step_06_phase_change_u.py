"""Unit tests for P2-21 — phase-aware classify_fluid_type and U-table entries."""

from __future__ import annotations

import pytest

from hx_engine.app.data.u_assumptions import (
    _U_TABLE,
    classify_fluid_type,
    get_U_assumption,
)


class TestPhaseClassification:
    """Phase arg routes to the correct phase-change category."""

    def test_steam_condensing_returns_condensing_vapor_water(self):
        assert classify_fluid_type("steam", phase="condensing") == "condensing_vapor_water"

    def test_water_condensing_returns_condensing_vapor_water(self):
        assert classify_fluid_type("water", phase="condensing") == "condensing_vapor_water"

    def test_organic_condensing_returns_condensing_vapor_organic(self):
        assert classify_fluid_type("toluene", phase="condensing") == "condensing_vapor_organic"

    def test_refrigerant_condensing_returns_condensing_vapor_refrigerant(self):
        assert classify_fluid_type("R-134a", phase="condensing") == "condensing_vapor_refrigerant"

    def test_water_evaporating_returns_boiling_water(self):
        assert classify_fluid_type("water", phase="evaporating") == "boiling_water"

    def test_organic_evaporating_returns_boiling_organic(self):
        assert classify_fluid_type("hexane", phase="evaporating") == "boiling_organic"

    def test_refrigerant_evaporating_returns_boiling_refrigerant(self):
        assert classify_fluid_type("R-134a", phase="evaporating") == "boiling_refrigerant"

    def test_no_phase_falls_through_to_sensible_path(self):
        """Existing sensible path unchanged — regression guard."""
        result = classify_fluid_type("water", phase=None)
        assert result == "water"

    def test_liquid_phase_treated_as_sensible(self):
        """phase='liquid' should not activate phase-change branch."""
        result = classify_fluid_type("water", phase="liquid")
        assert result == "water"


class TestUTablePhaseChangePairs:
    """New phase-change rows are present with physically reasonable U_mid values."""

    def test_steam_condenser_u_mid_approx_2750(self):
        u_low, u_mid, u_high = _U_TABLE[("condensing_vapor_water", "water")]
        # Coulson §12.1: steam–water ≈ 2000–3500 W/m²·K
        assert 2000 <= u_mid <= 3500

    def test_organic_condenser_u_mid_approx_900(self):
        u_low, u_mid, u_high = _U_TABLE[("condensing_vapor_organic", "water")]
        # Coulson §12.1: organic vapour–water ≈ 600–1200 W/m²·K
        assert 600 <= u_mid <= 1200

    def test_refrigerant_condenser_u_mid_approx_1000(self):
        u_low, u_mid, u_high = _U_TABLE[("condensing_vapor_refrigerant", "water")]
        assert 600 <= u_mid <= 1500

    def test_boiling_water_steam_u_mid_approx_1400(self):
        u_low, u_mid, u_high = _U_TABLE[("boiling_water", "steam")]
        assert 1000 <= u_mid <= 2000

    def test_boiling_organic_steam_u_mid_approx_700(self):
        u_low, u_mid, u_high = _U_TABLE[("boiling_organic", "steam")]
        assert 400 <= u_mid <= 1100


class TestGetUAssumptionWithPhase:
    """get_U_assumption forwards phase to classify_fluid_type."""

    def test_steam_condenser_u_mid_above_sensible(self):
        """Phase-aware U should be higher than a sensible water–water value."""
        phase_result = get_U_assumption(
            "steam", "water", hot_phase="condensing", cold_phase="liquid",
        )
        sensible_result = get_U_assumption("water", "water")
        assert phase_result["U_mid"] >= sensible_result["U_mid"]

    def test_organic_evaporator_returns_boiling_entry(self):
        result = get_U_assumption(
            "steam", "toluene", hot_phase="condensing", cold_phase="evaporating",
        )
        assert result["U_mid"] > 0
