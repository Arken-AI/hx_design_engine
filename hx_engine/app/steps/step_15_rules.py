"""Step 15 — Cost Estimate: Layer 2 hard validation rules.

Rules that AI cannot override. Registered automatically on module import.
"""

from __future__ import annotations

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.data.cost_indices import get_cost_per_m2_range
from hx_engine.app.models.step_result import StepResult


# ---------------------------------------------------------------------------
# Rule functions — each returns (passed: bool, error_msg: str | None)
# ---------------------------------------------------------------------------

def _rule_cost_computed(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R1: cost_usd must be present in outputs."""
    val = result.outputs.get("cost_usd")
    if val is None:
        return False, "cost_usd is missing from Step 15 outputs"
    return True, None


def _rule_cost_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R2: cost_usd must be > 0."""
    val = result.outputs.get("cost_usd")
    if val is None:
        return True, None  # R1 catches this
    if val <= 0:
        return False, f"cost_usd must be positive, got {val:.2f}"
    return True, None


def _rule_breakdown_present(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R3: cost_breakdown must be present."""
    bd = result.outputs.get("cost_breakdown")
    if bd is None:
        return False, "cost_breakdown is missing from Step 15 outputs"
    return True, None


def _rule_material_factor_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R4: F_M must be > 0."""
    bd = result.outputs.get("cost_breakdown")
    if bd is None:
        return True, None  # R3 catches this
    f_m = bd.get("F_M", 0)
    if f_m <= 0:
        return False, f"Material factor F_M must be positive, got {f_m}"
    return True, None


def _rule_pressure_factor_valid(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R5: F_P must be >= 1.0."""
    bd = result.outputs.get("cost_breakdown")
    if bd is None:
        return True, None  # R3 catches this
    f_p = bd.get("F_P", 1.0)
    if f_p < 1.0:
        return False, f"Pressure factor F_P must be >= 1.0, got {f_p:.4f}"
    return True, None


def _rule_cost_per_m2_range(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R6: cost_per_m2 must be within the per-material validation range."""
    bd = result.outputs.get("cost_breakdown")
    if bd is None:
        return True, None  # R3 catches this
    cost_per_m2 = bd.get("cost_per_m2_usd")
    if cost_per_m2 is None:
        return True, None
    tube_mat = result.outputs.get("tube_material", "carbon_steel")
    lo, hi = get_cost_per_m2_range(tube_mat)
    if cost_per_m2 < lo or cost_per_m2 > hi:
        return False, (
            f"cost_per_m2 = ${cost_per_m2:,.0f}/m² is outside the "
            f"expected range for {tube_mat}: ${lo:,.0f}–${hi:,.0f}/m²"
        )
    return True, None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_step15_rules() -> None:
    """Register all Step 15 hard rules."""
    register_rule(15, _rule_cost_computed)
    register_rule(15, _rule_cost_positive)
    register_rule(15, _rule_breakdown_present)
    register_rule(15, _rule_material_factor_positive)
    register_rule(15, _rule_pressure_factor_valid)
    register_rule(15, _rule_cost_per_m2_range)


# Auto-register on import (same pattern as step_14_rules.py)
register_step15_rules()
