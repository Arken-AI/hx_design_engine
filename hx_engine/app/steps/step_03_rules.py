"""Layer 2 validation rules for Step 3 (Fluid Properties).

These are hard physics rules that the AI cannot override.
Registered at module level via ``register_step3_rules()``.
"""

from __future__ import annotations

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.step_result import StepResult


def _rule_all_properties_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R1 — Every property field in both FluidProperties must be > 0."""
    for key in ("hot_fluid_props", "cold_fluid_props"):
        props = result.outputs.get(key)
        if props is None:
            return False, f"{key} is missing from outputs"
        for field in (
            "density_kg_m3", "viscosity_Pa_s", "cp_J_kgK", "k_W_mK", "Pr",
        ):
            val = getattr(props, field, None)
            if val is not None and val <= 0:
                return False, f"{key}.{field}={val} is not positive"
    return True, None


def _rule_density_bounds(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R2 — 50 ≤ ρ ≤ 2000 kg/m³ for both sides."""
    for key in ("hot_fluid_props", "cold_fluid_props"):
        props = result.outputs.get(key)
        if props is None:
            continue
        rho = props.density_kg_m3
        if rho is not None and (rho < 50 or rho > 2000):
            return False, f"{key}.density_kg_m3={rho} outside [50, 2000]"
    return True, None


def _rule_viscosity_bounds(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R3 — 1e-6 ≤ μ ≤ 1.0 Pa·s for both sides."""
    for key in ("hot_fluid_props", "cold_fluid_props"):
        props = result.outputs.get(key)
        if props is None:
            continue
        mu = props.viscosity_Pa_s
        if mu is not None and (mu < 1e-6 or mu > 1.0):
            return False, f"{key}.viscosity_Pa_s={mu} outside [1e-6, 1.0]"
    return True, None


def _rule_k_bounds(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R4 — 0.01 ≤ k ≤ 100 W/m·K for both sides."""
    for key in ("hot_fluid_props", "cold_fluid_props"):
        props = result.outputs.get(key)
        if props is None:
            continue
        k = props.k_W_mK
        if k is not None and (k < 0.01 or k > 100):
            return False, f"{key}.k_W_mK={k} outside [0.01, 100]"
    return True, None


def _rule_cp_bounds(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R5 — 500 ≤ Cp ≤ 10000 J/kg·K for both sides."""
    for key in ("hot_fluid_props", "cold_fluid_props"):
        props = result.outputs.get(key)
        if props is None:
            continue
        cp = props.cp_J_kgK
        if cp is not None and (cp < 500 or cp > 10000):
            return False, f"{key}.cp_J_kgK={cp} outside [500, 10000]"
    return True, None


def _rule_pr_consistency(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R6 — Pr ≈ μ·Cp/k within 5% (thermodynamic consistency)."""
    for key in ("hot_fluid_props", "cold_fluid_props"):
        props = result.outputs.get(key)
        if props is None:
            continue
        mu = props.viscosity_Pa_s
        cp = props.cp_J_kgK
        k = props.k_W_mK
        pr = props.Pr
        if all(v is not None and v > 0 for v in (mu, cp, k, pr)):
            expected_pr = mu * cp / k
            rel_error = abs(pr - expected_pr) / expected_pr
            if rel_error > 0.05:
                return False, (
                    f"{key}.Pr={pr:.2f} is inconsistent with "
                    f"μ·Cp/k={expected_pr:.2f} "
                    f"(error={rel_error * 100:.1f}% > 5%)"
                )
    return True, None


def register_step3_rules() -> None:
    """Register all Layer 2 rules for step_id=3."""
    register_rule(3, _rule_all_properties_positive)
    register_rule(3, _rule_density_bounds)
    register_rule(3, _rule_viscosity_bounds)
    register_rule(3, _rule_k_bounds)
    register_rule(3, _rule_cp_bounds)
    register_rule(3, _rule_pr_consistency)
