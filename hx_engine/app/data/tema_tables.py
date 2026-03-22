"""TEMA tube count lookup tables.

Data source: TEMA Standards Table D-7 / Sinnott Table 12.4 / Kern Table A-1.
Maps (shell_diameter, tube_OD, pitch_layout, n_passes) → n_tubes.

Shell diameters stored as nominal inches internally; public API uses meters.
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Conversion constants
# ---------------------------------------------------------------------------

_INCH_TO_M = 0.0254

# ---------------------------------------------------------------------------
# Standard shell IDs (inches, nominal pipe)
# ---------------------------------------------------------------------------

_STANDARD_SHELL_IDS_INCH: list[float] = [
    8, 10, 12, 13.25, 15.25, 17.25, 19.25, 21.25, 23.25, 25, 27, 29, 31,
    33, 35, 37,
]

# ---------------------------------------------------------------------------
# Tube count table
# TUBE_COUNT[shell_inch][tube_od_inch][pitch_layout][n_passes]
# Values sourced from TEMA / Kern / Sinnott published tables.
# ---------------------------------------------------------------------------

_TUBE_COUNT: dict[float, dict[str, dict[str, dict[int, int]]]] = {
    # --- 8" shell ---
    8: {
        "0.75": {
            "triangular": {1: 37, 2: 30, 4: 24, 6: 16},
            "square":     {1: 32, 2: 26, 4: 20, 6: 14},
        },
        "1.0": {
            "triangular": {1: 21, 2: 16, 4: 12, 6: 8},
            "square":     {1: 16, 2: 14, 4: 10, 6: 6},
        },
    },
    # --- 10" shell ---
    10: {
        "0.75": {
            "triangular": {1: 62, 2: 52, 4: 40, 6: 32},
            "square":     {1: 52, 2: 42, 4: 32, 6: 26},
        },
        "1.0": {
            "triangular": {1: 37, 2: 30, 4: 22, 6: 16},
            "square":     {1: 32, 2: 26, 4: 18, 6: 14},
        },
    },
    # --- 12" shell ---
    12: {
        "0.75": {
            "triangular": {1: 92, 2: 76, 4: 62, 6: 52},
            "square":     {1: 76, 2: 62, 4: 52, 6: 40},
        },
        "1.0": {
            "triangular": {1: 56, 2: 48, 4: 36, 6: 28},
            "square":     {1: 48, 2: 38, 4: 28, 6: 22},
        },
    },
    # --- 13.25" shell ---
    13.25: {
        "0.75": {
            "triangular": {1: 112, 2: 98, 4: 82, 6: 68},
            "square":     {1: 97, 2: 82, 4: 68, 6: 56},
        },
        "1.0": {
            "triangular": {1: 68, 2: 56, 4: 44, 6: 36},
            "square":     {1: 56, 2: 46, 4: 36, 6: 28},
        },
    },
    # --- 15.25" shell ---
    15.25: {
        "0.75": {
            "triangular": {1: 151, 2: 138, 4: 110, 6: 96},
            "square":     {1: 131, 2: 114, 4: 92, 6: 78},
        },
        "1.0": {
            "triangular": {1: 92, 2: 78, 4: 62, 6: 52},
            "square":     {1: 78, 2: 66, 4: 52, 6: 42},
        },
    },
    # --- 17.25" shell ---
    17.25: {
        "0.75": {
            "triangular": {1: 196, 2: 178, 4: 150, 6: 132},
            "square":     {1: 170, 2: 152, 4: 124, 6: 108},
        },
        "1.0": {
            "triangular": {1: 122, 2: 106, 4: 86, 6: 72},
            "square":     {1: 106, 2: 90, 4: 72, 6: 58},
        },
    },
    # --- 19.25" shell ---
    19.25: {
        "0.75": {
            "triangular": {1: 245, 2: 224, 4: 192, 6: 170},
            "square":     {1: 213, 2: 192, 4: 160, 6: 138},
        },
        "1.0": {
            "triangular": {1: 152, 2: 134, 4: 110, 6: 96},
            "square":     {1: 131, 2: 114, 4: 92, 6: 78},
        },
    },
    # --- 21.25" shell ---
    21.25: {
        "0.75": {
            "triangular": {1: 300, 2: 278, 4: 244, 6: 216},
            "square":     {1: 261, 2: 240, 4: 204, 6: 178},
        },
        "1.0": {
            "triangular": {1: 188, 2: 170, 4: 142, 6: 122},
            "square":     {1: 163, 2: 146, 4: 118, 6: 100},
        },
    },
    # --- 23.25" shell ---
    23.25: {
        "0.75": {
            "triangular": {1: 361, 2: 324, 4: 294, 6: 264},
            "square":     {1: 314, 2: 290, 4: 252, 6: 220},
        },
        "1.0": {
            "triangular": {1: 226, 2: 204, 4: 172, 6: 150},
            "square":     {1: 196, 2: 176, 4: 146, 6: 124},
        },
    },
    # --- 25" shell ---
    25: {
        "0.75": {
            "triangular": {1: 422, 2: 394, 4: 348, 6: 316},
            "square":     {1: 368, 2: 338, 4: 296, 6: 264},
        },
        "1.0": {
            "triangular": {1: 264, 2: 240, 4: 204, 6: 178},
            "square":     {1: 228, 2: 208, 4: 172, 6: 148},
        },
    },
    # --- 27" shell ---
    27: {
        "0.75": {
            "triangular": {1: 497, 2: 460, 4: 414, 6: 376},
            "square":     {1: 432, 2: 398, 4: 350, 6: 314},
        },
        "1.0": {
            "triangular": {1: 312, 2: 284, 4: 244, 6: 214},
            "square":     {1: 272, 2: 246, 4: 208, 6: 178},
        },
    },
    # --- 29" shell ---
    29: {
        "0.75": {
            "triangular": {1: 578, 2: 538, 4: 484, 6: 442},
            "square":     {1: 503, 2: 466, 4: 412, 6: 370},
        },
        "1.0": {
            "triangular": {1: 362, 2: 332, 4: 286, 6: 252},
            "square":     {1: 318, 2: 288, 4: 246, 6: 212},
        },
    },
    # --- 31" shell ---
    31: {
        "0.75": {
            "triangular": {1: 665, 2: 620, 4: 562, 6: 514},
            "square":     {1: 579, 2: 538, 4: 478, 6: 430},
        },
        "1.0": {
            "triangular": {1: 418, 2: 384, 4: 334, 6: 296},
            "square":     {1: 368, 2: 334, 4: 288, 6: 252},
        },
    },
    # --- 33" shell ---
    33: {
        "0.75": {
            "triangular": {1: 758, 2: 710, 4: 646, 6: 592},
            "square":     {1: 660, 2: 616, 4: 548, 6: 496},
        },
        "1.0": {
            "triangular": {1: 478, 2: 440, 4: 386, 6: 344},
            "square":     {1: 420, 2: 384, 4: 334, 6: 296},
        },
    },
    # --- 35" shell ---
    35: {
        "0.75": {
            "triangular": {1: 856, 2: 806, 4: 738, 6: 678},
            "square":     {1: 746, 2: 700, 4: 626, 6: 568},
        },
        "1.0": {
            "triangular": {1: 542, 2: 500, 4: 440, 6: 396},
            "square":     {1: 476, 2: 438, 4: 382, 6: 342},
        },
    },
    # --- 37" shell ---
    37: {
        "0.75": {
            "triangular": {1: 960, 2: 906, 4: 834, 6: 770},
            "square":     {1: 838, 2: 790, 4: 710, 6: 646},
        },
        "1.0": {
            "triangular": {1: 610, 2: 564, 4: 498, 6: 452},
            "square":     {1: 536, 2: 496, 4: 434, 6: 390},
        },
    },
}


# ---------------------------------------------------------------------------
# OD mapping: meters → inch key string
# ---------------------------------------------------------------------------

_TUBE_OD_M_TO_INCH_KEY: dict[float, str] = {
    0.01905:  "0.75",   # 3/4"
    0.02540:  "1.0",    # 1"
}

_TOL_M = 0.0001  # 0.1 mm tolerance for OD matching


def _match_tube_od_key(tube_od_m: float) -> str:
    """Match tube OD in meters to the inch-string key."""
    for std_m, key in _TUBE_OD_M_TO_INCH_KEY.items():
        if abs(tube_od_m - std_m) < _TOL_M:
            return key
    avail = ", ".join(f"{m:.5f}" for m in sorted(_TUBE_OD_M_TO_INCH_KEY))
    raise ValueError(
        f"tube_od_m={tube_od_m} not in tube count table. Available: {avail}"
    )


def _match_shell_inch(shell_diameter_m: float) -> float:
    """Match shell diameter in meters to the nearest standard inch value."""
    target_inch = shell_diameter_m / _INCH_TO_M
    best = None
    best_diff = float("inf")
    for std_inch in _STANDARD_SHELL_IDS_INCH:
        diff = abs(target_inch - std_inch)
        if diff < best_diff:
            best_diff = diff
            best = std_inch
    # Allow up to 0.5" tolerance for matching
    if best is not None and best_diff < 0.5:
        return best
    raise ValueError(
        f"shell_diameter_m={shell_diameter_m} "
        f"({target_inch:.2f}\") doesn't match any standard shell diameter"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_tube_count(
    shell_diameter_m: float,
    tube_od_m: float,
    pitch_layout: str,
    n_passes: int,
) -> int:
    """Look up number of tubes from TEMA table.

    Parameters
    ----------
    shell_diameter_m : Shell inner diameter in meters.
    tube_od_m : Tube outer diameter in meters.
    pitch_layout : "triangular" or "square".
    n_passes : Tube passes (1, 2, 4, or 6).

    Returns
    -------
    Number of tubes that fit in the shell.
    """
    shell_inch = _match_shell_inch(shell_diameter_m)
    od_key = _match_tube_od_key(tube_od_m)

    if shell_inch not in _TUBE_COUNT:
        raise ValueError(f"No data for shell diameter {shell_inch}\"")
    if od_key not in _TUBE_COUNT[shell_inch]:
        raise ValueError(
            f"No data for tube OD {od_key}\" in {shell_inch}\" shell"
        )
    layouts = _TUBE_COUNT[shell_inch][od_key]
    if pitch_layout not in layouts:
        raise ValueError(f"pitch_layout must be 'triangular' or 'square'")
    passes = layouts[pitch_layout]
    if n_passes not in passes:
        avail = sorted(passes.keys())
        raise ValueError(
            f"n_passes={n_passes} not in table. Available: {avail}"
        )
    return passes[n_passes]


def find_shell_diameter(
    n_tubes_required: int,
    tube_od_m: float,
    pitch_layout: str,
    n_passes: int,
) -> tuple[float, int]:
    """Find smallest standard shell that fits n_tubes_required.

    Returns
    -------
    (shell_diameter_m, actual_n_tubes)
    """
    od_key = _match_tube_od_key(tube_od_m)

    for shell_inch in _STANDARD_SHELL_IDS_INCH:
        shell_data = _TUBE_COUNT.get(shell_inch, {})
        od_data = shell_data.get(od_key, {})
        layout_data = od_data.get(pitch_layout, {})
        count = layout_data.get(n_passes)
        if count is not None and count >= n_tubes_required:
            return shell_inch * _INCH_TO_M, count

    # If no single shell fits, return the largest available
    largest_inch = _STANDARD_SHELL_IDS_INCH[-1]
    largest_data = _TUBE_COUNT.get(largest_inch, {})
    od_data = largest_data.get(od_key, {})
    layout_data = od_data.get(pitch_layout, {})
    count = layout_data.get(n_passes)
    if count is not None:
        return largest_inch * _INCH_TO_M, count

    raise ValueError(
        f"Cannot find shell for {n_tubes_required} tubes with "
        f"OD={tube_od_m}m, layout={pitch_layout}, passes={n_passes}"
    )


def get_standard_shell_diameters() -> list[float]:
    """Return all standard shell diameters in meters, ascending."""
    return [inch * _INCH_TO_M for inch in _STANDARD_SHELL_IDS_INCH]
