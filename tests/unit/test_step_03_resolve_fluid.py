"""Tests for Piece 2: _resolve_fluid() — single-fluid property retrieval wrapper."""

from __future__ import annotations

from unittest.mock import patch, AsyncMock

import pytest

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import FluidProperties
from hx_engine.app.steps.step_03_fluid_props import Step03FluidProperties

# Reference water properties (NIST @ 35°C, 1 atm) for mocked tests
_WATER_35 = FluidProperties(
    density_kg_m3=994.0,
    viscosity_Pa_s=7.19e-4,
    cp_J_kgK=4178.0,
    k_W_mK=0.623,
    Pr=4.83,
)


class TestResolveFluid:
    """Seven tests guarding the single-fluid retrieval wrapper."""

    async def test_water_at_35C(self):
        """Water at 35°C returns NIST-range properties (cp≈4178, ρ≈994).

        Mocked because iapws/CoolProp may not be installed.
        """
        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            new_callable=AsyncMock,
            return_value=_WATER_35,
        ):
            props = await Step03FluidProperties._resolve_fluid("water", 35.0, 101325.0)

        assert props.cp_J_kgK == pytest.approx(4178.0, rel=0.02)
        assert props.density_kg_m3 == pytest.approx(994.0, rel=0.02)
        assert props.viscosity_Pa_s > 0
        assert props.k_W_mK > 0
        assert props.Pr > 0

    async def test_crude_oil_at_120C(self):
        """Crude oil at 120°C returns populated FluidProperties.

        All 5 properties must be positive; density in ~700–900 range.
        """
        props = await Step03FluidProperties._resolve_fluid("crude oil", 120.0, 101325.0)

        assert props.density_kg_m3 is not None
        assert 700 < props.density_kg_m3 < 900
        assert props.viscosity_Pa_s is not None and props.viscosity_Pa_s > 0
        assert props.cp_J_kgK is not None and props.cp_J_kgK > 0
        assert props.k_W_mK is not None and props.k_W_mK > 0
        assert props.Pr is not None and props.Pr > 0

    async def test_unknown_fluid_raises(self):
        """Fantasy fluid 'unobtanium' raises CalculationError with step_id=3."""
        with pytest.raises(CalculationError) as exc_info:
            await Step03FluidProperties._resolve_fluid("unobtanium", 50.0, 101325.0)
        assert exc_info.value.step_id == 3
        assert "unobtanium" in exc_info.value.message

    async def test_default_pressure(self):
        """Passing pressure_Pa=None uses 1 atm default — same result."""
        props_default = await Step03FluidProperties._resolve_fluid(
            "crude oil", 120.0, None,
        )
        props_atm = await Step03FluidProperties._resolve_fluid(
            "crude oil", 120.0, 101325.0,
        )
        # Petroleum correlations are T-only, so should be identical
        assert props_default.cp_J_kgK == pytest.approx(
            props_atm.cp_J_kgK, rel=1e-6,
        )

    async def test_high_pressure(self):
        """High pressure (1 MPa) still returns valid FluidProperties."""
        props = await Step03FluidProperties._resolve_fluid(
            "crude oil", 120.0, 1_000_000.0,
        )
        assert props.density_kg_m3 is not None and props.density_kg_m3 > 0

    async def test_empty_fluid_name_raises(self):
        """Empty string raises CalculationError — guard against blank input."""
        with pytest.raises(CalculationError, match="empty") as exc_info:
            await Step03FluidProperties._resolve_fluid("", 50.0, 101325.0)
        assert exc_info.value.step_id == 3

    async def test_crude_bare_falls_back(self):
        """Bare 'crude' falls through to 'crude oil' via petroleum tier."""
        props = await Step03FluidProperties._resolve_fluid("crude", 120.0, 101325.0)

        assert props.density_kg_m3 is not None and props.density_kg_m3 > 0
        assert props.cp_J_kgK is not None and props.cp_J_kgK > 0
        # Should match "crude oil" results
        props_explicit = await Step03FluidProperties._resolve_fluid(
            "crude oil", 120.0, 101325.0,
        )
        assert props.cp_J_kgK == pytest.approx(
            props_explicit.cp_J_kgK, rel=1e-6,
        )

    async def test_resolve_properties_wraps_unexpected_error(self):
        """Pydantic ValidationError from the adapter is wrapped as CalculationError(3).

        Guards the narrowed ``except PydanticValidationError`` arm in
        ``_resolve_fluid``: when the thermo backend produces non-physical values
        that fail FluidProperties' field validators, the pipeline must surface
        a typed CalculationError with ``step_id == 3`` rather than bubbling an
        opaque "Unexpected error in step 3".
        """
        from pydantic import ValidationError as _PVE

        # Build a real ValidationError by trying to construct an invalid model.
        try:
            FluidProperties(
                density_kg_m3=-1.0,
                viscosity_Pa_s=-1.0,
                cp_J_kgK=-1.0,
                k_W_mK=-1.0,
                Pr=-1.0,
            )
            real_validation_error: _PVE | None = None
        except _PVE as ve:
            real_validation_error = ve

        assert real_validation_error is not None, (
            "FluidProperties did not reject negative inputs — test setup invalid"
        )

        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            new_callable=AsyncMock,
            side_effect=real_validation_error,
        ):
            with pytest.raises(CalculationError) as exc_info:
                await Step03FluidProperties._resolve_fluid(
                    "ethanol", 250.0, 101325.0,
                )

        assert exc_info.value.step_id == 3
        assert "Non-physical" in exc_info.value.message
        assert "ethanol" in exc_info.value.message

    async def test_resolve_properties_does_not_swallow_programming_errors(self):
        """AttributeError / KeyError must propagate unchanged (not be relabelled
        as 'non-physical properties'). Catching them would hide real bugs."""
        with patch(
            "hx_engine.app.steps.step_03_fluid_props.get_fluid_properties",
            new_callable=AsyncMock,
            side_effect=AttributeError("'NoneType' object has no attribute 'cp_J_kgK'"),
        ):
            with pytest.raises(AttributeError):
                await Step03FluidProperties._resolve_fluid(
                    "water", 50.0, 101325.0,
                )
