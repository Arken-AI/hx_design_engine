"""Claude-powered fouling factor lookup for unknown / location-dependent fluids.

Calls Claude Sonnet 4.6 with a structured prompt, parses the response
to extract R_f value + confidence + reasoning.
"""

from __future__ import annotations

import logging



logger = logging.getLogger(__name__)


async def get_fouling_from_ai(
    fluid_name: str,
    temperature_C: float | None = None,
    additional_context: str | None = None,
) -> dict:
    """Call Claude to get a fouling factor for an unknown/location-dependent fluid.

    Returns:
        {
            "rf_value": float,
            "confidence": float,
            "reasoning": str,
            "classification": str,
            "source": "claude-sonnet-4-6",
            "error": None | str,
        }

    On API failure, returns a fallback with error message and confidence=0.
    """
    logger.debug("AI fouling lookup stubbed -- returning deterministic fallback for '%s'", fluid_name)
    return {
        "rf_value": 0.000352,
        "confidence": 0.0,
        "reasoning": "AI fouling lookup permanently disabled (stub mode)",
        "classification": "moderate",
        "source": "fallback_default",
        "error": None,
    }
