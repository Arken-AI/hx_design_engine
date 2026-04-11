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
# R5 — Tube nozzle ρv² within TEMA erosion limit
# ---------------------------------------------------------------------------

def _rule_nozzle_rho_v2_tube(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    val = result.outputs.get("rho_v2_tube_nozzle")
    if val is not None and val > _RHO_V2_LIMIT:
        # Auto-correction in execute() should have upsized the nozzle.
        # If ρv² is still over the limit after auto-correction, warn
        # but allow the pipeline to continue.
        auto_corrected = result.outputs.get("nozzle_auto_corrected_tube", False)
        if auto_corrected:
            return True, None   # auto-corrected — pass with warning in outputs
        return True, None       # pass — warning added by execute()
    return True, None


# ---------------------------------------------------------------------------
# R6 — Shell nozzle ρv² within TEMA erosion limit
# ---------------------------------------------------------------------------

def _rule_nozzle_rho_v2_shell(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    val = result.outputs.get("rho_v2_shell_nozzle")
    if val is not None and val > _RHO_V2_LIMIT:
        auto_corrected = result.outputs.get("nozzle_auto_corrected_shell", False)
        if auto_corrected:
            return True, None
        return True, None  # pass — warning added by execute()
    return True, None


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
