"""BD-REF-001 gate test — validates bell_delaware.py against the reference calculator.

Tolerances:
  - Geometry values: ±0.5%
  - J-factors: ±0.5%
  - h values (h_ideal, h_o): ±2.0%

This test MUST pass before any Step 8 orchestration code proceeds.
"""

from __future__ import annotations

import json
import os

import pytest

from hx_engine.app.correlations.bell_delaware import (
    compute_geometry,
    compute_J_b,
    compute_J_c,
    compute_J_l,
    compute_J_r,
    compute_J_s,
    ideal_bank_ji,
    shell_side_htc,
)

# ---------------------------------------------------------------------------
# Load reference data
# ---------------------------------------------------------------------------

_REF_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "bd_ref_001.json")

with open(_REF_PATH) as _f:
    REF = json.load(_f)

REF_INPUTS = REF["inputs"]
REF_GEOM = REF["geometry"]
REF_RESULTS = REF["results"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct(actual: float, expected: float) -> float:
    """Return absolute percentage deviation."""
    if expected == 0:
        return abs(actual) * 100.0
    return abs(actual - expected) / abs(expected) * 100.0


# ---------------------------------------------------------------------------
# Test geometry computation — ±0.5%
# ---------------------------------------------------------------------------

class TestGeometry:
    """Validate every geometry intermediate against BD-REF-001."""

    @pytest.fixture(autouse=True)
    def _compute(self) -> None:
        self.geom = compute_geometry(
            shell_id_m=REF_INPUTS["shell_id_m"],
            tube_od_m=REF_INPUTS["tube_od_m"],
            tube_pitch_m=REF_INPUTS["tube_pitch_m"],
            layout_angle_deg=REF_INPUTS["layout_angle_deg"],
            n_tubes=REF_INPUTS["num_tubes"],
            tube_passes=REF_INPUTS["tube_passes"],
            baffle_cut_pct=REF_INPUTS["baffle_cut_pct"],
            baffle_spacing_central_m=REF_INPUTS["baffle_spacing_central_m"],
            baffle_spacing_inlet_m=REF_INPUTS["baffle_spacing_inlet_m"],
            baffle_spacing_outlet_m=REF_INPUTS["baffle_spacing_outlet_m"],
            n_baffles=REF_INPUTS["num_baffles"],
            n_sealing_strip_pairs=REF_INPUTS["num_sealing_strips"],
            delta_tb_m=REF_INPUTS["clearances"]["tube_baffle_diametral_m"],
            delta_sb_m=REF_INPUTS["clearances"]["shell_baffle_diametral_m"],
            delta_bundle_shell_m=REF_INPUTS["clearances"]["bundle_shell_diametral_m"],
            mass_flow_kg_s=REF_INPUTS["fluid"]["mass_flow_kg_s"],
            viscosity_Pa_s=REF_INPUTS["fluid"]["viscosity_Pa_s"],
        )

    @pytest.mark.parametrize("key", [
        "D_otl_m", "theta_ctl_rad", "theta_ds_rad",
        "F_c", "F_w", "N_tw",
        "S_m_m2", "S_w_m2", "S_tb_m2", "S_sb_m2", "S_b_m2",
        "r_lm", "r_s", "F_bp", "P_p_m",
        "N_c", "N_cw", "G_s_kg_m2s", "Re_shell",
    ])
    def test_geometry_value(self, key: str) -> None:
        actual = self.geom[key]
        expected = REF_GEOM[key]
        pct = _pct(actual, expected)
        assert pct < 0.5, (
            f"{key}: actual={actual:.6f}, expected={expected:.6f}, "
            f"deviation={pct:.3f}% (limit 0.5%)"
        )


# ---------------------------------------------------------------------------
# Test ideal j-factor — ±0.5%
# ---------------------------------------------------------------------------

class TestIdealJFactor:
    def test_ji_at_ref_Re(self) -> None:
        j_i = ideal_bank_ji(
            Re=REF_GEOM["Re_shell"],
            layout_angle_deg=REF_INPUTS["layout_angle_deg"],
            pitch_ratio=REF_INPUTS["pitch_ratio"],
        )
        pct = _pct(j_i, REF_RESULTS["j_i"])
        assert pct < 0.5, (
            f"j_i: actual={j_i:.6f}, expected={REF_RESULTS['j_i']:.6f}, "
            f"deviation={pct:.3f}%"
        )


# ---------------------------------------------------------------------------
# Test individual J-factors — ±0.5%
# ---------------------------------------------------------------------------

class TestJFactors:
    @pytest.fixture(autouse=True)
    def _compute_geom(self) -> None:
        self.geom = compute_geometry(
            shell_id_m=REF_INPUTS["shell_id_m"],
            tube_od_m=REF_INPUTS["tube_od_m"],
            tube_pitch_m=REF_INPUTS["tube_pitch_m"],
            layout_angle_deg=REF_INPUTS["layout_angle_deg"],
            n_tubes=REF_INPUTS["num_tubes"],
            tube_passes=REF_INPUTS["tube_passes"],
            baffle_cut_pct=REF_INPUTS["baffle_cut_pct"],
            baffle_spacing_central_m=REF_INPUTS["baffle_spacing_central_m"],
            baffle_spacing_inlet_m=REF_INPUTS["baffle_spacing_inlet_m"],
            baffle_spacing_outlet_m=REF_INPUTS["baffle_spacing_outlet_m"],
            n_baffles=REF_INPUTS["num_baffles"],
            n_sealing_strip_pairs=REF_INPUTS["num_sealing_strips"],
            delta_tb_m=REF_INPUTS["clearances"]["tube_baffle_diametral_m"],
            delta_sb_m=REF_INPUTS["clearances"]["shell_baffle_diametral_m"],
            delta_bundle_shell_m=REF_INPUTS["clearances"]["bundle_shell_diametral_m"],
            mass_flow_kg_s=REF_INPUTS["fluid"]["mass_flow_kg_s"],
            viscosity_Pa_s=REF_INPUTS["fluid"]["viscosity_Pa_s"],
        )

    def test_J_c(self) -> None:
        J_c = compute_J_c(self.geom["F_c"])
        pct = _pct(J_c, REF_RESULTS["J_c"])
        assert pct < 0.5, f"J_c: {J_c:.6f} vs {REF_RESULTS['J_c']:.6f} ({pct:.3f}%)"

    def test_J_l(self) -> None:
        J_l = compute_J_l(
            self.geom["S_tb_m2"], self.geom["S_sb_m2"], self.geom["S_m_m2"],
        )
        pct = _pct(J_l, REF_RESULTS["J_l"])
        assert pct < 0.5, f"J_l: {J_l:.6f} vs {REF_RESULTS['J_l']:.6f} ({pct:.3f}%)"

    def test_J_b(self) -> None:
        J_b = compute_J_b(
            self.geom["F_bp"],
            REF_INPUTS["num_sealing_strips"],
            self.geom["N_c"],
            self.geom["Re_shell"],
        )
        pct = _pct(J_b, REF_RESULTS["J_b"])
        assert pct < 0.5, f"J_b: {J_b:.6f} vs {REF_RESULTS['J_b']:.6f} ({pct:.3f}%)"

    def test_J_s(self) -> None:
        J_s = compute_J_s(
            REF_INPUTS["num_baffles"],
            REF_INPUTS["baffle_spacing_inlet_m"],
            REF_INPUTS["baffle_spacing_outlet_m"],
            REF_INPUTS["baffle_spacing_central_m"],
        )
        pct = _pct(J_s, REF_RESULTS["J_s"])
        assert pct < 0.5, f"J_s: {J_s:.6f} vs {REF_RESULTS['J_s']:.6f} ({pct:.3f}%)"

    def test_J_r(self) -> None:
        J_r = compute_J_r(self.geom["Re_shell"], self.geom["N_c"])
        pct = _pct(J_r, REF_RESULTS["J_r"])
        assert pct < 0.5, f"J_r: {J_r:.6f} vs {REF_RESULTS['J_r']:.6f} ({pct:.3f}%)"


# ---------------------------------------------------------------------------
# Test h values — ±2.0%
# ---------------------------------------------------------------------------

class TestHValues:
    def test_full_bell_delaware(self) -> None:
        result = shell_side_htc(
            shell_id_m=REF_INPUTS["shell_id_m"],
            tube_od_m=REF_INPUTS["tube_od_m"],
            tube_pitch_m=REF_INPUTS["tube_pitch_m"],
            layout_angle_deg=REF_INPUTS["layout_angle_deg"],
            n_tubes=REF_INPUTS["num_tubes"],
            tube_passes=REF_INPUTS["tube_passes"],
            baffle_cut_pct=REF_INPUTS["baffle_cut_pct"],
            baffle_spacing_central_m=REF_INPUTS["baffle_spacing_central_m"],
            baffle_spacing_inlet_m=REF_INPUTS["baffle_spacing_inlet_m"],
            baffle_spacing_outlet_m=REF_INPUTS["baffle_spacing_outlet_m"],
            n_baffles=REF_INPUTS["num_baffles"],
            n_sealing_strip_pairs=REF_INPUTS["num_sealing_strips"],
            delta_tb_m=REF_INPUTS["clearances"]["tube_baffle_diametral_m"],
            delta_sb_m=REF_INPUTS["clearances"]["shell_baffle_diametral_m"],
            delta_bundle_shell_m=REF_INPUTS["clearances"]["bundle_shell_diametral_m"],
            density_kg_m3=REF_INPUTS["fluid"]["density_kg_m3"],
            viscosity_Pa_s=REF_INPUTS["fluid"]["viscosity_Pa_s"],
            viscosity_wall_Pa_s=REF_INPUTS["fluid"]["viscosity_wall_Pa_s"],
            Cp_J_kgK=REF_INPUTS["fluid"]["Cp_J_kgK"],
            k_W_mK=REF_INPUTS["fluid"]["k_W_mK"],
            Pr=REF_INPUTS["fluid"]["Pr"],
            mass_flow_kg_s=REF_INPUTS["fluid"]["mass_flow_kg_s"],
            pitch_ratio=REF_INPUTS["pitch_ratio"],
        )

        # h_ideal ±2%
        pct_ideal = _pct(result["h_ideal_W_m2K"], REF_RESULTS["h_ideal_W_m2K"])
        assert pct_ideal < 2.0, (
            f"h_ideal: {result['h_ideal_W_m2K']:.2f} vs "
            f"{REF_RESULTS['h_ideal_W_m2K']:.2f} ({pct_ideal:.3f}%)"
        )

        # h_o ±2%
        pct_ho = _pct(result["h_o_W_m2K"], REF_RESULTS["h_o_W_m2K"])
        assert pct_ho < 2.0, (
            f"h_o: {result['h_o_W_m2K']:.2f} vs "
            f"{REF_RESULTS['h_o_W_m2K']:.2f} ({pct_ho:.3f}%)"
        )

        # J-product ±0.5%
        pct_jp = _pct(result["J_product"], REF_RESULTS["J_product"])
        assert pct_jp < 0.5, (
            f"J_product: {result['J_product']:.6f} vs "
            f"{REF_RESULTS['J_product']:.6f} ({pct_jp:.3f}%)"
        )

    def test_visc_correction(self) -> None:
        result = shell_side_htc(
            shell_id_m=REF_INPUTS["shell_id_m"],
            tube_od_m=REF_INPUTS["tube_od_m"],
            tube_pitch_m=REF_INPUTS["tube_pitch_m"],
            layout_angle_deg=REF_INPUTS["layout_angle_deg"],
            n_tubes=REF_INPUTS["num_tubes"],
            tube_passes=REF_INPUTS["tube_passes"],
            baffle_cut_pct=REF_INPUTS["baffle_cut_pct"],
            baffle_spacing_central_m=REF_INPUTS["baffle_spacing_central_m"],
            baffle_spacing_inlet_m=REF_INPUTS["baffle_spacing_inlet_m"],
            baffle_spacing_outlet_m=REF_INPUTS["baffle_spacing_outlet_m"],
            n_baffles=REF_INPUTS["num_baffles"],
            n_sealing_strip_pairs=REF_INPUTS["num_sealing_strips"],
            delta_tb_m=REF_INPUTS["clearances"]["tube_baffle_diametral_m"],
            delta_sb_m=REF_INPUTS["clearances"]["shell_baffle_diametral_m"],
            delta_bundle_shell_m=REF_INPUTS["clearances"]["bundle_shell_diametral_m"],
            density_kg_m3=REF_INPUTS["fluid"]["density_kg_m3"],
            viscosity_Pa_s=REF_INPUTS["fluid"]["viscosity_Pa_s"],
            viscosity_wall_Pa_s=REF_INPUTS["fluid"]["viscosity_wall_Pa_s"],
            Cp_J_kgK=REF_INPUTS["fluid"]["Cp_J_kgK"],
            k_W_mK=REF_INPUTS["fluid"]["k_W_mK"],
            Pr=REF_INPUTS["fluid"]["Pr"],
            mass_flow_kg_s=REF_INPUTS["fluid"]["mass_flow_kg_s"],
            pitch_ratio=REF_INPUTS["pitch_ratio"],
        )
        pct = _pct(result["visc_correction"], REF_RESULTS["visc_correction"])
        assert pct < 0.5, (
            f"visc_correction: {result['visc_correction']:.6f} vs "
            f"{REF_RESULTS['visc_correction']:.6f} ({pct:.3f}%)"
        )


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_invalid_layout_angle(self) -> None:
        with pytest.raises(ValueError, match="layout_angle_deg"):
            ideal_bank_ji(10000.0, 15, 1.33)

    def test_negative_Re(self) -> None:
        with pytest.raises(ValueError, match="Re must be > 0"):
            ideal_bank_ji(-100.0, 30, 1.33)
