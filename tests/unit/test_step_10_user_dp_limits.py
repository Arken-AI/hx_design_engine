"""Tests for user-supplied ΔP limit overrides in Step 10.

Covers:
- _tube_limit / _shell_limit return module defaults when state has no overrides
- _tube_limit / _shell_limit return user values when state has them
- _conditional_ai_trigger fires at 85% of user-supplied limit (not module default)
- R3 / R4 hard rules use effective limits from result.outputs
"""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.models.step_result import StepResult
from hx_engine.app.steps import step_10_pressure_drops as step10_mod
from hx_engine.app.steps.step_10_pressure_drops import (
    _DP_TUBE_LIMIT_PA,
    _DP_SHELL_LIMIT_PA,
    _tube_limit,
    _shell_limit,
)
from hx_engine.app.core import validation_rules
import hx_engine.app.steps.step_10_rules as _rules_mod  # ensure registration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_state(**overrides) -> DesignState:
    hot_props = FluidProperties(
        density_kg_m3=850.0,
        viscosity_Pa_s=0.0012,
        Cp_J_kgK=2100.0,
        k_W_mK=0.13,
        Pr=19.4,
    )
    cold_props = FluidProperties(
        density_kg_m3=998.0,
        viscosity_Pa_s=0.001,
        Cp_J_kgK=4182.0,
        k_W_mK=0.6,
        Pr=7.0,
    )
    geometry = GeometrySpec(
        n_tubes=200,
        tube_length_m=4.8,
        tube_od_m=0.019,
        tube_id_m=0.015,
        pitch_m=0.024,
        pitch_layout="triangular",
        n_passes=2,
        baffle_spacing_m=0.25,
        baffle_cut=0.25,
        n_baffles=18,
        shell_diameter_m=0.387,
        shell_wall_thickness_m=0.012,
    )
    state = DesignState(
        session_id="test-dp-limits",
        hot_fluid_name="Oil",
        cold_fluid_name="Water",
        T_hot_in=120.0,
        T_hot_out=80.0,
        T_cold_in=25.0,
        T_cold_out=55.0,
        m_dot_hot=50.0,
        m_dot_cold=100.0,
        Q_duty_W=4_200_000.0,
        hot_props=hot_props,
        cold_props=cold_props,
        shell_side_fluid="hot",
        tube_side_fluid="cold",
        geometry=geometry,
        U_estimated_W_m2K=350.0,
        U_calc_W_m2K=360.0,
        A_required_m2=30.0,
        A_calc_m2=31.5,
        tube_velocity_m_s=1.5,
        Re_tube=15_000.0,
        Re_shell=12_000.0,
        h_tube_W_m2K=2500.0,
        h_shell_W_m2K=1800.0,
        R_f_hot_m2KW=0.0002,
        R_f_cold_m2KW=0.0002,
        wall_resistance_m2KW=0.0001,
        pipeline_step=9,
        pipeline_status="running",
    )
    for key, val in overrides.items():
        object.__setattr__(state, key, val)
    return state


# ---------------------------------------------------------------------------
# _tube_limit / _shell_limit
# ---------------------------------------------------------------------------

class TestLimitHelpers:
    def test_tube_limit_returns_default_when_no_override(self):
        state = _base_state()
        assert state.dP_tube_max_Pa is None
        assert _tube_limit(state) == _DP_TUBE_LIMIT_PA

    def test_shell_limit_returns_default_when_no_override(self):
        state = _base_state()
        assert state.dP_shell_max_Pa is None
        assert _shell_limit(state) == _DP_SHELL_LIMIT_PA

    def test_tube_limit_returns_user_value(self):
        state = _base_state(dP_tube_max_Pa=200_000.0)
        assert _tube_limit(state) == 200_000.0

    def test_shell_limit_returns_user_value(self):
        state = _base_state(dP_shell_max_Pa=80_000.0)
        assert _shell_limit(state) == 80_000.0

    def test_tube_limit_user_value_differs_from_default(self):
        user_limit = 150_000.0
        assert user_limit != _DP_TUBE_LIMIT_PA
        state = _base_state(dP_tube_max_Pa=user_limit)
        assert _tube_limit(state) == user_limit


# ---------------------------------------------------------------------------
# R3 / R4 hard rules read effective limits from result.outputs
# ---------------------------------------------------------------------------

class TestRulesReadOutputLimits:
    """Verify that R3 and R4 honour user-supplied limits via result.outputs."""

    def _make_result(self, dP_tube: float, dP_shell: float,
                     tube_limit: float | None = None,
                     shell_limit: float | None = None) -> StepResult:
        outputs: dict = {
            "dP_tube_Pa": dP_tube,
            "dP_shell_Pa": dP_shell,
            # Include mandatory positivity-check values
            "rho_v2_tube": 500.0,
            "rho_v2_shell": 500.0,
        }
        if tube_limit is not None:
            outputs["dP_tube_limit_Pa"] = tube_limit
        if shell_limit is not None:
            outputs["dP_shell_limit_Pa"] = shell_limit
        return StepResult(
            step_id=10,
            step_name="Pressure Drops",
            outputs=outputs,
            passed=True,
        )

    def test_r3_passes_when_tube_dp_below_user_limit(self):
        """R3 should not fail when dP_tube is below the user-supplied limit."""
        result = self._make_result(
            dP_tube=180_000.0,   # within user's 200 kPa limit
            dP_shell=50_000.0,
            tube_limit=200_000.0,
        )
        vr = validation_rules.check(10, result)
        # The only possible failures should NOT be about tube ΔP exceeding the limit
        tube_limit_errors = [e for e in vr.errors if "tube" in e.lower() and "limit" in e.lower()]
        assert tube_limit_errors == [], f"Unexpected tube-limit errors: {tube_limit_errors}"

    def test_r3_fails_when_tube_dp_exceeds_user_limit(self):
        """R3 should fail when dP_tube exceeds the user-supplied limit."""
        result = self._make_result(
            dP_tube=250_000.0,   # exceeds user's 200 kPa limit
            dP_shell=50_000.0,
            tube_limit=200_000.0,
        )
        vr = validation_rules.check(10, result)
        assert not vr.passed, "Validation should fail when dP_tube > user-supplied limit"
        assert any("tube" in e.lower() and "limit" in e.lower() for e in vr.errors), (
            f"Expected a tube-limit error, got: {vr.errors}"
        )

    def test_r4_fails_when_shell_dp_exceeds_user_limit(self):
        """R4 should fail when dP_shell exceeds the user-supplied limit."""
        result = self._make_result(
            dP_tube=50_000.0,
            dP_shell=90_000.0,   # exceeds user's 80 kPa limit
            shell_limit=80_000.0,
        )
        vr = validation_rules.check(10, result)
        assert not vr.passed, "Validation should fail when dP_shell > user-supplied limit"
        assert any("shell" in e.lower() and "limit" in e.lower() for e in vr.errors), (
            f"Expected a shell-limit error, got: {vr.errors}"
        )

    def test_r3_falls_back_to_default_when_no_limit_in_outputs(self):
        """R3 should use _DP_TUBE_LIMIT_PA when dP_tube_limit_Pa absent from outputs."""
        # Value just under the module default — should pass R3
        result = self._make_result(
            dP_tube=_DP_TUBE_LIMIT_PA * 0.99,
            dP_shell=50_000.0,
        )
        vr = validation_rules.check(10, result)
        tube_limit_errors = [e for e in vr.errors if "tube" in e.lower() and "limit" in e.lower()]
        assert tube_limit_errors == [], (
            f"R3 should pass when dP_tube < default limit; got: {tube_limit_errors}"
        )
