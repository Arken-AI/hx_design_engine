"""Claude-powered fouling factor lookup for unknown / location-dependent fluids.

Calls Claude Sonnet 4.6 with a structured prompt, parses the response
to extract R_f value + confidence + reasoning.
"""

from __future__ import annotations

import json
import logging
import os
import re

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

# Claude model to use
_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 1024
_TEMPERATURE = 0.0  # deterministic for engineering values


_SYSTEM_PROMPT = """\
You are an expert heat exchanger design engineer with deep knowledge of \
fouling resistances from TEMA Standards (RGP-T-2.4), Perry's Chemical \
Engineers' Handbook (Table 11-10), and Kern's Process Heat Transfer.

When asked for a fouling resistance (R_f) for a fluid, you must:
1. Identify the fluid category and service conditions
2. Provide the R_f value in m²·K/W
3. Rate your confidence from 0.0 to 1.0
4. Cite your reasoning and source

Respond ONLY with a JSON object in this exact format:
{
    "rf_value": <float in m²·K/W>,
    "confidence": <float 0.0-1.0>,
    "reasoning": "<brief explanation citing source>",
    "classification": "<clean|moderate|heavy|severe>"
}

Do NOT include any text outside the JSON object.\
"""


def _build_user_prompt(
    fluid_name: str,
    temperature_C: float | None = None,
    additional_context: str | None = None,
) -> str:
    """Build the user prompt for the fouling factor request."""
    parts = [
        f"What is the fouling resistance (R_f) in m²·K/W for: {fluid_name}"
    ]
    if temperature_C is not None:
        parts.append(f"Operating temperature: {temperature_C:.0f}°C")
    if additional_context:
        parts.append(f"Additional context: {additional_context}")
    parts.append(
        "\nProvide your answer as the JSON object described in your instructions."
    )
    return "\n".join(parts)


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
    api_key = os.environ.get("HX_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_anthropic_api_key_here":
        logger.warning("ANTHROPIC_API_KEY not configured — cannot call AI")
        return {
            "rf_value": 0.000352,
            "confidence": 0.0,
            "reasoning": "AI unavailable (no API key configured)",
            "classification": "moderate",
            "source": "fallback_default",
            "error": "ANTHROPIC_API_KEY not configured",
        }

    client = AsyncAnthropic(api_key=api_key)
    user_prompt = _build_user_prompt(fluid_name, temperature_C, additional_context)

    try:
        message = await client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Extract text from response
        text = ""
        for block in message.content:
            if hasattr(block, "text"):
                text += block.text

        # Parse JSON from response
        parsed = _parse_response(text)
        parsed["source"] = _MODEL
        parsed["error"] = None

        logger.info(
            "AI fouling factor for '%s': R_f=%.6f (confidence=%.2f)",
            fluid_name, parsed["rf_value"], parsed["confidence"],
        )
        return parsed

    except Exception as e:
        logger.error("Claude API call failed: %s", e, exc_info=True)
        return {
            "rf_value": 0.000352,
            "confidence": 0.0,
            "reasoning": f"AI call failed: {e}",
            "classification": "moderate",
            "source": "fallback_default",
            "error": str(e),
        }


def _parse_response(text: str) -> dict:
    """Parse Claude's JSON response, with fallback for malformed responses."""
    # Try to extract JSON from the response
    text = text.strip()

    # Try direct parse
    try:
        data = json.loads(text)
        return _validate_parsed(data)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from markdown code blocks
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            return _validate_parsed(data)
        except json.JSONDecodeError:
            pass

    # Try finding any JSON object in the text
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return _validate_parsed(data)
        except json.JSONDecodeError:
            pass

    # Complete fallback
    logger.warning("Could not parse AI response: %s", text[:200])
    return {
        "rf_value": 0.000352,
        "confidence": 0.0,
        "reasoning": f"Unparseable AI response: {text[:200]}",
        "classification": "moderate",
    }


def _validate_parsed(data: dict) -> dict:
    """Validate and normalize the parsed AI response."""
    rf = float(data.get("rf_value", 0.000352))
    # Sanity: R_f should be between 0 and 0.01 m²·K/W
    if rf <= 0 or rf > 0.01:
        logger.warning("AI returned out-of-range R_f=%.6f, clamping", rf)
        rf = max(0.000001, min(0.01, rf))

    confidence = float(data.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))

    return {
        "rf_value": rf,
        "confidence": confidence,
        "reasoning": str(data.get("reasoning", "No reasoning provided")),
        "classification": str(data.get("classification", "moderate")),
    }
