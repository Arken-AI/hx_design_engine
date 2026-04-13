# Step 14 Implementation Plan — Mechanical Design Check

**Status:** Planning  
**Depends on:** Steps 1–13 (complete), BaseStep infrastructure (complete)  
**Reference:** STEPS_6_16_PLAN.md §Phase C, ARKEN_MASTER_PLAN.md §6.3, ASME BPVC Section VIII Div 1 (UG-27, UG-28, UG-33), ASME B36.10M/B36.19M  
**Date:** 2026-04-10

---

## Overview

Step 14 is a **post-convergence mechanical adequacy check** that verifies the converged geometry can withstand operating pressures and thermal stresses. It runs once on the final geometry from Step 12 (after Step 13 vibration check).

Three independent sub-checks:

1. **Tube wall adequacy** — UG-27 (internal pressure) + UG-28 (external pressure / shell-side collapse)
2. **Shell wall adequacy** — UG-27 (internal) + UG-28 (external / vacuum), with standard pipe schedule lookup
3. **Thermal expansion differential** — differential growth between tubes and shell, checked against TEMA type tolerance

**AI Mode: CONDITIONAL** — AI called only if `P_hot_Pa > 3e6 or P_cold_Pa > 3e6` (30 bar) OR thickness margin < 20% OR expansion differential exceeds tolerance for fixed-tubesheet type.

**Scope:** Single-phase liquids (Phase 1). Tubesheet thickness is NOT checked (deferred per STEPS_6_16_PLAN.md).

---

## Primary References

- **ASME BPVC Section VIII Div 1, UG-27:** Internal pressure — cylindrical shells
- **ASME BPVC Section VIII Div 1, UG-28:** External pressure — cylindrical shells (two-step Factor A/B procedure)
- **ASME BPVC Section II Part D, Subpart 1:** Tables 1A/1B — allowable stress S vs temperature
- **ASME BPVC Section II Part D, Subpart 3:** Table G + material charts (CS, HA, NFC, NFN, NFT) — Factor A/B data
- **ASME BPVC Section II Part D, Tables TE-1–TE-6:** Mean thermal expansion coefficients
- **ASME B36.10M / B36.19M:** Standard pipe dimensions (NPS → OD, wall thickness by schedule)
- **Serth & Lestina (2014):** Process Heat Transfer, Chapter 7 — mechanical design

---

## Agreed Design Decisions

| #   | Decision                                                                                                                                    | Rationale                                                                |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| D1  | Implement full UG-27 + UG-28 for both tubes and shell — no shortcuts                                                                        | User requested full scope, no stubs or deferrals                         |
| D2  | Design pressure = max(1.1 × P_operating, P_operating + 175000 Pa), whichever is greater                                                     | Standard industry practice per ASME VIII UG-21                           |
| D3  | Corrosion allowance: 3.175 mm (1/8") for carbon steel, 1.5 mm for alloy steels, 0 for Ti/exotic                                             | Industry defaults; conservative for Phase 1                              |
| D4  | Weld joint efficiency: E=1.0 for seamless tubes (SA-179), E=0.85 for shell (spot-examined longitudinal weld)                                | Standard assumptions; E=1.0 for full radiography can be an AI correction |
| D5  | Shell material defaults to `"carbon_steel"` unless shell-side fluid is corrosive                                                            | Add `shell_material` field to DesignState; Step 4 can set it             |
| D6  | Tube external pressure: unsupported length = baffle spacing (central span)                                                                  | Conservative — actual L is between baffles                               |
| D7  | Shell external pressure: L = tangent-to-tangent length (baffles are NOT code stiffeners)                                                    | Per ASME VIII UG-28 definition of L for unstiffened shells               |
| D8  | Vacuum detection: if P_shell < 101325 Pa or P_tube < 101325 Pa → external pressure check required                                           | Automatic detection — no user flag needed                                |
| D9  | Pipe schedule lookup for shells ≤ NPS 24 (610 mm); rolled plate for larger shells → report t_min only                                       | Standard industry practice                                               |
| D10 | Thermal expansion tolerance: fixed tubesheet (BEM/NEN) → max 3 mm differential; floating head (AES/AEU) → informational only; U-tube → skip | Per TEMA standards and industry practice                                 |
| D11 | TEMA type correction: if expansion fails on fixed tubesheet → AI recommends BEM→AES, flagged as ESCALATE                                    | Step 14 cannot re-converge; geometry changes need Step 12 re-run         |
| D12 | Factor A/B interpolation: log-log for A→B within a temperature curve; linear in temperature between curves                                  | Per ASME standard engineering practice                                   |
| D13 | Tubesheet thickness: NOT checked in Phase 1 — noted as limitation in output                                                                 | Per STEPS_6_16_PLAN.md                                                   |
| D14 | Share `material_properties.py` with Step 13 — add S_MPa, alpha_um_mK tables alongside existing E_GPa                                        | Same interpolation pattern, same module                                  |
| D15 | Admiralty brass (C44300) uses NFC-3 (90-10 CuNi) as conservative proxy for external pressure                                                | C44300 not in ASME external pressure charts; CuNi is weaker → safe       |
| D16 | Shell material for external pressure uses CS-2 (S_y ≥ 207 MPa) for SA-516 Gr.70                                                             | Standard refinery shell material                                         |

---

## Computation Flow

```
1. INPUTS (from DesignState)
   ├── Geometry: tube_od_m, tube_id_m, shell_diameter_m, tube_length_m,
   │             baffle_spacing_m, n_baffles, n_passes
   ├── Pressures: P_hot_Pa, P_cold_Pa
   ├── Temperatures: T_hot_in_C, T_hot_out_C, T_cold_in_C, T_cold_out_C
   ├── Materials: tube_material, shell_material (default: carbon_steel)
   ├── TEMA type: tema_type (for expansion tolerance check)
   └── Allocation: shell_side_fluid (hot/cold → determines which P is shell-side)

2. DESIGN PRESSURE CALCULATION
   ├── P_design_tube = max(1.1 × P_tube, P_tube + 175000)
   └── P_design_shell = max(1.1 × P_shell, P_shell + 175000)

3. TUBE WALL CHECK
   ├── 3a. Internal pressure (UG-27):
   │   ├── S = get_allowable_stress(tube_material, T_design_tube)
   │   ├── t_min_int = P_tube_internal × d_o / (2 × S × E_weld + P_tube_internal)
   │   └── t_actual = (tube_od - tube_id) / 2  [from BWG gauge]
   │
   └── 3b. External pressure (UG-28):
       ├── L = baffle_spacing_m (unsupported length)
       ├── D_o/t = tube_od / t_actual
       ├── L/D_o = L / tube_od
       ├── Factor_A = table_G_lookup(D_o_t, L_D_o)
       ├── Factor_B = material_chart_lookup(tube_material, T_design, Factor_A)
       ├── P_a = 4B / (3 × D_o/t)  OR  P_a = 2AE / (3 × D_o/t)  [elastic]
       └── Check: P_external ≤ P_a

4. SHELL WALL CHECK
   ├── 4a. Internal pressure (UG-27):
   │   ├── S = get_allowable_stress(shell_material, T_design_shell)
   │   ├── R = shell_ID / 2
   │   ├── CA = get_corrosion_allowance(shell_material)
   │   ├── t_min = P_shell_internal × R / (S × E_weld - 0.6 × P_shell_internal) + CA
   │   └── Lookup standard pipe schedule → find lightest adequate schedule
   │
   └── 4b. External pressure (UG-28) — if vacuum detected:
       ├── L = tube_length_m (tangent-to-tangent approximation)
       ├── t = shell wall thickness from pipe schedule
       ├── D_o/t, L/D_o → Factor_A → Factor_B → P_a
       └── Check: P_external ≤ P_a

5. THERMAL EXPANSION CHECK
   ├── α_tube = get_thermal_expansion(tube_material, T_mean_tube)
   ├── α_shell = get_thermal_expansion(shell_material, T_mean_shell)
   ├── ΔL_tube = α_tube × L × (T_mean_tube - 20)
   ├── ΔL_shell = α_shell × L × (T_mean_shell - 20)
   ├── expansion_mm = |ΔL_tube - ΔL_shell| × 1000
   └── Check vs TEMA type tolerance (D10)

6. OUTPUTS → DesignState
   ├── tube_thickness_ok: bool
   ├── shell_thickness_ok: bool
   ├── expansion_mm: float
   ├── mechanical_details: dict  (all intermediate values)
   └── warnings: list[str]
```

---

## Sub-Tasks

### ST-1: Extend `material_properties.py` — Allowable Stress Tables

**File:** `hx_engine/app/data/material_properties.py` — MODIFY  
**Action:** Add `S_MPa` table to each material in `_MATERIAL_PROPERTIES`

**Data source:** ASME BPVC Section II Part D, Tables 1A (ferrous) / 1B (non-ferrous)

Add to each material entry:

```python
"S_MPa": {
    temp_C: allowable_stress_MPa,
    ...
}
```

Add getter function:

```python
def get_allowable_stress(material: str, temperature_C: float = 25.0) -> float:
    """Return maximum allowable stress in Pa at the specified temperature.

    Uses same bisect interpolation as get_elastic_modulus().
    """
```

**Materials to encode (10 total):**

| Material          | ASME Spec     | Table | Key Temps (°C) |
| ----------------- | ------------- | ----- | -------------- |
| `carbon_steel`    | SA-179        | 1A    | 40–450         |
| `stainless_304`   | SA-213 TP304  | 1A    | 40–815         |
| `stainless_316`   | SA-213 TP316  | 1A    | 40–815         |
| `copper`          | SB-75 C12200  | 1B    | 40–205         |
| `admiralty_brass` | SB-111 C44300 | 1B    | 40–205         |
| `titanium`        | SB-338 Gr.2   | 1B    | 40–315         |
| `inconel_600`     | SB-163 N06600 | 1B    | 40–540         |
| `monel_400`       | SB-163 N04400 | 1B    | 40–480         |
| `duplex_2205`     | SA-240 S31803 | 1A    | 40–315         |
| `sa516_gr70`      | SA-516 Gr.70  | 1A    | 40–480         |

> Note: `sa516_gr70` is added for shell material. Tube materials map to existing 9 entries.

#### ST-1 Tests

| Test | Description                                                            | Asserts                                  |
| ---- | ---------------------------------------------------------------------- | ---------------------------------------- |
| T1.1 | `get_allowable_stress("carbon_steel", 100)` returns expected value     | Within ±1 MPa of ASME table              |
| T1.2 | `get_allowable_stress("stainless_304", 370)` — mid-range interpolation | Reasonable value between 370°C neighbors |
| T1.3 | Temperature below table range → clamps to lowest                       | Returns S at min temp                    |
| T1.4 | Temperature above table range → clamps to highest                      | Returns S at max temp                    |
| T1.5 | Unknown material raises `KeyError`                                     | Exception                                |
| T1.6 | All 10 materials return positive stress at 25°C                        | S > 0 for all                            |
| T1.7 | Stress decreases with temperature (sanity)                             | S(400°C) < S(100°C) for each material    |

---

### ST-2: Extend `material_properties.py` — Thermal Expansion Tables

**File:** `hx_engine/app/data/material_properties.py` — MODIFY  
**Action:** Add `alpha_um_mK` table (mean coefficient of thermal expansion, µm/m·°C) to each material

**Data source:** ASME BPVC Section II Part D, Tables TE-1 through TE-6

Add to each material entry:

```python
"alpha_um_mK": {
    temp_C: coeff_um_per_m_per_K,
    ...
}
```

Add getter function:

```python
def get_thermal_expansion(material: str, temperature_C: float = 25.0) -> float:
    """Return mean thermal expansion coefficient in 1/°C (not µm/m·°C).

    Divides stored µm/m·°C value by 1e6 to return dimensionless 1/°C.
    """
```

**Materials to encode (10 total — same 9 + sa516_gr70):**

| Material          | ASME Table | α at 100°C (µm/m·°C) | α at 300°C |
| ----------------- | ---------- | -------------------- | ---------- |
| `carbon_steel`    | TE-1       | ~12.0                | ~13.2      |
| `stainless_304`   | TE-1       | ~16.0                | ~17.2      |
| `stainless_316`   | TE-1       | ~15.9                | ~17.1      |
| `copper`          | TE-3       | ~17.0                | —          |
| `admiralty_brass` | TE-3       | ~20.0                | —          |
| `titanium`        | TE-5       | ~8.9                 | ~9.4       |
| `inconel_600`     | TE-4       | ~13.3                | ~14.4      |
| `monel_400`       | TE-4       | ~14.0                | ~15.1      |
| `duplex_2205`     | TE-1       | ~13.0                | ~14.0      |
| `sa516_gr70`      | TE-1       | ~12.0                | ~13.2      |

#### ST-2 Tests

| Test | Description                                                   | Asserts                        |
| ---- | ------------------------------------------------------------- | ------------------------------ |
| T2.1 | `get_thermal_expansion("carbon_steel", 100)` returns expected | Within ±0.5e-6 of reference    |
| T2.2 | `get_thermal_expansion("stainless_304", 200)` — interpolation | Between 100°C and 300°C values |
| T2.3 | Returns dimensionless 1/°C (not µm/m·°C)                      | Value ≈ 12e-6, not 12.0        |
| T2.4 | Expansion increases with temperature                          | α(300°C) > α(100°C) for each   |
| T2.5 | Stainless > carbon steel (known physical fact)                | α_304 > α_CS at same temp      |
| T2.6 | Titanium has lowest expansion of all 9 tube materials         | α_Ti < α_others                |
| T2.7 | Unknown material raises `KeyError`                            | Exception                      |

---

### ST-3: Create `data/asme_external_pressure.py` — Table G + Factor B Charts

**File:** `hx_engine/app/data/asme_external_pressure.py` — CREATE  
**Action:** Encode complete Table G (~250 points) and Factor B material charts for 10 materials

**Structure:**

```python
# Table G: {D_o_t: [(L_D_o, Factor_A), ...]}
TABLE_G: dict[int, list[tuple[float, float]]] = {
    4: [(2.2, 0.0959), (2.6, 0.0884), ...],
    5: [(1.4, 0.0929), ...],
    ...
    1000: [(0.05, 0.00113), ...],
}

# Material charts: {chart_id: {temp_C: [(Factor_A, Factor_B_MPa), ...]}}
FACTOR_B_CHARTS: dict[str, dict[int, list[tuple[float, float]]]] = {
    "CS-1": {
        150: [(1.35e-5, 1.38), (6.45e-4, 64.8), ...],
        260: [...],
        ...
    },
    "HA-1": { ... },
    ...
}

# Material → chart mapping
MATERIAL_TO_CHART: dict[str, str] = {
    "carbon_steel": "CS-1",
    "stainless_304": "HA-1",
    "stainless_316": "HA-2",
    "copper": "NFC-1",
    "admiralty_brass": "NFC-3",  # conservative proxy
    "titanium": "NFT-1",
    "inconel_600": "NFN-4",
    "monel_400": "NFN-3",
    "duplex_2205": "HA-5",
    "sa516_gr70": "CS-2",       # shell material
}
```

**Public API:**

```python
def lookup_factor_A(D_o_t: float, L_D_o: float) -> float:
    """Interpolate Factor A from Table G using log-log interpolation."""

def lookup_factor_B(material: str, temperature_C: float, factor_A: float) -> tuple[float, bool]:
    """Return (Factor_B_MPa, is_elastic).

    is_elastic=True when factor_A falls below the lowest A in the
    temperature curve (elastic buckling regime).
    """
```

**Charts to encode (10):**

| Chart | Material              | Temp Curves   | Data Points |
| ----- | --------------------- | ------------- | ----------- |
| CS-1  | carbon_steel (SA-179) | 5 (150–480°C) | ~50         |
| CS-2  | sa516_gr70 (shell)    | 5 (150–480°C) | ~50         |
| HA-1  | stainless_304         | 6 (40–815°C)  | ~60         |
| HA-2  | stainless_316         | 6 (40–815°C)  | ~70         |
| HA-5  | duplex_2205           | 3 (20–345°C)  | ~35         |
| NFC-1 | copper (C12200)       | 1 (65°C)      | ~8          |
| NFC-3 | admiralty_brass proxy | 3 (65–315°C)  | ~30         |
| NFN-3 | monel_400             | 6 (40–480°C)  | ~90         |
| NFN-4 | inconel_600           | 8 (40–650°C)  | ~60         |
| NFT-1 | titanium Gr.2         | 4 (40–315°C)  | ~70         |

**Total:** ~520 material data points + ~250 Table G points = ~770 data points

#### ST-3 Tests

| Test  | Description                                                                | Asserts                       |
| ----- | -------------------------------------------------------------------------- | ----------------------------- |
| T3.1  | `lookup_factor_A(100, 3.0)` — exact Table G entry for D_o/t=100, L/D_o=3.0 | Matches table value ±1%       |
| T3.2  | `lookup_factor_A(75, 2.5)` — interpolation between D_o/t=50 and D_o/t=80   | Reasonable interpolated value |
| T3.3  | `lookup_factor_A(4, 50)` — boundary (smallest D_o/t, largest L/D_o)        | Returns valid A               |
| T3.4  | `lookup_factor_A(1000, 0.05)` — boundary (largest D_o/t, smallest L/D_o)   | Returns valid A               |
| T3.5  | `lookup_factor_B("carbon_steel", 150, 0.001)` — CS-1 at 150°C              | B ≈ 77.2 MPa ±5%              |
| T3.6  | `lookup_factor_B("stainless_304", 370, 0.001)` — HA-1 at 370°C             | B ≈ 39.7 MPa ±5%              |
| T3.7  | `lookup_factor_B("carbon_steel", 150, 1e-6)` — below curve → elastic       | `is_elastic=True`             |
| T3.8  | `lookup_factor_B("titanium", 205, 0.005)` — NFT-1 mid-curve                | B within expected range       |
| T3.9  | Temperature interpolation: B at 275°C between 260 and 370 curves for CS-1  | Between respective B values   |
| T3.10 | Unknown material raises `KeyError`                                         | Exception                     |
| T3.11 | Verify ASME design example: CS shell, D_o=1000mm, t=12mm, L=3000mm, 150°C  | P_a ≈ 0.104 MPa ±10%          |
| T3.12 | Verify ASME design example: 304 SS, D_o=600mm, t=8mm, L=2400mm, 370°C      | P_a ≈ 1.097 MPa ±10%          |
| T3.13 | All charts have monotonically increasing A values per temperature          | `A[i+1] > A[i]`               |
| T3.14 | All charts have monotonically increasing B values per temperature          | `B[i+1] >= B[i]`              |

---

### ST-4: Create `data/pipe_schedules.py` — Standard Pipe Dimensions

**File:** `hx_engine/app/data/pipe_schedules.py` — CREATE  
**Action:** Encode ASME B36.10M / B36.19M standard pipe dimensions

**Structure:**

```python
# {NPS_inches: {"od_mm": float, "schedules": {schedule: wall_mm}}}
PIPE_SCHEDULE_TABLE: dict[float, dict] = {
    6: {"od_mm": 168.3, "schedules": {10: 3.40, 20: 4.78, 30: 6.35, 40: 7.11, 80: 10.97}},
    8: {"od_mm": 219.1, "schedules": {10: 3.76, 20: 6.35, 30: 7.04, 40: 8.18, 60: 10.31, 80: 12.70}},
    ...
    48: {"od_mm": 1219.2, "schedules": {}}  # rolled plate
}
```

**Public API:**

```python
def find_nps_for_shell(shell_id_m: float) -> tuple[float, float]:
    """Return (NPS_inches, OD_mm) for the nearest standard pipe matching shell ID.

    For shells > NPS 24, returns the NPS but schedules may be empty (rolled plate).
    """

def find_minimum_schedule(nps: float, t_min_mm: float) -> tuple[int | None, float | None]:
    """Return (schedule_number, wall_mm) of the lightest schedule with wall ≥ t_min.

    Returns (None, None) if no standard schedule is thick enough.
    """

def get_pipe_wall(nps: float, schedule: int) -> float:
    """Return wall thickness in mm for a specific NPS and schedule."""
```

**NPS sizes to encode (14):**  
6, 8, 10, 12, 14, 16, 18, 20, 24, 30, 36, 42, 48 inches

#### ST-4 Tests

| Test | Description                                                                         | Asserts                               |
| ---- | ----------------------------------------------------------------------------------- | ------------------------------------- |
| T4.1 | `find_nps_for_shell(0.305)` → NPS 12 (ID ≈ ~309 mm)                                 | Returns NPS 12                        |
| T4.2 | `find_nps_for_shell(0.508)` → NPS 20                                                | Returns NPS 20                        |
| T4.3 | `find_nps_for_shell(1.0)` → NPS 42 (rolled plate range)                             | Returns NPS 42                        |
| T4.4 | `find_minimum_schedule(20, 6.0)` → (10, 6.35) or next available                     | Wall ≥ 6.0 mm                         |
| T4.5 | `find_minimum_schedule(8, 20.0)` → None (no schedule thick enough?) or max schedule | Handles gracefully                    |
| T4.6 | All pipe ODs are correct per ASME B36.10M                                           | Spot-check 5 NPS values               |
| T4.7 | Schedules within each NPS are in ascending order of wall thickness                  | `wall[sch_i] < wall[sch_j]` for i < j |

---

### ST-5: Create `correlations/asme_thickness.py` — ASME Thickness Calculations

**File:** `hx_engine/app/correlations/asme_thickness.py` — CREATE  
**Action:** Pure calculation functions for UG-27, UG-28, and thermal expansion

**Functions:**

```python
def design_pressure(P_operating_Pa: float) -> float:
    """Return design pressure per UG-21 convention.

    P_design = max(1.1 × P_operating, P_operating + 175000)
    """

def tube_internal_pressure_thickness(
    P_Pa: float, d_o_m: float, S_Pa: float, E_weld: float = 1.0
) -> float:
    """UG-27: Minimum tube wall thickness for internal pressure.

    t_min = P × d_o / (2 × S × E + P)
    Returns thickness in meters.
    """

def shell_internal_pressure_thickness(
    P_Pa: float, R_i_m: float, S_Pa: float, E_weld: float = 0.85,
    CA_m: float = 0.003175
) -> float:
    """UG-27: Minimum shell wall thickness for internal pressure.

    t_min = P × R / (S × E - 0.6 × P) + CA
    Returns thickness in meters.
    """

def external_pressure_allowable(
    D_o_m: float, t_m: float, L_m: float,
    material: str, temperature_C: float
) -> dict:
    """UG-28: Maximum allowable external pressure.

    Returns {
        "D_o_t": float,
        "L_D_o": float,
        "factor_A": float,
        "factor_B_MPa": float | None,
        "is_elastic": bool,
        "P_allowable_Pa": float,
        "E_Pa": float,
    }
    """

def thermal_expansion_differential(
    tube_material: str, shell_material: str,
    T_mean_tube_C: float, T_mean_shell_C: float,
    tube_length_m: float, T_ambient_C: float = 20.0
) -> dict:
    """Calculate differential thermal expansion between tubes and shell.

    Returns {
        "dL_tube_mm": float,
        "dL_shell_mm": float,
        "differential_mm": float,
        "alpha_tube": float,
        "alpha_shell": float,
    }
    """

def get_corrosion_allowance(material: str) -> float:
    """Return corrosion allowance in meters for the given material."""
```

#### ST-5 Tests

| Test  | Description                                                                                | Asserts                                              |
| ----- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------- |
| T5.1  | `design_pressure(1e6)` → max(1.1e6, 1.175e6) = 1.175e6                                     | Correct                                              |
| T5.2  | `design_pressure(5e6)` → max(5.5e6, 5.175e6) = 5.5e6                                       | Correct                                              |
| T5.3  | `tube_internal_pressure_thickness(1e6, 0.01905, 118e6)` — typical case                     | t_min ≈ 0.08 mm (very thin — tubes are thick enough) |
| T5.4  | `shell_internal_pressure_thickness(1e6, 0.254, 118e6)` — NPS 20 shell                      | t_min in reasonable range (2–5 mm)                   |
| T5.5  | `external_pressure_allowable(0.01905, 0.00211, 0.127, "carbon_steel", 150)` — typical tube | P_a >> 1 bar (tubes too stiff to buckle)             |
| T5.6  | `external_pressure_allowable(0.610, 0.010, 4.877, "sa516_gr70", 150)` — shell vacuum       | P_a ≈ 0.1 MPa (borderline for vacuum)                |
| T5.7  | ASME example validation: CS shell D_o=1000mm, t=12mm, L=3000mm, 150°C                      | P_a ≈ 0.104 MPa ±10%                                 |
| T5.8  | ASME example validation: 304 SS D_o=600mm, t=8mm, L=2400mm, 370°C                          | P_a ≈ 1.097 MPa ±10%                                 |
| T5.9  | `thermal_expansion_differential("stainless_304", "carbon_steel", 150, 80, 4.877)`          | differential_mm ≈ 2–4 mm (304 expands more)          |
| T5.10 | Zero ΔT → zero expansion                                                                   | differential_mm = 0                                  |
| T5.11 | Same material on both sides → nearly zero differential                                     | differential_mm ≈ 0                                  |
| T5.12 | `get_corrosion_allowance("carbon_steel")` → 0.003175 m                                     | Correct                                              |
| T5.13 | `get_corrosion_allowance("titanium")` → 0.0                                                | Correct                                              |
| T5.14 | P=0 → t_min=0 (no pressure, no thickness needed)                                           | t_min = CA only                                      |
| T5.15 | Negative pressure input → raises ValueError                                                | Exception                                            |

---

### ST-6: Add DesignState Fields for Step 14

**File:** `hx_engine/app/models/design_state.py` — MODIFY  
**Action:** Add Step 14 output fields after the vibration check section

```python
# --- mechanical design check (populated by Step 14) ---
tube_thickness_ok: Optional[bool] = None
shell_thickness_ok: Optional[bool] = None
expansion_mm: Optional[float] = None
mechanical_details: Optional[dict] = None
shell_material: Optional[str] = None  # default: "carbon_steel"
```

**`mechanical_details` schema:**

```python
{
    "design_pressure_tube_Pa": float,
    "design_pressure_shell_Pa": float,
    "tube": {
        "t_actual_mm": float,
        "t_min_internal_mm": float,
        "margin_internal_pct": float,
        "external_pressure": {
            "D_o_t": float,
            "L_D_o": float,
            "factor_A": float,
            "factor_B_MPa": float | None,
            "is_elastic": bool,
            "P_allowable_Pa": float,
            "P_applied_Pa": float,
            "adequate": bool,
        },
    },
    "shell": {
        "nps_inches": float,
        "od_mm": float,
        "t_min_internal_mm": float,
        "recommended_schedule": int | None,
        "recommended_wall_mm": float | None,
        "corrosion_allowance_mm": float,
        "external_pressure": { ... } | None,  # None if not vacuum
    },
    "expansion": {
        "dL_tube_mm": float,
        "dL_shell_mm": float,
        "differential_mm": float,
        "tolerance_mm": float | None,  # None for floating head
        "tema_type": str,
        "within_tolerance": bool | None,
    },
    "limitations": ["Tubesheet thickness not checked (Phase 1)"],
}
```

#### ST-6 Tests

| Test | Description                                                                 | Asserts                       |
| ---- | --------------------------------------------------------------------------- | ----------------------------- |
| T6.1 | New fields default to `None`                                                | No breakage in existing tests |
| T6.2 | `shell_material` defaults to `None` (set by Step 4 or defaulted in Step 14) | Default is None               |
| T6.3 | DesignState round-trips through JSON with new fields                        | Serialize + deserialize works |

---

### ST-7: Create `steps/step_14_rules.py` — Hard Validation Rules

**File:** `hx_engine/app/steps/step_14_rules.py` — CREATE  
**Action:** Layer 2 hard rules that AI cannot override

**Rules:**

| Rule | Check                                                         | Hard Fail                                             |
| ---- | ------------------------------------------------------------- | ----------------------------------------------------- |
| R1   | `tube_thickness_ok is not None`                               | Result must be computed                               |
| R2   | `shell_thickness_ok is not None`                              | Result must be computed                               |
| R3   | `mechanical_details is not None`                              | Details must be populated                             |
| R4   | Tube internal: `t_actual >= t_min_internal`                   | Hard fail if tube too thin                            |
| R5   | Tube external: `P_applied <= P_allowable`                     | Hard fail if shell-side pressure would collapse tubes |
| R6   | Shell internal: `t_min > 0` (sanity)                          | Calculated minimum must be positive                   |
| R7   | Expansion: if fixed tubesheet, `expansion_mm <= tolerance_mm` | Hard fail if thermal expansion exceeds tolerance      |

#### ST-7 Tests

| Test | Description                                                                         | Asserts           |
| ---- | ----------------------------------------------------------------------------------- | ----------------- |
| T7.1 | All rules pass with valid mechanical_details                                        | All PASS          |
| T7.2 | Missing `tube_thickness_ok` → R1 fails                                              | FAIL with message |
| T7.3 | t_actual < t_min_internal → R4 fails                                                | FAIL              |
| T7.4 | P_applied > P_allowable for external → R5 fails                                     | FAIL              |
| T7.5 | expansion_mm > tolerance for BEM type → R7 fails                                    | FAIL              |
| T7.6 | expansion_mm > tolerance for AES type → R7 PASSES (floating head tolerance is None) | PASS              |
| T7.7 | Null mechanical_details → R3 fails                                                  | FAIL              |

---

### ST-8: Create `steps/step_14_mechanical.py` — Step Executor

**File:** `hx_engine/app/steps/step_14_mechanical.py` — CREATE  
**Action:** Implement `Step14MechanicalCheck(BaseStep)` following Step 13 pattern

**Key decisions in execute():**

1. Determine which pressure is tube-side vs shell-side from `shell_side_fluid`
2. Compute design pressures (D2)
3. Resolve tube wall from BWG gauge → `get_wall_thickness()`
4. Run tube internal + external pressure checks
5. Run shell internal pressure, lookup pipe schedule
6. If vacuum detected (D8) → run shell external pressure check
7. Compute thermal expansion differential
8. Check expansion against TEMA type tolerance (D10)
9. Populate `tube_thickness_ok`, `shell_thickness_ok`, `expansion_mm`, `mechanical_details`
10. Generate warnings and build `StepResult`

**AI trigger condition:**

```python
def _conditional_ai_trigger(self, state: DesignState) -> bool:
    P_max = max(state.P_hot_Pa or 0, state.P_cold_Pa or 0)
    if P_max > 3e6:  # > 30 bar
        return True
    if state.mechanical_details:
        margin = state.mechanical_details.get("tube", {}).get("margin_internal_pct", 100)
        if margin < 20:
            return True
        expansion = state.mechanical_details.get("expansion", {})
        if expansion.get("within_tolerance") is False:
            return True
    return False
```

#### ST-8 Tests

| Test  | Description                                                                      | Asserts                                                  |
| ----- | -------------------------------------------------------------------------------- | -------------------------------------------------------- |
| T8.1  | Basic execution with typical geometry (19.05mm OD, BWG 14, NPS 20 shell, 10 bar) | `tube_thickness_ok=True`, `shell_thickness_ok=True`      |
| T8.2  | Output populates all DesignState fields                                          | All 5 fields non-None after execution                    |
| T8.3  | `mechanical_details` has correct structure (all keys present)                    | JSON schema check                                        |
| T8.4  | Shell-side hot fluid → correct pressure assignment                               | P_shell = P_hot, P_tube = P_cold                         |
| T8.5  | Shell-side cold fluid → correct pressure assignment                              | P_shell = P_cold, P_tube = P_hot                         |
| T8.6  | Low pressure (1 bar) → no AI trigger                                             | `_conditional_ai_trigger() == False`                     |
| T8.7  | High pressure (50 bar) → AI trigger                                              | `_conditional_ai_trigger() == True`                      |
| T8.8  | Missing pressures (None) → default to atmospheric                                | P_design ≈ 0.275 MPa                                     |
| T8.9  | Unknown tube_material → defaults to carbon_steel (like Step 13)                  | No error; uses fallback                                  |
| T8.10 | In convergence loop → AI skipped                                                 | `_should_call_ai() == False`                             |
| T8.11 | Fixed tubesheet (BEM) with high ΔT → expansion warning                           | Warning about expansion                                  |
| T8.12 | Floating head (AES) with high ΔT → no expansion failure                          | `expansion` within_tolerance is None                     |
| T8.13 | Vacuum service detection → shell external pressure check runs                    | `mechanical_details.shell.external_pressure` is not None |
| T8.14 | Non-vacuum service → shell external pressure check skipped                       | `mechanical_details.shell.external_pressure` is None     |
| T8.15 | Step metadata: step_id=14, step_name, ai_mode=CONDITIONAL                        | Correct values                                           |
| T8.16 | Missing preconditions → raises `CalculationError`                                | Appropriate error                                        |
| T8.17 | Tube external pressure: typical BWG 14 tube at 10 bar                            | P_allowable >> P_applied (tubes very stiff)              |
| T8.18 | Thin-wall tube (BWG 18) at high shell pressure → tighter margin                  | Lower margin but still OK at moderate pressure           |
| T8.19 | Shell pipe schedule recommendation is correct                                    | Lightest schedule with wall ≥ t_min                      |
| T8.20 | Large shell (> NPS 24) → rolled plate note                                       | Warning/note about rolled plate                          |

---

### ST-9: Wire Step 14 into Pipeline Runner

**File:** `hx_engine/app/core/pipeline_runner.py` — MODIFY  
**Action:** Add Step 14 after Step 13 in the pipeline sequence

```python
from hx_engine.app.steps.step_14_mechanical import Step14MechanicalCheck

# In STEP_SEQUENCE or equivalent:
# ... Step 13 ...
Step14MechanicalCheck(),
# ... Step 15 ...
```

#### ST-9 Tests

| Test | Description                                         | Asserts                                               |
| ---- | --------------------------------------------------- | ----------------------------------------------------- |
| T9.1 | Pipeline includes Step 14 in sequence after Step 13 | Step 14 in step list                                  |
| T9.2 | Step 14 receives converged geometry from Step 12    | state.convergence_converged is True when Step 14 runs |

---

### ST-10: Integration Tests — Step 14 End-to-End

**File:** `tests/integration/test_step_14_integration.py` — CREATE  
**Action:** Full integration tests that run Step 14 with realistic DesignState

#### ST-10 Tests

| Test  | Description                                                         | Asserts                                                   |
| ----- | ------------------------------------------------------------------- | --------------------------------------------------------- |
| T10.1 | Serth Example 5.1 geometry through Step 14                          | All three checks pass; mechanical_details fully populated |
| T10.2 | High-pressure case (50 bar tube-side) → AI triggered                | Conditional AI returns True                               |
| T10.3 | Vacuum shell-side → external pressure check runs                    | Shell external pressure result present                    |
| T10.4 | BEM type with 304 SS tubes + CS shell, ΔT=120°C → expansion warning | differential_mm > 3 mm                                    |
| T10.5 | AES type with same conditions → expansion OK (floating head)        | within_tolerance is None                                  |
| T10.6 | Step 14 + rules pass → all rules return PASS                        | Zero hard rule failures                                   |
| T10.7 | Step 14 populates StepResult with correct outputs dict              | outputs has all key fields                                |
| T10.8 | Step record appended to state.step_records                          | len(step_records) increases by 1                          |

---

### ST-11: ASME External Pressure Validation Tests (Benchmark Gate)

**File:** `tests/unit/test_asme_external_pressure_validation.py` — CREATE  
**Action:** Validate external pressure calculations against known ASME examples

These are **benchmark tests** — they validate the encoded data and interpolation against published worked examples.

| Test  | Description                                                          | Expected Result | Tolerance                       |
| ----- | -------------------------------------------------------------------- | --------------- | ------------------------------- |
| T11.1 | CS shell: D_o=1000mm, t=12mm, L=3000mm, 150°C → P_a                  | 0.104 MPa       | ±10%                            |
| T11.2 | 304 SS shell: D_o=600mm, t=8mm, L=2400mm, 370°C → P_a                | 1.097 MPa       | ±10%                            |
| T11.3 | Typical tube: 19.05mm OD, BWG 14 (t=2.11mm), baffle=127mm, CS, 150°C | P_a >> 1 MPa    | P_a > 5 MPa (tube won't buckle) |
| T11.4 | Table G interpolation accuracy: D_o/t=20, L/D_o=2.0                  | A = 0.00713     | ±5%                             |
| T11.5 | Table G boundary: D_o/t=4, L/D_o=2.2                                 | A = 0.0959      | ±1% (exact table entry)         |
| T11.6 | CS-1 Factor B: A=0.001, 150°C                                        | B = 77.2 MPa    | ±2%                             |
| T11.7 | HA-1 Factor B: A=0.001, 370°C                                        | B = 39.7 MPa    | ±5%                             |
| T11.8 | NFT-1 Factor B: A=0.003, 205°C                                       | B ≈ 66.9 MPa    | ±5%                             |

---

### ST-12: Full Application Regression Tests

**File:** `tests/integration/test_step_14_regression.py` — CREATE  
**Action:** Ensure Step 14 doesn't break existing functionality

| Test  | Description                                                                                   | Asserts                                     |
| ----- | --------------------------------------------------------------------------------------------- | ------------------------------------------- |
| T12.1 | Run Steps 1–13 → verify all still pass (no regression)                                        | All existing test assertions hold           |
| T12.2 | DesignState serialization with new fields → JSON round-trip                                   | No field corruption                         |
| T12.3 | Step 14 with empty/None pressures → graceful handling (defaults to atm)                       | No crash                                    |
| T12.4 | Step 14 with missing geometry → raises CalculationError (not crash)                           | Proper exception                            |
| T12.5 | Step 14 with missing tube_material → uses default (no crash)                                  | Fallback works                              |
| T12.6 | material_properties.py backward compatibility → existing E, density, poisson calls unaffected | All existing material_properties tests pass |
| T12.7 | Step 13 still works after material_properties.py changes                                      | All Step 13 tests pass                      |

---

## File Summary

| File                                                   | Action | Sub-Task   | Description                          |
| ------------------------------------------------------ | ------ | ---------- | ------------------------------------ |
| `hx_engine/app/data/material_properties.py`            | MODIFY | ST-1, ST-2 | Add S_MPa + alpha tables + getters   |
| `hx_engine/app/data/asme_external_pressure.py`         | CREATE | ST-3       | Table G + 10 Factor B charts         |
| `hx_engine/app/data/pipe_schedules.py`                 | CREATE | ST-4       | Standard pipe NPS/schedule data      |
| `hx_engine/app/correlations/asme_thickness.py`         | CREATE | ST-5       | UG-27, UG-28, expansion calculations |
| `hx_engine/app/models/design_state.py`                 | MODIFY | ST-6       | Add 5 new fields                     |
| `hx_engine/app/steps/step_14_rules.py`                 | CREATE | ST-7       | 7 hard validation rules              |
| `hx_engine/app/steps/step_14_mechanical.py`            | CREATE | ST-8       | Step executor                        |
| `hx_engine/app/core/pipeline_runner.py`                | MODIFY | ST-9       | Wire Step 14 into sequence           |
| `tests/unit/test_material_properties_step14.py`        | CREATE | ST-1, ST-2 | Tests for S, α getters               |
| `tests/unit/test_asme_external_pressure.py`            | CREATE | ST-3       | Tests for Table G + Factor B lookups |
| `tests/unit/test_pipe_schedules.py`                    | CREATE | ST-4       | Tests for pipe schedule lookup       |
| `tests/unit/test_asme_thickness.py`                    | CREATE | ST-5       | Tests for correlation functions      |
| `tests/unit/test_step_14_state.py`                     | CREATE | ST-6       | Tests for new DesignState fields     |
| `tests/unit/test_step_14_rules.py`                     | CREATE | ST-7       | Tests for validation rules           |
| `tests/unit/test_step_14_mechanical.py`                | CREATE | ST-8       | Tests for step executor              |
| `tests/unit/test_asme_external_pressure_validation.py` | CREATE | ST-11      | Benchmark validation tests           |
| `tests/integration/test_step_14_integration.py`        | CREATE | ST-10      | End-to-end integration tests         |
| `tests/integration/test_step_14_regression.py`         | CREATE | ST-12      | Regression / backward compat tests   |

**Total files:** 18 (8 source + 10 test)

---

## Build Sequence

```
ST-1  ──→  ST-2  ──→  (material_properties.py complete)
                          │
ST-3  ──────────────────→─┤  (data layer complete)
                          │
ST-4  ──────────────────→─┤
                          │
                          ▼
                       ST-5  (correlations — depends on ST-1,2,3)
                          │
                       ST-6  (DesignState fields — independent)
                          │
                          ▼
                    ┌── ST-7  (rules)
                    │
                    └── ST-8  (step executor — depends on ST-5,6,7)
                          │
                          ▼
                       ST-9  (pipeline wiring)
                          │
                          ▼
                    ┌── ST-10  (integration tests)
                    ├── ST-11  (benchmark validation)
                    └── ST-12  (regression tests)
```

**Recommended build order (sequential):**

1. ST-1 + ST-2 → run T1._ + T2._ → data layer for material properties done
2. ST-3 → run T3.\* → external pressure data encoded
3. ST-4 → run T4.\* → pipe schedules
4. ST-5 → run T5.\* → correlation functions
5. ST-6 → run T6.\* → DesignState fields
6. ST-7 → run T7.\* → validation rules
7. ST-8 → run T8.\* → step executor
8. ST-9 → run T9.\* → pipeline integration
9. ST-10 → integration tests
10. ST-11 → benchmark validation (GATE — must pass before proceeding to Step 15)
11. ST-12 → regression (confirm nothing broken)

---

## Edge Cases

| #   | Edge Case                                                           | Expected Behaviour                                                                                   |
| --- | ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| E1  | Pressures are None (user didn't specify)                            | Default to atmospheric (101325 Pa); design pressure ≈ 0.275 MPa                                      |
| E2  | Both sides at same pressure                                         | No external pressure differential; external checks still run with P_external ≈ 0                     |
| E3  | Very high pressure (>100 bar)                                       | UG-27 gives large t_min; AI triggered; may need heavier BWG or different tube OD                     |
| E4  | Vacuum on shell side (P_shell < 101325 Pa)                          | External pressure check on shell runs; UG-28 procedure                                               |
| E5  | Vacuum on tube side (P_tube < 101325 Pa)                            | Unusual but valid; external pressure on tubes = shell pressure                                       |
| E6  | Full vacuum both sides                                              | Both external pressure checks run with P_external = ~0.1 MPa                                         |
| E7  | Shell diameter doesn't match any standard NPS                       | `find_nps_for_shell()` returns nearest NPS; note mismatch                                            |
| E8  | Shell > NPS 24 (610mm) — rolled plate territory                     | Return t_min as recommendation; note "rolled plate recommended"                                      |
| E9  | Fixed tubesheet (BEM) + high expansion differential                 | ESCALATE to user: recommend BEM→AES change                                                           |
| E10 | U-tube (BEU) type → skip expansion check entirely                   | ΔL check returns "N/A — U-tube absorbs expansion"                                                    |
| E11 | Same material tube and shell → near-zero differential               | expansion_mm ≈ 0; always OK                                                                          |
| E12 | Exotic material + carbon steel shell → large expansion mismatch     | 304 SS vs CS → ~2-4 mm differential at moderate ΔT                                                   |
| E13 | tube_material not in material_properties → fallback to carbon_steel | Warning + use CS values                                                                              |
| E14 | Temperature above material table range → clamp to highest           | Conservative (stress doesn't increase with temp)                                                     |
| E15 | BWG gauge gives wall < UG-27 minimum                                | `tube_thickness_ok = False`; warning recommends heavier gauge                                        |
| E16 | Shell-side fluid allocation is None                                 | Default: hot fluid shell-side                                                                        |
| E17 | TEMA type is None (Step 4 didn't run properly)                      | Treat as BEM (most conservative for expansion check)                                                 |
| E18 | Convergence didn't converge (convergence_converged = False)         | Step 14 still runs (warning only; mechanical check is geometry-dependent, not convergence-dependent) |
| E19 | Negative design pressure from formula (impossible physically)       | Raise CalculationError                                                                               |
| E20 | Tube D_o/t ratio outside Table G range (< 4 or > 1000)              | Raise CalculationError with message about non-standard geometry                                      |

---

## Formula Cross-Reference

| Function                                | ASME Reference                | Formula                              |
| --------------------------------------- | ----------------------------- | ------------------------------------ |
| `design_pressure`                       | UG-21                         | P_d = max(1.1P, P + 175 kPa)         |
| `tube_internal_pressure_thickness`      | UG-27(c)(1)                   | t = P·d_o / (2·S·E + P)              |
| `shell_internal_pressure_thickness`     | UG-27(c)(1)                   | t = P·R / (S·E - 0.6·P) + CA         |
| `lookup_factor_A`                       | UG-28, Fig. G                 | Geometric chart interpolation        |
| `lookup_factor_B`                       | UG-28, CS/HA/NFC/NFN/NFT figs | Material chart interpolation         |
| `external_pressure_allowable` (plastic) | UG-28(c) Step 6               | P_a = 4B / [3·(D_o/t)]               |
| `external_pressure_allowable` (elastic) | UG-28(c) Step 5               | P_a = 2AE / [3·(D_o/t)]              |
| `thermal_expansion_differential`        | TEMA / Serth §7               | ΔL = α·L·(T - T_ref)                 |
| `get_corrosion_allowance`               | Industry practice             | CS: 3.175mm, alloy: 1.5mm, exotic: 0 |

---

## Test Count Summary

| Sub-Task                      | Unit Tests | Integration Tests | Total   |
| ----------------------------- | ---------- | ----------------- | ------- |
| ST-1 (Allowable stress)       | 7          | —                 | 7       |
| ST-2 (Thermal expansion)      | 7          | —                 | 7       |
| ST-3 (External pressure data) | 14         | —                 | 14      |
| ST-4 (Pipe schedules)         | 7          | —                 | 7       |
| ST-5 (Correlations)           | 15         | —                 | 15      |
| ST-6 (DesignState fields)     | 3          | —                 | 3       |
| ST-7 (Validation rules)       | 7          | —                 | 7       |
| ST-8 (Step executor)          | 20         | —                 | 20      |
| ST-9 (Pipeline wiring)        | 2          | —                 | 2       |
| ST-10 (Integration)           | —          | 8                 | 8       |
| ST-11 (Benchmark validation)  | 8          | —                 | 8       |
| ST-12 (Regression)            | —          | 7                 | 7       |
| **Total**                     | **90**     | **15**            | **105** |
