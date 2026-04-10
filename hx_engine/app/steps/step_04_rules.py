"""Layer 2 validation rules for Step 4 (TEMA Type + Initial Geometry).

These are hard engineering rules that AI **cannot** override.
Registered at module level via ``register_step4_rules()``.
"""

from __future__ import annotations

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.design_state import GeometrySpec
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_04_tema_geometry import VALID_TEMA_TYPES


# ---------------------------------------------------------------------------
# R1 — Valid TEMA type
# ---------------------------------------------------------------------------

def _rule_valid_tema_type(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """TEMA type must be in the known set."""
    tt = result.outputs.get("tema_type")
    if tt is None:
        return False, "tema_type is missing from outputs"
    if tt not in VALID_TEMA_TYPES:
        return False, (
            f"tema_type='{tt}' is not a valid TEMA designation. "
            f"Must be one of {sorted(VALID_TEMA_TYPES)}"
        )
    return True, None


# ---------------------------------------------------------------------------
# R2 — Tube ID < Tube OD
# ---------------------------------------------------------------------------

def _rule_tube_id_lt_od(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Tube inner diameter must be less than outer diameter."""
    geom: GeometrySpec | None = result.outputs.get("geometry")
    if geom is None:
        return False, "geometry is missing from outputs"
    if geom.tube_id_m is not None and geom.tube_od_m is not None:
        if geom.tube_id_m >= geom.tube_od_m:
            return False, (
                f"tube_id_m ({geom.tube_id_m}) >= tube_od_m ({geom.tube_od_m})"
                f" — physically impossible"
            )
    return True, None


# ---------------------------------------------------------------------------
# R3 — All geometry values positive
# ---------------------------------------------------------------------------

def _rule_all_geometry_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Every numeric geometry field must be > 0."""
    geom: GeometrySpec | None = result.outputs.get("geometry")
    if geom is None:
        return False, "geometry is missing from outputs"
    for field_name in (
        "tube_od_m", "tube_id_m", "tube_length_m", "pitch_ratio",
        "shell_diameter_m", "baffle_cut", "baffle_spacing_m",
    ):
        val = getattr(geom, field_name, None)
        if val is not None and val <= 0:
            return False, f"geometry.{field_name}={val} is not positive"
    if geom.n_tubes is not None and geom.n_tubes < 1:
        return False, f"geometry.n_tubes={geom.n_tubes} must be ≥ 1"
    return True, None


# ---------------------------------------------------------------------------
# R4 — Shell diameter > tube OD
# ---------------------------------------------------------------------------

def _rule_shell_gt_tube(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Shell diameter must be larger than tube OD."""
    geom: GeometrySpec | None = result.outputs.get("geometry")
    if geom is None:
        return True, None  # already caught by R3
    if geom.shell_diameter_m is not None and geom.tube_od_m is not None:
        if geom.shell_diameter_m <= geom.tube_od_m:
            return False, (
                f"shell_diameter_m ({geom.shell_diameter_m}) <= "
                f"tube_od_m ({geom.tube_od_m}) — tubes cannot fit"
            )
    return True, None


# ---------------------------------------------------------------------------
# R5 — Baffle spacing >= 0.2 × shell diameter
# ---------------------------------------------------------------------------

def _rule_baffle_spacing_min(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Baffle spacing must be at least 20% of shell diameter."""
    geom: GeometrySpec | None = result.outputs.get("geometry")
    if geom is None:
        return True, None
    if geom.baffle_spacing_m is not None and geom.shell_diameter_m is not None:
        min_spacing = 0.2 * geom.shell_diameter_m
        if geom.baffle_spacing_m < min_spacing - 1e-6:
            return False, (
                f"baffle_spacing_m ({geom.baffle_spacing_m:.4f}) < "
                f"0.2 × shell_diameter ({min_spacing:.4f}) — "
                f"too close for fabrication"
            )
    return True, None


# ---------------------------------------------------------------------------
# R6 — Baffle spacing <= 1.0 × shell diameter
# ---------------------------------------------------------------------------

def _rule_baffle_spacing_max(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Baffle spacing must not exceed shell diameter."""
    geom: GeometrySpec | None = result.outputs.get("geometry")
    if geom is None:
        return True, None
    if geom.baffle_spacing_m is not None and geom.shell_diameter_m is not None:
        max_spacing = 1.0 * geom.shell_diameter_m
        if geom.baffle_spacing_m > max_spacing + 1e-6:
            return False, (
                f"baffle_spacing_m ({geom.baffle_spacing_m:.4f}) > "
                f"shell_diameter ({max_spacing:.4f}) — "
                f"spacing too wide, poor flow distribution"
            )
    return True, None


# ---------------------------------------------------------------------------
# R7 — Pitch ratio in [1.2, 1.5]
# ---------------------------------------------------------------------------

def _rule_pitch_ratio_range(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Pitch ratio must be in TEMA range [1.2, 1.5]."""
    geom: GeometrySpec | None = result.outputs.get("geometry")
    if geom is None:
        return True, None
    pr = geom.pitch_ratio
    if pr is not None and (pr < 1.2 or pr > 1.5):
        return False, (
            f"pitch_ratio={pr} outside TEMA range [1.2, 1.5]"
        )
    return True, None


# ---------------------------------------------------------------------------
# R8 — N_tubes >= 1
# ---------------------------------------------------------------------------

def _rule_n_tubes_positive(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """Must have at least 1 tube."""
    geom: GeometrySpec | None = result.outputs.get("geometry")
    if geom is None:
        return True, None
    if geom.n_tubes is not None and geom.n_tubes < 1:
        return False, f"n_tubes={geom.n_tubes} must be ≥ 1"
    return True, None


# ---------------------------------------------------------------------------
# R9 — Fixed tubesheet (BEM) ΔT check
# ---------------------------------------------------------------------------

def _rule_bem_delta_t(
    step_id: int, result: StepResult,
) -> tuple[bool, str | None]:
    """BEM must not be used when max ΔT > 50°C.

    This rule uses the tema_type from outputs and checks against
    temperature data stored in the result context.
    """
    tt = result.outputs.get("tema_type")
    if tt != "BEM":
        return True, None

    # Check for temperature data in escalation hints or reasoning
    hints = result.outputs.get("escalation_hints", [])
    for hint in hints:
        if hint.get("trigger") == "user_preference_conflict":
            return False, (
                "BEM (fixed tubesheet) with large ΔT — "
                "thermal expansion risk. " + hint.get("recommendation", "")
            )

    return True, None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_step4_rules() -> None:
    """Register all Layer 2 rules for step_id=4."""
    register_rule(4, _rule_valid_tema_type)
    register_rule(4, _rule_tube_id_lt_od)
    register_rule(4, _rule_all_geometry_positive)
    register_rule(4, _rule_shell_gt_tube)
    register_rule(4, _rule_baffle_spacing_min)
    register_rule(4, _rule_baffle_spacing_max)
    register_rule(4, _rule_pitch_ratio_range)
    register_rule(4, _rule_n_tubes_positive)
    register_rule(4, _rule_bem_delta_t)


register_step4_rules()
