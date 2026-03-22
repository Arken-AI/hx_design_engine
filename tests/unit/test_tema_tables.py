"""Tests for Piece 2: TEMA Tube Count Tables."""

from __future__ import annotations

import pytest

from hx_engine.app.data.tema_tables import (
    find_shell_diameter,
    get_standard_shell_diameters,
    get_tube_count,
    _TUBE_COUNT,
    _INCH_TO_M,
)


class TestTEMATables:
    def test_known_tube_count_23in_shell(self):
        """23.25\" shell, 3/4\" tubes, triangular, 2-pass → ~324 tubes."""
        count = get_tube_count(23.25 * _INCH_TO_M, 0.01905, "triangular", 2)
        assert count == 324

    def test_known_tube_count_12in_shell(self):
        """12\" shell, 3/4\" tubes, triangular, 2-pass → ~76 tubes."""
        count = get_tube_count(12 * _INCH_TO_M, 0.01905, "triangular", 2)
        assert count == 76

    def test_square_fewer_than_triangular(self):
        """Same shell, same tubes → square gives fewer tubes than triangular."""
        for shell_inch in [12, 17.25, 23.25, 31]:
            for passes in [1, 2, 4]:
                tri = get_tube_count(
                    shell_inch * _INCH_TO_M, 0.01905, "triangular", passes,
                )
                sq = get_tube_count(
                    shell_inch * _INCH_TO_M, 0.01905, "square", passes,
                )
                assert sq <= tri, (
                    f"Shell={shell_inch}\", passes={passes}: "
                    f"square={sq} > triangular={tri}"
                )

    def test_more_passes_fewer_tubes(self):
        """Same shell, 4-pass < 2-pass tube count."""
        for shell_inch in [12, 17.25, 23.25]:
            c2 = get_tube_count(
                shell_inch * _INCH_TO_M, 0.01905, "triangular", 2,
            )
            c4 = get_tube_count(
                shell_inch * _INCH_TO_M, 0.01905, "triangular", 4,
            )
            assert c4 < c2, (
                f"Shell={shell_inch}\": 4-pass={c4} >= 2-pass={c2}"
            )

    def test_find_shell_for_324_tubes(self):
        """324 tubes required → ≥ 23.25\" shell."""
        shell_m, actual = find_shell_diameter(
            324, 0.01905, "triangular", 2,
        )
        assert actual >= 324
        assert shell_m >= 23.25 * _INCH_TO_M - 0.001

    def test_find_shell_rounds_up(self):
        """100 tubes required → next shell size up (conservative)."""
        shell_m, actual = find_shell_diameter(
            100, 0.01905, "triangular", 2,
        )
        assert actual >= 100

    def test_very_large_tube_count(self):
        """5000 tubes → returns largest shell (graceful handling)."""
        shell_m, actual = find_shell_diameter(
            5000, 0.01905, "triangular", 2,
        )
        # Should return the largest shell available
        assert shell_m > 0

    def test_all_tube_counts_positive(self):
        """Every entry in table > 0."""
        for shell_inch, ods in _TUBE_COUNT.items():
            for od_key, layouts in ods.items():
                for layout, passes in layouts.items():
                    for n_pass, count in passes.items():
                        assert count > 0, (
                            f"Shell={shell_inch}\", OD={od_key}\", "
                            f"layout={layout}, passes={n_pass}: count={count}"
                        )

    def test_tube_count_increases_with_shell(self):
        """Larger shell → more tubes (monotonic)."""
        prev_count = 0
        shells = sorted(_TUBE_COUNT.keys())
        for shell_inch in shells:
            data = _TUBE_COUNT[shell_inch].get("0.75", {})
            tri = data.get("triangular", {})
            count = tri.get(2, 0)
            if count > 0:
                assert count >= prev_count, (
                    f"Shell={shell_inch}\": count={count} < previous={prev_count}"
                )
                prev_count = count

    def test_standard_shell_diameters_sorted(self):
        """Return value is ascending."""
        diams = get_standard_shell_diameters()
        assert diams == sorted(diams)
        assert len(diams) == 16
