"""Validation rule registry — Layer 2 hard rules that AI cannot override."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from hx_engine.app.models.step_result import StepResult


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    auto_corrections: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

# Type: (step_id, StepResult) -> (passed: bool, error_msg: str | None)
RuleFunc = Callable[[int, StepResult], tuple[bool, str | None]]

_rules: dict[int, list[RuleFunc]] = {}


def register_rule(step_id: int, rule: RuleFunc) -> None:
    """Register a validation rule for a specific step."""
    _rules.setdefault(step_id, []).append(rule)


def check(step_id: int, result: StepResult) -> ValidationResult:
    """Run all registered rules for *step_id* against *result*.

    All rules execute — no short-circuiting.
    """
    vr = ValidationResult()
    for rule in _rules.get(step_id, []):
        passed, msg = rule(step_id, result)
        if not passed:
            vr.passed = False
            if msg:
                vr.errors.append(msg)
    return vr


def clear_rules() -> None:
    """Remove all registered rules (useful in tests)."""
    _rules.clear()
