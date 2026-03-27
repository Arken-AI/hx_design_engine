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

import math
from typing import TYPE_CHECKING

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.data.bwg_gauge import get_tube_id, get_wall_thickness
from hx_engine.app.data.fouling_factors import (
    classify_fouling,
    get_fouling_factor,
    get_fouling_factor_with_source,
    is_fouling_fluid,
    is_location_dependent,
    resolve_fouling_factor,
)
from hx_engine.app.data.tema_tables import find_shell_diameter, get_tube_count
from hx_engine.app.data.u_assumptions import classify_fluid_type, get_U_assumption
from hx_engine.app.models.design_state import FluidProperties, GeometrySpec
from hx_engine.app.models.step_result import AIModeEnum, StepResult
from hx_engine.app.steps.base import BaseStep

if TYPE_CHECKING:
    from hx_engine.app.models.design_state import DesignState


# ---------------------------------------------------------------------------
# Valid TEMA types (Phase 1)
# ---------------------------------------------------------------------------

VALID_TEMA_TYPES = {"BEM", "AES", "AEP", "AEU", "AEL", "AEW"}

# Pressure threshold for high-pressure rule (Pa)
_HIGH_PRESSURE_PA = 30e5  # 30 bar
_VERY_HIGH_PRESSURE_PA = 70e5  # 70 bar

# Temperature difference threshold for thermal expansion
_DT_EXPANSION_THRESHOLD = 50.0  # °C

# Fluids that should go shell-side with floating-head (AES/AEU) geometry
# for mechanical cleaning access — standard refinery practice
_SHELL_SIDE_CRUDE_OILS = {"crude oil", "crude", "heavy hydrocarbon", "heavy hydrocarbons", "fuel oil"}

# Duty thresholds for warnings
_SMALL_DUTY_W = 50_000       # 50 kW
_LARGE_DUTY_W = 50_000_000   # 50 MW


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

    # Compute max ΔT between streams
    temps = [
        state.T_hot_in_C, state.T_hot_out_C,
        state.T_cold_in_C, state.T_cold_out_C,
    ]
    temps = [t for t in temps if t is not None]
    delta_T_max = max(temps) - min(temps) if len(temps) >= 2 else 0.0

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
            if pref_upper == "BEM" and delta_T_max > _DT_EXPANSION_THRESHOLD:
                warnings.append(
                    f"User requested BEM but ΔT={delta_T_max:.0f}°C > "
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
        needs_expansion = delta_T_max > _DT_EXPANSION_THRESHOLD

        if needs_expansion:
            if max_pressure > _VERY_HIGH_PRESSURE_PA:
                tema_type = "AEW"
                reasoning = (
                    f"ΔT={delta_T_max:.0f}°C requires expansion compensation; "
                    f"P={max_pressure/1e5:.0f} bar requires externally sealed "
                    f"floating head → AEW"
                )
            elif tube_clean:
                tema_type = "AEU"
                reasoning = (
                    f"ΔT={delta_T_max:.0f}°C requires expansion compensation; "
                    f"tube-side fluid is {tube_fouling} → U-tube (AEU) is "
                    f"cheapest floating option"
                )
            else:
                tema_type = "AES"
                reasoning = (
                    f"ΔT={delta_T_max:.0f}°C requires expansion compensation; "
                    f"tube-side fluid fouls ({tube_fouling}) → floating head "
                    f"(AES) needed for tube access"
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
                    f"ΔT={delta_T_max:.0f}°C ≤ {_DT_EXPANSION_THRESHOLD}°C "
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
                        f"ΔT={delta_T_max:.0f}°C allows fixed tubesheet but "
                        f"fouling ({tube_fouling}/{shell_fouling}) requires "
                        f"full tube access → AES floating head"
                    )
                else:
                    tema_type = "AEP"
                    reasoning = (
                        f"ΔT={delta_T_max:.0f}°C ≤ {_DT_EXPANSION_THRESHOLD}°C; "
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

    # Corrosive fluid note
    for fluid_name in (state.hot_fluid_name, state.cold_fluid_name):
        name_lower = (fluid_name or "").lower()
        if any(kw in name_lower for kw in ("acid", "caustic", "corrosive")):
            warnings.append(
                f"Fluid '{fluid_name}' may be corrosive — verify tube/shell "
                f"material selection (exotic alloy may be needed for tubes)."
            )

    return tema_type, reasoning, warnings


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

    if any_heavy_fouling:
        pitch_layout = "square"
        pitch_ratio = 1.25
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
    # Start at 0.4 × shell diameter (within TEMA range)
    baffle_spacing_m = 0.4 * shell_diameter_m
    # Clamp to TEMA validator range
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

    # --- Fouling factor uncertainty (AI should refine) ---
    for side_label, fluid_name, T_mean in [
        ("hot", state.hot_fluid_name or "", T_hot_mean),
        ("cold", state.cold_fluid_name or "", T_cold_mean),
    ]:
        if not fluid_name:
            continue
        info = get_fouling_factor_with_source(fluid_name, T_mean)
        if info["needs_ai"]:
            hints.append({
                "trigger": "fouling_factor_uncertain",
                "recommendation": (
                    f"{side_label.title()} fluid '{fluid_name}': {info['reason']} "
                    f"Current R_f={info['rf']:.6f} m²·K/W (source: {info['source']}). "
                    f"Please provide the correct fouling resistance for this fluid "
                    f"given the operating temperature (~{T_mean:.0f}°C) "
                    if T_mean is not None else
                    f"{side_label.title()} fluid '{fluid_name}': {info['reason']} "
                    f"Current R_f={info['rf']:.6f} m²·K/W (source: {info['source']}). "
                    f"Please provide the correct fouling resistance for this fluid."
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

        # --- TEMA type selection (Piece 5) ---
        tema_type, reasoning, type_warnings = _select_tema_type(
            state, shell_side,
        )
        all_warnings.extend(type_warnings)

        # --- Initial geometry (Piece 6) ---
        geometry, geom_warnings = _select_initial_geometry(
            state, tema_type, shell_side,
        )
        all_warnings.extend(geom_warnings)

        # --- Escalation hints (Piece 9) ---
        escalation_hints = _build_escalation_hints(
            state, tema_type, shell_side, reasoning,
        )

        # --- Fouling factor metadata for AI review ---
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

        # --- Build StepResult ---
        # Expose resolved R_f values as outputs so the AI can correct them
        # (corrections land on DesignState via pipeline_runner._apply_outputs,
        # and are read back on the next execute() call, breaking the loop).
        outputs = {
            "tema_type": tema_type,
            "geometry": geometry,
            "shell_side_fluid": shell_side,
            "tema_reasoning": reasoning,
            "escalation_hints": escalation_hints,
            "fouling_metadata": fouling_metadata,
            "R_f_hot_m2KW": fouling_metadata.get("hot", {}).get("rf"),
            "R_f_cold_m2KW": fouling_metadata.get("cold", {}).get("rf"),
        }

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            warnings=all_warnings,
        )
