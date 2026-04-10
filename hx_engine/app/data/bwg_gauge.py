"""BWG (Birmingham Wire Gauge) tube dimension lookup tables.

Data source: TEMA Standards / Perry's Chemical Engineers' Handbook Table 11-2.
Maps (tube_OD, BWG_gauge) → (wall_thickness, tube_ID).

All dimensions stored internally in millimeters; public API returns meters.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Raw data: {tube_od_mm: {bwg: (wall_mm, id_mm)}}
# ---------------------------------------------------------------------------

_BWG_TABLE: dict[float, dict[int, tuple[float, float]]] = {
    # 3/4" tubes (19.05 mm)
    19.05: {
        12: (2.769, 13.512),
        13: (2.413, 14.224),
        14: (2.108, 14.834),
        15: (1.829, 15.392),
        16: (1.651, 15.748),
        17: (1.473, 16.104),
        18: (1.245, 16.560),
    },
    # 1" tubes (25.40 mm)
    25.40: {
        10: (3.404, 18.592),
        12: (2.769, 19.862),
        13: (2.413, 20.574),
        14: (2.108, 21.184),
        15: (1.829, 21.742),
        16: (1.651, 22.098),
        17: (1.473, 22.454),
        18: (1.245, 22.910),
    },
    # 1.25" tubes (31.75 mm)
    31.75: {
        10: (3.404, 24.942),
        12: (2.769, 26.212),
        14: (2.108, 27.534),
        16: (1.651, 28.448),
    },
    # 1.5" tubes (38.10 mm)
    38.10: {
        10: (3.404, 31.292),
        12: (2.769, 32.562),
        14: (2.108, 33.884),
        16: (1.651, 34.798),
    },
    # 5/8" tubes (15.875 mm)
    15.875: {
        13: (2.413, 11.049),
        14: (2.108, 11.659),
        16: (1.651, 12.573),
        18: (1.245, 13.385),
    },
    # 2" tubes (50.80 mm)
    50.80: {
        10: (3.404, 43.992),
        12: (2.769, 45.262),
        14: (2.108, 46.584),
    },
}

# Pre-compute OD values in meters for fast lookup
_OD_MM_TO_M = {od_mm: od_mm / 1000.0 for od_mm in _BWG_TABLE}
_OD_M_SET = set(_OD_MM_TO_M.values())

# Tolerance for floating-point OD matching (0.01 mm)
_TOL_MM = 0.01


def _find_od_mm(tube_od_m: float) -> float:
    """Find the matching standard OD in mm, or raise ValueError."""
    od_mm = tube_od_m * 1000.0
    for std_od_mm in _BWG_TABLE:
        if abs(od_mm - std_od_mm) < _TOL_MM:
            return std_od_mm
    available = ", ".join(f"{od:.3f}" for od in sorted(_OD_M_SET))
    raise ValueError(
        f"tube_od_m={tube_od_m} is not a standard tube OD. "
        f"Available ODs (m): {available}"
    )


def get_tube_id(tube_od_m: float, bwg: int = 14) -> float:
    """Return tube inner diameter in meters for given OD and BWG gauge."""
    od_mm = _find_od_mm(tube_od_m)
    gauges = _BWG_TABLE[od_mm]
    if bwg not in gauges:
        available = ", ".join(str(g) for g in sorted(gauges))
        raise ValueError(
            f"BWG {bwg} not available for OD={od_mm}mm. "
            f"Available gauges: {available}"
        )
    _wall_mm, id_mm = gauges[bwg]
    return id_mm / 1000.0


def get_wall_thickness(tube_od_m: float, bwg: int = 14) -> float:
    """Return wall thickness in meters for given OD and BWG gauge."""
    od_mm = _find_od_mm(tube_od_m)
    gauges = _BWG_TABLE[od_mm]
    if bwg not in gauges:
        available = ", ".join(str(g) for g in sorted(gauges))
        raise ValueError(
            f"BWG {bwg} not available for OD={od_mm}mm. "
            f"Available gauges: {available}"
        )
    wall_mm, _id_mm = gauges[bwg]
    return wall_mm / 1000.0


def get_available_tube_ods() -> list[float]:
    """Return sorted list of standard tube ODs in meters."""
    return sorted(_OD_M_SET)
