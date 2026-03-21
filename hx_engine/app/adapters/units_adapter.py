"""Unit conversion utilities for the HX design pipeline.

All internal calculations use SI: °C, kg/s, Pa, W/(m²·K), m.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Temperature
# ---------------------------------------------------------------------------

def fahrenheit_to_celsius(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


def celsius_to_fahrenheit(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


def kelvin_to_celsius(k: float) -> float:
    return k - 273.15


def celsius_to_kelvin(c: float) -> float:
    return c + 273.15


# ---------------------------------------------------------------------------
# Pressure
# ---------------------------------------------------------------------------

def psi_to_pascal(psi: float) -> float:
    return psi * 6894.757293168


def pascal_to_psi(pa: float) -> float:
    return pa / 6894.757293168


def bar_to_pascal(bar: float) -> float:
    return bar * 100_000.0


def pascal_to_bar(pa: float) -> float:
    return pa / 100_000.0


# ---------------------------------------------------------------------------
# Mass flow
# ---------------------------------------------------------------------------

def lb_hr_to_kg_s(lb_hr: float) -> float:
    return lb_hr * 0.45359237 / 3600.0


def kg_s_to_lb_hr(kg_s: float) -> float:
    return kg_s * 3600.0 / 0.45359237


# ---------------------------------------------------------------------------
# Length
# ---------------------------------------------------------------------------

def inch_to_meter(inch: float) -> float:
    return inch * 0.0254


def meter_to_inch(m: float) -> float:
    return m / 0.0254


# ---------------------------------------------------------------------------
# Heat-transfer coefficient
# ---------------------------------------------------------------------------

def btu_hr_ft2_F_to_W_m2K(btu: float) -> float:
    return btu * 5.678263337


def W_m2K_to_btu_hr_ft2_F(w: float) -> float:
    return w / 5.678263337


# ---------------------------------------------------------------------------
# Auto-detection helpers for user input
# ---------------------------------------------------------------------------

_TEMP_PATTERNS: dict[str, str] = {
    "F": r"(?:°?\s*F|fahrenheit)",
    "K": r"(?:K|kelvin)",
    "C": r"(?:°?\s*C|celsius)",
}

_FLOW_PATTERNS: dict[str, str] = {
    "lb/hr": r"(?:lb/?h(?:r|our)?|lbs?/h(?:r|our)?|pound.*/h(?:r|our)?)",
    "kg/s": r"(?:kg/?s|kilogram.*/s(?:ec(?:ond)?)?)",
    "m3/hr": r"(?:m[³3]/?h(?:r|our)?)",
}

_PRESSURE_PATTERNS: dict[str, str] = {
    "psi": r"(?:psi|lbf?/in)",
    "bar": r"(?:bar)",
    "Pa": r"(?:Pa|pascal)",
    "kPa": r"(?:kPa|kilopascal)",
    "atm": r"(?:atm|atmosphere)",
}


def detect_and_convert_temperature(value: float, unit_str: str) -> float:
    """Convert *value* in *unit_str* to °C."""
    unit = unit_str.strip()
    if re.search(_TEMP_PATTERNS["F"], unit, re.IGNORECASE):
        return fahrenheit_to_celsius(value)
    if re.search(_TEMP_PATTERNS["K"], unit, re.IGNORECASE):
        return kelvin_to_celsius(value)
    # Default: already Celsius
    return value


def detect_and_convert_flow_rate(value: float, unit_str: str) -> float:
    """Convert *value* in *unit_str* to kg/s."""
    unit = unit_str.strip()
    if re.search(_FLOW_PATTERNS["lb/hr"], unit, re.IGNORECASE):
        return lb_hr_to_kg_s(value)
    if re.search(_FLOW_PATTERNS["m3/hr"], unit, re.IGNORECASE):
        # Approximate using water density ~1000 kg/m³
        return value * 1000.0 / 3600.0
    # Default: already kg/s
    return value


def detect_and_convert_pressure(value: float, unit_str: str) -> float:
    """Convert *value* in *unit_str* to Pa."""
    unit = unit_str.strip()
    if re.search(_PRESSURE_PATTERNS["psi"], unit, re.IGNORECASE):
        return psi_to_pascal(value)
    if re.search(_PRESSURE_PATTERNS["bar"], unit, re.IGNORECASE):
        return bar_to_pascal(value)
    if re.search(_PRESSURE_PATTERNS["kPa"], unit, re.IGNORECASE):
        return value * 1000.0
    if re.search(_PRESSURE_PATTERNS["atm"], unit, re.IGNORECASE):
        return value * 101325.0
    # Default: already Pa
    return value
