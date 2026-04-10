"""Tests for Piece 8: Layer 2 Validation Rules for Step 4."""

from __future__ import annotations

import pytest

from hx_engine.app.core.validation_rules import check, clear_rules
from hx_engine.app.models.design_state import GeometrySpec
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_04_rules import register_step4_rules


@pytest.fixture(autouse=True)
def _setup_rules():
    """Register Step 4 rules before each test, clear after."""
    clear_rules()
    register_step4_rules()
    yield
    clear_rules()


def _make_result(**overrides) -> StepResult:
    """Build a valid Step 4 result for rule testing."""
    geom = overrides.pop("geometry", GeometrySpec(
        tube_od_m=0.01905,
        tube_id_m=0.014834,
        tube_length_m=4.877,
        pitch_ratio=1.25,
        pitch_layout="triangular",
        n_tubes=324,
        n_passes=2,
        shell_passes=1,
        shell_diameter_m=0.59055,  # 23.25"
        baffle_cut=0.25,
        baffle_spacing_m=0.236,  # 0.4 * shell
    ))
    defaults = dict(
        step_id=4,
        step_name="TEMA Geometry Selection",
        outputs={
            "tema_type": "BEM",
            "geometry": geom,
            "shell_side_fluid": "cold",
            "tema_reasoning": "test",
            "escalation_hints": [],
        },
    )
    # Allow overriding specific output keys
    if "tema_type" in overrides:
        defaults["outputs"]["tema_type"] = overrides.pop("tema_type")
    if "escalation_hints" in overrides:
        defaults["outputs"]["escalation_hints"] = overrides.pop("escalation_hints")
    defaults.update(overrides)
    return StepResult(**defaults)


class TestStep04Rules:
    def test_valid_tema_passes(self):
        """tema_type='BEM' → passes R1."""
        result = _make_result(tema_type="BEM")
        vr = check(4, result)
        assert vr.passed

    def test_invalid_tema_fails(self):
        """tema_type='XYZ' → fails R1."""
        result = _make_result(tema_type="XYZ")
        vr = check(4, result)
        assert not vr.passed
        assert any("XYZ" in e for e in vr.errors)

    def test_tube_id_lt_od_passes(self):
        """ID=0.015, OD=0.019 → passes R2."""
        geom = GeometrySpec(
            tube_od_m=0.01905, tube_id_m=0.015, tube_length_m=4.877,
            pitch_ratio=1.25, shell_diameter_m=0.59,
            baffle_cut=0.25, baffle_spacing_m=0.236,
            n_tubes=100, n_passes=2,
        )
        result = _make_result(geometry=geom)
        vr = check(4, result)
        assert vr.passed

    def test_tube_id_gt_od_fails(self):
        """ID > OD → fails (caught by Pydantic model_validator).
        We test the rule directly with a mock geometry.
        """
        # Bypass Pydantic validation to test the rule
        from hx_engine.app.steps.step_04_rules import _rule_tube_id_lt_od
        result = _make_result()
        result.outputs["geometry"] = type(
            "FakeGeom", (), {
                "tube_id_m": 0.02, "tube_od_m": 0.019,
                "tube_length_m": 4.877, "pitch_ratio": 1.25,
                "shell_diameter_m": 0.59, "baffle_cut": 0.25,
                "baffle_spacing_m": 0.236, "n_tubes": 100,
            },
        )()
        passed, msg = _rule_tube_id_lt_od(4, result)
        assert not passed

    def test_all_positive_passes(self):
        """All fields > 0 → passes R3."""
        result = _make_result()
        vr = check(4, result)
        assert vr.passed

    def test_negative_length_fails(self):
        """tube_length=-1 → fails R3 (caught by Pydantic first,
        but we verify the rule logic).
        """
        from hx_engine.app.steps.step_04_rules import _rule_all_geometry_positive
        result = _make_result()
        result.outputs["geometry"] = type(
            "FakeGeom", (), {
                "tube_od_m": 0.019, "tube_id_m": 0.015,
                "tube_length_m": -1, "pitch_ratio": 1.25,
                "shell_diameter_m": 0.59, "baffle_cut": 0.25,
                "baffle_spacing_m": 0.236, "n_tubes": 100,
            },
        )()
        passed, msg = _rule_all_geometry_positive(4, result)
        assert not passed

    def test_shell_gt_tube_passes(self):
        """shell=0.5, tube_od=0.019 → passes R4."""
        result = _make_result()
        vr = check(4, result)
        assert vr.passed  # default geom has shell >> tube_od

    def test_shell_lt_tube_fails(self):
        """shell < tube_od → fails R4."""
        from hx_engine.app.steps.step_04_rules import _rule_shell_gt_tube
        result = _make_result()
        result.outputs["geometry"] = type(
            "FakeGeom", (), {
                "tube_od_m": 0.019, "tube_id_m": 0.015,
                "tube_length_m": 4.877, "pitch_ratio": 1.25,
                "shell_diameter_m": 0.01, "baffle_cut": 0.25,
                "baffle_spacing_m": 0.005, "n_tubes": 1,
            },
        )()
        passed, msg = _rule_shell_gt_tube(4, result)
        assert not passed

    def test_baffle_spacing_within_range(self):
        """spacing=0.15, shell=0.5 (ratio=0.3) → passes R5, R6."""
        geom = GeometrySpec(
            tube_od_m=0.01905, tube_id_m=0.014834, tube_length_m=4.877,
            pitch_ratio=1.25, shell_diameter_m=0.5,
            baffle_cut=0.25, baffle_spacing_m=0.15,
            n_tubes=100, n_passes=2,
        )
        result = _make_result(geometry=geom)
        vr = check(4, result)
        assert vr.passed

    def test_baffle_too_close_fails(self):
        """spacing=0.05, shell=0.5 (ratio=0.1) → fails R5."""
        from hx_engine.app.steps.step_04_rules import _rule_baffle_spacing_min
        result = _make_result()
        result.outputs["geometry"] = type(
            "FakeGeom", (), {
                "tube_od_m": 0.019, "tube_id_m": 0.015,
                "tube_length_m": 4.877, "pitch_ratio": 1.25,
                "shell_diameter_m": 0.5, "baffle_cut": 0.25,
                "baffle_spacing_m": 0.05, "n_tubes": 100,
            },
        )()
        passed, msg = _rule_baffle_spacing_min(4, result)
        assert not passed

    def test_baffle_too_wide_fails(self):
        """spacing=0.6, shell=0.5 (ratio=1.2) → fails R6."""
        from hx_engine.app.steps.step_04_rules import _rule_baffle_spacing_max
        result = _make_result()
        result.outputs["geometry"] = type(
            "FakeGeom", (), {
                "tube_od_m": 0.019, "tube_id_m": 0.015,
                "tube_length_m": 4.877, "pitch_ratio": 1.25,
                "shell_diameter_m": 0.5, "baffle_cut": 0.25,
                "baffle_spacing_m": 0.6, "n_tubes": 100,
            },
        )()
        passed, msg = _rule_baffle_spacing_max(4, result)
        assert not passed

    def test_pitch_ratio_in_range(self):
        """pitch=1.25 → passes R7."""
        result = _make_result()
        vr = check(4, result)
        assert vr.passed

    def test_BEM_with_high_dt_fails(self):
        """BEM + user preference conflict → fails R9."""
        result = _make_result(
            tema_type="BEM",
            escalation_hints=[{
                "trigger": "user_preference_conflict",
                "recommendation": "User requested BEM but ΔT=120°C",
            }],
        )
        vr = check(4, result)
        assert not vr.passed

    def test_AES_with_high_dt_passes(self):
        """AES + ΔT=120°C → passes R9 (floating head handles expansion)."""
        result = _make_result(tema_type="AES")
        vr = check(4, result)
        assert vr.passed
