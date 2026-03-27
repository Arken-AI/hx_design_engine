"""Step 01 — Process Requirements.

Parses a user's heat-exchanger design request (structured JSON **or**
natural language) into a validated set of temperatures, flow rates,
fluid names, and optional pressures / TEMA preferences.

ai_mode = FULL — the AI engineer always reviews Step 1 outputs.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from hx_engine.app.adapters.units_adapter import (
    detect_and_convert_flow_rate,
    detect_and_convert_pressure,
    detect_and_convert_temperature,
)
from hx_engine.app.models.design_state import DesignState
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep


# ---------------------------------------------------------------------------
# Structured input schema
# ---------------------------------------------------------------------------

class DesignInput(BaseModel):
    """Validated structured input for an HX design request."""

    hot_fluid: str
    cold_fluid: str
    T_hot_in: float
    T_hot_out: Optional[float] = None
    T_cold_in: float
    T_cold_out: Optional[float] = None
    m_dot_hot: float
    m_dot_cold: Optional[float] = None
    temp_unit: str = "C"
    flow_unit: str = "kg/s"
    pressure: Optional[float] = None
    pressure_unit: str = "Pa"
    tema_class: Optional[str] = None
    tema_preference: Optional[str] = None

    @field_validator("m_dot_hot", "m_dot_cold", mode="before")
    @classmethod
    def _flow_must_be_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError(f"Flow rate must be positive, got {v}")
        return v


# ========================== AMBIGUOUS FLUIDS ==============================

_AMBIGUOUS_FLUIDS = {"oil", "gas", "fluid", "liquid", "chemical", "solvent"}

# Known fluid names for NL matching
_KNOWN_FLUIDS = [
    "crude oil", "thermal oil", "vegetable oil", "mineral oil",
    "cooling water", "chilled water", "sea water", "seawater",
    "hot water", "boiler water",
    "water", "steam", "condensate",
    "ethanol", "methanol", "glycol", "ethylene glycol",
    "propylene glycol", "ammonia", "kerosene", "diesel",
    "naphtha", "gasoline", "toluene", "benzene", "xylene",
    "acetone", "hexane", "heptane", "pentane",
    "nitrogen", "air", "hydrogen", "oxygen",
    "brine", "molten salt",
]


# ========================== NL REGEX PATTERNS ==============================

# Temperature: "150°C", "302 °F", "373.15 K", "from 150 to 90°C"
_RE_TEMP = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*°?\s*(C|F|K|celsius|fahrenheit|kelvin)\b",
    re.IGNORECASE,
)

# "from X to Y °C/F/K"
_RE_TEMP_RANGE = re.compile(
    r"from\s+(-?\d+(?:\.\d+)?)\s*(?:°?\s*(?:C|F|K))?"
    r"\s+to\s+(-?\d+(?:\.\d+)?)\s*°?\s*(C|F|K|celsius|fahrenheit|kelvin)",
    re.IGNORECASE,
)

# Flow rate: "50 kg/s", "110000 lb/hr", "100 m³/hr"
_RE_FLOW = re.compile(
    r"(\d+(?:\.\d+)?)\s*(kg/?s|lb/?hr?|lbs?/?hr?|m[³3]/?hr?)\b",
    re.IGNORECASE,
)

# Pressure: "5 bar", "100 psi", "500 kPa"
_RE_PRESSURE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(bar|psi|kPa|Pa|atm)\b",
    re.IGNORECASE,
)

# TEMA preference keywords
_RE_TEMA = re.compile(
    r"(floating\s+head|fixed\s+tube\s*sheet|u[- ]?tube|pull[- ]?through)",
    re.IGNORECASE,
)

# Directional verbs
_RE_COOLING = re.compile(r"\bcool(?:ing|ed|s)?\b", re.IGNORECASE)
_RE_HEATING = re.compile(r"\bheat(?:ing|ed|s)?\b", re.IGNORECASE)


# ========================== STEP 01 =======================================

class Step01Requirements(BaseStep):
    step_id: int = 1
    step_name: str = "Process Requirements"
    ai_mode: AIModeEnum = AIModeEnum.FULL

    # ------------------------------------------------------------------
    # execute() — entry point
    # ------------------------------------------------------------------

    async def execute(self, state: DesignState) -> StepResult:
        """Try structured JSON first; fall back to NL parsing."""
        raw = state.raw_request.strip()
        if not raw:
            return StepResult(
                step_id=self.step_id,
                step_name=self.step_name,
                validation_passed=False,
                validation_errors=["Empty request — nothing to parse"],
            )

        # Attempt JSON
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return self._from_structured(state, data)
        except (json.JSONDecodeError, TypeError):
            pass

        # Fall back to NL
        return self._from_natural_language(state, raw)

    # ------------------------------------------------------------------
    # Structured path
    # ------------------------------------------------------------------

    def _from_structured(
        self,
        state: DesignState,
        data: dict[str, Any],
    ) -> StepResult:
        errors: list[str] = []
        warnings: list[str] = []

        try:
            inp = DesignInput(**data)
        except Exception as exc:
            return StepResult(
                step_id=self.step_id,
                step_name=self.step_name,
                validation_passed=False,
                validation_errors=[str(exc)],
            )

        # Convert temps
        T_hot_in = detect_and_convert_temperature(inp.T_hot_in, inp.temp_unit)
        T_hot_out = (
            detect_and_convert_temperature(inp.T_hot_out, inp.temp_unit)
            if inp.T_hot_out is not None
            else None
        )
        T_cold_in = detect_and_convert_temperature(inp.T_cold_in, inp.temp_unit)
        T_cold_out = (
            detect_and_convert_temperature(inp.T_cold_out, inp.temp_unit)
            if inp.T_cold_out is not None
            else None
        )

        # Convert flow
        m_dot_hot = detect_and_convert_flow_rate(inp.m_dot_hot, inp.flow_unit)
        m_dot_cold = (
            detect_and_convert_flow_rate(inp.m_dot_cold, inp.flow_unit)
            if inp.m_dot_cold is not None
            else None
        )

        # Convert pressure
        pressure_Pa = (
            detect_and_convert_pressure(inp.pressure, inp.pressure_unit)
            if inp.pressure is not None
            else 101325.0
        )

        # Physics warnings
        if T_hot_out is not None and T_hot_in < T_hot_out:
            warnings.append(
                "Hot stream gaining heat — T_hot_in < T_hot_out"
            )
        if (
            T_cold_out is not None
            and T_cold_in > T_cold_out
        ):
            warnings.append(
                "Cold stream losing heat — T_cold_in > T_cold_out"
            )
        if T_cold_out is not None and T_cold_out > T_hot_in:
            warnings.append(
                "Temperature cross — T_cold_out > T_hot_in"
            )

        missing_T_cold_out = T_cold_out is None
        missing_m_dot_cold = m_dot_cold is None

        outputs: dict[str, Any] = {
            "hot_fluid_name": inp.hot_fluid,
            "cold_fluid_name": inp.cold_fluid,
            "T_hot_in_C": T_hot_in,
            "T_hot_out_C": T_hot_out,
            "T_cold_in_C": T_cold_in,
            "T_cold_out_C": T_cold_out,
            "m_dot_hot_kg_s": m_dot_hot,
            "m_dot_cold_kg_s": m_dot_cold,
            "P_hot_Pa": pressure_Pa,
            "P_cold_Pa": pressure_Pa,
            "missing_T_cold_out": missing_T_cold_out,
            "missing_m_dot_cold": missing_m_dot_cold,
        }
        if inp.tema_class:
            outputs["tema_class"] = inp.tema_class
        if inp.tema_preference:
            outputs["tema_preference"] = inp.tema_preference

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            validation_passed=len(errors) == 0,
            validation_errors=errors,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Natural-language path
    # ------------------------------------------------------------------

    def _from_natural_language(
        self,
        state: DesignState,
        text: str,
    ) -> StepResult:
        errors: list[str] = []
        warnings: list[str] = []
        outputs: dict[str, Any] = {}

        # --- Extract fluids ---
        hot_fluid, cold_fluid = self._extract_fluids(text, errors)
        outputs["hot_fluid_name"] = hot_fluid
        outputs["cold_fluid_name"] = cold_fluid

        # --- Extract temperatures ---
        temps = self._extract_temperatures(text)
        if len(temps) < 3:
            errors.append(
                f"Found only {len(temps)} temperature(s) — need at least 3"
            )

        # Assign temps to hot/cold based on context
        self._assign_temperatures(text, temps, outputs, warnings)

        # --- Extract flow rate ---
        flows = self._extract_flows(text)
        if not flows:
            errors.append("No flow rate found in request")
        else:
            self._assign_flows(text, flows, outputs)

        # --- Optional: pressure ---
        pressure_match = _RE_PRESSURE.search(text)
        if pressure_match:
            p_val = float(pressure_match.group(1))
            p_unit = pressure_match.group(2)
            p_pa = detect_and_convert_pressure(p_val, p_unit)
            outputs["P_hot_Pa"] = p_pa
            outputs["P_cold_Pa"] = p_pa
        else:
            outputs["P_hot_Pa"] = 101325.0
            outputs["P_cold_Pa"] = 101325.0

        # --- Optional: TEMA preference ---
        tema_match = _RE_TEMA.search(text)
        if tema_match:
            outputs["tema_preference"] = tema_match.group(1).lower()

        # --- Mark missing fields ---
        outputs.setdefault("T_cold_out_C", None)
        outputs.setdefault("T_hot_out_C", None)
        outputs["missing_T_cold_out"] = outputs.get("T_cold_out_C") is None
        outputs["missing_m_dot_cold"] = outputs.get("m_dot_cold_kg_s") is None

        # Physics warnings on extracted temps
        T_hot_in = outputs.get("T_hot_in_C")
        T_hot_out = outputs.get("T_hot_out_C")
        T_cold_in = outputs.get("T_cold_in_C")
        T_cold_out = outputs.get("T_cold_out_C")

        if T_hot_in is not None and T_hot_out is not None:
            if T_hot_in < T_hot_out:
                warnings.append(
                    "Hot stream gaining heat — T_hot_in < T_hot_out"
                )
        if T_cold_in is not None and T_cold_out is not None:
            if T_cold_in > T_cold_out:
                warnings.append(
                    "Cold stream losing heat — T_cold_in > T_cold_out"
                )
        if T_cold_out is not None and T_hot_in is not None:
            if T_cold_out > T_hot_in:
                warnings.append(
                    "Temperature cross — T_cold_out > T_hot_in"
                )

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            validation_passed=len(errors) == 0,
            validation_errors=errors,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # NL helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_fluids(
        text: str, errors: list[str]
    ) -> tuple[Optional[str], Optional[str]]:
        """Find fluid names in text. Returns (hot_fluid, cold_fluid)."""
        text_lower = text.lower()
        found: list[str] = []
        for fluid in sorted(_KNOWN_FLUIDS, key=len, reverse=True):
            if fluid in text_lower:
                found.append(fluid)
                # Remove ALL occurrences to avoid ambiguous-bare-word false positives
                text_lower = text_lower.replace(fluid, "")

        # Check for ambiguous bare words
        remaining = text_lower
        for ambig in _AMBIGUOUS_FLUIDS:
            if re.search(rf"\b{ambig}\b", remaining, re.IGNORECASE):
                errors.append(
                    f"'{ambig}' is ambiguous — please specify "
                    f"(e.g. 'crude oil', 'thermal oil')"
                )

        hot_fluid: Optional[str] = None
        cold_fluid: Optional[str] = None

        if len(found) >= 2:
            # Heuristic: first mentioned is usually the process fluid
            # Determine hot/cold from context
            hot_fluid, cold_fluid = _assign_fluid_sides(text, found)
        elif len(found) == 1:
            # Single fluid — likely paired with water
            hot_fluid = found[0]
            cold_fluid = None
            if not errors:
                errors.append("Only one fluid identified — need both hot and cold sides")
        else:
            if not errors:
                errors.append("No recognisable fluid names found")

        return hot_fluid, cold_fluid

    @staticmethod
    def _extract_temperatures(
        text: str,
    ) -> list[tuple[float, str]]:
        """Return list of (value_in_celsius, original_unit)."""
        results: list[tuple[float, str]] = []

        # First try "from X to Y unit" patterns
        for m in _RE_TEMP_RANGE.finditer(text):
            unit = m.group(3)
            v1 = float(m.group(1))
            v2 = float(m.group(2))
            results.append((detect_and_convert_temperature(v1, unit), unit))
            results.append((detect_and_convert_temperature(v2, unit), unit))

        # Then individual temps not already captured
        range_spans = [m.span() for m in _RE_TEMP_RANGE.finditer(text)]
        for m in _RE_TEMP.finditer(text):
            # Skip if inside a range match
            start, end = m.span()
            if any(rs <= start and end <= re for rs, re in range_spans):
                continue
            val = float(m.group(1))
            unit = m.group(2)
            results.append((detect_and_convert_temperature(val, unit), unit))

        return results

    @staticmethod
    def _extract_flows(
        text: str,
    ) -> list[tuple[float, str]]:
        """Return list of (value_in_kg_s, original_unit)."""
        results: list[tuple[float, str]] = []
        for m in _RE_FLOW.finditer(text):
            val = float(m.group(1))
            unit = m.group(2)
            results.append((detect_and_convert_flow_rate(val, unit), unit))
        return results

    @staticmethod
    def _assign_temperatures(
        text: str,
        temps: list[tuple[float, str]],
        outputs: dict[str, Any],
        warnings: list[str],
    ) -> None:
        """Heuristic assignment of extracted temps to hot/cold sides."""
        if not temps:
            return

        values = [t[0] for t in temps]

        is_cooling = bool(_RE_COOLING.search(text))
        is_heating = bool(_RE_HEATING.search(text))

        if len(values) >= 4:
            # Sort: highest two become hot side, lowest two become cold side
            sorted_vals = sorted(values, reverse=True)
            outputs["T_hot_in_C"] = sorted_vals[0]
            outputs["T_hot_out_C"] = sorted_vals[1]
            outputs["T_cold_out_C"] = sorted_vals[2]
            outputs["T_cold_in_C"] = sorted_vals[3]
        elif len(values) == 3:
            sorted_vals = sorted(values, reverse=True)
            if is_cooling:
                # "cooling X from A to B using Y at C"
                outputs["T_hot_in_C"] = sorted_vals[0]
                outputs["T_hot_out_C"] = sorted_vals[1]
                outputs["T_cold_in_C"] = sorted_vals[2]
            elif is_heating:
                # "heating Y from A to B using X at C"
                outputs["T_cold_in_C"] = sorted_vals[2]
                outputs["T_cold_out_C"] = sorted_vals[1]
                outputs["T_hot_in_C"] = sorted_vals[0]
            else:
                # Default: highest is hot in, next is hot out, lowest is cold in
                outputs["T_hot_in_C"] = sorted_vals[0]
                outputs["T_hot_out_C"] = sorted_vals[1]
                outputs["T_cold_in_C"] = sorted_vals[2]
        elif len(values) == 2:
            sorted_vals = sorted(values, reverse=True)
            outputs["T_hot_in_C"] = sorted_vals[0]
            outputs["T_cold_in_C"] = sorted_vals[1]
        elif len(values) == 1:
            outputs["T_hot_in_C"] = values[0]

    @staticmethod
    def _assign_flows(
        text: str,
        flows: list[tuple[float, str]],
        outputs: dict[str, Any],
    ) -> None:
        """Assign extracted flow rates to hot/cold sides."""
        if len(flows) >= 2:
            outputs["m_dot_hot_kg_s"] = flows[0][0]
            outputs["m_dot_cold_kg_s"] = flows[1][0]
        elif len(flows) == 1:
            outputs["m_dot_hot_kg_s"] = flows[0][0]


# ---------------------------------------------------------------------------
# Fluid side assignment helper
# ---------------------------------------------------------------------------

_COLD_INDICATORS = {
    "cooling water", "chilled water", "cold water", "sea water",
    "seawater", "brine", "water",
}


def _assign_fluid_sides(
    text: str, found: list[str]
) -> tuple[Optional[str], Optional[str]]:
    """Given found fluids and the original text, decide hot vs cold."""
    is_cooling = bool(_RE_COOLING.search(text))

    # If one fluid is a known cold utility, assign it cold
    hot_candidates = []
    cold_candidates = []
    for f in found:
        if f.lower() in _COLD_INDICATORS:
            cold_candidates.append(f)
        else:
            hot_candidates.append(f)

    if hot_candidates and cold_candidates:
        return hot_candidates[0], cold_candidates[0]

    # Fallback: if "cooling" context, first mentioned is hot
    if is_cooling and len(found) >= 2:
        return found[0], found[1]

    # Default: first = hot, second = cold
    if len(found) >= 2:
        return found[0], found[1]

    return found[0] if found else None, None
