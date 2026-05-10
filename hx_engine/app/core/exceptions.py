"""Pipeline exceptions for calculation and hard-validation failures."""

from __future__ import annotations

from typing import Any, Optional


class CalculationError(Exception):
    """Raised when a step's calculation fails (math error, property lookup, etc.)."""

    def __init__(
        self,
        step_id: int,
        message: str,
        cause: Optional[Exception] = None,
    ) -> None:
        self.step_id = step_id
        self.message = message
        self.cause = cause
        super().__init__(f"Step {step_id}: {message}")


class StepHardFailure(Exception):
    """Raised when a Layer-2 rule violation is detected that AI cannot override."""

    def __init__(
        self,
        step_id: int,
        validation_errors: list[str],
    ) -> None:
        self.step_id = step_id
        self.validation_errors = validation_errors
        super().__init__(
            f"Step {step_id} hard failure: {'; '.join(validation_errors)}"
        )


class DesignConstraintViolation(Exception):
    """Recoverable design-constraint violation that the redesign loop can act on.

    Distinct from :class:`CalculationError` (which is a true math/lookup
    failure) — this is raised when a downstream step proves an upstream
    geometry/assumption is infeasible, and an experienced engineer would
    change a lever and try again. The redesign driver
    (``hx_engine.app.core.redesign_loop.RedesignDriver``) catches this
    type, asks the AI advisor (or its deterministic fallback) which
    lever to tweak, mutates the state, and restarts the pipeline.

    Attributes
    ----------
    step_id:
        The pipeline step that detected the violation.
    constraint:
        Short identifier of the failing constraint, e.g.
        ``"nozzle_envelope"``, ``"overdesign_band"``,
        ``"tube_velocity_max"``, ``"shell_vibration"``. Used by the
        AI prompt and by the deterministic fallback's lever lookup.
    failing_value:
        The numeric value that violated the constraint (e.g.
        the actual ρv² in nozzle units). Stored for the audit trail.
    allowed_range:
        Tuple ``(low, high)`` — the legal envelope. Either bound may
        be ``None`` if one side is unbounded.
    suggested_levers:
        Ordered list of upstream parameter names the redesign driver
        is allowed to vary to recover. Names must come from the
        canonical lever set (see ``redesign_loop.LEGAL_LEVERS``).
    message:
        Human-readable explanation, surfaced both in the audit trail
        and in the closest-feasible-design SSE event when the loop
        budget is exhausted.
    """

    def __init__(
        self,
        step_id: int,
        constraint: str,
        message: str,
        *,
        failing_value: Any = None,
        allowed_range: tuple[Optional[float], Optional[float]] = (None, None),
        suggested_levers: Optional[list[str]] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        self.step_id = step_id
        self.constraint = constraint
        self.message = message
        self.failing_value = failing_value
        self.allowed_range = allowed_range
        self.suggested_levers = list(suggested_levers or ())
        self.cause = cause
        super().__init__(
            f"Step {step_id} constraint violation [{constraint}]: {message}"
        )
