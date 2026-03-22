"""Tests for Piece 3: Fouling Factors."""

from __future__ import annotations

import pytest

from hx_engine.app.data.fouling_factors import (
    classify_fouling,
    get_fouling_factor,
    get_fouling_factor_with_source,
    is_fouling_fluid,
    is_location_dependent,
    _FOULING_SIMPLE,
    _FOULING_TEMP_DEPENDENT,
)


class TestFoulingFactors:
    def test_water_fouling_factor(self):
        """Cooling water → R_f ≈ 0.000352 m²·K/W."""
        rf = get_fouling_factor("cooling water")
        assert abs(rf - 0.000352) < 1e-6

    def test_crude_oil_120C(self):
        """Crude at 100°C → R_f ≈ 0.000352."""
        rf = get_fouling_factor("crude oil", 100)
        assert abs(rf - 0.000352) < 1e-6

    def test_crude_oil_200C(self):
        """Crude at 200°C → R_f ≈ 0.000704 (higher temp = higher fouling)."""
        rf = get_fouling_factor("crude oil", 200)
        assert abs(rf - 0.000704) < 1e-6

    def test_clean_fluid_classification(self):
        """Boiler feedwater → 'clean'."""
        c = classify_fouling("boiler feedwater")
        assert c == "clean"

    def test_heavy_fluid_is_fouling(self):
        """Crude at 200°C → is_fouling_fluid() returns True."""
        assert is_fouling_fluid("crude oil", 200) is True

    def test_light_hydrocarbon_not_fouling(self):
        """Gasoline → is_fouling_fluid() returns False."""
        assert is_fouling_fluid("gasoline") is False

    def test_all_factors_positive(self):
        """Every entry > 0."""
        for name, rf in _FOULING_SIMPLE.items():
            assert rf > 0, f"{name}: R_f={rf}"
        for name, ranges in _FOULING_TEMP_DEPENDENT.items():
            for t_min, t_max, rf in ranges:
                assert rf > 0, f"{name} [{t_min}-{t_max}]: R_f={rf}"

    def test_unknown_fluid_returns_default(self):
        """Unknown fluid → conservative default (0.000352)."""
        rf = get_fouling_factor("unobtanium")
        assert abs(rf - 0.000352) < 1e-6


class TestFoulingFactorWithSource:
    """Tests for get_fouling_factor_with_source() — AI escalation metadata."""

    def test_known_fluid_exact_match(self):
        """Gasoline → exact match, no AI needed."""
        info = get_fouling_factor_with_source("gasoline")
        assert abs(info["rf"] - 0.000176) < 1e-6
        assert info["source"] == "exact"
        assert info["needs_ai"] is False

    def test_temp_dependent_fluid(self):
        """Crude oil at 100°C → temp_dependent source."""
        info = get_fouling_factor_with_source("crude oil", 100)
        assert info["source"] == "temp_dependent"
        # Crude is location-dependent → needs AI
        assert info["needs_ai"] is True

    def test_unknown_fluid_needs_ai(self):
        """Completely unknown fluid → ai_recommended, needs_ai=True."""
        info = get_fouling_factor_with_source("phosphoric acid solution")
        assert info["source"] == "ai_recommended"
        assert info["needs_ai"] is True
        assert abs(info["rf"] - 0.000352) < 1e-6
        assert "not in the standard fouling tables" in info["reason"]

    def test_unknown_fluid_reason_includes_fluid_name(self):
        """Reason message should include the fluid name for AI context."""
        info = get_fouling_factor_with_source("molten polymer")
        assert "molten polymer" in info["reason"]

    def test_location_dependent_river_water_needs_ai(self):
        """River water → in table but location-dependent, needs AI."""
        info = get_fouling_factor_with_source("river water")
        assert info["needs_ai"] is True
        assert "location" in info["reason"].lower() or "varies" in info["reason"].lower()
        # Still returns the table value as a starting point
        assert abs(info["rf"] - 0.000528) < 1e-6

    def test_location_dependent_cooling_tower_water(self):
        """Cooling tower water → location-dependent, needs AI."""
        info = get_fouling_factor_with_source("cooling tower water")
        assert info["needs_ai"] is True

    def test_location_dependent_seawater(self):
        """Seawater → temp-dependent AND location-dependent."""
        info = get_fouling_factor_with_source("seawater", 30)
        assert info["needs_ai"] is True
        assert abs(info["rf"] - 0.000088) < 1e-6

    def test_stable_fluid_no_ai(self):
        """Methanol → well-defined R_f, no AI needed."""
        info = get_fouling_factor_with_source("methanol")
        assert info["needs_ai"] is False
        assert info["source"] == "exact"

    def test_steam_no_ai(self):
        """Steam → well-defined, no AI needed."""
        info = get_fouling_factor_with_source("steam")
        assert info["needs_ai"] is False

    @pytest.mark.parametrize("fluid", [
        "river water", "seawater", "cooling tower water",
        "cooling water", "brine", "crude oil",
    ])
    def test_all_location_dependent_flagged(self, fluid):
        """Every member of _LOCATION_DEPENDENT → needs_ai=True."""
        info = get_fouling_factor_with_source(fluid)
        assert info["needs_ai"] is True, f"{fluid} should need AI"

    def test_result_dict_keys(self):
        """Result always has rf, source, needs_ai, reason."""
        for fluid in ["gasoline", "unobtanium", "river water"]:
            info = get_fouling_factor_with_source(fluid)
            assert {"rf", "source", "needs_ai", "reason"} == set(info.keys())


class TestIsLocationDependent:
    def test_river_water(self):
        assert is_location_dependent("river water") is True

    def test_seawater(self):
        assert is_location_dependent("seawater") is True

    def test_gasoline(self):
        assert is_location_dependent("gasoline") is False

    def test_steam(self):
        assert is_location_dependent("steam") is False

    def test_partial_match_river(self):
        """'dirty river water' contains 'river water' → True."""
        assert is_location_dependent("dirty river water") is True

    def test_case_insensitive(self):
        assert is_location_dependent("River Water") is True
