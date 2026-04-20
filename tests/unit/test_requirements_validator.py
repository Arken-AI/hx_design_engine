"""Unit tests for requirements_validator — Layer 1 + Layer 2 rules."""

from __future__ import annotations

import pytest

from hx_engine.app.core.requirements_validator import validate_requirements


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base() -> dict:
    """Minimal valid input dict."""
    return {
        "hot_fluid_name": "crude oil",
        "cold_fluid_name": "water",
        "T_hot_in_C": 150.0,
        "T_hot_out_C": 80.0,
        "T_cold_in_C": 25.0,
        "T_cold_out_C": 50.0,
        "m_dot_hot_kg_s": 10.0,
    }


def _error_fields(result) -> list[str]:
    return [e.field for e in result.errors]


def _error_messages(result) -> list[str]:
    return [e.message for e in result.errors]


# ---------------------------------------------------------------------------
# Layer 1 — Required fields
# ---------------------------------------------------------------------------

class TestLayer1RequiredFields:

    def test_valid_base_passes(self):
        result = validate_requirements(_base())
        assert result.valid

    def test_missing_hot_fluid(self):
        d = _base()
        del d["hot_fluid_name"]
        result = validate_requirements(d)
        assert not result.valid
        assert "hot_fluid_name" in _error_fields(result)

    def test_empty_hot_fluid(self):
        d = _base()
        d["hot_fluid_name"] = "  "
        result = validate_requirements(d)
        assert not result.valid
        assert "hot_fluid_name" in _error_fields(result)

    def test_missing_cold_fluid(self):
        d = _base()
        del d["cold_fluid_name"]
        result = validate_requirements(d)
        assert not result.valid
        assert "cold_fluid_name" in _error_fields(result)

    def test_missing_T_hot_in(self):
        d = _base()
        del d["T_hot_in_C"]
        result = validate_requirements(d)
        assert not result.valid
        assert "T_hot_in_C" in _error_fields(result)

    def test_missing_T_cold_in(self):
        d = _base()
        del d["T_cold_in_C"]
        result = validate_requirements(d)
        assert not result.valid
        assert "T_cold_in_C" in _error_fields(result)

    def test_missing_m_dot_hot(self):
        d = _base()
        del d["m_dot_hot_kg_s"]
        result = validate_requirements(d)
        assert not result.valid
        assert "m_dot_hot_kg_s" in _error_fields(result)

    def test_multiple_missing_fields(self):
        result = validate_requirements({"user_id": "x"})
        fields = _error_fields(result)
        assert "hot_fluid_name" in fields
        assert "cold_fluid_name" in fields
        assert "T_hot_in_C" in fields
        assert "T_cold_in_C" in fields
        assert "m_dot_hot_kg_s" in fields


# ---------------------------------------------------------------------------
# Layer 1 — Range checks
# ---------------------------------------------------------------------------

class TestLayer1RangeChecks:

    def test_temp_below_min(self):
        d = _base()
        d["T_cold_in_C"] = -100.0
        result = validate_requirements(d)
        assert not result.valid
        assert "T_cold_in_C" in _error_fields(result)

    def test_temp_above_max(self):
        d = _base()
        d["T_hot_in_C"] = 1500.0
        result = validate_requirements(d)
        assert not result.valid
        assert "T_hot_in_C" in _error_fields(result)

    def test_temp_at_boundary_passes(self):
        d = _base()
        d["T_hot_in_C"] = 1000.0
        d["T_hot_out_C"] = 80.0
        result = validate_requirements(d)
        assert result.valid

    def test_zero_flow_rate(self):
        d = _base()
        d["m_dot_hot_kg_s"] = 0.0
        result = validate_requirements(d)
        assert not result.valid
        assert "m_dot_hot_kg_s" in _error_fields(result)

    def test_negative_flow_rate(self):
        d = _base()
        d["m_dot_cold_kg_s"] = -5.0
        result = validate_requirements(d)
        assert not result.valid
        assert "m_dot_cold_kg_s" in _error_fields(result)

    def test_zero_pressure(self):
        d = _base()
        d["P_hot_Pa"] = 0.0
        result = validate_requirements(d)
        assert not result.valid
        assert "P_hot_Pa" in _error_fields(result)

    def test_negative_pressure(self):
        d = _base()
        d["P_cold_Pa"] = -101325.0
        result = validate_requirements(d)
        assert not result.valid
        assert "P_cold_Pa" in _error_fields(result)


# ---------------------------------------------------------------------------
# Layer 1 — Optional field validation
# ---------------------------------------------------------------------------

class TestLayer1OptionalFields:

    def test_invalid_tema_preference(self):
        d = _base()
        d["tema_preference"] = "XYZ"
        result = validate_requirements(d)
        assert not result.valid
        assert "tema_preference" in _error_fields(result)

    @pytest.mark.parametrize("tema", ["AES", "BEM", "AEU", "AEP", "AEW"])
    def test_valid_tema_preferences(self, tema: str):
        d = _base()
        d["tema_preference"] = tema
        result = validate_requirements(d)
        assert result.valid, f"TEMA type {tema} should be valid"

    def test_unknown_fluid_produces_warning_not_error(self):
        d = _base()
        d["hot_fluid_name"] = "dragon oil"
        result = validate_requirements(d)
        # Should be valid (unknown fluid is a warning, not error)
        assert result.valid
        assert any("dragon oil" in w.message for w in result.warnings)

    def test_known_fluid_no_warning(self):
        d = _base()  # crude oil + water are both known
        result = validate_requirements(d)
        assert result.valid
        fluid_warnings = [w for w in result.warnings if "not in known fluid list" in w.message]
        assert len(fluid_warnings) == 0


# ---------------------------------------------------------------------------
# Layer 2 — Physics feasibility
# ---------------------------------------------------------------------------

class TestLayer2PhysicsFeasibility:

    def test_hot_out_above_hot_in(self):
        d = _base()
        d["T_hot_out_C"] = 200.0  # > T_hot_in 150
        result = validate_requirements(d)
        assert not result.valid
        assert "T_hot_out_C" in _error_fields(result)
        assert "must cool" in _error_messages(result)[0]

    def test_cold_out_below_cold_in(self):
        d = _base()
        d["T_cold_out_C"] = 10.0  # < T_cold_in 25
        result = validate_requirements(d)
        assert not result.valid
        assert "T_cold_out_C" in _error_fields(result)

    def test_temperature_cross_cold_out_above_hot_in(self):
        d = _base()
        d["T_cold_out_C"] = 160.0  # > T_hot_in 150
        result = validate_requirements(d)
        assert not result.valid
        assert any("cross" in m.lower() for m in _error_messages(result))

    def test_temperature_cross_cold_in_above_hot_out(self):
        d = _base()
        d["T_cold_in_C"] = 90.0   # > T_hot_out 80
        result = validate_requirements(d)
        assert not result.valid
        assert any("cross" in m.lower() for m in _error_messages(result))

    def test_min_approach_too_small(self):
        d = _base()
        d["T_hot_out_C"] = 52.0   # T_hot_out - T_cold_in = 52 - 25 = 27 OK
        d["T_cold_out_C"] = 50.0  # T_hot_in - T_cold_out = 150 - 50 = 100 OK
        # Make approach tiny: T_hot_out = 26, T_cold_in = 25
        d["T_hot_out_C"] = 26.0
        result = validate_requirements(d)
        # delta2 = 26 - 25 = 1°C < 3°C
        assert not result.valid
        assert any("approach" in m.lower() for m in _error_messages(result))

    def test_approach_exactly_at_minimum_passes(self):
        d = _base()
        d["T_hot_out_C"] = 28.0   # T_hot_out - T_cold_in = 28 - 25 = 3°C exactly
        d["T_cold_out_C"] = 45.0
        result = validate_requirements(d)
        assert result.valid

    def test_high_r_factor_produces_warning(self):
        d = _base()
        d["T_hot_in_C"] = 300.0
        d["T_hot_out_C"] = 100.0   # ΔT_hot = 200
        d["T_cold_in_C"] = 20.0
        d["T_cold_out_C"] = 30.0   # ΔT_cold = 10, R = 20 ... boundary
        # Make R clearly > 20
        d["T_cold_out_C"] = 29.0   # ΔT_cold = 9, R = 22.2
        result = validate_requirements(d)
        assert result.valid  # warning, not error
        assert any("R=" in w.message for w in result.warnings)

    def test_underdetermined_no_optional_temps_or_flows(self):
        d = {
            "hot_fluid_name": "crude oil",
            "cold_fluid_name": "water",
            "T_hot_in_C": 150.0,
            "T_cold_in_C": 25.0,
            "m_dot_hot_kg_s": 10.0,
            # No T_hot_out, T_cold_out, or m_dot_cold
        }
        result = validate_requirements(d)
        assert not result.valid
        assert any("underdetermined" in m.lower() for m in _error_messages(result))

    def test_only_T_hot_out_provided_is_underdetermined(self):
        """T_hot_out alone is NOT sufficient — cold side still underdetermined.
        Step 2 can compute Q from the hot side, but cannot back-calculate
        T_cold_out without m_dot_cold_kg_s.
        """
        d = {
            "hot_fluid_name": "crude oil",
            "cold_fluid_name": "water",
            "T_hot_in_C": 150.0,
            "T_hot_out_C": 80.0,
            "T_cold_in_C": 25.0,
            "m_dot_hot_kg_s": 10.0,
        }
        result = validate_requirements(d)
        assert not result.valid
        assert any("cold side underdetermined" in m.lower() for m in _error_messages(result))

    def test_T_hot_out_plus_T_cold_out_is_sufficient(self):
        d = {
            "hot_fluid_name": "crude oil",
            "cold_fluid_name": "water",
            "T_hot_in_C": 150.0,
            "T_hot_out_C": 80.0,
            "T_cold_in_C": 25.0,
            "T_cold_out_C": 60.0,
            "m_dot_hot_kg_s": 10.0,
        }
        result = validate_requirements(d)
        assert result.valid

    def test_T_hot_out_plus_m_dot_cold_is_sufficient(self):
        d = {
            "hot_fluid_name": "crude oil",
            "cold_fluid_name": "water",
            "T_hot_in_C": 150.0,
            "T_hot_out_C": 80.0,
            "T_cold_in_C": 25.0,
            "m_dot_hot_kg_s": 10.0,
            "m_dot_cold_kg_s": 8.0,
        }
        result = validate_requirements(d)
        assert result.valid

    def test_only_m_dot_cold_provided_is_sufficient(self):
        d = {
            "hot_fluid_name": "crude oil",
            "cold_fluid_name": "water",
            "T_hot_in_C": 150.0,
            "T_cold_in_C": 25.0,
            "m_dot_hot_kg_s": 10.0,
            "m_dot_cold_kg_s": 8.0,
        }
        result = validate_requirements(d)
        assert result.valid
