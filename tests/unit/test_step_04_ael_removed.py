"""P2-13 — AEL must not appear in any selectable TEMA-type set.

Bug ref: artifacts/bugs/bug_p2_13_step04_ael_dead_code_in_tema_selection.md
Plan ref: artifacts/plans/implementation_plan_p2_13_step04_ael_dead_code_removal.md
"""

from __future__ import annotations

from hx_engine.app.core.requirements_validator import _VALID_TEMA
from hx_engine.app.steps.step_04_tema_geometry import VALID_TEMA_TYPES


def test_ael_excluded_from_step_04_valid_set():
    assert "AEL" not in VALID_TEMA_TYPES


def test_remaining_five_types_present_in_step_04():
    assert VALID_TEMA_TYPES == frozenset({"BEM", "AES", "AEP", "AEU", "AEW"})


def test_ael_excluded_from_requirements_validator_set():
    assert "AEL" not in _VALID_TEMA
    assert _VALID_TEMA == {"AES", "BEM", "AEU", "AEP", "AEW"}
