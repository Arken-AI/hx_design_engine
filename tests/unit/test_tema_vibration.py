"""Tests for TEMA Section 6 vibration correlations (tema_vibration.py).

Covers:
  - Unit conversions
  - Tube properties (moment of inertia, effective weight, C_m)
  - Natural frequency (V-5.3) + damping (V-8)
  - Crossflow velocity (V-9)
  - Fluidelastic instability (V-10)
  - Vortex shedding (V-11.2)
  - Turbulent buffeting (V-11.3)
  - Acoustic resonance (V-12)
  - Full check_all_spans orchestrator
"""

from __future__ import annotations

import math
import pytest

from hx_engine.app.correlations.tema_vibration import (
    _m_to_in,
    _in_to_m,
    _m_to_ft,
    _kg_m3_to_lb_ft3,
    _Pa_to_psi,
    _kg_s_to_lb_hr,
    _ft_s_to_m_s,
    _lb_ft_to_kg_m,
    _kg_m_to_lb_ft,
    compute_moment_of_inertia,
    _interpolate_Cm,
    compute_effective_tube_weight,
    compute_natural_frequency,
    compute_damping_liquid,
    compute_damping_vapor,
    compute_fluid_elastic_parameter,
    compute_crossflow_velocity,
    _compute_D_factor,
    check_fluidelastic,
    _interpolate_strouhal,
    _interpolate_CL,
    check_vortex_shedding,
    _get_force_coefficient,
    check_turbulent_buffeting,
    check_acoustic_resonance,
    _compute_longitudinal_pitch_ratio,
    check_all_spans,
    _EDGE_CONDITION_C,
    _CM_TABLE,
)


# ═══════════════════════════════════════════════════════════════════════════
# Unit conversions
# ═══════════════════════════════════════════════════════════════════════════

class TestUnitConversions:
    def test_m_to_in_roundtrip(self):
        assert _in_to_m(_m_to_in(1.0)) == pytest.approx(1.0, rel=1e-6)

    def test_m_to_in_known(self):
        assert _m_to_in(0.0254) == pytest.approx(1.0, rel=1e-4)

    def test_m_to_ft(self):
        assert _m_to_ft(0.3048) == pytest.approx(1.0, rel=1e-4)

    def test_kg_m3_to_lb_ft3(self):
        assert _kg_m3_to_lb_ft3(1000.0) == pytest.approx(62.428, rel=1e-3)

    def test_Pa_to_psi(self):
        assert _Pa_to_psi(6894.76) == pytest.approx(1.0, rel=1e-3)

    def test_kg_s_to_lb_hr(self):
        assert _kg_s_to_lb_hr(1.0) == pytest.approx(7936.64, rel=1e-3)

    def test_ft_s_to_m_s(self):
        assert _ft_s_to_m_s(1.0) == pytest.approx(0.3048, rel=1e-4)

    def test_lb_ft_kg_m_roundtrip(self):
        val = 2.5
        assert _kg_m_to_lb_ft(_lb_ft_to_kg_m(val)) == pytest.approx(val, rel=1e-6)


# ═══════════════════════════════════════════════════════════════════════════
# Tube properties
# ═══════════════════════════════════════════════════════════════════════════

class TestMomentOfInertia:
    def test_positive(self):
        I = compute_moment_of_inertia(d_o_m=0.01905, d_i_m=0.01483)
        assert I > 0

    def test_known_value(self):
        """3/4" 16BWG tube: OD=0.75in, ID≈0.620in."""
        d_o = 0.75 / 39.3701
        d_i = 0.620 / 39.3701
        I = compute_moment_of_inertia(d_o, d_i)
        I_expected = math.pi / 64.0 * (0.75**4 - 0.620**4)
        assert I == pytest.approx(I_expected, rel=1e-4)

    def test_zero_wall(self):
        """Same OD and ID gives zero."""
        assert compute_moment_of_inertia(0.01905, 0.01905) == pytest.approx(0.0, abs=1e-12)


class TestCmInterpolation:
    def test_exact_table_point_square(self):
        assert _interpolate_Cm(1.25, 90) == pytest.approx(1.58, rel=1e-6)

    def test_exact_table_point_triangular(self):
        assert _interpolate_Cm(1.25, 30) == pytest.approx(1.48, rel=1e-6)

    def test_interpolation_between_points(self):
        # Between 1.25 (sq=1.58) and 1.30 (sq=1.48) → at 1.275 → ~1.53
        Cm = _interpolate_Cm(1.275, 90)
        assert 1.48 < Cm < 1.58

    def test_clamp_low(self):
        assert _interpolate_Cm(0.5, 90) == pytest.approx(_CM_TABLE[0][1])

    def test_clamp_high(self):
        assert _interpolate_Cm(5.0, 30) == pytest.approx(_CM_TABLE[-1][2])


class TestEffectiveTubeWeight:
    @pytest.fixture
    def typical_params(self):
        return dict(
            d_o_m=0.01905,          # 3/4" OD
            d_i_m=0.01483,          # 16BWG ID
            rho_metal_kg_m3=7850.0, # carbon steel
            rho_tube_fluid_kg_m3=998.0,
            rho_shell_fluid_kg_m3=998.0,
            pitch_ratio=1.25,
            pitch_angle_deg=30,
        )

    def test_keys(self, typical_params):
        result = compute_effective_tube_weight(**typical_params)
        assert set(result.keys()) == {"w_t", "w_fi", "C_m", "H_m", "w_0"}

    def test_positive_values(self, typical_params):
        result = compute_effective_tube_weight(**typical_params)
        for key in result:
            assert result[key] > 0, f"{key} should be positive"

    def test_w0_equals_sum(self, typical_params):
        r = compute_effective_tube_weight(**typical_params)
        assert r["w_0"] == pytest.approx(r["w_t"] + r["w_fi"] + r["H_m"], rel=1e-6)


# ═══════════════════════════════════════════════════════════════════════════
# Natural frequency & damping
# ═══════════════════════════════════════════════════════════════════════════

class TestNaturalFrequency:
    def test_simply_simply_positive(self):
        f = compute_natural_frequency(
            span_m=0.3,
            E_Pa=200e9,
            I_in4=0.003,
            w_0_lb_ft=0.6,
        )
        assert f > 0

    def test_fixed_simply_higher_than_ss(self):
        common = dict(span_m=0.3, E_Pa=200e9, I_in4=0.003, w_0_lb_ft=0.6)
        f_ss = compute_natural_frequency(**common, edge_condition="simply-simply")
        f_fs = compute_natural_frequency(**common, edge_condition="fixed-simply")
        assert f_fs > f_ss

    def test_fixed_fixed_highest(self):
        common = dict(span_m=0.3, E_Pa=200e9, I_in4=0.003, w_0_lb_ft=0.6)
        f_fs = compute_natural_frequency(**common, edge_condition="fixed-simply")
        f_ff = compute_natural_frequency(**common, edge_condition="fixed-fixed")
        assert f_ff > f_fs

    def test_shorter_span_higher_freq(self):
        common = dict(E_Pa=200e9, I_in4=0.003, w_0_lb_ft=0.6)
        f_long = compute_natural_frequency(span_m=0.5, **common)
        f_short = compute_natural_frequency(span_m=0.3, **common)
        assert f_short > f_long

    def test_edge_condition_keys(self):
        for key in _EDGE_CONDITION_C:
            f = compute_natural_frequency(0.3, 200e9, 0.003, 0.6, key)
            assert f > 0


class TestDampingLiquid:
    def test_keys(self):
        r = compute_damping_liquid(0.01905, 0.6, 50.0, 998.0, 0.001)
        assert set(r.keys()) == {"delta_1", "delta_2", "delta_T"}

    def test_delta_T_is_max(self):
        r = compute_damping_liquid(0.01905, 0.6, 50.0, 998.0, 0.001)
        assert r["delta_T"] == max(r["delta_1"], r["delta_2"])

    def test_positive(self):
        r = compute_damping_liquid(0.01905, 0.6, 50.0, 998.0, 0.001)
        assert r["delta_T"] > 0


class TestDampingVapor:
    def test_positive(self):
        dv = compute_damping_vapor(n_spans=6, baffle_thickness_m=0.00635, span_m=0.3)
        assert dv > 0

    def test_more_spans_higher_damping(self):
        dv5 = compute_damping_vapor(5, 0.00635, 0.3)
        dv10 = compute_damping_vapor(10, 0.00635, 0.3)
        assert dv10 > dv5


class TestFluidElasticParameter:
    def test_positive(self):
        X = compute_fluid_elastic_parameter(0.6, 0.05, 998.0, 0.01905)
        assert X > 0


# ═══════════════════════════════════════════════════════════════════════════
# Crossflow velocity
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossflowVelocity:
    @pytest.fixture
    def typical_params(self):
        return dict(
            shell_id_m=0.489,
            otl_m=0.467,
            tube_od_m=0.01905,
            tube_pitch_m=0.02381,
            baffle_spacing_m=0.20,
            baffle_cut=0.25,
            pitch_angle_deg=30,
            shell_flow_kg_s=10.0,
            rho_shell_kg_m3=998.0,
        )

    def test_positive_velocity(self, typical_params):
        r = compute_crossflow_velocity(**typical_params)
        assert r["V_ft_s"] > 0
        assert r["V_m_s"] > 0

    def test_keys(self, typical_params):
        r = compute_crossflow_velocity(**typical_params)
        assert "V_ft_s" in r and "V_m_s" in r and "F_h" in r

    def test_seal_strips_reduce_v(self, typical_params):
        r_no = compute_crossflow_velocity(**typical_params, n_sealing_strip_pairs=0)
        r_yes = compute_crossflow_velocity(**typical_params, n_sealing_strip_pairs=5)
        # Seal strips should reduce bypass, which can affect velocity
        assert r_yes["V_ft_s"] != r_no["V_ft_s"]


# ═══════════════════════════════════════════════════════════════════════════
# Vibration checks
# ═══════════════════════════════════════════════════════════════════════════

class TestDFactor:
    def test_30deg_valid_range(self):
        D = _compute_D_factor(30, 1.25, 0.5)
        assert D > 0

    def test_90deg_low_X(self):
        D = _compute_D_factor(90, 1.25, 0.1)
        assert D > 0

    def test_45deg(self):
        D = _compute_D_factor(45, 1.25, 1.0)
        assert D > 0

    def test_60deg(self):
        D = _compute_D_factor(60, 1.25, 0.5)
        assert D > 0

    def test_higher_X_higher_D(self):
        D_low = _compute_D_factor(30, 1.25, 1.0)
        D_high = _compute_D_factor(30, 1.25, 10.0)
        assert D_high > D_low


class TestFluidelastic:
    def test_safe_low_velocity(self):
        r = check_fluidelastic(V_ft_s=1.0, f_n_Hz=100.0, d_o_m=0.01905, D_factor=5.0)
        assert r["fluidelastic_safe"] is True

    def test_unsafe_high_velocity(self):
        r = check_fluidelastic(V_ft_s=100.0, f_n_Hz=10.0, d_o_m=0.01905, D_factor=2.0)
        assert r["fluidelastic_safe"] is False

    def test_keys(self):
        r = check_fluidelastic(1.0, 50.0, 0.01905, 5.0)
        expected_keys = {"V_crit_ft_s", "V_crit_m_s", "velocity_ratio", "D_factor", "fluidelastic_safe"}
        assert set(r.keys()) == expected_keys


class TestStrouhalInterpolation:
    def test_90_deg_within_range(self):
        S = _interpolate_strouhal(90, 1.5, 2.0)
        assert 0.0 < S < 1.0

    def test_30_deg_within_range(self):
        S = _interpolate_strouhal(30, 1.5, 1.0)
        assert 0.0 < S < 1.0

    def test_higher_spacing_lower_strouhal(self):
        """At wide spacing, Strouhal should decrease."""
        S_tight = _interpolate_strouhal(90, 1.2, 1.5)
        S_wide = _interpolate_strouhal(90, 3.0, 1.5)
        assert S_wide >= S_tight  # wider pt_do generally gives higher S


class TestLiftCoefficient:
    def test_known_point(self):
        C_L = _interpolate_CL(1.25, 30)
        assert C_L == pytest.approx(0.091, rel=1e-3)

    def test_interpolated(self):
        C_L = _interpolate_CL(1.30, 90)
        assert 0.0 < C_L < 1.0


class TestVortexShedding:
    def test_safe_low_velocity(self):
        r = check_vortex_shedding(
            V_ft_s=1.0, f_n_Hz=50.0, d_o_m=0.01905,
            rho_shell_kg_m3=998.0, w_0_lb_ft=0.6, delta_T=0.05,
            pitch_angle_deg=30, pitch_ratio=1.25, pl_do=1.08,
        )
        assert r["vortex_shedding_safe"] is True

    def test_keys(self):
        r = check_vortex_shedding(
            V_ft_s=1.0, f_n_Hz=50.0, d_o_m=0.01905,
            rho_shell_kg_m3=998.0, w_0_lb_ft=0.6, delta_T=0.05,
            pitch_angle_deg=30, pitch_ratio=1.25, pl_do=1.08,
        )
        for key in ["f_vs_Hz", "y_vs_mm", "y_max_mm", "amplitude_ratio_vs",
                     "vortex_shedding_safe", "strouhal_number", "C_L"]:
            assert key in r


class TestForceCoefficient:
    def test_low_freq(self):
        assert _get_force_coefficient(20.0, True) == pytest.approx(0.022)
        assert _get_force_coefficient(20.0, False) == pytest.approx(0.012)

    def test_high_freq(self):
        assert _get_force_coefficient(100.0, True) == pytest.approx(0.0)
        assert _get_force_coefficient(100.0, False) == pytest.approx(0.0)

    def test_mid_freq(self):
        C_F = _get_force_coefficient(64.0, True)
        assert 0.0 < C_F < 0.022


class TestTurbulentBuffeting:
    def test_safe(self):
        r = check_turbulent_buffeting(
            V_ft_s=1.0, f_n_Hz=50.0, d_o_m=0.01905,
            rho_shell_kg_m3=998.0, w_0_lb_ft=0.6, delta_T=0.05,
            pitch_ratio=1.25, pl_do=1.08,
        )
        assert r["turbulent_buffeting_safe"] is True

    def test_entrance_higher_cf(self):
        r_entrance = check_turbulent_buffeting(
            V_ft_s=5.0, f_n_Hz=30.0, d_o_m=0.01905,
            rho_shell_kg_m3=998.0, w_0_lb_ft=0.6, delta_T=0.05,
            pitch_ratio=1.25, pl_do=1.08, is_entrance=True,
        )
        r_interior = check_turbulent_buffeting(
            V_ft_s=5.0, f_n_Hz=30.0, d_o_m=0.01905,
            rho_shell_kg_m3=998.0, w_0_lb_ft=0.6, delta_T=0.05,
            pitch_ratio=1.25, pl_do=1.08, is_entrance=False,
        )
        assert r_entrance["C_F"] > r_interior["C_F"]


class TestAcousticResonance:
    def test_liquid_not_applicable(self):
        r = check_acoustic_resonance(
            V_ft_s=5.0, f_vs_Hz=100.0, f_tb_Hz=80.0,
            d_o_m=0.01905, shell_id_m=0.489, pitch_ratio=1.25,
            pl_do=1.08, pitch_angle_deg=30, rho_shell_kg_m3=998.0,
            mu_shell_Pa_s=0.001, is_gas=False,
        )
        assert r["applicable"] is False
        assert r["resonance_possible"] is False

    def test_gas_applicable(self):
        r = check_acoustic_resonance(
            V_ft_s=5.0, f_vs_Hz=100.0, f_tb_Hz=80.0,
            d_o_m=0.01905, shell_id_m=0.489, pitch_ratio=1.25,
            pl_do=1.08, pitch_angle_deg=30, rho_shell_kg_m3=5.0,
            mu_shell_Pa_s=1.8e-5, is_gas=True,
            P_shell_Pa=500000.0, gamma=1.4,
        )
        assert r["applicable"] is True
        assert "f_a_modes_Hz" in r


class TestLongitudinalPitchRatio:
    def test_triangular_30(self):
        pl = _compute_longitudinal_pitch_ratio(30, 1.25)
        assert pl == pytest.approx(1.25 * math.sqrt(3) / 2, rel=1e-6)

    def test_square_90(self):
        pl = _compute_longitudinal_pitch_ratio(90, 1.25)
        assert pl == pytest.approx(1.25, rel=1e-6)


# ═══════════════════════════════════════════════════════════════════════════
# Full orchestrator
# ═══════════════════════════════════════════════════════════════════════════

class TestCheckAllSpans:
    @pytest.fixture
    def typical_inputs(self):
        return dict(
            tube_od_m=0.01905,
            tube_id_m=0.01483,
            tube_pitch_m=0.02381,
            shell_id_m=0.489,
            baffle_spacing_m=0.20,
            inlet_baffle_spacing_m=None,
            outlet_baffle_spacing_m=None,
            baffle_cut=0.25,
            baffle_thickness_m=0.00635,
            n_baffles=5,
            pitch_angle_deg=30,
            pitch_ratio=1.25,
            n_sealing_strip_pairs=0,
            otl_m=0.467,
            E_Pa=200e9,
            rho_metal_kg_m3=7850.0,
            rho_shell_kg_m3=998.0,
            mu_shell_Pa_s=0.001,
            rho_tube_fluid_kg_m3=998.0,
            shell_flow_kg_s=10.0,
        )

    def test_result_structure(self, typical_inputs):
        r = check_all_spans(**typical_inputs)
        assert "spans" in r
        assert len(r["spans"]) == 3
        assert "acoustic_resonance" in r
        assert "tube_properties" in r
        assert "crossflow_velocity" in r
        assert "all_safe" in r
        assert "controlling_mechanism" in r
        assert "critical_span" in r

    def test_span_locations(self, typical_inputs):
        r = check_all_spans(**typical_inputs)
        locs = [s["location"] for s in r["spans"]]
        assert locs == ["inlet", "central", "outlet"]

    def test_safe_for_typical_exchanger(self, typical_inputs):
        r = check_all_spans(**typical_inputs)
        assert isinstance(r["all_safe"], bool)

    def test_worst_velocity_ratio_positive(self, typical_inputs):
        r = check_all_spans(**typical_inputs)
        assert r["worst_velocity_ratio"] > 0

    def test_explicit_inlet_outlet_spacing(self, typical_inputs):
        typical_inputs["inlet_baffle_spacing_m"] = 0.30
        typical_inputs["outlet_baffle_spacing_m"] = 0.30
        r = check_all_spans(**typical_inputs)
        inlet = r["spans"][0]
        assert inlet["span_m"] == pytest.approx(0.30)

    def test_gas_service(self, typical_inputs):
        typical_inputs["is_gas"] = True
        typical_inputs["rho_shell_kg_m3"] = 5.0
        typical_inputs["mu_shell_Pa_s"] = 1.8e-5
        typical_inputs["P_shell_Pa"] = 500000.0
        typical_inputs["gamma"] = 1.4
        r = check_all_spans(**typical_inputs)
        assert r["acoustic_resonance"]["applicable"] is True

    def test_90deg_layout(self, typical_inputs):
        typical_inputs["pitch_angle_deg"] = 90
        r = check_all_spans(**typical_inputs)
        assert len(r["spans"]) == 3

    def test_controlling_mechanism_valid(self, typical_inputs):
        r = check_all_spans(**typical_inputs)
        valid = {"none", "fluidelastic_instability", "vortex_shedding",
                 "turbulent_buffeting", "acoustic_resonance"}
        assert r["controlling_mechanism"] in valid
