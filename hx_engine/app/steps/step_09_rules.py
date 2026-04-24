"""Layer 2 validation rules for Step 9 (Overall Heat Transfer Coefficient).

Hard rules that AI **cannot** override.
Registered at module level via ``register_step9_rules()``.
"""

from __future__ import annotations

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.step_result import StepResult


# ---------------------------------------------------------------------------
# R1 — U_dirty must be positive
# ---------------------------------------------------------------------------

def _rule_u_dirty_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Calculated U (dirty) must be > 0."""
    val = result.outputs.get("U_dirty_W_m2K")
    if val is None:
        return False, "U_dirty_W_m2K is missing from Step 9 outputs"
    if val <= 0:
        return False, f"Calculated U (dirty) must be positive, got {val:.2f} W/m²K"
    return True, None


# ---------------------------------------------------------------------------
# R2 — U_clean must be positive
# ---------------------------------------------------------------------------

def _rule_u_clean_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Clean U must be > 0."""
    val = result.outputs.get("U_clean_W_m2K")
    if val is None:
        return False, "U_clean_W_m2K is missing from Step 9 outputs"
    if val <= 0:
        return False, f"Clean U must be positive, got {val:.2f} W/m²K"
    return True, None


# ---------------------------------------------------------------------------
# R3 — U_clean >= U_dirty (fouling can only reduce U)
# ---------------------------------------------------------------------------

def _rule_u_clean_ge_dirty(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Clean U must be >= dirty U."""
    u_clean = result.outputs.get("U_clean_W_m2K")
    u_dirty = result.outputs.get("U_dirty_W_m2K")
    if u_clean is not None and u_dirty is not None and u_clean < u_dirty - 0.01:
        return False, (
            f"Clean U ({u_clean:.2f}) must be ≥ dirty U ({u_dirty:.2f}) "
            "— fouling can only reduce U"
        )
    return True, None


# ---------------------------------------------------------------------------
# R4 — Cleanliness factor in [0.5, 1.0]
# ---------------------------------------------------------------------------

def _rule_cleanliness_factor_bounds(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Cleanliness factor must be within physical bounds."""
    cf = result.outputs.get("cleanliness_factor")
    if cf is not None and (cf < 0.5 or cf > 1.0):
        return False, (
            f"Cleanliness factor {cf:.3f} outside physical bounds [0.5, 1.0]"
        )
    return True, None


# ---------------------------------------------------------------------------
# R5 — All 5 individual resistances must be >= 0
# ---------------------------------------------------------------------------

def _rule_resistances_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """All individual thermal resistances must be non-negative."""
    breakdown = result.outputs.get("resistance_breakdown", {})
    for name, data in breakdown.items():
        if name == "total_1_over_U":
            continue
        val = data.get("value_m2KW", 0) if isinstance(data, dict) else 0
        if val < 0:
            return False, f"Resistance '{name}' is negative ({val:.6f} m²·K/W)"
    return True, None


# ---------------------------------------------------------------------------
# R6 — Resistance percentages must sum to ~100%
# ---------------------------------------------------------------------------

def _rule_pct_sum(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Sum of resistance percentages should be approximately 100%."""
    breakdown = result.outputs.get("resistance_breakdown", {})
    pct_sum = sum(
        data.get("pct", 0)
        for name, data in breakdown.items()
        if isinstance(data, dict) and name != "total_1_over_U"
    )
    if abs(pct_sum - 100.0) > 0.5:
        return False, (
            f"Resistance percentages sum to {pct_sum:.1f}%, expected ~100%"
        )
    return True, None


# ---------------------------------------------------------------------------
# R7 — Tube diameters must be physically ordered (d_o > d_i > 0)
# ---------------------------------------------------------------------------

def _rule_tube_diameters_ordered(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Tube outer diameter must strictly exceed inner diameter; both > 0.

    Guards ``R_wall = d_o * ln(d_o/d_i) / (2*k_w)`` against:
      - d_i == d_o  -> ln(1) = 0  -> wall resistance silently dropped
      - d_i  > d_o  -> ln(<1) < 0 -> negative wall resistance
      - d_i <= 0 or d_o <= 0      -> math.log domain error / non-physical

    correctable=False — this is an upstream geometry contract violation
    (Step 4 BWG selection, Step 12 adjustment, or an applied correction).
    """
    d_o = result.outputs.get("tube_od_m")
    d_i = result.outputs.get("tube_id_m")

    if d_o is None or d_i is None:
        # Precondition gate in execute() fires first; this is defence-in-depth.
        return True, None
    if d_o <= 0:
        return False, f"Tube outer diameter must be > 0, got d_o={d_o:.6f} m"
    if d_i <= 0:
        return False, f"Tube inner diameter must be > 0, got d_i={d_i:.6f} m"
    if d_i >= d_o:
        return False, (
            f"Tube inner diameter must be strictly less than outer diameter "
            f"(got d_i={d_i:.6f} m >= d_o={d_o:.6f} m); "
            f"wall conduction term ln(d_o/d_i) is non-physical"
        )
    return True, None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_step9_rules() -> None:
    """Register all Layer 2 rules for step_id=9."""
    register_rule(9, _rule_u_dirty_positive)
    register_rule(9, _rule_u_clean_positive)
    register_rule(9, _rule_u_clean_ge_dirty)
    register_rule(9, _rule_cleanliness_factor_bounds)
    register_rule(9, _rule_resistances_positive)
    register_rule(9, _rule_pct_sum)
    register_rule(9, _rule_tube_diameters_ordered)  # R7


# Auto-register on import
register_step9_rules()
