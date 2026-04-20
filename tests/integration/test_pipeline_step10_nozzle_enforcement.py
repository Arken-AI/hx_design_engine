"""Phase 3 — End-to-end Step 10 nozzle ρv² enforcement smoke + regression.

Drives ``Step10PressureDrops.execute(...)`` with realistic fixtures and pipes
the result through the registered Layer 2 rules via
``validation_rules.check(10, ...)`` — the same call the pipeline runner makes.

Guarantees the canonical no-silent-pass invariant:

    NEVER (ρv² > 2230 kg/m·s²  AND  validation_rules.check(10, ...).passed)

Plus a regression on the comfortable-margin baseline so the Phase 1 tightening
does not widen the blast radius onto designs that were previously fine.
"""

from __future__ import annotations

import pytest

from hx_engine.app.core import validation_rules
from hx_engine.app.models.design_state import (
    DesignState,
    FluidProperties,
    GeometrySpec,
)
from hx_engine.app.steps.step_10_pressure_drops import Step10PressureDrops

# Importing the rules module triggers registration on import.
import hx_engine.app.steps.step_10_rules  # noqa: F401


_RHO_V2_LIMIT = 2230.0


def _state(
    m_dot_hot: float,
    m_dot_cold: float,
    shell_side_fluid: str = "hot",
    shell_diameter_m: float = 0.489,
) -> DesignState:
    """Build a post-Step-9 DesignState ready for Step 10 execution."""
    hot = FluidProperties(
        density_kg_m3=850.0,
        viscosity_Pa_s=0.0012,
        specific_heat_J_kgK=2200.0,
        thermal_conductivity_W_mK=0.13,
        Pr=20.3,
    )
    cold = FluidProperties(
        density_kg_m3=995.0,
        viscosity_Pa_s=0.0008,
        specific_heat_J_kgK=4180.0,
        thermal_conductivity_W_mK=0.62,
        Pr=5.4,
    )
    return DesignState(
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        T_cold_out_C=55.0,
        hot_fluid_name="crude oil",
        cold_fluid_name="cooling water",
        m_dot_hot_kg_s=m_dot_hot,
        m_dot_cold_kg_s=m_dot_cold,
        hot_fluid_props=hot,
        cold_fluid_props=cold,
        shell_side_fluid=shell_side_fluid,
        geometry=GeometrySpec(
            shell_diameter_m=shell_diameter_m,
            tube_od_m=0.01905,
            tube_id_m=0.01483,
            tube_length_m=4.88,
            n_tubes=158,
            tube_pitch_m=0.02381,
            pitch_ratio=1.25,
            pitch_layout="triangular",
            n_passes=2,
            baffle_spacing_m=0.15,
            baffle_cut=0.25,
            n_baffles=30,
        ),
        tube_velocity_m_s=1.5,
        Re_tube=15_000.0,
        Re_shell=12_000.0,
        h_tube_W_m2K=5000.0,
        h_shell_W_m2K=2000.0,
        R_f_hot_m2KW=0.000176,
        R_f_cold_m2KW=0.000176,
    )


class TestStep10NoSilentPassOnNozzleViolation:
    """The canonical guarantee: ρv² over limit must never coexist with a passed
    Layer 2 result. Either auto-correction brought ρv² ≤ limit, or the rule
    failed and the recovery loop will be invoked."""

    @pytest.mark.asyncio
    async def test_high_tube_flow_never_silent_passes(self):
        # Arrange — high tube-side flow drives ρv² over default-nozzle limit
        state = _state(m_dot_hot=5.0, m_dot_cold=200.0)
        step = Step10PressureDrops()

        # Act
        result = await step.execute(state)
        vr = validation_rules.check(10, result)

        # Assert — never (over limit AND passed)
        rho_v2 = result.outputs["rho_v2_tube_nozzle"]
        assert not (rho_v2 > _RHO_V2_LIMIT and vr.passed), (
            f"Silent pass detected: rho_v2_tube_nozzle={rho_v2:.0f} "
            f"> {_RHO_V2_LIMIT:.0f} but Layer 2 passed"
        )

    @pytest.mark.asyncio
    async def test_high_shell_flow_never_silent_passes(self):
        # Arrange — high shell-side flow
        state = _state(m_dot_hot=20.0, m_dot_cold=10.0, shell_side_fluid="hot")
        step = Step10PressureDrops()

        # Act
        result = await step.execute(state)
        vr = validation_rules.check(10, result)

        # Assert
        rho_v2 = result.outputs["rho_v2_shell_nozzle"]
        assert not (rho_v2 > _RHO_V2_LIMIT and vr.passed), (
            f"Silent pass detected: rho_v2_shell_nozzle={rho_v2:.0f} "
            f"> {_RHO_V2_LIMIT:.0f} but Layer 2 passed"
        )


class TestStep10BaselineRegression:
    """Designs whose nozzles are well under the limit must still pass cleanly —
    no false positives from the Phase 1 tightening."""

    @pytest.mark.asyncio
    async def test_comfortable_margin_baseline_passes_validation(self):
        # Arrange — flows that produce ρv² well under TEMA limit
        state = _state(m_dot_hot=5.0, m_dot_cold=10.0)
        step = Step10PressureDrops()

        # Act
        result = await step.execute(state)
        vr = validation_rules.check(10, result)

        # Assert
        assert result.outputs["rho_v2_tube_nozzle"] <= _RHO_V2_LIMIT
        assert result.outputs["rho_v2_shell_nozzle"] <= _RHO_V2_LIMIT
        assert result.outputs["nozzle_auto_corrected_tube"] is False
        assert result.outputs["nozzle_auto_corrected_shell"] is False
        assert vr.passed is True
        assert vr.errors == []
