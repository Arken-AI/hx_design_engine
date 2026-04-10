"""Unit tests for HMAC token sign/verify logic."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from hx_engine.app.core.requirements_validator import sign_token, verify_token


_SAMPLE_INPUT = {
    "hot_fluid_name": "crude oil",
    "cold_fluid_name": "water",
    "T_hot_in_C": 150.0,
    "T_hot_out_C": 80.0,
    "T_cold_in_C": 25.0,
    "T_cold_out_C": 50.0,
    "m_dot_hot_kg_s": 10.0,
}


class TestTokenSignVerify:

    def test_sign_and_verify_same_minute(self):
        token = sign_token(_SAMPLE_INPUT)
        assert verify_token(token, _SAMPLE_INPUT)

    def test_wrong_token_rejected(self):
        assert not verify_token("deadbeef" * 8, _SAMPLE_INPUT)

    def test_tampered_input_rejected(self):
        token = sign_token(_SAMPLE_INPUT)
        tampered = dict(_SAMPLE_INPUT)
        tampered["T_hot_in_C"] = 999.0
        assert not verify_token(token, tampered)

    def test_token_valid_from_previous_minute(self):
        """Token signed in minute N should be accepted in minute N+1."""
        base_minute = int(time.time()) // 60

        # Sign at minute N
        with patch("hx_engine.app.core.requirements_validator.time") as mock_time:
            mock_time.time.return_value = base_minute * 60 + 30  # middle of minute N
            token = sign_token(_SAMPLE_INPUT)

        # Verify at minute N+1
        with patch("hx_engine.app.core.requirements_validator.time") as mock_time:
            mock_time.time.return_value = (base_minute + 1) * 60 + 30  # middle of minute N+1
            assert verify_token(token, _SAMPLE_INPUT)

    def test_token_expired_after_two_minutes(self):
        """Token signed in minute N should be rejected in minute N+2."""
        base_minute = int(time.time()) // 60

        # Sign at minute N
        with patch("hx_engine.app.core.requirements_validator.time") as mock_time:
            mock_time.time.return_value = base_minute * 60 + 30
            token = sign_token(_SAMPLE_INPUT)

        # Verify at minute N+2 (expired)
        with patch("hx_engine.app.core.requirements_validator.time") as mock_time:
            mock_time.time.return_value = (base_minute + 2) * 60 + 30
            assert not verify_token(token, _SAMPLE_INPUT)

    def test_token_is_hex_string(self):
        token = sign_token(_SAMPLE_INPUT)
        # SHA-256 hex digest = 64 characters
        assert len(token) == 64
        assert all(c in "0123456789abcdef" for c in token)

    def test_key_order_invariant(self):
        """Canonical JSON uses sort_keys — key order must not matter."""
        input_a = {"T_hot_in_C": 150.0, "hot_fluid_name": "crude oil",
                   "cold_fluid_name": "water", "T_cold_in_C": 25.0,
                   "m_dot_hot_kg_s": 10.0}
        input_b = {"hot_fluid_name": "crude oil", "cold_fluid_name": "water",
                   "T_hot_in_C": 150.0, "T_cold_in_C": 25.0,
                   "m_dot_hot_kg_s": 10.0}
        token_a = sign_token(input_a)
        assert verify_token(token_a, input_b)
