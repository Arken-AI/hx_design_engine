"""Tests for ST-6 — DesignState Step 14 fields."""

from __future__ import annotations

from hx_engine.app.models.design_state import DesignState


class TestStep14StateFields:
    """T6.1–T6.3"""

    def test_defaults_to_none(self):
        """T6.1: New fields default to None."""
        state = DesignState()
        assert state.tube_thickness_ok is None
        assert state.shell_thickness_ok is None
        assert state.expansion_mm is None
        assert state.mechanical_details is None
        assert state.shell_material is None

    def test_shell_material_default(self):
        """T6.2: shell_material defaults to None."""
        state = DesignState()
        assert state.shell_material is None

    def test_json_round_trip(self):
        """T6.3: DesignState serializes/deserializes with new fields."""
        state = DesignState(
            tube_thickness_ok=True,
            shell_thickness_ok=True,
            expansion_mm=2.5,
            mechanical_details={"tube": {"t_actual_mm": 2.11}},
            shell_material="sa516_gr70",
        )
        data = state.model_dump()
        restored = DesignState(**data)
        assert restored.tube_thickness_ok is True
        assert restored.shell_thickness_ok is True
        assert restored.expansion_mm == 2.5
        assert restored.mechanical_details["tube"]["t_actual_mm"] == 2.11
        assert restored.shell_material == "sa516_gr70"
