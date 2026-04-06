"""Tests for nozzle sizing data table (Serth Table 5.3 + Schedule 40)."""

from __future__ import annotations

import math

import pytest

from hx_engine.app.data.nozzle_table import (
    get_default_nozzle_diameter_m,
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
        with pytest.raises(ValueError, match="outside the nozzle table range"):
            get_default_nozzle_diameter_m(0.05)  # ~2 inches

    def test_out_of_range_too_large(self) -> None:
        with pytest.raises(ValueError, match="outside the nozzle table range"):
            get_default_nozzle_diameter_m(1.5)  # ~59 inches


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
