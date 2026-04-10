"""Material physical properties for tube materials.

Sources:
  - Young's modulus: ASME BPVC Section II Part D, Tables TM-1, TM-4, TM-5
  - Density: ASME BPVC Section II Part D, Table PRD
  - Poisson's ratio: ASME BPVC Section II Part D, Table PRD

Used by:
  - Step 13 (vibration): E for natural frequency, ρ for tube mass
  - Step 14 (mechanical): E for ASME VIII calculations, ν for stress
"""

from __future__ import annotations

import bisect

# ---------------------------------------------------------------------------
# Material data table
# E_GPa: {temperature_C: modulus_GPa}
# ---------------------------------------------------------------------------

_MATERIAL_PROPERTIES: dict[str, dict] = {
    "carbon_steel": {
        "label": "Carbon Steel (SA-179/SA-214)",
        "density_kg_m3": 7750.0,
        "poisson": 0.30,
        "E_GPa": {  # ASME II-D TM-1, Group C ≤ 0.30%
            25: 202, 100: 198, 150: 195, 200: 192, 250: 189,
            300: 185, 350: 179, 400: 171, 450: 162, 500: 151,
        },
    },
    "stainless_304": {
        "label": "Stainless Steel 304",
        "density_kg_m3": 8030.0,
        "poisson": 0.31,
        "E_GPa": {  # ASME II-D TM-1, Group G (Austenitic SS)
            25: 195, 100: 189, 150: 186, 200: 183, 250: 179,
            300: 176, 350: 172, 400: 169, 450: 165, 500: 160,
            550: 156, 600: 151, 650: 146, 700: 140,
        },
    },
    "stainless_316": {
        "label": "Stainless Steel 316",
        "density_kg_m3": 8030.0,
        "poisson": 0.31,
        "E_GPa": {  # Same Group G as 304
            25: 195, 100: 189, 150: 186, 200: 183, 250: 179,
            300: 176, 350: 172, 400: 169, 450: 165, 500: 160,
            550: 156, 600: 151, 650: 146, 700: 140,
        },
    },
    "copper": {
        "label": "Copper (C12200)",
        "density_kg_m3": 8940.0,
        "poisson": 0.33,
        "E_GPa": {25: 117},  # TM-3; single-point (Cu HX typically < 150°C)
    },
    "admiralty_brass": {
        "label": "Admiralty Brass (C44300)",
        "density_kg_m3": 8520.0,
        "poisson": 0.33,
        "E_GPa": {25: 100},  # TM-3; single-point
    },
    "titanium": {
        "label": "Titanium Gr. 2",
        "density_kg_m3": 4510.0,
        "poisson": 0.32,
        "E_GPa": {  # ASME II-D TM-5, Ti Gr 1/2/3/7/11/12
            25: 107, 100: 103, 150: 101, 200: 97, 250: 93,
            300: 88, 350: 84, 400: 80,
        },
    },
    "inconel_600": {
        "label": "Inconel 600 (N06600)",
        "density_kg_m3": 8410.0,
        "poisson": 0.31,
        "E_GPa": {  # ASME II-D TM-4, N06600
            25: 213, 100: 209, 200: 203, 300: 198, 400: 192,
            500: 186, 600: 178, 700: 170,
        },
    },
    "monel_400": {
        "label": "Monel 400 (N04400)",
        "density_kg_m3": 8860.0,
        "poisson": 0.31,
        "E_GPa": {  # ASME II-D TM-4, N04400
            25: 179, 100: 175, 200: 171, 300: 166, 400: 161,
            500: 155, 600: 149, 700: 142,
        },
    },
    "duplex_2205": {
        "label": "Duplex SS 2205 (S31803)",
        "density_kg_m3": 7800.0,
        "poisson": 0.31,
        "E_GPa": {  # ASME II-D TM-1, Group H
            25: 200, 100: 194, 200: 186, 300: 180, 400: 174,
            450: 172,
        },
    },
}


def _interpolate_E(E_table: dict[int, float], temperature_C: float) -> float:
    """Linearly interpolate E from a {temp: E_GPa} table.

    Clamps to nearest available temperature if *temperature_C* is outside
    the table range.
    """
    temps = sorted(E_table.keys())
    # Clamp
    if temperature_C <= temps[0]:
        return float(E_table[temps[0]])
    if temperature_C >= temps[-1]:
        return float(E_table[temps[-1]])
    # Find bracketing pair
    idx = bisect.bisect_right(temps, temperature_C)
    T_lo, T_hi = temps[idx - 1], temps[idx]
    E_lo, E_hi = E_table[T_lo], E_table[T_hi]
    frac = (temperature_C - T_lo) / (T_hi - T_lo)
    return E_lo + frac * (E_hi - E_lo)


def get_elastic_modulus(material: str, temperature_C: float = 25.0) -> float:
    """Return Young's modulus in Pa at the specified temperature.

    Linearly interpolates between available data points.
    Clamps to nearest available temperature if out of range.

    Raises
    ------
    KeyError
        If *material* is not in the material property table.
    """
    props = _MATERIAL_PROPERTIES[material]
    E_GPa = _interpolate_E(props["E_GPa"], temperature_C)
    return E_GPa * 1e9


def get_density(material: str) -> float:
    """Return tube metal density in kg/m³.

    Raises
    ------
    KeyError
        If *material* is not in the material property table.
    """
    return _MATERIAL_PROPERTIES[material]["density_kg_m3"]


def get_poisson(material: str) -> float:
    """Return Poisson's ratio.

    Raises
    ------
    KeyError
        If *material* is not in the material property table.
    """
    return _MATERIAL_PROPERTIES[material]["poisson"]


def get_available_materials() -> list[str]:
    """Return list of valid material keys."""
    return list(_MATERIAL_PROPERTIES.keys())
