"""Step 14 — Mechanical Design Check: Layer 2 hard validation rules.

Rules that AI cannot override. Registered automatically on module import.
"""

from __future__ import annotations

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.step_result import StepResult


# ---------------------------------------------------------------------------
# Rule functions — each returns (passed: bool, error_msg: str | None)
# ---------------------------------------------------------------------------

def _rule_tube_thickness_present(
    step_id: int, result: StepResult
) -> tuple[bool, str | None]:
    """R1: tube_thickness_ok must exist in outputs."""
    val = result.outputs.get("tube_thickness_ok")
    if val is None:
        return False, "tube_thickness_ok is missing from Step 14 outputs"
    return True, None


def _rule_shell_thickness_present(
    step_id: int, result: StepResult
) -> tuple[bool, str | None]:
    """R2: shell_thickness_ok must exist in outputs."""
    val = result.outputs.get("shell_thickness_ok")
    if val is None:
        return False, "shell_thickness_ok is missing from Step 14 outputs"
    return True, None


def _rule_mechanical_details_present(
    step_id: int, result: StepResult
) -> tuple[bool, str | None]:
    """R3: mechanical_details must be populated."""
    details = result.outputs.get("mechanical_details")
    if details is None:
        return False, "mechanical_details is missing from Step 14 outputs"
    return True, None


def _rule_tube_internal_adequate(
    step_id: int, result: StepResult
) -> tuple[bool, str | None]:
    """R4: Tube wall must be thick enough for internal pressure."""
    details = result.outputs.get("mechanical_details")
    if details is None:
        return True, None  # R3 catches this
    tube = details.get("tube", {})
    t_actual = tube.get("t_actual_mm", 0)
    t_min = tube.get("t_min_internal_mm", 0)
    if t_actual < t_min:
        return False, (
            f"Tube wall too thin for internal pressure: "
            f"t_actual={t_actual:.3f} mm < t_min={t_min:.3f} mm"
        )
    return True, None


def _rule_tube_external_adequate(
    step_id: int, result: StepResult
) -> tuple[bool, str | None]:
    """R5: Shell-side pressure must not collapse tubes."""
    details = result.outputs.get("mechanical_details")
    if details is None:
        return True, None
    ext = details.get("tube", {}).get("external_pressure", {})
    if not ext:
        return True, None
    P_applied = ext.get("P_applied_Pa", 0)
    P_allow = ext.get("P_allowable_Pa", float("inf"))
    if P_applied > P_allow:
        return False, (
            f"Tube external pressure exceeds allowable: "
            f"P_applied={P_applied/1e6:.3f} MPa > P_allowable={P_allow/1e6:.3f} MPa"
        )
    return True, None


def _rule_shell_t_min_positive(
    step_id: int, result: StepResult
) -> tuple[bool, str | None]:
    """R6: Shell minimum thickness must be positive (sanity)."""
    details = result.outputs.get("mechanical_details")
    if details is None:
        return True, None
    shell = details.get("shell", {})
    t_min = shell.get("t_min_internal_mm", 0)
    if t_min <= 0:
        return False, (
            f"Shell t_min_internal_mm must be positive, got {t_min:.3f}"
        )
    return True, None


def _rule_expansion_within_tolerance(
    step_id: int, result: StepResult
) -> tuple[bool, str | None]:
    """R7: For fixed tubesheet types, expansion must be within tolerance."""
    details = result.outputs.get("mechanical_details")
    if details is None:
        return True, None
    expansion = details.get("expansion", {})
    within = expansion.get("within_tolerance")
    if within is False:
        diff = expansion.get("differential_mm", 0)
        tol = expansion.get("tolerance_mm", 0)
        tema = expansion.get("tema_type", "unknown")
        return False, (
            f"Thermal expansion exceeds tolerance for {tema}: "
            f"differential={diff:.2f} mm > tolerance={tol:.1f} mm — "
            f"consider switching to floating-head type (e.g. AES)"
        )
    return True, None


# ---------------------------------------------------------------------------
# Auto-register on import
# ---------------------------------------------------------------------------

def register_step14_rules() -> None:
    register_rule(14, _rule_tube_thickness_present)
    register_rule(14, _rule_shell_thickness_present)
    register_rule(14, _rule_mechanical_details_present)
    register_rule(14, _rule_tube_internal_adequate)
    register_rule(14, _rule_tube_external_adequate)
    register_rule(14, _rule_shell_t_min_positive)
    register_rule(14, _rule_expansion_within_tolerance)


register_step14_rules()
