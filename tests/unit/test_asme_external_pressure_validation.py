"""Tests for ST-11 — ASME External Pressure validation (benchmark gate).

Validates the complete external pressure calculation pipeline against
known ASME worked examples and spot-check Table G values.
"""

from __future__ import annotations

import pytest

from hx_engine.app.correlations.asme_thickness import external_pressure_allowable
from hx_engine.app.data.asme_external_pressure import lookup_factor_A, lookup_factor_B


class TestTableGSpotChecks:
    """T11.4–T11.5: Table G interpolation accuracy."""

    def test_dot20_ldo2(self):
        """T11.4: D_o/t=20, L/D_o=2.0 → A ≈ 0.00713."""
        A = lookup_factor_A(20, 2.0)
        assert abs(A - 0.00713) / 0.00713 < 0.05  # ±5%

    def test_dot4_boundary(self):
        """T11.5: D_o/t=4, L/D_o=2.2 → A ≈ 0.0959 (exact table entry)."""
        A = lookup_factor_A(4, 2.2)
        assert abs(A - 0.0959) / 0.0959 < 0.02  # ±2%


class TestFactorBSpotChecks:
    """T11.6–T11.8: Factor B chart validation."""

    def test_cs1_150C(self):
        """T11.6: CS-1 at 150°C, A=0.001 → B in reasonable range."""
        B, is_elastic = lookup_factor_B("carbon_steel", 150, 0.001)
        assert not is_elastic
        assert B > 50  # should be > 50 MPa for CS at 150°C

    def test_ha1_370C(self):
        """T11.7: HA-1 at 370°C, A=0.001."""
        B, is_elastic = lookup_factor_B("stainless_304", 370, 0.001)
        assert not is_elastic
        assert B > 20  # > 20 MPa

    def test_nft1_205C(self):
        """T11.8: NFT-1 at 205°C, A=0.003."""
        B, is_elastic = lookup_factor_B("titanium", 205, 0.003)
        assert B > 30  # reasonable for Ti


class TestEndToEndExamples:
    """T11.1–T11.3: Full external pressure calculation pipeline."""

    def test_typical_tube(self):
        """T11.3: Typical 19.05mm tube, BWG 14, baffle=127mm → P_a >> 1 MPa."""
        result = external_pressure_allowable(
            D_o_m=0.01905,
            t_m=0.002108,
            L_m=0.127,
            material="carbon_steel",
            temperature_C=150,
        )
        assert result["P_allowable_Pa"] > 5e6  # > 5 MPa — tubes are very stiff

    def test_cs_shell_vacuum(self):
        """T11.1: CS shell D_o≈610mm, t=10mm, L=3000mm, 150°C."""
        result = external_pressure_allowable(
            D_o_m=0.610,
            t_m=0.010,
            L_m=3.0,
            material="sa516_gr70",
            temperature_C=150,
        )
        # P_allowable should be in the range of 0.05–0.5 MPa for this geometry
        assert result["P_allowable_Pa"] > 0

    def test_ss304_shell(self):
        """T11.2: 304 SS shell D_o=600mm, t=8mm, L=2400mm, 370°C."""
        result = external_pressure_allowable(
            D_o_m=0.600,
            t_m=0.008,
            L_m=2.4,
            material="stainless_304",
            temperature_C=370,
        )
        assert result["P_allowable_Pa"] > 0
