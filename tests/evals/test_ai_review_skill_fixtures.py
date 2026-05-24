from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = Path(__file__).with_name("ai_review_skill_fixtures.json")

STEP_SKILL_FILES = {
    4: "step_04_tema_geometry.md",
    8: "step_08_shell_side_htc.md",
    11: "step_11_area_overdesign.md",
    16: "step_16_final_validation.md",
}

VALID_DECISIONS = {"proceed", "warn", "correct", "escalate"}


def _fixtures() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _skill_text(step_id: int) -> str:
    path = REPO_ROOT / "hx_engine" / "app" / "skills" / STEP_SKILL_FILES[step_id]
    return _normalize(path.read_text(encoding="utf-8"))


def _normalize(text: str) -> str:
    return text.replace("\u2013", "-").replace("\u2014", "-").casefold()


def test_eval_fixture_schema_is_valid() -> None:
    names = []
    for fixture in _fixtures():
        names.append((fixture["step_id"], fixture["name"]))
        assert fixture["step_id"] in STEP_SKILL_FILES
        assert fixture["name"]
        assert isinstance(fixture["input_outputs"], dict)
        assert fixture["expected_decision"] in VALID_DECISIONS
        assert isinstance(fixture["must_include"], list)
        assert isinstance(fixture["must_not_include"], list)

    duplicates = [name for name, count in Counter(names).items() if count > 1]
    assert not duplicates, f"Duplicate eval fixture names: {duplicates}"


def test_each_high_impact_step_has_minimum_eval_coverage() -> None:
    counts = Counter(fixture["step_id"] for fixture in _fixtures())

    assert set(counts) == set(STEP_SKILL_FILES)
    for step_id in STEP_SKILL_FILES:
        assert counts[step_id] >= 5, f"Step {step_id} needs at least 5 eval fixtures"


def test_eval_guardrails_are_present_in_target_skill_files() -> None:
    for fixture in _fixtures():
        skill_text = _skill_text(fixture["step_id"])

        for phrase in fixture["must_include"]:
            assert _normalize(phrase) in skill_text, (
                f"{fixture['name']} missing required skill guardrail: {phrase}"
            )
        for phrase in fixture["must_not_include"]:
            assert _normalize(phrase) not in skill_text, (
                f"{fixture['name']} includes forbidden skill text: {phrase}"
            )


def test_eval_decision_labels_cover_critical_outcomes() -> None:
    by_step = {step_id: set() for step_id in STEP_SKILL_FILES}
    for fixture in _fixtures():
        by_step[fixture["step_id"]].add(fixture["expected_decision"])

    for step_id, decisions in by_step.items():
        assert "escalate" in decisions, f"Step {step_id} must cover escalation"
        assert decisions & {"proceed", "warn", "correct"}, (
            f"Step {step_id} needs at least one non-escalation expectation"
        )