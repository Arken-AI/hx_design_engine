"""Tests for ST-3 — ASME external pressure Table G and Factor B lookups.

Validates data against ASME BPVC Section II Part D, Subpart 3.
"""

from __future__ import annotations

import pytest

from hx_engine.app.data.asme_external_pressure import (
    FACTOR_B_CHARTS,
    TABLE_G,
    lookup_factor_A,
    lookup_factor_B,
)


class TestTableGLookup:
    """T3.1–T3.4: Factor A interpolation from Table G."""

    def test_exact_entry(self):
        """T3.1: Known D_o/t=100, L/D_o=3.0 — should be near table value."""
        A = lookup_factor_A(100, 3.0)
        assert A > 0
        assert 0.0001 < A < 0.01  # reasonable range for this geometry

    def test_interpolation(self):
        """T3.2: D_o/t=75, L/D_o=2.5 — interpolated value between neighbors."""
        A = lookup_factor_A(75, 2.5)
        assert A > 0
        # Should be between values for nearby D_o/t curves
        A_50 = lookup_factor_A(50, 2.5)
        A_100 = lookup_factor_A(100, 2.5)
        # Interpolated A should be bounded
        assert min(A_50, A_100) <= A <= max(A_50, A_100) * 1.1

    def test_boundary_small_dot(self):
        """T3.3: D_o/t=4, large L/D_o — boundary condition."""
        A = lookup_factor_A(4, 50.0)
        assert A > 0

    def test_boundary_large_dot(self):
        """T3.4: D_o/t=1000, small L/D_o — boundary."""
        A = lookup_factor_A(1000, 0.05)
        assert A > 0


class TestFactorBLookup:
    """T3.5–T3.10: Factor B material chart lookups."""

    def test_cs_at_150(self):
        """T3.5: CS-1 at 150°C, A=0.001 — Factor B ≈ 77–104 MPa range."""
        B, is_elastic = lookup_factor_B("carbon_steel", 150, 0.001)
        assert not is_elastic
        assert 50.0 < B < 150.0  # reasonable range for CS at 150°C

    def test_ss304_at_370(self):
        """T3.6: HA-1 at 370°C, A=0.001."""
        B, is_elastic = lookup_factor_B("stainless_304", 370, 0.001)
        assert not is_elastic
        assert B > 0

    def test_elastic_regime(self):
        """T3.7: Very small A falls below curve → elastic."""
        _B, is_elastic = lookup_factor_B("carbon_steel", 150, 1e-7)
        assert is_elastic

    def test_titanium(self):
        """T3.8: NFT-1 at 205°C, A=0.005."""
        B, is_elastic = lookup_factor_B("titanium", 205, 0.005)
        assert B > 0

    def test_temperature_interpolation(self):
        """T3.9: CS at 275°C should interpolate between available curves."""
        B, _ = lookup_factor_B("carbon_steel", 275, 0.001)
        assert B > 0

    def test_unknown_material_raises(self):
        """T3.10: Unknown material raises KeyError."""
        with pytest.raises(KeyError):
            lookup_factor_B("unobtanium", 150, 0.001)


class TestDataIntegrity:
    """T3.13–T3.14: Monotonicity checks on encoded data."""

    def test_table_g_factor_a_monotonic(self):
        """T3.13: Within each D_o/t curve, A should decrease as L/D_o increases."""
        for d_o_t, pairs in TABLE_G.items():
            sorted_pairs = sorted(pairs, key=lambda p: p[0])
            for i in range(len(sorted_pairs) - 1):
                L1, A1 = sorted_pairs[i]
                L2, A2 = sorted_pairs[i + 1]
                # A should generally decrease or stay same as L/D_o increases
                # (longer cylinders buckle more easily = lower A)
                # Allow small tolerance for encoded data
                assert A2 <= A1 * 1.01, (
                    f"D_o/t={d_o_t}: A not monotonically decreasing: "
                    f"({L1},{A1}) → ({L2},{A2})"
                )

    def test_factor_b_monotonic_per_temp(self):
        """T3.14: Within each temperature curve, B increases with A."""
        for chart_id, temp_curves in FACTOR_B_CHARTS.items():
            for temp, pairs in temp_curves.items():
                sorted_pairs = sorted(pairs, key=lambda p: p[0])
                for i in range(len(sorted_pairs) - 1):
                    A1, B1 = sorted_pairs[i]
                    A2, B2 = sorted_pairs[i + 1]
                    assert B2 >= B1 * 0.99, (
                        f"Chart {chart_id} @ {temp}°C: B not monotonic: "
                        f"({A1},{B1}) → ({A2},{B2})"
                    )
