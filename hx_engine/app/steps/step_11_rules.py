"""Layer 2 validation rules for Step 11 (Area and Overdesign).

Hard rules that AI **cannot** override.
Registered at module level via ``register_step11_rules()``.
"""

from __future__ import annotations

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.step_result import StepResult


# ---------------------------------------------------------------------------
# R1 — Required area must be positive
# ---------------------------------------------------------------------------

def _rule_area_required_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    val = result.outputs.get("area_required_m2")
    if val is None:
        return False, "area_required_m2 is missing from Step 11 outputs"
    if val <= 0:
        return False, f"Required area must be positive, got {val:.4f} m²"
    return True, None


# ---------------------------------------------------------------------------
# R2 — Provided area must be positive
# ---------------------------------------------------------------------------

def _rule_area_provided_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    val = result.outputs.get("area_provided_m2")
    if val is None:
        return False, "area_provided_m2 is missing from Step 11 outputs"
    if val <= 0:
        return False, f"Provided area must be positive, got {val:.4f} m²"
    return True, None


# ---------------------------------------------------------------------------
# R3 — Overdesign must not be negative (exchanger must not be undersized)
# ---------------------------------------------------------------------------

def _rule_overdesign_not_negative(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    val = result.outputs.get("overdesign_pct")
    if val is None:
        return False, "overdesign_pct is missing from Step 11 outputs"
    if val < 0:
        return False, (
            f"Overdesign is {val:.1f}% — exchanger is undersized. "
            f"Need more area or higher U."
        )
    return True, None


# ---------------------------------------------------------------------------
# R4 — Low-velocity fouling paradox ESCALATE (P2-24)
# ---------------------------------------------------------------------------

def _rule_fouling_paradox_escalate(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R4 — Escalate when Layer 1 flagged the low-velocity fouling paradox.

    The paradox (excess area → low velocity → accelerated fouling) cannot be
    resolved by geometry correction alone; it requires the engineer to decide
    whether to reduce tube count, add a shell, or re-evaluate the fouling
    resistance. Routes straight to ESCALATE (correctable=False).
    """
    if result.outputs.get("fouling_paradox_severity") != "escalate":
        return True, None
    od = result.outputs.get("overdesign_pct")
    od_str = f"{od:.1f}%" if od is not None else "unknown"
    return False, (
        f"Low-velocity fouling paradox requires intervention: "
        f"overdesign={od_str} — excess area reduces tube velocity and "
        f"accelerates fouling deposit. Reduce tube count, add a parallel "
        f"shell, or revise the fouling resistance assumption."
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_step11_rules() -> None:
    """Register all Layer 2 rules for step_id=11."""
    register_rule(11, _rule_area_required_positive)
    register_rule(11, _rule_area_provided_positive)
    register_rule(11, _rule_overdesign_not_negative)
    register_rule(11, _rule_fouling_paradox_escalate, correctable=False)


# Auto-register on import
register_step11_rules()
