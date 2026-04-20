"""Phase 2 — Verify Step 10 nozzle ρv² rules wire into the Layer 2 recovery path.

These tests prove that when the rewritten ``_rule_nozzle_rho_v2_*`` rules
return ``False`` (per the Phase 1 strict-fail contract), the standard Layer 2
machinery in ``validation_rules.check`` reports a correctable failure that
``BaseStep.run_with_review_loop`` / ``run_with_layer2_recovery`` will pick up
and route through the AI correction loop.

Scope: registration + return-shape integration only. The loop-level behaviour
itself (correction attempts, escalation, rollback) is covered by the generic
``test_layer2_recovery.py`` suite using ``RecoverableStep``; re-asserting it
here would be duplication.
"""

from __future__ import annotations

from hx_engine.app.core import validation_rules
from hx_engine.app.models.step_result import StepResult

# Importing the module triggers ``register_step10_rules()`` at module load.
import hx_engine.app.steps.step_10_rules as rules_mod  # noqa: F401


def _make_result(**outputs) -> StepResult:
    defaults = {
        "dP_tube_Pa": 50_000.0,
        "dP_shell_Pa": 80_000.0,
        "rho_v2_tube_nozzle": 500.0,
        "rho_v2_shell_nozzle": 500.0,
    }
    defaults.update(outputs)
    return StepResult(step_id=10, step_name="Pressure Drops", outputs=defaults)


class TestNozzleRulesRegistered:

    def test_both_nozzle_rules_registered_for_step_10(self):
        registered = [m.func for m in validation_rules._rules.get(10, [])]
        assert rules_mod._rule_nozzle_rho_v2_tube in registered
        assert rules_mod._rule_nozzle_rho_v2_shell in registered

    def test_nozzle_rules_registered_as_correctable(self):
        # correctable=True triggers the AI review loop on failure
        for meta in validation_rules._rules.get(10, []):
            if meta.func in (
                rules_mod._rule_nozzle_rho_v2_tube,
                rules_mod._rule_nozzle_rho_v2_shell,
            ):
                assert meta.correctable is True


class TestCheckSurfacesNozzleViolation:

    def test_tube_over_limit_no_auto_correction_routes_as_correctable_failure(self):
        # Arrange
        result = _make_result(
            rho_v2_tube_nozzle=2900.0,
            nozzle_auto_corrected_tube=False,
        )

        vr = validation_rules.check(10, result)

        assert vr.passed is False
        assert vr.has_correctable_failure is True
        assert vr.has_uncorrectable_failure is False
        assert any("2900" in e and "2230" in e for e in vr.errors)

    def test_shell_over_limit_after_auto_correction_routes_as_correctable_failure(self):
        result = _make_result(
            rho_v2_shell_nozzle=2800.0,
            nozzle_auto_corrected_shell=True,
        )

        vr = validation_rules.check(10, result)

        assert vr.passed is False
        assert any("even after auto-correction" in e for e in vr.errors)

    def test_healthy_design_passes_validation(self):
        result = _make_result(rho_v2_tube_nozzle=500.0, rho_v2_shell_nozzle=500.0)

        vr = validation_rules.check(10, result)

        assert vr.passed is True
        assert vr.errors == []
