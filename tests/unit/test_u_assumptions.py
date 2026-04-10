"""Tests for Piece 10: U Assumptions."""

from __future__ import annotations

import pytest

from hx_engine.app.data.u_assumptions import (
    classify_fluid_type,
    get_U_assumption,
    _U_TABLE,
)


class TestUAssumptions:
    def test_water_water_U_high(self):
        """Water-water → U_mid ≈ 1200."""
        u = get_U_assumption("water", "cooling water")
        assert u["U_mid"] == 1200

    def test_crude_water_U_moderate(self):
        """Crude-water → U_mid ≈ 300."""
        u = get_U_assumption("crude oil", "water")
        assert u["U_mid"] == 300

    def test_gas_gas_U_very_low(self):
        """Gas-gas → U_mid ≈ 25."""
        u = get_U_assumption("air", "nitrogen")
        assert u["U_mid"] == 25

    def test_U_low_lt_mid_lt_high(self):
        """All entries: U_low < U_mid < U_high."""
        for key, (u_low, u_mid, u_high) in _U_TABLE.items():
            assert u_low < u_mid < u_high, (
                f"{key}: {u_low} < {u_mid} < {u_high} failed"
            )

    def test_all_U_positive(self):
        """Every U value > 0."""
        for key, (u_low, u_mid, u_high) in _U_TABLE.items():
            assert u_low > 0 and u_mid > 0 and u_high > 0, f"{key}"

    def test_classify_water(self):
        """'water', 'cooling water' → 'water'."""
        assert classify_fluid_type("water") == "water"
        assert classify_fluid_type("cooling water") == "water"

    def test_classify_crude(self):
        """'crude oil' → 'crude'."""
        assert classify_fluid_type("crude oil") == "crude"

    def test_unknown_pair_returns_conservative(self):
        """Unknown pair → returns liquid-liquid mid range."""
        u = get_U_assumption("unobtanium", "vibranium")
        assert u["U_mid"] == 300  # default liquid-liquid
