# Step 8 Implementation Plan — Shell-Side Heat Transfer Coefficient (Bell-Delaware)

> **Status:** Ready for implementation  
> **Depends on:** Steps 1–7 complete  
> **Primary method:** Bell-Delaware (Taborek, 1983 — HEDH correlations)  
> **Secondary cross-check:** Kern / Simplified Delaware method  
> **AI Mode:** FULL (always — most complex calculation in the pipeline)

---

## Table of Contents

1. [Architectural Decisions](#1-architectural-decisions)
2. [Reference Data & Validation Strategy](#2-reference-data--validation-strategy)
3. [BD-REF-001 Answer Key](#3-bd-ref-001-answer-key)
4. [J-Factor Equations](#4-j-factor-equations)
5. [Žukauskas Ideal Bank Correlations](#5-žukauskas-ideal-bank-correlations)
6. [Implementation Phases](#6-implementation-phases)
7. [File Inventory](#7-file-inventory)
8. [Execution Order & Gates](#8-execution-order--gates)
9. [Reference Sources Summary](#9-reference-sources-summary)

---

## 1. Architectural Decisions

Seven key decisions were made during the discussion phase. These are locked in.

### Decision 1: Pure Float Function Signatures (Option A)

`correlations/bell_delaware.py` uses **pure float arguments** — no Pydantic model imports. A separate `compute_geometry()` helper returns a plain dict of intermediate areas and counts. This keeps the correlation module independently testable with zero coupling to the model layer.

```python
# Example signature
def shell_side_htc(
    shell_id_m: float, tube_od_m: float, tube_pitch_m: float,
    layout_angle_deg: int, n_tubes: int, baffle_cut_pct: float,
    baffle_spacing_central_m: float, ...
) -> dict:
```

### Decision 2: TEMA Clearances in `tema_tables.py`

Shell-baffle (δ_sb) and tube-baffle (δ_tb) clearances are looked up from TEMA RCB-4.3 by shell ID. Added as a new function in the existing `tema_tables.py` — same file that already handles tube count lookups.

- Shell-baffle clearance: 1.6 mm (200 mm shell) to 4.8 mm (1500 mm shell)
- Tube-baffle clearance: 0.4 mm to 0.8 mm by shell ID range
- Function: `get_tema_clearances(shell_id_m, fit_class="normal")` → `{"delta_sb_m": ..., "delta_tb_m": ...}`
- Uses the same `_snap_shell_id()` pattern already in the file

### Decision 3: Piecewise Power-Law (Žukauskas) for Ideal Bank j_i / f_i

Taborek (1983) HEDH Table 10 coefficients — `j_i = a1 × (1.33/PR)^a × Re^a2` where `a = a3 / (1 + 0.14 × Re^a4)`. Four Reynolds number ranges per layout angle (30°, 45°, 60°, 90°). Approximately 40 lines of coefficient tables hardcoded as Python dicts. No graph digitization needed — these are published algebraic fits.

### Decision 4: Full J_b Formula with Sealing Strips Support

The bypass correction J_b uses the full Taborek formula including sealing strip ratio `r_ss = N_ss / N_c`. Default `N_ss = 0` (no sealing strips) so J_b degrades gracefully. The reference case BD-REF-001 uses `N_ss = 2` to validate the sealing strip branch.

### Decision 5: Inlet/Outlet Baffle Spacing Fields

`GeometrySpec` gets `inlet_baffle_spacing_m` and `outlet_baffle_spacing_m` fields, both `Optional[float]` defaulting to `None`. When `None`, code falls back to `baffle_spacing_m` (central spacing). This matters for J_s (unequal spacing correction) and is common in real designs.

### Decision 6: Wall Temperature Iteration for Viscosity Correction

2–3 iteration passes:

1. Estimate T_wall = (T_bulk + T_other_side) / 2
2. Get μ_wall at T_wall via thermo adapter
3. Compute h_o with (μ_bulk/μ_wall)^0.14 correction
4. Recalculate T_wall from heat balance: T_wall = T_bulk ± Q_local / (h_o × A_local)
5. Re-get μ_wall, recompute h_o
6. Check convergence (|Δh_o| < 1%)

Typically converges in 2 passes. Cap at 3 to avoid infinite loops.

### Decision 7: Kern Cross-Check — Dual Validation

Compute both Bell-Delaware (primary) and Kern/Simplified Delaware (secondary) h_o values. Compare:

- **Divergence > 20%** → WARNING (flag to AI reviewer)
- **Divergence > 50%** → ERROR (escalate to user)

This is not "pick the lower value" — it's a sanity signal. Bell-Delaware is always the reported h_o. The Kern value is metadata for validation.

---

## 2. Reference Data & Validation Strategy

### 2.1 Why Not RAG/Supermemory for Correlation Data

**Decision:** Hardcode correlation constants as Python dicts. RAG is reserved for runtime AI context only.

**Rationale:** Correlation coefficients (Žukauskas a1/a2/a3/a4, J-factor formula constants) are fixed published mathematics — not retrieval targets. Embedding them in a vector store adds latency, hallucination risk, and a retrieval failure mode for data that never changes. Hardcoded dicts are:

- Deterministic (no retrieval failure)
- Auditable (diff-able in git)
- Fast (no embedding lookup)
- Testable (unit test compares dict to published source)

### 2.2 BD-REF-001 — Self-Documenting Reference Calculator

**The core validation artifact.** A standalone Python script (`tests/fixtures/bd_ref_calculator.py`) that:

1. Defines a canonical geometry (0.489m shell, 158 tubes, 30° triangular, 25% cut)
2. Implements every Bell-Delaware formula from Taborek (1983)
3. Computes every intermediate value deterministically
4. Runs 8 internal sanity checks
5. Outputs a JSON answer key (`tests/fixtures/bd_ref_001.json`)

**Why 100% confidence:** There are no "I recall the answer was about X" steps. Every number is a deterministic output of published correlations applied to defined inputs. Change an input → re-run → get a new answer key.

### 2.3 Serth 5.1 — Kern Cross-Check Validation

**Important limitation:** Serth Example 5.1 uses the **Simplified Delaware method** (Kern-like with j_H correlation), NOT the full Bell-Delaware with J-factors. Therefore:

- J_c, J_l, J_b, J_s, J_r reference values are **NOT available** from Serth 5.1
- Serth 5.1 is only useful as the **Kern cross-check** reference: h_o ≈ 692.8 W/m²K ±15%

**Serth 5.1 Key Data (Second Trial, SI):**

| Parameter      | Value                             |
| -------------- | --------------------------------- |
| Shell ID       | 0.489 m (19.25 in)                |
| Tubes          | 124, 4 passes                     |
| Tube OD/ID     | 1" OD, 14 BWG (25.4 mm / 21.2 mm) |
| Pitch          | 1.25" square (31.75 mm)           |
| Baffle cut     | 20%                               |
| Baffle spacing | 0.0978 m                          |
| Re_shell       | 37,158                            |
| h_o (Kern)     | 692.8 W/m²K (122 Btu/h·ft²·°F)    |
| h_i            | 885.8 W/m²K                       |
| U_D            | 261.2 W/m²K                       |

**Serth 5.1 Key Data (Imperial, for cross-reference):**

| Parameter        | Value                    |
| ---------------- | ------------------------ |
| Shell side fluid | Crude oil, 350°F → 250°F |
| Tube side fluid  | Gasoline, 150°F → 250°F  |
| Q                | 13.92 × 10⁶ Btu/h        |
| m_hot            | 150,000 lb/h             |
| m_cold           | 112,500 lb/h             |
| LMTD             | 63.05°F                  |
| F                | 0.8656                   |
| U_D (assumed)    | 60 Btu/h·ft²·°F          |

### 2.4 NPTEL Kern Method Reference

A second Kern cross-check source from NPTEL "Process Design of Heat Exchanger":

- Kerosene cooled by gasoline
- 31" shell, 368 tubes, 1-6 tube passes, square pitch
- h_o = 155.3 Btu/h·ft²·°F (Kern)
- h_i = 141.3 Btu/h·ft²·°F
- U_o,cal = 53.5 Btu/h·ft²·°F
- Provides: equivalent diameter formulas (square & triangular), j_H correlations, shell-side crossflow area, pressure drop formulas, fouling factors

### 2.5 Coulson & Richardson Graphs

Four uploaded graphs (Figures 12.23, 12.24, 12.29, 12.30) — these are **Kern method** j_H and j_f factors, NOT Bell-Delaware J-factors. Useful for:

- Implementing the Kern cross-check layer
- Visual sanity checks during development
- NOT for primary Bell-Delaware validation

### 2.6 Validation Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                    VALIDATION GATES                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  PRIMARY: BD-REF-001 (Bell-Delaware)                        │
│  ├── Geometry values: ±0.5%                                 │
│  ├── Each J-factor: ±0.5%                                   │
│  ├── h_ideal: ±2%                                           │
│  └── h_o: ±2%                                               │
│  → MUST PASS before any step code is written                │
│                                                             │
│  SECONDARY: Serth 5.1 (Kern cross-check)                    │
│  ├── h_o_kern: ±15% of 692.8 W/m²K                         │
│  └── Validates cross-check layer, not primary method        │
│                                                             │
│  TERTIARY: NPTEL Kern example (optional)                    │
│  └── Second independent Kern cross-check data point         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. BD-REF-001 Answer Key

Full deterministic answer key. Every number is computed from Taborek (1983) HEDH correlations, not recalled from memory.

### 3.1 Inputs

```json
{
  "shell_id_m": 0.489,
  "tube_od_m": 0.01905,
  "tube_id_m": 0.01483,
  "tube_pitch_m": 0.0254,
  "pitch_ratio": 1.3333,
  "layout_angle_deg": 30,
  "num_tubes": 158,
  "tube_length_m": 4.877,
  "tube_passes": 2,
  "baffle_cut_pct": 25.0,
  "baffle_spacing_central_m": 0.1956,
  "baffle_spacing_inlet_m": 0.3048,
  "baffle_spacing_outlet_m": 0.3048,
  "num_baffles": 22,
  "num_sealing_strips": 2,
  "clearances": {
    "tube_baffle_diametral_m": 0.0008,
    "shell_baffle_diametral_m": 0.003175,
    "bundle_shell_diametral_m": 0.0111
  },
  "fluid": {
    "description": "Light hydrocarbon oil @ 80C mean",
    "density_kg_m3": 820.0,
    "viscosity_Pa_s": 0.00052,
    "viscosity_wall_Pa_s": 0.00068,
    "Cp_J_kgK": 2200.0,
    "k_W_mK": 0.138,
    "Pr": 8.2899,
    "mass_flow_kg_s": 36.0
  }
}
```

### 3.2 Intermediate Geometry

| Quantity     | Value    | Description                         |
| ------------ | -------- | ----------------------------------- |
| D_otl_m      | 0.4779   | Outer tube limit diameter           |
| F_c          | 0.621753 | Fraction of tubes in crossflow      |
| F_w          | 0.189123 | Fraction of tubes in window         |
| S_m_m²       | 0.014196 | Crossflow area at bundle centerline |
| S_w_m²       | 0.028199 | Window flow area                    |
| S_tb_m²      | 0.003067 | Tube-to-baffle leakage area         |
| S_sb_m²      | 0.001626 | Shell-to-baffle leakage area        |
| S_b_m²       | 0.002171 | Bundle bypass area                  |
| r_lm         | 0.330588 | Leakage area ratio                  |
| r_s          | 0.346451 | Shell-to-baffle leakage fraction    |
| F_bp         | 0.152947 | Bypass fraction                     |
| N_c_rows     | 11.12    | Crossflow tube rows                 |
| N_cw_rows    | 4.45     | Window tube rows                    |
| G_s (kg/m²s) | 2536.01  | Shell-side mass velocity            |
| Re_shell     | 92,905.8 | Shell-side Reynolds number          |

### 3.3 Results

| Quantity    | Value              | Formula / Note                            |
| ----------- | ------------------ | ----------------------------------------- |
| j_ideal     | 0.003792           | Taborek Table 10, a1=0.321, a2=−0.388     |
| **h_ideal** | **4,974.78 W/m²K** | j_i × Cp × G_s × Pr^(−2/3) × (μ/μ_w)^0.14 |
| J_c         | 0.997662           | 25% cut → F_c ≈ 0.622 → near-unity        |
| J_l         | 0.631822           | Biggest penalty — leakage eats 37%        |
| J_b         | 0.942130           | 2 sealing strips keep bypass modest       |
| J_s         | 0.969802           | Inlet/outlet spacing 1.56× central        |
| J_r         | 1.000000           | Turbulent → no adverse gradient           |
| ΠJ          | 0.575934           | Product of all 5 J-factors                |
| **h_o**     | **2,865.14 W/m²K** | h_ideal × ΠJ                              |

### 3.4 Gate Assertion Tolerances

| Category                | Tolerance | Rationale                                               |
| ----------------------- | --------- | ------------------------------------------------------- |
| Geometry & J-factors    | ±0.5%     | Pure algebra — tight                                    |
| h values (h_ideal, h_o) | ±2.0%     | Minor sensitivity to j-factor correlation interpolation |

### 3.5 Correlation Citations

| Quantity | Citation                                                                          |
| -------- | --------------------------------------------------------------------------------- |
| j_ideal  | Taborek (1983) HEDH Table 10, Sec 3.3.10 — `j_i = a1*(1.33/PR)^a * Re^a2`         |
| J_c      | Taborek (1983) Eq 3.3.10-1 — `J_c = 0.55 + 0.72*F_c`                              |
| J_l      | Taborek (1983) Eq 3.3.10-2 — `J_l = 0.44(1-r_s) + [1-0.44(1-r_s)]*exp(-2.2*r_lm)` |
| J_b      | Taborek (1983) Eq 3.3.10-3 — `J_b = exp(-C_bh*F_bp*[1-(2*r_ss)^(1/3)])`           |
| J_s      | Taborek (1983) Eq 3.3.10-4 — ratio of power-law corrected spacings                |
| J_r      | Taborek (1983) Eq 3.3.10-5 — `1.0 for Re >= 100`                                  |

---

## 4. J-Factor Equations

All 5 J-factors are computed from **closed-form algebraic equations** — no graph interpolation, no digitization needed.

### J_c — Baffle Cut Correction

```
θ_ctl = 2 × arccos(D_s × (1 - 2 × B_c/100) / D_otl)
F_c = 1/π × (π + 2 × (D_s(1-2Bc/100)/D_otl) × sin(arccos(...)) - arccos(...))
  -- simplified form: computed from baffle cut geometry
J_c = 0.55 + 0.72 × F_c
```

For 25% cut → F_c ≈ 0.622 → J_c ≈ 0.998 (near unity — most tubes in crossflow)

### J_l — Leakage Correction

```
r_lm = (S_tb + S_sb) / S_m          # total leakage / crossflow area
r_s  = S_sb / (S_tb + S_sb)         # shell leak fraction of total leakage
J_l  = 0.44(1 - r_s) + [1 - 0.44(1 - r_s)] × exp(-2.2 × r_lm)
```

Typically the **biggest penalty** (J_l ≈ 0.5–0.8). Leakage through clearances bypasses crossflow.

### J_b — Bundle Bypass Correction

```
F_bp = S_b / S_m                     # bypass fraction
r_ss = N_ss / N_c                    # sealing strip ratio
C_bh = 1.35 for Re < 100, 1.25 for Re >= 100
J_b  = exp(-C_bh × F_bp × [1 - (2 × r_ss)^(1/3)])
```

When `r_ss >= 0.5`, J_b = 1.0 (bypass fully sealed). Without sealing strips (N_ss=0), J_b can be 0.7–0.9.

### J_s — Unequal Baffle Spacing Correction

```
n = 0.6 (turbulent exponent for heat transfer)
J_s = (N_b - 1 + (L_i/L_c)^(1-n) + (L_o/L_c)^(1-n)) / (N_b - 1 + (L_i/L_c) + (L_o/L_c))
```

When inlet/outlet spacing equals central spacing → J_s = 1.0. Larger end spacings → J_s < 1.0.

### J_r — Adverse Temperature Gradient Correction (Laminar)

```
For Re >= 100:  J_r = 1.0
For Re >= 20:   J_r = (10/N_c)^0.18
For Re < 20:    J_r = (10/N_c)^0.18 × (Re/20)^0.5  -- very small exchangers only
```

In turbulent flow (Re > 10,000), J_r is always 1.0. Only matters for viscous laminar flow.

---

## 5. Žukauskas Ideal Bank Correlations

### Taborek (1983) HEDH Table 10 — j_i Coefficients

The ideal tube-bank Colburn j-factor uses:

```
j_i = a1 × (1.33 / PR)^a × Re^a2
where a = a3 / (1 + 0.14 × Re^a4)
```

Coefficient table (example for 30° triangular layout):

| Re Range    | a1    | a2     | a3    | a4    |
| ----------- | ----- | ------ | ----- | ----- |
| 10^0 – 10^1 | 1.40  | −0.667 | 1.450 | 0.519 |
| 10^1 – 10^2 | 0.321 | −0.388 | 1.450 | 0.519 |
| 10^2 – 10^3 | 0.321 | −0.388 | 1.450 | 0.519 |
| 10^3 – 10^4 | 0.321 | −0.388 | 1.450 | 0.519 |
| 10^4 – 10^5 | 0.321 | −0.388 | 1.450 | 0.519 |

_(Full 4-angle × 4-range table to be hardcoded in `bell_delaware.py`)_

### h_ideal Calculation

```
h_ideal = j_i × Cp × G_s × Pr^(-2/3) × (μ_bulk / μ_wall)^0.14
```

Where:

- `G_s = m_dot / S_m` (shell-side mass velocity through crossflow area)
- `S_m` = crossflow area at bundle centerline (from geometry)
- `Pr^(-2/3)` = Prandtl number correction
- `(μ_bulk/μ_wall)^0.14` = viscosity correction (requires wall temp iteration)

---

## 6. Implementation Phases

### Phase 0: Save Reference Calculator (Pre-requisite)

**Files to create:**

- `tests/fixtures/bd_ref_calculator.py` — the self-documenting Python script already run in terminal
- `tests/fixtures/bd_ref_001.json` — the deterministic JSON answer key

**Gate:** `python bd_ref_calculator.py` reproduces `bd_ref_001.json` exactly. All 8 internal sanity checks pass.

### Phase 1: Data Layer — TEMA Clearances

**File to modify:** `hx_engine/app/data/tema_tables.py`

Add `get_tema_clearances(shell_id_m, fit_class="normal")`:

- Returns `{"delta_sb_m": float, "delta_tb_m": float}`
- Data from TEMA RCB-4.3
- Shell-baffle diametral clearance (mm): interpolated from table by shell ID
- Tube-baffle diametral clearance (mm): stepped by shell ID range
- Uses same `_snap_shell_id()` pattern already in the file

**TEMA RCB-4.3 Clearance Data (approximate):**

| Shell ID (mm) | δ_sb diametral (mm) | δ_tb diametral (mm) |
| ------------- | ------------------- | ------------------- |
| 200           | 1.6                 | 0.4                 |
| 300           | 2.0                 | 0.4                 |
| 400           | 2.4                 | 0.4                 |
| 500           | 2.8                 | 0.8                 |
| 600           | 3.2                 | 0.8                 |
| 800           | 3.6                 | 0.8                 |
| 1000          | 4.0                 | 0.8                 |
| 1200          | 4.4                 | 0.8                 |
| 1500          | 4.8                 | 0.8                 |

**Test:** `tests/unit/test_tema_clearances.py` — spot-check 3 shell sizes.

### Phase 2: Model Updates

**File to modify:** `hx_engine/app/models/design_state.py`

#### GeometrySpec — New Fields

```python
# Absolute pitch (some calcs need it directly, not just ratio)
tube_pitch_m: Optional[float] = None

# Bell-Delaware specific
n_sealing_strip_pairs: Optional[int] = 0
inlet_baffle_spacing_m: Optional[float] = None   # defaults to baffle_spacing_m in code
outlet_baffle_spacing_m: Optional[float] = None   # defaults to baffle_spacing_m in code
n_baffles: Optional[int] = None
```

Validators:

- `tube_pitch_m`: range [0.01, 0.10]
- `n_sealing_strip_pairs`: range [0, 20]
- `inlet_baffle_spacing_m`: range [0.05, 2.0] (same as central)
- `outlet_baffle_spacing_m`: range [0.05, 2.0]
- `n_baffles`: range [1, 100]

#### DesignState — New Fields

```python
# --- shell-side heat transfer (populated by Step 8) ---
h_shell_W_m2K: Optional[float] = None
Re_shell: Optional[float] = None
shell_side_j_factors: Optional[dict] = None  # {"J_c": ..., "J_l": ..., "J_b": ..., "J_s": ..., "J_r": ..., "product": ...}
h_shell_ideal_W_m2K: Optional[float] = None
h_shell_kern_W_m2K: Optional[float] = None   # Kern cross-check value
```

**Gate:** No import errors, all existing tests still pass after adding fields.

### Phase 3: Core Correlation — `correlations/bell_delaware.py`

The most critical and complex file. Pure-float functions, zero model imports, zero side effects. Follows the same pattern as `correlations/gnielinski.py`.

#### 3a. `compute_geometry()` — Geometric Areas & Counts

Takes all geometric floats, returns a dict:

```python
def compute_geometry(
    shell_id_m: float, tube_od_m: float, tube_pitch_m: float,
    layout_angle_deg: int, n_tubes: int, tube_passes: int,
    baffle_cut_pct: float, baffle_spacing_central_m: float,
    baffle_spacing_inlet_m: float, baffle_spacing_outlet_m: float,
    n_baffles: int, n_sealing_strip_pairs: int,
    delta_tb_m: float, delta_sb_m: float, delta_bundle_shell_m: float,
) -> dict:
    """Return geometry dict with all intermediate areas and counts.

    Keys: D_otl, F_c, F_w, S_m, S_w, S_tb, S_sb, S_b,
          r_lm, r_s, F_bp, N_c, N_cw, G_s, Re_shell
    """
```

Key formulas:

- `D_otl = D_s - delta_bundle_shell` (outer tube limit)
- `θ_ctl = 2 × arccos((D_s(1 - 2×Bc/100)) / D_otl)` (central angle)
- `F_c = (1/π)(π + 2(D_s(1-2Bc/100)/D_otl)sin(θ_ctl/2) - θ_ctl)` (crossflow fraction)
- `F_w = (N_tubes_window) / N_t` (window fraction — from geometric calculation)
- `S_m = B × (D_s - D_otl + (D_otl/P_t)(P_t - d_o))` for triangular layout
- `S_w = window area minus tubes in window`
- `S_tb = (π/4)((d_o + δ_tb)² - d_o²) × N_t × (1 - F_c)` (tube-baffle leakage)
- `S_sb = π × D_s × (δ_sb/2) × (1 - θ_ctl/(2π))` (shell-baffle leakage)
- `S_b = B × (D_s - D_otl)` (bypass area, reduced for pass lanes)
- `N_c = (D_s × (1 - 2×Bc/100)) / P_p` (crossflow rows)
- `N_cw` = rows in window (from geometry)

This geometry dict is **reused in Step 10** (shell-side pressure drop) — the separation is deliberate.

#### 3b. `ideal_bank_ji()` — Taborek Table 10

```python
def ideal_bank_ji(Re: float, layout_angle_deg: int, pitch_ratio: float) -> float:
    """Taborek (1983) HEDH Table 10 — ideal Colburn j-factor.

    j_i = a1 × (1.33/PR)^a × Re^a2
    where a = a3 / (1 + 0.14 × Re^a4)
    """
```

Coefficient table hardcoded as nested dict:

```python
_JI_COEFFS = {
    30: [  # 30° triangular
        (1, 10, 1.40, -0.667, 1.450, 0.519),
        (10, 100, ...),
        ...
    ],
    45: [...],  # 45° rotated square
    60: [...],  # 60° (equivalent to 30° mirrored, same coeffs)
    90: [...],  # 90° square
}
```

#### 3c. Five J-Factor Functions

Each takes relevant geometry values and returns a single float:

```python
def compute_J_c(F_c: float) -> float:
    """Taborek Eq 3.3.10-1: J_c = 0.55 + 0.72 × F_c"""

def compute_J_l(S_tb: float, S_sb: float, S_m: float, S_w: float) -> float:
    """Taborek Eq 3.3.10-2: leakage correction"""

def compute_J_b(F_bp: float, N_ss: int, N_c: float, Re: float) -> float:
    """Taborek Eq 3.3.10-3: bypass correction with sealing strips"""

def compute_J_s(N_b: int, N_c: float, N_cw: float,
                L_i: float, L_o: float, L_c: float) -> float:
    """Taborek Eq 3.3.10-4: unequal baffle spacing correction"""

def compute_J_r(Re: float, N_c: float, N_cw: float) -> float:
    """Taborek Eq 3.3.10-5: adverse temp gradient (laminar only)"""
```

#### 3d. `shell_side_htc()` — Orchestrator

```python
def shell_side_htc(
    # geometry params ...
    # fluid params: rho, mu, mu_wall, Cp, k, Pr, m_dot ...
    # clearance params ...
) -> dict:
    """Compute shell-side h using Bell-Delaware method.

    Returns dict with keys:
        h_ideal, j_i, J_c, J_l, J_b, J_s, J_r, J_product,
        h_o, Re_shell, geometry (sub-dict), warnings
    """
    geom = compute_geometry(...)
    j_i = ideal_bank_ji(geom["Re_shell"], layout_angle_deg, pitch_ratio)
    h_ideal = j_i * Cp * geom["G_s"] * Pr**(-2/3) * (mu/mu_wall)**0.14

    J_c = compute_J_c(geom["F_c"])
    J_l = compute_J_l(geom["S_tb"], geom["S_sb"], geom["S_m"], geom["S_w"])
    J_b = compute_J_b(geom["F_bp"], n_sealing_strips, geom["N_c"], geom["Re_shell"])
    J_s = compute_J_s(n_baffles, geom["N_c"], geom["N_cw"], L_i, L_o, L_c)
    J_r = compute_J_r(geom["Re_shell"], geom["N_c"], geom["N_cw"])

    J_product = J_c * J_l * J_b * J_s * J_r
    h_o = h_ideal * J_product

    return {
        "h_ideal_W_m2K": h_ideal,
        "h_o_W_m2K": h_o,
        "j_i": j_i,
        "J_c": J_c, "J_l": J_l, "J_b": J_b, "J_s": J_s, "J_r": J_r,
        "J_product": J_product,
        "Re_shell": geom["Re_shell"],
        "geometry": geom,
        "warnings": [],
    }
```

#### 3e. Gate Test: `test_bell_delaware_vs_ref.py`

```python
# Loads bd_ref_001.json
# Calls shell_side_htc() with BD-REF-001 inputs
# Asserts:
#   - Each geometry value within ±0.5%
#   - Each J-factor within ±0.5%
#   - h_ideal within ±2%
#   - h_o within ±2%
```

**THIS GATE MUST PASS BEFORE PROCEEDING TO PHASE 4.**
If it fails → debug `bell_delaware.py`, NOT the reference calculator.

### Phase 4: Kern Cross-Check (Optional Separate Correlation or Inline)

Simplified Delaware / Kern method for h_o:

1. Compute equivalent diameter `D_e` (hydraulic or equivalent, depends on pitch layout)
2. Shell-side crossflow area `A_s = D_s × B × C' / P_t` (where C' = clearance between tubes)
3. Shell-side mass velocity `G_s = m_dot / A_s`
4. `Re_kern = D_e × G_s / μ`
5. Read `j_H` from Kern correlation (or use fit: `j_H = a × Re^b` from Coulson & Richardson Fig 12.29)
6. `h_o_kern = j_H × k / D_e × (μ/μ_w)^0.14`

This can either be:

- A separate function in `bell_delaware.py` (e.g., `kern_shell_side_htc(...)`)
- Or a lightweight inline calculation in `step_08_shell_side_h.py`

The Kern value is **metadata only** — not reported as the primary h_o. It's only for the divergence check.

### Phase 5: Step Orchestration — `steps/step_08_shell_side_h.py`

Follows the exact pattern of `step_07_tube_side_h.py`:

```python
class Step08ShellSideH(BaseStep):
    step_id: int = 8
    step_name: str = "Shell-Side Heat Transfer Coefficient"
    ai_mode: AIModeEnum = AIModeEnum.FULL  # ALWAYS — most complex step

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        """Required from Steps 1-7:
        - geometry: shell_diameter_m, tube_od_m, baffle_spacing_m, pitch_ratio,
                    baffle_cut, n_tubes, pitch_layout (+ optional new fields)
        - shell_side_fluid (from Step 4)
        - fluid properties for shell-side stream
        - temperatures (for wall temp iteration)
        """

    async def execute(self, state: "DesignState") -> StepResult:
        """
        1. Check preconditions
        2. Identify shell-side fluid
        3. Get fluid properties at bulk temp
        4. Compute TEMA clearances via get_tema_clearances()
        5. Resolve inlet/outlet baffle spacing (default to central)
        6. Call bell_delaware.shell_side_htc() → h_o, J-factors, intermediates
        7. Wall temperature iteration (2-3 passes):
           a. T_wall = T_bulk ± Q/(h_o × A)
           b. Get μ_wall at T_wall via thermo adapter
           c. Recompute h_o with updated μ_wall
           d. Check convergence |Δh_o| < 1%
        8. Kern cross-check: compute h_o_kern, log divergence
        9. Write to state:
           - state.h_shell_W_m2K = h_o
           - state.Re_shell = Re
           - state.shell_side_j_factors = {"J_c": ..., "J_l": ..., ...}
           - state.h_shell_ideal_W_m2K = h_ideal
           - state.h_shell_kern_W_m2K = h_o_kern
        10. Build outputs dict with all intermediates
        11. Add escalation hints for edge cases
        12. Return StepResult
        """
```

**AI trigger:** Always FULL mode — no `_conditional_ai_trigger()` needed. The AI reviewer sees all intermediates, J-factors, and the Kern cross-check divergence. This is the most complex single calculation in the pipeline and benefits from AI review on every run.

**Wall temperature iteration detail:**

```
Iteration 0:
  T_wall_est = (T_bulk_shell + T_bulk_tube) / 2
  μ_wall = get_fluid_properties(fluid, T_wall_est).viscosity_Pa_s
  h_o_0 = bell_delaware.shell_side_htc(..., mu_wall=μ_wall)

Iteration 1:
  T_wall_1 = T_bulk_shell - Q / (h_o_0 × A_shell)  [or + for heating]
  μ_wall_1 = get_fluid_properties(fluid, T_wall_1).viscosity_Pa_s
  h_o_1 = bell_delaware.shell_side_htc(..., mu_wall=μ_wall_1)

Iteration 2 (if needed):
  T_wall_2 = T_bulk_shell - Q / (h_o_1 × A_shell)
  μ_wall_2 = get_fluid_properties(fluid, T_wall_2).viscosity_Pa_s
  h_o_2 = bell_delaware.shell_side_htc(..., mu_wall=μ_wall_2)

Convergence: |h_o_n - h_o_(n-1)| / h_o_(n-1) < 0.01  → stop
Max iterations: 3
```

### Phase 6: Rules — `steps/step_08_rules.py`

Follows the exact pattern of `step_07_rules.py`:

#### Hard Rules (AI cannot override)

| Rule | Check                    | Fail Message                                             |
| ---- | ------------------------ | -------------------------------------------------------- |
| R1   | `h_shell_W_m2K > 0`      | "h_shell must be positive"                               |
| R2   | Each J ∈ [0.2, 1.2]      | "J\_{name} = {val} outside physical range [0.2, 1.2]"    |
| R3   | `J_c × J_l × J_b > 0.30` | "Combined correction product too low — geometry suspect" |
| R4   | `Re_shell > 0`           | "Shell-side Re must be positive"                         |

#### Soft Rules (Warnings / Escalation)

| Rule | Check                    | Action                                    |
| ---- | ------------------------ | ----------------------------------------- |
| W1   | BD/Kern divergence > 20% | WARNING — flag to AI reviewer             |
| W2   | BD/Kern divergence > 50% | ERROR — escalate to user                  |
| W3   | `h_o < 50 W/m²K`         | WARNING — unusually low, possible fouling |
| W4   | `h_o > 15000 W/m²K`      | WARNING — unusually high, verify inputs   |

#### Registration

```python
def register_step8_rules() -> None:
    register_rule(8, _rule_h_positive)
    register_rule(8, _rule_j_factors_range)
    register_rule(8, _rule_j_product_floor)
    register_rule(8, _rule_re_positive)
```

Step 08 module imports `step_08_rules` at module level (same pattern as Step 07):

```python
import hx_engine.app.steps.step_08_rules  # noqa: F401
```

### Phase 7: Integration Test

**File:** `tests/unit/test_step_08_integration.py` (or `tests/integration/test_step_08.py`)

Full pipeline test (Steps 1→8) with a realistic input set:

1. Build a DesignState with Steps 1–7 already populated
2. Run Step08ShellSideH.execute()
3. Verify:
   - `state.h_shell_W_m2K` is populated and > 0
   - `state.Re_shell` is populated and > 0
   - `state.shell_side_j_factors` contains all 5 J-factors
   - All J-factors in [0.2, 1.2]
   - J-product > 0.30
   - Kern cross-check was computed (h_shell_kern_W_m2K is not None)
   - Kern divergence logged (present in outputs)
   - Layer 2 rules pass
   - StepResult has no empty outputs

---

## 7. File Inventory

### Files to Create

| File                                          | Purpose                               | Phase |
| --------------------------------------------- | ------------------------------------- | ----- |
| `tests/fixtures/bd_ref_calculator.py`         | Self-documenting reference calculator | 0     |
| `tests/fixtures/bd_ref_001.json`              | Deterministic JSON answer key         | 0     |
| `hx_engine/app/correlations/bell_delaware.py` | Core Bell-Delaware correlations       | 3     |
| `hx_engine/app/steps/step_08_shell_side_h.py` | Step 8 orchestration                  | 5     |
| `hx_engine/app/steps/step_08_rules.py`        | Layer 2 validation rules              | 6     |
| `tests/unit/test_bell_delaware_vs_ref.py`     | BD-REF-001 gate test                  | 3     |
| `tests/unit/test_tema_clearances.py`          | TEMA clearance unit test              | 1     |
| `tests/unit/test_step_08_integration.py`      | Integration test                      | 7     |

### Files to Modify

| File                                   | Change                                | Phase |
| -------------------------------------- | ------------------------------------- | ----- |
| `hx_engine/app/data/tema_tables.py`    | Add `get_tema_clearances()`           | 1     |
| `hx_engine/app/models/design_state.py` | Add GeometrySpec + DesignState fields | 2     |

### Files Referenced (Read Only)

| File                                         | Pattern to Follow                                       |
| -------------------------------------------- | ------------------------------------------------------- |
| `hx_engine/app/correlations/gnielinski.py`   | Pure-float correlation function pattern                 |
| `hx_engine/app/steps/step_07_tube_side_h.py` | Step class pattern (preconditions, execute, AI trigger) |
| `hx_engine/app/steps/step_07_rules.py`       | Rule registration pattern                               |
| `hx_engine/app/steps/base.py`                | BaseStep 4-layer review loop                            |

---

## 8. Execution Order & Gates

| Order | Phase   | What                                  | Gate Criteria                                                                    |
| ----- | ------- | ------------------------------------- | -------------------------------------------------------------------------------- |
| 1     | Phase 0 | Save reference calculator + JSON      | Files exist; `python bd_ref_calculator.py` reproduces JSON; 8 sanity checks pass |
| 2     | Phase 1 | `tema_tables.py` clearances           | Unit test passes (3 shell sizes spot-checked)                                    |
| 3     | Phase 2 | `GeometrySpec` + `DesignState` fields | No import errors; ALL existing tests still pass                                  |
| 4     | Phase 3 | `correlations/bell_delaware.py`       | **BD-REF-001 gate: geometry ±0.5%, J-factors ±0.5%, h values ±2%**               |
| 5     | Phase 4 | Kern cross-check function             | Serth 5.1 h_o_kern ≈ 692.8 ±15%                                                  |
| 6     | Phase 5 | `step_08_shell_side_h.py`             | Existing tests pass + step produces valid outputs                                |
| 7     | Phase 6 | `step_08_rules.py`                    | Rule tests pass (positive/negative cases)                                        |
| 8     | Phase 7 | Integration test                      | Full pipeline Steps 1→8, all assertions green                                    |

**Critical:** Phase 3 / Phase 4 (the BD-REF-001 gate) is the make-or-break moment. If it fails, debug `bell_delaware.py` — not the reference calculator. Everything downstream is plumbing.

---

## 9. Reference Sources Summary

| Source                             | Type         | What It Provides                                                 | Used For                                    |
| ---------------------------------- | ------------ | ---------------------------------------------------------------- | ------------------------------------------- |
| **Taborek (1983) HEDH**            | Primary      | All Bell-Delaware formulas, j_i coefficients, J-factor equations | `bell_delaware.py` implementation           |
| **BD-REF-001** (self-computed)     | Primary gate | Deterministic answer key with all intermediates                  | Gate assertion (±0.5% / ±2%)                |
| **Serth Example 5.1**              | Secondary    | Kern/Simplified Delaware h_o = 692.8 W/m²K                       | Kern cross-check validation                 |
| **NPTEL Kern Method**              | Tertiary     | Independent Kern example (kerosene/gasoline)                     | Optional second Kern cross-check            |
| **Coulson & Richardson Fig 12.29** | Reference    | j_H vs Re curves for Kern method                                 | Visual sanity check for Kern implementation |
| **TEMA RCB-4.3**                   | Data table   | Shell-baffle & tube-baffle clearances by shell ID                | `get_tema_clearances()` data                |

---

## Appendix A: RAG vs Hardcoded Decision Log

**Question asked:** Should we use RAG/Supermemory to store Serth 5.1 textbook data and correlation coefficients?

**Answer:** No, for correlation constants.

| Approach                      | Pros                                                | Cons                                                                   |
| ----------------------------- | --------------------------------------------------- | ---------------------------------------------------------------------- |
| **RAG for correlations**      | Flexible, can add more textbooks                    | Latency, hallucination risk, retrieval failure mode, non-deterministic |
| **Hardcoded Python dicts** ✅ | Deterministic, auditable, fast, testable, diff-able | Must manually add new data                                             |

**Policy:** Correlation coefficients (Žukauskas a1/a2, J-factor constants) → hardcoded Python dicts. RAG → reserved for runtime AI context (design notes, cross-step observations, textbook prose guidance).

---

## Appendix B: Why Step 8 is AI Mode FULL

Every other step in the pipeline has `ai_mode = CONDITIONAL` or `ai_mode = NONE`. Step 8 is the only step that is **always** `FULL`. Reasons:

1. **Most complex single calculation** — 5 correction factors, each with multiple sub-calculations
2. **Geometry sensitivity** — small changes in clearances can swing h_o by 30%+
3. **Cross-check interpretation** — AI needs to reason about BD vs Kern divergence
4. **Vibration risk** — crossflow velocity must be checked against TEMA vibration limits
5. **No "obviously correct" regime** — unlike tube-side (well-understood Gnielinski), shell-side flow is inherently complex with bypass and leakage streams

The AI reviewer receives all intermediate values (j_i, all J-factors, geometry areas, crossflow velocity, Kern cross-check divergence) and can flag issues that hard rules can't catch — like a suspiciously high J_c with very low baffle cut, or a geometry where bypass dominates but no sealing strips were specified.

---

## Appendix C: Shell-Side Pressure Drop Reuse

The `compute_geometry()` function returns all areas (S_m, S_w, S_tb, S_sb, S_b) and row counts (N_c, N_cw) that Step 10 (Shell-Side Pressure Drop) also needs. This is why geometry computation is separated from h_o computation — Step 10 calls `compute_geometry()` directly and applies its own R_l, R_b, R_s correction factors for pressure drop (similar concept to J-factors but different coefficients).

The architecture ensures:

- Step 8 calls `compute_geometry()` → uses result for h_o
- Step 10 calls `compute_geometry()` → uses result for ΔP_shell
- Same geometry, guaranteed-consistent areas, no divergence between HTC and pressure drop calculations

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR (PLAN) | 8 issues, 2 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |

- **OUTSIDE VOICE:** Claude subagent, 10 findings. Key: circular BD validation, nested convergence question, Kern threshold too aggressive, bulk vs wall T undocumented. All 4 cross-model tensions resolved.
- **UNRESOLVED:** 0
- **VERDICT:** ENG CLEARED — ready to implement. P1 TODO: find external BD reference before Phase 3 gate.
