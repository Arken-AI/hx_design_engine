"""Step 4 — TEMA Type Selection + Initial Geometry.

This is the first 'engineering judgment' step. AI always reviews (FULL mode)
because TEMA type choice has cascading effects on every downstream calculation.

Pieces implemented here:
  4 — Fluid Allocation (_allocate_fluids)
  5 — TEMA Type Selection (_select_tema_type)
  6 — Initial Geometry Heuristics (_select_initial_geometry)
  7 — Core execute() wiring
  9 — Escalation hints
"""

from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.data.bwg_gauge import get_tube_id, get_wall_thickness
from hx_engine.app.data.fouling_factors import (
    classify_fouling,
    get_fouling_factor,
    get_fouling_factor_with_source,
    get_fouling_lower_bound,
    is_fouling_fluid,
    is_location_dependent,
    resolve_fouling_factor,
)
from hx_engine.app.data.tema_tables import (
    find_shell_diameter,
    get_bundle_to_shell_clearance_m,
    get_tube_count,
)
from hx_engine.app.data.u_assumptions import classify_fluid_type, get_U_assumption
from hx_engine.app.models.design_state import FluidProperties, GeometrySpec
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState
    from hx_engine.app.models.step_result import AICorrection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Valid TEMA types (Phase 1)
# ---------------------------------------------------------------------------

# AEL (lantern-ring floating head, low-fin tubes) intentionally excluded:
# no selection path produces it and no downstream geometry support exists
# (low-fin tubes / fin efficiency). Deferred to Phase 2 alongside P3-30.
VALID_TEMA_TYPES = frozenset({"BEM", "AES", "AEP", "AEU", "AEW"})

# Pressure threshold for high-pressure rule (Pa)
_HIGH_PRESSURE_PA = 30e5  # 30 bar
_VERY_HIGH_PRESSURE_PA = 70e5  # 70 bar

# P2-14 — thermal-expansion threshold is interpreted as the **tubesheet
# differential** (|T_shell_mean − T_tube_mean|), not the four-temperature
# stream span. 50 K matches Serth §3 / TEMA Table RGP-G-7 fixed-tubesheet
# practice (no expansion joint required up to ~50–60 K differential).
_DT_EXPANSION_THRESHOLD = 50.0  # K, tubesheet differential

# Fluids that should go shell-side with floating-head (AES/AEU) geometry
# for mechanical cleaning access — standard refinery practice
_SHELL_SIDE_CRUDE_OILS = {"crude oil", "crude", "heavy hydrocarbon", "heavy hydrocarbons", "fuel oil"}

# Duty thresholds for warnings
_SMALL_DUTY_W = 50_000       # 50 kW
_LARGE_DUTY_W = 50_000_000   # 50 MW

# P2-15 — Length-to-shell-diameter ratio bands.
# Inside [5, 10] is the engineering sweet spot for shell-and-tube units.
# WARN bands flag economically suboptimal proportions; the ESCALATE
# extremes (3, 15) are enforced via Layer 2 rule
# `_rule_ld_ratio_within_extremes` and surface as user decisions.
LD_RATIO_LOW_WARN: float = 5.0
LD_RATIO_HIGH_WARN: float = 10.0
LD_RATIO_LOW_ESCALATE: float = 3.0
LD_RATIO_HIGH_ESCALATE: float = 15.0


# ---------------------------------------------------------------------------
# P2-12 — Toxic-fluid keyword sets and helpers
# ---------------------------------------------------------------------------
# Tube-side allocation for toxic streams keeps any leak inside the tube
# bundle (easier to isolate and replace than a leaking shell).
# Sources: API 660 §6.4, NACE MR0175, Perry §10.
_TOXIC_KEYWORDS = frozenset({
    "h2s", "hydrogen sulfide", "sour",
    "chlorine", "cl2",
    "ammonia", "nh3",
    "phosgene",
    "hcn", "hydrogen cyanide", "cyanide",
    "hf", "hydrogen fluoride",
    "benzene",
    "co", "carbon monoxide",
})

# Subset that triggers double-tubesheet evaluation in Step 14.
_HIGHLY_TOXIC_KEYWORDS = frozenset({
    "phosgene",
    "hcn", "hydrogen cyanide", "cyanide",
    "hf", "hydrogen fluoride",
    "chlorine", "cl2",
})


def _keyword_matches(name: str | None, keywords) -> bool:
    """Word-boundary keyword match against a fluid name.

    Uses ``\\b`` so short tokens (``co``, ``hf``, ``h2s``) don't trigger
    false positives on substrings like ``carbon dioxide``, ``H2SO4``, or
    ``ethylene glycol``.  Multi-word keywords still match because ``\\b``
    surrounds the whole phrase.
    """
    if not name:
        return False
    lowered = name.lower()
    for kw in keywords:
        if re.search(rf"\b{re.escape(kw)}\b", lowered):
            return True
    return False


def _is_toxic(name: str | None) -> bool:
    return _keyword_matches(name, _TOXIC_KEYWORDS)


def _is_highly_toxic(name: str | None) -> bool:
    return _keyword_matches(name, _HIGHLY_TOXIC_KEYWORDS)


# ---------------------------------------------------------------------------
# P2-11 — Corrosive-fluid keyword set, severity ranking, and helpers
# ---------------------------------------------------------------------------
# Corrosive streams go tube-side so the (typically more expensive)
# corrosion-resistant alloy is required only for tubes, not the shell.
# Sources: TEMA RGP-RCB, Serth §3, NACE MR0175.
_CORROSIVE_KEYWORDS = frozenset({
    "acid", "caustic", "corrosive",
    "hf", "hydrogen fluoride", "phosgene",
    "hcl", "hydrochloric",
    "h2so4", "sulfuric",
    "hno3", "nitric",
    "chloride",
})

# Ordered most → least aggressive (used to pick which side goes tube
# when both streams are corrosive). Lower index = more aggressive.
# Each inner frozenset is a synonym group — all members share the same rank
# so "hf" and "hydrogen fluoride" are treated identically.
# Sources: NACE MR0175, Perry §23, ASTM G31.
_CORROSIVE_SEVERITY_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"hf", "hydrogen fluoride"}),   # extreme — SCC + tube failure risk
    frozenset({"phosgene"}),                  # extreme + toxic
    frozenset({"hcl", "hydrochloric"}),       # halide acid
    frozenset({"h2so4", "sulfuric"}),         # strong acid
    frozenset({"hno3", "nitric"}),            # oxidising acid
    frozenset({"chloride"}),                  # SCC risk for SS
    frozenset({"caustic"}),                   # NaOH / KOH
    frozenset({"acid"}),                      # generic acid catch-all
    frozenset({"corrosive"}),                 # generic catch-all
)


def _is_corrosive(name: str | None) -> bool:
    return _keyword_matches(name, _CORROSIVE_KEYWORDS)


def _corrosive_severity_rank(name: str | None) -> int:
    """Return severity group index (lower = more aggressive).

    Returns ``len(_CORROSIVE_SEVERITY_GROUPS)`` when no keyword matches.
    All synonyms within a group share the same rank.
    """
    if not name:
        return len(_CORROSIVE_SEVERITY_GROUPS)
    lowered = name.lower()
    for idx, group in enumerate(_CORROSIVE_SEVERITY_GROUPS):
        for keyword in group:
            if re.search(rf"\b{re.escape(keyword)}\b", lowered):
                return idx
    return len(_CORROSIVE_SEVERITY_GROUPS)


def _compute_tubesheet_differential(
    state: "DesignState", shell_side: str,
) -> tuple[float, float, str]:
    """Return ``(delta_T_tubesheet_K, stream_span_K, basis)`` (P2-14).

    The tubesheet differential ``|T_shell_mean − T_tube_mean|`` drives
    the thermal-expansion / floating-head decision. The four-temperature
    stream span is retained for informational display only.
    Falls back to the span when temperatures are incomplete.
    """
    temps = [
        state.T_hot_in_C, state.T_hot_out_C,
        state.T_cold_in_C, state.T_cold_out_C,
    ]
    temps = [t for t in temps if t is not None]
    span = max(temps) - min(temps) if len(temps) >= 2 else 0.0

    if (
        state.T_hot_in_C is not None and state.T_hot_out_C is not None
        and state.T_cold_in_C is not None and state.T_cold_out_C is not None
    ):
        T_hot_mean = 0.5 * (state.T_hot_in_C + state.T_hot_out_C)
        T_cold_mean = 0.5 * (state.T_cold_in_C + state.T_cold_out_C)
        if shell_side == "hot":
            T_shell_mean, T_tube_mean = T_hot_mean, T_cold_mean
        else:
            T_shell_mean, T_tube_mean = T_cold_mean, T_hot_mean
        return abs(T_shell_mean - T_tube_mean), span, "tubesheet_differential"
    return span, span, "stream_span_fallback"


# ===================================================================
# Piece 4 — Fluid Allocation
# ===================================================================

def _allocate_fluids(state: "DesignState") -> tuple[str, list[str]]:
    """Decide which fluid goes shell-side ("hot" or "cold").

    Returns (shell_side_fluid, warnings_list).

    Decision rules (priority order):
      1. User preference (explicit override)
      2. High pressure → tube-side
      3. Fouling → tube-side
      4. Viscous → shell-side (baffles create turbulence)
      5. Hotter → tube-side (reduces shell cost)
      6. Default: hot → tube-side, cold → shell-side
    """
    warnings: list[str] = []

    # --- Rule 0: User preference ---
    if state.tema_preference and "tube" in state.tema_preference.lower():
        # User explicitly stated which fluid goes where
        if "hot" in state.tema_preference.lower():
            return "cold", warnings  # hot on tube → cold on shell
        if "cold" in state.tema_preference.lower():
            return "hot", warnings  # cold on tube → hot on shell

    # --- Rules 1a / 1b: Safety-driven allocation (toxic > corrosive) ---
    # Documented precedence (highest → lowest):
    #   toxic > corrosive > high-pressure > crude/floating > fouling > viscous > default
    # Toxic and corrosive both override high pressure because containment /
    # alloy cost dominates the design once safety boundaries are crossed.
    hot_toxic = _is_toxic(state.hot_fluid_name)
    cold_toxic = _is_toxic(state.cold_fluid_name)
    hot_corrosive = _is_corrosive(state.hot_fluid_name)
    cold_corrosive = _is_corrosive(state.cold_fluid_name)

    if hot_toxic or cold_toxic:
        if hot_toxic and not cold_toxic:
            tube_side = "hot"
            reason = f"toxic hot fluid '{state.hot_fluid_name}' \u2192 tube-side (containment)"
        elif cold_toxic and not hot_toxic:
            tube_side = "cold"
            reason = f"toxic cold fluid '{state.cold_fluid_name}' \u2192 tube-side (containment)"
        else:
            # Both toxic — prefer the more hazardous stream (highly toxic) to tubes.
            # If both or neither qualify as highly toxic, fall back to higher pressure.
            hot_highly = _is_highly_toxic(state.hot_fluid_name)
            cold_highly = _is_highly_toxic(state.cold_fluid_name)
            if hot_highly and not cold_highly:
                tube_side = "hot"
                reason = (
                    f"both streams toxic; '{state.hot_fluid_name}' is highly toxic "
                    f"\u2192 tube-side (stricter containment)"
                )
            elif cold_highly and not hot_highly:
                tube_side = "cold"
                reason = (
                    f"both streams toxic; '{state.cold_fluid_name}' is highly toxic "
                    f"\u2192 tube-side (stricter containment)"
                )
            else:
                tube_side = "hot" if (state.P_hot_Pa or 0) >= (state.P_cold_Pa or 0) else "cold"
                reason = "both streams equally toxic; higher-pressure side \u2192 tube-side"
            warnings.append(
                "Both streams flagged toxic \u2014 review allocation manually; "
                "consider exotic alloy on both sides."
            )
        # Highly toxic service \u2192 flag double-tubesheet review for Step 14.
        if _is_highly_toxic(state.hot_fluid_name) or _is_highly_toxic(state.cold_fluid_name):
            state.requires_double_tubesheet_review = True
            warnings.append(
                "Highly toxic service \u2014 Step 14 will recommend double-tubesheet "
                "construction for leak isolation."
            )
        shell_side = "cold" if tube_side == "hot" else "hot"
        warnings.insert(0, f"Fluid allocation: {tube_side} fluid \u2192 tube-side ({reason})")
        return shell_side, warnings

    if hot_corrosive or cold_corrosive:
        if hot_corrosive and not cold_corrosive:
            tube_side = "hot"
            reason = (
                f"corrosive hot fluid '{state.hot_fluid_name}' \u2192 tube-side "
                f"(corrosion-resistant alloy on tubes only)"
            )
        elif cold_corrosive and not hot_corrosive:
            tube_side = "cold"
            reason = (
                f"corrosive cold fluid '{state.cold_fluid_name}' \u2192 tube-side "
                f"(corrosion-resistant alloy on tubes only)"
            )
        else:
            # Both corrosive — route the more aggressive stream to tubes.
            hot_rank = _corrosive_severity_rank(state.hot_fluid_name)
            cold_rank = _corrosive_severity_rank(state.cold_fluid_name)
            if hot_rank == cold_rank:
                tube_side = "hot" if (state.P_hot_Pa or 0) >= (state.P_cold_Pa or 0) else "cold"
                reason = (
                    "both streams corrosive with equal severity rank; "
                    "higher-pressure side \u2192 tube-side"
                )
                warnings.append(
                    "Both streams corrosive at the same severity rank \u2014 "
                    "consider exotic alloy on both sides."
                )
            elif hot_rank < cold_rank:
                tube_side = "hot"
                reason = (
                    f"both streams corrosive; '{state.hot_fluid_name}' is more "
                    f"aggressive \u2192 tube-side"
                )
            else:
                tube_side = "cold"
                reason = (
                    f"both streams corrosive; '{state.cold_fluid_name}' is more "
                    f"aggressive \u2192 tube-side"
                )
        shell_side = "cold" if tube_side == "hot" else "hot"
        warnings.insert(0, f"Fluid allocation: {tube_side} fluid \u2192 tube-side ({reason})")
        return shell_side, warnings

    # Gather data
    P_hot = state.P_hot_Pa or 101325
    P_cold = state.P_cold_Pa or 101325
    delta_P = abs(P_hot - P_cold)

    hot_props = state.hot_fluid_props
    cold_props = state.cold_fluid_props

    mu_hot = hot_props.viscosity_Pa_s if hot_props else 0.001
    mu_cold = cold_props.viscosity_Pa_s if cold_props else 0.001

    T_hot_mean = None
    if state.T_hot_in_C is not None and state.T_hot_out_C is not None:
        T_hot_mean = (state.T_hot_in_C + state.T_hot_out_C) / 2.0
    T_cold_mean = None
    if state.T_cold_in_C is not None and state.T_cold_out_C is not None:
        T_cold_mean = (state.T_cold_in_C + state.T_cold_out_C) / 2.0

    hot_fouling = classify_fouling(
        state.hot_fluid_name or "", T_hot_mean,
    )
    cold_fouling = classify_fouling(
        state.cold_fluid_name or "", T_cold_mean,
    )

    hot_fouls = hot_fouling in ("heavy", "severe")
    cold_fouls = cold_fouling in ("heavy", "severe")

    # Track allocation reasoning
    tube_side = "hot"  # default
    reason = "default (hot → tube-side)"

    # --- Rule 2: High pressure (priority 2) ---
    if delta_P > _HIGH_PRESSURE_PA:
        if P_hot > P_cold:
            tube_side = "hot"
            reason = f"high-pressure hot fluid ({P_hot/1e5:.0f} bar) → tube-side"
        else:
            tube_side = "cold"
            reason = f"high-pressure cold fluid ({P_cold/1e5:.0f} bar) → tube-side"

    # --- Rule 2.5: Crude/heavy oil with floating-head geometry → shell-side ---
    # AES/floating-head is specifically designed for shell-side mechanical cleaning
    # of fouling hydrocarbons — standard refinery practice (TEMA Sec. 7)
    elif any(
        oil in (state.hot_fluid_name or "").lower()
        for oil in _SHELL_SIDE_CRUDE_OILS
    ) and (
        not (state.tema_preference) or
        "aes" in (state.tema_preference or "").lower() or
        "float" in (state.tema_preference or "").lower()
    ):
        tube_side = "cold"
        reason = (
            f"crude/heavy oil hot fluid → shell-side "
            f"(AES floating-head enables mechanical cleaning)"
        )

    elif any(
        oil in (state.cold_fluid_name or "").lower()
        for oil in _SHELL_SIDE_CRUDE_OILS
    ) and (
        not (state.tema_preference) or
        "aes" in (state.tema_preference or "").lower() or
        "float" in (state.tema_preference or "").lower()
    ):
        tube_side = "hot"
        reason = (
            f"crude/heavy oil cold fluid → shell-side "
            f"(AES floating-head enables mechanical cleaning)"
        )

    # --- Rule 3: Fouling (overridden by pressure if both apply) ---
    elif hot_fouls or cold_fouls:
        if hot_fouls and not cold_fouls:
            tube_side = "hot"
            reason = f"fouling hot fluid ({hot_fouling}) → tube-side"
        elif cold_fouls and not hot_fouls:
            tube_side = "cold"
            reason = f"fouling cold fluid ({cold_fouling}) → tube-side"
        else:
            # Both foul — put the worse one on tube-side
            tube_side = "hot" if hot_fouling >= cold_fouling else "cold"
            reason = "both fluids foul; worst fouler → tube-side"
            warnings.append(
                "Both fluids have heavy fouling — consider AES with "
                "square pitch for cleaning access on both sides."
            )

        # Check for conflict with viscosity
        if mu_hot > 0.01 and tube_side == "hot":
            warnings.append(
                f"Conflict: hot fluid is both fouling ({hot_fouling}) and "
                f"viscous (μ={mu_hot:.4f} Pa·s). Fouling rule takes priority "
                f"(tube-side), but shell-side baffles would improve h."
            )
        if mu_cold > 0.01 and tube_side == "cold":
            warnings.append(
                f"Conflict: cold fluid is both fouling ({cold_fouling}) and "
                f"viscous (μ={mu_cold:.4f} Pa·s). Fouling rule takes priority "
                f"(tube-side), but shell-side baffles would improve h."
            )

    # --- Rule 4: Viscosity (if no fouling concern) ---
    elif mu_hot > 10 * mu_cold and mu_hot > 0.005:
        # Hot fluid is much more viscous → put on shell-side
        tube_side = "cold"
        reason = (
            f"viscous hot fluid (μ={mu_hot:.4f} Pa·s) → shell-side "
            f"for baffle-induced turbulence"
        )
    elif mu_cold > 10 * mu_hot and mu_cold > 0.005:
        tube_side = "hot"
        reason = (
            f"viscous cold fluid (μ={mu_cold:.4f} Pa·s) → shell-side "
            f"for baffle-induced turbulence"
        )

    # --- Rules 5/6: Default — hot on tube-side ---
    # Already set as default above

    # shell_side is the opposite of tube_side
    shell_side = "cold" if tube_side == "hot" else "hot"

    warnings.insert(0, f"Fluid allocation: {tube_side} fluid → tube-side ({reason})")

    return shell_side, warnings


# ===================================================================
# Piece 5 — TEMA Type Selection
# ===================================================================

def _select_tema_type(
    state: "DesignState",
    shell_side: str,
) -> tuple[str, str, list[str]]:
    """Select the 3-letter TEMA designation.

    Returns (tema_type, reasoning, warnings).
    """
    warnings: list[str] = []

    # P2-14 — tubesheet differential drives the expansion / floating-head decision.
    delta_T_tubesheet_K, _, expansion_decision_basis = _compute_tubesheet_differential(
        state, shell_side,
    )
    if expansion_decision_basis == "stream_span_fallback":
        warnings.append(
            "Tubesheet differential could not be computed (incomplete "
            "temperatures) \u2014 falling back to stream temperature span "
            "for the expansion decision."
        )
    delta_T_for_expansion = delta_T_tubesheet_K

    Q_W = state.Q_W or 0.0

    # Determine tube-side fouling
    tube_side = "cold" if shell_side == "hot" else "hot"
    if tube_side == "hot":
        T_tube_mean = None
        if state.T_hot_in_C is not None and state.T_hot_out_C is not None:
            T_tube_mean = (state.T_hot_in_C + state.T_hot_out_C) / 2.0
        tube_fluid = state.hot_fluid_name or ""
    else:
        T_tube_mean = None
        if state.T_cold_in_C is not None and state.T_cold_out_C is not None:
            T_tube_mean = (state.T_cold_in_C + state.T_cold_out_C) / 2.0
        tube_fluid = state.cold_fluid_name or ""

    tube_fouling = classify_fouling(tube_fluid, T_tube_mean)
    tube_clean = tube_fouling in ("clean", "moderate")

    # Shell-side fouling
    if shell_side == "hot":
        T_shell_mean = None
        if state.T_hot_in_C is not None and state.T_hot_out_C is not None:
            T_shell_mean = (state.T_hot_in_C + state.T_hot_out_C) / 2.0
        shell_fluid = state.hot_fluid_name or ""
    else:
        T_shell_mean = None
        if state.T_cold_in_C is not None and state.T_cold_out_C is not None:
            T_shell_mean = (state.T_cold_in_C + state.T_cold_out_C) / 2.0
        shell_fluid = state.cold_fluid_name or ""

    shell_fouling = classify_fouling(shell_fluid, T_shell_mean)

    # Pressures
    P_hot = state.P_hot_Pa or 101325
    P_cold = state.P_cold_Pa or 101325
    max_pressure = max(P_hot, P_cold)

    # Check user preference
    user_pref = state.tema_class or state.tema_preference
    user_override = False
    if user_pref:
        pref_upper = user_pref.strip().upper()
        if pref_upper in VALID_TEMA_TYPES:
            user_override = True
            # Warn if it conflicts with physics
            if pref_upper == "BEM" and delta_T_for_expansion > _DT_EXPANSION_THRESHOLD:
                warnings.append(
                    f"User requested BEM but tubesheet ΔT={delta_T_for_expansion:.0f}°C > "
                    f"{_DT_EXPANSION_THRESHOLD}°C. Fixed tubesheet risks "
                    f"thermal stress damage. Consider AES or AEU instead."
                )
            tema_type = pref_upper
            reasoning = f"User requested {pref_upper}"
            if warnings:
                reasoning += f" (with warnings: {'; '.join(warnings)})"
        else:
            user_override = False

    if not user_override:
        # Decision tree
        needs_expansion = delta_T_for_expansion > _DT_EXPANSION_THRESHOLD

        if needs_expansion:
            if max_pressure > _VERY_HIGH_PRESSURE_PA:
                tema_type = "AEW"
                reasoning = (
                    f"tubesheet ΔT={delta_T_for_expansion:.0f}°C requires expansion compensation; "
                    f"P={max_pressure/1e5:.0f} bar requires externally sealed "
                    f"floating head → AEW"
                )
            elif (
                tube_clean
                and shell_fouling in ("clean", "moderate")
                and not any(oil in shell_fluid.lower() for oil in _SHELL_SIDE_CRUDE_OILS)
            ):
                # Both sides genuinely clean and no crude/heavy oil — U-tube cheapest
                tema_type = "AEU"
                reasoning = (
                    f"tubesheet ΔT={delta_T_for_expansion:.0f}°C requires expansion compensation; "
                    f"both fluids clean/moderate → U-tube (AEU) cheapest option"
                )
            else:
                # Shell fouls, or shell-side is crude/heavy oil (industry standard = AES)
                tema_type = "AES"
                reasoning = (
                    f"tubesheet ΔT={delta_T_for_expansion:.0f}°C requires expansion compensation; "
                    f"shell-side fluid '{shell_fluid}' ({shell_fouling}) → "
                    f"floating head AES for bundle removal and mechanical cleaning"
                )
        else:
            # Fixed tubesheet viable
            both_clean = (
                tube_fouling in ("clean", "moderate")
                and shell_fouling in ("clean", "moderate")
            )
            if both_clean:
                tema_type = "BEM"
                reasoning = (
                    f"tubesheet ΔT={delta_T_for_expansion:.0f}°C ≤ {_DT_EXPANSION_THRESHOLD}°C "
                    f"and both fluids clean → fixed tubesheet BEM (cheapest)"
                )
            else:
                # One or both fouling
                heavy_fouling = (
                    tube_fouling in ("heavy", "severe")
                    or shell_fouling in ("heavy", "severe")
                )
                if heavy_fouling:
                    tema_type = "AES"
                    reasoning = (
                        f"tubesheet ΔT={delta_T_for_expansion:.0f}°C allows fixed tubesheet but "
                        f"fouling ({tube_fouling}/{shell_fouling}) requires "
                        f"full tube access → AES floating head"
                    )
                else:
                    tema_type = "AEP"
                    reasoning = (
                        f"tubesheet ΔT={delta_T_for_expansion:.0f}°C ≤ {_DT_EXPANSION_THRESHOLD}°C; "
                        f"moderate fouling ({tube_fouling}/{shell_fouling}) → "
                        f"outside packed floating head AEP for easier maintenance"
                    )

    # Duty warnings (non-blocking)
    if Q_W > 0 and Q_W < _SMALL_DUTY_W:
        warnings.append(
            f"Heat duty Q={Q_W/1000:.1f} kW is very small. "
            f"Consider a double-pipe exchanger instead."
        )
    if Q_W > _LARGE_DUTY_W:
        warnings.append(
            f"Heat duty Q={Q_W/1e6:.1f} MW is very large. "
            f"May require multiple shells in series/parallel."
        )

    # Both-fouling note
    hot_fouling_class = classify_fouling(
        state.hot_fluid_name or "",
        (state.T_hot_in_C + state.T_hot_out_C) / 2.0
        if state.T_hot_in_C is not None and state.T_hot_out_C is not None
        else None,
    )
    cold_fouling_class = classify_fouling(
        state.cold_fluid_name or "",
        (state.T_cold_in_C + state.T_cold_out_C) / 2.0
        if state.T_cold_in_C is not None and state.T_cold_out_C is not None
        else None,
    )
    if (
        hot_fouling_class in ("heavy", "severe")
        and cold_fouling_class in ("heavy", "severe")
    ):
        warnings.append(
            "Both fluids foul heavily — use square pitch for "
            "cleaning access on shell-side."
        )

    # Corrosive fluid note (shares _is_corrosive — single source of truth per P2-11)
    for fluid_name in (state.hot_fluid_name, state.cold_fluid_name):
        if _is_corrosive(fluid_name):
            warnings.append(
                f"Fluid '{fluid_name}' may be corrosive — verify tube/shell "
                f"material selection (exotic alloy may be needed for tubes)."
            )

    return tema_type, reasoning, warnings


# ===================================================================
# Piece 5b — TEMA Class (R/C/B) Determination
# ===================================================================

# Fluid keywords that indicate refinery service → TEMA Class R
_REFINERY_FLUIDS = frozenset({
    "crude", "crude oil", "naphtha", "kerosene", "diesel", "gas oil",
    "vacuum gas oil", "fuel oil", "heavy fuel oil", "bunker fuel",
    "residual fuel", "heavy hydrocarbon", "heavy hydrocarbons",
    "gasoline", "hfo", "lube oil", "lubricating oil", "heating oil",
    "light gas oil", "heavy gas oil", "light naphtha", "heavy naphtha",
})

# Fluid keywords that indicate chemical service → TEMA Class C
_CHEMICAL_FLUIDS = frozenset({
    "acid", "caustic", "ammonia", "methanol", "ethanol", "toluene",
    "benzene", "xylene", "acetone", "formaldehyde", "glycol",
    "ethylene glycol", "propylene glycol", "molten salt",
})


def _determine_tema_class(
    state: "DesignState",
) -> tuple[str, str]:
    """Determine TEMA mechanical class (R, C, or B).

    Returns (tema_class, reasoning).

    Rules (TEMA 10th Ed., Section 1):
      R — Petroleum & related processing (refinery service).
          Strictest: thicker tubes, tighter tolerances, higher nozzle ratings.
      C — Chemical processing (moderate corrosion / toxicity).
      B — General service (HVAC, comfort cooling, benign fluids).
    """
    hot_name = (state.hot_fluid_name or "").strip().lower()
    cold_name = (state.cold_fluid_name or "").strip().lower()
    all_names = {hot_name, cold_name}

    # Check if any fluid is a refinery hydrocarbon
    is_refinery = any(
        name in _REFINERY_FLUIDS
        or any(rf in name for rf in ("crude", "naphtha", "gas oil", "fuel oil"))
        for name in all_names
        if name
    )

    # Check if any fluid is a chemical-service fluid
    is_chemical = any(
        name in _CHEMICAL_FLUIDS
        or any(cf in name for cf in ("acid", "caustic", "glycol", "ammonia"))
        for name in all_names
        if name
    )

    # Refinery takes priority (stricter requirements)
    if is_refinery:
        fluids_str = ", ".join(n for n in all_names if n)
        return "R", f"Refinery service ({fluids_str}) → TEMA Class R (strictest mechanical requirements)"

    if is_chemical:
        fluids_str = ", ".join(n for n in all_names if n)
        return "C", f"Chemical service ({fluids_str}) → TEMA Class C"

    return "B", "General service (benign fluids) → TEMA Class B"


# ===================================================================
# Piece 6 — Initial Geometry Heuristics
# ===================================================================

def _select_initial_geometry(
    state: "DesignState",
    tema_type: str,
    shell_side: str,
) -> tuple[GeometrySpec, list[str]]:
    """Select starting geometry parameters using engineering heuristics.

    Returns (GeometrySpec, warnings).
    """
    warnings: list[str] = []

    Q_W = state.Q_W or 0.0
    hot_props = state.hot_fluid_props
    cold_props = state.cold_fluid_props

    # --- Tube OD selection ---
    mu_hot = hot_props.viscosity_Pa_s if hot_props else 0.001
    mu_cold = cold_props.viscosity_Pa_s if cold_props else 0.001
    max_viscosity = max(mu_hot, mu_cold)

    if max_viscosity > 0.05:
        tube_od_m = 0.0254    # 1" for very viscous fluids
        warnings.append(
            f"Using 1\" (25.4mm) tubes due to high viscosity "
            f"(μ_max={max_viscosity:.4f} Pa·s)"
        )
    else:
        tube_od_m = 0.01905   # 3/4" standard

    # --- Tube ID from BWG ---
    tube_id_m = get_tube_id(tube_od_m, bwg=14)

    # --- Pitch layout ---
    T_hot_mean = None
    if state.T_hot_in_C is not None and state.T_hot_out_C is not None:
        T_hot_mean = (state.T_hot_in_C + state.T_hot_out_C) / 2.0
    T_cold_mean = None
    if state.T_cold_in_C is not None and state.T_cold_out_C is not None:
        T_cold_mean = (state.T_cold_in_C + state.T_cold_out_C) / 2.0

    hot_fouling = classify_fouling(state.hot_fluid_name or "", T_hot_mean)
    cold_fouling = classify_fouling(state.cold_fluid_name or "", T_cold_mean)
    any_heavy_fouling = (
        hot_fouling in ("heavy", "severe")
        or cold_fouling in ("heavy", "severe")
    )

    # Shell-side crude/heavy oil needs square pitch for mechanical cleaning access
    shell_fluid_name = (
        state.hot_fluid_name if shell_side == "hot" else state.cold_fluid_name
    ) or ""
    shell_needs_cleaning = any(
        oil in shell_fluid_name.lower() for oil in _SHELL_SIDE_CRUDE_OILS
    )

    if any_heavy_fouling or shell_needs_cleaning:
        pitch_layout = "square"
        pitch_ratio = 1.25
        if shell_needs_cleaning and not any_heavy_fouling:
            warnings.append(
                f"Shell-side fluid '{shell_fluid_name}' requires mechanical cleaning — "
                f"using square pitch (90°) for lane access."
            )
    else:
        pitch_layout = "triangular"
        pitch_ratio = 1.25

    # --- Tube length ---
    if Q_W < 500_000:       # < 500 kW
        tube_length_m = 3.66    # 12 ft
    elif Q_W > 10_000_000:  # > 10 MW
        tube_length_m = 6.096   # 20 ft
    else:
        tube_length_m = 4.877   # 16 ft (standard)

    # --- Tube passes ---
    n_passes = 2  # default

    # --- Shell passes ---
    shell_passes = 1  # TEMA E shell default

    # --- Baffle cut ---
    baffle_cut = 0.25  # 25% standard starting point

    # --- Estimate N_tubes and shell diameter ---
    # Rough area estimation: A = Q / (U_assumed × LMTD_estimated)
    U_data = get_U_assumption(
        state.hot_fluid_name or "liquid",
        state.cold_fluid_name or "liquid",
        hot_properties=state.hot_fluid_props,
        cold_properties=state.cold_fluid_props,
    )
    U_assumed = U_data["U_mid"]

    # Estimate LMTD
    T_hi = state.T_hot_in_C or 150
    T_ho = state.T_hot_out_C or 90
    T_ci = state.T_cold_in_C or 30
    T_co = state.T_cold_out_C or 60

    dt1 = T_hi - T_co  # hot inlet - cold outlet
    dt2 = T_ho - T_ci  # hot outlet - cold inlet

    if dt1 <= 0 or dt2 <= 0:
        # Temperature cross — use arithmetic mean as fallback
        lmtd_est = abs((dt1 + dt2) / 2.0) if (dt1 + dt2) != 0 else 10.0
    elif abs(dt1 - dt2) < 0.01:
        lmtd_est = dt1
    else:
        lmtd_est = (dt1 - dt2) / math.log(dt1 / dt2)

    if lmtd_est < 1.0:
        lmtd_est = 1.0  # prevent division by ~zero

    A_estimated = Q_W / (U_assumed * lmtd_est)
    # Single tube area = π × OD × L
    single_tube_area = math.pi * tube_od_m * tube_length_m
    n_tubes_estimated = max(1, int(math.ceil(A_estimated / single_tube_area)))

    # Look up standard shell
    try:
        shell_diameter_m, actual_n_tubes = find_shell_diameter(
            n_tubes_estimated, tube_od_m, pitch_layout, n_passes,
        )
    except ValueError:
        # Fallback: use rough formula shell_D ≈ 0.637 * sqrt(CL/CTP * A_tube/L)
        # Simplified: just pick 23.25" shell as default
        shell_diameter_m = 23.25 * 0.0254
        actual_n_tubes = n_tubes_estimated
        warnings.append(
            "Could not find standard shell diameter from TEMA tables; "
            "using 23.25\" shell as fallback."
        )

    # --- Baffle spacing ---
    # Viscous shell-side fluids (crude oil, heavy oils) need wider spacing
    # to keep shell-side ΔP in range. Start at 0.5× shell ID instead of 0.4×.
    shell_mu = mu_hot if shell_side == "hot" else mu_cold
    if shell_mu > 0.001 or shell_needs_cleaning:
        baffle_spacing_m = 0.5 * shell_diameter_m
    else:
        baffle_spacing_m = 0.4 * shell_diameter_m
    baffle_spacing_m = max(0.05, min(2.0, baffle_spacing_m))

    geometry = GeometrySpec(
        tube_od_m=tube_od_m,
        tube_id_m=tube_id_m,
        tube_length_m=tube_length_m,
        pitch_ratio=pitch_ratio,
        pitch_layout=pitch_layout,
        n_tubes=actual_n_tubes,
        n_passes=n_passes,
        shell_passes=shell_passes,
        shell_diameter_m=shell_diameter_m,
        baffle_cut=baffle_cut,
        baffle_spacing_m=baffle_spacing_m,
    )

    return geometry, warnings


# ===================================================================
# Piece 9 — Escalation Hints
# ===================================================================

def _build_escalation_hints(
    state: "DesignState",
    tema_type: str,
    shell_side: str,
    tema_reasoning: str,
    fouling_metadata: dict | None = None,
) -> list[dict[str, str]]:
    """Build escalation hints for AI review.

    Returns list of {"trigger": str, "recommendation": str} dicts.
    """
    hints: list[dict[str, str]] = []

    Q_W = state.Q_W or 0.0
    P_hot = state.P_hot_Pa or 101325
    P_cold = state.P_cold_Pa or 101325

    # User preference conflicts with physics
    user_pref = state.tema_class or state.tema_preference
    if user_pref:
        pref_upper = user_pref.strip().upper()
        temps = [
            state.T_hot_in_C, state.T_hot_out_C,
            state.T_cold_in_C, state.T_cold_out_C,
        ]
        temps = [t for t in temps if t is not None]
        delta_T = max(temps) - min(temps) if len(temps) >= 2 else 0
        if pref_upper == "BEM" and delta_T > _DT_EXPANSION_THRESHOLD:
            hints.append({
                "trigger": "user_preference_conflict",
                "recommendation": (
                    f"User requested BEM but ΔT={delta_T:.0f}°C exceeds "
                    f"safe limit for fixed tubesheet. Recommend AES or AEU."
                ),
            })

    # Both fluids foul
    T_hot_mean = None
    if state.T_hot_in_C is not None and state.T_hot_out_C is not None:
        T_hot_mean = (state.T_hot_in_C + state.T_hot_out_C) / 2.0
    T_cold_mean = None
    if state.T_cold_in_C is not None and state.T_cold_out_C is not None:
        T_cold_mean = (state.T_cold_in_C + state.T_cold_out_C) / 2.0

    hot_fouling = classify_fouling(state.hot_fluid_name or "", T_hot_mean)
    cold_fouling = classify_fouling(state.cold_fluid_name or "", T_cold_mean)
    if (
        hot_fouling in ("heavy", "severe")
        and cold_fouling in ("heavy", "severe")
    ):
        hints.append({
            "trigger": "both_fluids_fouling",
            "recommendation": (
                "Both fluids foul heavily. Consider AES with square "
                "pitch for bilateral cleaning access."
            ),
        })

    # Extreme pressure
    if max(P_hot, P_cold) > 100e5:  # > 100 bar
        hints.append({
            "trigger": "extreme_pressure",
            "recommendation": (
                f"Pressure={max(P_hot, P_cold)/1e5:.0f} bar — verify "
                f"head type and material ratings."
            ),
        })

    # Very small duty
    if 0 < Q_W < _SMALL_DUTY_W:
        hints.append({
            "trigger": "small_duty",
            "recommendation": (
                f"Q={Q_W/1000:.1f} kW is very small for shell-and-tube. "
                f"Consider double-pipe exchanger."
            ),
        })

    # Very large duty
    if Q_W > _LARGE_DUTY_W:
        hints.append({
            "trigger": "large_duty",
            "recommendation": (
                f"Q={Q_W/1e6:.1f} MW — likely needs multiple shells "
                f"in series or parallel."
            ),
        })

    # --- Fouling factor uncertainty ---
    # Use already-resolved fouling_metadata (from 3-tier async lookup) when available.
    # Only flag as uncertain if the resolved value still needs_ai=True or confidence<0.70.
    resolved_fm = fouling_metadata or {}
    for side_label, fluid_name, T_mean in [
        ("hot", state.hot_fluid_name or "", T_hot_mean),
        ("cold", state.cold_fluid_name or "", T_cold_mean),
    ]:
        if not fluid_name:
            continue
        resolved = resolved_fm.get(side_label)
        if resolved is not None:
            # Already resolved via MongoDB/AI — only flag if still uncertain
            if resolved.get("needs_ai") or resolved.get("confidence", 1.0) < 0.70:
                raw_conf = resolved.get("confidence")
                source = resolved.get("source", "unknown")
                # Table values with location-dependent uncertainty are usable
                # starting points, not zero-confidence unknowns.
                if source in ("exact", "partial_match", "temp_dependent"):
                    conf_text = (
                        f"Table value available (source: {source}), "
                        f"confirmation recommended for site-specific conditions"
                    )
                elif raw_conf is not None:
                    conf_text = f"confidence={raw_conf:.0%}"
                else:
                    conf_text = "confidence unknown"
                hints.append({
                    "trigger": "fouling_factor_uncertain",
                    "recommendation": (
                        f"{side_label.title()} fluid '{fluid_name}': "
                        f"R_f={resolved['rf']:.6f} m²·K/W ({conf_text}). "
                        f"Please confirm or provide the correct fouling resistance."
                    ),
                })
        else:
            # Fall back to sync table check for unknown fluids
            info = get_fouling_factor_with_source(fluid_name, T_mean)
            if info["needs_ai"]:
                hints.append({
                    "trigger": "fouling_factor_uncertain",
                    "recommendation": (
                        f"{side_label.title()} fluid '{fluid_name}': {info['reason']} "
                        f"Current R_f={info['rf']:.6f} m²·K/W (source: {info['source']}). "
                        f"Please provide the correct fouling resistance for this fluid "
                        + (f"given the operating temperature (~{T_mean:.0f}°C)." if T_mean is not None else ".")
                    ),
                })

    return hints


# ===================================================================
# Piece 7 — Step04TEMAGeometry (core execute)
# ===================================================================

class Step04TEMAGeometry(BaseStep):
    """Step 4: TEMA type selection + initial geometry sizing."""

    step_id: int = 4
    step_name: str = "TEMA Geometry Selection"
    ai_mode: AIModeEnum = AIModeEnum.FULL

    async def execute(self, state: "DesignState") -> StepResult:
        """Orchestrate fluid allocation, TEMA selection, and geometry sizing.

        Pre-conditions (from Steps 1-3):
          - hot_fluid_name, cold_fluid_name
          - T_hot_in_C, T_hot_out_C, T_cold_in_C, T_cold_out_C
          - hot_fluid_props, cold_fluid_props
          - Q_W
        """
        # --- Pre-condition checks ---
        missing = []
        if not state.hot_fluid_name:
            missing.append("hot_fluid_name")
        if not state.cold_fluid_name:
            missing.append("cold_fluid_name")
        for t_field in (
            "T_hot_in_C", "T_hot_out_C", "T_cold_in_C", "T_cold_out_C",
        ):
            if getattr(state, t_field) is None:
                missing.append(t_field)
        if state.hot_fluid_props is None:
            missing.append("hot_fluid_props")
        if state.cold_fluid_props is None:
            missing.append("cold_fluid_props")
        if state.Q_W is None:
            missing.append("Q_W")

        if missing:
            raise CalculationError(
                4,
                f"Step 4 requires the following from Steps 1-3: "
                f"{', '.join(missing)}",
            )

        all_warnings: list[str] = []

        # --- Fluid allocation (Piece 4) ---
        shell_side, alloc_warnings = _allocate_fluids(state)
        all_warnings.extend(alloc_warnings)

        # --- P2-14: tubesheet differential (post-allocation, exposed to UI) ---
        delta_T_tubesheet_K, stream_temperature_span_K, expansion_decision_basis = (
            _compute_tubesheet_differential(state, shell_side)
        )

        # --- TEMA type selection (Piece 5) ---
        # If the correction loop has already applied an AI override for tema_type,
        # skip the deterministic decision tree — using it would re-select the
        # original type and undo the correction, causing an infinite loop.
        if "tema_type" in state.applied_corrections:
            corrected = state.applied_corrections["tema_type"]
            if corrected not in VALID_TEMA_TYPES:
                raise CalculationError(
                    4,
                    f"Invalid tema_type correction '{corrected}'; "
                    f"supported types: {sorted(VALID_TEMA_TYPES)}",
                )
            tema_type = corrected
            reasoning = f"AI correction override: {tema_type}"
            type_warnings = []
        else:
            tema_type, reasoning, type_warnings = _select_tema_type(
                state, shell_side,
            )
        all_warnings.extend(type_warnings)

        # --- Initial geometry (Piece 6) ---
        geometry, geom_warnings = _select_initial_geometry(
            state, tema_type, shell_side,
        )
        all_warnings.extend(geom_warnings)

        # --- Fouling factor metadata for AI review ---
        # Resolved BEFORE escalation hints so hints can use confirmed values.
        # Use 3-tier resolution: Table → MongoDB → Claude AI.
        # If state already holds a corrected R_f (from a prior AI correction),
        # skip the lookup entirely — this breaks the CORRECT→re-run→same-hint loop.
        fouling_metadata = {}
        _rf_overrides = {
            "hot": state.R_f_hot_m2KW,
            "cold": state.R_f_cold_m2KW,
        }
        for side_label, fluid_name, T_field_in, T_field_out in [
            ("hot", state.hot_fluid_name, state.T_hot_in_C, state.T_hot_out_C),
            ("cold", state.cold_fluid_name, state.T_cold_in_C, state.T_cold_out_C),
        ]:
            if not fluid_name:
                continue

            # If AI (or user) already corrected this value, use it directly
            if _rf_overrides[side_label] is not None:
                fouling_metadata[side_label] = {
                    "rf": _rf_overrides[side_label],
                    "source": "state_override",
                    "confidence": 1.0,
                    "needs_ai": False,
                    "needs_user_confirmation": False,
                }
                continue

            T_mean = (
                (T_field_in + T_field_out) / 2.0
                if T_field_in is not None and T_field_out is not None
                else None
            )
            # Quick table check first (sync, no I/O)
            table_info = get_fouling_factor_with_source(fluid_name, T_mean)
            if table_info["needs_ai"]:
                # 3-tier async resolution
                resolved = await resolve_fouling_factor(
                    fluid_name, T_mean,
                )
                if resolved["source"] == "fallback":
                    # AI was unavailable — keep original table info
                    fouling_metadata[side_label] = table_info
                else:
                    fouling_metadata[side_label] = {
                        "rf": resolved["rf"],
                        "source": resolved["source"],
                        "confidence": resolved["confidence"],
                        "needs_ai": False,  # successfully resolved
                        "needs_user_confirmation": resolved["needs_user_confirmation"],
                        "reason": resolved["reasoning"],
                        "ai_suggestion": resolved.get("ai_suggestion"),
                    }
                if resolved["needs_user_confirmation"]:
                    all_warnings.append(
                        f"Fouling factor for '{fluid_name}' has low AI confidence "
                        f"({resolved['confidence']:.0%}). R_f={resolved['rf']:.6f} m²·K/W. "
                        f"Please confirm or provide your own value."
                    )
            else:
                fouling_metadata[side_label] = table_info

        # --- P2-16: finalise shell ID by adding bundle-to-shell clearance ---
        # The initial shell diameter from `_select_initial_geometry` is the
        # bundle envelope from TEMA tube-count tables.  Adding the per-TEMA
        # diametral clearance produces the final shell ID used by every
        # downstream step (Bell-Delaware crossflow area, ΔP, mechanical
        # sizing, cost).  Always set the flag so Step 14 can assert it.
        shell_id_initial_m = geometry.shell_diameter_m
        bundle_to_shell_clearance_m = get_bundle_to_shell_clearance_m(tema_type)
        if shell_id_initial_m is not None:
            geometry.shell_diameter_m = (
                shell_id_initial_m + bundle_to_shell_clearance_m
            )
        shell_id_final_m = geometry.shell_diameter_m
        state.shell_id_finalised = True
        if bundle_to_shell_clearance_m > 0 and shell_id_initial_m is not None:
            all_warnings.append(
                f"Shell ID finalised: {shell_id_initial_m * 1000:.0f} mm "
                f"+ {bundle_to_shell_clearance_m * 1000:.0f} mm "
                f"bundle-to-shell clearance ({tema_type}) "
                f"\u2192 {shell_id_final_m * 1000:.0f} mm"
            )

        # --- P2-15: length / shell-diameter ratio + WARN bands ---
        LD_ratio: float | None = None
        if (
            geometry.tube_length_m is not None
            and geometry.shell_diameter_m
            and geometry.shell_diameter_m > 0
        ):
            LD_ratio = geometry.tube_length_m / geometry.shell_diameter_m
            if LD_ratio < LD_RATIO_LOW_WARN:
                all_warnings.append(
                    f"L/D={LD_ratio:.2f} below {LD_RATIO_LOW_WARN} "
                    f"\u2014 short, wide bundle is economically suboptimal; "
                    f"consider lengthening tubes or fewer parallel passes."
                )
            elif LD_ratio > LD_RATIO_HIGH_WARN:
                all_warnings.append(
                    f"L/D={LD_ratio:.2f} above {LD_RATIO_HIGH_WARN} "
                    f"\u2014 long, slender bundle increases vibration risk and "
                    f"plot-plan footprint; consider larger shell or shorter tubes."
                )

        # --- FE-2: Rf lower-bound warning ---
        # When tube-side Rf equals the TEMA lower bound AND tube-side fluid
        # properties came from a low-confidence source (< 0.80), warn the
        # engineer that actual service conditions may push Rf higher.
        tube_side = "cold" if shell_side == "hot" else "hot"
        tube_fluid_name = (
            state.hot_fluid_name if tube_side == "hot" else state.cold_fluid_name
        ) or ""
        tube_side_props = (
            state.hot_fluid_props if tube_side == "hot" else state.cold_fluid_props
        )
        tube_rf = fouling_metadata.get(tube_side, {}).get("rf")
        tube_conf = (
            tube_side_props.property_confidence
            if tube_side_props is not None else None
        )
        if tube_rf is not None and tube_conf is not None and tube_conf < 0.80:
            T_tube_in = (
                state.T_hot_in_C if tube_side == "hot" else state.T_cold_in_C
            )
            T_tube_out = (
                state.T_hot_out_C if tube_side == "hot" else state.T_cold_out_C
            )
            T_tube_mean = (
                (T_tube_in + T_tube_out) / 2.0
                if T_tube_in is not None and T_tube_out is not None else None
            )
            lower_bound = get_fouling_lower_bound(tube_fluid_name, T_tube_mean)
            if lower_bound is not None and tube_rf <= lower_bound:
                rf2 = 2.0 * lower_bound
                rf3 = 3.0 * lower_bound
                warning_msg = (
                    f"Rf at lower bound for '{tube_fluid_name}': "
                    f"R_f = {tube_rf:.6f} m²·K/W is the TEMA minimum for this fluid class "
                    f"(tube-side property confidence = {tube_conf:.0%}). "
                    f"Confirm oil cleanliness class. Three Rf scenarios: "
                    f"(1) Clean service: {lower_bound:.6f} m²·K/W [current], "
                    f"(2) Moderate contamination: {rf2:.6f} m²·K/W, "
                    f"(3) Heavy contamination: {rf3:.6f} m²·K/W. "
                    f"Area impact shown in Step 6."
                )
                all_warnings.append(warning_msg)
                state.warnings.append(warning_msg)

        # --- TEMA Class (R/C/B) determination ---
        tema_class, class_reasoning = _determine_tema_class(state)
        all_warnings.append(f"TEMA Class: {tema_class} — {class_reasoning}")

        # --- Escalation hints (built after fouling_metadata is resolved) ---
        escalation_hints = _build_escalation_hints(
            state, tema_type, shell_side, reasoning, fouling_metadata,
        )

        # --- Build StepResult ---
        # Expose resolved R_f values as outputs so the AI can correct them
        # (corrections land on DesignState via pipeline_runner._apply_outputs,
        # and are read back on the next execute() call, breaking the loop).
        outputs = {
            "tema_type": tema_type,
            "tema_class": tema_class,
            "tema_class_reasoning": class_reasoning,
            "geometry": geometry,
            "shell_side_fluid": shell_side,
            "tema_reasoning": reasoning,
            "escalation_hints": escalation_hints,
            "fouling_metadata": fouling_metadata,
            "R_f_hot_m2KW": fouling_metadata.get("hot", {}).get("rf"),
            "R_f_cold_m2KW": fouling_metadata.get("cold", {}).get("rf"),
            "shell_id_finalised": state.shell_id_finalised,
            "shell_id_initial_m": shell_id_initial_m,
            "bundle_to_shell_clearance_m": bundle_to_shell_clearance_m,
            "shell_id_final_m": shell_id_final_m,
            "LD_ratio": LD_ratio,
            "delta_T_tubesheet_K": delta_T_tubesheet_K,
            "stream_temperature_span_K": stream_temperature_span_K,
            "expansion_decision_basis": expansion_decision_basis,
            "requires_double_tubesheet_review": getattr(
                state, "requires_double_tubesheet_review", False,
            ),
        }

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            warnings=all_warnings,
        )

    async def on_review_accepted(
        self,
        state: "DesignState",
        corrections: list["AICorrection"],
        recommendation: str,
    ) -> None:
        """Extract TEMA type hints from the AI's recommendation text.

        Called after the user accepts the AI review. Skipped if the accepted
        corrections already set tema_preference directly.
        """
        if not recommendation:
            return
        correction_fields = {c.field for c in corrections} if corrections else set()
        if "tema_preference" in correction_fields:
            return  # explicit correction takes priority over the hint
        match = re.search(
            r"\b(AES|AEP|AEU|AEL|AEW|BEM|NEN|BEU)\b",
            recommendation,
            re.IGNORECASE,
        )
        if match:
            suggested = match.group(1).upper()
            logger.info("Applying recommendation hint: tema_preference = %r", suggested)
            state.tema_preference = suggested

    def build_ai_context(self, state: "DesignState", result: "StepResult") -> str:
        geom = result.outputs.get("geometry")
        lines = []
        if state.T_hot_in_C is not None and state.T_cold_out_C is not None:
            dt1 = state.T_hot_in_C - (state.T_cold_out_C or 0)
            dt2 = (state.T_hot_out_C or 0) - (state.T_cold_in_C or 0)
            dt_mean = (dt1 + dt2) / 2
            lines.append(f"ΔT_mean = {dt_mean:.1f} °C  (ΔT₁={dt1:.1f}, ΔT₂={dt2:.1f})")
        if geom is not None:
            tube_od = getattr(geom, "tube_od_m", None)
            tube_id = getattr(geom, "tube_id_m", None)
            shell_d = getattr(geom, "shell_diameter_m", None)
            baffle_s = getattr(geom, "baffle_spacing_m", None)
            pitch_r = getattr(geom, "pitch_ratio", None)
            if tube_od and tube_id:
                lines.append(
                    f"Tube ID < OD check: {tube_id:.4f} < {tube_od:.4f}"
                    f" = {tube_id < tube_od}"
                )
            if pitch_r:
                lines.append(f"Pitch ratio = {pitch_r:.3f}  (valid: 1.2–1.5)")
            if baffle_s and shell_d:
                ratio = baffle_s / shell_d
                lines.append(
                    f"Baffle/shell ratio = {ratio:.3f}  (valid: 0.2–1.0)"
                )
        return "\n".join(lines)
