"""Layer 2 validation rules for Step 10 (Pressure Drops).

Hard rules that AI **cannot** override.
Registered at module level via ``register_step10_rules()``.
"""

from __future__ import annotations

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.step_result import StepResult

# Hard limits
_DP_TUBE_LIMIT_PA = 70_000.0   # 0.7 bar
_DP_SHELL_LIMIT_PA = 140_000.0  # 1.4 bar
_RHO_V2_LIMIT = 2230.0          # TEMA erosion limit


# ---------------------------------------------------------------------------
# R1 — Tube-side ΔP must be positive
# ---------------------------------------------------------------------------

def _rule_dp_tube_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    val = result.outputs.get("dP_tube_Pa")
    if val is None:
        return False, "dP_tube_Pa is missing from Step 10 outputs"
    if val <= 0:
        return False, f"Tube-side ΔP must be positive, got {val:.1f} Pa"
    return True, None


# ---------------------------------------------------------------------------
# R2 — Shell-side ΔP must be positive
# ---------------------------------------------------------------------------

def _rule_dp_shell_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    val = result.outputs.get("dP_shell_Pa")
    if val is None:
        return False, "dP_shell_Pa is missing from Step 10 outputs"
    if val <= 0:
        return False, f"Shell-side ΔP must be positive, got {val:.1f} Pa"
    return True, None


# ---------------------------------------------------------------------------
# R3 — Tube-side ΔP within limit
# ---------------------------------------------------------------------------

def _rule_dp_tube_within_limit(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    val = result.outputs.get("dP_tube_Pa")
    if val is not None and val > _DP_TUBE_LIMIT_PA:
        return False, (
            f"Tube-side ΔP {val:.0f} Pa exceeds 0.7 bar "
            f"({_DP_TUBE_LIMIT_PA:.0f} Pa) limit"
        )
    return True, None


# ---------------------------------------------------------------------------
# R4 — Shell-side ΔP within limit
# ---------------------------------------------------------------------------

def _rule_dp_shell_within_limit(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    val = result.outputs.get("dP_shell_Pa")
    if val is not None and val > _DP_SHELL_LIMIT_PA:
        return False, (
            f"Shell-side ΔP {val:.0f} Pa exceeds 1.4 bar "
            f"({_DP_SHELL_LIMIT_PA:.0f} Pa) limit"
        )
    return True, None


# ---------------------------------------------------------------------------
# Shared nozzle ρv² check (R5 + R6)
# ---------------------------------------------------------------------------

def _check_nozzle_rho_v2(
    side: str,
    val: float | None,
    auto_corrected: bool,
) -> tuple[bool, str | None]:
    # auto_corrected is message-only: the flag marks when an upsize was applied,
    # not when the resulting ρv² is verified under the limit.
    if val is None:
        return True, None  # missing output is a Layer 1 contract issue
    if val <= _RHO_V2_LIMIT:
        return True, None
    if auto_corrected:
        reason = (
            f"{side.capitalize()}-side nozzle ρv² {val:.0f} kg/m·s² exceeds "
            f"TEMA erosion limit ({_RHO_V2_LIMIT:.0f} kg/m·s²) even after "
            f"auto-correction (larger nozzle / dual-nozzle exhausted)"
        )
    else:
        reason = (
            f"{side.capitalize()}-side nozzle ρv² {val:.0f} kg/m·s² exceeds "
            f"TEMA erosion limit ({_RHO_V2_LIMIT:.0f} kg/m·s²); "
            f"auto-correction was not applied"
        )
    return False, reason


# ---------------------------------------------------------------------------
# R5 — Tube nozzle ρv² within TEMA erosion limit
# ---------------------------------------------------------------------------

def _rule_nozzle_rho_v2_tube(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    val = result.outputs.get("rho_v2_tube_nozzle")
    auto_corrected = bool(result.outputs.get("nozzle_auto_corrected_tube", False))
    return _check_nozzle_rho_v2("tube", val, auto_corrected)


# ---------------------------------------------------------------------------
# R6 — Shell nozzle ρv² within TEMA erosion limit
# ---------------------------------------------------------------------------

def _rule_nozzle_rho_v2_shell(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    val = result.outputs.get("rho_v2_shell_nozzle")
    auto_corrected = bool(result.outputs.get("nozzle_auto_corrected_shell", False))
    return _check_nozzle_rho_v2("shell", val, auto_corrected)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_step10_rules() -> None:
    """Register all Layer 2 rules for step_id=10."""
    register_rule(10, _rule_dp_tube_positive)
    register_rule(10, _rule_dp_shell_positive)
    register_rule(10, _rule_dp_tube_within_limit)
    register_rule(10, _rule_dp_shell_within_limit)
    register_rule(10, _rule_nozzle_rho_v2_tube)
    register_rule(10, _rule_nozzle_rho_v2_shell)


# Auto-register on import
register_step10_rules()
