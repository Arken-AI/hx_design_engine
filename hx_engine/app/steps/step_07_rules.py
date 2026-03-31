"""Layer 2 validation rules for Step 7 (Tube-Side Heat Transfer Coefficient).

These are hard rules that AI **cannot** override.
Registered at module level via ``register_step7_rules()``.
"""

from __future__ import annotations

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.step_result import StepResult


# ---------------------------------------------------------------------------
# R1 — h_tube must be positive
# ---------------------------------------------------------------------------

def _rule_h_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Tube-side HTC must be > 0."""
    val = result.outputs.get("h_tube_W_m2K")
    if val is None:
        return False, "h_tube_W_m2K is missing from Step 7 outputs"
    if val <= 0:
        return False, f"h_tube must be positive, got {val:.2f} W/m²K"
    return True, None


# ---------------------------------------------------------------------------
# R2 — Velocity within liquid bounds
# ---------------------------------------------------------------------------

# TODO Phase B: Add gas velocity limits (5.0–30.0 m/s) when gas-phase
# support is added. Currently engine is single-phase liquid only;
# FluidProperties validator enforces ρ ∈ [50, 2000] kg/m³.
V_HARD_MIN, V_HARD_MAX = 0.3, 5.0


def _rule_velocity_bounds(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Tube-side velocity must be within liquid bounds [0.3, 5.0] m/s."""
    val = result.outputs.get("tube_velocity_m_s")
    if val is None:
        return False, "tube_velocity_m_s is missing from Step 7 outputs"
    if val < V_HARD_MIN:
        return False, (
            f"Tube velocity {val:.3f} m/s below hard minimum "
            f"{V_HARD_MIN} m/s"
        )
    if val > V_HARD_MAX:
        return False, (
            f"Tube velocity {val:.3f} m/s above hard maximum "
            f"{V_HARD_MAX} m/s"
        )
    return True, None


# ---------------------------------------------------------------------------
# R3 — Re must be positive
# ---------------------------------------------------------------------------

def _rule_re_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Tube-side Reynolds number must be > 0."""
    val = result.outputs.get("Re_tube")
    if val is None:
        return False, "Re_tube is missing from Step 7 outputs"
    if val <= 0:
        return False, f"Re_tube must be positive, got {val:.1f}"
    return True, None


# ---------------------------------------------------------------------------
# R4 — Pr must be positive
# ---------------------------------------------------------------------------

def _rule_pr_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Tube-side Prandtl number must be > 0."""
    val = result.outputs.get("Pr_tube")
    if val is None:
        return False, "Pr_tube is missing from Step 7 outputs"
    if val <= 0:
        return False, f"Pr_tube must be positive, got {val:.2f}"
    return True, None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_step7_rules() -> None:
    """Register all Layer 2 rules for step_id=7."""
    register_rule(7, _rule_h_positive)
    register_rule(7, _rule_velocity_bounds)
    register_rule(7, _rule_re_positive)
    register_rule(7, _rule_pr_positive)


# Auto-register on import
register_step7_rules()
