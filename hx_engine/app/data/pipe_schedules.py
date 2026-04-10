"""Standard pipe dimensions per ASME B36.10M / B36.19M.

Data source: ASME B36.10M (carbon & alloy steel) / B36.19M (stainless steel)
All dimensions stored internally in mm; public API returns meters where noted.

Used by:
  - Step 14 (mechanical design check): shell wall thickness via standard pipe schedule
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Pipe schedule table
# {NPS_inches: {"od_mm": float, "schedules": {schedule_number: wall_mm}}}
# Schedules sorted ascending by wall thickness.
# ---------------------------------------------------------------------------

PIPE_SCHEDULE_TABLE: dict[float, dict] = {
    6: {
        "od_mm": 168.3,
        "schedules": {
            5: 2.77, 10: 3.40, 20: 4.78, 30: 5.56,
            40: 7.11, 60: 8.74, 80: 10.97, 100: 12.70,
            120: 14.27, 140: 15.88, 160: 18.26,
        },
    },
    8: {
        "od_mm": 219.1,
        "schedules": {
            5: 2.77, 10: 3.76, 20: 6.35, 30: 7.04,
            40: 8.18, 60: 10.31, 80: 12.70, 100: 15.09,
            120: 18.26, 140: 20.62, 160: 23.01,
        },
    },
    10: {
        "od_mm": 273.1,
        "schedules": {
            5: 3.40, 10: 4.19, 20: 6.35, 30: 7.80,
            40: 9.27, 60: 12.70, 80: 15.09, 100: 18.26,
            120: 21.44, 140: 25.40, 160: 28.58,
        },
    },
    12: {
        "od_mm": 323.9,
        "schedules": {
            5: 3.96, 10: 4.57, 20: 6.35, 30: 8.38,
            40: 10.31, 60: 14.27, 80: 17.48, 100: 21.44,
            120: 25.40, 140: 28.58, 160: 33.32,
        },
    },
    14: {
        "od_mm": 355.6,
        "schedules": {
            5: 3.96, 10: 6.35, 20: 7.92, 30: 9.52,
            40: 11.13, 60: 15.09, 80: 19.05, 100: 23.83,
            120: 27.79, 140: 31.75, 160: 35.71,
        },
    },
    16: {
        "od_mm": 406.4,
        "schedules": {
            5: 4.19, 10: 6.35, 20: 7.92, 30: 9.52,
            40: 12.70, 60: 16.66, 80: 21.44, 100: 26.19,
            120: 30.96, 140: 36.53, 160: 40.49,
        },
    },
    18: {
        "od_mm": 457.2,
        "schedules": {
            5: 4.19, 10: 6.35, 20: 7.92, 30: 11.13,
            40: 14.27, 60: 19.05, 80: 23.83, 100: 29.36,
            120: 34.93, 140: 39.67, 160: 45.24,
        },
    },
    20: {
        "od_mm": 508.0,
        "schedules": {
            5: 4.78, 10: 6.35, 20: 9.53, 30: 12.70,
            40: 15.09, 60: 20.62, 80: 26.19, 100: 32.54,
            120: 38.10, 140: 44.45, 160: 50.01,
        },
    },
    24: {
        "od_mm": 609.6,
        "schedules": {
            5: 5.54, 10: 6.35, 20: 9.53, 30: 14.27,
            40: 17.48, 60: 24.61, 80: 30.96, 100: 38.89,
            120: 46.02, 140: 52.37, 160: 59.54,
        },
    },
    30: {
        "od_mm": 762.0,
        "schedules": {
            5: 6.35, 10: 7.92, 20: 12.70, 30: 15.88,
        },
    },
    36: {
        "od_mm": 914.4,
        "schedules": {
            5: 7.92, 10: 9.53, 20: 12.70, 30: 16.66,
            40: 19.05,
        },
    },
    42: {
        "od_mm": 1066.8,
        "schedules": {
            5: 9.53, 10: 9.53, 20: 12.70, 30: 16.66,
        },
    },
    48: {
        "od_mm": 1219.2,
        "schedules": {
            5: 9.53, 10: 9.53, 20: 12.70, 30: 16.66,
        },
    },
}

# Pre-compute NPS → OD_mm sorted list for fast lookup
_NPS_LIST: list[float] = sorted(PIPE_SCHEDULE_TABLE.keys())
_OD_LIST_MM: list[float] = [PIPE_SCHEDULE_TABLE[n]["od_mm"] for n in _NPS_LIST]


def find_nps_for_shell(shell_id_m: float) -> tuple[float, float]:
    """Return (NPS_inches, OD_mm) for the nearest standard pipe matching shell ID.

    For shells > NPS 24 (610 mm), returns the NPS but schedules may be
    limited or empty (rolled plate territory).

    Parameters
    ----------
    shell_id_m : float
        Shell inner diameter in meters.

    Returns
    -------
    tuple[float, float]
        (NPS in inches, outer diameter in mm).
    """
    shell_id_mm = shell_id_m * 1000.0
    best_nps = _NPS_LIST[0]
    best_od = _OD_LIST_MM[0]
    best_diff = float("inf")

    for nps, od_mm in zip(_NPS_LIST, _OD_LIST_MM):
        # Shell ID is approximately OD minus 2 × wall thickness.
        # For matching, we compare against the OD since pipe ID varies
        # by schedule. We pick the NPS whose OD is closest to shell_id + ~2×wall.
        # A simpler heuristic: closest OD that is >= shell_id (pipe must enclose).
        diff = abs(od_mm - shell_id_mm)
        if diff < best_diff:
            best_diff = diff
            best_nps = nps
            best_od = od_mm

    return best_nps, best_od


def find_minimum_schedule(
    nps: float, t_min_mm: float
) -> tuple[int | None, float | None]:
    """Return (schedule_number, wall_mm) of the lightest schedule with wall >= t_min.

    Parameters
    ----------
    nps : float
        Nominal pipe size in inches.
    t_min_mm : float
        Minimum required wall thickness in mm.

    Returns
    -------
    tuple[int | None, float | None]
        (schedule, wall_mm) or (None, None) if no standard schedule is thick enough.

    Raises
    ------
    KeyError
        If NPS is not in the pipe schedule table.
    """
    pipe = PIPE_SCHEDULE_TABLE[nps]
    schedules = pipe["schedules"]
    # Iterate by ascending schedule number (ascending wall thickness)
    for sch in sorted(schedules.keys()):
        wall = schedules[sch]
        if wall >= t_min_mm:
            return sch, wall
    return None, None


def get_pipe_wall(nps: float, schedule: int) -> float:
    """Return wall thickness in mm for a specific NPS and schedule.

    Raises
    ------
    KeyError
        If NPS or schedule is not in the table.
    """
    pipe = PIPE_SCHEDULE_TABLE[nps]
    schedules = pipe["schedules"]
    if schedule not in schedules:
        available = sorted(schedules.keys())
        raise KeyError(
            f"Schedule {schedule} not available for NPS {nps}. "
            f"Available: {available}"
        )
    return schedules[schedule]


def get_pipe_od(nps: float) -> float:
    """Return pipe outer diameter in mm for a given NPS.

    Raises
    ------
    KeyError
        If NPS is not in the table.
    """
    return PIPE_SCHEDULE_TABLE[nps]["od_mm"]
