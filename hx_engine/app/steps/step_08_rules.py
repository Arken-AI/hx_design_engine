"""Layer 2 validation rules for Step 8 (Shell-Side Heat Transfer Coefficient).

Hard rules that AI **cannot** override.
Registered at module level via ``register_step8_rules()``.
"""

from __future__ import annotations

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.step_result import StepResult


# ---------------------------------------------------------------------------
# R1 — h_shell must be positive
# ---------------------------------------------------------------------------

def _rule_h_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Shell-side HTC must be > 0."""
    val = result.outputs.get("h_shell_W_m2K")
    if val is None:
        return False, "h_shell_W_m2K is missing from Step 8 outputs"
    if val <= 0:
        return False, f"h_shell must be positive, got {val:.2f} W/m²K"
    return True, None


# ---------------------------------------------------------------------------
# R2 — Each J-factor in [0.2, 1.2]
# ---------------------------------------------------------------------------

_J_FACTOR_KEYS = ("J_c", "J_l", "J_b", "J_s", "J_r")


def _rule_j_factors_range(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Each J-factor must be within [0.2, 1.2]."""
    for key in _J_FACTOR_KEYS:
        val = result.outputs.get(key)
        if val is None:
            return False, f"{key} is missing from Step 8 outputs"
        if val < 0.2 or val > 1.2:
            return False, (
                f"{key} = {val:.4f} outside physical range [0.2, 1.2]"
            )
    return True, None


# ---------------------------------------------------------------------------
# R3 — J_c × J_l × J_b product floor
# ---------------------------------------------------------------------------

def _rule_j_product_floor(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Combined correction product J_c × J_l × J_b must be > 0.30."""
    J_c = result.outputs.get("J_c")
    J_l = result.outputs.get("J_l")
    J_b = result.outputs.get("J_b")
    if J_c is None or J_l is None or J_b is None:
        return False, "J_c, J_l, or J_b missing from Step 8 outputs"
    product = J_c * J_l * J_b
    if product < 0.30:
        return False, (
            f"J_c × J_l × J_b = {product:.4f} below minimum 0.30 — "
            f"geometry suspect (J_c={J_c:.4f}, J_l={J_l:.4f}, J_b={J_b:.4f})"
        )
    return True, None


# ---------------------------------------------------------------------------
# R4 — Re_shell must be positive
# ---------------------------------------------------------------------------

def _rule_re_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Shell-side Reynolds number must be > 0."""
    val = result.outputs.get("Re_shell")
    if val is None:
        return False, "Re_shell is missing from Step 8 outputs"
    if val <= 0:
        return False, f"Re_shell must be positive, got {val:.1f}"
    return True, None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_step8_rules() -> None:
    """Register all Layer 2 rules for step_id=8."""
    register_rule(8, _rule_h_positive)
    register_rule(8, _rule_j_factors_range)
    register_rule(8, _rule_j_product_floor)
    register_rule(8, _rule_re_positive)


# Auto-register on import
register_step8_rules()
