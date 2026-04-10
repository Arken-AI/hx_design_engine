"""Tests for Pre-Piece 0: Model updates (GeometrySpec + DesignState new fields)."""

from __future__ import annotations

import json

import pytest

from hx_engine.app.models.design_state import DesignState, GeometrySpec


# -------------------------------------------------------------------
# GeometrySpec.n_tubes
# -------------------------------------------------------------------

class TestGeometrySpecNTubes:
    def test_n_tubes_valid(self):
        """n_tubes=324 accepted (standard tube count)."""
        g = GeometrySpec(n_tubes=324)
        assert g.n_tubes == 324

    def test_n_tubes_zero_rejected(self):
        """n_tubes=0 → ValueError (must have at least 1 tube)."""
        with pytest.raises(ValueError, match="n_tubes"):
            GeometrySpec(n_tubes=0)

    def test_n_tubes_excessive(self):
        """n_tubes=20000 → ValueError (beyond fabrication limits)."""
        with pytest.raises(ValueError, match="n_tubes"):
            GeometrySpec(n_tubes=20000)


# -------------------------------------------------------------------
# GeometrySpec.n_passes
# -------------------------------------------------------------------

class TestGeometrySpecNPasses:
    @pytest.mark.parametrize("val", [1, 2, 4, 6, 8])
    def test_n_passes_valid_values(self, val):
        """n_passes ∈ {1,2,4,6,8} accepted."""
        g = GeometrySpec(n_passes=val)
        assert g.n_passes == val

    def test_n_passes_3_rejected(self):
        """n_passes=3 → ValueError (not a standard TEMA pass count)."""
        with pytest.raises(ValueError, match="n_passes"):
            GeometrySpec(n_passes=3)

    def test_n_passes_5_rejected(self):
        """n_passes=5 is not standard."""
        with pytest.raises(ValueError, match="n_passes"):
            GeometrySpec(n_passes=5)


# -------------------------------------------------------------------
# GeometrySpec.pitch_layout
# -------------------------------------------------------------------

class TestGeometrySpecPitchLayout:
    @pytest.mark.parametrize("val", ["triangular", "square"])
    def test_pitch_layout_valid(self, val):
        """'triangular' and 'square' accepted."""
        g = GeometrySpec(pitch_layout=val)
        assert g.pitch_layout == val

    def test_pitch_layout_invalid(self):
        """'hexagonal' → ValueError."""
        with pytest.raises(ValueError, match="pitch_layout"):
            GeometrySpec(pitch_layout="hexagonal")


# -------------------------------------------------------------------
# DesignState.tema_type
# -------------------------------------------------------------------

class TestDesignStateTemaType:
    def test_tema_type_stored(self):
        """DesignState(tema_type='BEM') round-trips through JSON."""
        ds = DesignState(tema_type="BEM")
        assert ds.tema_type == "BEM"
        # Round-trip through JSON
        data = json.loads(ds.model_dump_json())
        ds2 = DesignState(**data)
        assert ds2.tema_type == "BEM"

    def test_shell_side_fluid_stored(self):
        """DesignState(shell_side_fluid='hot') round-trips."""
        ds = DesignState(shell_side_fluid="hot")
        assert ds.shell_side_fluid == "hot"
        data = json.loads(ds.model_dump_json())
        ds2 = DesignState(**data)
        assert ds2.shell_side_fluid == "hot"
