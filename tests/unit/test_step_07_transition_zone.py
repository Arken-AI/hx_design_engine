"""P2-22 — Transition-zone band is consistent across warning, hint and AI trigger.

Bug ref:  artifacts/bugs/bug_p2_22_step07_transition_zone_boundary_inconsistency.md
Plan ref: artifacts/plans/implementation_plan_p2_22_step07_transition_zone_standardisation.md
"""

from __future__ import annotations

import pytest

from hx_engine.app.steps.step_07_tube_side_h import (
    _TRANSITION_RE_HIGH,
    _TRANSITION_RE_LOW,
    _flag_transition_zone,
)


@pytest.mark.parametrize(
    "Re,expected",
    [
        (1500, False),                # laminar
        (_TRANSITION_RE_LOW, False),  # boundary, strict <
        (3500, True),                 # transition (was already flagged)
        (7000, True),                 # regression target — silent before P2-22
        (_TRANSITION_RE_HIGH, False), # boundary, strict <
        (11000, False),               # turbulent
        (None, False),                # defensive
    ],
)
def test_flag_transition_zone(Re, expected):
    assert _flag_transition_zone(Re) is expected


def test_band_constants_match_gnielinski_validity():
    """Engineering invariant: Gnielinski valid for Re ≥ 10000."""
    assert _TRANSITION_RE_LOW == 2300
    assert _TRANSITION_RE_HIGH == 10000
