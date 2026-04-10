"""Tests for Piece 1: BWG Gauge Table."""

from __future__ import annotations

import pytest

from hx_engine.app.data.bwg_gauge import (
    get_available_tube_ods,
    get_tube_id,
    get_wall_thickness,
    _BWG_TABLE,
)


class TestBWGGauge:
    def test_19mm_bwg14_id(self):
        """19.05mm OD, BWG 14 → ID ≈ 14.83mm (Perry's reference)."""
        tube_id = get_tube_id(0.01905, 14)
        assert abs(tube_id * 1000 - 14.834) < 0.1

    def test_25mm_bwg14_id(self):
        """25.40mm OD, BWG 14 → ID ≈ 21.18mm (Perry's reference)."""
        tube_id = get_tube_id(0.02540, 14)
        assert abs(tube_id * 1000 - 21.184) < 0.1

    def test_wall_positive(self):
        """All (OD, BWG) combos → wall > 0."""
        for od_mm, gauges in _BWG_TABLE.items():
            for bwg in gauges:
                wall = get_wall_thickness(od_mm / 1000.0, bwg)
                assert wall > 0, f"OD={od_mm}, BWG={bwg}: wall={wall}"

    def test_id_less_than_od(self):
        """For all entries: ID < OD."""
        for od_mm, gauges in _BWG_TABLE.items():
            for bwg in gauges:
                tube_id = get_tube_id(od_mm / 1000.0, bwg)
                assert tube_id < od_mm / 1000.0, (
                    f"OD={od_mm}, BWG={bwg}: ID={tube_id*1000} >= OD"
                )

    def test_wall_equals_half_od_minus_id(self):
        """wall = (OD - ID) / 2 for all entries (geometric consistency)."""
        for od_mm, gauges in _BWG_TABLE.items():
            for bwg in gauges:
                od_m = od_mm / 1000.0
                tube_id = get_tube_id(od_m, bwg)
                wall = get_wall_thickness(od_m, bwg)
                expected_wall = (od_m - tube_id) / 2.0
                assert abs(wall - expected_wall) < 1e-7, (
                    f"OD={od_mm}, BWG={bwg}: "
                    f"wall={wall} != (OD-ID)/2={expected_wall}"
                )

    def test_unknown_od_raises(self):
        """get_tube_id(0.123) → ValueError."""
        with pytest.raises(ValueError, match="not a standard"):
            get_tube_id(0.123)

    def test_available_ods_includes_common(self):
        """0.01905 and 0.0254 in available ODs list."""
        ods = get_available_tube_ods()
        # Check within tolerance
        assert any(abs(od - 0.01905) < 1e-6 for od in ods)
        assert any(abs(od - 0.02540) < 1e-6 for od in ods)
