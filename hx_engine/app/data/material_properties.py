"""Material physical properties for tube and shell materials.

Sources:
  - Young's modulus: ASME BPVC Section II Part D, Tables TM-1, TM-4, TM-5
  - Density: ASME BPVC Section II Part D, Table PRD
  - Poisson's ratio: ASME BPVC Section II Part D, Table PRD
  - Allowable stress: ASME BPVC Section II Part D, Tables 1A (ferrous) / 1B (non-ferrous)
  - Thermal expansion: ASME BPVC Section II Part D, Tables TE-1 through TE-6

Used by:
  - Step 13 (vibration): E for natural frequency, ρ for tube mass
  - Step 14 (mechanical): S for ASME VIII thickness, α for thermal expansion
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
        "S_MPa": {  # ASME II-D Table 1A, SA-179
            40: 118, 100: 118, 150: 118, 200: 118, 250: 118,
            300: 118, 350: 118, 400: 110, 450: 80,
        },
        "alpha_um_mK": {  # ASME II-D Table TE-1, Group 1
            25: 11.7, 50: 11.8, 100: 12.0, 150: 12.3, 200: 12.5,
            250: 12.8, 300: 13.0, 350: 13.3, 400: 13.5, 450: 13.7,
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
        "S_MPa": {  # ASME II-D Table 1A, SA-213 TP304
            40: 138, 100: 129, 150: 122, 200: 115, 250: 110,
            300: 105, 350: 102, 400: 98, 450: 95, 500: 93,
            550: 89, 600: 86, 650: 83, 700: 79, 750: 69,
            800: 54, 815: 48,
        },
        "alpha_um_mK": {  # ASME II-D Table TE-1, Group 3
            25: 15.3, 50: 15.5, 100: 16.0, 150: 16.3, 200: 16.6,
            250: 16.9, 300: 17.2, 350: 17.5, 400: 17.8, 450: 18.0,
            500: 18.2,
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
        "S_MPa": {  # ASME II-D Table 1A, SA-213 TP316
            40: 138, 100: 131, 150: 124, 200: 118, 250: 113,
            300: 108, 350: 105, 400: 102, 450: 99, 500: 96,
            550: 93, 600: 89, 650: 85, 700: 80, 750: 69,
            800: 54, 815: 48,
        },
        "alpha_um_mK": {  # ASME II-D Table TE-1, Group 3
            25: 15.3, 50: 15.5, 100: 15.9, 150: 16.2, 200: 16.5,
            250: 16.8, 300: 17.1, 350: 17.4, 400: 17.7, 450: 17.9,
            500: 18.1,
        },
    },
    "copper": {
        "label": "Copper (C12200)",
        "density_kg_m3": 8940.0,
        "poisson": 0.33,
        "E_GPa": {25: 117},  # TM-3; single-point (Cu HX typically < 150°C)
        "S_MPa": {  # ASME II-D Table 1B, SB-75 C12200
            40: 46, 65: 46, 100: 43, 150: 35, 205: 25,
        },
        "alpha_um_mK": {  # ASME II-D Table TE-3, Group 1
            25: 16.5, 50: 16.6, 100: 17.0, 150: 17.3, 200: 17.6,
            205: 17.6,
        },
    },
    "admiralty_brass": {
        "label": "Admiralty Brass (C44300)",
        "density_kg_m3": 8520.0,
        "poisson": 0.33,
        "E_GPa": {25: 100},  # TM-3; single-point
        "S_MPa": {  # ASME II-D Table 1B, SB-111 C44300
            40: 69, 65: 69, 100: 69, 150: 62, 205: 48,
        },
        "alpha_um_mK": {  # ASME II-D Table TE-3, Group 2
            25: 19.9, 50: 20.0, 100: 20.2, 150: 20.4, 200: 20.5,
            205: 20.5,
        },
    },
    "titanium": {
        "label": "Titanium Gr. 2",
        "density_kg_m3": 4510.0,
        "poisson": 0.32,
        "E_GPa": {  # ASME II-D TM-5, Ti Gr 1/2/3/7/11/12
            25: 107, 100: 103, 150: 101, 200: 97, 250: 93,
            300: 88, 350: 84, 400: 80,
        },
        "S_MPa": {  # ASME II-D Table 1B, SB-338 Gr.2
            40: 165, 100: 145, 150: 129, 200: 115, 250: 103,
            300: 92, 315: 87,
        },
        "alpha_um_mK": {  # ASME II-D Table TE-5, Ti Gr 1-4
            25: 8.6, 50: 8.7, 100: 8.9, 150: 9.0, 200: 9.2,
            250: 9.3, 300: 9.4, 315: 9.5,
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
        "S_MPa": {  # ASME II-D Table 1B, SB-163 N06600
            40: 172, 100: 168, 150: 159, 200: 153, 250: 148,
            300: 145, 350: 143, 400: 141, 450: 139, 500: 131,
            540: 117,
        },
        "alpha_um_mK": {  # ASME II-D Table TE-4, Group 1
            25: 13.1, 50: 13.1, 100: 13.3, 150: 13.5, 200: 13.7,
            250: 13.9, 300: 14.1, 350: 14.3, 400: 14.4, 450: 14.6,
            500: 14.8, 540: 15.0,
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
        "S_MPa": {  # ASME II-D Table 1B, SB-163 N04400
            40: 156, 100: 149, 150: 141, 200: 138, 250: 137,
            300: 136, 350: 133, 400: 124, 450: 96, 480: 82,
        },
        "alpha_um_mK": {  # ASME II-D Table TE-4, Group 2
            25: 13.7, 50: 13.8, 100: 14.0, 150: 14.2, 200: 14.4,
            250: 14.6, 300: 14.8, 350: 15.0, 400: 15.1, 450: 15.2,
            480: 15.3,
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
        "S_MPa": {  # ASME II-D Table 1A, SA-240 S31803
            40: 230, 100: 212, 150: 202, 200: 192, 250: 182,
            300: 176, 315: 174,
        },
        "alpha_um_mK": {  # ASME II-D Table TE-1, Group 2
            25: 12.5, 50: 12.6, 100: 13.0, 150: 13.2, 200: 13.5,
            250: 13.7, 300: 14.0, 315: 14.1,
        },
    },
    "sa516_gr70": {
        "label": "SA-516 Gr.70 (Shell plate)",
        "density_kg_m3": 7750.0,
        "poisson": 0.30,
        "E_GPa": {  # ASME II-D TM-1, Group C (same as carbon steel)
            25: 202, 100: 198, 150: 195, 200: 192, 250: 189,
            300: 185, 350: 179, 400: 171, 450: 162, 500: 151,
        },
        "S_MPa": {  # ASME II-D Table 1A, SA-516 Gr.70
            40: 138, 100: 138, 150: 138, 200: 138, 250: 138,
            300: 138, 350: 138, 400: 130, 450: 100, 480: 83,
        },
        "alpha_um_mK": {  # ASME II-D Table TE-1, Group 1 (same as CS)
            25: 11.7, 50: 11.8, 100: 12.0, 150: 12.3, 200: 12.5,
            250: 12.8, 300: 13.0, 350: 13.3, 400: 13.5, 450: 13.7,
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


# ---------------------------------------------------------------------------
# Key resolver — accepts either a dict key or a display label
# ---------------------------------------------------------------------------

# Build a reverse map from label → key (built once at import time)
_LABEL_TO_KEY: dict[str, str] = {}
for _key, _props in _MATERIAL_PROPERTIES.items():
    _label = _props.get("label", "")
    if _label:
        _LABEL_TO_KEY[_label.lower()] = _key


def _resolve_key(material: str) -> str:
    """Resolve a material identifier to its canonical dict key.

    Accepts:
      - A dict key (e.g. ``"carbon_steel"``) — returned as-is.
      - A display label (e.g. ``"Carbon Steel (SA-179/SA-214)"``) — mapped
        back to the dict key via a case-insensitive reverse lookup.

    Raises
    ------
    KeyError
        If *material* matches neither a key nor a known label.
    """
    if material in _MATERIAL_PROPERTIES:
        return material
    # Try case-insensitive label lookup
    resolved = _LABEL_TO_KEY.get(material.lower())
    if resolved is not None:
        return resolved
    raise KeyError(
        f"Unknown material '{material}'. "
        f"Valid keys: {sorted(_MATERIAL_PROPERTIES.keys())}"
    )


def resolve_material_key(material: str) -> str:
    """Public wrapper around ``_resolve_key``.

    Useful for callers that need to normalise a material identifier
    before storing it on state.
    """
    return _resolve_key(material)


def get_elastic_modulus(material: str, temperature_C: float = 25.0) -> float:
    """Return Young's modulus in Pa at the specified temperature.

    Linearly interpolates between available data points.
    Clamps to nearest available temperature if out of range.

    Raises
    ------
    KeyError
        If *material* is not in the material property table.
    """
    props = _MATERIAL_PROPERTIES[_resolve_key(material)]
    E_GPa = _interpolate_E(props["E_GPa"], temperature_C)
    return E_GPa * 1e9


def get_density(material: str) -> float:
    """Return tube metal density in kg/m³.

    Raises
    ------
    KeyError
        If *material* is not in the material property table.
    """
    return _MATERIAL_PROPERTIES[_resolve_key(material)]["density_kg_m3"]


def get_poisson(material: str) -> float:
    """Return Poisson's ratio.

    Raises
    ------
    KeyError
        If *material* is not in the material property table.
    """
    return _MATERIAL_PROPERTIES[_resolve_key(material)]["poisson"]


def get_available_materials() -> list[str]:
    """Return list of valid material keys."""
    return list(_MATERIAL_PROPERTIES.keys())


def get_allowable_stress(material: str, temperature_C: float = 25.0) -> float:
    """Return maximum allowable stress in Pa at the specified temperature.

    Uses same bisect interpolation as get_elastic_modulus().

    Raises
    ------
    KeyError
        If *material* is not in the material property table.
    """
    props = _MATERIAL_PROPERTIES[_resolve_key(material)]
    S_MPa = _interpolate_E(props["S_MPa"], temperature_C)
    return S_MPa * 1e6


def get_thermal_expansion(material: str, temperature_C: float = 25.0) -> float:
    """Return mean thermal expansion coefficient in 1/°C (dimensionless).

    Divides stored µm/m·°C value by 1e6 to return 1/°C.

    Raises
    ------
    KeyError
        If *material* is not in the material property table.
    """
    props = _MATERIAL_PROPERTIES[_resolve_key(material)]
    alpha_um = _interpolate_E(props["alpha_um_mK"], temperature_C)
    return alpha_um * 1e-6
