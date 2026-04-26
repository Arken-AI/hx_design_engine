"""Classify user intent signals for the HX design pipeline.

Currently scoped to termination intent (user wants to abandon a design path).
Add new classifiers here as the harness needs them — keeps domain/UX
vocabulary out of pipeline_runner.py.
"""

# Phrases in escalation-option text or user free-text that signal the user
# wants to abandon this design path entirely.  Matched case-insensitively
# against the full option text that was selected (or the user's typed input).
_TERMINATION_PHRASES = (
    "terminate",
    "flag design as impractical",
    "flag as impractical",
    "not viable",
    "impractical",
    "abort design",
    "abandon",
    "no further steps",
    "cannot proceed",
    "stop design",
    "recommend plate",
    "recommend double-pipe",
    "recommend a plate",
    "recommend a double-pipe",
    "use a plate",
    "use a double-pipe",
)


def is_termination_intent(text: str) -> bool:
    """Return True if *text* signals the user wants to terminate this design path."""
    lowered = text.lower()
    return any(phrase in lowered for phrase in _TERMINATION_PHRASES)
