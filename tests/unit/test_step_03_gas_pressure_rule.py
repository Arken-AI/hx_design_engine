"""Tests for Step 03 R7 — _rule_gas_pressure_required (P1-6 coverage).

Vapor / condensing / evaporating phases must NOT default to 1 atm when the
user did not supply a pressure. Liquid phases tolerate the silent fallback.
The rule is registered ``correctable=False`` so a violation routes straight
to ESCALATE.
"""

from __future__ import annotations

from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_03_rules import _rule_gas_pressure_required


def _result(**outputs) -> StepResult:
    return StepResult(step_id=3, step_name="Fluid Properties", outputs=outputs)


class TestRuleGasPressureRequired:
    """Six tests covering the phase × pressure_source matrix."""

    def test_hot_vapor_with_default_1atm_fails(self):
        result = _result(
            hot_phase="vapor", hot_pressure_source="default_1atm",
            cold_phase="liquid", cold_pressure_source="user",
        )
        passed, msg = _rule_gas_pressure_required(3, result)
        assert passed is False
        assert "hot" in msg
        assert "P_hot_Pa" in msg

    def test_hot_vapor_with_user_pressure_passes(self):
        result = _result(
            hot_phase="vapor", hot_pressure_source="user",
            cold_phase="liquid", cold_pressure_source="user",
        )
        assert _rule_gas_pressure_required(3, result) == (True, None)

    def test_liquid_with_default_1atm_passes(self):
        """Liquid density is nearly P-independent; 1 atm fallback is safe."""
        result = _result(
            hot_phase="liquid", hot_pressure_source="default_1atm",
            cold_phase="liquid", cold_pressure_source="default_1atm",
        )
        assert _rule_gas_pressure_required(3, result) == (True, None)

    def test_cold_evaporating_with_default_1atm_fails(self):
        result = _result(
            hot_phase="liquid", hot_pressure_source="user",
            cold_phase="evaporating", cold_pressure_source="default_1atm",
        )
        passed, msg = _rule_gas_pressure_required(3, result)
        assert passed is False
        assert "cold" in msg

    def test_condensing_with_default_1atm_fails(self):
        result = _result(
            hot_phase="condensing", hot_pressure_source="default_1atm",
            cold_phase="liquid", cold_pressure_source="user",
        )
        passed, msg = _rule_gas_pressure_required(3, result)
        assert passed is False
        assert "condensing" in msg

    def test_missing_phase_metadata_passes(self):
        """Backwards-compat: outputs without phase fields don't trip the rule."""
        result = _result()  # no hot_phase / cold_phase / *_pressure_source
        assert _rule_gas_pressure_required(3, result) == (True, None)
