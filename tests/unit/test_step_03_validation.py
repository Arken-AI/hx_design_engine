"""Tests for Piece 5: Layer 2 validation rules for Step 3."""

from __future__ import annotations

import pytest

from hx_engine.app.core import validation_rules
from hx_engine.app.models.design_state import FluidProperties
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_03_rules import (
    _rule_all_properties_positive,
    _rule_cp_bounds,
    _rule_density_bounds,
    _rule_k_bounds,
    _rule_pr_consistency,
    _rule_viscosity_bounds,
    register_step3_rules,
)


def _make_result(hot: FluidProperties, cold: FluidProperties) -> StepResult:
    return StepResult(
        step_id=3,
        step_name="Fluid Properties",
        outputs={
            "hot_fluid_props": hot,
            "cold_fluid_props": cold,
        },
    )


def _good_hot() -> FluidProperties:
    """Valid crude oil-like properties."""
    return FluidProperties(
        density_kg_m3=850.0, viscosity_Pa_s=0.002,
        cp_J_kgK=2000.0, k_W_mK=0.13, Pr=30.77,
    )


def _good_cold() -> FluidProperties:
    """Valid ethanol-like properties."""
    return FluidProperties(
        density_kg_m3=780.0, viscosity_Pa_s=0.001,
        cp_J_kgK=2500.0, k_W_mK=0.16, Pr=15.63,
    )


class TestValidationRules:
    """Ten tests guarding Layer 2 hard validation rules."""

    def test_valid_benchmark_passes_all(self):
        """Known-good crude oil + ethanol passes all rules."""
        result = _make_result(_good_hot(), _good_cold())

        assert _rule_all_properties_positive(3, result) == (True, None)
        assert _rule_density_bounds(3, result) == (True, None)
        assert _rule_viscosity_bounds(3, result) == (True, None)
        assert _rule_k_bounds(3, result) == (True, None)
        assert _rule_cp_bounds(3, result) == (True, None)
        assert _rule_pr_consistency(3, result) == (True, None)

    def test_negative_density_fails_r1(self):
        """Negative density → R1 fails (density can't be negative).

        Uses raw mock to bypass Pydantic validators (which also catch this).
        """
        bad = type("FP", (), {
            "density_kg_m3": -100.0, "viscosity_Pa_s": 0.001,
            "cp_J_kgK": 2000.0, "k_W_mK": 0.13, "Pr": 15.0,
        })()
        result = StepResult(
            step_id=3, step_name="Fluid Properties",
            outputs={"hot_fluid_props": bad, "cold_fluid_props": _good_cold()},
        )
        passed, msg = _rule_all_properties_positive(3, result)
        assert passed is False
        assert "density_kg_m3" in msg

    def test_zero_viscosity_fails_r1(self):
        """Zero viscosity → R1 fails (only superfluids have μ=0).

        Uses raw mock to bypass Pydantic validators.
        """
        bad = type("FP", (), {
            "density_kg_m3": 850.0, "viscosity_Pa_s": 0.0,
            "cp_J_kgK": 2000.0, "k_W_mK": 0.13, "Pr": 15.0,
        })()
        result = StepResult(
            step_id=3, step_name="Fluid Properties",
            outputs={"hot_fluid_props": bad, "cold_fluid_props": _good_cold()},
        )
        passed, msg = _rule_all_properties_positive(3, result)
        assert passed is False
        assert "viscosity_Pa_s" in msg

    def test_density_too_high_fails_r2(self):
        """ρ = 3000 → R2 fails (only mercury/molten metals exceed 2000).

        Note: Pydantic validator on FluidProperties already caps at 2000,
        so we test via the rule function directly with a raw result.
        """
        # Build result with raw dict (bypassing Pydantic) to test rule logic
        result = StepResult(
            step_id=3, step_name="Fluid Properties",
            outputs={
                "hot_fluid_props": type("FP", (), {
                    "density_kg_m3": 3000.0, "viscosity_Pa_s": 0.001,
                    "cp_J_kgK": 2000.0, "k_W_mK": 0.13, "Pr": 15.0,
                })(),
                "cold_fluid_props": _good_cold(),
            },
        )
        passed, msg = _rule_density_bounds(3, result)
        assert passed is False
        assert "3000" in msg

    def test_density_too_low_fails_r2(self):
        """ρ = 10 → R2 fails (too low for any liquid/dense gas in HX)."""
        result = StepResult(
            step_id=3, step_name="Fluid Properties",
            outputs={
                "hot_fluid_props": type("FP", (), {
                    "density_kg_m3": 10.0, "viscosity_Pa_s": 0.001,
                    "cp_J_kgK": 2000.0, "k_W_mK": 0.13, "Pr": 15.0,
                })(),
                "cold_fluid_props": _good_cold(),
            },
        )
        passed, msg = _rule_density_bounds(3, result)
        assert passed is False
        assert "10" in msg

    def test_viscosity_too_high_fails_r3(self):
        """μ = 5.0 → R3 fails (beyond heavy bitumen range)."""
        result = StepResult(
            step_id=3, step_name="Fluid Properties",
            outputs={
                "hot_fluid_props": type("FP", (), {
                    "density_kg_m3": 850.0, "viscosity_Pa_s": 5.0,
                    "cp_J_kgK": 2000.0, "k_W_mK": 0.13, "Pr": 15.0,
                })(),
                "cold_fluid_props": _good_cold(),
            },
        )
        passed, msg = _rule_viscosity_bounds(3, result)
        assert passed is False
        assert "5.0" in msg

    def test_k_too_low_fails_r4(self):
        """k = 0.001 → R4 fails (even vacuum insulation > 0.01)."""
        result = StepResult(
            step_id=3, step_name="Fluid Properties",
            outputs={
                "hot_fluid_props": type("FP", (), {
                    "density_kg_m3": 850.0, "viscosity_Pa_s": 0.001,
                    "cp_J_kgK": 2000.0, "k_W_mK": 0.001, "Pr": 15.0,
                })(),
                "cold_fluid_props": _good_cold(),
            },
        )
        passed, msg = _rule_k_bounds(3, result)
        assert passed is False
        assert "0.001" in msg

    def test_cp_out_of_range_fails_r5(self):
        """Cp = 50000 → R5 fails (no engineering fluid has Cp this high)."""
        result = StepResult(
            step_id=3, step_name="Fluid Properties",
            outputs={
                "hot_fluid_props": type("FP", (), {
                    "density_kg_m3": 850.0, "viscosity_Pa_s": 0.001,
                    "cp_J_kgK": 50000.0, "k_W_mK": 0.13, "Pr": 15.0,
                })(),
                "cold_fluid_props": _good_cold(),
            },
        )
        passed, msg = _rule_cp_bounds(3, result)
        assert passed is False
        assert "50000" in msg

    def test_pr_self_consistent_passes_r6(self):
        """μ=0.001, Cp=4180, k=0.6 → Pr ≈ 6.97 → R6 passes."""
        # Pr = μ·Cp/k = 0.001 × 4180 / 0.6 = 6.9667
        props = FluidProperties(
            density_kg_m3=994.0, viscosity_Pa_s=0.001,
            cp_J_kgK=4180.0, k_W_mK=0.6, Pr=6.97,
        )
        result = _make_result(props, _good_cold())
        passed, msg = _rule_pr_consistency(3, result)
        assert passed is True

    def test_pr_inconsistent_fails_r6(self):
        """μ=0.001, Cp=4180, k=0.6, Pr=50 → R6 fails (stale Pr value)."""
        # Expected Pr = 6.97, but Pr=50 → way off
        props = FluidProperties(
            density_kg_m3=994.0, viscosity_Pa_s=0.001,
            cp_J_kgK=4180.0, k_W_mK=0.6, Pr=50.0,
        )
        result = _make_result(props, _good_cold())
        passed, msg = _rule_pr_consistency(3, result)
        assert passed is False
        assert "inconsistent" in msg


class TestStep3RulesRegistration:
    """Verify rules register and check() integration works."""

    def setup_method(self):
        validation_rules.clear_rules()

    def teardown_method(self):
        validation_rules.clear_rules()

    def test_register_and_check(self):
        """register_step3_rules() populates the registry; check() runs them."""
        register_step3_rules()
        result = _make_result(_good_hot(), _good_cold())
        vr = validation_rules.check(3, result)
        assert vr.passed is True
        assert len(vr.errors) == 0
