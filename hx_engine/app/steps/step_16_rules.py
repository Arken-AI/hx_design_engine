"""Step 16 — Final Validation: Layer 2 hard validation rules.

Rules that AI cannot override. Registered automatically on module import.
"""

from __future__ import annotations

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.step_result import StepResult

# Expected keys in the confidence breakdown dict
_EXPECTED_BREAKDOWN_KEYS = frozenset({
    "geometry_convergence",
    "ai_agreement_rate",
    "validation_passes",
})


# ---------------------------------------------------------------------------
# Rule functions — each returns (passed: bool, error_msg: str | None)
# ---------------------------------------------------------------------------

def _rule_confidence_computed(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R16.1 — confidence_score must exist and be in [0.0, 1.0]."""
    val = result.outputs.get("confidence_score")
    if val is None:
        return False, "confidence_score is missing from Step 16 outputs"
    if not isinstance(val, (int, float)):
        return False, f"confidence_score must be numeric, got {type(val).__name__}"
    if val < 0.0 or val > 1.0:
        return False, f"confidence_score must be between 0.0 and 1.0, got {val:.4f}"
    return True, None


def _rule_breakdown_complete(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R16.2 — confidence_breakdown must have exactly 3 keys."""
    bd = result.outputs.get("confidence_breakdown")
    if bd is None:
        return False, "confidence_breakdown is missing from Step 16 outputs"
    if not isinstance(bd, dict):
        return False, f"confidence_breakdown must be a dict, got {type(bd).__name__}"
    if len(bd) != 3:
        return False, (
            f"confidence_breakdown must have exactly 3 components, "
            f"got {len(bd)}: {sorted(bd.keys())}"
        )
    return True, None


def _rule_breakdown_values_valid(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R16.3 — each breakdown value must be in [0.0, 1.0]."""
    bd = result.outputs.get("confidence_breakdown")
    if bd is None or not isinstance(bd, dict):
        return True, None  # R16.2 catches this
    for key, val in bd.items():
        if not isinstance(val, (int, float)):
            return False, (
                f"confidence_breakdown['{key}'] must be numeric, "
                f"got {type(val).__name__}"
            )
        if val < 0.0 or val > 1.0:
            return False, (
                f"confidence_breakdown['{key}'] must be between 0.0 and 1.0, "
                f"got {val:.4f}"
            )
    return True, None


def _rule_summary_present(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R16.4 — design_summary must be non-empty."""
    val = result.outputs.get("design_summary")
    if val is None or (isinstance(val, str) and not val.strip()):
        return False, "design_summary must be non-empty"
    return True, None


def _rule_breakdown_keys_correct(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R16.5 — breakdown keys must match expected names."""
    bd = result.outputs.get("confidence_breakdown")
    if bd is None or not isinstance(bd, dict):
        return True, None  # R16.2 catches this
    actual_keys = frozenset(bd.keys())
    if actual_keys != _EXPECTED_BREAKDOWN_KEYS:
        missing = _EXPECTED_BREAKDOWN_KEYS - actual_keys
        extra = actual_keys - _EXPECTED_BREAKDOWN_KEYS
        parts = []
        if missing:
            parts.append(f"missing: {sorted(missing)}")
        if extra:
            parts.append(f"unexpected: {sorted(extra)}")
        return False, (
            f"confidence_breakdown keys must be "
            f"{sorted(_EXPECTED_BREAKDOWN_KEYS)}, {'; '.join(parts)}"
        )
    return True, None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_step16_rules() -> None:
    """Register all Step 16 hard rules."""
    register_rule(16, _rule_confidence_computed)
    register_rule(16, _rule_breakdown_complete)
    register_rule(16, _rule_breakdown_values_valid)
    register_rule(16, _rule_summary_present)
    register_rule(16, _rule_breakdown_keys_correct)


# Auto-register on import (same pattern as step_15_rules.py)
register_step16_rules()
