"""Tests for material_properties.py — ASME BPVC II-D data."""

import pytest

from hx_engine.app.data.material_properties import (
    get_available_materials,
    get_density,
    get_elastic_modulus,
    get_poisson,
)


class TestElasticModulus:
    """Young's modulus lookups and interpolation."""

    def test_carbon_steel_E_at_25C(self):
        assert get_elastic_modulus("carbon_steel", 25.0) == 202e9

    def test_carbon_steel_E_at_200C(self):
        assert get_elastic_modulus("carbon_steel", 200.0) == 192e9

    def test_carbon_steel_E_interpolation(self):
        # 175°C is between 150°C (195 GPa) and 200°C (192 GPa)
        E = get_elastic_modulus("carbon_steel", 175.0)
        expected = (195 + 192) / 2 * 1e9  # 193.5 GPa
        assert E == pytest.approx(expected, rel=1e-6)

    def test_E_clamp_below_range(self):
        # Below 25°C → returns E at 25°C
        E = get_elastic_modulus("carbon_steel", -50.0)
        assert E == 202e9

    def test_E_clamp_above_range(self):
        # Carbon steel table max is 500°C → 151 GPa
        E = get_elastic_modulus("carbon_steel", 600.0)
        assert E == 151e9

    def test_copper_single_point(self):
        # Only 25°C available — any temperature returns 117 GPa
        assert get_elastic_modulus("copper", 25.0) == 117e9
        assert get_elastic_modulus("copper", 200.0) == 117e9
        assert get_elastic_modulus("copper", -10.0) == 117e9

    def test_stainless_304_at_300C(self):
        assert get_elastic_modulus("stainless_304", 300.0) == 176e9

    def test_titanium_interpolation(self):
        # 75°C between 25°C (107) and 100°C (103)
        E = get_elastic_modulus("titanium", 75.0)
        expected = (107 + (103 - 107) * (75 - 25) / (100 - 25)) * 1e9
        assert E == pytest.approx(expected, rel=1e-6)

    def test_unknown_material_raises(self):
        with pytest.raises(KeyError):
            get_elastic_modulus("unobtainium")


class TestDensity:
    """Metal density lookups."""

    def test_carbon_steel(self):
        assert get_density("carbon_steel") == 7750.0

    def test_copper(self):
        assert get_density("copper") == 8940.0

    def test_titanium(self):
        assert get_density("titanium") == 4510.0

    def test_unknown_material_raises(self):
        with pytest.raises(KeyError):
            get_density("unobtainium")


class TestPoisson:
    """Poisson's ratio lookups."""

    def test_carbon_steel(self):
        assert get_poisson("carbon_steel") == 0.30

    def test_stainless_316(self):
        assert get_poisson("stainless_316") == 0.31

    def test_copper(self):
        assert get_poisson("copper") == 0.33


class TestAllMaterials:
    """Validate all nine materials have consistent data."""

    def test_all_nine_materials(self):
        materials = get_available_materials()
        assert len(materials) == 9
        for mat in materials:
            E = get_elastic_modulus(mat)
            rho = get_density(mat)
            nu = get_poisson(mat)
            assert E > 0, f"{mat}: E must be positive"
            assert rho > 0, f"{mat}: density must be positive"
            assert 0 < nu < 0.5, f"{mat}: Poisson out of range"

    def test_available_materials_list(self):
        materials = get_available_materials()
        expected = {
            "carbon_steel", "stainless_304", "stainless_316",
            "copper", "admiralty_brass", "titanium",
            "inconel_600", "monel_400", "duplex_2205",
        }
        assert set(materials) == expected
