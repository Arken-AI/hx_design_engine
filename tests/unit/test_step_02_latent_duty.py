"""Tests for Step 02 latent (phase-change) duty path — P1-5 regression guard.

Covers ``_latent_duty_for_side`` which produces ``Q = ṁ · h_fg · Δx`` for
isothermal sides and the ``_quality_override`` helper that reads partial
phase-change endpoints from ``state.applied_corrections``.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import DesignState, FluidProperties
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


# ═══════════════════════════════════════════════════════════════════════════════
# Vapor-inlet condenser path — three-segment energy balance
# (desuperheat + condense + optional subcool / partial-condense).
#
# These tests guard the new path in ``Step02HeatDuty.execute`` that intercepts
# vapor-suffixed hot streams (e.g. "ethanol vapor") and replaces the
# sensible-Cp solve for T_hot_out_C with a saturation-based balance.
# ═══════════════════════════════════════════════════════════════════════════════


# Reference saturation block used by the condenser tests.
# T_sat = 100°C, h_fg = 2.257 MJ/kg, cp_g = 2000, cp_f = 4200 (water-like).
_SAT_COND = {
    "T_sat_C": 100.0,
    "h_fg": 2_257_000.0,
    "cp_g": 2000.0,
    "cp_f": 4200.0,
}

_FP_VAPOR = FluidProperties(
    density_kg_m3=1.0,
    viscosity_Pa_s=1.5e-5,
    cp_J_kgK=2000.0,
    k_W_mK=0.025,
    Pr=0.9,
)
_FP_WATER = FluidProperties(
    density_kg_m3=997.0,
    viscosity_Pa_s=8.9e-4,
    cp_J_kgK=4181.0,
    k_W_mK=0.6,
    Pr=6.2,
)


def _vapor_state(
    *,
    T_hot_in_C: float,
    T_hot_out_C: float | None,
    T_cold_in_C: float,
    T_cold_out_C: float,
    m_dot_hot: float,
    m_dot_cold: float,
    P_hot_Pa: float | None,
    hot_fluid_name: str = "ethanol vapor",
    hot_phase: str | None = None,
) -> DesignState:
    """Build a minimal DesignState representing a vapor-condenser problem."""
    return DesignState(
        hot_fluid_name=hot_fluid_name,
        cold_fluid_name="water",
        T_hot_in_C=T_hot_in_C,
        T_hot_out_C=T_hot_out_C,
        T_cold_in_C=T_cold_in_C,
        T_cold_out_C=T_cold_out_C,
        m_dot_hot_kg_s=m_dot_hot,
        m_dot_cold_kg_s=m_dot_cold,
        P_hot_Pa=P_hot_Pa,
        P_cold_Pa=101_325.0,
        hot_phase=hot_phase,
    )


def _fp_side_effect(name, *_args, **_kwargs):
    """Return vapor-side or water-side mocked FluidProperties based on name."""
    n = (name or "").lower()
    if "vapor" in n or "vapour" in n or "gas" in n:
        return _FP_VAPOR
    return _FP_WATER


class TestVaporInletCondenser:
    """Four tests guarding the vapor-inlet three-segment condenser balance."""

    @pytest.mark.asyncio
    async def test_full_condense_subcool_path(self):
        """Q_cold > Q_desup + Q_cond_full → full condense + subcool branch.

        State: hot=ethanol vapor 200°C, m_hot=0.1 kg/s; cold water 30→60°C,
        m_cold sized so Q_cold = 250 kW > (Q_desup=20 kW + Q_cond=225.7 kW).
        Expect T_hot_out_C ≈ 100 − ΔT_sub (≈ 89.8°C) and a "subcool" basis.
        """
        m_cold = 250_000.0 / (4181.0 * 30.0)  # ≈ 1.993 kg/s
        state = _vapor_state(
            T_hot_in_C=200.0,
            T_hot_out_C=None,
            T_cold_in_C=30.0,
            T_cold_out_C=60.0,
            m_dot_hot=0.1,
            m_dot_cold=m_cold,
            P_hot_Pa=101_325.0,
        )

        with patch(
            "hx_engine.app.adapters.thermo_adapter.get_fluid_properties",
            new_callable=AsyncMock,
            side_effect=_fp_side_effect,
        ), patch(
            "hx_engine.app.adapters.thermo_adapter.get_saturation_props",
            return_value=_SAT_COND,
        ):
            result = await Step02HeatDuty().execute(state)

        assert result.outputs["heat_duty_basis"] in {
            "condense+subcool",
            "desuperheat+condense+subcool",
        }
        assert result.outputs["T_sat_C"] == pytest.approx(100.0)
        assert result.outputs["lambda_J_kg"] == pytest.approx(2_257_000.0)
        # T_hot_out should be below T_sat (subcooled liquid)
        assert result.outputs["T_hot_out_C"] < 100.0
        assert result.outputs["T_hot_out_C"] > -100.0  # above the runaway guard
        # x_out is only emitted on the partial-condense branch
        assert "x_out" not in result.outputs
        assert result.validation_passed is True

    @pytest.mark.asyncio
    async def test_partial_condense_path(self):
        """Q_cold < Q_desup + Q_cond_full → partial-condense branch.

        State: hot=ethanol vapor 200°C, m_hot=0.1 kg/s; cold water 30→50°C,
        m_cold sized so Q_cold = 100 kW < Q_no_subcool = 245.7 kW.
        Expect T_hot_out_C ≈ T_sat (100°C) and 0 ≤ x_out ≤ 1.
        """
        m_cold = 100_000.0 / (4181.0 * 20.0)  # ≈ 1.196 kg/s
        state = _vapor_state(
            T_hot_in_C=200.0,
            T_hot_out_C=None,
            T_cold_in_C=30.0,
            T_cold_out_C=50.0,
            m_dot_hot=0.1,
            m_dot_cold=m_cold,
            P_hot_Pa=101_325.0,
        )

        with patch(
            "hx_engine.app.adapters.thermo_adapter.get_fluid_properties",
            new_callable=AsyncMock,
            side_effect=_fp_side_effect,
        ), patch(
            "hx_engine.app.adapters.thermo_adapter.get_saturation_props",
            return_value=_SAT_COND,
        ):
            result = await Step02HeatDuty().execute(state)

        assert "partial_condense" in result.outputs["heat_duty_basis"]
        assert result.outputs["T_hot_out_C"] == pytest.approx(100.0, abs=1e-6)
        assert 0.0 <= result.outputs["x_out"] <= 1.0
        # x_out should reflect partial condensation: dropped from 1.0 by Q_cond_used / Q_cond_full
        # Q_desup = 0.1 * 2000 * 100 = 20 kW; Q_cond_used = 100 - 20 = 80 kW;
        # x_out = 1 - 80_000 / 225_700 ≈ 0.6455
        assert result.outputs["x_out"] == pytest.approx(0.6455, abs=0.01)
        assert result.validation_passed is True

    @pytest.mark.asyncio
    async def test_vapor_inlet_missing_pressure_escalates(self):
        """Vapor hot inlet without P_hot_Pa must raise CalculationError(2)."""
        state = _vapor_state(
            T_hot_in_C=200.0,
            T_hot_out_C=None,
            T_cold_in_C=30.0,
            T_cold_out_C=60.0,
            m_dot_hot=0.1,
            m_dot_cold=2.0,
            P_hot_Pa=None,
        )

        with patch(
            "hx_engine.app.adapters.thermo_adapter.get_fluid_properties",
            new_callable=AsyncMock,
            side_effect=_fp_side_effect,
        ):
            with pytest.raises(CalculationError) as exc_info:
                await Step02HeatDuty().execute(state)

        assert exc_info.value.step_id == 2
        assert "P_hot_Pa" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_runaway_temp_guard_catches_nonphysical_solve(self):
        """A solved temperature outside [-100, 1500]°C must raise CalculationError(2).

        Path: non-vapor inlet so condenser branch is skipped; we monkey-patch
        ``_calculate_missing_temp`` to return a runaway value, simulating the
        ethanol-vapor sensible-Cp pathology where T_hot_out solves to ~−471°C.
        """
        state = DesignState(
            hot_fluid_name="ethanol",  # no "vapor" suffix → condenser branch skipped
            cold_fluid_name="water",
            T_hot_in_C=200.0,
            T_hot_out_C=None,
            T_cold_in_C=30.0,
            T_cold_out_C=60.0,
            m_dot_hot_kg_s=0.1,
            m_dot_cold_kg_s=2.0,
            P_hot_Pa=101_325.0,
            P_cold_Pa=101_325.0,
        )

        runaway_result = {
            "calculated_field": "T_hot_out_C",
            "T_hot_in_C": 200.0,
            "T_hot_out_C": -471.0,
            "T_cold_in_C": 30.0,
            "T_cold_out_C": 60.0,
            "Q_known_side_W": 1e6,
        }

        with patch(
            "hx_engine.app.adapters.thermo_adapter.get_fluid_properties",
            new_callable=AsyncMock,
            side_effect=_fp_side_effect,
        ), patch.object(
            Step02HeatDuty,
            "_calculate_missing_temp",
            staticmethod(lambda **_kw: runaway_result),
        ):
            with pytest.raises(CalculationError) as exc_info:
                await Step02HeatDuty().execute(state)

        assert exc_info.value.step_id == 2
        assert "physical range" in exc_info.value.message


class TestVaporPhaseDetection:
    """Three tests guarding broadened vapor-detection signals.

    The condenser branch must fire when ANY of these is true:
      1. ``state.hot_phase`` is one of {vapor, vapour, gas, condensing, superheated}
      2. ``state.hot_fluid_name`` ends with a recognised phase suffix
    """

    @pytest.mark.asyncio
    async def test_hot_phase_vapor_with_clean_name_triggers_condenser(self):
        """hot_phase='vapor' + clean name 'ethanol' must take the condenser path.

        Regression guard: the previous implementation only inspected the fluid
        name suffix, so an upstream parser that correctly populated hot_phase
        but wrote a clean fluid name fell through to the sensible-Cp path and
        produced runaway negative temperatures.
        """
        m_cold = 250_000.0 / (4181.0 * 30.0)
        state = _vapor_state(
            T_hot_in_C=200.0,
            T_hot_out_C=None,
            T_cold_in_C=30.0,
            T_cold_out_C=60.0,
            m_dot_hot=0.1,
            m_dot_cold=m_cold,
            P_hot_Pa=101_325.0,
            hot_fluid_name="ethanol",  # clean name, no suffix
            hot_phase="vapor",
        )

        with patch(
            "hx_engine.app.adapters.thermo_adapter.get_fluid_properties",
            new_callable=AsyncMock,
            side_effect=_fp_side_effect,
        ), patch(
            "hx_engine.app.adapters.thermo_adapter.get_saturation_props",
            return_value=_SAT_COND,
        ):
            result = await Step02HeatDuty().execute(state)

        # Condenser path fired → heat_duty_basis is one of the condenser labels
        assert result.outputs["heat_duty_basis"] in {
            "condense+subcool",
            "desuperheat+condense+subcool",
            "partial_condense",
            "desuperheat+partial_condense",
        }
        assert "T_sat_C" in result.outputs

    @pytest.mark.asyncio
    async def test_gases_suffix_triggers_condenser(self):
        """' gases' suffix (plural) must also be recognised — matches adapter
        _PHASE_SUFFIXES so detection here and name-stripping there agree."""
        m_cold = 250_000.0 / (4181.0 * 30.0)
        state = _vapor_state(
            T_hot_in_C=200.0,
            T_hot_out_C=None,
            T_cold_in_C=30.0,
            T_cold_out_C=60.0,
            m_dot_hot=0.1,
            m_dot_cold=m_cold,
            P_hot_Pa=101_325.0,
            hot_fluid_name="ethanol gases",
        )

        with patch(
            "hx_engine.app.adapters.thermo_adapter.get_fluid_properties",
            new_callable=AsyncMock,
            side_effect=_fp_side_effect,
        ), patch(
            "hx_engine.app.adapters.thermo_adapter.get_saturation_props",
            return_value=_SAT_COND,
        ):
            result = await Step02HeatDuty().execute(state)

        assert "T_sat_C" in result.outputs

    @pytest.mark.asyncio
    async def test_explicit_liquid_phase_skips_condenser(self):
        """hot_phase='liquid' on a clean name must NOT trigger the condenser path,
        even when other heuristics could be ambiguous."""
        m_cold_balanced = (50.0 * 1900.0 * 60.0) / (4181.0 * 30.0)
        state = _vapor_state(
            T_hot_in_C=150.0,
            T_hot_out_C=90.0,
            T_cold_in_C=30.0,
            T_cold_out_C=60.0,
            m_dot_hot=50.0,
            m_dot_cold=m_cold_balanced,
            P_hot_Pa=101_325.0,
            hot_fluid_name="crude oil",
            hot_phase="liquid",
        )

        # If the condenser path fires, get_saturation_props would be invoked.
        # We assert it is NOT called.
        with patch(
            "hx_engine.app.adapters.thermo_adapter.get_fluid_properties",
            new_callable=AsyncMock,
            side_effect=_fp_side_effect,
        ), patch(
            "hx_engine.app.adapters.thermo_adapter.get_saturation_props",
        ) as _sat_mock:
            result = await Step02HeatDuty().execute(state)

        assert _sat_mock.call_count == 0
        assert "T_sat_C" not in result.outputs


class TestVaporCondenserPreconditions:
    """Two tests guarding hard pre-conditions on the vapor-condenser branch.

    Previously the branch silently fell through to the sensible-Cp solver when
    cold-side data was incomplete, re-introducing the runaway-temperature bug
    this entire path was added to prevent. Each missing input must now surface
    as a typed CalculationError(2) that names the offending field.
    """

    @pytest.mark.asyncio
    async def test_vapor_path_missing_T_cold_out_raises(self):
        """Vapor inlet + missing T_cold_out_C → CalculationError(2) naming the field.

        Crucially: the upstream pre-condition check at the top of execute()
        accepts ``T_cold_in_C OR T_cold_out_C`` (only one is required), so
        T_cold_out_C=None reaches the condenser branch and would historically
        have caused a silent fall-through. This test pins that down.
        """
        state = _vapor_state(
            T_hot_in_C=200.0,
            T_hot_out_C=None,
            T_cold_in_C=30.0,
            T_cold_out_C=None,  # missing — would silently fall through pre-fix
            m_dot_hot=0.1,
            m_dot_cold=2.0,
            P_hot_Pa=101_325.0,
        )

        with patch(
            "hx_engine.app.adapters.thermo_adapter.get_fluid_properties",
            new_callable=AsyncMock,
            side_effect=_fp_side_effect,
        ), patch(
            "hx_engine.app.adapters.thermo_adapter.get_saturation_props",
            return_value=_SAT_COND,
        ):
            with pytest.raises(CalculationError) as exc_info:
                await Step02HeatDuty().execute(state)

        assert exc_info.value.step_id == 2
        assert "T_cold_out_C" in exc_info.value.message
        assert "condenser" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_vapor_path_missing_m_dot_cold_raises(self):
        """Vapor inlet + missing m_dot_cold_kg_s → CalculationError(2) naming the field."""
        state = DesignState(
            hot_fluid_name="ethanol vapor",
            cold_fluid_name="water",
            T_hot_in_C=200.0,
            T_hot_out_C=None,
            T_cold_in_C=30.0,
            T_cold_out_C=60.0,
            m_dot_hot_kg_s=0.1,
            m_dot_cold_kg_s=None,  # missing — but m_dot_hot satisfies upstream check
            P_hot_Pa=101_325.0,
            P_cold_Pa=101_325.0,
        )

        with patch(
            "hx_engine.app.adapters.thermo_adapter.get_fluid_properties",
            new_callable=AsyncMock,
            side_effect=_fp_side_effect,
        ), patch(
            "hx_engine.app.adapters.thermo_adapter.get_saturation_props",
            return_value=_SAT_COND,
        ):
            with pytest.raises(CalculationError) as exc_info:
                await Step02HeatDuty().execute(state)

        assert exc_info.value.step_id == 2
        assert "m_dot_cold_kg_s" in exc_info.value.message
