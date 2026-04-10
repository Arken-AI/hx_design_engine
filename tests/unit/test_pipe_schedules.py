"""Tests for ST-4 — Pipe schedule lookup (ASME B36.10M / B36.19M)."""

from __future__ import annotations

import pytest

from hx_engine.app.data.pipe_schedules import (
    PIPE_SCHEDULE_TABLE,
    find_minimum_schedule,
    find_nps_for_shell,
    get_pipe_od,
    get_pipe_wall,
)


class TestFindNPS:
    """T4.1–T4.3"""

    def test_nps12(self):
        """T4.1: shell_id ≈ 305 mm → NPS 12."""
        nps, od_mm = find_nps_for_shell(0.305)
        assert nps == 12
        assert abs(od_mm - 323.9) < 0.1

    def test_nps20(self):
        """T4.2: shell_id ≈ 508 mm → NPS 20."""
        nps, od_mm = find_nps_for_shell(0.508)
        assert nps == 20
        assert abs(od_mm - 508.0) < 0.1

    def test_large_shell(self):
        """T4.3: shell_id ≈ 1.0 m → NPS 42 range."""
        nps, _od_mm = find_nps_for_shell(1.0)
        assert nps >= 36  # large shell territory


class TestFindMinimumSchedule:
    """T4.4–T4.5"""

    def test_basic_nps20(self):
        """T4.4: NPS 20, t_min=6.0 mm → Sch 10 (6.35 mm)."""
        sch, wall = find_minimum_schedule(20, 6.0)
        assert sch is not None
        assert wall >= 6.0

    def test_no_schedule_thick_enough(self):
        """T4.5: NPS 8, t_min very large → None."""
        sch, wall = find_minimum_schedule(8, 999.0)
        assert sch is None
        assert wall is None


class TestSpotCheckOD:
    """T4.6: Verify ODs match ASME B36.10M."""

    @pytest.mark.parametrize("nps,expected_od", [
        (6, 168.3), (10, 273.1), (14, 355.6), (20, 508.0), (24, 609.6),
    ])
    def test_od_values(self, nps, expected_od):
        assert abs(get_pipe_od(nps) - expected_od) < 0.1


class TestScheduleAscending:
    """T4.7: Wall thickness increases with schedule number."""

    def test_ascending_wall(self):
        for nps, data in PIPE_SCHEDULE_TABLE.items():
            scheds = data["schedules"]
            sorted_scheds = sorted(scheds.keys())
            for i in range(len(sorted_scheds) - 1):
                s1, s2 = sorted_scheds[i], sorted_scheds[i + 1]
                assert scheds[s1] <= scheds[s2], (
                    f"NPS {nps}: Sch {s1} wall={scheds[s1]} > "
                    f"Sch {s2} wall={scheds[s2]}"
                )
