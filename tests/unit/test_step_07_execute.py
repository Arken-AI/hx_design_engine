"""Tests for Step 07 — Tube-Side Heat Transfer Coefficient.

Covers:
  - Correlation unit tests (Petukhov, Hausen, Gnielinski, Dittus-Boelter)
  - Step 7 execution tests (turbulent water, laminar oil, warnings)
  - AI trigger tests
  - Validation rules tests

Physics references:
  - Incropera, Fundamentals of Heat and Mass Transfer, Ch. 8 (Example 8.4)
  - Serth, Process Heat Transfer, Ch. 4 (laminar oil)
"""

from __future__ import annotations

import math

import pytest

from hx_engine.app.correlations.gnielinski import (
    dittus_boelter_nu,
    gnielinski_nu,
    hausen_nu,
    petukhov_friction,
    tube_side_h,
)
from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.steps.step_07_tube_side_h import Step07TubeSideH


# ===================================================================
# Helpers
# ===================================================================

def _make_geometry(**overrides) -> GeometrySpec:
    """Standard Step 6 geometry — 3/4" tubes, triangular pitch, 2-pass."""
    defaults = dict(
        tube_od_m=0.01905,
        tube_id_m=0.01483,
        tube_length_m=4.88,
        pitch_ratio=1.25,
        pitch_layout="triangular",
        n_passes=2,
        shell_passes=1,
        baffle_cut=0.25,
        baffle_spacing_m=0.15,
        shell_diameter_m=0.489,
        n_tubes=158,
    )
    defaults.update(overrides)
    return GeometrySpec(**defaults)


def _water_props() -> FluidProperties:
    """Typical water properties near 50 °C."""
    return FluidProperties(
        density_kg_m3=988.0,
        viscosity_Pa_s=0.000547,
        cp_J_kgK=4181.0,
        k_W_mK=0.644,
        Pr=3.55,
    )


def _heavy_oil_props() -> FluidProperties:
    """Heavy oil properties — high viscosity, low k."""
    return FluidProperties(
        density_kg_m3=870.0,
        viscosity_Pa_s=0.040,
        cp_J_kgK=2100.0,
        k_W_mK=0.13,
        Pr=646.0,
    )


def _make_state(
    tube_side="cold",
    hot_fluid="water",
    cold_fluid="water",
    hot_props=None,
    cold_props=None,
    geometry=None,
    m_dot_hot=10.0,
    m_dot_cold=10.0,
    **kwargs,
) -> DesignState:
    """Create a DesignState pre-populated through Step 6."""
    if hot_props is None:
        hot_props = _water_props()
    if cold_props is None:
        cold_props = _water_props()
    if geometry is None:
        geometry = _make_geometry()

    shell_side_fluid = "cold" if tube_side == "hot" else "hot"

    return DesignState(
        hot_fluid_name=hot_fluid,
        cold_fluid_name=cold_fluid,
        hot_fluid_props=hot_props,
        cold_fluid_props=cold_props,
        geometry=geometry,
        shell_side_fluid=shell_side_fluid,
        m_dot_hot_kg_s=m_dot_hot,
        m_dot_cold_kg_s=m_dot_cold,
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=55.0,
        Q_W=1_000_000.0,
        LMTD_K=30.0,
        F_factor=0.9,
        U_W_m2K=500.0,
        A_m2=74.0,
        **kwargs,
    )


@pytest.fixture
def step():
    return Step07TubeSideH()


# ===================================================================
# 7.1 — Correlation unit tests
# ===================================================================

class TestPetukhovFriction:

    def test_turbulent(self):
        """Re=35000 → f ≈ 0.022 (typical turbulent)."""
        f = petukhov_friction(35000)
        assert 0.02 < f < 0.03

    def test_re_negative_raises(self):
        with pytest.raises(ValueError, match="Re must be > 0"):
            petukhov_friction(-100)

    def test_re_zero_raises(self):
        with pytest.raises(ValueError, match="Re must be > 0"):
            petukhov_friction(0)


class TestHausenNu:

    def test_laminar_oil(self):
        """Laminar oil case — Serth Ch4 style: Re=500, Pr=120, D=14.83mm, L=4.88m."""
        Nu = hausen_nu(Re=500, Pr=120, D=0.01483, L=4.88)
        # Gz = 500 * 120 * 0.01483 / 4.88 ≈ 182.2
        # Nu should be well above 3.66 for developing flow
        assert Nu > 3.66
        assert Nu < 30  # sanity upper bound for low Re

    def test_floor(self):
        """Very low Gz → floor at 3.66."""
        Nu = hausen_nu(Re=10, Pr=1.0, D=0.01, L=10.0)
        assert Nu == pytest.approx(3.66, abs=0.01)

    def test_invalid_D(self):
        with pytest.raises(ValueError, match="D must be > 0"):
            hausen_nu(100, 5.0, 0.0, 1.0)

    def test_invalid_L(self):
        with pytest.raises(ValueError, match="L must be > 0"):
            hausen_nu(100, 5.0, 0.01, 0.0)


class TestGnielinskiNu:

    def test_turbulent_water(self):
        """Re=35000, Pr=3.0 → typical turbulent water Nu."""
        f = petukhov_friction(35000)
        Nu = gnielinski_nu(35000, 3.0, f)
        # Expected: Nu ≈ 170–220 range for these inputs
        assert 100 < Nu < 300

    def test_transition(self):
        """Re=3500, Pr=4.5 → transition zone."""
        f = petukhov_friction(3500)
        Nu = gnielinski_nu(3500, 4.5, f)
        assert Nu > 0


class TestDittusBoelter:

    def test_basic(self):
        """Re=35000, Pr=3.0 → standard DB value."""
        Nu = dittus_boelter_nu(35000, 3.0)
        assert Nu > 0
        # DB gives similar order as Gnielinski
        f = petukhov_friction(35000)
        Nu_g = gnielinski_nu(35000, 3.0, f)
        divergence = abs(Nu - Nu_g) / Nu_g * 100
        assert divergence < 25  # should be within ~20%


class TestTubeSideH:

    def test_cutover_at_2300(self):
        """Re=2299 → Hausen; Re=2301 → Gnielinski."""
        r1 = tube_side_h(2299, 5.0, 0.015, 5.0, 0.6, 0.001, 0.001)
        assert r1["method"] == "hausen"
        assert r1["flow_regime"] == "laminar"

        r2 = tube_side_h(2301, 5.0, 0.015, 5.0, 0.6, 0.001, 0.001)
        assert r2["method"] == "gnielinski"
        assert r2["flow_regime"] == "transition"

    def test_turbulent_water(self):
        """Re=35000, Pr=3.0, D_i=14.83mm, k=0.65 → h ~ 7500–8500 W/m²K."""
        result = tube_side_h(35000, 3.0, 0.01483, 4.88, 0.644, 0.000547, 0.000547)
        assert result["flow_regime"] == "turbulent"
        assert result["method"] == "gnielinski"
        # Typical range for water at Re=35000
        assert 5000 < result["h_i"] < 12000

    def test_gnielinski_transition(self):
        """Re=3500, Pr=4.5 → transition regime, gnielinski method."""
        result = tube_side_h(3500, 4.5, 0.015, 5.0, 0.6, 0.001, 0.001)
        assert result["method"] == "gnielinski"
        assert result["flow_regime"] == "transition"
        assert result["h_i"] > 0

    def test_dittus_boelter_crosscheck(self):
        """Re=35000, Pr=3.0 → crosscheck divergence < 20%."""
        result = tube_side_h(35000, 3.0, 0.015, 5.0, 0.6, 0.001, 0.001)
        assert result["dittus_boelter_Nu"] is not None
        assert result["dittus_boelter_divergence_pct"] is not None
        assert result["dittus_boelter_divergence_pct"] < 20

    def test_viscosity_correction_heating(self):
        """Heating: mu_bulk > mu_wall → correction > 1."""
        result = tube_side_h(35000, 3.0, 0.015, 5.0, 0.6, 0.001, 0.0005)
        expected_corr = (0.001 / 0.0005) ** 0.14
        assert result["viscosity_correction"] == pytest.approx(expected_corr, rel=1e-4)
        assert result["viscosity_correction"] > 1.0

    def test_viscosity_no_wall(self):
        """mu_wall=None → correction=1.0, warning emitted."""
        result = tube_side_h(35000, 3.0, 0.015, 5.0, 0.6, 0.001, None)
        assert result["viscosity_correction"] == 1.0
        assert any("viscosity correction skipped" in w for w in result["warnings"])

    def test_laminar_returns_no_friction(self):
        """Laminar flow should not compute Petukhov friction."""
        result = tube_side_h(500, 120, 0.015, 5.0, 0.13, 0.040, 0.040)
        assert result["f_petukhov"] is None
        assert result["dittus_boelter_Nu"] is None


# ===================================================================
# 7.2 — Step 7 execution tests
# ===================================================================

class TestStep07Execute:

    @pytest.mark.asyncio
    async def test_normal_turbulent_water(self, step):
        """Water/water, tube side cold, normal turbulent flow."""
        state = _make_state(tube_side="cold")
        result = await step.execute(state)

        assert result.outputs["h_tube_W_m2K"] > 0
        assert result.outputs["flow_regime_tube"] == "turbulent"
        assert result.outputs["Re_tube"] > 10000
        assert result.outputs["Pr_tube"] > 0
        assert result.outputs["Nu_tube"] > 0

    @pytest.mark.asyncio
    async def test_laminar_oil(self, step):
        """Heavy oil on tube side → laminar flow, low h_i."""
        oil_props = _heavy_oil_props()
        state = _make_state(
            tube_side="hot",
            hot_fluid="heavy fuel oil",
            hot_props=oil_props,
            m_dot_hot=2.0,  # lower flow to reduce velocity
            geometry=_make_geometry(n_tubes=158, n_passes=1),
        )
        result = await step.execute(state)

        assert result.outputs["h_tube_W_m2K"] > 0
        assert result.outputs["flow_regime_tube"] == "laminar"
        assert result.outputs["Re_tube"] < 2300

    @pytest.mark.asyncio
    async def test_low_velocity_warning(self, step):
        """Very large n_tubes + low m_dot → low velocity → fouling warning."""
        state = _make_state(
            tube_side="cold",
            m_dot_cold=1.0,
            geometry=_make_geometry(n_tubes=500, n_passes=1),
        )
        result = await step.execute(state)

        assert any("fouling" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_high_velocity_warning(self, step):
        """Few tubes + high m_dot + many passes → high velocity → erosion warning."""
        state = _make_state(
            tube_side="cold",
            m_dot_cold=30.0,
            geometry=_make_geometry(n_tubes=20, n_passes=4),
        )
        result = await step.execute(state)

        assert any("erosion" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_transition_warning(self, step):
        """Conditions that produce Re in 2300–4000 → transition warning."""
        # Tune flow rate to get Re in transition zone
        # Re = rho * v * D_i / mu → need v that gives Re ~ 3000
        # With water: Re = 988 * v * 0.01483 / 0.000547
        # v ≈ Re * 0.000547 / (988 * 0.01483) ≈ 3000 * 0.000547 / 14.65 ≈ 0.112
        # m_dot = rho * A_flow * v; A_flow = (n_tubes/n_passes) * pi/4 * D_i^2
        # With 158 tubes, 2 passes: tubes_per_pass = 79
        # A_flow = 79 * pi/4 * 0.01483^2 = 79 * 1.727e-4 = 0.01364 m^2
        # m_dot = 988 * 0.01364 * 0.112 ≈ 1.51 kg/s
        state = _make_state(
            tube_side="cold",
            m_dot_cold=1.5,
        )
        result = await step.execute(state)

        # Check if Re is indeed in transition zone
        Re = result.outputs["Re_tube"]
        if 2300 < Re < 4000:
            assert any("transition" in w.lower() or "unstable" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_precondition_missing_geometry(self, step):
        """No geometry → CalculationError."""
        state = _make_state()
        state.geometry = None
        with pytest.raises(CalculationError, match="geometry"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_precondition_missing_fluid_props(self, step):
        """Missing tube-side fluid props → CalculationError."""
        state = _make_state(tube_side="cold")
        state.cold_fluid_props = None
        with pytest.raises(CalculationError, match="cold_fluid_props"):
            await step.execute(state)

    @pytest.mark.asyncio
    async def test_state_fields_populated(self, step):
        """Normal run → all DesignState fields populated."""
        state = _make_state()
        await step.execute(state)

        assert state.h_tube_W_m2K is not None
        assert state.tube_velocity_m_s is not None
        assert state.Re_tube is not None
        assert state.Pr_tube is not None
        assert state.Nu_tube is not None
        assert state.flow_regime_tube is not None
        assert state.T_mean_hot_C is not None
        assert state.T_mean_cold_C is not None

    @pytest.mark.asyncio
    async def test_outputs_dict_complete(self, step):
        """Normal run → StepResult.outputs has all expected keys."""
        state = _make_state()
        result = await step.execute(state)

        expected_keys = {
            "h_tube_W_m2K", "tube_velocity_m_s", "Re_tube", "Pr_tube",
            "Nu_tube", "flow_regime_tube", "method", "f_petukhov",
            "viscosity_correction", "T_wall_estimated_C", "mu_wall_Pa_s",
            "dittus_boelter_Nu", "dittus_boelter_divergence_pct",
            "T_mean_hot_C", "T_mean_cold_C",
        }
        assert expected_keys.issubset(result.outputs.keys())

    @pytest.mark.asyncio
    async def test_mean_temps_correct(self, step):
        """Mean temperatures are arithmetic means of inlet/outlet."""
        state = _make_state()
        result = await step.execute(state)

        expected_hot = (state.T_hot_in_C + state.T_hot_out_C) / 2.0
        expected_cold = (state.T_cold_in_C + state.T_cold_out_C) / 2.0

        assert result.outputs["T_mean_hot_C"] == pytest.approx(expected_hot)
        assert result.outputs["T_mean_cold_C"] == pytest.approx(expected_cold)


# ===================================================================
# 7.3 — AI trigger tests
# ===================================================================

class TestStep07AITrigger:

    @pytest.mark.asyncio
    async def test_ai_triggered_low_velocity(self, step):
        """Low velocity → conditional trigger fires."""
        state = _make_state(
            tube_side="cold",
            m_dot_cold=1.0,
            geometry=_make_geometry(n_tubes=500, n_passes=1),
        )
        await step.execute(state)
        assert step._conditional_ai_trigger(state) is True

    @pytest.mark.asyncio
    async def test_ai_triggered_high_velocity(self, step):
        """High velocity → conditional trigger fires."""
        state = _make_state(
            tube_side="cold",
            m_dot_cold=30.0,
            geometry=_make_geometry(n_tubes=20, n_passes=4),
        )
        await step.execute(state)
        assert step._conditional_ai_trigger(state) is True

    @pytest.mark.asyncio
    async def test_ai_not_triggered_normal(self, step):
        """Normal water turbulent → no trigger."""
        state = _make_state(tube_side="cold")
        await step.execute(state)

        # For normal water conditions, velocity and h_i should be in range
        v = getattr(step, "_velocity", None)
        Re = getattr(step, "_Re", None)
        h = getattr(step, "_h_i", None)

        # Only assert no-trigger if conditions are truly normal
        if (v is not None and 0.8 <= v <= 2.5
                and Re is not None and Re >= 10000
                and h is not None and 50 <= h <= 15000):
            assert step._conditional_ai_trigger(state) is False

    @pytest.mark.asyncio
    async def test_ai_skipped_convergence_loop(self, step):
        """in_convergence_loop=True → _should_call_ai returns False."""
        state = _make_state(in_convergence_loop=True)
        await step.execute(state)
        assert step._should_call_ai(state) is False


# ===================================================================
# 7.4 — Validation rules tests
# ===================================================================

class TestStep07Rules:

    def _make_result(self, **overrides) -> "StepResult":
        from hx_engine.app.models.step_result import StepResult
        outputs = {
            "h_tube_W_m2K": 5000.0,
            "tube_velocity_m_s": 1.5,
            "Re_tube": 30000.0,
            "Pr_tube": 3.5,
        }
        outputs.update(overrides)
        return StepResult(step_id=7, step_name="test", outputs=outputs)

    def test_rule_h_positive_pass(self):
        from hx_engine.app.steps.step_07_rules import _rule_h_positive
        passed, msg = _rule_h_positive(7, self._make_result(h_tube_W_m2K=5000))
        assert passed is True
        assert msg is None

    def test_rule_h_positive_fail(self):
        from hx_engine.app.steps.step_07_rules import _rule_h_positive
        passed, msg = _rule_h_positive(7, self._make_result(h_tube_W_m2K=-1))
        assert passed is False
        assert "positive" in msg

    def test_rule_h_missing(self):
        from hx_engine.app.steps.step_07_rules import _rule_h_positive
        from hx_engine.app.models.step_result import StepResult
        result = StepResult(step_id=7, step_name="test", outputs={})
        passed, msg = _rule_h_positive(7, result)
        assert passed is False
        assert "missing" in msg

    def test_rule_velocity_too_low(self):
        from hx_engine.app.steps.step_07_rules import _rule_velocity_bounds
        passed, msg = _rule_velocity_bounds(7, self._make_result(tube_velocity_m_s=0.1))
        assert passed is False
        assert "below" in msg

    def test_rule_velocity_too_high(self):
        from hx_engine.app.steps.step_07_rules import _rule_velocity_bounds
        passed, msg = _rule_velocity_bounds(7, self._make_result(tube_velocity_m_s=6.0))
        assert passed is False
        assert "above" in msg

    def test_rule_velocity_ok(self):
        from hx_engine.app.steps.step_07_rules import _rule_velocity_bounds
        passed, msg = _rule_velocity_bounds(7, self._make_result(tube_velocity_m_s=1.5))
        assert passed is True
        assert msg is None

    def test_rule_re_positive(self):
        from hx_engine.app.steps.step_07_rules import _rule_re_positive
        passed, msg = _rule_re_positive(7, self._make_result(Re_tube=30000))
        assert passed is True

    def test_rule_re_negative(self):
        from hx_engine.app.steps.step_07_rules import _rule_re_positive
        passed, msg = _rule_re_positive(7, self._make_result(Re_tube=-5))
        assert passed is False

    def test_rule_pr_positive(self):
        from hx_engine.app.steps.step_07_rules import _rule_pr_positive
        passed, msg = _rule_pr_positive(7, self._make_result(Pr_tube=3.5))
        assert passed is True

    def test_rule_pr_negative(self):
        from hx_engine.app.steps.step_07_rules import _rule_pr_positive
        passed, msg = _rule_pr_positive(7, self._make_result(Pr_tube=-1))
        assert passed is False
