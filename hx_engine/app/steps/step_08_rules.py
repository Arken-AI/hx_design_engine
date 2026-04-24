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


def _is_shah_condensing(result: StepResult) -> bool:
    """True when Step 8 used the Shah condensation correlation.

    Shah outputs have no J-factors; the Bell-Delaware J-factor rules must
    not run on this branch.
    """
    return result.outputs.get("method") == "shah_condensation"


def _rule_j_factors_range(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Each J-factor must be within [0.2, 1.2] (Bell-Delaware path only)."""
    if _is_shah_condensing(result):
        return True, None
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
# R3 — Full 5-factor Bell-Delaware J-product floor
# ---------------------------------------------------------------------------

_J_PRODUCT_FLOOR = 0.30

# Geometry remediation hints keyed by the dominant (lowest) J-factor.
_J_LEVER_HINTS: dict[str, str] = {
    "J_c": "increase baffle cut or reduce baffle overlap",
    "J_l": "tighten shell-to-baffle / tube-to-baffle clearances",
    "J_b": "add sealing strips to close bundle-to-shell bypass lanes",
    "J_s": "even out inlet/outlet baffle spacing",
    "J_r": "raise shell-side Reynolds (tighter baffle spacing or higher flow)",
}


def _rule_j_product_floor(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Full Bell-Delaware product J_c·J_l·J_b·J_s·J_r must exceed the floor.

    The original 3-factor check silently dropped J_s and J_r, masking
    infeasible geometries where unequal baffle spacing or low Re dragged
    the true product below 0.30 while the partial product was benign.

    Skipped for the Shah condensation path — that path has no J-factors.
    """
    if _is_shah_condensing(result):
        return True, None
    factors = {key: result.outputs.get(key) for key in _J_FACTOR_KEYS}
    missing = [key for key, val in factors.items() if val is None]
    if missing:
        return False, (
            f"Missing J-factors {missing} in Step 8 outputs — cannot evaluate "
            f"Bell-Delaware correction product"
        )

    product = 1.0
    for val in factors.values():
        product *= val

    if product >= _J_PRODUCT_FLOOR:
        return True, None

    dominant_key = min(factors, key=lambda k: factors[k])
    dominant_val = factors[dominant_key]
    lever = _J_LEVER_HINTS.get(dominant_key, "revise shell-side geometry")
    breakdown = ", ".join(f"{k}={factors[k]:.4f}" for k in _J_FACTOR_KEYS)
    return False, (
        f"J_c·J_l·J_b·J_s·J_r = {product:.4f} below minimum {_J_PRODUCT_FLOOR:.2f} — "
        f"dominant low factor {dominant_key}={dominant_val:.4f} ({lever}). "
        f"Breakdown: {breakdown}."
    )


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
