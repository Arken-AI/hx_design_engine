# Step 15 Implementation Plan — Cost Estimate (Turton Method)

**Status:** Planning  
**Depends on:** Steps 1–14 (complete), BaseStep infrastructure (complete)  
**Reference:** STEPS_6_16_PLAN.md §Phase C, ARKEN_MASTER_PLAN.md §6.3, Turton et al. _Analysis, Synthesis, and Design of Chemical Processes_ (5th ed., 2013) Appendix A  
**Date:** 2026-04-10

---

## Overview

Step 15 is a **post-convergence cost estimation** that computes the bare module cost of the heat exchanger using Turton's CAPCOST correlations, adjusted from 2001 base-year dollars to 2026 via CEPCI.

Three sequential calculations:

1. **Base purchased cost** ($C_p^0$) — from heat transfer area and HX type using Turton K-constants
2. **Pressure & material corrections** ($F_P$, $F_M$) — from design pressure and shell/tube material combination
3. **Bare module cost** ($C_{BM}$) — combining base cost with correction factors and CEPCI year adjustment

**AI Mode: CONDITIONAL** — AI called only if cost/m² falls outside the per-material typical range, OR CEPCI is stale (>90 days), OR area is outside Turton's valid range (10–1000 m²).

**Scope:** Single-phase liquid heat exchangers (Phase 1). All 6 TEMA types currently supported. USD only.

---

## Primary References

- **Turton et al. (2013):** _Analysis, Synthesis, and Design of Chemical Processes_, 5th ed., Appendix A
  - Table A.1 — Equipment Purchase Cost Constants ($K_1, K_2, K_3$)
  - Table A.2 — Pressure Factor Constants ($C_1, C_2, C_3$)
  - Table A.4 — Bare Module Factor Constants ($B_1, B_2$)
  - Figure A.18 — Material Factors ($F_M$) by ID number
  - Table A.3 — ID-to-material mapping for Figure A.18
- **CEPCI (Chemical Engineering Plant Cost Index):** Published monthly in _Chemical Engineering_ magazine

---

## Agreed Design Decisions

| #   | Decision                                                                                                             | Rationale                                                                       |
| --- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| D1  | Output bare module cost ($C_{BM}$) as the primary cost figure, not just purchased equipment cost ($C_p^0$)           | More useful for project estimates; includes installation factor                 |
| D2  | Smart pressure factor selection: compare shell-side vs tube-side pressure to pick "both" or "tube only" C-constants  | Avoids overpredicting cost when only one side is at elevated pressure           |
| D3  | CEPCI staleness (>90 days) triggers AI conditional review AND emits a warning                                        | Engineers should know the cost index may be outdated; AI can flag concern       |
| D4  | Material cost ratios for F_M gap-filling live in `cost_indices.py`, separate from `material_properties.py`           | Keeps physical properties (ASME) separate from economic data (commodity prices) |
| D5  | Layer 2 cost/m² validation uses per-material ranges (e.g., CS: 100–800, Ti: 1000–5000 $/m²)                          | Wide single band would miss anomalies; per-material catches real problems       |
| D6  | USD only — no currency conversion                                                                                    | Phase 1 simplification; currency field can be added later                       |
| D7  | TEMA type → Turton HX row mapping by 3rd letter of TEMA code (M,L→fixed; S,P,W→floating; U→U-tube)                   | 3rd letter determines rear-end construction, which drives fabrication cost      |
| D8  | For material combos not in Turton's 10 known pairings → deterministic interpolation from material cost ratios + warn | AI stays in "reviewer" role; cost generation is deterministic; transparent      |
| D9  | Area outside Turton valid range (10–1000 m²) → still compute but warn + trigger AI                                   | Better to give an estimate with caveat than no estimate at all                  |
| D10 | CEPCI base year = 2001, base value = 397; current year = 2026, current value = 816 (projected)                       | Turton 5th edition correlations are referenced to mid-2001 CEPCI                |
| D11 | Kettle reboiler max area = 100 m² (vs 1000 m² for others); warn if exceeded                                          | Turton's valid range is narrower for kettles                                    |
| D12 | For F_P calculation: P in barg (gauge pressure); convert from Pa stored in DesignState                               | Turton convention uses barg throughout                                          |

---

## Turton Correlation Equations

### Base Purchased Cost

$$\log_{10} C_p^0 = K_1 + K_2 \log_{10}(A) + K_3 [\log_{10}(A)]^2$$

Where $A$ = heat transfer area in m², $C_p^0$ in 2001 USD.

### Pressure Factor

$$\log_{10} F_P = C_1 + C_2 \log_{10}(P) + C_3 [\log_{10}(P)]^2$$

Where $P$ = design pressure in barg. $F_P = 1.0$ when $P < 5$ barg.

### Bare Module Cost

$$C_{BM} = C_p^0 \times (B_1 + B_2 \cdot F_M \cdot F_P)$$

Where $B_1 = 1.63$, $B_2 = 1.66$ for shell-and-tube HX.

### CEPCI Adjustment

$$C_{2026} = C_{BM,2001} \times \frac{CEPCI_{2026}}{CEPCI_{2001}} = C_{BM,2001} \times \frac{816}{397}$$

---

## Turton Constants (Source Data)

### K-Constants (Table A.1 — Heat Exchangers)

| Turton Row      | $K_1$  | $K_2$   | $K_3$  | Area Range (m²) | TEMA Codes     |
| --------------- | ------ | ------- | ------ | --------------- | -------------- |
| Fixed tube      | 4.3247 | −0.3030 | 0.1634 | 10–1000         | BEM, AEL       |
| Floating head   | 4.8306 | −0.8509 | 0.3187 | 10–1000         | AES, AEP, AEW  |
| U-tube          | 4.1884 | −0.2503 | 0.1974 | 10–1000         | AEU            |
| Kettle reboiler | 4.4646 | −0.5277 | 0.3955 | 10–100          | (future — AKT) |

### Pressure Factor Constants (Table A.2)

**"Both shell and tube" pressurized:**

| Pressure Range | $C_1$   | $C_2$    | $C_3$   |
| -------------- | ------- | -------- | ------- |
| P < 5 barg     | 0       | 0        | 0       |
| 5–140 barg     | 0.03881 | −0.11272 | 0.08183 |

**"Tube only" pressurized (shell near atmospheric):**

| Pressure Range | $C_1$    | $C_2$    | $C_3$  |
| -------------- | -------- | -------- | ------ |
| P < 5 barg     | 0        | 0        | 0      |
| 5–140 barg     | −0.00164 | −0.00627 | 0.0123 |

### Bare Module Factor Constants (Table A.4)

$B_1 = 1.63$, $B_2 = 1.66$ (for fixed tube sheet, floating head, U-tube, bayonet, kettle reboiler, and Teflon tube)

### Material Factors (Figure A.18, IDs 1–9)

| ID  | Shell Material | Tube Material | $F_M$ |
| --- | -------------- | ------------- | ----- |
| 1   | Carbon Steel   | Carbon Steel  | 1.0   |
| 2   | Carbon Steel   | Brass         | 1.0   |
| 3   | Carbon Steel   | Copper        | 1.4   |
| 4   | Carbon Steel   | Stainless 304 | 1.7   |
| 5   | Carbon Steel   | Stainless 316 | 1.9   |
| 6   | Carbon Steel   | Monel 400     | 2.7   |
| 7   | Carbon Steel   | Inconel 600   | 2.8   |
| 8   | Stainless 304  | Stainless 304 | 3.8   |
| 9a  | Carbon Steel   | Titanium      | 4.7   |
| 9b  | Titanium       | Titanium      | 11.4  |

---

## Material Factor Gap-Filling Strategy (D8)

For shell/tube combinations NOT in Turton's 10 known pairings, use a deterministic cost-ratio interpolation:

$$F_M \approx \frac{w_{shell} \cdot c_{shell} + w_{tubes} \cdot c_{tubes}}{w_{shell} \cdot c_{CS} + w_{tubes} \cdot c_{CS}}$$

Where:

- $w_{shell}$, $w_{tubes}$ = approximate weight fractions (estimated from geometry: shell surface area × thickness × density vs tube count × length × wall area × density)
- $c_{material}$ = cost per kg from `cost_indices.py` material cost table

This is only used when the exact shell/tube combo is not in Turton's table. A warning is always emitted: _"Cost estimate uses interpolated material factor — not from Turton directly."_

### Material Cost Ratios (for gap-filling)

Approximate commodity prices (relative to carbon steel = 1.0):

| Material        | Relative $/kg | Source              |
| --------------- | ------------- | ------------------- |
| carbon_steel    | 1.0           | Baseline            |
| sa516_gr70      | 1.0           | CS pressure plate   |
| copper          | 4.0           | LME commodity price |
| admiralty_brass | 3.5           | Cu-Zn alloy         |
| stainless_304   | 3.0           | Market average      |
| stainless_316   | 3.5           | Market average      |
| monel_400       | 8.0           | Specialty alloy     |
| inconel_600     | 12.0          | Superalloy          |
| titanium        | 15.0          | Aerospace grade     |
| duplex_2205     | 4.5           | Specialty SS        |

These ratios are approximate and used ONLY for gap-filling. A `last_updated` date accompanies them for staleness tracking.

---

## Pressure Factor Selection Logic (D2)

```
1. Convert P_shell_Pa and P_tube_Pa to barg:
   P_shell_barg = (P_shell_Pa - 101325) / 1e5
   P_tube_barg  = (P_tube_Pa  - 101325) / 1e5

2. Determine which side has higher design pressure:
   P_design_barg = max(P_shell_barg, P_tube_barg)

3. If P_design_barg < 5:
   → F_P = 1.0 (no correction)

4. If P_design_barg >= 5:
   a. If P_shell_barg >= 5 AND P_tube_barg >= 5:
      → Use "both shell and tube" C-constants
   b. If only one side >= 5 barg (the other near atmospheric):
      → Use "tube only" C-constants
      (Note: Turton only distinguishes "both" vs "tube only";
       if shell is high-pressure alone, use "both" conservatively)

5. Clamp: If P_design_barg > 140: warn "exceeds Turton range" + use 140
```

---

## Computation Flow

```
1. INPUTS (from DesignState)
   ├── area_provided_m2  (Step 11 — primary cost driver)
   ├── tema_type          (Step 4 — selects K-constant row)
   ├── P_hot_Pa, P_cold_Pa (Step 1 — pressure factor)
   ├── shell_side_fluid    (Step 4 — which fluid is on which side)
   ├── tube_material       (Step 4 — material factor)
   ├── shell_material      (Step 14 — defaults to carbon_steel)
   └── geometry: shell_diameter_m, tube_od_m, tube_id_m, tube_length_m,
                 n_tubes (for weight estimation in gap-fill scenario)

2. TEMA TYPE → TURTON ROW MAPPING (D7)
   ├── Extract 3rd letter of tema_type
   ├── M, L → "fixed_tube"
   ├── S, P, W → "floating_head"
   ├── U → "u_tube"
   └── (K → "kettle_reboiler" — future)

3. BASE PURCHASED COST (C_p0)
   ├── A = area_provided_m2
   ├── Validate: 10 ≤ A ≤ 1000 (or 100 for kettle) — warn if outside
   ├── log10_A = log10(A)
   ├── log10_Cp0 = K1 + K2 × log10_A + K3 × (log10_A)²
   └── Cp0 = 10^(log10_Cp0)  [2001 USD]

4. PRESSURE FACTOR (F_P)
   ├── Determine P_shell_barg and P_tube_barg from DesignState
   ├── Select "both" or "tube only" C-constants (D2 logic)
   ├── If P < 5 barg → F_P = 1.0
   ├── Else: log10_Fp = C1 + C2 × log10(P) + C3 × (log10(P))²
   └── F_P = 10^(log10_Fp)

5. MATERIAL FACTOR (F_M)
   ├── Build key: (shell_material, tube_material)
   ├── Lookup in TURTON_MATERIAL_FACTORS table (10 known combos)
   ├── If found → use directly
   ├── If not found → compute from cost ratios (D8):
   │   ├── Estimate shell weight from geometry + density
   │   ├── Estimate tube weight from geometry + density
   │   ├── Compute weighted cost ratio vs CS baseline
   │   └── Emit warning: "interpolated material factor"
   └── Return F_M

6. BARE MODULE COST (C_BM)
   ├── C_BM_2001 = Cp0 × (B1 + B2 × F_M × F_P)
   │             = Cp0 × (1.63 + 1.66 × F_M × F_P)
   └── C_BM_2026 = C_BM_2001 × (CEPCI_2026 / CEPCI_2001)
                  = C_BM_2001 × (816 / 397)

7. CEPCI STALENESS CHECK (D3)
   ├── days_since_update = (today - CEPCI.last_updated).days
   ├── If days_since_update > 90: emit warning + set cepci_stale = True
   └── cepci_stale feeds into _conditional_ai_trigger()

8. COST/m² SANITY CHECK
   ├── cost_per_m2 = C_BM_2026 / area_provided_m2
   ├── Lookup per-material range (D5)
   └── If outside range → feeds into _conditional_ai_trigger()

9. OUTPUTS → DesignState
   ├── cost_usd: float (C_BM_2026)
   └── cost_breakdown: dict (all intermediate values)
```

---

## Sub-Tasks

### ST-1: Create `data/cost_indices.py` — CEPCI + Turton Constants + Material Cost Ratios

**File:** `hx_engine/app/data/cost_indices.py` — CREATE  
**Action:** Static data file containing all economic constants for Step 15

**Contents:**

```python
"""Economic data for cost estimation.

Sources:
  - Turton et al. (2013), Appendix A: K, C, B constants + material factors
  - CEPCI: Chemical Engineering magazine (projected 2026 value)
  - Material cost ratios: commodity price averages (approximate)

Used by:
  - Step 15 (cost estimate): turton_cost.py correlation
"""

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
PRESSURE_FACTOR_CONSTANTS = {
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
# ──────────────────────────────────────────────────────────
COST_PER_M2_RANGES: dict[str, tuple[float, float]] = {
    "carbon_steel":    (100.0, 800.0),
    "sa516_gr70":      (100.0, 800.0),
    "copper":          (200.0, 1500.0),
    "admiralty_brass":  (200.0, 1200.0),
    "stainless_304":   (300.0, 2000.0),
    "stainless_316":   (350.0, 2500.0),
    "monel_400":       (500.0, 3500.0),
    "inconel_600":     (600.0, 4000.0),
    "titanium":        (1000.0, 5000.0),
    "duplex_2205":     (350.0, 2500.0),
}
# Default range for unknown materials
COST_PER_M2_DEFAULT_RANGE = (50.0, 6000.0)
```

**Public API:**

```python
def get_cepci_ratio() -> float:
    """Return CEPCI_current / CEPCI_base."""

def get_cepci_staleness_days() -> int:
    """Return days since CEPCI last_updated."""

def get_turton_row(tema_type: str) -> str:
    """Map 3-letter TEMA code to Turton row name. Raises KeyError if unknown."""

def get_k_constants(turton_row: str) -> tuple[float, float, float]:
    """Return (K1, K2, K3) for the given Turton row."""

def get_area_range(turton_row: str) -> tuple[float, float]:
    """Return (A_min, A_max) validity range for the given Turton row."""

def get_material_factor(shell_material: str, tube_material: str) -> tuple[float, bool]:
    """Return (F_M, is_interpolated).

    Looks up TURTON_MATERIAL_FACTORS first. If not found, computes from
    MATERIAL_COST_RATIOS. is_interpolated=True when using the fallback.
    """

def get_cost_per_m2_range(tube_material: str) -> tuple[float, float]:
    """Return (min, max) $/m² for the given tube material."""
```

#### ST-1 Tests

| Test  | Description                                                            | Asserts                       |
| ----- | ---------------------------------------------------------------------- | ----------------------------- |
| T1.1  | `get_cepci_ratio()` returns 816/397 ≈ 2.0554                           | Within 0.001 of expected      |
| T1.2  | `get_cepci_staleness_days()` returns positive integer                  | int ≥ 0                       |
| T1.3  | `get_turton_row("BEM")` → "fixed_tube"                                 | Correct mapping               |
| T1.4  | `get_turton_row("AES")` → "floating_head"                              | Correct mapping               |
| T1.5  | `get_turton_row("AEU")` → "u_tube"                                     | Correct mapping               |
| T1.6  | `get_turton_row("AEL")` → "fixed_tube"                                 | L maps to fixed               |
| T1.7  | `get_turton_row("AEW")` → "floating_head"                              | W maps to floating            |
| T1.8  | `get_turton_row("XYZ")` → raises `KeyError`                            | Unknown type fails            |
| T1.9  | `get_k_constants("fixed_tube")` → (4.3247, -0.3030, 0.1634)            | Exact match                   |
| T1.10 | `get_k_constants("floating_head")` → (4.8306, -0.8509, 0.3187)         | Exact match                   |
| T1.11 | `get_area_range("kettle_reboiler")` → (10, 100)                        | Narrower range                |
| T1.12 | `get_material_factor("carbon_steel", "carbon_steel")` → (1.0, False)   | Known combo, not interpolated |
| T1.13 | `get_material_factor("carbon_steel", "stainless_304")` → (1.7, False)  | Known combo                   |
| T1.14 | `get_material_factor("titanium", "titanium")` → (11.4, False)          | Known combo                   |
| T1.15 | `get_material_factor("sa516_gr70", "stainless_316")` → (1.9, False)    | sa516 treated as CS           |
| T1.16 | `get_material_factor("duplex_2205", "stainless_316")` → (>1.0, True)   | Interpolated + flag           |
| T1.17 | `get_material_factor("stainless_316", "stainless_316")` → (>1.0, True) | Not in Turton → interpolated  |
| T1.18 | `get_cost_per_m2_range("carbon_steel")` → (100, 800)                   | Correct range                 |
| T1.19 | `get_cost_per_m2_range("titanium")` → (1000, 5000)                     | Correct range                 |
| T1.20 | `get_cost_per_m2_range("unknown_material")` → default (50, 6000)       | Fallback range                |
| T1.21 | All 10 materials present in `MATERIAL_COST_RATIOS`                     | No gaps                       |
| T1.22 | All 10 materials present in `COST_PER_M2_RANGES`                       | No gaps                       |
| T1.23 | `CEPCI_INDEX["base_value"]` == 397.0                                   | Correct base                  |

---

### ST-2: Create `correlations/turton_cost.py` — Cost Correlation Functions

**File:** `hx_engine/app/correlations/turton_cost.py` — CREATE  
**Action:** Pure calculation functions for Turton's cost method

**Functions:**

```python
def purchased_equipment_cost(
    area_m2: float,
    K1: float, K2: float, K3: float,
) -> float:
    """Calculate base purchased equipment cost (C_p^0) in 2001 USD.

    C_p^0 = 10^(K1 + K2*log10(A) + K3*(log10(A))^2)

    Raises ValueError if area_m2 <= 0.
    """

def pressure_factor(
    pressure_barg: float,
    C1: float, C2: float, C3: float,
) -> float:
    """Calculate pressure correction factor F_P.

    F_P = 10^(C1 + C2*log10(P) + C3*(log10(P))^2)

    Returns 1.0 if pressure_barg < 5 (below correction threshold).
    Raises ValueError if pressure_barg < 0.
    """

def bare_module_cost(
    Cp0: float,
    F_M: float,
    F_P: float,
    B1: float = 1.63,
    B2: float = 1.66,
) -> float:
    """Calculate bare module cost in base-year USD.

    C_BM = Cp0 × (B1 + B2 × F_M × F_P)

    Raises ValueError if any input < 0.
    """

def cepci_adjust(
    cost_base_year: float,
    cepci_current: float,
    cepci_base: float,
) -> float:
    """Adjust cost from base year to current year using CEPCI ratio.

    C_current = C_base × (CEPCI_current / CEPCI_base)
    """

def interpolated_material_factor(
    shell_material: str,
    tube_material: str,
    shell_weight_kg: float,
    tube_weight_kg: float,
    cost_ratios: dict[str, float],
) -> float:
    """Estimate F_M from material cost ratios when Turton lookup fails.

    F_M ≈ (w_shell × c_shell + w_tubes × c_tubes) /
           (w_shell × c_CS + w_tubes × c_CS)

    Raises KeyError if material not in cost_ratios.
    """

def estimate_component_weights(
    shell_diameter_m: float,
    shell_length_m: float,
    shell_thickness_m: float,
    shell_density_kg_m3: float,
    tube_od_m: float,
    tube_id_m: float,
    tube_length_m: float,
    n_tubes: int,
    tube_density_kg_m3: float,
) -> tuple[float, float]:
    """Estimate shell and tube weights in kg.

    Returns (shell_weight_kg, tube_weight_kg).
    Shell = π × D × L × t × ρ  (cylindrical shell, no heads)
    Tubes = n × π/4 × (d_o² − d_i²) × L × ρ
    """
```

#### ST-2 Tests

| Test  | Description                                                                                             | Asserts                                            |
| ----- | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| T2.1  | `purchased_equipment_cost(100, 4.3247, -0.3030, 0.1634)` — fixed tube, 100 m²                           | C_p0 ≈ $24,000–$30,000 (2001 USD)                  |
| T2.2  | `purchased_equipment_cost(100, 4.8306, -0.8509, 0.3187)` — floating head, 100 m²                        | C_p0 > fixed tube cost (floating more expensive)   |
| T2.3  | `purchased_equipment_cost(100, 4.1884, -0.2503, 0.1974)` — U-tube, 100 m²                               | C_p0 < fixed tube cost (U-tube cheapest)           |
| T2.4  | Cost increases with area: C_p0(200) > C_p0(100)                                                         | Monotonically increasing                           |
| T2.5  | `purchased_equipment_cost(0)` → raises ValueError                                                       | Zero area invalid                                  |
| T2.6  | `purchased_equipment_cost(-1)` → raises ValueError                                                      | Negative area invalid                              |
| T2.7  | `pressure_factor(3.0, ...)` → 1.0                                                                       | Below 5 barg threshold                             |
| T2.8  | `pressure_factor(0.0, ...)` → 1.0                                                                       | Atmospheric                                        |
| T2.9  | `pressure_factor(100, 0.03881, -0.11272, 0.08183)` — "both" at 100 barg                                 | F_P ≈ 1.38                                         |
| T2.10 | `pressure_factor(100, -0.00164, -0.00627, 0.0123)` — "tube only" at 100 barg                            | F_P < "both" value                                 |
| T2.11 | `pressure_factor(5, ...)` — at threshold                                                                | F_P ≈ 1.0 (just at boundary)                       |
| T2.12 | Pressure factor increases with pressure: F_P(100) > F_P(50) > F_P(10)                                   | Monotonically increasing                           |
| T2.13 | `pressure_factor(-1, ...)` → raises ValueError                                                          | Negative pressure invalid                          |
| T2.14 | `bare_module_cost(25000, 1.0, 1.0)` — CS/CS at atmospheric                                              | C_BM ≈ 25000 × 3.29 ≈ $82,250                      |
| T2.15 | `bare_module_cost(25000, 1.7, 1.0)` — CS/SS304 at atmospheric                                           | C_BM ≈ 25000 × (1.63 + 1.66×1.7) ≈ $111,350        |
| T2.16 | C_BM increases with F_M: CS/Ti > CS/SS > CS/CS                                                          | Correct ordering                                   |
| T2.17 | `cepci_adjust(82250, 816, 397)` — 2001→2026                                                             | ≈ $168,950 (×2.055)                                |
| T2.18 | `cepci_adjust(X, 397, 397)` → X (same year, no adjustment)                                              | Identity                                           |
| T2.19 | `interpolated_material_factor("duplex_2205", "duplex_2205", 5000, 3000, ratios)` — exotic combo         | F_M > 1.0, reasonable value                        |
| T2.20 | `interpolated_material_factor("carbon_steel", "carbon_steel", 5000, 3000, ratios)` → 1.0                | CS/CS always = 1.0                                 |
| T2.21 | `estimate_component_weights(0.508, 4.877, 0.008, 7750, 0.01905, 0.01575, 4.877, 324, 7750)` — Serth 5.1 | Shell ~480 kg, tubes ~1100 kg (order of magnitude) |
| T2.22 | Full pipeline: area=100, fixed, CS/CS, 10 barg, CEPCI 2026                                              | Total ≈ $170,000–$200,000 (sanity)                 |

---

### ST-3: Add DesignState Fields for Step 15

**File:** `hx_engine/app/models/design_state.py` — MODIFY  
**Action:** Add Step 15 output fields after the mechanical design section

```python
# --- cost estimate (populated by Step 15) ---
cost_usd: Optional[float] = None
cost_breakdown: Optional[dict] = None
```

**`cost_breakdown` schema:**

```python
{
    "area_m2": float,                    # input: heat transfer area
    "turton_row": str,                   # "fixed_tube" / "floating_head" / "u_tube"
    "K1": float, "K2": float, "K3": float,  # constants used
    "Cp0_2001_usd": float,              # base purchased cost (2001 USD)
    "pressure_barg": float,             # design pressure used
    "pressure_regime": str,             # "none" / "both_shell_and_tube" / "tube_only"
    "C1": float, "C2": float, "C3": float,  # pressure constants used (0 if none)
    "F_P": float,                        # pressure factor
    "shell_material": str,
    "tube_material": str,
    "F_M": float,                        # material factor
    "F_M_interpolated": bool,           # True if gap-filled, not from Turton
    "B1": float, "B2": float,           # bare module constants
    "bare_module_factor": float,         # B1 + B2 × F_M × F_P
    "C_BM_2001_usd": float,             # bare module cost (2001 USD)
    "cepci_base_year": int,
    "cepci_base_value": float,
    "cepci_current_year": int,
    "cepci_current_value": float,
    "cepci_ratio": float,
    "cepci_stale": bool,                 # True if > 90 days since update
    "cepci_stale_days": int | None,      # days since update (if stale)
    "C_BM_2026_usd": float,             # final bare module cost (2026 USD)
    "cost_per_m2_usd": float,           # C_BM_2026 / area
    "area_in_valid_range": bool,         # True if 10 ≤ A ≤ max for type
    "warnings": list[str],               # any warnings generated
}
```

#### ST-3 Tests

| Test | Description                                           | Asserts                       |
| ---- | ----------------------------------------------------- | ----------------------------- |
| T3.1 | New fields default to `None`                          | No breakage in existing tests |
| T3.2 | DesignState round-trips through JSON with cost fields | Serialize + deserialize works |
| T3.3 | `cost_usd` is `Optional[float]`                       | Type annotation correct       |

---

### ST-4: Create `steps/step_15_rules.py` — Hard Validation Rules

**File:** `hx_engine/app/steps/step_15_rules.py` — CREATE  
**Action:** Layer 2 hard rules that AI cannot override

**Rules:**

| Rule | Check                                                             | Hard Fail                            |
| ---- | ----------------------------------------------------------------- | ------------------------------------ |
| R1   | `cost_usd is not None`                                            | Cost must be computed                |
| R2   | `cost_usd > 0`                                                    | Cost must be positive                |
| R3   | `cost_breakdown is not None`                                      | Breakdown must be populated          |
| R4   | `cost_breakdown["F_M"] > 0`                                       | Material factor must be positive     |
| R5   | `cost_breakdown["F_P"] >= 1.0`                                    | Pressure factor can't be less than 1 |
| R6   | `cost_per_m2_usd` within per-material range (from `cost_indices`) | Anomalous cost per area              |

```python
def _check_cost_computed(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    """R1: cost_usd must be present in outputs."""

def _check_cost_positive(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    """R2: cost_usd > 0."""

def _check_breakdown_present(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    """R3: cost_breakdown must be present."""

def _check_material_factor_positive(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    """R4: F_M > 0."""

def _check_pressure_factor_valid(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    """R5: F_P >= 1.0."""

def _check_cost_per_m2_range(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    """R6: cost_per_m2 within range for tube material."""
```

#### ST-4 Tests

| Test  | Description                                                             | Asserts           |
| ----- | ----------------------------------------------------------------------- | ----------------- |
| T4.1  | All rules pass with valid cost_breakdown                                | All PASS          |
| T4.2  | Missing `cost_usd` → R1 fails                                           | FAIL with message |
| T4.3  | `cost_usd = 0` → R2 fails                                               | FAIL              |
| T4.4  | `cost_usd = -1000` → R2 fails                                           | FAIL              |
| T4.5  | Null `cost_breakdown` → R3 fails                                        | FAIL              |
| T4.6  | `F_M = 0` → R4 fails                                                    | FAIL              |
| T4.7  | `F_P = 0.5` → R5 fails                                                  | FAIL              |
| T4.8  | `cost_per_m2_usd = 10` (below CS range of 100) → R6 fails               | FAIL              |
| T4.9  | `cost_per_m2_usd = 10000` (above Ti range of 5000) → R6 fails           | FAIL              |
| T4.10 | `cost_per_m2_usd = 500` with CS tubes → R6 passes                       | PASS              |
| T4.11 | Unknown tube material → uses default range (50–6000), `cost_per_m2=200` | PASS              |

---

### ST-5: Create `steps/step_15_cost.py` — Step Executor

**File:** `hx_engine/app/steps/step_15_cost.py` — CREATE  
**Action:** Implement `Step15CostEstimate(BaseStep)` following Step 14 pattern

**Key decisions in `execute()`:**

1. Validate preconditions: `area_provided_m2` must exist
2. Map TEMA type to Turton row (D7)
3. Check area against valid range; warn if outside (D9, D11)
4. Compute $C_p^0$ from K-constants
5. Determine shell/tube pressures; select "both" vs "tube only" regime (D2)
6. Compute $F_P$; clamp pressure at 140 barg with warning
7. Look up $F_M$ from Turton table or compute gap-fill (D8)
8. Compute $C_{BM}$ in 2001 USD
9. Apply CEPCI adjustment to 2026 USD (D10)
10. Check CEPCI staleness (D3)
11. Compute cost/m² for validation
12. Build `cost_breakdown` dict and `StepResult`

**AI trigger condition:**

```python
def _conditional_ai_trigger(self, state: DesignState) -> bool:
    # Trigger if cost/m² outside per-material range
    if state.cost_breakdown:
        cost_per_m2 = state.cost_breakdown.get("cost_per_m2_usd", 0)
        tube_mat = state.cost_breakdown.get("tube_material", "carbon_steel")
        lo, hi = get_cost_per_m2_range(tube_mat)
        if cost_per_m2 < lo or cost_per_m2 > hi:
            return True
        # Trigger if CEPCI stale
        if state.cost_breakdown.get("cepci_stale", False):
            return True
        # Trigger if area outside Turton valid range
        if not state.cost_breakdown.get("area_in_valid_range", True):
            return True
        # Trigger if material factor was interpolated
        if state.cost_breakdown.get("F_M_interpolated", False):
            return True
    return False
```

**StepResult outputs dict keys:**

```python
outputs = {
    "cost_usd": float,
    "cost_breakdown": dict,  # full breakdown as defined in ST-3
    "tube_material": str,    # for rule R6 lookup
}
```

#### ST-5 Tests

| Test  | Description                                                                             | Asserts                                          |
| ----- | --------------------------------------------------------------------------------------- | ------------------------------------------------ |
| T5.1  | Basic execution: 100 m², BEM, CS/CS, 10 barg                                            | `cost_usd > 0`, all breakdown fields populated   |
| T5.2  | Cost increases with area: 200 m² > 100 m²                                               | Monotonically increasing                         |
| T5.3  | Floating head more expensive than fixed tube for same area                              | cost_AES > cost_BEM                              |
| T5.4  | U-tube cheapest for same area                                                           | cost_AEU < cost_BEM                              |
| T5.5  | Higher pressure → higher cost: 50 barg > 10 barg > 3 barg                               | Monotonically increasing                         |
| T5.6  | Exotic material → higher cost: CS/Ti > CS/SS304 > CS/CS                                 | Correct ordering                                 |
| T5.7  | Atmospheric pressure (1 bar) → F_P = 1.0                                                | No pressure correction                           |
| T5.8  | TEMA type "AES" maps correctly to floating_head K-constants                             | Correct K1, K2, K3 in breakdown                  |
| T5.9  | TEMA type "AEL" maps correctly to fixed_tube                                            | L → fixed                                        |
| T5.10 | TEMA type "AEW" maps correctly to floating_head                                         | W → floating                                     |
| T5.11 | Missing `area_provided_m2` → raises `CalculationError`                                  | Proper exception                                 |
| T5.12 | Missing `tema_type` → raises `CalculationError`                                         | Proper exception                                 |
| T5.13 | Missing pressures (None) → defaults to atmospheric; F_P = 1.0                           | No crash                                         |
| T5.14 | Missing `shell_material` → defaults to "carbon_steel"                                   | Valid fallback                                   |
| T5.15 | Missing `tube_material` → defaults to "carbon_steel"                                    | Valid fallback                                   |
| T5.16 | Area = 5 m² (below Turton min) → warning emitted, cost still calculated                 | Warning in result, `area_in_valid_range = False` |
| T5.17 | Area = 2000 m² (above Turton max) → warning emitted, cost still calculated              | Warning in result, `area_in_valid_range = False` |
| T5.18 | Pressure = 200 barg (above 140 max) → clamped to 140, warning emitted                   | Warning + F_P computed at 140                    |
| T5.19 | Unknown material combo → interpolated F_M + warning + `F_M_interpolated = True`         | Warning, trigger AI                              |
| T5.20 | CEPCI stale (>90 days) → warning + `cepci_stale = True`                                 | Warning + AI trigger flag                        |
| T5.21 | `_conditional_ai_trigger` returns True when cost/m² out of range                        | Correct trigger                                  |
| T5.22 | `_conditional_ai_trigger` returns True when CEPCI stale                                 | Correct trigger                                  |
| T5.23 | `_conditional_ai_trigger` returns True when area out of range                           | Correct trigger                                  |
| T5.24 | `_conditional_ai_trigger` returns True when F_M interpolated                            | Correct trigger                                  |
| T5.25 | `_conditional_ai_trigger` returns False when everything normal                          | No trigger                                       |
| T5.26 | Step metadata: step_id=15, step_name correct, ai_mode=CONDITIONAL                       | Correct values                                   |
| T5.27 | In convergence loop → AI skipped (shouldn't happen for Step 15, but contract fulfilled) | `_should_call_ai() == False`                     |
| T5.28 | `cost_breakdown` has all expected keys (no missing/extra)                               | Schema validation                                |
| T5.29 | Pressure factor "both" vs "tube only" selection works correctly                         | P_shell low, P_tube high → "tube_only" regime    |
| T5.30 | sa516_gr70 shell + SS 316 tubes → F_M = 1.9 (treated as CS shell)                       | Not interpolated, exact Turton value             |

---

### ST-6: Wire Step 15 into Pipeline Runner

**File:** `hx_engine/app/core/pipeline_runner.py` — MODIFY  
**Action:** Add Step 15 after Step 14 in the pipeline sequence

```python
from hx_engine.app.steps.step_15_cost import Step15CostEstimate

# In PIPELINE_STEPS or post-convergence sequence:
# ... Step 14 ...
Step15CostEstimate(),
# ... Step 16 ...
```

#### ST-6 Tests

| Test | Description                                         | Asserts                                                |
| ---- | --------------------------------------------------- | ------------------------------------------------------ |
| T6.1 | Pipeline includes Step 15 in sequence after Step 14 | Step 15 in step list                                   |
| T6.2 | Step 15 receives converged geometry from Step 12    | `state.area_provided_m2` is not None when Step 15 runs |
| T6.3 | Step 15 receives mechanical data from Step 14       | `state.shell_material` is not None when Step 15 runs   |

---

### ST-7: Integration Tests — Step 15 End-to-End

**File:** `tests/integration/test_step_15_integration.py` — CREATE  
**Action:** Full integration tests that run Step 15 with realistic DesignState

#### ST-7 Tests

| Test  | Description                                                                | Asserts                                      |
| ----- | -------------------------------------------------------------------------- | -------------------------------------------- |
| T7.1  | Serth Example 5.1 geometry through Step 15 (BEM, CS/CS, 10 bar, ~47 m²)    | cost_usd > 0; cost_breakdown fully populated |
| T7.2  | Same geometry with AES type → higher cost than BEM                         | cost_AES > cost_BEM                          |
| T7.3  | Same geometry with CS/SS304 tubes → higher cost than CS/CS                 | cost_SS > cost_CS                            |
| T7.4  | High pressure case (50 bar) → AI triggered if cost/m² at edge              | F_P > 1.0                                    |
| T7.5  | Step 15 + rules pass → all Layer 2 rules return PASS                       | Zero hard rule failures                      |
| T7.6  | Step result populates StepResult with correct outputs dict                 | outputs has `cost_usd` and `cost_breakdown`  |
| T7.7  | Step record appended to state.step_records                                 | `len(step_records)` increases by 1           |
| T7.8  | Cost/m² for CS/CS at atmospheric falls within (100, 800) $/m²              | Sanity check                                 |
| T7.9  | Full pipeline Steps 1–15 mock run → Step 15 produces valid output          | No crash; cost_usd > 0                       |
| T7.10 | Exotic material combo (duplex/duplex) → F_M interpolated + warning present | `F_M_interpolated = True` + warning string   |

---

### ST-8: Regression Tests — Backward Compatibility

**File:** `tests/integration/test_step_15_regression.py` — CREATE  
**Action:** Ensure Step 15 doesn't break existing functionality

| Test | Description                                                          | Asserts                      |
| ---- | -------------------------------------------------------------------- | ---------------------------- |
| T8.1 | Run Steps 1–14 → verify all still pass (no regression)               | All existing assertions hold |
| T8.2 | DesignState serialization with new cost fields → JSON round-trip     | No field corruption          |
| T8.3 | Step 15 with missing area → raises CalculationError (not crash)      | Proper exception             |
| T8.4 | Step 15 with missing tema_type → raises CalculationError (not crash) | Proper exception             |
| T8.5 | Step 15 with None pressures → graceful fallback to atmospheric       | No crash; F_P = 1.0          |
| T8.6 | Pipeline runner wiring doesn't break Steps 1–14 execution            | All prior steps pass         |

---

## File Summary

| File                                            | Action | Sub-Task | Description                            |
| ----------------------------------------------- | ------ | -------- | -------------------------------------- |
| `hx_engine/app/data/cost_indices.py`            | CREATE | ST-1     | CEPCI + Turton constants + cost ratios |
| `hx_engine/app/correlations/turton_cost.py`     | CREATE | ST-2     | Pure cost calculation functions        |
| `hx_engine/app/models/design_state.py`          | MODIFY | ST-3     | Add 2 new fields (cost_usd, breakdown) |
| `hx_engine/app/steps/step_15_rules.py`          | CREATE | ST-4     | 6 hard validation rules                |
| `hx_engine/app/steps/step_15_cost.py`           | CREATE | ST-5     | Step executor                          |
| `hx_engine/app/core/pipeline_runner.py`         | MODIFY | ST-6     | Wire Step 15 into sequence             |
| `tests/unit/test_cost_indices.py`               | CREATE | ST-1     | Tests for data lookups                 |
| `tests/unit/test_turton_cost.py`                | CREATE | ST-2     | Tests for correlation functions        |
| `tests/unit/test_step_15_state.py`              | CREATE | ST-3     | Tests for DesignState cost fields      |
| `tests/unit/test_step_15_rules.py`              | CREATE | ST-4     | Tests for validation rules             |
| `tests/unit/test_step_15_cost.py`               | CREATE | ST-5     | Tests for step executor                |
| `tests/integration/test_step_15_integration.py` | CREATE | ST-7     | End-to-end integration tests           |
| `tests/integration/test_step_15_regression.py`  | CREATE | ST-8     | Regression / backward compat tests     |

**Total files:** 13 (6 source + 7 test)

---

## Build Sequence

```
ST-1  (cost_indices.py — static data)
  │
  ▼
ST-2  (turton_cost.py — correlations, depends on ST-1 data)
  │
  │    ST-3  (DesignState fields — independent)
  │      │
  ▼      ▼
ST-4  (rules — depends on ST-1 for range lookups)
  │
  ▼
ST-5  (step executor — depends on ST-1, ST-2, ST-3, ST-4)
  │
  ▼
ST-6  (pipeline wiring)
  │
  ├── ST-7  (integration tests)
  └── ST-8  (regression tests)
```

**Recommended build order (sequential):**

1. ST-1 → run T1.\* → data layer complete
2. ST-2 → run T2.\* → correlation functions verified
3. ST-3 → run T3.\* → DesignState fields added
4. ST-4 → run T4.\* → validation rules ready
5. ST-5 → run T5.\* → step executor working
6. ST-6 → run T6.\* → pipeline wired
7. ST-7 → integration tests pass
8. ST-8 → regression tests pass (nothing broken)

---

## Edge Cases

| #   | Edge Case                                                            | Expected Behaviour                                                                  |
| --- | -------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| E1  | Area < 10 m² (below Turton minimum)                                  | Warning "area below Turton valid range"; still compute; AI triggered                |
| E2  | Area > 1000 m² (above Turton maximum)                                | Warning "area above Turton valid range"; still compute; AI triggered                |
| E3  | Area > 100 m² with kettle reboiler type                              | Warning "area exceeds kettle reboiler valid range (100 m²)"; still compute          |
| E4  | Pressure > 140 barg                                                  | Clamp to 140 barg; warning "exceeds Turton pressure range"; AI triggered            |
| E5  | Pressure = 0 (atmospheric / no pressure specified)                   | F_P = 1.0; no correction; no warning                                                |
| E6  | Pressures are None                                                   | Default to atmospheric (101325 Pa); F_P = 1.0                                       |
| E7  | Shell material is None                                               | Default to "carbon_steel"                                                           |
| E8  | Tube material is None                                                | Default to "carbon_steel"                                                           |
| E9  | Unknown material combo (e.g., duplex_2205 shell + inconel_600 tubes) | Interpolated F_M from cost ratios; warning; `F_M_interpolated = True`; AI triggered |
| E10 | CEPCI > 90 days stale                                                | Warning "CEPCI may be outdated ({N} days since update)"; AI triggered               |
| E11 | All materials carbon steel + atmospheric pressure                    | Simplest case: F_M = 1.0, F_P = 1.0, C_BM = C_p0 × 3.29 × CEPCI ratio               |
| E12 | tema_type is None or missing                                         | Raise CalculationError — cannot determine cost without HX type                      |
| E13 | area_provided_m2 is None                                             | Raise CalculationError — cannot compute cost without area                           |
| E14 | Shell-side pressure high, tube-side atmospheric                      | Use "both" C-constants (conservative — Turton only has "both" and "tube only")      |
| E15 | Tube-side pressure high, shell-side atmospheric                      | Use "tube only" C-constants                                                         |
| E16 | Both sides > 5 barg                                                  | Use "both" C-constants                                                              |
| E17 | Very small cost (< $1000)                                            | Likely an error — area too small or constants wrong. Warning emitted                |
| E18 | Very large cost (> $10M)                                             | Possibly valid for large Ti/Ti exchanger. No hard limit but AI reviews              |
| E19 | sa516_gr70 used as shell material                                    | Treated as carbon_steel for F_M lookup (same cost class)                            |
| E20 | Step 15 runs but convergence didn't converge                         | Still runs — cost is geometry-dependent, provides estimate with warnings            |

---

## Formula Cross-Reference

| Function                       | Reference                    | Formula                                                                 |
| ------------------------------ | ---------------------------- | ----------------------------------------------------------------------- |
| `purchased_equipment_cost`     | Turton Table A.1             | $\log_{10} C_p^0 = K_1 + K_2 \log_{10}(A) + K_3 [\log_{10}(A)]^2$       |
| `pressure_factor`              | Turton Table A.2             | $\log_{10} F_P = C_1 + C_2 \log_{10}(P) + C_3 [\log_{10}(P)]^2$         |
| `bare_module_cost`             | Turton Table A.4             | $C_{BM} = C_p^0 \times (B_1 + B_2 \cdot F_M \cdot F_P)$                 |
| `cepci_adjust`                 | Standard CEPCI method        | $C_{curr} = C_{base} \times (CEPCI_{curr} / CEPCI_{base})$              |
| `interpolated_material_factor` | Cost-ratio estimation        | $F_M \approx (w_s c_s + w_t c_t) / (w_s c_{CS} + w_t c_{CS})$           |
| `estimate_component_weights`   | Geometry-based approximation | Shell: $\pi D L t \rho$; Tubes: $n \frac{\pi}{4}(d_o^2 - d_i^2) L \rho$ |

---

## Test Count Summary

| Sub-Task                   | Unit Tests | Integration Tests | Total   |
| -------------------------- | ---------- | ----------------- | ------- |
| ST-1 (Cost indices data)   | 23         | —                 | 23      |
| ST-2 (Turton correlations) | 22         | —                 | 22      |
| ST-3 (DesignState fields)  | 3          | —                 | 3       |
| ST-4 (Validation rules)    | 11         | —                 | 11      |
| ST-5 (Step executor)       | 30         | —                 | 30      |
| ST-6 (Pipeline wiring)     | 3          | —                 | 3       |
| ST-7 (Integration)         | —          | 10                | 10      |
| ST-8 (Regression)          | —          | 6                 | 6       |
| **Total**                  | **92**     | **16**            | **108** |

---

## Sanity Check — Expected Cost Ranges

Quick reference for validating results during development:

| Scenario                                         | Area (m²) | Type  | Material | P (barg) | Expected C_BM (2026 USD) |
| ------------------------------------------------ | --------- | ----- | -------- | -------- | ------------------------ |
| Small CS/CS atmospheric                          | 20        | Fixed | CS/CS    | 1        | ~$60,000–$80,000         |
| Medium CS/CS atmospheric                         | 100       | Fixed | CS/CS    | 1        | ~$150,000–$200,000       |
| Medium CS/SS304 atmospheric                      | 100       | Fixed | CS/SS304 | 1        | ~$200,000–$280,000       |
| Large CS/CS atmospheric                          | 500       | Fixed | CS/CS    | 1        | ~$400,000–$550,000       |
| Medium CS/CS high pressure                       | 100       | Float | CS/CS    | 50       | ~$250,000–$350,000       |
| Serth 5.1 approximation (324 tubes, 4.877m, BEM) | ~47       | Fixed | CS/CS    | ~10      | ~$100,000–$150,000       |

These are order-of-magnitude checks, not precise targets. The formulas are well-defined; the check is whether we transcribed the constants correctly.
