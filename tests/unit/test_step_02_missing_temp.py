"""Tests for Piece 3: _calculate_missing_temp() — back-calculation of the 4th temperature."""

from __future__ import annotations

import pytest

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.steps.step_02_heat_duty import Step02HeatDuty

# -----------------------------------------------------------------
# Reference case used across tests:
#   Hot:  crude oil, 150 → 90 °C, 50 kg/s, Cp = 1900 J/kg·K
#   Cold: water,     30  → ? °C,  ? kg/s,  Cp = 4181 J/kg·K
#   Q_hot = 50 × 1900 × (150 − 90) = 5,700,000 W
# -----------------------------------------------------------------

CP_HOT = 1900.0
CP_COLD = 4181.0


class TestCalculateMissingTemp:
    """Seven tests guarding missing-temperature back-calculation correctness."""

    # ---- Test 1 ----
    def test_missing_T_cold_out(self):
        """T_cold_out calculated correctly from Q_hot.

        Q_hot = 50 × 1900 × 60 = 5,700,000 W
        T_cold_out = 30 + 5,700,000 / (45.44 × 4181) ≈ 60.0 °C
        (m_dot_cold chosen so that T_cold_out = 60 °C exactly)

        Physics: must satisfy Q_hot = Q_cold (first law).
        """
        m_dot_cold = 5_700_000.0 / (CP_COLD * 30.0)  # ≈ 45.44 kg/s

        result = Step02HeatDuty._calculate_missing_temp(
            T_hot_in_C=150.0,
            T_hot_out_C=90.0,
            T_cold_in_C=30.0,
            T_cold_out_C=None,
            m_dot_hot_kg_s=50.0,
            m_dot_cold_kg_s=m_dot_cold,
            cp_hot_J_kgK=CP_HOT,
            cp_cold_J_kgK=CP_COLD,
        )

        assert result["calculated_field"] == "T_cold_out_C"
        assert result["T_cold_out_C"] == pytest.approx(60.0, abs=0.1)
        assert result["Q_known_side_W"] == pytest.approx(5_700_000.0, rel=1e-6)

    # ---- Test 2 ----
    def test_missing_T_hot_out(self):
        """T_hot_out back-calculated from Q_cold.

        Cold side: 45.44 kg/s water, 30 → 60 °C
        Q_cold = 45.44 × 4181 × 30 = 5,700,014 W ≈ 5.7 MW
        T_hot_out = 150 − Q_cold / (50 × 1900) ≈ 90.0 °C

        Physics: energy balance must close to < 1%.
        """
        m_dot_cold = 5_700_000.0 / (CP_COLD * 30.0)

        result = Step02HeatDuty._calculate_missing_temp(
            T_hot_in_C=150.0,
            T_hot_out_C=None,
            T_cold_in_C=30.0,
            T_cold_out_C=60.0,
            m_dot_hot_kg_s=50.0,
            m_dot_cold_kg_s=m_dot_cold,
            cp_hot_J_kgK=CP_HOT,
            cp_cold_J_kgK=CP_COLD,
        )

        assert result["calculated_field"] == "T_hot_out_C"
        assert result["T_hot_out_C"] == pytest.approx(90.0, abs=0.1)

    # ---- Test 3 ----
    def test_back_calculated_T_roundtrip(self):
        """Set all 4 temps → remove T_cold_out → recalculate → matches original.

        Round-trip consistency proves the algebra is correct.
        """
        T_hot_in = 150.0
        T_hot_out = 90.0
        T_cold_in = 30.0
        T_cold_out_original = 60.0
        m_dot_hot = 50.0

        # Derive m_dot_cold from balanced energy
        Q_hot = m_dot_hot * CP_HOT * (T_hot_in - T_hot_out)
        m_dot_cold = Q_hot / (CP_COLD * (T_cold_out_original - T_cold_in))

        result = Step02HeatDuty._calculate_missing_temp(
            T_hot_in_C=T_hot_in,
            T_hot_out_C=T_hot_out,
            T_cold_in_C=T_cold_in,
            T_cold_out_C=None,
            m_dot_hot_kg_s=m_dot_hot,
            m_dot_cold_kg_s=m_dot_cold,
            cp_hot_J_kgK=CP_HOT,
            cp_cold_J_kgK=CP_COLD,
        )

        assert result["T_cold_out_C"] == pytest.approx(
            T_cold_out_original, abs=0.1
        )

    # ---- Test 4 ----
    def test_result_temp_cross_detected(self):
        """Calculated T_cold_out > T_hot_in — thermodynamically impossible.

        Setup: very small cold flow so that T_cold_out is forced above T_hot_in.
        The function itself does *not* reject this (Layer-2 rules do), but the
        returned value must be flaggable by downstream validation.

        Physics: temperature cross means no heat transfer is possible without
        external work.
        """
        # Hot: 150 → 90 °C, 50 kg/s, Cp 1900 → Q_hot = 5.7 MW
        # Cold: tiny flow → enormous ΔT_cold
        m_dot_cold_tiny = 1.0  # only 1 kg/s

        result = Step02HeatDuty._calculate_missing_temp(
            T_hot_in_C=150.0,
            T_hot_out_C=90.0,
            T_cold_in_C=30.0,
            T_cold_out_C=None,
            m_dot_hot_kg_s=50.0,
            m_dot_cold_kg_s=m_dot_cold_tiny,
            cp_hot_J_kgK=CP_HOT,
            cp_cold_J_kgK=CP_COLD,
        )

        # T_cold_out = 30 + 5_700_000 / (1 × 4181) ≈ 1393 °C
        assert result["T_cold_out_C"] > result["T_hot_in_C"], (
            "Calculated T_cold_out should exceed T_hot_in (temperature cross) "
            "— downstream Layer-2 rules flag this."
        )

    # ---- Test 5 ----
    def test_missing_both_cold_temps(self):
        """T_cold_in & T_cold_out both None → CalculationError (underdetermined).

        Physics: with two unknowns on the same side the system has infinite
        solutions — must escalate.
        """
        with pytest.raises(CalculationError, match="Multiple temperatures missing"):
            Step02HeatDuty._calculate_missing_temp(
                T_hot_in_C=150.0,
                T_hot_out_C=90.0,
                T_cold_in_C=None,
                T_cold_out_C=None,
                m_dot_hot_kg_s=50.0,
                m_dot_cold_kg_s=45.0,
                cp_hot_J_kgK=CP_HOT,
                cp_cold_J_kgK=CP_COLD,
            )

    # ---- Test 6 ----
    def test_small_missing_delta_T(self):
        """Q_hot is small → T_cold_out barely above T_cold_in (valid).

        Hot: 150 → 149 °C (only 1 °C drop), 50 kg/s, Cp=1900
        Q_hot = 50 × 1900 × 1 = 95,000 W
        T_cold_out = 30 + 95,000 / (45.44 × 4181) ≈ 30.50 °C

        Physics: ΔT can be small but not zero; the function should calculate
        correctly without numerical issues.
        """
        m_dot_cold = 5_700_000.0 / (CP_COLD * 30.0)  # ≈ 45.44 kg/s

        result = Step02HeatDuty._calculate_missing_temp(
            T_hot_in_C=150.0,
            T_hot_out_C=149.0,
            T_cold_in_C=30.0,
            T_cold_out_C=None,
            m_dot_hot_kg_s=50.0,
            m_dot_cold_kg_s=m_dot_cold,
            cp_hot_J_kgK=CP_HOT,
            cp_cold_J_kgK=CP_COLD,
        )

        Q_hot = 50.0 * CP_HOT * 1.0  # 95,000 W
        expected_T_cold_out = 30.0 + Q_hot / (m_dot_cold * CP_COLD)

        assert result["T_cold_out_C"] == pytest.approx(expected_T_cold_out, abs=0.01)
        assert result["T_cold_out_C"] > 30.0, "T_cold_out must exceed T_cold_in"

    # ---- Test 7 ----
    def test_missing_m_dot_cold_with_4_temps(self):
        """All 4 temps known, m_dot_cold missing → solve from energy balance.

        Q_hot = 50 × 1900 × 60 = 5,700,000 W
        m_dot_cold = Q_hot / (Cp_cold × ΔT_cold) = 5,700,000 / (4181 × 30)
                   ≈ 45.44 kg/s

        Physics: must be positive and physically reasonable.
        """
        result = Step02HeatDuty._calculate_missing_temp(
            T_hot_in_C=150.0,
            T_hot_out_C=90.0,
            T_cold_in_C=30.0,
            T_cold_out_C=60.0,
            m_dot_hot_kg_s=50.0,
            m_dot_cold_kg_s=None,
            cp_hot_J_kgK=CP_HOT,
            cp_cold_J_kgK=CP_COLD,
        )

        expected_m_dot = 5_700_000.0 / (CP_COLD * 30.0)

        assert result["calculated_field"] == "m_dot_cold_kg_s"
        assert result["m_dot_cold_kg_s"] == pytest.approx(expected_m_dot, rel=1e-4)
        assert result["m_dot_cold_kg_s"] > 0, "Flow rate must be positive"
        assert result["Q_known_side_W"] == pytest.approx(5_700_000.0, rel=1e-6)
