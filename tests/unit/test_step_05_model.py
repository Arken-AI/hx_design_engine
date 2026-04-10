"""Tests for Piece 0 — F_factor field on DesignState."""

from __future__ import annotations

import json

import pytest

from hx_engine.app.models.design_state import DesignState


class TestDesignStateFfactor:
    """Verify the F_factor field on DesignState."""

    def test_f_factor_default_none(self):
        """F_factor defaults to None until Step 5 runs."""
        state = DesignState()
        assert state.F_factor is None

    def test_f_factor_accepts_valid(self):
        """A valid F value can be set without error."""
        state = DesignState(F_factor=0.92)
        assert state.F_factor == pytest.approx(0.92)

    def test_f_factor_roundtrips_json(self):
        """F_factor survives JSON serialization and deserialization."""
        state = DesignState(F_factor=0.87)
        dumped = state.model_dump_json()
        loaded = DesignState.model_validate_json(dumped)
        assert loaded.F_factor == pytest.approx(0.87)
