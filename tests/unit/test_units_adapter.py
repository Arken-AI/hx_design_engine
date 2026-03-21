"""Tests for Piece 6: Units adapter."""

import pytest

from hx_engine.app.adapters.units_adapter import (
    bar_to_pascal,
    btu_hr_ft2_F_to_W_m2K,
    celsius_to_fahrenheit,
    detect_and_convert_flow_rate,
    detect_and_convert_pressure,
    detect_and_convert_temperature,
    fahrenheit_to_celsius,
    inch_to_meter,
    kelvin_to_celsius,
    lb_hr_to_kg_s,
    psi_to_pascal,
)


class TestTemperatureConversions:
    def test_f_to_c_boiling(self):
        assert fahrenheit_to_celsius(212.0) == pytest.approx(100.0)

    def test_f_to_c_freezing(self):
        assert fahrenheit_to_celsius(32.0) == pytest.approx(0.0)

    def test_f_to_c_absolute_zero(self):
        assert fahrenheit_to_celsius(-459.67) == pytest.approx(-273.15, abs=0.01)

    def test_roundtrip_f_c_f(self):
        original = 150.0
        c = fahrenheit_to_celsius(original)
        f = celsius_to_fahrenheit(c)
        assert f == pytest.approx(original, rel=1e-10)


class TestPressureConversions:
    def test_psi_to_pascal_atm(self):
        assert psi_to_pascal(14.696) == pytest.approx(101325.0, rel=0.001)

    def test_bar_to_pascal(self):
        assert bar_to_pascal(1.0) == pytest.approx(100000.0)


class TestFlowConversions:
    def test_lb_hr_to_kg_s(self):
        assert lb_hr_to_kg_s(7936.6) == pytest.approx(1.0, rel=0.001)


class TestLengthConversions:
    def test_inch_to_meter(self):
        assert inch_to_meter(1.0) == pytest.approx(0.0254)


class TestHeatTransferCoeff:
    def test_btu_to_W_m2K(self):
        assert btu_hr_ft2_F_to_W_m2K(1.0) == pytest.approx(5.678, rel=0.001)


class TestDetectTemp:
    def test_fahrenheit(self):
        assert detect_and_convert_temperature(150, "°F") == pytest.approx(65.556, rel=0.01)

    def test_celsius(self):
        assert detect_and_convert_temperature(150, "°C") == 150.0

    def test_kelvin(self):
        assert detect_and_convert_temperature(373.15, "K") == pytest.approx(100.0)

    def test_kelvin_word(self):
        assert detect_and_convert_temperature(373.15, "kelvin") == pytest.approx(100.0)


class TestDetectFlow:
    def test_lb_hr(self):
        assert detect_and_convert_flow_rate(7936.6, "lb/hr") == pytest.approx(1.0, rel=0.001)

    def test_kg_s(self):
        assert detect_and_convert_flow_rate(50.0, "kg/s") == 50.0

    def test_m3_hr(self):
        # 100 m³/hr of water ≈ 27.78 kg/s
        assert detect_and_convert_flow_rate(100.0, "m³/hr") == pytest.approx(27.78, rel=0.01)


class TestDetectPressure:
    def test_bar(self):
        assert detect_and_convert_pressure(5.0, "bar") == pytest.approx(500000.0)

    def test_psi(self):
        assert detect_and_convert_pressure(14.696, "psi") == pytest.approx(101325.0, rel=0.001)

    def test_pa(self):
        assert detect_and_convert_pressure(101325.0, "Pa") == 101325.0

    def test_kpa(self):
        assert detect_and_convert_pressure(500.0, "kPa") == pytest.approx(500000.0)
