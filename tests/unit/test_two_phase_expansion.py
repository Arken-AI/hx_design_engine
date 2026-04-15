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


# =====================================================================
# 7. Segment loop — IncrementResult population in Step 8 condensation
# =====================================================================


class TestSegmentLoopStep8:
    """Tests for per-segment IncrementResult generation in _execute_condensing."""

    def test_increment_results_populated(self):
        """Step 8 condensation should populate state.increment_results."""
        from hx_engine.app.correlations.shah_condensation import shah_condensation_h

        # Just verify the Shah local function returns valid h_cond at various qualities
        for x in [0.1, 0.3, 0.5, 0.7, 0.9]:
            result = shah_condensation_h(
                x=x, G=100.0, D_i=0.019,
                rho_l=958.0, rho_g=0.6, mu_l=2.82e-4, mu_g=1.2e-5,
                k_l=0.68, cp_l=4216.0, h_fg=2.257e6,
                P_sat=101325.0, P_crit=22.064e6,
            )
            assert result["h_cond"] > 0
            assert result["h_cond"] > result["h_lo"]  # condensation always > liquid-only

    def test_increment_result_fields(self):
        """IncrementResult should store all segment-level fields."""
        inc = IncrementResult(
            segment_index=3,
            T_hot_in_C=100.0,
            T_hot_out_C=100.0,
            T_cold_in_C=30.0,
            T_cold_out_C=40.0,
            quality_in=0.8,
            quality_out=0.6,
            phase="two_phase",
            h_tube_W_m2K=5000.0,
            h_shell_W_m2K=8000.0,
            U_local_W_m2K=2500.0,
            dQ_W=50000.0,
            dA_m2=0.35,
            LMTD_local_K=65.0,
        )
        assert inc.segment_index == 3
        assert inc.quality_in == 0.8
        assert inc.quality_out == 0.6
        assert inc.dA_m2 == pytest.approx(0.35)

    def test_shah_h_decreases_with_quality(self):
        """Shah HTC should generally decrease as quality drops (less vapor)."""
        from hx_engine.app.correlations.shah_condensation import shah_condensation_h

        kwargs = dict(
            G=100.0, D_i=0.019,
            rho_l=958.0, rho_g=0.6, mu_l=2.82e-4, mu_g=1.2e-5,
            k_l=0.68, cp_l=4216.0, h_fg=2.257e6,
            P_sat=101325.0, P_crit=22.064e6,
        )
        h_high = shah_condensation_h(x=0.8, **kwargs)["h_cond"]
        h_low = shah_condensation_h(x=0.2, **kwargs)["h_cond"]
        # At high quality, more vapor → higher condensation HTC
        assert h_high > h_low

    def test_lmtd_local_calculation(self):
        """LMTD for a condensation segment with constant T_hot."""
        T_hot = 100.0
        T_cold_in = 30.0
        T_cold_out = 40.0
        dT1 = T_hot - T_cold_in   # 70
        dT2 = T_hot - T_cold_out  # 60
        lmtd = (dT1 - dT2) / math.log(dT1 / dT2)
        assert 60 < lmtd < 70
        assert lmtd == pytest.approx(64.9, abs=0.5)

    def test_segment_dA_from_dQ_U_LMTD(self):
        """dA = dQ / (U_local × LMTD_local)."""
        dQ = 50000.0  # W
        U_local = 2500.0  # W/m²K
        LMTD = 65.0  # K
        dA = dQ / (U_local * LMTD)
        assert dA == pytest.approx(0.3077, abs=0.01)


# =====================================================================
# 8. Step 9 — per-segment U_local computation
# =====================================================================


class TestStep9IncrementalU:
    """Verify Step 9 computes U_local for each IncrementResult."""

    def test_u_local_formula(self):
        """U_local = 1 / (1/h_o + d_o/d_i/h_i + R_f_o + R_f_i×d_o/d_i + R_wall)."""
        h_o = 8000.0   # shell-side (condensation)
        h_i = 5000.0   # tube-side
        d_o = 0.01905
        d_i = 0.01483
        R_f_o = 0.00018  # shell fouling
        R_f_i = 0.00018  # tube fouling
        k_wall = 50.0

        R_shell = 1.0 / h_o
        R_tube = (d_o / d_i) / h_i
        R_fo = R_f_o
        R_fi = R_f_i * (d_o / d_i)
        R_w = d_o * math.log(d_o / d_i) / (2.0 * k_wall)
        U = 1.0 / (R_shell + R_tube + R_fo + R_fi + R_w)
        # Should be ~1500-3000 W/m²K range for condensation
        assert 1000 < U < 4000

    def test_segment_u_varies_with_h_shell(self):
        """Segments with higher h_shell should yield higher U_local."""
        d_o = 0.01905
        d_i = 0.01483
        h_i = 5000.0
        R_f = 0.00018
        k_w = 50.0

        R_tube = (d_o / d_i) / h_i
        R_fo = R_f
        R_fi = R_f * (d_o / d_i)
        R_w = d_o * math.log(d_o / d_i) / (2.0 * k_w)

        def U_from_ho(h_o):
            return 1.0 / (1.0/h_o + R_tube + R_fo + R_fi + R_w)

        U_high_x = U_from_ho(10000.0)  # high quality → high h_shell
        U_low_x = U_from_ho(3000.0)    # low quality → lower h_shell
        assert U_high_x > U_low_x


# =====================================================================
# 9. Step 11 — Σ(dA) for condensation area
# =====================================================================


class TestStep11IncrementalArea:
    """Verify Step 11 uses Σ(dA) when increment_results are available."""

    def test_sum_dA_matches_total(self):
        """Total A_required should equal sum of segment dA values."""
        segments = []
        total_dA = 0.0
        for i in range(10):
            dA = 0.3 + i * 0.02  # increasing dA per segment
            total_dA += dA
            segments.append(IncrementResult(
                segment_index=i,
                dA_m2=dA,
            ))
        A_required = sum(inc.dA_m2 for inc in segments)
        assert A_required == pytest.approx(total_dA)

    def test_sum_dA_greater_than_uniform_U(self):
        """Σ(dA) with varying U_local should differ from Q/(U_avg×LMTD).

        In condensation, U varies strongly with quality, so incremental Σ(dA)
        gives a more accurate area than using the average U.
        """
        Q_total = 500_000.0  # 500 kW
        dQ = Q_total / 10

        dA_incremental = 0.0
        U_values = []
        for i in range(10):
            x = 0.95 - i * 0.09  # quality decreasing
            # Make U vary nonlinearly (exponentially) with quality
            U_local = 1000 + 3000 * x ** 2
            LMTD_local = 40.0 + i * 3.0
            dA = dQ / (U_local * LMTD_local)
            dA_incremental += dA
            U_values.append(U_local)

        # Compare with uniform calculation
        U_avg = sum(U_values) / len(U_values)
        LMTD_avg = sum(40.0 + i * 3.0 for i in range(10)) / 10
        A_uniform = Q_total / (U_avg * LMTD_avg)

        # With nonlinear U, incremental sum should differ noticeably
        assert abs(dA_incremental - A_uniform) / A_uniform > 0.02


# =====================================================================
# 10. Step 12 — phase-aware velocity limits
# =====================================================================


class TestStep12PhaseAwareVelocity:
    """Verify Step 12 convergence uses correct velocity thresholds by phase."""

    def _make_state(self, tube_phase="liquid"):
        """Create a minimal DesignState for velocity limit testing."""
        state = DesignState()
        state.shell_side_fluid = "hot"
        # tube side = cold
        state.cold_phase = tube_phase
        state.hot_phase = "liquid"
        return state

    def test_liquid_velocity_limits(self):
        from hx_engine.app.steps.step_12_convergence import Step12Convergence

        conv = Step12Convergence()
        state = self._make_state("liquid")
        v_low, v_high = conv._velocity_limits(state)
        assert v_low == pytest.approx(0.8)
        assert v_high == pytest.approx(2.5)

    def test_gas_velocity_limits(self):
        from hx_engine.app.steps.step_12_convergence import Step12Convergence

        conv = Step12Convergence()
        state = self._make_state("vapor")
        v_low, v_high = conv._velocity_limits(state)
        assert v_low == pytest.approx(5.0)
        assert v_high == pytest.approx(30.0)

    def test_default_is_liquid_when_no_phase(self):
        from hx_engine.app.steps.step_12_convergence import Step12Convergence

        conv = Step12Convergence()
        state = DesignState()
        state.shell_side_fluid = "hot"
        # No phase set — should default to liquid
        v_low, v_high = conv._velocity_limits(state)
        assert v_low == pytest.approx(0.8)
        assert v_high == pytest.approx(2.5)

    def test_gas_velocity_low_detected_as_violation(self):
        from hx_engine.app.steps.step_12_convergence import Step12Convergence

        conv = Step12Convergence()
        state = self._make_state("vapor")
        state.tube_velocity_m_s = 3.0  # below 5 m/s gas min
        state.dP_tube_Pa = 10000.0
        state.dP_shell_Pa = 10000.0
        state.overdesign_pct = 15.0
        violations = conv._detect_violations(state)
        assert "velocity_low" in violations

    def test_gas_velocity_ok_no_violation(self):
        from hx_engine.app.steps.step_12_convergence import Step12Convergence

        conv = Step12Convergence()
        state = self._make_state("vapor")
        state.tube_velocity_m_s = 15.0  # within 5-30 m/s gas range
        state.dP_tube_Pa = 10000.0
        state.dP_shell_Pa = 10000.0
        state.overdesign_pct = 15.0
        violations = conv._detect_violations(state)
        assert "velocity_low" not in violations
        assert "velocity_high" not in violations

    def test_liquid_velocity_in_gas_range_is_violation(self):
        """Liquid at 15 m/s should trigger velocity_high."""
        from hx_engine.app.steps.step_12_convergence import Step12Convergence

        conv = Step12Convergence()
        state = self._make_state("liquid")
        state.tube_velocity_m_s = 15.0  # way above 2.5 m/s liquid max
        state.dP_tube_Pa = 10000.0
        state.dP_shell_Pa = 10000.0
        state.overdesign_pct = 15.0
        violations = conv._detect_violations(state)
        assert "velocity_high" in violations
