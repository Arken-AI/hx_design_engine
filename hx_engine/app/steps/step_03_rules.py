"""Layer 2 validation rules for Step 3 (Fluid Properties).

These are hard physics rules that the AI cannot override.
Registered at module level via ``register_step3_rules()``.
"""

from __future__ import annotations

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_03_fluid_props import _MU_VARIATION_ESCALATE


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
    """R2 — 0.01 ≤ ρ ≤ 2000 kg/m³ for both sides (covers gas & liquid)."""
    for key in ("hot_fluid_props", "cold_fluid_props"):
        props = result.outputs.get(key)
        if props is None:
            continue
        rho = props.density_kg_m3
        if rho is not None and (rho < 0.01 or rho > 2000):
            return False, f"{key}.density_kg_m3={rho} outside [0.01, 2000]"
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


_GAS_PHASES = frozenset({"vapor", "condensing", "evaporating"})


def _rule_gas_pressure_required(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R7 — Gas-phase streams require an explicit operating pressure.

    Liquid density is nearly pressure-independent, so a silent 1 atm
    fallback is acceptable. Gas density scales linearly with P, and
    defaulting to 1 atm when the real system runs at 10–100 bar produces
    wildly under-sized velocities and h_shell values. Route these cases
    to the user via ESCALATE instead of returning wrong numbers.
    """
    checks = (
        ("hot", result.outputs.get("hot_phase"), result.outputs.get("hot_pressure_source")),
        ("cold", result.outputs.get("cold_phase"), result.outputs.get("cold_pressure_source")),
    )
    for side, phase, source in checks:
        if phase in _GAS_PHASES and source == "default_1atm":
            return False, (
                f"{side} stream phase='{phase}' but no operating pressure was "
                f"supplied (P_{side}_Pa is None). Silent 1 atm default is unsafe "
                f"for gas-phase service — please provide P_{side}_Pa so density, "
                f"saturation temperature and h_shell are computed correctly."
            )
    return True, None


# ── P2-18: viscosity variation ESCALATE band ────────────────────────────────

def _rule_viscosity_variation_extreme(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R8 — μ_max / μ_min ≥ 10 on either side → ESCALATE.

    Above this band the constant-property correlations (Bell-Delaware,
    Gnielinski) are unreliable; the design needs segmented analysis or
    a fluid swap. Routed straight to ESCALATE since neither AI nor a
    geometry tweak can recover physical fidelity here.
    """
    mu_var = result.outputs.get("viscosity_variation") or {}
    failures: list[str] = []
    for side, info in mu_var.items():
        if not info:
            continue
        ratio = info.get("mu_ratio")
        if ratio is not None and ratio >= _MU_VARIATION_ESCALATE:
            failures.append(f"{side}: μ_ratio={ratio:.1f}× ≥ {_MU_VARIATION_ESCALATE:.0f}×")
    if failures:
        return False, (
            "Extreme viscosity variation across ΔT — "
            + " | ".join(failures)
            + ". Consider splitting into multiple units, segmented "
            "analysis, or a different working fluid."
        )
    return True, None


# ── P2-19: freezing-point ESCALATE rule ─────────────────────────────────────


def _rule_above_freezing_point(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """R9 — Minimum operating temperature must stay above the freezing /
    pour point of each stream. Unresolved freeze points are *not* a
    failure here (they trigger the conditional AI path instead) — only
    a numerically-resolved violation routes to ESCALATE.
    """
    freeze = result.outputs.get("freezing_check") or {}
    failures: list[str] = []
    for side, info in freeze.items():
        if not info:
            continue
        T_freeze = info.get("T_freeze_K")
        T_min = info.get("T_min_K")
        if T_freeze is None or T_min is None:
            continue
        if T_min <= T_freeze:
            failures.append(
                f"{side}: T_min={T_min - 273.15:.1f}°C ≤ "
                f"T_freeze={T_freeze - 273.15:.1f}°C "
                f"(source={info.get('freeze_property_source')})"
            )
    if failures:
        return False, (
            "Operating temperature crosses freezing / pour point — "
            + " | ".join(failures)
            + ". Raise outlet setpoint, switch fluid, or add freeze-"
            "protection additive."
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
    # Missing gas-phase pressure is a user-input gap, not an AI-fixable
    # geometry problem — route straight to ESCALATE.
    register_rule(3, _rule_gas_pressure_required, correctable=False)
    # P2-18 / P2-19 — physical-fidelity guards, both correctable=False.
    register_rule(3, _rule_viscosity_variation_extreme, correctable=False)
    register_rule(3, _rule_above_freezing_point, correctable=False)


register_step3_rules()
