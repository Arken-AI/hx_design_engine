"""Requirements validator — Layer 1 (schema) + Layer 2 (physics) + HMAC token.

Used by POST /requirements (stateless endpoint) and POST /design (inline fallback).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from hx_engine.app.config import settings

# ---------------------------------------------------------------------------
# Error / Warning containers
# ---------------------------------------------------------------------------

@dataclass
class ValidationError:
    field: str
    message: str
    suggestion: str = ""
    valid_range: str = ""


@dataclass
class ValidationWarning:
    field: str
    message: str


@dataclass
class ValidationResult:
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# Known fluids (for warning-only name check)
# ---------------------------------------------------------------------------

_KNOWN_FLUIDS = {
    "crude oil", "thermal oil", "vegetable oil", "mineral oil",
    "cooling water", "chilled water", "sea water", "seawater",
    "hot water", "boiler water",
    "water", "steam", "condensate",
    "ethanol", "methanol", "glycol", "ethylene glycol",
    "propylene glycol", "ammonia", "kerosene", "diesel",
    "diesel fuel", "lube oil", "lubricating oil",
    "heavy fuel oil", "hfo", "fuel oil", "bunker fuel",
    "naphtha", "gasoline", "toluene", "benzene", "xylene",
    "acetone", "hexane", "heptane", "pentane",
    "nitrogen", "air", "hydrogen", "oxygen",
    "brine", "molten salt",
}

_VALID_TEMA = {"AES", "BEM", "AEU", "AEP", "AEL", "AEW"}

# Temperature bounds (°C)
_TEMP_MIN = -50.0
_TEMP_MAX = 1000.0

# Minimum approach temperature (°C)
_MIN_APPROACH_C = 3.0

# Petroleum correlation validity ceiling (°C)
# Crude oil correlations (Lee-Kesler, Beggs-Robinson, Cragoe) are typically
# reliable up to ~350°C; extrapolation beyond this range is uncertain.
_PETROLEUM_TEMP_LIMIT_C = 350.0
_PETROLEUM_KEYWORDS = frozenset({
    "crude", "crude oil", "naphtha", "kerosene", "diesel",
    "gas oil", "fuel oil", "heavy fuel oil", "hfo", "bunker fuel",
    "lube oil", "lubricating oil", "heating oil",
})


# ---------------------------------------------------------------------------
# Layer 1 — schema / completeness checks
# ---------------------------------------------------------------------------

def _layer1(data: dict[str, Any]) -> tuple[list[ValidationError], list[ValidationWarning]]:
    errors: list[ValidationError] = []
    warnings: list[ValidationWarning] = []

    # --- Required fields ---
    for fname in ("hot_fluid_name", "cold_fluid_name"):
        v = data.get(fname)
        if not v or not str(v).strip():
            errors.append(ValidationError(
                field=fname,
                message=f"{fname} is required",
                suggestion=f"Provide a fluid name, e.g. 'crude oil' or 'water'",
            ))

    for fname in ("T_hot_in_C", "T_cold_in_C"):
        if data.get(fname) is None:
            errors.append(ValidationError(
                field=fname,
                message=f"{fname} is required",
                suggestion=f"Provide the {'hot' if 'hot' in fname else 'cold'} inlet temperature in °C",
            ))

    if data.get("m_dot_hot_kg_s") is None:
        errors.append(ValidationError(
            field="m_dot_hot_kg_s",
            message="m_dot_hot_kg_s is required (hot-side flow rate)",
            suggestion="Provide the hot-side mass flow rate in kg/s",
        ))

    # --- Range checks on any provided temperature ---
    temp_fields = ("T_hot_in_C", "T_hot_out_C", "T_cold_in_C", "T_cold_out_C")
    for fname in temp_fields:
        v = data.get(fname)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            errors.append(ValidationError(field=fname, message=f"{fname} must be a number"))
            continue
        if not (_TEMP_MIN <= v <= _TEMP_MAX):
            errors.append(ValidationError(
                field=fname,
                message=f"{fname}={v}°C outside physical range [{_TEMP_MIN}, {_TEMP_MAX}]°C",
                valid_range=f"[{_TEMP_MIN}, {_TEMP_MAX}]°C",
            ))

    # --- Range checks on flow rates ---
    flow_fields = ("m_dot_hot_kg_s", "m_dot_cold_kg_s")
    for fname in flow_fields:
        v = data.get(fname)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            errors.append(ValidationError(field=fname, message=f"{fname} must be a number"))
            continue
        if v <= 0:
            errors.append(ValidationError(
                field=fname,
                message=f"{fname} must be positive, got {v}",
                valid_range="> 0",
            ))

    # --- Range checks on pressures ---
    pressure_fields = ("P_hot_Pa", "P_cold_Pa")
    for fname in pressure_fields:
        v = data.get(fname)
        if v is None:
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            errors.append(ValidationError(field=fname, message=f"{fname} must be a number"))
            continue
        if v <= 0:
            errors.append(ValidationError(
                field=fname,
                message=f"{fname} must be positive, got {v}",
                valid_range="> 0",
            ))

    # --- Optional: tema_preference allow-list ---
    tema = data.get("tema_preference")
    if tema and str(tema).upper() not in _VALID_TEMA:
        errors.append(ValidationError(
            field="tema_preference",
            message=f"Unknown TEMA type '{tema}' — allowed: {', '.join(sorted(_VALID_TEMA))}",
            valid_range=", ".join(sorted(_VALID_TEMA)),
        ))

    # --- Optional: fluid name warning ---
    for fname in ("hot_fluid_name", "cold_fluid_name"):
        v = data.get(fname)
        if v and str(v).strip().lower() not in _KNOWN_FLUIDS:
            warnings.append(ValidationWarning(
                field=fname,
                message=(
                    f"'{v}' not in known fluid list — the engine will attempt "
                    f"partial matching and petroleum correlations, but verify "
                    f"properties in Step 3 output"
                ),
            ))

    return errors, warnings


# ---------------------------------------------------------------------------
# Layer 2 — physics feasibility (fires only when all required fields present)
# ---------------------------------------------------------------------------

def _layer2(data: dict[str, Any]) -> tuple[list[ValidationError], list[ValidationWarning]]:
    errors: list[ValidationError] = []
    warnings: list[ValidationWarning] = []

    T_hot_in = data.get("T_hot_in_C")
    T_hot_out = data.get("T_hot_out_C")
    T_cold_in = data.get("T_cold_in_C")
    T_cold_out = data.get("T_cold_out_C")

    # Hot inlet must be hotter than cold inlet (basic sanity)
    if T_hot_in is not None and T_cold_in is not None:
        if T_hot_in <= T_cold_in:
            errors.append(ValidationError(
                field="T_hot_in_C",
                message=(
                    f"Hot inlet ({T_hot_in}°C) must be hotter than "
                    f"cold inlet ({T_cold_in}°C)"
                ),
                suggestion="Check that the hot and cold streams are not swapped",
                valid_range=f"> {T_cold_in}°C",
            ))

    # Hot fluid must cool
    if T_hot_in is not None and T_hot_out is not None:
        if T_hot_out >= T_hot_in:
            errors.append(ValidationError(
                field="T_hot_out_C",
                message=f"Hot fluid must cool: T_hot_out ({T_hot_out}°C) >= T_hot_in ({T_hot_in}°C)",
                suggestion=f"T_hot_out_C must be less than T_hot_in_C ({T_hot_in}°C)",
                valid_range=f"< {T_hot_in}°C",
            ))

    # Cold fluid must heat
    if T_cold_in is not None and T_cold_out is not None:
        if T_cold_out <= T_cold_in:
            errors.append(ValidationError(
                field="T_cold_out_C",
                message=f"Cold fluid must heat: T_cold_out ({T_cold_out}°C) <= T_cold_in ({T_cold_in}°C)",
                suggestion=f"T_cold_out_C must be greater than T_cold_in_C ({T_cold_in}°C)",
                valid_range=f"> {T_cold_in}°C",
            ))

    # Temperature cross: T_cold_out < T_hot_in
    if T_cold_out is not None and T_hot_in is not None:
        if T_cold_out >= T_hot_in:
            errors.append(ValidationError(
                field="T_cold_out_C",
                message=f"Temperature cross: T_cold_out ({T_cold_out}°C) >= T_hot_in ({T_hot_in}°C)",
                suggestion="Reduce T_cold_out or increase T_hot_in",
                valid_range=f"< {T_hot_in}°C",
            ))

    # Temperature cross: T_cold_in < T_hot_out
    if T_cold_in is not None and T_hot_out is not None:
        if T_cold_in >= T_hot_out:
            errors.append(ValidationError(
                field="T_cold_in_C",
                message=f"Temperature cross: T_cold_in ({T_cold_in}°C) >= T_hot_out ({T_hot_out}°C)",
                suggestion="Reduce T_cold_in or increase T_hot_out",
                valid_range=f"< {T_hot_out}°C",
            ))

    # Minimum approach temperature (only when all 4 temps present)
    if all(t is not None for t in (T_hot_in, T_hot_out, T_cold_in, T_cold_out)):
        delta1 = T_hot_in - T_cold_out   # hot inlet vs cold outlet
        delta2 = T_hot_out - T_cold_in   # hot outlet vs cold inlet
        min_approach = min(delta1, delta2)
        if min_approach < _MIN_APPROACH_C:
            errors.append(ValidationError(
                field="T_hot_out_C",
                message=f"Min approach {min_approach:.1f}°C < {_MIN_APPROACH_C}°C — HX would be infinitely large",
                suggestion=f"Increase the temperature difference by at least {_MIN_APPROACH_C - min_approach:.1f}°C",
                valid_range=f">= {_MIN_APPROACH_C}°C",
            ))

        # R-factor warning (not an error)
        delta_T_hot = T_hot_in - T_hot_out
        delta_T_cold = T_cold_out - T_cold_in
        if delta_T_cold > 0:
            R = delta_T_hot / delta_T_cold
            if R > 20:
                warnings.append(ValidationWarning(
                    field="T_hot_out_C",
                    message=f"R={R:.1f} is very high — may need multiple shells",
                ))
            elif R > 3:
                warnings.append(ValidationWarning(
                    field="T_hot_out_C",
                    message=(
                        f"R={R:.1f} (> 3) — F-factor is highly sensitive to "
                        f"operating point drift at this ratio. Small temperature "
                        f"deviations may cause large F-factor changes."
                    ),
                ))
        elif delta_T_cold == 0:
            warnings.append(ValidationWarning(
                field="T_cold_out_C",
                message="T_cold_out equals T_cold_in — cold fluid shows no temperature rise",
            ))

    # Petroleum correlation validity range warning
    # Crude oil correlations are reliable up to ~350°C; flag any petroleum
    # fluid whose inlet temperature approaches or exceeds this limit.
    for fluid_field, temp_field in [
        ("hot_fluid_name", "T_hot_in_C"),
        ("cold_fluid_name", "T_cold_in_C"),
    ]:
        fluid_name = data.get(fluid_field)
        temp_val = data.get(temp_field)
        if fluid_name and temp_val is not None:
            name_lower = str(fluid_name).strip().lower()
            is_petroleum = (
                name_lower in _PETROLEUM_KEYWORDS
                or any(kw in name_lower for kw in _PETROLEUM_KEYWORDS)
            )
            if is_petroleum and float(temp_val) >= _PETROLEUM_TEMP_LIMIT_C:
                warnings.append(ValidationWarning(
                    field=temp_field,
                    message=(
                        f"{fluid_name} at {temp_val}°C is at or beyond the "
                        f"petroleum correlation validity range (~{_PETROLEUM_TEMP_LIMIT_C:.0f}°C). "
                        f"Property predictions (especially viscosity) may be unreliable. "
                        f"Consider providing measured properties."
                    ),
                ))

    # Underdetermined system check: the energy balance in Step 2 needs enough
    # knowns to solve for every unknown temperature.  The rules are:
    #
    #  1. If NEITHER T_hot_out NOR T_cold_out NOR m_dot_cold is given → fail
    #     (nothing to constrain the balance at all).
    #
    #  2. If T_hot_out is given but BOTH T_cold_out AND m_dot_cold are missing
    #     → fail.  Step 2 can compute Q from the hot side, but cannot
    #     back-calculate T_cold_out without knowing m_dot_cold.
    #
    # (Only run when no errors so far.)
    if not errors:
        has_T_hot_out = T_hot_out is not None
        has_T_cold_out = T_cold_out is not None
        has_m_dot_cold = data.get("m_dot_cold_kg_s") is not None

        if not any((has_T_hot_out, has_T_cold_out, has_m_dot_cold)):
            errors.append(ValidationError(
                field="T_cold_out_C",
                message=(
                    "Underdetermined: provide at least one of "
                    "T_hot_out_C, T_cold_out_C, or m_dot_cold_kg_s "
                    "so Step 2 can close the energy balance"
                ),
                suggestion="Add the cold outlet temperature (most common) or cold-side flow rate",
            ))
        elif has_T_hot_out and not has_T_cold_out and not has_m_dot_cold:
            errors.append(ValidationError(
                field="T_cold_out_C",
                message=(
                    "Cold side underdetermined: T_hot_out_C is given but both "
                    "T_cold_out_C and m_dot_cold_kg_s are missing — the engine "
                    "cannot compute the cold outlet temperature"
                ),
                suggestion=(
                    "Provide either T_cold_out_C (cold outlet temperature in °C) "
                    "or m_dot_cold_kg_s (cold-side mass flow rate in kg/s)"
                ),
            ))

    return errors, warnings


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def validate_requirements(data: dict[str, Any]) -> ValidationResult:
    """Run Layer 1 then Layer 2 (if L1 passes) on a design input dict.

    Returns a ValidationResult with errors and warnings.
    Layer 2 only runs when Layer 1 passes — no point checking physics
    when required fields are missing.
    """
    l1_errors, l1_warnings = _layer1(data)
    result = ValidationResult(errors=l1_errors, warnings=l1_warnings)

    if result.valid:
        l2_errors, l2_warnings = _layer2(data)
        result.errors.extend(l2_errors)
        result.warnings.extend(l2_warnings)

    return result


# ---------------------------------------------------------------------------
# HMAC token — stateless proof that /requirements ran on these inputs
# ---------------------------------------------------------------------------

def _canonical_payload(design_input: dict[str, Any], minute: str) -> bytes:
    """Deterministic JSON + unix-minute string, sorted keys."""
    return (json.dumps(design_input, sort_keys=True) + minute).encode()


def sign_token(design_input: dict[str, Any]) -> str:
    """HMAC-SHA256 of canonical JSON + current unix-minute."""
    minute = str(int(time.time()) // 60)
    payload = _canonical_payload(design_input, minute)
    return hmac.new(
        settings.hx_engine_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()


def verify_token(token: str, design_input: dict[str, Any]) -> bool:
    """Accept tokens from current minute or previous (±1 min tolerance).

    Uses hmac.compare_digest to prevent timing attacks.
    """
    current_minute = int(time.time()) // 60
    for offset in (0, -1):
        minute = str(current_minute + offset)
        payload = _canonical_payload(design_input, minute)
        expected = hmac.new(
            settings.hx_engine_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(token, expected):
            return True
    return False


# ---------------------------------------------------------------------------
# User-facing summary message
# ---------------------------------------------------------------------------

def build_user_message(data: dict[str, Any], warnings: list[ValidationWarning]) -> str:
    """Build a concise user-facing confirmation message for Claude to relay."""
    parts = []

    hot = data.get("hot_fluid_name", "hot fluid")
    cold = data.get("cold_fluid_name", "cold fluid")
    T_hi = data.get("T_hot_in_C")
    T_ho = data.get("T_hot_out_C")
    T_ci = data.get("T_cold_in_C")
    T_co = data.get("T_cold_out_C")
    m_hot = data.get("m_dot_hot_kg_s")

    # Fluid summary
    fluid_line = f"{hot.title()} → {cold.title()}"
    parts.append(fluid_line)

    # Temperature summary
    if T_hi is not None and T_ho is not None:
        parts.append(f"Hot: {T_hi}→{T_ho}°C")
    elif T_hi is not None:
        parts.append(f"Hot inlet: {T_hi}°C")

    if T_ci is not None and T_co is not None:
        parts.append(f"Cold: {T_ci}→{T_co}°C")
    elif T_ci is not None:
        parts.append(f"Cold inlet: {T_ci}°C")

    if m_hot is not None:
        parts.append(f"Flow: {m_hot} kg/s (hot side)")

    # Rough Q estimate when all 4 temps + m_dot_hot known
    if all(t is not None for t in (T_hi, T_ho, T_ci, T_co)) and m_hot is not None:
        Cp_approx = 2000.0  # J/(kg·K) — generic conservative estimate
        Q_kW = abs(m_hot * Cp_approx * (T_hi - T_ho)) / 1000
        parts.append(f"Q≈{Q_kW:.0f} kW (rough estimate)")

    summary = ", ".join(parts)
    msg = f"Requirements valid. {summary}. Ready to design."

    if warnings:
        warn_str = "; ".join(w.message for w in warnings)
        msg += f" Notes: {warn_str}"

    return msg
