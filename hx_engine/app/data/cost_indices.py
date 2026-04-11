"""Economic data for cost estimation.

Sources:
  - Turton et al. (2013), Appendix A: K, C, B constants + material factors
  - CEPCI: Chemical Engineering magazine (projected 2026 value)
  - Material cost ratios: commodity price averages (approximate)

Used by:
  - Step 15 (cost estimate): turton_cost.py correlation
"""

from __future__ import annotations

from datetime import date

# ──────────────────────────────────────────────────────────
# CEPCI (Chemical Engineering Plant Cost Index)
# ──────────────────────────────────────────────────────────
CEPCI_INDEX = {
    "base_year": 2001,
    "base_value": 397.0,
    "current_year": 2026,
    "current_value": 816.0,
    "last_updated": date(2026, 3, 1),
}

# ──────────────────────────────────────────────────────────
# Turton K-Constants (Table A.1) — Shell-and-Tube HX types
# Key = Turton row name, Value = (K1, K2, K3, A_min_m2, A_max_m2)
# ──────────────────────────────────────────────────────────
TURTON_K_CONSTANTS: dict[str, tuple[float, float, float, float, float]] = {
    "fixed_tube":      (4.3247, -0.3030, 0.1634, 10.0, 1000.0),
    "floating_head":   (4.8306, -0.8509, 0.3187, 10.0, 1000.0),
    "u_tube":          (4.1884, -0.2503, 0.1974, 10.0, 1000.0),
    "kettle_reboiler": (4.4646, -0.5277, 0.3955, 10.0, 100.0),
}

# ──────────────────────────────────────────────────────────
# TEMA type 3rd letter → Turton row mapping
# ──────────────────────────────────────────────────────────
TEMA_TO_TURTON_ROW: dict[str, str] = {
    "M": "fixed_tube",       # BEM, NEN
    "L": "fixed_tube",       # AEL
    "S": "floating_head",    # AES
    "P": "floating_head",    # AEP
    "W": "floating_head",    # AEW
    "T": "floating_head",    # AET (future)
    "U": "u_tube",           # AEU, BEU
    "K": "kettle_reboiler",  # AKT (future)
}

# ──────────────────────────────────────────────────────────
# Pressure Factor C-Constants (Table A.2)
# Key = pressure regime, Value = (C1, C2, C3)
# Valid for P in barg.  P < 5 barg → Fp = 1.0 (no correction).
# ──────────────────────────────────────────────────────────
PRESSURE_FACTOR_CONSTANTS: dict[str, tuple[float, float, float]] = {
    "both_shell_and_tube": (0.03881, -0.11272, 0.08183),   # 5 < P < 140 barg
    "tube_only":           (-0.00164, -0.00627, 0.0123),    # 5 < P < 140 barg
}

PRESSURE_FACTOR_MAX_BARG = 140.0
PRESSURE_FACTOR_MIN_BARG = 5.0

# ──────────────────────────────────────────────────────────
# Bare Module Factor Constants (Table A.4)
# For: fixed tube sheet, floating head, U-tube, bayonet,
#      kettle reboiler, Teflon tube
# ──────────────────────────────────────────────────────────
B1 = 1.63
B2 = 1.66

# ──────────────────────────────────────────────────────────
# Material Factors (Figure A.18, IDs 1–9)
# Key = (shell_material, tube_material), Value = F_M
# Uses our internal material names from material_properties.py
# ──────────────────────────────────────────────────────────
TURTON_MATERIAL_FACTORS: dict[tuple[str, str], float] = {
    ("carbon_steel",  "carbon_steel"):   1.0,
    ("carbon_steel",  "admiralty_brass"): 1.0,
    ("carbon_steel",  "copper"):         1.4,
    ("carbon_steel",  "stainless_304"):  1.7,
    ("carbon_steel",  "stainless_316"):  1.9,
    ("carbon_steel",  "monel_400"):      2.7,
    ("carbon_steel",  "inconel_600"):    2.8,
    ("stainless_304", "stainless_304"):  3.8,
    ("carbon_steel",  "titanium"):       4.7,
    ("titanium",      "titanium"):       11.4,
    # sa516_gr70 is carbon steel plate — treated as CS
    ("sa516_gr70",    "carbon_steel"):   1.0,
    ("sa516_gr70",    "admiralty_brass"): 1.0,
    ("sa516_gr70",    "copper"):         1.4,
    ("sa516_gr70",    "stainless_304"):  1.7,
    ("sa516_gr70",    "stainless_316"):  1.9,
    ("sa516_gr70",    "monel_400"):      2.7,
    ("sa516_gr70",    "inconel_600"):    2.8,
    ("sa516_gr70",    "titanium"):       4.7,
}

# ──────────────────────────────────────────────────────────
# Material cost ratios relative to carbon steel (for F_M gap-filling)
# Approximate commodity price ratios — NOT used for known Turton combos.
# ──────────────────────────────────────────────────────────
MATERIAL_COST_RATIOS: dict[str, float] = {
    "carbon_steel":    1.0,
    "sa516_gr70":      1.0,
    "copper":          4.0,
    "admiralty_brass":  3.5,
    "stainless_304":   3.0,
    "stainless_316":   3.5,
    "monel_400":       8.0,
    "inconel_600":     12.0,
    "titanium":        15.0,
    "duplex_2205":     4.5,
}
MATERIAL_COST_RATIOS_UPDATED = date(2026, 3, 1)

# ──────────────────────────────────────────────────────────
# Per-material cost/m² validation ranges (2026 USD, bare module)
# Used by Layer 2 rules to flag anomalous results.
# Ranges are wide to accommodate small HX (10 m² → high $/m²)
# through large HX (1000 m² → low $/m²).  These catch
# genuinely wrong values, not tight engineering bounds.
# ──────────────────────────────────────────────────────────
COST_PER_M2_RANGES: dict[str, tuple[float, float]] = {
    "carbon_steel":    (50.0,  15_000.0),
    "sa516_gr70":      (50.0,  15_000.0),
    "copper":          (100.0, 25_000.0),
    "admiralty_brass":  (100.0, 20_000.0),
    "stainless_304":   (150.0, 30_000.0),
    "stainless_316":   (150.0, 35_000.0),
    "monel_400":       (200.0, 50_000.0),
    "inconel_600":     (250.0, 60_000.0),
    "titanium":        (400.0, 80_000.0),
    "duplex_2205":     (150.0, 35_000.0),
}
# Default range for unknown materials
COST_PER_M2_DEFAULT_RANGE = (25.0, 100_000.0)

# Staleness threshold (days)
CEPCI_STALENESS_THRESHOLD_DAYS = 90


# ──────────────────────────────────────────────────────────
# Public API functions
# ──────────────────────────────────────────────────────────

def get_cepci_ratio() -> float:
    """Return CEPCI_current / CEPCI_base."""
    return CEPCI_INDEX["current_value"] / CEPCI_INDEX["base_value"]


def get_cepci_staleness_days() -> int:
    """Return days since CEPCI last_updated."""
    return (date.today() - CEPCI_INDEX["last_updated"]).days


def get_turton_row(tema_type: str) -> str:
    """Map 3-letter TEMA code to Turton row name.

    Extracts the 3rd letter (rear-end type) and looks it up in
    ``TEMA_TO_TURTON_ROW``.

    Raises
    ------
    KeyError
        If the 3rd letter is not in the mapping table.
    """
    if len(tema_type) < 3:
        raise KeyError(f"TEMA type must be 3 letters, got {tema_type!r}")
    rear_end_letter = tema_type[2]
    if rear_end_letter not in TEMA_TO_TURTON_ROW:
        raise KeyError(
            f"Unknown TEMA rear-end type {rear_end_letter!r} "
            f"(from {tema_type!r})"
        )
    return TEMA_TO_TURTON_ROW[rear_end_letter]


def get_k_constants(turton_row: str) -> tuple[float, float, float]:
    """Return (K1, K2, K3) for the given Turton row.

    Raises
    ------
    KeyError
        If *turton_row* is not in ``TURTON_K_CONSTANTS``.
    """
    row = TURTON_K_CONSTANTS[turton_row]
    return row[0], row[1], row[2]


def get_area_range(turton_row: str) -> tuple[float, float]:
    """Return (A_min, A_max) validity range for the given Turton row.

    Raises
    ------
    KeyError
        If *turton_row* is not in ``TURTON_K_CONSTANTS``.
    """
    row = TURTON_K_CONSTANTS[turton_row]
    return row[3], row[4]


def get_material_factor(
    shell_material: str, tube_material: str,
) -> tuple[float, bool]:
    """Return (F_M, is_interpolated).

    Looks up ``TURTON_MATERIAL_FACTORS`` first.  If not found, computes
    a simple average from ``MATERIAL_COST_RATIOS``.
    ``is_interpolated=True`` when using the fallback.

    Raises
    ------
    KeyError
        If a material is not in ``MATERIAL_COST_RATIOS`` during fallback.
    """
    key = (shell_material, tube_material)
    if key in TURTON_MATERIAL_FACTORS:
        return TURTON_MATERIAL_FACTORS[key], False

    # Gap-fill: simple ratio of material costs vs carbon steel baseline
    c_shell = MATERIAL_COST_RATIOS[shell_material]
    c_tube = MATERIAL_COST_RATIOS[tube_material]
    # Weighted average — equal weighting of shell/tube cost ratios as
    # a rough proxy.  The Step 15 executor uses the geometry-based
    # interpolated_material_factor() for more accuracy; this is only
    # a quick lookup.
    f_m = (c_shell + c_tube) / 2.0
    return f_m, True


def get_cost_per_m2_range(tube_material: str) -> tuple[float, float]:
    """Return (min, max) $/m² for the given tube material.

    Falls back to ``COST_PER_M2_DEFAULT_RANGE`` if material is unknown.
    """
    return COST_PER_M2_RANGES.get(tube_material, COST_PER_M2_DEFAULT_RANGE)
