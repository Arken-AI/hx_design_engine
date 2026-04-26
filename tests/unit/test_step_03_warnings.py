"""Tests for Piece 6: Corner cases & warnings."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import DesignState, FluidProperties
from hx_engine.app.steps.step_03_fluid_props import Step03FluidProperties

# Standard mock properties
_WATER_PROPS = FluidProperties(
    density_kg_m3=994.0, viscosity_Pa_s=7.19e-4,
    cp_J_kgK=4178.0, k_W_mK=0.623, Pr=4.83,
)

_WATER_NEAR_BOILING = FluidProperties(
    density_kg_m3=960.0, viscosity_Pa_s=2.82e-4,
    cp_J_kgK=4216.0, k_W_mK=0.679, Pr=1.75,
)

_WATER_NEAR_FREEZING = FluidProperties(
    density_kg_m3=999.8, viscosity_Pa_s=1.79e-3,
    cp_J_kgK=4217.0, k_W_mK=0.561, Pr=13.44,
)

_HIGH_VISC_OIL = FluidProperties(
    density_kg_m3=950.0, viscosity_Pa_s=0.15,
    cp_J_kgK=1800.0, k_W_mK=0.50, Pr=540.0,
)


class TestCornerCases:
    """Six tests guarding corner-case warnings."""

    async def test_crude_no_api_warning(self):
        """crude oil → warning about generic API assumption."""
        state = DesignState(
            hot_fluid_name="crude oil",
            cold_fluid_name="thermal oil",
            T_hot_in_C=150.0,
            T_hot_out_C=90.0,
            T_cold_in_C=30.0,
            T_cold_out_C=60.0,
        )
        step = Step03FluidProperties()
        result = await step.execute(state)

        api_warnings = [w for w in result.warnings if "API" in w]
        assert len(api_warnings) >= 1
        assert "generic" in api_warnings[0].lower() or "API" in api_warnings[0]

    async def test_water_near_boiling_warning(self):
        """Water at T_mean=98°C, P=1 atm → phase change warning."""

        def _mock_adapter(fluid_name, T_mean_C, pressure_Pa=None):
            if T_mean_C > 90:
                return _WATER_NEAR_BOILING
            return _WATER_PROPS

        state = DesignState(
            hot_fluid_name="water",
            cold_fluid_name="water",
            T_hot_in_C=100.0,
            T_hot_out_C=96.0,
            T_cold_in_C=30.0,
            T_cold_out_C=60.0,
            P_hot_Pa=101325.0,
            P_cold_Pa=101325.0,
        )
        step = Step03FluidProperties()
        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            side_effect=_mock_adapter,
        ):
            result = await step.execute(state)

        boiling_warnings = [w for w in result.warnings if "boiling" in w.lower()]
        assert len(boiling_warnings) >= 1

    async def test_water_below_5C_warning(self):
        """Water at T_mean=3°C → freezing/phase change warning."""

        def _mock_adapter(fluid_name, T_mean_C, pressure_Pa=None):
            return _WATER_NEAR_FREEZING

        state = DesignState(
            hot_fluid_name="ethylene glycol",
            cold_fluid_name="water",
            T_hot_in_C=20.0,
            T_hot_out_C=10.0,
            T_cold_in_C=1.0,
            T_cold_out_C=5.0,
            P_cold_Pa=101325.0,
        )
        step = Step03FluidProperties()
        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            side_effect=_mock_adapter,
        ):
            result = await step.execute(state)

        freeze_warnings = [w for w in result.warnings if "freezing" in w.lower()]
        assert len(freeze_warnings) >= 1

    async def test_high_viscosity_sieder_tate_warning(self):
        """Heavy oil with μ > 0.1 → Sieder-Tate warning."""

        def _mock_adapter(fluid_name, T_mean_C, pressure_Pa=None):
            if "heavy" in (fluid_name or "").lower() or "fuel" in (fluid_name or "").lower():
                return _HIGH_VISC_OIL
            return _WATER_PROPS

        state = DesignState(
            hot_fluid_name="heavy fuel oil",
            cold_fluid_name="water",
            T_hot_in_C=100.0,
            T_hot_out_C=60.0,
            T_cold_in_C=20.0,
            T_cold_out_C=40.0,
        )
        step = Step03FluidProperties()
        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            side_effect=_mock_adapter,
        ):
            result = await step.execute(state)

        visc_warnings = [w for w in result.warnings if "Sieder-Tate" in w]
        assert len(visc_warnings) >= 1

    async def test_normal_case_no_warnings(self):
        """Ethanol + thermal oil at typical temps → no corner-case warnings."""
        state = DesignState(
            hot_fluid_name="thermal oil",
            cold_fluid_name="ethanol",
            T_hot_in_C=150.0,
            T_hot_out_C=100.0,
            T_cold_in_C=30.0,
            T_cold_out_C=60.0,
            P_hot_Pa=101325.0,
            P_cold_Pa=101325.0,
        )
        step = Step03FluidProperties()

        # Stable props: constant viscosity (ratio=1.0 → no variation warning),
        # confidence=1.0 (no petroleum-source warning), viscosity < 0.1 Pa·s.
        _STABLE_PROPS = FluidProperties(
            density_kg_m3=880.0,
            viscosity_Pa_s=0.005,
            cp_J_kgK=2200.0,
            k_W_mK=0.14,
            Pr=78.0,
        )

        async def _stable_adapter(fluid_name, T_mean_C, pressure_Pa=None):
            return _STABLE_PROPS

        # Provide a valid freezing point well below min operating temperature
        # (thermal oil min = 100°C = 373.15 K; ethanol min = 30°C = 303.15 K;
        # return T_freeze = 200 K for both so margin is positive and large).
        def _stable_freeze(fluid_name, pressure_Pa=None):
            return 200.0, "test"

        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            side_effect=_stable_adapter,
        ), patch(
            "hx_engine.app.steps.step_03_fluid_props.get_freezing_or_pour_point",
            side_effect=_stable_freeze,
        ):
            result = await step.execute(state)

        # Should have no warnings (stable props, no crude, no water, no high viscosity)
        assert len(result.warnings) == 0

    async def test_unknown_fluid_error_is_helpful(self):
        """'unobtanium' → CalculationError message contains fluid name."""
        state = DesignState(
            hot_fluid_name="unobtanium",
            cold_fluid_name="ethanol",
            T_hot_in_C=150.0,
            T_hot_out_C=90.0,
            T_cold_in_C=30.0,
            T_cold_out_C=60.0,
        )
        step = Step03FluidProperties()
        with pytest.raises(CalculationError) as exc_info:
            await step.execute(state)

        assert "unobtanium" in exc_info.value.message
        assert exc_info.value.step_id == 3
