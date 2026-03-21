"""Tests for Piece 9: Step 1 Layer 2 validation rules."""

import pytest

from hx_engine.app.core.validation_rules import check, clear_rules
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps.step_01_rules import register_step1_rules


def _make_result(**outputs) -> StepResult:
    return StepResult(step_id=1, step_name="Process Requirements", outputs=outputs)


class TestStep1ValidationRules:

    def setup_method(self):
        clear_rules()
        register_step1_rules()

    # --- Fluid names ---

    def test_both_fluids_present(self):
        r = _make_result(
            hot_fluid_name="crude oil", cold_fluid_name="water",
            T_hot_in_C=150, T_hot_out_C=90, T_cold_in_C=30,
            m_dot_hot_kg_s=50,
        )
        vr = check(1, r)
        assert all("fluid" not in e.lower() for e in vr.errors)

    def test_missing_hot_fluid(self):
        r = _make_result(
            hot_fluid_name=None, cold_fluid_name="water",
            T_hot_in_C=150, T_hot_out_C=90, T_cold_in_C=30,
            m_dot_hot_kg_s=50,
        )
        vr = check(1, r)
        assert not vr.passed
        assert any("hot fluid" in e.lower() for e in vr.errors)

    def test_missing_cold_fluid(self):
        r = _make_result(
            hot_fluid_name="crude oil", cold_fluid_name=None,
            T_hot_in_C=150, T_hot_out_C=90, T_cold_in_C=30,
            m_dot_hot_kg_s=50,
        )
        vr = check(1, r)
        assert not vr.passed
        assert any("cold fluid" in e.lower() for e in vr.errors)

    # --- Temperatures ---

    def test_3_temps_sufficient(self):
        r = _make_result(
            hot_fluid_name="oil", cold_fluid_name="water",
            T_hot_in_C=150, T_hot_out_C=90, T_cold_in_C=30,
            m_dot_hot_kg_s=50,
        )
        vr = check(1, r)
        assert all("temperature" not in e.lower() for e in vr.errors)

    def test_2_temps_insufficient(self):
        r = _make_result(
            hot_fluid_name="oil", cold_fluid_name="water",
            T_hot_in_C=150, T_cold_in_C=30,
            m_dot_hot_kg_s=50,
        )
        vr = check(1, r)
        assert not vr.passed
        assert any("temperature" in e.lower() for e in vr.errors)

    # --- Flow rates ---

    def test_flow_rate_present(self):
        r = _make_result(
            hot_fluid_name="oil", cold_fluid_name="water",
            T_hot_in_C=150, T_hot_out_C=90, T_cold_in_C=30,
            m_dot_hot_kg_s=50,
        )
        vr = check(1, r)
        assert all("flow rate" not in e.lower() for e in vr.errors)

    def test_no_flow_rate(self):
        r = _make_result(
            hot_fluid_name="oil", cold_fluid_name="water",
            T_hot_in_C=150, T_hot_out_C=90, T_cold_in_C=30,
        )
        vr = check(1, r)
        assert not vr.passed
        assert any("flow rate" in e.lower() for e in vr.errors)

    # --- Physics limits ---

    def test_temp_below_absolute_zero(self):
        r = _make_result(
            hot_fluid_name="oil", cold_fluid_name="water",
            T_hot_in_C=-300, T_hot_out_C=90, T_cold_in_C=30,
            m_dot_hot_kg_s=50,
        )
        vr = check(1, r)
        assert not vr.passed
        assert any("absolute zero" in e.lower() for e in vr.errors)

    def test_temp_unreasonably_high(self):
        r = _make_result(
            hot_fluid_name="oil", cold_fluid_name="water",
            T_hot_in_C=2000, T_hot_out_C=90, T_cold_in_C=30,
            m_dot_hot_kg_s=50,
        )
        vr = check(1, r)
        assert not vr.passed
        assert any("1500" in e for e in vr.errors)

    def test_hot_inlet_must_exceed_outlet(self):
        r = _make_result(
            hot_fluid_name="oil", cold_fluid_name="water",
            T_hot_in_C=50, T_hot_out_C=100, T_cold_in_C=30,
            m_dot_hot_kg_s=50,
        )
        vr = check(1, r)
        assert not vr.passed
        assert any("gain" in e.lower() for e in vr.errors)

    def test_cold_out_exceeds_hot_in(self):
        r = _make_result(
            hot_fluid_name="oil", cold_fluid_name="water",
            T_hot_in_C=150, T_hot_out_C=90, T_cold_in_C=30,
            T_cold_out_C=200, m_dot_hot_kg_s=50,
        )
        vr = check(1, r)
        assert not vr.passed
        assert any("cross" in e.lower() or "2nd law" in e.lower() for e in vr.errors)

    def test_all_pass_happy_path(self):
        r = _make_result(
            hot_fluid_name="crude oil", cold_fluid_name="cooling water",
            T_hot_in_C=150, T_hot_out_C=90, T_cold_in_C=30,
            m_dot_hot_kg_s=50,
        )
        vr = check(1, r)
        assert vr.passed
