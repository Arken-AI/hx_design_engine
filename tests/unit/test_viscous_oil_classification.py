"""Tests for viscous_oil fluid classification and U-estimate accuracy.

Validates that high-viscosity oils (lube oil, gear oil, hydraulic oil, etc.)
are classified as 'viscous_oil' rather than 'heavy_organic', and that the
U-estimate table returns appropriate values for laminar tube-side service.

References:
  - Perry's Table 11-4: viscous oil / water U ~ 20-100 W/m²K
  - Serth Table 3.5: heavy organic / water (laminar) U ~ 50-80 W/m²K
"""

from __future__ import annotations

import pytest

from hx_engine.app.data.u_assumptions import (
    classify_fluid_type,
    get_U_assumption,
)
from hx_engine.app.models.design_state import FluidProperties

# Viscosity boundary above which tube-side flow is laminar for typical
# industrial velocities — same threshold used in classify_fluid_type().
_VISCOUS_OIL_THRESHOLD_Pa_s = 0.005  # 5 cP

_VISCOUS_OIL_FLUID_NAMES = [
    "lubricating oil",
    "lube oil",
    "lubrication oil",
    "hydraulic oil",
    "mineral oil",
    "transformer oil",
    "gear oil",
    "engine oil",
    "turbine oil",
]


class TestViscousOilClassification:
    """Name-based classification of viscous oil fluids."""

    @pytest.mark.parametrize("fluid_name", _VISCOUS_OIL_FLUID_NAMES)
    def test_viscous_oil_names_classified_correctly(self, fluid_name: str):
        """Every known viscous oil name → 'viscous_oil'."""
        assert classify_fluid_type(fluid_name) == "viscous_oil"


class TestHeavyOrganicNotReclassified:
    """Fluids that should remain 'heavy_organic' after the split."""

    def test_ethylene_glycol_stays_heavy_organic(self):
        assert classify_fluid_type("ethylene glycol") == "heavy_organic"

    def test_thermal_oil_stays_heavy_organic(self):
        assert classify_fluid_type("thermal oil") == "heavy_organic"

    def test_propylene_glycol_stays_heavy_organic(self):
        assert classify_fluid_type("propylene glycol") == "heavy_organic"

    def test_fuel_oil_stays_heavy_organic(self):
        assert classify_fluid_type("fuel oil") == "heavy_organic"

    def test_vegetable_oil_stays_heavy_organic(self):
        assert classify_fluid_type("vegetable oil") == "heavy_organic"


class TestViscosityBasedClassification:
    """Property-based heuristics for unknown fluid names with high viscosity."""

    def test_high_viscosity_unknown_fluid_classified_as_viscous_oil(self):
        """Unknown name + viscosity >= threshold → 'viscous_oil'."""
        props = FluidProperties(
            density_kg_m3=870,
            viscosity_Pa_s=0.02,
            cp_J_kgK=2100,
            k_W_mK=0.13,
            Pr=300.0,
        )
        result = classify_fluid_type("unknown_process_oil", props)
        assert result == "viscous_oil"

    def test_at_threshold_viscosity_classified_as_viscous_oil(self):
        """Viscosity exactly at 5 cP boundary → 'viscous_oil'."""
        props = FluidProperties(
            density_kg_m3=860,
            viscosity_Pa_s=_VISCOUS_OIL_THRESHOLD_Pa_s,
            cp_J_kgK=2000,
            k_W_mK=0.13,
            Pr=76.9,
        )
        result = classify_fluid_type("some_oil", props)
        assert result == "viscous_oil"

    def test_below_threshold_viscosity_not_viscous_oil(self):
        """Viscosity below threshold + high density → 'heavy_organic'."""
        props = FluidProperties(
            density_kg_m3=920,
            viscosity_Pa_s=0.003,
            cp_J_kgK=2200,
            k_W_mK=0.15,
            Pr=44.0,
        )
        result = classify_fluid_type("some_organic", props)
        assert result == "heavy_organic"

    def test_name_takes_precedence_over_properties(self):
        """Named fluid classified by name even if viscosity suggests otherwise."""
        low_visc_props = FluidProperties(
            density_kg_m3=800,
            viscosity_Pa_s=0.001,
            cp_J_kgK=2000,
            k_W_mK=0.14,
            Pr=14.3,
        )
        assert classify_fluid_type("lube oil", low_visc_props) == "viscous_oil"


class TestViscousOilUEstimate:
    """U-estimate table returns correct values for viscous oil services."""

    def test_viscous_oil_water_u_mid(self):
        """viscous_oil/water → U_mid = 60, not 300."""
        u = get_U_assumption("lube oil", "cooling water")
        assert u["U_mid"] == 60

    def test_viscous_oil_water_u_range(self):
        """viscous_oil/water U range: 20-100 W/m²K."""
        u = get_U_assumption("lubricating oil", "water")
        assert u["U_low"] == 20
        assert u["U_mid"] == 60
        assert u["U_high"] == 100

    def test_water_viscous_oil_symmetric(self):
        """Lookup is symmetric: water/viscous_oil same as viscous_oil/water."""
        u_fwd = get_U_assumption("lube oil", "water")
        u_rev = get_U_assumption("water", "lube oil")
        assert u_fwd == u_rev

    def test_viscous_oil_steam_u_mid(self):
        """viscous_oil/steam → U_mid = 80."""
        u = get_U_assumption("lube oil", "steam")
        assert u["U_mid"] == 80

    def test_viscous_oil_viscous_oil_u_mid(self):
        """viscous_oil/viscous_oil → U_mid = 30."""
        u = get_U_assumption("lube oil", "gear oil")
        assert u["U_mid"] == 30

    def test_heavy_organic_water_unchanged(self):
        """heavy_organic/water → still U_mid = 300 (glycol, thermal oil)."""
        u = get_U_assumption("ethylene glycol", "water")
        assert u["U_mid"] == 300

    def test_viscous_oil_property_based_lookup(self):
        """Unknown name + high viscosity → viscous_oil U lookup."""
        high_visc_props = FluidProperties(
            density_kg_m3=880,
            viscosity_Pa_s=0.05,
            cp_J_kgK=2000,
            k_W_mK=0.12,
            Pr=833.3,
        )
        u = get_U_assumption(
            "process_oil_grade_7",
            "water",
            hot_properties=high_visc_props,
        )
        assert u["U_mid"] == 60


class TestViscousOilTableIntegrity:
    """viscous_oil U values are ordered and lower than heavy_organic equivalents."""

    @pytest.mark.parametrize("hot,cold", [
        ("lube oil", "water"),
        ("water", "lube oil"),
        ("lube oil", "steam"),
        ("steam", "lube oil"),
        ("lube oil", "gear oil"),
    ])
    def test_viscous_oil_pair_u_values_ordered(self, hot: str, cold: str):
        """U_low < U_mid < U_high for all representative viscous oil pairs."""
        u = get_U_assumption(hot, cold)
        assert u["U_low"] < u["U_mid"] < u["U_high"]

    def test_viscous_oil_water_u_lower_than_heavy_organic_water(self):
        """viscous_oil/water U_mid must be lower than heavy_organic/water U_mid."""
        visc_u = get_U_assumption("lube oil", "water")
        heavy_u = get_U_assumption("ethylene glycol", "water")
        assert visc_u["U_mid"] < heavy_u["U_mid"]
