"""Unit tests for TEMA RCB-4.3 clearance lookups."""

from __future__ import annotations

import pytest

from hx_engine.app.data.tema_tables import get_tema_clearances


class TestGetTemaClearances:
    """Spot-check 3 shell sizes per implementation plan."""

    def test_small_shell_200mm(self) -> None:
        result = get_tema_clearances(0.200)
        assert result["delta_sb_m"] == pytest.approx(0.0016, abs=1e-6)
        assert result["delta_tb_m"] == pytest.approx(0.0004, abs=1e-6)

    def test_medium_shell_500mm(self) -> None:
        result = get_tema_clearances(0.500)
        assert result["delta_sb_m"] == pytest.approx(0.0028, abs=1e-6)
        assert result["delta_tb_m"] == pytest.approx(0.0008, abs=1e-6)

    def test_large_shell_1000mm(self) -> None:
        result = get_tema_clearances(1.000)
        assert result["delta_sb_m"] == pytest.approx(0.0040, abs=1e-6)
        assert result["delta_tb_m"] == pytest.approx(0.0008, abs=1e-6)

    def test_snap_to_nearest(self) -> None:
        """489 mm shell should snap to 500 mm entry."""
        result = get_tema_clearances(0.489)
        assert result["delta_sb_m"] == pytest.approx(0.0028, abs=1e-6)
        assert result["delta_tb_m"] == pytest.approx(0.0008, abs=1e-6)

    def test_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError, match="outside"):
            get_tema_clearances(0.050)

    def test_invalid_fit_class_raises(self) -> None:
        with pytest.raises(ValueError, match="fit class"):
            get_tema_clearances(0.500, fit_class="tight")
