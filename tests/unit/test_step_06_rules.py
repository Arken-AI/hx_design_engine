"""Tests for step_06_rules.py — Layer 2 validation rules for Step 6."""

from __future__ import annotations

import pytest

from hx_engine.app.core.validation_rules import check, clear_rules
from hx_engine.app.models.design_state import GeometrySpec
from hx_engine.app.models.step_result import StepResult

# Import triggers auto-registration
import hx_engine.app.steps.step_06_rules  # noqa: F401


def _make_geometry(**overrides) -> GeometrySpec:
    defaults = dict(
        tube_od_m=0.01905,
        tube_id_m=0.01483,
        tube_length_m=4.88,
        pitch_ratio=1.25,
        pitch_layout="triangular",
        n_passes=2,
        shell_passes=1,
        baffle_cut=0.25,
        baffle_spacing_m=0.15,
        shell_diameter_m=13.25 * 0.0254,  # 13.25" TEMA standard
        n_tubes=98,
    )
    defaults.update(overrides)
    return GeometrySpec(**defaults)


@pytest.fixture(autouse=True)
def _register_rules():
    """Re-register rules for each test to handle clear_rules calls."""
    clear_rules()
    hx_engine.app.steps.step_06_rules.register_step6_rules()
    yield
    clear_rules()


def _make_result(**overrides) -> StepResult:
    """Build a valid Step 6 StepResult with optional overrides."""
    outputs = {
        "U_W_m2K": 1200.0,
        "A_m2": 37.0,
        "U_range": {"U_low": 800, "U_mid": 1200, "U_high": 1800},
        "hot_fluid_type": "water",
        "cold_fluid_type": "water",
        "n_tubes_required": 128,
        "A_provided_m2": 38.5,
        "geometry": _make_geometry(),
    }
    outputs.update(overrides)
    return StepResult(step_id=6, step_name="Initial U + Size Estimate", outputs=outputs)


class TestStep06Rules:

    # --- U rules ---

    def test_rule_u_positive_passes(self):
        vr = check(6, _make_result(U_W_m2K=300.0))
        assert vr.passed

    def test_rule_u_zero_fails(self):
        vr = check(6, _make_result(U_W_m2K=0.0))
        assert not vr.passed
        assert any("U must be positive" in e for e in vr.errors)

    def test_rule_u_negative_fails(self):
        vr = check(6, _make_result(U_W_m2K=-100.0))
        assert not vr.passed

    def test_rule_u_missing_fails(self):
        result = _make_result()
        del result.outputs["U_W_m2K"]
        vr = check(6, result)
        assert not vr.passed
        assert any("missing" in e.lower() for e in vr.errors)

    # --- Area rules ---

    def test_rule_area_positive_passes(self):
        vr = check(6, _make_result(A_m2=50.0))
        assert vr.passed

    def test_rule_area_zero_fails(self):
        vr = check(6, _make_result(A_m2=0.0))
        assert not vr.passed
        assert any("area" in e.lower() for e in vr.errors)

    def test_rule_area_negative_fails(self):
        vr = check(6, _make_result(A_m2=-10.0))
        assert not vr.passed

    def test_rule_area_missing_fails(self):
        result = _make_result()
        del result.outputs["A_m2"]
        vr = check(6, result)
        assert not vr.passed
        assert any("missing" in e.lower() for e in vr.errors)

    # --- Tube count rules ---

    def test_rule_n_tubes_ge_1_passes(self):
        vr = check(6, _make_result(geometry=_make_geometry(n_tubes=50)))
        assert vr.passed

    def test_rule_n_tubes_1_passes(self):
        vr = check(6, _make_result(geometry=_make_geometry(n_tubes=1)))
        assert vr.passed

    # --- Shell diameter rules ---

    def test_rule_shell_standard_passes(self):
        """13.25\" shell (0.33655 m) is a standard TEMA size."""
        vr = check(6, _make_result(
            geometry=_make_geometry(shell_diameter_m=13.25 * 0.0254),
        ))
        assert vr.passed

    def test_rule_shell_nonstandard_fails(self):
        """Non-standard shell diameter should fail."""
        vr = check(6, _make_result(
            geometry=_make_geometry(shell_diameter_m=0.4),
        ))
        assert not vr.passed
        assert any("not a TEMA standard" in e for e in vr.errors)

    def test_rule_geometry_missing_fails(self):
        """Missing geometry entirely."""
        result = _make_result()
        del result.outputs["geometry"]
        vr = check(6, result)
        assert not vr.passed
        assert any("geometry" in e.lower() for e in vr.errors)
