"""Unit tests for P2-20 volumetric flow conversion table + resolver."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional
from unittest.mock import patch

import pytest

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.core.volumetric_flow import (
    SUPPORTED_VOLUMETRIC_UNITS,
    apply_flow_inputs,
    resolve_mass_flow,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

@dataclass
class FakeProps:
    density_kg_m3: Optional[float]
    property_source: str = "fake"


def _patch_props(rho: Optional[float], source: str = "fake"):
    """Patch get_fluid_properties to return a fixed density."""

    async def _fake(name, T_C, P=None):
        return FakeProps(density_kg_m3=rho, property_source=source)

    return patch(
        "hx_engine.app.core.volumetric_flow.get_fluid_properties",
        side_effect=_fake,
    )


# ---------------------------------------------------------------------------
# Conversion table — pure unit math
# ---------------------------------------------------------------------------

class TestConversionTable:
    def test_kg_s_passes_through_unchanged(self):
        basis, factor = SUPPORTED_VOLUMETRIC_UNITS["kg_s"]
        assert basis == "mass"
        assert factor == 1.0

    def test_m3_h_factor_is_one_over_3600(self):
        _, factor = SUPPORTED_VOLUMETRIC_UNITS["m3_h"]
        assert math.isclose(factor, 1.0 / 3600.0)

    def test_us_gpm_factor_matches_published_value(self):
        # 1 US gpm = 6.30901964×10⁻⁵ m³/s
        _, factor = SUPPORTED_VOLUMETRIC_UNITS["gpm"]
        assert math.isclose(factor, 6.30902e-5, rel_tol=1e-4)

    def test_us_oil_barrel_per_day_factor(self):
        # 1 US bbl/d ≈ 1.84013×10⁻⁶ m³/s
        _, factor = SUPPORTED_VOLUMETRIC_UNITS["bbl_d"]
        assert math.isclose(factor, 1.84013e-6, rel_tol=1e-4)

    def test_all_units_have_basis_and_positive_factor(self):
        for unit, (basis, factor) in SUPPORTED_VOLUMETRIC_UNITS.items():
            assert basis in {
                "mass", "liquid_vol",
                "gas_std_15C_1atm", "gas_std_0C_1atm",
            }
            assert factor > 0


# ---------------------------------------------------------------------------
# resolve_mass_flow — main paths
# ---------------------------------------------------------------------------

class TestResolveMassFlow:
    @pytest.mark.asyncio
    async def test_mass_unit_passthrough(self):
        res = await resolve_mass_flow(
            value=42.0, unit="kg_s",
            fluid_name="water", T_in_C=25.0, P_in_Pa=None,
        )
        assert res.m_dot_kg_s == 42.0
        assert res.density_kg_m3 is None

    @pytest.mark.asyncio
    async def test_liquid_volumetric_uses_inlet_density(self):
        with _patch_props(rho=997.0, source="iapws"):
            res = await resolve_mass_flow(
                value=3600.0, unit="m3_h",
                fluid_name="water", T_in_C=25.0, P_in_Pa=101325.0,
            )
        # 1 m³/s × 997 kg/m³ = 997 kg/s
        assert math.isclose(res.m_dot_kg_s, 997.0, rel_tol=1e-9)
        assert res.density_source == "iapws"

    @pytest.mark.asyncio
    async def test_gas_std_requires_pressure(self):
        with pytest.raises(CalculationError) as exc:
            await resolve_mass_flow(
                value=1000.0, unit="sm3_h",
                fluid_name="methane", T_in_C=20.0, P_in_Pa=None,
            )
        assert "operating pressure" in str(exc.value)


# ---------------------------------------------------------------------------
# Negative paths
# ---------------------------------------------------------------------------

class TestNegativePaths:
    @pytest.mark.asyncio
    async def test_unknown_unit_rejected(self):
        with pytest.raises(CalculationError) as exc:
            await resolve_mass_flow(
                value=10.0, unit="lbm_hr",
                fluid_name="water", T_in_C=25.0, P_in_Pa=101325.0,
            )
        assert "Unknown flow unit" in str(exc.value)

    @pytest.mark.asyncio
    async def test_non_positive_value_rejected(self):
        with pytest.raises(CalculationError):
            await resolve_mass_flow(
                value=0.0, unit="kg_s",
                fluid_name="water", T_in_C=25.0, P_in_Pa=None,
            )


# ---------------------------------------------------------------------------
# apply_flow_inputs — router-side helper
# ---------------------------------------------------------------------------

class TestApplyFlowInputs:
    @pytest.mark.asyncio
    async def test_no_flow_objects_passes_through(self):
        d = {"m_dot_hot_kg_s": 5.0, "T_hot_in_C": 80.0}
        out, hot, cold = await apply_flow_inputs(
            d, hot_flow=None, cold_flow=None,
            hot_fluid_name="water", cold_fluid_name="water",
        )
        assert out == d
        assert hot is None and cold is None

    @pytest.mark.asyncio
    async def test_hot_flow_overrides_m_dot_and_strips_key(self):
        d = {
            "hot_flow": {"value": 3600.0, "unit": "m3_h"},
            "T_hot_in_C": 25.0,
            "P_hot_Pa": 101325.0,
        }
        with _patch_props(rho=1000.0):
            out, hot, _ = await apply_flow_inputs(
                d,
                hot_flow=d["hot_flow"], cold_flow=None,
                hot_fluid_name="water", cold_fluid_name=None,
            )
        assert "hot_flow" not in out
        assert math.isclose(out["m_dot_hot_kg_s"], 1000.0)
        assert hot.density_kg_m3 == 1000.0
