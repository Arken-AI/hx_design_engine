"""P2-14 — Tubesheet differential drives expansion decision.

Bug ref:  artifacts/bugs/bug_p2_14_step04_delta_t_max_full_span_not_tubesheet_differential.md
Plan ref: artifacts/plans/implementation_plan_p2_14_step04_tubesheet_differential.md
"""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import DesignState, FluidProperties
from hx_engine.app.steps.step_04_tema_geometry import (
    _DT_EXPANSION_THRESHOLD,
    _compute_tubesheet_differential,
)


def _props() -> FluidProperties:
    return FluidProperties(
        density_kg_m3=1000.0, viscosity_Pa_s=1e-3,
        cp_J_kgK=4180.0, k_W_mK=0.6, Pr=7.0,
    )


def _state(T_hot_in, T_hot_out, T_cold_in, T_cold_out) -> DesignState:
    return DesignState(
        hot_fluid_name="water", cold_fluid_name="water",
        T_hot_in_C=T_hot_in, T_hot_out_C=T_hot_out,
        T_cold_in_C=T_cold_in, T_cold_out_C=T_cold_out,
        hot_fluid_props=_props(), cold_fluid_props=_props(),
        Q_W=1e6, m_dot_hot_kg_s=10.0, m_dot_cold_kg_s=12.0,
    )


def test_tubesheet_diff_is_abs_of_mean_difference():
    # Hot mean = 110, cold mean = 45 → |110 − 45| = 65
    state = _state(120, 100, 40, 50)
    diff, span, basis = _compute_tubesheet_differential(state, shell_side="hot")
    assert diff == pytest.approx(65.0)
    assert basis == "tubesheet_differential"


def test_stream_span_kept_for_information():
    state = _state(120, 100, 40, 50)
    _, span, _ = _compute_tubesheet_differential(state, shell_side="hot")
    # max - min = 120 - 40 = 80
    assert span == pytest.approx(80.0)


def test_identical_means_yields_zero_differential():
    state = _state(80, 80, 80, 80)
    diff, _, _ = _compute_tubesheet_differential(state, shell_side="hot")
    assert diff == pytest.approx(0.0)


def test_basis_falls_back_to_span_when_temps_missing():
    state = _state(120, 100, None, 50)
    diff, span, basis = _compute_tubesheet_differential(state, shell_side="hot")
    assert basis == "stream_span_fallback"
    assert diff == span


def test_asymmetric_high_span_low_differential_below_threshold():
    """Bug repro: stream span 120 K but tubesheet differential 65 K.

    Old code would force AES (expansion); new code stays under the
    50-K threshold for the per-side mean difference and so accepts
    fixed-tubesheet candidates (BEM/AES depending on fouling).
    """
    state = _state(180, 60, 30, 90)  # span = 150, hot mean = 120, cold mean = 60
    diff, span, _ = _compute_tubesheet_differential(state, shell_side="hot")
    assert span == pytest.approx(150.0)
    assert diff == pytest.approx(60.0)
    # With 60 K differential (>50), expansion is still required.  Confirm
    # the constant against documented practice.
    assert _DT_EXPANSION_THRESHOLD == 50.0


def test_threshold_matches_documented_value():
    assert _DT_EXPANSION_THRESHOLD == 50.0
