"""Tests for Piece 2 — step_05_rules.py Layer 2 validation rules."""

from __future__ import annotations

import pytest

from hx_engine.app.core.validation_rules import check, clear_rules
from hx_engine.app.models.step_result import StepResult

# Import triggers auto-registration
import hx_engine.app.steps.step_05_rules  # noqa: F401


@pytest.fixture(autouse=True)
def _register_rules():
    """Re-register rules for each test to handle clear_rules calls."""
    clear_rules()
    hx_engine.app.steps.step_05_rules.register_step5_rules()
    yield
    clear_rules()


def _make_result(**overrides) -> StepResult:
    """Build a valid Step 5 StepResult with optional overrides."""
    outputs = {
        "LMTD_K": 76.17,
        "F_factor": 0.945,
        "effective_LMTD": 71.98,
        "R": 2.4,
        "P": 0.2083,
        "shell_passes": 1,
        "auto_corrected": False,
    }
    outputs.update(overrides)
    return StepResult(step_id=5, step_name="LMTD & F-Factor", outputs=outputs)


class TestStep05Rules:

    # --- LMTD rules ---

    def test_rule_lmtd_positive_passes(self):
        vr = check(5, _make_result(LMTD_K=73.1))
        assert vr.passed

    def test_rule_lmtd_zero_fails(self):
        vr = check(5, _make_result(LMTD_K=0.0))
        assert not vr.passed
        assert any("LMTD must be > 0" in e for e in vr.errors)

    def test_rule_lmtd_negative_fails(self):
        vr = check(5, _make_result(LMTD_K=-5.0))
        assert not vr.passed

    def test_rule_lmtd_missing_fails(self):
        result = _make_result()
        del result.outputs["LMTD_K"]
        vr = check(5, result)
        assert not vr.passed
        assert any("missing" in e for e in vr.errors)

    # --- F-factor rules ---

    def test_rule_f_above_075_passes(self):
        vr = check(5, _make_result(F_factor=0.92))
        assert vr.passed

    def test_rule_f_below_075_fails(self):
        vr = check(5, _make_result(F_factor=0.70))
        assert not vr.passed
        assert any("< 0.75" in e for e in vr.errors)

    def test_rule_f_above_1_fails(self):
        vr = check(5, _make_result(F_factor=1.05))
        assert not vr.passed
        assert any("> 1.0" in e for e in vr.errors)

    # --- R and P rules ---

    def test_rule_R_positive_passes(self):
        vr = check(5, _make_result(R=2.4))
        assert vr.passed

    def test_rule_P_in_range_passes(self):
        vr = check(5, _make_result(P=0.208))
        assert vr.passed

    def test_rule_P_out_of_range_fails(self):
        vr = check(5, _make_result(P=1.1))
        assert not vr.passed
        assert any("outside valid range" in e for e in vr.errors)

    # --- Isothermal phase-change bypass (P1-7 regression guard) ---

    def test_isothermal_bypass_skips_R_positive_rule(self):
        """f_factor_basis=isothermal_phase_change → R=0 must NOT fail R4."""
        vr = check(5, _make_result(
            R=0.0, P=1.0, F_factor=1.0,
            f_factor_basis="isothermal_phase_change",
        ))
        assert vr.passed, f"Bypass should clear R/P rules; got errors: {vr.errors}"

    def test_isothermal_bypass_skips_P_in_range_rule(self):
        """f_factor_basis=isothermal_phase_change → P=1.0 must NOT fail R5."""
        vr = check(5, _make_result(
            R=0.0, P=1.0, F_factor=1.0,
            f_factor_basis="isothermal_phase_change",
        ))
        assert vr.passed
        assert not any("P =" in e for e in vr.errors)

    def test_R_zero_without_bypass_still_fails(self):
        """Regression guard: bypass must be opt-in, not silent for all cases."""
        vr = check(5, _make_result(R=0.0))
        assert not vr.passed
        assert any("R = 0.0000" in e for e in vr.errors)
