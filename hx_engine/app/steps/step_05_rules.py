"""Layer 2 validation rules for Step 5 (LMTD + F-Factor).

These are hard thermodynamic rules that AI **cannot** override.
Registered at module level via ``register_step5_rules()``.
"""

from __future__ import annotations

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.step_result import StepResult


# ---------------------------------------------------------------------------
# R1 — LMTD must be positive
# ---------------------------------------------------------------------------

def _rule_lmtd_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """LMTD must be > 0 — no heat transfer driving force otherwise."""
    val = result.outputs.get("LMTD_K")
    if val is None:
        return False, "LMTD_K is missing from Step 5 outputs"
    if val <= 0:
        return False, (
            f"LMTD must be > 0, got {val:.4f} — no heat transfer driving force"
        )
    return True, None


# ---------------------------------------------------------------------------
# R2 — F-factor >= 0.75
# ---------------------------------------------------------------------------

def _rule_f_factor_minimum(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """F-factor must be >= 0.75 — below this the exchanger is infeasible."""
    val = result.outputs.get("F_factor")
    if val is None:
        return False, "F_factor is missing from Step 5 outputs"
    if val < 0.75:
        return False, (
            f"F-factor = {val:.4f} < 0.75 — exchanger configuration is thermally "
            f"infeasible. Even with 2 shell passes, F is too low. Consider: "
            f"(1) reducing temperature cross, (2) different TEMA configuration, "
            f"or (3) splitting into multiple units."
        )
    return True, None


# ---------------------------------------------------------------------------
# R3 — F-factor <= 1.0
# ---------------------------------------------------------------------------

def _rule_f_factor_maximum(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """F-factor cannot exceed 1.0 — violates thermodynamics."""
    val = result.outputs.get("F_factor")
    if val is not None and val > 1.0 + 1e-9:
        return False, (
            f"F-factor = {val:.4f} > 1.0 — mathematically impossible"
        )
    return True, None


# ---------------------------------------------------------------------------
# R4 — R must be positive
# ---------------------------------------------------------------------------

def _is_isothermal_bypass(result: StepResult) -> bool:
    """True when Step 5 short-circuited due to isothermal phase change.

    Isothermal sides produce R=0 or P=1 by construction; the R/P rules
    must not treat those values as physics violations.
    """
    return result.outputs.get("f_factor_basis") == "isothermal_phase_change"


def _rule_R_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R must be > 0 for valid heat exchange (skipped for isothermal service)."""
    if _is_isothermal_bypass(result):
        return True, None
    val = result.outputs.get("R")
    if val is not None and val <= 0:
        return False, (
            f"R = {val:.4f} must be > 0 — invalid temperature data"
        )
    return True, None


# ---------------------------------------------------------------------------
# R5 — P must be in (0, 1)
# ---------------------------------------------------------------------------

def _rule_P_in_range(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """P must be in (0, 1) — skipped for isothermal phase-change service."""
    if _is_isothermal_bypass(result):
        return True, None
    val = result.outputs.get("P")
    if val is not None:
        if val <= 0 or val >= 1:
            return False, (
                f"P = {val:.4f} outside valid range (0, 1) — check temperatures"
            )
    return True, None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_step5_rules() -> None:
    """Register all Layer 2 rules for step_id=5."""
    register_rule(5, _rule_lmtd_positive)
    # F below 0.75 is a thermodynamic infeasibility, not a correctable
    # AI geometry error — route straight to the user via ESCALATE.
    register_rule(5, _rule_f_factor_minimum, correctable=False)
    register_rule(5, _rule_f_factor_maximum)
    register_rule(5, _rule_R_positive)
    register_rule(5, _rule_P_in_range)


# Auto-register on import
register_step5_rules()
