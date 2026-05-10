"""Nozzle sizing data — Serth Table 5.3 + Schedule 40 pipe IDs.

Default nozzle diameter look-up for shell-and-tube heat exchangers.
The user can override with explicit nozzle sizes; this table is the
engineering-standard fallback.

Ref: Serth, R.W. & Lestina, T. (2014). *Process Heat Transfer*,
     2nd ed., Table 5.3.
"""

from __future__ import annotations

import math

from hx_engine.app.core.exceptions import CalculationError, DesignConstraintViolation

# ═══════════════════════════════════════════════════════════════════════════
# Serth Table 5.3 — nominal nozzle diameter by shell size
# ═══════════════════════════════════════════════════════════════════════════
# (shell_lower_in, shell_upper_in, nozzle_nominal_in)
# Bands MUST stay sorted ascending by shell_lower_in — the lookup relies on it.
_NOZZLE_TABLE: list[tuple[float, float, float]] = [
    (4.0, 10.0, 2.0),
    (12.0, 17.25, 3.0),
    (19.25, 21.25, 4.0),
    (23.0, 29.0, 6.0),
    (31.0, 37.0, 8.0),
    (39.0, 42.0, 10.0),
]

# Tolerance (inches) absorbing float-conversion drift on band edges.
# 1e-3 in. ≈ 0.025 mm — far below any real engineering resolution but enough
# to keep e.g. 0.9398 m × 39.3701 = 36.99819… inside the (31, 37) band.
_BOUNDARY_TOL_IN: float = 1e-3

# Engineering envelope of the table.
_ENVELOPE_MIN_IN: float = _NOZZLE_TABLE[0][0]   # 4.0
_ENVELOPE_MAX_IN: float = _NOZZLE_TABLE[-1][1]  # 42.0

# ═══════════════════════════════════════════════════════════════════════════
# Schedule 40 nominal → actual inside diameter (inches → metres)
# ═══════════════════════════════════════════════════════════════════════════
_SCH40_ID_M: dict[float, float] = {
    2.0: 0.05250,   # 2.067 in.
    3.0: 0.07793,   # 3.068 in.
    4.0: 0.10226,   # 4.026 in.
    6.0: 0.15405,   # 6.065 in.
    8.0: 0.20272,   # 7.981 in.
    10.0: 0.25451,  # 10.020 in.
}

_M_TO_IN = 39.3701  # metres → inches conversion factor

# Sorted nominal sizes for upsize look-up
_NOMINAL_SIZES_SORTED: list[float] = sorted(_SCH40_ID_M.keys())


def get_next_larger_nozzle_diameter_m(current_id_m: float) -> float | None:
    """Return the next larger Schedule 40 nozzle ID, or None if already max.

    Finds the current nozzle in the table and returns the next size up.
    If the current diameter doesn't exactly match a table entry, returns
    the first Schedule 40 size whose ID is strictly larger.
    """
    for nom in _NOMINAL_SIZES_SORTED:
        sch40_id = _SCH40_ID_M[nom]
        if sch40_id > current_id_m + 1e-6:
            return sch40_id
    return None  # already at the largest available size


def get_default_nozzle_diameter_m(shell_id_m: float) -> float:
    """Look up default nozzle ID from Serth Table 5.3.

    Converts shell_id_m → inches and returns a Schedule 40 actual inside
    diameter in metres.

    Behaviour at the band edges:

    * **In-band** (within any ``(lower, upper)`` ± ``_BOUNDARY_TOL_IN``):
      returns that band's nozzle.
    * **In-gap** (between two bands, e.g. 10–12, 17.25–19.25, 21.25–23,
      29–31, 37–39 in.): snaps **up** to the next-larger band's nozzle.
      Snapping up rather than down is conservative for ρv² and matches the
      auto-correction strategy already used downstream in Step 10.
    * **Outside the engineering envelope** (≲ 4 in. or ≳ 42 in.): raises a
      structured ``DesignConstraintViolation(step_id=10)`` so the
      RedesignDriver can ask an upstream lever (n_shells, shell_passes,
      tube_length_m, multi_shell_arrangement) to bring the shell back
      inside the table envelope and restart the pipeline.

    Raises:
        DesignConstraintViolation: If shell_id_m is outside the 4–42 in.
            envelope. Carries failing value, allowed range, and the legal
            upstream levers for the redesign loop.
        CalculationError: For unreachable internal lookup failures.
    """
    shell_in = shell_id_m * _M_TO_IN

    # Out-of-envelope (with edge tolerance) — structured violation so the
    # RedesignDriver picks an upstream lever (smaller shell ID → bigger
    # n_shells / shell_passes, or a longer tube to drop required shell area).
    if shell_in < _ENVELOPE_MIN_IN - _BOUNDARY_TOL_IN or \
       shell_in > _ENVELOPE_MAX_IN + _BOUNDARY_TOL_IN:
        raise DesignConstraintViolation(
            step_id=10,
            constraint="nozzle_envelope",
            message=(
                f"Shell ID {shell_id_m:.4f} m ({shell_in:.2f} in.) "
                f"is outside the nozzle table envelope "
                f"[{_ENVELOPE_MIN_IN:.0f}–{_ENVELOPE_MAX_IN:.0f} in.]"
            ),
            failing_value=shell_in,
            allowed_range=(_ENVELOPE_MIN_IN, _ENVELOPE_MAX_IN),
            suggested_levers=[
                "n_shells",
                "shell_passes",
                "tube_length_m",
                "multi_shell_arrangement",
            ],
        )

    # Bands are ascending. The first band whose upper bound (with tolerance)
    # is ≥ shell_in is either the band that contains shell_in or the band
    # immediately above a gap → snap-up to that band's nozzle.
    for _lower, upper, nom_nozzle in _NOZZLE_TABLE:
        if shell_in <= upper + _BOUNDARY_TOL_IN:
            return _SCH40_ID_M[nom_nozzle]

    # Unreachable: the envelope check above guarantees we matched a band.
    raise CalculationError(
        step_id=10,
        message=(
            f"Shell ID {shell_id_m:.4f} m ({shell_in:.2f} in.) "
            f"could not be matched to any nozzle band"
        ),
    )


def nozzle_rho_v_squared(
    mass_flow_kg_s: float,
    density_kg_m3: float,
    nozzle_id_m: float,
    n_nozzles: int = 1,
) -> float:
    """Compute ρv² at the nozzle (kg / m·s²).

    ρv² = ṁ² / (ρ × A² × n²)
    TEMA hard limit: 2230 kg/m·s² (= 1500 lbm/ft·s²).

    Args:
        mass_flow_kg_s: Total mass flow rate through all nozzles.
        density_kg_m3: Bulk density at nozzle conditions.
        nozzle_id_m: Inside diameter of one nozzle (m).
        n_nozzles: Number of nozzles in parallel (default 1).

    Returns:
        ρv² (kg/m·s²).
    """
    A_nozzle = math.pi / 4.0 * nozzle_id_m ** 2
    v_nozzle = mass_flow_kg_s / (density_kg_m3 * A_nozzle * n_nozzles)
    return density_kg_m3 * v_nozzle ** 2


def nozzle_dP_Pa(
    mass_flow_kg_s: float,
    density_kg_m3: float,
    nozzle_id_m: float,
    n_nozzles: int = 1,
    K_nozzle: float = 1.0,
) -> float:
    """Nozzle pressure loss (Pa).

    ΔP_n = K × ρ × v² / 2   (one inlet + one outlet combined when K=1.0)

    Serth Eq. 5.A.3 uses K ≈ 1.0 for turbulent single-nozzle loss.
    Total inlet + outlet ≈ 2.0 × this.

    Args:
        mass_flow_kg_s: Total mass flow.
        density_kg_m3: Bulk density.
        nozzle_id_m: Inside diameter of one nozzle (m).
        n_nozzles: Number of nozzles in parallel.
        K_nozzle: Loss coefficient (default 1.0).

    Returns:
        Pressure drop (Pa).
    """
    A_nozzle = math.pi / 4.0 * nozzle_id_m ** 2
    v_nozzle = mass_flow_kg_s / (density_kg_m3 * A_nozzle * n_nozzles)
    return K_nozzle * density_kg_m3 * v_nozzle ** 2 / 2.0
