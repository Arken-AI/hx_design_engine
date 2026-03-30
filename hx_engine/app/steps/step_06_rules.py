"""Layer 2 validation rules for Step 6 (Initial U + Size Estimate).

These are hard rules that AI **cannot** override.
Registered at module level via ``register_step6_rules()``.
"""

from __future__ import annotations

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.step_result import StepResult


# ---------------------------------------------------------------------------
# R1 — U must be positive
# ---------------------------------------------------------------------------

def _rule_u_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """U (overall heat transfer coefficient) must be > 0."""
    val = result.outputs.get("U_W_m2K")
    if val is None:
        return False, "U_W_m2K is missing from Step 6 outputs"
    if val <= 0:
        return False, (
            f"U must be positive, got {val:.2f} W/m²K"
        )
    return True, None


# ---------------------------------------------------------------------------
# R2 — Heat transfer area must be positive
# ---------------------------------------------------------------------------

def _rule_area_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Required heat transfer area must be > 0."""
    val = result.outputs.get("A_m2")
    if val is None:
        return False, "A_m2 is missing from Step 6 outputs"
    if val <= 0:
        return False, (
            f"Heat transfer area must be positive, got {val:.4f} m²"
        )
    return True, None


# ---------------------------------------------------------------------------
# R3 — Tube count must be at least 1
# ---------------------------------------------------------------------------

def _rule_n_tubes_minimum(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Tube count must be >= 1."""
    geom = result.outputs.get("geometry")
    if geom is None:
        return False, "geometry is missing from Step 6 outputs"
    # GeometrySpec may be a model or dict
    n_tubes = getattr(geom, "n_tubes", None)
    if n_tubes is None and isinstance(geom, dict):
        n_tubes = geom.get("n_tubes")
    if n_tubes is None:
        return False, "n_tubes is missing from geometry in Step 6 outputs"
    if n_tubes < 1:
        return False, (
            f"Tube count must be at least 1, got {n_tubes}"
        )
    return True, None


# ---------------------------------------------------------------------------
# R4 — Shell diameter must be a TEMA standard size
# ---------------------------------------------------------------------------

def _rule_shell_standard(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Shell diameter must be a TEMA standard size."""
    geom = result.outputs.get("geometry")
    if geom is None:
        return True, None  # Already caught by R3

    shell_d = getattr(geom, "shell_diameter_m", None)
    if shell_d is None and isinstance(geom, dict):
        shell_d = geom.get("shell_diameter_m")
    if shell_d is None:
        return False, "shell_diameter_m is missing from geometry in Step 6 outputs"
    if shell_d <= 0:
        return False, (
            f"Shell diameter must be positive, got {shell_d:.4f} m"
        )

    # Verify it matches a standard shell diameter
    from hx_engine.app.data.tema_tables import get_standard_shell_diameters

    standard = get_standard_shell_diameters()
    tol = 0.001  # 1 mm tolerance
    if not any(abs(shell_d - s) < tol for s in standard):
        return False, (
            f"Shell diameter {shell_d:.4f} m is not a TEMA standard size"
        )
    return True, None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_step6_rules() -> None:
    """Register all Layer 2 rules for step_id=6."""
    register_rule(6, _rule_u_positive)
    register_rule(6, _rule_area_positive)
    register_rule(6, _rule_n_tubes_minimum)
    register_rule(6, _rule_shell_standard)


# Auto-register on import
register_step6_rules()
