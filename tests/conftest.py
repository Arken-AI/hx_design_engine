"""Shared fixtures for the HX engine test suite."""

from __future__ import annotations

import copy
import json

import pytest

from hx_engine.app.models.design_state import DesignState


@pytest.fixture(autouse=True)
def _restore_validation_rules():
    """Restore the global validation rule registry after every test.

    Some test classes call ``validation_rules.clear_rules()`` in
    setup/teardown to isolate rule-registration assertions.  Without
    restoration, all subsequently-executed tests lose rules that were
    registered at import time (e.g. step_10_rules.py auto-registers on
    import).  This fixture snapshots and restores the registry so each
    test gets a clean slate without leaving the shared state corrupted.
    """
    from hx_engine.app.core.validation_rules import _rules

    # Deep-copy the list of RuleMeta objects for each step
    snapshot = {k: list(v) for k, v in _rules.items()}
    yield
    _rules.clear()
    _rules.update(snapshot)


@pytest.fixture
def empty_state() -> DesignState:
    return DesignState()


@pytest.fixture
def benchmark_state() -> DesignState:
    """The standard benchmark request: 50 kg/s crude oil 150→90°C, water at 30°C."""
    return DesignState(
        raw_request=(
            "Design a heat exchanger for cooling 50 kg/s of crude oil "
            "from 150°C to 90°C using cooling water at 30°C"
        )
    )


@pytest.fixture
def benchmark_structured_json() -> str:
    return json.dumps(
        {
            "hot_fluid": "crude oil",
            "cold_fluid": "cooling water",
            "T_hot_in": 150.0,
            "T_hot_out": 90.0,
            "T_cold_in": 30.0,
            "m_dot_hot": 50.0,
            "temp_unit": "C",
            "flow_unit": "kg/s",
        }
    )
