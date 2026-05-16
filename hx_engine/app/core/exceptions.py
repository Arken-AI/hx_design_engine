"""Pipeline exceptions for calculation and hard-validation failures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import FluidProperties


class PropertyResolutionRequired(Exception):
    """Raised when fluid properties cannot be resolved from validated sources
    and the AI confidence is below the configurable threshold.

    Instead of silently applying a low-confidence estimate, this exception
    signals that the pipeline must pause and ask the engineer to:
      (a) approve the AI estimate as-is
      (b) provide their own measured / datasheet values  (Slice 2)
      (c) specify a substitute fluid                     (future)

    Attributes
    ----------
    fluid_name:
        The normalised fluid name the lookup was attempted with.
    temperature_C:
        The mean temperature at which properties were requested.
    ai_estimate:
        The ``FluidProperties`` returned by the AI, if available.
        ``None`` when no API key is present or the AI call failed.
    confidence:
        AI confidence score 0–1 (0.0 when no estimate is available).
    threshold:
        The configured threshold that triggered this exception.
    side:
        ``"hot"`` or ``"cold"`` — identifies which fluid stream needs data.
    """

    def __init__(
        self,
        fluid_name: str,
        temperature_C: float,
        *,
        ai_estimate: Optional["FluidProperties"] = None,
        confidence: float = 0.0,
        threshold: float = 0.70,
        side: str = "hot",
    ) -> None:
        self.fluid_name = fluid_name
        self.temperature_C = temperature_C
        self.ai_estimate = ai_estimate
        self.confidence = confidence
        self.threshold = threshold
        self.side = side
        super().__init__(
            f"Fluid '{fluid_name}' at T={temperature_C:.1f}°C: "
            f"AI confidence {confidence:.0%} is below the threshold {threshold:.0%}. "
            f"Engineer input required before the pipeline can continue."
        )


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
