"""Tests for two-phase / gas-phase expansion.

Covers:
  1. FluidProperties — gas-phase values, phase/quality fields
  2. IncrementResult model
  3. DesignState — new phase fields
  4. Shah condensation correlation
  5. Phase detection in Step 3
  6. thermo_adapter saturation helpers
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    IncrementResult,
)


# =====================================================================
# 1. FluidProperties with gas-phase values
# =====================================================================

class TestFluidPropertiesGasPhase:

    def test_gas_phase_density_accepted(self):
        """Gas density ~1-5 kg/m³ should pass validation."""
        fp = FluidProperties(density_kg_m3=1.2)
        assert fp.density_kg_m3 == pytest.approx(1.2)

    def test_gas_viscosity_accepted(self):
        """Gas viscosity ~1e-5 Pa·s should pass validation."""
        fp = FluidProperties(viscosity_Pa_s=1.8e-5)
        assert fp.viscosity_Pa_s == pytest.approx(1.8e-5)

    def test_gas_conductivity_accepted(self):
        """Gas thermal conductivity ~0.02 W/m·K should pass."""
        fp = FluidProperties(k_W_mK=0.026)
        assert fp.k_W_mK == pytest.approx(0.026)

    def test_gas_prandtl_accepted(self):
        """Gas Pr ~0.7 should pass."""
        fp = FluidProperties(Pr=0.71)
        assert fp.Pr == pytest.approx(0.71)

    def test_gas_cp_accepted(self):
        """Gas cp ~1000 J/kg·K should pass."""
        fp = FluidProperties(cp_J_kgK=1005.0)
        assert fp.cp_J_kgK == pytest.approx(1005.0)

    def test_very_low_density_rejected(self):
        """Density below 0.01 kg/m³ is unreasonable."""
        with pytest.raises(ValidationError, match="density_kg_m3"):
            FluidProperties(density_kg_m3=0.001)

    def test_very_low_viscosity_rejected(self):
        """Viscosity below 1e-7 Pa·s is unreasonable."""
        with pytest.raises(ValidationError, match="viscosity_Pa_s"):
            FluidProperties(viscosity_Pa_s=1e-9)

    def test_phase_field(self):
        fp = FluidProperties(phase="vapor")
        assert fp.phase == "vapor"

    def test_phase_none_default(self):
        fp = FluidProperties()
        assert fp.phase is None

    def test_quality_field(self):
        fp = FluidProperties(quality=0.5)
        assert fp.quality == pytest.approx(0.5)

    def test_quality_out_of_range_rejected(self):
        with pytest.raises(ValidationError, match="quality"):
            FluidProperties(quality=1.5)

    def test_quality_negative_rejected(self):
        with pytest.raises(ValidationError, match="quality"):
            FluidProperties(quality=-0.1)

    def test_quality_boundaries(self):
        fp0 = FluidProperties(quality=0.0)
        fp1 = FluidProperties(quality=1.0)
        assert fp0.quality == 0.0
        assert fp1.quality == 1.0

    def test_enthalpy_field(self):
        fp = FluidProperties(enthalpy_J_kg=2_500_000.0)
        assert fp.enthalpy_J_kg == pytest.approx(2_500_000.0)

    def test_latent_heat_field(self):
        fp = FluidProperties(latent_heat_J_kg=2_257_000.0)
        assert fp.latent_heat_J_kg == pytest.approx(2_257_000.0)

    def test_T_sat_field(self):
        fp = FluidProperties(T_sat_C=100.0)
        assert fp.T_sat_C == pytest.approx(100.0)

    def test_P_sat_field(self):
        fp = FluidProperties(P_sat_Pa=101325.0)
        assert fp.P_sat_Pa == pytest.approx(101325.0)

    def test_full_gas_properties(self):
        """Complete gas-phase property set for air-like fluid."""
        fp = FluidProperties(
            density_kg_m3=1.2,
            viscosity_Pa_s=1.8e-5,
            cp_J_kgK=1005.0,
            k_W_mK=0.026,
            Pr=0.71,
            phase="vapor",
        )
        assert fp.phase == "vapor"
        assert fp.density_kg_m3 == pytest.approx(1.2)

    def test_full_two_phase_properties(self):
        """Complete two-phase property set (condensing steam)."""
        fp = FluidProperties(
            density_kg_m3=900.0,
            viscosity_Pa_s=0.0003,
            cp_J_kgK=4200.0,
            k_W_mK=0.65,
            Pr=2.0,
            phase="two_phase",
            quality=0.5,
            enthalpy_J_kg=2_000_000.0,
            latent_heat_J_kg=2_257_000.0,
            T_sat_C=100.0,
            P_sat_Pa=101325.0,
        )
        assert fp.phase == "two_phase"
        assert fp.quality == pytest.approx(0.5)


# =====================================================================
# 2. IncrementResult model
# =====================================================================

class TestIncrementResult:

    def test_basic_increment(self):
        ir = IncrementResult(
            segment_index=0,
            quality_in=1.0,
            quality_out=0.9,
            T_hot_in_C=100.0,
            T_cold_in_C=30.0,
            h_tube_W_m2K=5000.0,
            h_shell_W_m2K=8000.0,
            U_local_W_m2K=2500.0,
            dQ_W=50000.0,
            LMTD_local_K=50.0,
            dA_m2=0.4,
        )
        assert ir.segment_index == 0
        assert ir.quality_in == pytest.approx(1.0)
        assert ir.dA_m2 == pytest.approx(0.4)

    def test_optional_fields_default_none(self):
        ir = IncrementResult(
            segment_index=0,
        )
        # Optional fields should default to None
        assert ir.quality_in is None
        assert ir.quality_out is None
        assert ir.h_tube_W_m2K is None
        assert ir.phase is None


# =====================================================================
# 3. DesignState — new phase fields
# =====================================================================

class TestDesignStatePhaseFields:

    def test_hot_phase_default_none(self):
        s = DesignState()
        assert s.hot_phase is None

    def test_cold_phase_default_none(self):
        s = DesignState()
        assert s.cold_phase is None

    def test_n_increments_default_none(self):
        s = DesignState()
        assert s.n_increments is None

    def test_set_hot_phase(self):
        s = DesignState(hot_phase="condensing")
        assert s.hot_phase == "condensing"

    def test_set_cold_phase(self):
        s = DesignState(cold_phase="vapor")
        assert s.cold_phase == "vapor"

    def test_increment_results_default_empty(self):
        s = DesignState()
        assert s.increment_results == []

    def test_add_increment_results(self):
        s = DesignState()
        ir = IncrementResult(
            segment_index=0,
            quality_in=1.0,
            quality_out=0.8,
            T_hot_in_C=100.0,
            T_cold_in_C=30.0,
            h_tube_W_m2K=5000.0,
            h_shell_W_m2K=8000.0,
            U_local_W_m2K=2500.0,
            dQ_W=50000.0,
            LMTD_local_K=50.0,
            dA_m2=0.4,
        )
        s.increment_results.append(ir)
        assert len(s.increment_results) == 1


# =====================================================================
# 4. Shah condensation correlation
# =====================================================================

class TestShahCondensation:

    def test_shah_h_basic(self):
        """Shah condensation at mid-quality for water at 1 atm."""
        from hx_engine.app.correlations.shah_condensation import shah_condensation_h

        result = shah_condensation_h(
            x=0.5,
            G=200.0,         # kg/m²·s
            D_i=0.019,       # m
            rho_l=958.0,     # kg/m³
            rho_g=0.6,       # kg/m³
            mu_l=0.000282,   # Pa·s
            mu_g=1.2e-5,     # Pa·s
            k_l=0.679,       # W/m·K
            cp_l=4216.0,     # J/kg·K
            h_fg=2_257_000,  # J/kg
            P_sat=101325.0,  # Pa
            P_crit=22.064e6, # Pa
        )
        h = result["h_cond"]
        # Shah condensation HTC for water should be in reasonable range
        # typical: 2000-15000 W/m²K
        assert 500 < h < 50000, f"h={h} outside expected range"
        assert result["Re_lo"] > 0
        assert result["Pr_l"] > 0

    def test_shah_h_at_quality_zero(self):
        """At x=0 (all liquid), HTC should still be positive."""
        from hx_engine.app.correlations.shah_condensation import shah_condensation_h

        result = shah_condensation_h(
            x=0.01,  # near zero
            G=200.0,
            D_i=0.019,
            rho_l=958.0,
            rho_g=0.6,
            mu_l=0.000282,
            mu_g=1.2e-5,
            k_l=0.679,
            cp_l=4216.0,
            h_fg=2_257_000,
            P_sat=101325.0,
            P_crit=22.064e6,
        )
        assert result["h_cond"] > 0

    def test_shah_h_at_quality_one(self):
        """At x≈1 (all vapor), HTC should still be positive."""
        from hx_engine.app.correlations.shah_condensation import shah_condensation_h

        result = shah_condensation_h(
            x=0.99,
            G=200.0,
            D_i=0.019,
            rho_l=958.0,
            rho_g=0.6,
            mu_l=0.000282,
            mu_g=1.2e-5,
            k_l=0.679,
            cp_l=4216.0,
            h_fg=2_257_000,
            P_sat=101325.0,
            P_crit=22.064e6,
        )
        assert result["h_cond"] > 0

    def test_shah_h_increases_with_quality(self):
        """Higher quality should generally give higher HTC for condensation."""
        from hx_engine.app.correlations.shah_condensation import shah_condensation_h

        kwargs = dict(
            G=200.0,
            D_i=0.019,
            rho_l=958.0,
            rho_g=0.6,
            mu_l=0.000282,
            mu_g=1.2e-5,
            k_l=0.679,
            cp_l=4216.0,
            h_fg=2_257_000,
            P_sat=101325.0,
            P_crit=22.064e6,
        )
        h_low = shah_condensation_h(x=0.2, **kwargs)["h_cond"]
        h_high = shah_condensation_h(x=0.8, **kwargs)["h_cond"]
        assert h_high > h_low, "HTC should increase with quality for condensation"

    def test_shah_average_h(self):
        """Average HTC over x=1→0 should be in reasonable range."""
        from hx_engine.app.correlations.shah_condensation import (
            shah_condensation_average_h,
        )

        result = shah_condensation_average_h(
            G=200.0,
            D_i=0.019,
            rho_l=958.0,
            rho_g=0.6,
            mu_l=0.000282,
            mu_g=1.2e-5,
            k_l=0.679,
            cp_l=4216.0,
            h_fg=2_257_000,
            P_sat=101325.0,
            P_crit=22.064e6,
            x_in=1.0,
            x_out=0.0,
        )
        h_avg = result["h_avg"]
        assert 500 < h_avg < 50000, f"h_avg={h_avg} outside expected range"
        assert len(result["warnings"]) == 0 or isinstance(result["warnings"], list)

    def test_shah_average_partial_condensation(self):
        """Average HTC for partial condensation x=1→0.5."""
        from hx_engine.app.correlations.shah_condensation import (
            shah_condensation_average_h,
        )

        result = shah_condensation_average_h(
            G=200.0,
            D_i=0.019,
            rho_l=958.0,
            rho_g=0.6,
            mu_l=0.000282,
            mu_g=1.2e-5,
            k_l=0.679,
            cp_l=4216.0,
            h_fg=2_257_000,
            P_sat=101325.0,
            P_crit=22.064e6,
            x_in=1.0,
            x_out=0.5,
        )
        h_avg = result["h_avg"]
        assert h_avg > 0

    def test_get_critical_pressure_water(self):
        from hx_engine.app.correlations.shah_condensation import get_critical_pressure

        p = get_critical_pressure("water")
        assert p is not None
        assert abs(p - 22.064e6) < 1e4  # within 10 kPa of known value

    def test_get_critical_pressure_steam(self):
        from hx_engine.app.correlations.shah_condensation import get_critical_pressure

        p = get_critical_pressure("steam")
        assert p is not None
        assert abs(p - 22.064e6) < 1e4

    def test_get_critical_pressure_unknown(self):
        from hx_engine.app.correlations.shah_condensation import get_critical_pressure

        p = get_critical_pressure("unknown_fluid_xyz")
        assert p is None


# =====================================================================
# 5. Phase detection logic (Step 3)
# =====================================================================

class TestPhaseDetection:

    def _make_props(self, T_sat_C=None, phase=None, density=998.0):
        """Helper to create FluidProperties with T_sat set."""
        return FluidProperties(
            density_kg_m3=density,
            viscosity_Pa_s=0.001,
            cp_J_kgK=4181.0,
            k_W_mK=0.6,
            Pr=7.0,
            T_sat_C=T_sat_C,
            phase=phase,
        )

    def test_detect_liquid_phase(self):
        """Both temps well below saturation → liquid."""
        from hx_engine.app.steps.step_03_fluid_props import (
            _detect_single_stream_phase,
        )

        props = self._make_props(T_sat_C=100.0)
        phase = _detect_single_stream_phase(
            props=props, T_in=80.0, T_out=50.0,
            P_Pa=101325.0, fluid_name="water", is_hot_side=True,
        )
        assert phase == "liquid"

    def test_detect_vapor_phase(self):
        """Both temps well above saturation → vapor."""
        from hx_engine.app.steps.step_03_fluid_props import (
            _detect_single_stream_phase,
        )

        props = self._make_props(T_sat_C=100.0, density=1.2)
        phase = _detect_single_stream_phase(
            props=props, T_in=150.0, T_out=120.0,
            P_Pa=101325.0, fluid_name="water", is_hot_side=True,
        )
        assert phase == "vapor"

    def test_detect_condensing(self):
        """Inlet above T_sat, outlet below → condensing (hot side)."""
        from hx_engine.app.steps.step_03_fluid_props import (
            _detect_single_stream_phase,
        )

        props = self._make_props(T_sat_C=100.0)
        phase = _detect_single_stream_phase(
            props=props, T_in=120.0, T_out=80.0,
            P_Pa=101325.0, fluid_name="water", is_hot_side=True,
        )
        assert phase == "condensing"

    def test_detect_evaporating(self):
        """Inlet below T_sat, outlet above → evaporating (cold side)."""
        from hx_engine.app.steps.step_03_fluid_props import (
            _detect_single_stream_phase,
        )

        props = self._make_props(T_sat_C=100.0)
        phase = _detect_single_stream_phase(
            props=props, T_in=80.0, T_out=120.0,
            P_Pa=101325.0, fluid_name="water", is_hot_side=False,
        )
        assert phase == "evaporating"

    def test_no_saturation_data_defaults_liquid(self):
        """When T_sat is None, default to liquid (high density)."""
        from hx_engine.app.steps.step_03_fluid_props import (
            _detect_single_stream_phase,
        )

        props = self._make_props(T_sat_C=None, density=998.0)
        phase = _detect_single_stream_phase(
            props=props, T_in=80.0, T_out=50.0,
            P_Pa=101325.0, fluid_name="water", is_hot_side=True,
        )
        assert phase == "liquid"

    def test_temps_near_saturation(self):
        """Temps very close to T_sat (within tolerance)."""
        from hx_engine.app.steps.step_03_fluid_props import (
            _detect_single_stream_phase,
        )

        props = self._make_props(T_sat_C=100.0)
        phase = _detect_single_stream_phase(
            props=props, T_in=100.0, T_out=100.0,
            P_Pa=101325.0, fluid_name="water", is_hot_side=True,
        )
        # Within 1°C tolerance, falls through to density/phase fallbacks
        assert phase in ("liquid", "vapor", "condensing", "evaporating")


# =====================================================================
# 6. thermo_adapter saturation helpers
# =====================================================================


def _has_iapws() -> bool:
    try:
        import iapws  # noqa: F401
        return True
    except ImportError:
        return False


def _has_coolprop() -> bool:
    try:
        import CoolProp  # noqa: F401
        return True
    except ImportError:
        return False


class TestThermoAdapterSaturation:

    @pytest.mark.skipif(
        not _has_iapws(),
        reason="IAPWS not installed",
    )
    def test_saturation_props_water_1atm(self):
        """Get saturation properties for water at 1 atm."""
        from hx_engine.app.adapters.thermo_adapter import get_saturation_props

        result = get_saturation_props("water", 101325.0)
        assert abs(result["T_sat_C"] - 100.0) < 1.0
        assert result["h_fg"] > 2_000_000  # latent heat > 2 MJ/kg
        assert result["rho_f"] > 900  # liquid density
        assert result["rho_g"] < 1.0  # vapor density at 1 atm
        assert result["mu_f"] > 0
        assert result["k_f"] > 0
        assert result["cp_f"] > 0

    @pytest.mark.skipif(
        not _has_iapws(),
        reason="IAPWS not installed",
    )
    def test_saturation_props_water_10bar(self):
        """Get saturation properties for water at 10 bar."""
        from hx_engine.app.adapters.thermo_adapter import get_saturation_props

        result = get_saturation_props("water", 10e5)
        assert abs(result["T_sat_C"] - 179.9) < 2.0  # ~180°C at 10 bar
        assert result["h_fg"] > 1_500_000

    @pytest.mark.skipif(
        not _has_iapws(),
        reason="IAPWS not installed",
    )
    def test_two_phase_props_water(self):
        """Get two-phase properties at mid-quality."""
        from hx_engine.app.adapters.thermo_adapter import get_two_phase_props

        result = get_two_phase_props("water", 0.5, 101325.0)
        # Mixture density should be between liquid and vapor
        assert result.density_kg_m3 is not None
        assert result.density_kg_m3 < 958  # less than liquid
        assert result.density_kg_m3 > 0.6  # more than vapor
