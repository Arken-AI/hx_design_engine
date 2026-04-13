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
    has_correctable_failure: bool = False
    has_uncorrectable_failure: bool = False

    @property
    def any_correctable(self) -> bool:
        """True when at least one failing rule is AI-correctable."""
        return self.has_correctable_failure


# ---------------------------------------------------------------------------
# Rule metadata
# ---------------------------------------------------------------------------

@dataclass
class RuleMeta:
    """Pairs a rule function with a correctable flag.

    correctable=True  → AI may attempt geometry/parameter corrections.
    correctable=False → physics violation; skip AI, escalate to user.
    """

    func: RuleFunc
    correctable: bool = True


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

# Type: (step_id, StepResult) -> (passed: bool, error_msg: str | None)
RuleFunc = Callable[[int, StepResult], tuple[bool, str | None]]

_rules: dict[int, list[RuleMeta]] = {}


def register_rule(
    step_id: int,
    rule: RuleFunc,
    *,
    correctable: bool = True,
) -> None:
    """Register a validation rule for a specific step.

    Args:
        step_id: Pipeline step this rule applies to.
        rule: Callable ``(step_id, StepResult) -> (passed, error_msg)``.
        correctable: If *False* the rule represents a physics violation that
            AI cannot fix — the pipeline should escalate directly to the user.
    """
    _rules.setdefault(step_id, []).append(RuleMeta(func=rule, correctable=correctable))


def check(step_id: int, result: StepResult) -> ValidationResult:
    """Run all registered rules for *step_id* against *result*.

    All rules execute — no short-circuiting.
    """
    vr = ValidationResult()
    for meta in _rules.get(step_id, []):
        passed, msg = meta.func(step_id, result)
        if not passed:
            vr.passed = False
            if msg:
                vr.errors.append(msg)
            if meta.correctable:
                vr.has_correctable_failure = True
            else:
                vr.has_uncorrectable_failure = True
    return vr


def clear_rules() -> None:
    """Remove all registered rules (useful in tests)."""
    _rules.clear()
