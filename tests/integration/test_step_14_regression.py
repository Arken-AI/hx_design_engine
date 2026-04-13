"""Tests for ST-12 — Step 14 regression/backward compatibility tests."""

from __future__ import annotations

import pytest

from hx_engine.app.models.design_state import DesignState
from hx_engine.app.data.material_properties import (
    get_density,
    get_elastic_modulus,
    get_poisson,
)


class TestMaterialPropertiesBackwardCompat:
    """T12.6: Existing E, density, poisson calls still work."""

    @pytest.mark.parametrize("mat", [
        "carbon_steel", "stainless_304", "stainless_316",
        "copper", "admiralty_brass", "titanium",
        "inconel_600", "monel_400", "duplex_2205",
    ])
    def test_elastic_modulus(self, mat):
        E = get_elastic_modulus(mat, 100.0)
        assert E >= 100e9  # >= 100 GPa for all metals

    @pytest.mark.parametrize("mat", [
        "carbon_steel", "stainless_304", "stainless_316",
        "copper", "admiralty_brass", "titanium",
        "inconel_600", "monel_400", "duplex_2205",
    ])
    def test_density(self, mat):
        rho = get_density(mat)
        assert 2000 < rho < 10000  # reasonable metal density range

    @pytest.mark.parametrize("mat", [
        "carbon_steel", "stainless_304", "stainless_316",
        "copper", "admiralty_brass", "titanium",
        "inconel_600", "monel_400", "duplex_2205",
    ])
    def test_poisson(self, mat):
        nu = get_poisson(mat)
        assert 0.2 < nu < 0.4  # typical metal Poisson's ratio range


class TestDesignStateSerialization:
    """T12.2: JSON round-trip with new Step 14 fields."""

    def test_round_trip(self):
        state = DesignState(
            tube_thickness_ok=True,
            shell_thickness_ok=False,
            expansion_mm=4.2,
            mechanical_details={"tube": {"t_actual_mm": 2.11}},
            shell_material="sa516_gr70",
        )
        json_str = state.model_dump_json()
        restored = DesignState.model_validate_json(json_str)
        assert restored.tube_thickness_ok is True
        assert restored.shell_thickness_ok is False
        assert restored.expansion_mm == 4.2
        assert restored.shell_material == "sa516_gr70"


class TestDesignStateDefaults:
    """T12.3: Empty state has correct defaults."""

    def test_empty_state(self):
        state = DesignState()
        assert state.tube_thickness_ok is None
        assert state.shell_thickness_ok is None
        assert state.expansion_mm is None
        assert state.mechanical_details is None
        assert state.shell_material is None
