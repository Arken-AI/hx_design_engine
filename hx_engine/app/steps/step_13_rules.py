"""Layer 2 validation rules for Step 13 (Vibration Check).

Hard rules that AI **cannot** override — safety-critical.
Registered at module level via ``register_step13_rules()``.
"""

from __future__ import annotations

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.step_result import StepResult


# ---------------------------------------------------------------------------
# R1 — vibration_safe must be present
# ---------------------------------------------------------------------------

def _rule_vibration_safe_present(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    val = result.outputs.get("vibration_safe")
    if val is None:
        return False, "vibration_safe is missing from Step 13 outputs"
    return True, None


# ---------------------------------------------------------------------------
# R2 — Fluidelastic velocity ratio < 0.5 at all spans
# ---------------------------------------------------------------------------

def _rule_fluidelastic_safe(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    details = result.outputs.get("vibration_details")
    if details is None:
        return False, "vibration_details is missing from Step 13 outputs"
    spans = details.get("spans", [])
    for span in spans:
        vr = span.get("velocity_ratio", 0.0)
        if vr >= 0.5:
            loc = span.get("location", "unknown")
            return (
                False,
                f"Fluidelastic instability at {loc} span: "
                f"velocity ratio = {vr:.3f} ≥ 0.5",
            )
    return True, None


# ---------------------------------------------------------------------------
# R3 — Vortex shedding amplitude ≤ 2% of tube OD at all spans
# ---------------------------------------------------------------------------

def _rule_vortex_shedding_safe(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    details = result.outputs.get("vibration_details")
    if details is None:
        return False, "vibration_details is missing from Step 13 outputs"
    spans = details.get("spans", [])
    for span in spans:
        ar = span.get("amplitude_ratio_vs", 0.0)
        if ar > 1.0:
            loc = span.get("location", "unknown")
            return (
                False,
                f"Vortex shedding amplitude exceeds limit at {loc} span: "
                f"amplitude ratio = {ar:.3f} > 1.0",
            )
    return True, None


# ---------------------------------------------------------------------------
# R4 — Turbulent buffeting amplitude ≤ 2% of tube OD at all spans
# ---------------------------------------------------------------------------

def _rule_turbulent_buffeting_safe(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    details = result.outputs.get("vibration_details")
    if details is None:
        return False, "vibration_details is missing from Step 13 outputs"
    spans = details.get("spans", [])
    for span in spans:
        ar = span.get("amplitude_ratio_tb", 0.0)
        if ar > 1.0:
            loc = span.get("location", "unknown")
            return (
                False,
                f"Turbulent buffeting amplitude exceeds limit at {loc} span: "
                f"amplitude ratio = {ar:.3f} > 1.0",
            )
    return True, None


# ---------------------------------------------------------------------------
# Auto-register on import
# ---------------------------------------------------------------------------

def register_step13_rules() -> None:
    register_rule(13, _rule_vibration_safe_present)
    register_rule(13, _rule_fluidelastic_safe)
    register_rule(13, _rule_vortex_shedding_safe)
    register_rule(13, _rule_turbulent_buffeting_safe)


register_step13_rules()
