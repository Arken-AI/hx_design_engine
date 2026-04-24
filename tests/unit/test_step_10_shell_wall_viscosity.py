"""P2-25 — Shell-side μ_wall is resolved (not silently approximated to bulk).

Bug ref:  artifacts/bugs/bug_p2_25_step10_mu_wall_approximated_undisclosed_shell_side.md
Plan ref: artifacts/plans/implementation_plan_p2_25_step10_shell_wall_viscosity.md
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from hx_engine.app.steps import step_10_pressure_drops as step10
from hx_engine.app.steps.step_10_pressure_drops import (
    _MU_VISCOUS_THRESHOLD_PA_S,
    _estimate_shell_wall_temperature,
    _resolve_shell_wall_viscosity,
    _shell_bulk_temperature,
)


def _state(**overrides):
    base = dict(
        shell_side_fluid="hot",
        T_hot_in_C=200.0, T_hot_out_C=120.0,
        T_cold_in_C=30.0, T_cold_out_C=60.0,
        h_shell_W_m2K=500.0,
        h_tube_W_m2K=2000.0,
        hot_fluid_name="crude_oil",
        cold_fluid_name="water",
        P_hot_Pa=5e5, P_cold_Pa=3e5,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ── Wall-temperature estimate ──────────────────────────────────────

def test_wall_temp_for_hot_shell_lies_between_bulks():
    state = _state()
    T_bulk = _shell_bulk_temperature(state)
    T_wall = _estimate_shell_wall_temperature(state, T_bulk)
    assert T_bulk == 160.0
    # h_shell/(h_shell+h_tube) = 500/2500 = 0.2; bulk gap = 160-45 = 115
    # T_wall = 160 - 0.2*115 = 137.0
    assert T_wall == pytest.approx(137.0, abs=0.01)


def test_wall_temp_returns_none_when_h_missing():
    state = _state(h_shell_W_m2K=None)
    assert _estimate_shell_wall_temperature(state, 160.0) is None


# ── Wall-viscosity resolver ────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_returns_computed_when_backend_succeeds():
    fake = SimpleNamespace(viscosity_Pa_s=0.005)
    async def _ok(*_a, **_k):
        return fake
    with patch.object(step10, "get_fluid_properties", _ok):
        mu, basis, reason = await _resolve_shell_wall_viscosity(
            "crude_oil", T_wall=137.0, pressure_Pa=5e5, mu_bulk=0.020,
        )
    assert mu == 0.005
    assert basis == "computed"
    assert reason is None


@pytest.mark.asyncio
async def test_resolve_falls_back_when_wall_T_missing():
    mu, basis, reason = await _resolve_shell_wall_viscosity(
        "crude_oil", T_wall=None, pressure_Pa=5e5, mu_bulk=0.020,
    )
    assert mu == 0.020
    assert basis == "approx_bulk"
    assert reason == "wall_temperature_unavailable"


@pytest.mark.asyncio
async def test_resolve_falls_back_when_backend_returns_none():
    fake = SimpleNamespace(viscosity_Pa_s=None)
    async def _none(*_a, **_k):
        return fake
    with patch.object(step10, "get_fluid_properties", _none):
        mu, basis, reason = await _resolve_shell_wall_viscosity(
            "crude_oil", T_wall=137.0, pressure_Pa=5e5, mu_bulk=0.020,
        )
    assert basis == "approx_bulk"
    assert reason == "viscosity_backend_no_value"


@pytest.mark.asyncio
async def test_resolve_falls_back_on_backend_exception():
    async def _boom(*_a, **_k):
        raise RuntimeError("network down")
    with patch.object(step10, "get_fluid_properties", _boom):
        _, basis, reason = await _resolve_shell_wall_viscosity(
            "crude_oil", T_wall=137.0, pressure_Pa=5e5, mu_bulk=0.020,
        )
    assert basis == "approx_bulk"
    assert reason.startswith("viscosity_backend_error:")


# ── Threshold sanity ───────────────────────────────────────────────

def test_viscous_threshold_is_10cP():
    assert _MU_VISCOUS_THRESHOLD_PA_S == 0.01
