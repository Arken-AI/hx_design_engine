"""Tests for nozzle sizing data table (Serth Table 5.3 + Schedule 40)."""

from __future__ import annotations

import math

import pytest

from hx_engine.app.core.exceptions import CalculationError, DesignConstraintViolation
from hx_engine.app.data.nozzle_table import (
    get_default_nozzle_diameter_m,
    get_next_larger_nozzle_diameter_m,
    nozzle_dP_Pa,
    nozzle_rho_v_squared,
)

_M_TO_IN = 39.3701


class TestNozzleLookup:
    """Verify Serth Table 5.3 ranges."""

    @pytest.mark.parametrize(
        "shell_in, expected_nozzle_id_m",
        [
            (6.0, 0.05250),    # 4–10 → 2-in. nozzle
            (15.0, 0.07793),   # 12–17.25 → 3-in.
            (19.25, 0.10226),  # 19.25–21.25 → 4-in.
            (25.0, 0.15405),   # 23–29 → 6-in.
            (35.0, 0.20272),   # 31–37 → 8-in.
            (40.0, 0.25451),   # 39–42 → 10-in.
        ],
    )
    def test_each_shell_range(self, shell_in: float, expected_nozzle_id_m: float) -> None:
        shell_m = shell_in / _M_TO_IN
        result = get_default_nozzle_diameter_m(shell_m)
        assert result == pytest.approx(expected_nozzle_id_m, rel=0.01)

    def test_19_25_inch_shell(self) -> None:
        """0.489 m shell ≈ 19.25 in. → 4-in. nozzle."""
        result = get_default_nozzle_diameter_m(0.489)
        assert result == pytest.approx(0.10226, rel=0.02)

    def test_out_of_range_too_small(self) -> None:
        with pytest.raises(DesignConstraintViolation, match="outside the nozzle table envelope"):
            get_default_nozzle_diameter_m(0.05)  # ~2 inches

    def test_out_of_range_too_large(self) -> None:
        with pytest.raises(DesignConstraintViolation, match="outside the nozzle table envelope"):
            get_default_nozzle_diameter_m(1.5)  # ~59 inches

    def test_out_of_range_carries_step_id_10(self) -> None:
        """Structured failure must be tagged to Step 10 for the redesign driver."""
        with pytest.raises(DesignConstraintViolation) as exc_info:
            get_default_nozzle_diameter_m(1.5)
        assert exc_info.value.step_id == 10
        assert exc_info.value.constraint == "nozzle_envelope"
        assert "n_shells" in exc_info.value.suggested_levers

    # ── Boundary / floating-point drift cases (regression for the
    #    'Shell ID 0.9398 m (37.00 in.)' hard-crash bug) ──────────────
    def test_37_inch_boundary_returns_8in_nozzle(self) -> None:
        """0.9398 m × 39.3701 ≈ 36.998 in. — must land in (31, 37) band → 8-in."""
        result = get_default_nozzle_diameter_m(0.9398)
        assert result == pytest.approx(0.20272, rel=1e-3)

    def test_42_inch_upper_envelope_boundary(self) -> None:
        """Exactly 42 in. must succeed (returns 10-in. nozzle), not raise."""
        shell_m = 42.0 / _M_TO_IN
        result = get_default_nozzle_diameter_m(shell_m)
        assert result == pytest.approx(0.25451, rel=1e-3)

    def test_4_inch_lower_envelope_boundary(self) -> None:
        """Exactly 4 in. must succeed (returns 2-in. nozzle), not raise."""
        shell_m = 4.0 / _M_TO_IN
        result = get_default_nozzle_diameter_m(shell_m)
        assert result == pytest.approx(0.05250, rel=1e-3)

    # ── Gap-region snap-up cases — every gap in Serth Table 5.3 must
    #    snap UP to the next-larger band's nozzle, never raise. ───────
    @pytest.mark.parametrize(
        "shell_in, expected_nozzle_id_m, gap_desc",
        [
            (11.0, 0.07793, "10–12 in. gap → 3-in. nozzle"),
            (18.0, 0.10226, "17.25–19.25 in. gap → 4-in. nozzle"),
            (22.0, 0.15405, "21.25–23 in. gap → 6-in. nozzle"),
            (30.0, 0.20272, "29–31 in. gap → 8-in. nozzle"),
            (38.0, 0.25451, "37–39 in. gap → 10-in. nozzle"),
        ],
    )
    def test_gap_regions_snap_up(
        self, shell_in: float, expected_nozzle_id_m: float, gap_desc: str
    ) -> None:
        shell_m = shell_in / _M_TO_IN
        result = get_default_nozzle_diameter_m(shell_m)
        assert result == pytest.approx(expected_nozzle_id_m, rel=1e-3), gap_desc


class TestRhoVSquared:

    def test_basic_calculation(self) -> None:
        """ρv² for known inputs."""
        m_dot = 10.0  # kg/s
        rho = 1000.0  # kg/m³
        d_nozzle = 0.10226  # 4-in. Schedule 40

        A = math.pi / 4.0 * d_nozzle ** 2
        v = m_dot / (rho * A)
        expected_rho_v2 = rho * v ** 2

        result = nozzle_rho_v_squared(m_dot, rho, d_nozzle)
        assert result == pytest.approx(expected_rho_v2, rel=1e-6)

    def test_typical_design_under_limit(self) -> None:
        """Typical water flow through 3-in. nozzle should be well under 2230."""
        result = nozzle_rho_v_squared(
            mass_flow_kg_s=5.0,
            density_kg_m3=995.0,
            nozzle_id_m=0.07793,
        )
        assert result < 2230.0


class TestNozzleDeltaP:

    def test_basic_nozzle_dp(self) -> None:
        """K=1.0 → ΔP = 0.5 × ρ × v²."""
        m_dot = 10.0
        rho = 1000.0
        d = 0.10226
        A = math.pi / 4.0 * d ** 2
        v = m_dot / (rho * A)
        expected = 1.0 * rho * v ** 2 / 2.0

        result = nozzle_dP_Pa(m_dot, rho, d)
        assert result == pytest.approx(expected, rel=1e-6)


class TestGetNextLargerNozzle:
    """Tests for the nozzle upsize helper."""

    def test_2in_to_3in(self) -> None:
        """2-in. nozzle (0.05250) → 3-in. (0.07793)."""
        result = get_next_larger_nozzle_diameter_m(0.05250)
        assert result == pytest.approx(0.07793, rel=1e-3)

    def test_3in_to_4in(self) -> None:
        result = get_next_larger_nozzle_diameter_m(0.07793)
        assert result == pytest.approx(0.10226, rel=1e-3)

    def test_4in_to_6in(self) -> None:
        result = get_next_larger_nozzle_diameter_m(0.10226)
        assert result == pytest.approx(0.15405, rel=1e-3)

    def test_6in_to_8in(self) -> None:
        result = get_next_larger_nozzle_diameter_m(0.15405)
        assert result == pytest.approx(0.20272, rel=1e-3)

    def test_8in_to_10in(self) -> None:
        result = get_next_larger_nozzle_diameter_m(0.20272)
        assert result == pytest.approx(0.25451, rel=1e-3)

    def test_10in_returns_none(self) -> None:
        """Largest size returns None (no bigger available)."""
        result = get_next_larger_nozzle_diameter_m(0.25451)
        assert result is None

    def test_intermediate_value_returns_next_above(self) -> None:
        """A diameter between 3-in. and 4-in. → returns 4-in."""
        result = get_next_larger_nozzle_diameter_m(0.09)
        assert result == pytest.approx(0.10226, rel=1e-3)

    def test_very_small_returns_smallest(self) -> None:
        """A very small diameter → returns 2-in. (smallest)."""
        result = get_next_larger_nozzle_diameter_m(0.01)
        assert result == pytest.approx(0.05250, rel=1e-3)


class TestDualNozzles:
    """Tests for n_nozzles parameter in ρv² and ΔP."""

    def test_dual_nozzles_halves_rho_v2(self) -> None:
        """Dual nozzles should reduce ρv² by factor of 4 (v halved → v² quartered)."""
        m_dot = 40.0
        rho = 995.0
        d = 0.07793

        single = nozzle_rho_v_squared(m_dot, rho, d, n_nozzles=1)
        dual = nozzle_rho_v_squared(m_dot, rho, d, n_nozzles=2)
        assert dual == pytest.approx(single / 4.0, rel=1e-6)

    def test_dual_nozzles_quarters_dp(self) -> None:
        """Dual nozzles should reduce ΔP by factor of 4."""
        m_dot = 40.0
        rho = 995.0
        d = 0.07793

        single = nozzle_dP_Pa(m_dot, rho, d, n_nozzles=1)
        dual = nozzle_dP_Pa(m_dot, rho, d, n_nozzles=2)
        assert dual == pytest.approx(single / 4.0, rel=1e-6)
