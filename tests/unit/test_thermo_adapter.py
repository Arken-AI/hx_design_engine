"""Tests for Piece 1: Thermo adapter — Cp / fluid property retrieval.

Tests cover:
- Tier 1: iapws (water Cp, density, viscosity, near-boiling, fallback to CoolProp)
- Tier 3: thermo library (acetic acid, diphenyl oxide — NOT in CoolProp)
- Tier 4: Petroleum correlations (T-dependent, crude-specific, name resolution)
- Tier 5: Specialty fluids (thermal oil T-dependent)
- Failure modes: unknown fluid, out-of-range properties
"""

import pytest

from hx_engine.app.adapters.thermo_adapter import (
    get_cp,
    get_fluid_properties,
    _get_props_iapws,
    _get_props_thermo,
    _COOLPROP_MAP,
)
from hx_engine.app.adapters.petroleum_correlations import (
    cp_petroleum,
    density_petroleum,
    viscosity_petroleum,
    conductivity_petroleum,
    get_petroleum_properties,
    resolve_petroleum_name,
    _api_to_sg,
    PetroleumCharacterization,
)
from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import FluidProperties


# ═══════════════════════════════════════════════════════════════════════════════
# Tier 1 — iapws (water / steam)
# ═══════════════════════════════════════════════════════════════════════════════

class TestWaterAt25C:
    """NIST reference: Cp ≈ 4181 J/kg·K at 25°C, 1 atm."""

    def test_water_at_25C_cp(self):
        props = get_fluid_properties("water", 25.0)
        assert props.cp_J_kgK == pytest.approx(4181.0, rel=0.01)

    def test_water_at_25C_density(self):
        """NIST reference: ρ ≈ 997.05 kg/m³ at 25°C, 1 atm."""
        props = get_fluid_properties("water", 25.0)
        assert props.density_kg_m3 == pytest.approx(997.05, rel=0.01)

    def test_water_at_25C_viscosity(self):
        """NIST reference: μ ≈ 8.9e-4 Pa·s at 25°C, 1 atm."""
        props = get_fluid_properties("water", 25.0)
        assert props.viscosity_Pa_s == pytest.approx(8.9e-4, rel=0.05)


class TestFluidNearBoiling:
    def test_fluid_near_boiling(self):
        """Water at 99°C, 1 atm — must return liquid props, not gas."""
        props = get_fluid_properties("water", 99.0)
        assert props.density_kg_m3 > 900.0
        assert props.cp_J_kgK == pytest.approx(4215.0, rel=0.02)


class TestFallbackChain:
    def test_fallback_chain_works(self, monkeypatch):
        """Mock iapws failing → CoolProp should handle water correctly."""
        def _iapws_raises(*args, **kwargs):
            raise CalculationError(2, "mocked iapws failure")

        monkeypatch.setattr(
            "hx_engine.app.adapters.thermo_adapter._get_props_iapws",
            _iapws_raises,
        )
        props = get_fluid_properties("water", 25.0)
        assert props.cp_J_kgK == pytest.approx(4181.0, rel=0.01)
        assert props.density_kg_m3 == pytest.approx(997.0, rel=0.01)


# ═══════════════════════════════════════════════════════════════════════════════
# Tier 3 — thermo library (broad chemical database)
# ═══════════════════════════════════════════════════════════════════════════════

class TestThermoLibrary:
    """Compounds that exist in thermo but NOT in CoolProp's 124 fluids."""

    def test_acetic_acid_cp_reasonable(self):
        """Acetic acid Cp ≈ 2050–2200 J/kg·K at 25°C (published handbooks)."""
        props = _get_props_thermo("acetic acid", 25.0, 101325.0)
        assert 1900 <= props.cp_J_kgK <= 2400

    def test_acetic_acid_density(self):
        """Acetic acid ρ ≈ 1042–1049 kg/m³ at 25°C."""
        props = _get_props_thermo("acetic acid", 25.0, 101325.0)
        assert 1020 <= props.density_kg_m3 <= 1060

    def test_acetic_acid_all_fields(self):
        props = _get_props_thermo("acetic acid", 25.0, 101325.0)
        assert props.density_kg_m3 is not None
        assert props.viscosity_Pa_s is not None
        assert props.cp_J_kgK is not None
        assert props.k_W_mK is not None
        assert props.Pr is not None

    def test_diphenyl_oxide_at_200C(self):
        """Diphenyl oxide (Dowtherm A component) at 200°C."""
        props = _get_props_thermo("diphenyl oxide", 200.0, 101325.0)
        assert 1800 <= props.cp_J_kgK <= 2300
        assert props.density_kg_m3 > 800

    def test_thermo_temperature_dependent(self):
        """Same compound at two temperatures → different Cp."""
        props_25 = _get_props_thermo("acetic acid", 25.0, 101325.0)
        props_80 = _get_props_thermo("acetic acid", 80.0, 101325.0)
        assert props_25.cp_J_kgK != props_80.cp_J_kgK

    def test_thermo_unknown_fluid_raises(self):
        """Completely made-up fluid → CalculationError."""
        with pytest.raises(CalculationError):
            _get_props_thermo("unobtanium", 50.0, 101325.0)

    def test_thermo_resolves_via_get_fluid_properties(self):
        """acetic acid is not in CoolProp map → falls through to thermo."""
        props = get_fluid_properties("acetic acid", 25.0)
        assert props.cp_J_kgK is not None
        assert props.density_kg_m3 is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Tier 4 — Petroleum correlations
# ═══════════════════════════════════════════════════════════════════════════════

class TestPetroleumCorrelations:
    """Validate individual correlation functions against hand-calculations."""

    def test_api_to_sg(self):
        """API 10 → SG 1.0, API ~33 → SG ~0.86."""
        assert _api_to_sg(10.0) == pytest.approx(1.0, rel=0.001)
        assert _api_to_sg(33.0) == pytest.approx(141.5 / 164.5, rel=0.001)

    def test_cp_lee_kesler_hand_calc(self):
        """Maya crude (API 22.2) at 120°C → hand-calc ≈ 2216 J/kg·K."""
        sg = 141.5 / (22.2 + 131.5)  # 0.9213
        T_F = 120.0 * 1.8 + 32.0     # 248°F
        expected_btu = 0.6811 - 0.308 * sg + (0.000815 - 0.000306 * sg) * T_F
        expected_si = expected_btu * 4186.8
        assert cp_petroleum(22.2, 120.0) == pytest.approx(expected_si, rel=1e-6)

    def test_density_at_reference(self):
        """At 15.56°C (60°F), density should equal SG × 999.012."""
        api = 33.0
        sg = _api_to_sg(api)
        rho = density_petroleum(api, 15.56)
        assert rho == pytest.approx(sg * 999.012, rel=0.001)

    def test_viscosity_decreases_with_temperature(self):
        """Viscosity must decrease as temperature increases (all crudes)."""
        api = 30.0
        mu_80 = viscosity_petroleum(api, 80.0)
        mu_120 = viscosity_petroleum(api, 120.0)
        assert mu_80 > mu_120

    def test_conductivity_reasonable(self):
        """Crude oil k ≈ 0.10–0.15 W/m·K in 50–200°C range."""
        k = conductivity_petroleum(33.0, 100.0)
        assert 0.08 <= k <= 0.18


class TestPetroleumCrudeSpecific:
    """Different crudes → different properties (the whole point)."""

    def test_maya_vs_arab_light_different_cp(self):
        """Maya (API 22.2) should have lower Cp than Arab Light (API 33.4)."""
        props_maya = get_fluid_properties("Maya crude oil", 120.0)
        props_arab = get_fluid_properties("Arab Light crude oil", 120.0)
        # Lighter crudes have higher Cp (Lee-Kesler: inverse relationship with SG)
        assert props_arab.cp_J_kgK > props_maya.cp_J_kgK

    def test_maya_vs_arab_light_different_density(self):
        """Maya (heavier) should be denser than Arab Light."""
        props_maya = get_fluid_properties("Maya crude", 100.0)
        props_arab = get_fluid_properties("Arab Light crude", 100.0)
        assert props_maya.density_kg_m3 > props_arab.density_kg_m3

    def test_maya_vs_arab_light_different_viscosity(self):
        """Maya (heavier) should be more viscous than Arab Light."""
        props_maya = get_fluid_properties("Maya crude", 100.0)
        props_arab = get_fluid_properties("Arab Light crude", 100.0)
        assert props_maya.viscosity_Pa_s > props_arab.viscosity_Pa_s


class TestPetroleumTemperatureDependence:
    """Same fluid at different temperatures → different properties."""

    def test_crude_oil_cp_temperature_dependent(self):
        """Cp increases with temperature for petroleum (Lee-Kesler)."""
        cp_60 = get_cp("crude oil", 60.0)
        cp_120 = get_cp("crude oil", 120.0)
        assert cp_120 > cp_60

    def test_crude_oil_density_decreases_with_temp(self):
        p60 = get_fluid_properties("crude oil", 60.0)
        p120 = get_fluid_properties("crude oil", 120.0)
        assert p60.density_kg_m3 > p120.density_kg_m3


class TestPetroleumNameResolution:
    """Name matching handles variations and qualifiers."""

    @pytest.mark.parametrize("name", [
        "Maya crude oil",
        "Maya crude",
        "maya",
        "MAYA",
        "  Maya  ",
    ])
    def test_crude_name_variations(self, name: str):
        result = resolve_petroleum_name(name.strip().lower())
        assert result is not None
        char, source = result
        assert char.api_gravity == pytest.approx(22.2)
        assert source == "petroleum-named"

    def test_ural_crude(self):
        props = get_fluid_properties("Ural crude oil", 100.0)
        assert props.cp_J_kgK is not None
        assert props.density_kg_m3 is not None

    def test_abu_bukhoosh_crude(self):
        props = get_fluid_properties("Abu Bukhoosh crude oil", 100.0)
        assert props.cp_J_kgK is not None

    def test_kerosene_as_petroleum_fraction(self):
        """Kerosene now uses Lee-Kesler (not hardcoded)."""
        cp_50 = get_cp("kerosene", 50.0)
        cp_150 = get_cp("kerosene", 150.0)
        assert cp_150 > cp_50  # T-dependent, not a frozen constant

    def test_unknown_petroleum_returns_none(self):
        assert resolve_petroleum_name("unobtanium") is None

    def test_generic_crude_oil_resolves(self):
        """Plain 'crude oil' resolves to generic medium (API ≈ 33)."""
        result = resolve_petroleum_name("crude oil")
        assert result is not None
        char, source = result
        assert 30 <= char.api_gravity <= 36
        assert source == "petroleum-generic"


# ═══════════════════════════════════════════════════════════════════════════════
# Tier 5 — Specialty fluids
# ═══════════════════════════════════════════════════════════════════════════════

class TestSpecialtyFluids:
    def test_thermal_oil_temperature_dependent(self):
        """Thermal oil at 100°C vs 250°C — Cp should change."""
        p100 = get_fluid_properties("thermal oil", 100.0)
        p250 = get_fluid_properties("thermal oil", 250.0)
        assert p250.cp_J_kgK > p100.cp_J_kgK  # Cp increases with T

    def test_ethylene_glycol_all_fields(self):
        props = get_fluid_properties("ethylene glycol", 60.0)
        assert props.density_kg_m3 is not None
        assert props.viscosity_Pa_s is not None
        assert props.cp_J_kgK is not None
        assert props.k_W_mK is not None
        assert props.Pr is not None

    def test_molten_salt_at_350C(self):
        props = get_fluid_properties("molten salt", 350.0)
        assert 1500 <= props.cp_J_kgK <= 1600
        assert props.density_kg_m3 > 1700


# ═══════════════════════════════════════════════════════════════════════════════
# Failure modes
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnknownFluid:
    def test_unknown_fluid_raises(self):
        with pytest.raises(CalculationError, match="Unknown fluid"):
            get_fluid_properties("unobtanium", 50.0)


class TestAllFieldsPopulated:
    @pytest.mark.parametrize(
        "fluid,temp",
        [
            ("water", 50.0),
            ("crude oil", 100.0),
            ("ethanol", 25.0),
            ("Maya crude", 100.0),
            ("kerosene", 80.0),
            ("thermal oil", 150.0),
            ("acetic acid", 25.0),
        ],
    )
    def test_all_fields_populated(self, fluid: str, temp: float):
        props = get_fluid_properties(fluid, temp)
        assert props.density_kg_m3 is not None
        assert props.viscosity_Pa_s is not None
        assert props.cp_J_kgK is not None
        assert props.k_W_mK is not None
        assert props.Pr is not None
