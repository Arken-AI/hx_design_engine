"""P2-17 — Pitch ratio vs layout consistency rule.

Bug ref:  artifacts/bugs/bug_p2_17_step04_no_pitch_ratio_layout_consistency_check.md
Plan ref: artifacts/plans/implementation_plan_p2_17_step04_pitch_ratio_layout_consistency.md
"""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import GeometrySpec
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_04_rules import (
    SQUARE_LAYOUTS,
    SQUARE_MIN_PITCH_RATIO,
    TRIANGULAR_MIN_PITCH_RATIO,
    _rule_pitch_ratio_layout_consistency,
)


def _result(layout: str | None, pitch_ratio: float | None) -> StepResult:
    geom = GeometrySpec(
        tube_od_m=0.0254, tube_id_m=0.0212,
        tube_length_m=4.0, pitch_ratio=pitch_ratio,
        n_tubes=100, n_passes=2, shell_passes=1,
        shell_diameter_m=0.4, baffle_cut=0.25,
        baffle_spacing_m=0.2, pitch_layout=layout,
    )
    return StepResult(step_id=4, step_name="x", outputs={"geometry": geom})


# ── Constants sanity ─────────────────────────────────────────────

def test_constants_match_documented_floors():
    assert SQUARE_MIN_PITCH_RATIO == 1.25
    assert TRIANGULAR_MIN_PITCH_RATIO == 1.20


def test_square_layouts_includes_canonical_short_form():
    assert "square" in SQUARE_LAYOUTS


# ── Rule behaviour: square layouts (1.25 floor) ──────────────────

def test_square_with_pitch_below_floor_fails():
    ok, msg = _rule_pitch_ratio_layout_consistency(4, _result("square", 1.22))
    assert not ok
    assert "1.25" in msg and "square" in msg


def test_square_with_pitch_at_floor_passes():
    ok, msg = _rule_pitch_ratio_layout_consistency(4, _result("square", 1.25))
    assert ok and msg is None


def test_square_with_pitch_above_floor_passes():
    ok, _ = _rule_pitch_ratio_layout_consistency(4, _result("square", 1.40))
    assert ok


# ── Rule behaviour: triangular layouts (1.20 floor) ─────────────
#
# Note: GeometrySpec.pitch_ratio is field-validated against the TEMA
# range [1.2, 1.5], so a triangular layout cannot be constructed with a
# ratio below 1.20.  The rule's triangular branch is therefore a
# defensive guard for future layouts and the lower-bound failure case
# is not reachable via the public model — only the pass paths are
# exercised here.

def test_triangular_with_pitch_at_floor_passes():
    ok, _ = _rule_pitch_ratio_layout_consistency(4, _result("triangular", 1.20))
    assert ok


def test_triangular_with_pitch_22_passes():
    """1.22 fails for square but passes for triangular — the regression
    case that motivates the layout-aware rule."""
    ok, _ = _rule_pitch_ratio_layout_consistency(4, _result("triangular", 1.22))
    assert ok


# ── Defensive: missing fields ────────────────────────────────────

def test_missing_layout_passes_defensively():
    # Use a valid pitch_ratio (≥ 1.20) so GeometrySpec construction succeeds;
    # the assertion is that the rule short-circuits when layout is None.
    ok, msg = _rule_pitch_ratio_layout_consistency(4, _result(None, 1.30))
    assert ok and msg is None


def test_missing_pitch_passes_defensively():
    ok, msg = _rule_pitch_ratio_layout_consistency(4, _result("square", None))
    assert ok and msg is None
