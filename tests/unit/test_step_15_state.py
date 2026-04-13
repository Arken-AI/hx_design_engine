"""Tests for DesignState Step 15 cost fields."""

from __future__ import annotations

import json

from hx_engine.app.models.design_state import DesignState


def test_cost_fields_default_none():
    """T3.1: New cost fields default to None — no breakage."""
    state = DesignState()
    assert state.cost_usd is None
    assert state.cost_breakdown is None


def test_cost_fields_json_roundtrip():
    """T3.2: DesignState round-trips through JSON with cost fields."""
    state = DesignState(
        cost_usd=168_000.0,
        cost_breakdown={
            "area_m2": 100.0,
            "turton_row": "fixed_tube",
            "Cp0_2001_usd": 23_000.0,
            "F_M": 1.0,
            "F_P": 1.0,
            "C_BM_2026_usd": 168_000.0,
        },
    )
    json_str = state.model_dump_json()
    restored = DesignState.model_validate_json(json_str)
    assert restored.cost_usd == state.cost_usd
    assert restored.cost_breakdown["area_m2"] == 100.0
    assert restored.cost_breakdown["turton_row"] == "fixed_tube"


def test_cost_usd_is_optional_float():
    """T3.3: cost_usd accepts float values."""
    state = DesignState(cost_usd=250_000.50)
    assert isinstance(state.cost_usd, float)
    assert state.cost_usd == 250_000.50
