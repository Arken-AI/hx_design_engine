"""Pipeline exceptions for calculation and hard-validation failures."""

from __future__ import annotations

from typing import Optional


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
