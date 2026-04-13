"""Layer 2 validation rules for Step 1 (Process Requirements).

These are hard physics/TEMA rules that the AI cannot override.
"""

from __future__ import annotations

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.step_result import StepResult


def _rule_both_fluids(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    o = result.outputs
    if not o.get("hot_fluid_name"):
        return False, "Hot fluid name is missing"
    if not o.get("cold_fluid_name"):
        return False, "Cold fluid name is missing"
    return True, None


def _rule_at_least_3_temps(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    o = result.outputs
    count = sum(
        1
        for k in ("T_hot_in_C", "T_hot_out_C", "T_cold_in_C", "T_cold_out_C")
        if o.get(k) is not None
    )
    if count < 3:
        return False, f"Need at least 3 temperatures, found {count}"
    return True, None


def _rule_at_least_1_flow(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    o = result.outputs
    if o.get("m_dot_hot_kg_s") is None and o.get("m_dot_cold_kg_s") is None:
        return False, "At least one flow rate is required"
    return True, None


def _rule_temps_physically_reasonable(
    step_id: int, result: StepResult
) -> tuple[bool, str | None]:
    o = result.outputs
    for key in ("T_hot_in_C", "T_hot_out_C", "T_cold_in_C", "T_cold_out_C"):
        val = o.get(key)
        if val is None:
            continue
        if val < -273.15:
            return False, f"{key}={val}°C is below absolute zero"
        if val > 1500:
            return False, f"{key}={val}°C exceeds 1500°C material limit"
    return True, None


def _rule_flow_rates_positive(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    o = result.outputs
    for key in ("m_dot_hot_kg_s", "m_dot_cold_kg_s"):
        val = o.get(key)
        if val is not None and val <= 0:
            return False, f"{key}={val} is not positive"
    return True, None


def _rule_hot_inlet_gt_outlet(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    o = result.outputs
    t_in = o.get("T_hot_in_C")
    t_out = o.get("T_hot_out_C")
    if t_in is not None and t_out is not None and t_in <= t_out:
        return False, "Hot stream would gain heat — T_hot_in must exceed T_hot_out"
    return True, None


def _rule_cold_out_lt_hot_in(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    o = result.outputs
    t_cold_out = o.get("T_cold_out_C")
    t_hot_in = o.get("T_hot_in_C")
    if (
        t_cold_out is not None
        and t_hot_in is not None
        and t_cold_out > t_hot_in
    ):
        return False, "Temperature cross — T_cold_out exceeds T_hot_in (2nd law)"
    return True, None


def register_step1_rules() -> None:
    """Register all Layer 2 rules for step_id=1."""
    register_rule(1, _rule_both_fluids)
    register_rule(1, _rule_at_least_3_temps)
    register_rule(1, _rule_at_least_1_flow)
    register_rule(1, _rule_temps_physically_reasonable, correctable=False)
    register_rule(1, _rule_flow_rates_positive, correctable=False)
    register_rule(1, _rule_hot_inlet_gt_outlet, correctable=False)
    register_rule(1, _rule_cold_out_lt_hot_in, correctable=False)


register_step1_rules()
