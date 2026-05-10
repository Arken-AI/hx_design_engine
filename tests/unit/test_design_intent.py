"""Tests for hx_engine.app.core.design_intent."""
import pytest
from hx_engine.app.core.design_intent import _TERMINATION_PHRASES, is_termination_intent


class TestIsTerminationIntentPositive:
    """Every phrase in _TERMINATION_PHRASES must be detected."""

    def test_every_phrase_matches(self):
        for phrase in _TERMINATION_PHRASES:
            assert is_termination_intent(phrase) is True, f"Expected True for: {phrase!r}"

    def test_every_phrase_case_insensitive(self):
        for phrase in _TERMINATION_PHRASES:
            assert is_termination_intent(phrase.upper()) is True, (
                f"Expected True for upper-cased: {phrase.upper()!r}"
            )

    def test_every_phrase_with_surrounding_whitespace(self):
        for phrase in _TERMINATION_PHRASES:
            assert is_termination_intent(f"  {phrase}  ") is True, (
                f"Expected True for phrase with whitespace: {phrase!r}"
            )


class TestIsTerminationIntentNegative:
    """Benign user text must return False."""

    def test_benign_phrases(self):
        for text in [
            "increase tube count",
            "use larger shell",
            "raise inlet temperature",
            "",
        ]:
            assert is_termination_intent(text) is False, f"Expected False for: {text!r}"

    def test_swap_fluid_not_termination(self):
        assert is_termination_intent("swap fluid allocation") is False

    def test_proceed_not_termination(self):
        assert is_termination_intent("proceed with minimum TEMA shell geometry") is False

    def test_accept_not_termination(self):
        assert is_termination_intent("yes, go ahead") is False
        assert is_termination_intent("accept") is False


class TestIsTerminationIntentSubstringMatch:
    """Phrase embedded in a longer sentence still matches."""

    def test_flag_as_impractical_in_sentence(self):
        assert is_termination_intent(
            "Given the constraints, please flag as impractical and stop."
        ) is True

    def test_terminate_in_sentence(self):
        assert is_termination_intent(
            "Terminate this shell-and-tube design path entirely"
        ) is True

    def test_not_viable_in_sentence(self):
        assert is_termination_intent("This design is not viable for S&T") is True

    def test_recommend_plate_in_sentence(self):
        assert is_termination_intent("Recommend plate exchanger for this duty") is True

    def test_recommend_double_pipe_in_sentence(self):
        assert is_termination_intent("recommend double-pipe exchanger instead") is True

    def test_abort_design_in_sentence(self):
        assert is_termination_intent("abort design and start over") is True

    def test_no_further_steps_in_sentence(self):
        assert is_termination_intent("no further steps possible") is True

    def test_flag_design_as_impractical_full(self):
        assert is_termination_intent(
            "Flag design as impractical and recommend plate or double-pipe exchanger to the user"
        ) is True
