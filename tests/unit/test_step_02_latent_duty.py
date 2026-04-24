"""Tests for Step 02 latent (phase-change) duty path — P1-5 regression guard.

Covers ``_latent_duty_for_side`` which produces ``Q = ṁ · h_fg · Δx`` for
isothermal sides and the ``_quality_override`` helper that reads partial
phase-change endpoints from ``state.applied_corrections``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hx_engine.app.steps.step_02_heat_duty import Step02HeatDuty


def _sat_water_1_atm() -> dict:
    """Saturated water at 1 atm: T_sat=100°C, h_fg ≈ 2.257 MJ/kg."""
    return {"T_sat_C": 100.0, "h_fg": 2_257_000.0}


class TestLatentDutyForSide:
    """Six tests guarding Q = ṁ · h_fg · Δx for isothermal phase change."""

    @pytest.mark.asyncio
    async def test_full_condensation_uses_full_h_fg(self):
        """Hot side, x_in=1 → x_out=0, ΔT≈0 → Q = ṁ · h_fg."""
        warnings: list[str] = []
        with patch(
            "hx_engine.app.adapters.thermo_adapter.get_saturation_props",
            return_value=_sat_water_1_atm(),
        ):
            result = await Step02HeatDuty._latent_duty_for_side(
                side="hot",
                fluid_name="water",
                T_in_C=100.0,
                T_out_C=100.0,
                m_dot_kg_s=1.0,
                pressure_Pa=101_325.0,
                x_in=1.0,
                x_out=0.0,
                warnings=warnings,
            )

        assert result is not None
        assert result["Q_W"] == pytest.approx(2_257_000.0, rel=1e-6)
        assert result["dx"] == pytest.approx(1.0)
        assert result["mode"] == "condensing"

    @pytest.mark.asyncio
    async def test_partial_condensation_scales_linearly_with_dx(self):
        """Partial condensation x_in=1 → x_out=0.5 → Q = 0.5 · ṁ · h_fg."""
        warnings: list[str] = []
        with patch(
            "hx_engine.app.adapters.thermo_adapter.get_saturation_props",
            return_value=_sat_water_1_atm(),
        ):
            result = await Step02HeatDuty._latent_duty_for_side(
                side="hot",
                fluid_name="water",
                T_in_C=100.0,
                T_out_C=100.0,
                m_dot_kg_s=1.0,
                pressure_Pa=101_325.0,
                x_in=1.0,
                x_out=0.5,
                warnings=warnings,
            )

        assert result is not None
        assert result["dx"] == pytest.approx(0.5)
        assert result["Q_W"] == pytest.approx(0.5 * 2_257_000.0, rel=1e-6)
        assert any("partial" in w.lower() for w in warnings)

    @pytest.mark.asyncio
    async def test_evaporation_uses_cold_side_dx_direction(self):
        """Cold side evaporating x_in=0 → x_out=1 → Q = ṁ · h_fg, mode=evaporating."""
        warnings: list[str] = []
        with patch(
            "hx_engine.app.adapters.thermo_adapter.get_saturation_props",
            return_value=_sat_water_1_atm(),
        ):
            result = await Step02HeatDuty._latent_duty_for_side(
                side="cold",
                fluid_name="water",
                T_in_C=100.0,
                T_out_C=100.0,
                m_dot_kg_s=2.0,
                pressure_Pa=101_325.0,
                x_in=0.0,
                x_out=1.0,
                warnings=warnings,
            )

        assert result is not None
        assert result["mode"] == "evaporating"
        assert result["Q_W"] == pytest.approx(2.0 * 2_257_000.0, rel=1e-6)

    @pytest.mark.asyncio
    async def test_zero_dx_returns_none(self):
        """x_in == x_out → no phase change occurring → fall back to sensible Q."""
        warnings: list[str] = []
        result = await Step02HeatDuty._latent_duty_for_side(
            side="hot",
            fluid_name="water",
            T_in_C=100.0,
            T_out_C=100.0,
            m_dot_kg_s=1.0,
            pressure_Pa=101_325.0,
            x_in=1.0,
            x_out=1.0,
            warnings=warnings,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_pressure_warns_and_returns_none(self):
        """ΔT≈0 + P_Pa is None → cannot compute saturation → warn + None."""
        warnings: list[str] = []
        result = await Step02HeatDuty._latent_duty_for_side(
            side="hot",
            fluid_name="water",
            T_in_C=100.0,
            T_out_C=100.0,
            m_dot_kg_s=1.0,
            pressure_Pa=None,
            x_in=1.0,
            x_out=0.0,
            warnings=warnings,
        )
        assert result is None
        assert any("operating pressure" in w.lower() for w in warnings)

    @pytest.mark.asyncio
    async def test_non_isothermal_dt_returns_none(self):
        """ΔT > 0.5°C → not phase-change service → return None."""
        warnings: list[str] = []
        result = await Step02HeatDuty._latent_duty_for_side(
            side="hot",
            fluid_name="water",
            T_in_C=120.0,
            T_out_C=80.0,
            m_dot_kg_s=1.0,
            pressure_Pa=101_325.0,
            x_in=1.0,
            x_out=0.0,
            warnings=warnings,
        )
        assert result is None


class TestQualityOverride:
    """Three tests guarding _quality_override applied_corrections plumbing."""

    def test_default_when_no_override(self):
        state = SimpleNamespace(applied_corrections={})
        assert Step02HeatDuty._quality_override(state, "hot_quality_out", 0.0) == 0.0

    def test_valid_override_used(self):
        state = SimpleNamespace(applied_corrections={"hot_quality_out": 0.3})
        assert Step02HeatDuty._quality_override(state, "hot_quality_out", 0.0) == 0.3

    def test_out_of_range_override_falls_back_to_default(self):
        state = SimpleNamespace(applied_corrections={"hot_quality_out": 1.5})
        assert Step02HeatDuty._quality_override(state, "hot_quality_out", 0.0) == 0.0
