# Dev A — Step 4: Select TEMA Type + Initial Geometry — Implementation Plan

## Overview

Step 4 takes process conditions from Steps 1–3 (fluids, temperatures, pressures, fluid properties) and makes two critical engineering decisions:

1. **TEMA type selection** — Which shell-and-tube configuration (BEM, AES, AEP, etc.)?
2. **Initial geometry** — Tube OD, pitch, layout, passes, length, baffle cut, baffle spacing

This is the first "engineering judgment" step. It's **FULL AI** — AI always reviews the selection because TEMA type choice has cascading effects on every downstream calculation (Steps 5–16).

### Dependencies (must exist before Step 4)

- ✅ `DesignState` model — exists
- ✅ `StepResult` / `BaseStep` framework — exists
- ✅ `Step01Requirements` — exists (provides fluids, temps, flows)
- ✅ `Step02HeatDuty` — exists (provides Q_W)
- ✅ `Step03FluidProperties` — exists (provides fluid properties)
- ✅ `GeometrySpec` model — exists (with CG3A validators)
- ❌ `tema_type` field on DesignState — **needs to be added**
- ❌ `n_tubes`, `n_passes`, `pitch_layout` on GeometrySpec — **needs to be added**
- ❌ `hx_engine/app/data/` directory — **needs to be created**
- ❌ `tema_tables.py` — **needs to be created** (decision matrix + tube count tables)
- ❌ `fouling_factors.py` — **needs to be created** (R_f lookup by fluid pair)
- ❌ `bwg_gauge.py` — **needs to be created** (tube OD → ID by BWG gauge)

### What Step 4 Produces (outputs dict)

```
tema_type: str          # e.g., "BEM", "AES", "AEP"
geometry: GeometrySpec  # Fully populated initial geometry
```

### Decision Flow Summary

```
Process Conditions (Steps 1-3)
    ↓
┌─ Fluid Allocation ─┐    ┌─ TEMA Type Selection ─┐    ┌─ Geometry Sizing ─┐
│ Which fluid goes    │ →  │ Fixed (BEM)?           │ →  │ Tube OD/ID        │
│ tube-side vs        │    │ Floating (AES)?        │    │ Pitch & layout    │
│ shell-side?         │    │ U-tube (AEU)?          │    │ Passes, length    │
└─────────────────────┘    └────────────────────────┘    │ Baffle cut/spacing│
                                                          │ N_tubes estimate  │
                                                          │ Shell diameter    │
                                                          └───────────────────┘
```

---

## Pre-Piece 0: Model Updates (DesignState + GeometrySpec)

**What:** Add missing fields to `DesignState` and `GeometrySpec` that Step 4 needs to populate.

**Files to modify:**

- `hx_engine/app/models/design_state.py`

**Changes to `GeometrySpec`:**

| Field          | Type            | Default | Validator                  | Why                                       |
| -------------- | --------------- | ------- | -------------------------- | ----------------------------------------- |
| `n_tubes`      | `Optional[int]` | `None`  | `[1, 10000]`               | Tube count from TEMA tables               |
| `n_passes`     | `Optional[int]` | `None`  | `{1, 2, 4, 6, 8}`          | Tube passes (must be standard)            |
| `pitch_layout` | `Optional[str]` | `None`  | `{"triangular", "square"}` | Pitch pattern                             |
| `shell_passes` | `Optional[int]` | `None`  | `{1, 2}`                   | Shell passes (1 for TEMA E, 2 for TEMA F) |

**Changes to `DesignState`:**

| Field              | Type            | Default | Why                                            |
| ------------------ | --------------- | ------- | ---------------------------------------------- |
| `tema_type`        | `Optional[str]` | `None`  | 3-letter TEMA designation (e.g., "BEM", "AES") |
| `shell_side_fluid` | `Optional[str]` | `None`  | "hot" or "cold" — which fluid is on shell side |

**Testing Plan (8 tests):**

| #   | Test                                       | What it validates                                     | Physics check                  |
| --- | ------------------------------------------ | ----------------------------------------------------- | ------------------------------ |
| 1   | `test_geometry_spec_n_tubes_valid`         | n_tubes=324 accepted                                  | Standard tube count            |
| 2   | `test_geometry_spec_n_tubes_zero_rejected` | n_tubes=0 → ValueError                                | Must have at least 1 tube      |
| 3   | `test_geometry_spec_n_tubes_excessive`     | n_tubes=20000 → ValueError                            | Beyond fabrication limits      |
| 4   | `test_geometry_spec_n_passes_valid_values` | n_passes ∈ {1,2,4,6,8} accepted                       | TEMA standard pass counts      |
| 5   | `test_geometry_spec_n_passes_3_rejected`   | n_passes=3 → ValueError                               | Not a standard TEMA pass count |
| 6   | `test_geometry_spec_pitch_layout_valid`    | "triangular" and "square" accepted                    | Only two standard layouts      |
| 7   | `test_geometry_spec_pitch_layout_invalid`  | "hexagonal" → ValueError                              | Not a TEMA standard layout     |
| 8   | `test_design_state_tema_type_stored`       | DesignState(tema_type="BEM") round-trips through JSON | Persistence works              |

---

## Piece 1: Data Files — BWG Gauge Table (`bwg_gauge.py`)

**What:** Lookup table mapping (tube_OD, BWG_gauge_number) → tube_ID and wall_thickness. This is a reference data file — pure constants, no logic.

**File:** `hx_engine/app/data/__init__.py` — CREATE (empty)
**File:** `hx_engine/app/data/bwg_gauge.py` — CREATE

**Data source:** TEMA Standards / Perry's Chemical Engineers' Handbook Table 11-2

**Key data points (subset):**

| Tube OD (mm)  | BWG | Wall (mm) | ID (mm) |
| ------------- | --- | --------- | ------- |
| 19.05 (3/4")  | 14  | 2.108     | 14.834  |
| 19.05 (3/4")  | 16  | 1.651     | 15.748  |
| 25.40 (1")    | 14  | 2.108     | 21.184  |
| 25.40 (1")    | 16  | 1.651     | 22.098  |
| 31.75 (1.25") | 14  | 2.108     | 27.534  |
| 38.10 (1.5")  | 12  | 2.769     | 32.562  |

**Public interface:**

```python
def get_tube_id(tube_od_m: float, bwg: int = 14) -> float:
    """Returns tube ID in meters for given OD and BWG gauge."""

def get_wall_thickness(tube_od_m: float, bwg: int = 14) -> float:
    """Returns wall thickness in meters."""

def get_available_tube_ods() -> list[float]:
    """Returns list of standard tube ODs in meters."""
```

**Testing Plan (7 tests):**

| #   | Test                                 | What it validates                                | Physics check                |
| --- | ------------------------------------ | ------------------------------------------------ | ---------------------------- |
| 1   | `test_19mm_bwg14_id`                 | 19.05mm OD, BWG 14 → ID ≈ 14.83mm (within 0.1mm) | Perry's reference value      |
| 2   | `test_25mm_bwg14_id`                 | 25.40mm OD, BWG 14 → ID ≈ 21.18mm                | Perry's reference            |
| 3   | `test_wall_positive`                 | All (OD, BWG) combos → wall > 0                  | Wall thickness is physical   |
| 4   | `test_id_less_than_od`               | For all entries: ID < OD                         | Tube ID must be less than OD |
| 5   | `test_wall_equals_half_od_minus_id`  | wall = (OD - ID) / 2 for all entries             | Geometric consistency        |
| 6   | `test_unknown_od_raises`             | get_tube_id(0.123) → ValueError                  | Only standard ODs supported  |
| 7   | `test_available_ods_includes_common` | 0.01905 and 0.0254 in list                       | 3/4" and 1" are universal    |

---

## Piece 2: Data Files — TEMA Tube Count Tables (`tema_tables.py`)

**What:** Lookup table mapping (shell_diameter, tube_OD, pitch_ratio, pitch_layout, n_passes) → n_tubes. Also provides the reverse lookup: given a required tube count, find the smallest standard shell diameter.

**File:** `hx_engine/app/data/tema_tables.py` — CREATE

**Data source:** TEMA Standards Table D-7 / Sinnott Table 12.4 / Kern Table A-1

**Key data structure:**

```python
# TUBE_COUNT_TABLE[shell_id_inch][tube_od_inch][pitch_layout][n_passes]
# e.g., TUBE_COUNT_TABLE[23.25]["0.75"]["triangular"][2] = 324
```

**Standard shell IDs (inches, nominal):** 8, 10, 12, 13.25, 15.25, 17.25, 19.25, 21.25, 23.25, 25, 27, 29, 31, 33, 35, 37

**Public interface:**

```python
def get_tube_count(shell_diameter_m: float, tube_od_m: float,
                   pitch_layout: str, n_passes: int) -> int:
    """Look up number of tubes from TEMA table."""

def find_shell_diameter(n_tubes_required: int, tube_od_m: float,
                        pitch_layout: str, n_passes: int) -> tuple[float, int]:
    """Find smallest standard shell that fits n_tubes_required.
    Returns (shell_diameter_m, actual_n_tubes)."""

def get_standard_shell_diameters() -> list[float]:
    """Returns all standard shell diameters in meters."""
```

**Testing Plan (10 tests):**

| #   | Test                                   | What it validates                                         | Physics check                                         |
| --- | -------------------------------------- | --------------------------------------------------------- | ----------------------------------------------------- |
| 1   | `test_known_tube_count_23in_shell`     | 23.25" shell, 3/4" tubes, triangular, 2-pass → ~324 tubes | Published TEMA table value                            |
| 2   | `test_known_tube_count_12in_shell`     | 12" shell, 3/4" tubes, triangular, 2-pass → ~76 tubes     | Published TEMA table value                            |
| 3   | `test_square_fewer_than_triangular`    | Same shell, same tubes → square pitch gives fewer tubes   | Square has less packing density                       |
| 4   | `test_more_passes_fewer_tubes`         | Same shell, 4-pass < 2-pass tube count                    | More passes = more pass-partition lanes = fewer tubes |
| 5   | `test_find_shell_for_324_tubes`        | 324 tubes required → ≥ 23.25" shell                       | Reverse lookup works                                  |
| 6   | `test_find_shell_rounds_up`            | 100 tubes required → next shell size up (conservative)    | Never undersized                                      |
| 7   | `test_very_large_tube_count`           | 5000 tubes → returns largest shell or raises              | Graceful handling of extreme cases                    |
| 8   | `test_all_tube_counts_positive`        | Every entry in table > 0                                  | Can't have negative tubes                             |
| 9   | `test_tube_count_increases_with_shell` | For same config, bigger shell = more tubes                | Monotonic: larger shell fits more                     |
| 10  | `test_standard_shell_diameters_sorted` | Return value is ascending                                 | Convenience for users of the API                      |

---

## Piece 3: Data Files — Fouling Factors (`fouling_factors.py`)

**What:** Lookup table for fouling resistance (R_f in m²·K/W) by fluid type. Used by Step 4 to influence tube-side allocation (fouling fluid should go tube-side for easier cleaning) and by Steps 9–11 for U-calculation.

**File:** `hx_engine/app/data/fouling_factors.py` — CREATE

**Data source:** TEMA Standards Table RGP-T-2.4 / Perry's Table 11-10

**Key data points:**

| Fluid                        | R_f (m²·K/W) | Classification |
| ---------------------------- | ------------ | -------------- |
| Cooling tower water          | 0.000352     | Moderate       |
| River water                  | 0.000528     | Moderate-heavy |
| Boiler feedwater (treated)   | 0.000088     | Clean          |
| Seawater (< 50°C)            | 0.000088     | Clean          |
| Seawater (> 50°C)            | 0.000352     | Moderate       |
| Light hydrocarbons           | 0.000176     | Clean          |
| Heavy hydrocarbons (> 200°C) | 0.000528     | Moderate-heavy |
| Crude oil (< 120°C)          | 0.000352     | Moderate       |
| Crude oil (120–175°C)        | 0.000528     | Moderate-heavy |
| Crude oil (175–230°C)        | 0.000704     | Heavy          |
| Gasoline                     | 0.000176     | Clean          |
| Kerosene                     | 0.000176     | Clean          |
| Diesel                       | 0.000352     | Moderate       |
| Steam (clean condensate)     | 0.000088     | Clean          |
| Refrigerant (liquid)         | 0.000176     | Clean          |
| Organic solvents             | 0.000176     | Clean          |
| Vegetable oil                | 0.000528     | Moderate-heavy |

**Public interface:**

```python
def get_fouling_factor(fluid_name: str, temperature_C: float = None) -> float:
    """Return R_f in m²·K/W for a fluid. Temperature used for temp-dependent fluids (e.g. crude)."""

def classify_fouling(fluid_name: str, temperature_C: float = None) -> str:
    """Return 'clean', 'moderate', 'heavy', or 'severe'."""

def is_fouling_fluid(fluid_name: str, temperature_C: float = None) -> bool:
    """True if R_f > 0.000352 (moderate or worse)."""
```

**Testing Plan (8 tests):**

| #   | Test                                 | What it validates                                                      | Physics check                          |
| --- | ------------------------------------ | ---------------------------------------------------------------------- | -------------------------------------- |
| 1   | `test_water_fouling_factor`          | Cooling water → R_f ≈ 0.000352 m²·K/W                                  | TEMA published value                   |
| 2   | `test_crude_oil_120C`                | Crude at 100°C → R_f ≈ 0.000352                                        | Temperature-dependent lookup           |
| 3   | `test_crude_oil_200C`                | Crude at 200°C → R_f ≈ 0.000704                                        | Higher temp = higher fouling for crude |
| 4   | `test_clean_fluid_classification`    | Boiler feedwater → "clean"                                             | Classification matches TEMA            |
| 5   | `test_heavy_fluid_is_fouling`        | Crude at 200°C → `is_fouling_fluid()` returns True                     | Correctly identifies fouling fluids    |
| 6   | `test_light_hydrocarbon_not_fouling` | Gasoline → `is_fouling_fluid()` returns False                          | Clean fluids correctly classified      |
| 7   | `test_all_factors_positive`          | Every entry > 0                                                        | Fouling resistance is always positive  |
| 8   | `test_unknown_fluid_returns_default` | Unknown fluid → returns a conservative default (0.000352) with warning | Graceful fallback, not crash           |

---

## Piece 4: Fluid Allocation Logic (`_allocate_fluids()`)

**What:** Decide which fluid goes tube-side and which goes shell-side. This is a critical engineering decision that affects cleaning, pressure containment, and heat transfer.

**File:** `hx_engine/app/steps/step_04_tema_geometry.py` — CREATE (start with this function)

**Decision rules (priority order):**

1. **Corrosion/exotic material:** Corrosive or expensive-to-clad fluid → tube-side (only tubes need exotic material, not shell)
2. **High pressure:** Higher-pressure fluid → tube-side (tubes handles pressure more efficiently than shell)
3. **Fouling:** More-fouling fluid → tube-side (easier to clean straight tubes; enables square pitch if needed)
4. **Viscous fluid:** More-viscous fluid → shell-side (shell-side baffles induce turbulence, improving h for viscous fluids)
5. **Hotter fluid:** Hotter fluid → tube-side (reduces shell material cost; shell at lower temp)
6. **Default:** If no differentiating factor, hot fluid → tube-side (convention)

**Returns:** `"hot"` or `"cold"` indicating which fluid goes shell-side.

**Testing Plan (10 tests):**

| #   | Test                                    | What it validates                                              | Physics check                                                                         |
| --- | --------------------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| 1   | `test_high_pressure_to_tube`            | P_hot=50 bar, P_cold=2 bar → hot fluid tube-side               | Pressure containment: smaller diameter = thinner walls for same hoop stress           |
| 2   | `test_fouling_to_tube`                  | Hot=crude oil, Cold=water → crude tube-side                    | Straight tubes are mechanically cleanable                                             |
| 3   | `test_viscous_to_shell`                 | Hot μ=0.001, Cold μ=0.5 Pa·s → cold (viscous) shell-side       | Shell baffles create turbulence for viscous fluids, bypass rule #3 only if both clean |
| 4   | `test_fouling_overrides_viscosity`      | Hot=crude(fouling+viscous), Cold=water → crude tube-side       | Fouling (rule 3) beats viscosity (rule 4)                                             |
| 5   | `test_high_pressure_overrides_fouling`  | Hot: 100 bar+clean, Cold: 2 bar+fouling → hot tube-side        | Pressure (rule 2) beats fouling (rule 3)                                              |
| 6   | `test_both_clean_low_pressure_hot_tube` | Both clean, similar pressure → hot fluid tube-side             | Default convention (rule 6)                                                           |
| 7   | `test_symmetric_case`                   | Same fluid both sides, same conditions → default hot tube-side | Deterministic in tie-break                                                            |
| 8   | `test_user_preference_respected`        | User specified tema_preference with explicit allocation        | User override takes precedence over heuristics                                        |
| 9   | `test_returns_warnings_for_conflicts`   | Fouling says tube-side, viscosity says shell-side → warning    | Conflicting rules documented                                                          |
| 10  | `test_extreme_pressure_difference`      | P_hot=200 bar, P_cold=1 bar → hot tube-side, no ambiguity      | Clear-cut high pressure case                                                          |

---

## Piece 5: TEMA Type Selection Logic (`_select_tema_type()`)

**What:** Decision tree to select the 3-letter TEMA designation based on process conditions. This is the core engineering judgment of Step 4.

**File:** `hx_engine/app/steps/step_04_tema_geometry.py`

**TEMA Type Coverage (Phase 1 — Shell-and-Tube only):**

| TEMA | Front Head | Shell  | Rear Head                  | When to Use                                                        |
| ---- | ---------- | ------ | -------------------------- | ------------------------------------------------------------------ |
| BEM  | Bonnet     | 1-pass | Fixed tubesheet            | Both fluids clean, ΔT < 50°C, cheapest                             |
| AES  | Channel    | 1-pass | Floating head (split ring) | ΔT > 50°C OR one fluid fouls, most common industrial               |
| AEP  | Channel    | 1-pass | Outside packed floating    | ΔT > 50°C, moderate pressure, easier maintenance than AES          |
| AEU  | Channel    | 1-pass | U-tube                     | ΔT > 50°C, clean tube-side only (can't mechanically clean U-bends) |
| BEM  | Bonnet     | 1-pass | Fixed                      | Default for clean-clean service                                    |
| AEL  | Channel    | 1-pass | Fixed (lantern ring)       | Low pressure, moderate ΔT                                          |
| AEW  | Channel    | 1-pass | Externally sealed floating | High-pressure, large ΔT                                            |

**Decision tree:**

```
1. Is ΔT between streams > 50°C?
   ├── YES → Need thermal expansion compensation
   │   ├── Is tube-side fluid clean (can skip mechanical cleaning)?
   │   │   ├── YES → AEU (U-tube, cheapest floating option)
   │   │   └── NO → AES (floating head, full tube access)
   │   └── Is pressure > 70 bar on either side?
   │       └── YES → AEW (externally sealed, handles high pressure)
   └── NO → Fixed tubesheet is viable
       ├── Both fluids clean?
       │   └── YES → BEM (cheapest possible)
       └── One or both fouling?
           └── YES → Can we clean from one end (straight pull-through)?
               ├── YES → AEL or AEP (easier maintenance)
               └── NO → AES (requires full floating head for access)

2. User preference override?
   └── If user specified tema_class/tema_preference, use it
       (but warn if it conflicts with conditions, e.g. BEM with 80°C ΔT)

3. Edge cases:
   - Very small duty (Q < 50 kW) → Note: "Consider double-pipe instead" (warning only)
   - Very large duty (Q > 50 MW) → Note: "May need multiple shells" (warning only)
   - Both fluids foul heavily → AES with square pitch (hard to clean both sides otherwise)
```

**Returns:** `(tema_type: str, reasoning: str, warnings: list[str])`

**Testing Plan (14 tests):**

| #   | Test                                  | What it validates                                   | Physics check                                   |
| --- | ------------------------------------- | --------------------------------------------------- | ----------------------------------------------- |
| 1   | `test_clean_clean_low_dt_BEM`         | Water(30→60) + water(90→70), ΔT=30°C → BEM          | No expansion concern, cheapest option           |
| 2   | `test_high_dt_clean_tube_AEU`         | ΔT=80°C, tube-side fluid clean → AEU                | Thermal expansion needs floating/U-tube         |
| 3   | `test_high_dt_fouling_tube_AES`       | ΔT=80°C, tube-side fluid fouls → AES                | Can't mechanically clean U-tube bends           |
| 4   | `test_low_dt_one_fouling_AES`         | ΔT=30°C, one fluid fouls → AES or AEP               | Fouling needs removal access                    |
| 5   | `test_very_high_pressure_AEW`         | P=150 bar, ΔT=80°C → AEW                            | High pressure + expansion needs sealed floating |
| 6   | `test_user_preference_respected`      | User says "BEM" → BEM selected                      | Override heuristics                             |
| 7   | `test_user_preference_conflict_warns` | User says "BEM" but ΔT=80°C → BEM + warning         | Respect user but flag risk                      |
| 8   | `test_small_duty_warns`               | Q=20 kW → any TEMA + "consider double-pipe" warning | Not a blocking error                            |
| 9   | `test_large_duty_warns`               | Q=100 MW → TEMA + "multi-shell" warning             | Not blocking, but important                     |
| 10  | `test_both_fouling_heavy_AES_square`  | Both fluids foul heavily → AES + square pitch note  | Only option for bilateral fouling               |
| 11  | `test_delta_T_exactly_50_boundary`    | ΔT=50°C → BEM (boundary is exclusive)               | Boundary condition                              |
| 12  | `test_delta_T_51_requires_floating`   | ΔT=51°C → AEU or AES (not BEM)                      | Just above threshold                            |
| 13  | `test_reasoning_is_populated`         | Any valid case → reasoning string non-empty         | Audit trail for AI review                       |
| 14  | `test_corrosive_fluid_notes_material` | Corrosive fluid → warning about material selection  | Material impacts are flagged early              |

---

## Piece 6: Initial Geometry Heuristics (`_select_initial_geometry()`)

**What:** Select starting geometry parameters using standard engineering heuristics. These are initial estimates that will be refined by the convergence loop (Step 12).

**File:** `hx_engine/app/steps/step_04_tema_geometry.py`

**Heuristic rules:**

| Parameter      | Default                     | Logic                                                                        |
| -------------- | --------------------------- | ---------------------------------------------------------------------------- |
| Tube OD        | 19.05mm (3/4")              | Industry standard; use 25.4mm (1") for very viscous fluids                   |
| Tube ID        | From BWG 14 gauge           | Via `bwg_gauge.py` lookup                                                    |
| Pitch ratio    | 1.25 triangular             | Use 1.25 square if shell-side fouls (cleaning lanes needed)                  |
| Pitch layout   | triangular                  | Use square if either fluid fouls heavily                                     |
| Tube length    | 4.877m (16 ft)              | Standard; use 3.66m (12 ft) if duty < 500 kW; 6.096m (20 ft) if duty > 10 MW |
| Tube passes    | 2                           | Default; 1 if counter-current needed (F-factor issue); 4 if velocity too low |
| Shell passes   | 1                           | TEMA E shell; 2 if Step 5 determines F < 0.8 (handled later)                 |
| Baffle cut     | 25% (0.25)                  | Standard starting point                                                      |
| Baffle spacing | shell_diameter × 0.3 to 0.5 | Initial estimate; refined in convergence                                     |
| N_tubes        | From TEMA table             | Via `tema_tables.py` lookup based on estimated area                          |
| Shell diameter | From TEMA table             | Smallest standard shell that fits N_tubes                                    |

**Rough area estimation (for N_tubes starting point):**

```
U_assumed = get from u_assumptions.py by fluid pair
A_estimated = Q / (U_assumed × LMTD_estimated)
  where LMTD_estimated = (ΔT_max - ΔT_min) / ln(ΔT_max / ΔT_min)   # rough, Step 5 will be exact
N_tubes_estimated = A_estimated / (π × tube_OD × tube_length)
```

**Note:** U_assumptions are needed for this rough estimate. However, Step 4 doesn't need highly accurate U — a ±50% estimate is fine since the convergence loop (Step 12) will correct it. If `u_assumptions.py` isn't built yet, we can use a hardcoded conservative U (300 W/m²·K for liquid-liquid, 50 W/m²·K for gas-liquid).

**Returns:** `GeometrySpec` with all fields populated

**Testing Plan (12 tests):**

| #   | Test                                       | What it validates                               | Physics check                                |
| --- | ------------------------------------------ | ----------------------------------------------- | -------------------------------------------- |
| 1   | `test_default_tube_od_19mm`                | Standard case → tube_od=0.01905                 | 3/4" is industry standard                    |
| 2   | `test_viscous_fluid_25mm_tube`             | Very viscous fluid (μ>0.05) → tube_od=0.0254    | Wider tubes reduce viscous pressure drop     |
| 3   | `test_tube_id_from_bwg`                    | OD=0.01905 → ID matches BWG 14 (≈0.01483)       | ID must come from gauge table, not arbitrary |
| 4   | `test_fouling_square_pitch`                | Fouling service → pitch_layout="square"         | Square pitch allows cleaning lanes           |
| 5   | `test_clean_triangular_pitch`              | Clean-clean service → pitch_layout="triangular" | Triangular maximizes tube count (lower cost) |
| 6   | `test_default_tube_length_4877`            | Medium duty → tube_length=4.877m                | 16 ft standard                               |
| 7   | `test_small_duty_shorter_tubes`            | Q < 500 kW → tube_length=3.66m                  | Avoid very long exchangers for small duties  |
| 8   | `test_large_duty_longer_tubes`             | Q > 10 MW → tube_length=6.096m                  | Standard 20 ft for large duties              |
| 9   | `test_default_2_passes`                    | Standard case → n_passes=2                      | 2-pass is most common starting point         |
| 10  | `test_baffle_cut_025`                      | Any case → baffle_cut=0.25                      | 25% is universal starting point              |
| 11  | `test_all_geometry_fields_populated`       | Full run → every GeometrySpec field is not None | Downstream steps require complete geometry   |
| 12  | `test_geometry_passes_pydantic_validators` | Output GeometrySpec passes all CG3A validators  | No out-of-range values                       |

---

## Piece 7: Core `execute()` Logic — Wire Everything Together

**What:** The `execute(self, state: DesignState) -> StepResult` method that orchestrates Pieces 4, 5, and 6.

**File:** `hx_engine/app/steps/step_04_tema_geometry.py`

**Logic:**

1. **Pre-condition check:** Verify required state fields exist:
   - `state.hot_fluid_name`, `state.cold_fluid_name` — must not be None
   - `state.T_hot_in_C`, `state.T_hot_out_C`, `state.T_cold_in_C`, `state.T_cold_out_C` — must not be None
   - `state.hot_fluid_props`, `state.cold_fluid_props` — must not be None (from Step 3)
   - `state.Q_W` — must not be None (from Step 2)
   - If any missing → `CalculationError(4, "Step 4 requires ... from Steps 1-3")`

2. **Fluid allocation:**
   - `shell_side = _allocate_fluids(state)` → `"hot"` or `"cold"`

3. **TEMA type selection:**
   - `tema_type, reasoning, type_warnings = _select_tema_type(state, shell_side)`

4. **Initial geometry:**
   - `geometry = _select_initial_geometry(state, tema_type, shell_side)`

5. **Collect warnings** from allocation + TEMA selection + geometry

6. **Return StepResult:**
   - `outputs = {"tema_type": tema_type, "geometry": geometry, "shell_side_fluid": shell_side}`

**Class attributes:**

```python
step_id = 4
step_name = "TEMA Geometry Selection"
ai_mode = AIModeEnum.FULL
```

**Testing Plan (10 tests):**

| #   | Test                              | What it validates                                                    | Physics check                                    |
| --- | --------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------ |
| 1   | `test_benchmark_crude_water`      | Crude oil 150→90°C + water 30→60°C → complete result                 | Standard industry benchmark                      |
| 2   | `test_missing_fluid_props_error`  | `state.hot_fluid_props = None` → CalculationError                    | Pre-condition enforcement                        |
| 3   | `test_missing_Q_error`            | `state.Q_W = None` → CalculationError                                | Heat duty is required                            |
| 4   | `test_missing_temperatures_error` | Any temp is None → CalculationError                                  | All 4 temps needed for ΔT calculation            |
| 5   | `test_outputs_dict_keys`          | Normal run → outputs has "tema_type", "geometry", "shell_side_fluid" | Contract with pipeline runner                    |
| 6   | `test_step_result_metadata`       | Normal run → step_id=4, step_name="TEMA Geometry Selection"          | Audit trail                                      |
| 7   | `test_state_not_mutated`          | Compare state before/after execute()                                 | Layer 1 purity — execute() must not modify state |
| 8   | `test_geometry_is_valid_spec`     | Output geometry passes GeometrySpec validators                       | No out-of-range values                           |
| 9   | `test_water_water_clean_service`  | Water both sides → BEM + triangular pitch                            | Both clean → cheapest configuration              |
| 10  | `test_step_protocol_compliance`   | `isinstance(Step04TEMAGeometry(), StepProtocol)` → True              | Structural typing contract                       |

---

## Piece 8: Layer 2 Validation Rules (`step_04_rules.py`)

**What:** Hard engineering rules that AI **cannot** override. These catch geometry that is physically impossible or outside TEMA standards.

**File:** `hx_engine/app/steps/step_04_rules.py` — CREATE

**Rules:**

| Rule                             | Condition                                                      | Failure Mode                                  |
| -------------------------------- | -------------------------------------------------------------- | --------------------------------------------- |
| R1: Valid TEMA type              | `tema_type` in known set {"BEM","AES","AEP","AEU","AEL","AEW"} | Hard fail — invalid designation               |
| R2: Tube ID < Tube OD            | `tube_id_m < tube_od_m`                                        | Hard fail — physically impossible             |
| R3: All geometry positive        | Every numeric field > 0                                        | Hard fail — non-physical                      |
| R4: Shell diameter > tube OD     | `shell_diameter_m > tube_od_m`                                 | Hard fail — tubes don't fit                   |
| R5: Baffle spacing ≥ 0.2 × shell | `baffle_spacing_m >= 0.2 * shell_diameter_m`                   | Hard fail — too close, fabrication impossible |
| R6: Baffle spacing ≤ 1.0 × shell | `baffle_spacing_m <= 1.0 * shell_diameter_m`                   | Hard fail — too wide, poor distribution       |
| R7: Pitch ratio in range         | `1.2 ≤ pitch_ratio ≤ 1.5`                                      | Hard fail — TEMA limits                       |
| R8: N_tubes > 0                  | `n_tubes >= 1`                                                 | Hard fail                                     |
| R9: Fixed tubesheet ΔT check     | If BEM and max ΔT > 50°C → fails                               | Hard fail — thermal expansion risk            |

**Testing Plan (14 tests):**

| #   | Test                               | What it validates                                            | Physics check                                 |
| --- | ---------------------------------- | ------------------------------------------------------------ | --------------------------------------------- |
| 1   | `test_valid_tema_passes`           | tema_type="BEM" → passes R1                                  | Known TEMA type                               |
| 2   | `test_invalid_tema_fails`          | tema_type="XYZ" → fails R1                                   | Must be in TEMA standard set                  |
| 3   | `test_tube_id_lt_od_passes`        | ID=0.015, OD=0.019 → passes R2                               | Physically correct                            |
| 4   | `test_tube_id_gt_od_fails`         | ID=0.02, OD=0.019 → fails R2                                 | Impossible geometry                           |
| 5   | `test_all_positive_passes`         | All fields > 0 → passes R3                                   | Physical dimension                            |
| 6   | `test_negative_length_fails`       | tube_length=-1 → fails R3                                    | Can't have negative length                    |
| 7   | `test_shell_gt_tube_passes`        | shell=0.5, tube_od=0.019 → passes R4                         | Tubes fit in shell                            |
| 8   | `test_shell_lt_tube_fails`         | shell=0.01, tube_od=0.019 → fails R4                         | Tubes can't fit                               |
| 9   | `test_baffle_spacing_within_range` | spacing=0.15, shell=0.5 (ratio=0.3) → passes R5, R6          | Engineering practice                          |
| 10  | `test_baffle_too_close_fails`      | spacing=0.05, shell=0.5 (ratio=0.1) → fails R5               | Can't fabricate                               |
| 11  | `test_baffle_too_wide_fails`       | spacing=0.6, shell=0.5 (ratio=1.2) → fails R6                | Poor flow distribution                        |
| 12  | `test_pitch_ratio_in_range`        | pitch=1.25 → passes R7                                       | TEMA standard                                 |
| 13  | `test_BEM_with_high_dt_fails`      | BEM + T_hot_in=150, T_cold_in=30 (ΔT=120°C) → fails R9       | Thermal expansion will damage fixed tubesheet |
| 14  | `test_AES_with_high_dt_passes`     | AES + ΔT=120°C → passes R9 (floating head handles expansion) | Floating head accommodates expansion          |

---

## Piece 9: AI Escalation Logic

**What:** Since Step 4 is `ai_mode = FULL`, AI always reviews. But there are specific cases where the step itself knows escalation is likely needed — e.g., two TEMA types are equally valid. This piece doesn't override `_conditional_ai_trigger` (because mode is FULL), but instead sets flags/metadata in the StepResult that the AI can act on.

**File:** `hx_engine/app/steps/step_04_tema_geometry.py` (add to execute logic)

**Escalation triggers (added as `result.outputs["escalation_hints"]`):**

| Trigger                             | Condition                              | What AI should do                    |
| ----------------------------------- | -------------------------------------- | ------------------------------------ |
| Two types equally valid             | Score difference < 10% between top 2   | Present both options with trade-offs |
| User preference contradicts physics | BEM specified but ΔT > 50°C            | Warn user, recommend override        |
| Both fluids foul                    | Both classified as "moderate" or worse | Note cleaning difficulty both sides  |
| Extreme pressure                    | P > 100 bar either side                | Note material/head type impact       |
| Very small duty                     | Q < 50 kW                              | Suggest double-pipe alternative      |
| Very large duty                     | Q > 50 MW                              | Suggest multi-shell configuration    |

**Testing Plan (8 tests):**

| #   | Test                               | What it validates                                       | Physics check                     |
| --- | ---------------------------------- | ------------------------------------------------------- | --------------------------------- |
| 1   | `test_no_escalation_clear_choice`  | Clear-cut BEM case → no escalation hints                | Clean cases don't over-complicate |
| 2   | `test_escalation_two_types_close`  | AEU and AES both valid (clean tube, high ΔT) → hint set | Ambiguity is flagged              |
| 3   | `test_escalation_user_conflict`    | User wants BEM but ΔT=80°C → hint set                   | Safety concern flagged            |
| 4   | `test_escalation_both_fouling`     | Both fluids foul → hint set                             | Unusual and difficult case        |
| 5   | `test_escalation_extreme_pressure` | P_hot=150 bar → hint set                                | Material/cost implications        |
| 6   | `test_escalation_small_duty`       | Q=20 kW → hint about double-pipe                        | Right-sizing the equipment        |
| 7   | `test_escalation_large_duty`       | Q=100 MW → hint about multi-shell                       | Single shell can't handle this    |
| 8   | `test_hints_are_list_of_strings`   | Any escalation → hints is a list of dicts               | Structured data for AI to parse   |

---

## Piece 10: Data Files — U Assumptions (`u_assumptions.py`)

**What:** Starting-guess U values for fluid pair combinations. Used by Piece 6 to estimate area for initial tube count, and later by Step 6 for formal U estimation.

**File:** `hx_engine/app/data/u_assumptions.py` — CREATE

**Data source:** Coulson & Richardson Table 12.1 / Perry's Table 11-4

**Key data points:**

| Hot Fluid        | Cold Fluid    | U_low (W/m²·K) | U_mid (W/m²·K) | U_high (W/m²·K) |
| ---------------- | ------------- | -------------- | -------------- | --------------- |
| Light organic    | Light organic | 100            | 300            | 500             |
| Heavy organic    | Heavy organic | 50             | 150            | 300             |
| Light organic    | Water         | 200            | 500            | 800             |
| Heavy organic    | Water         | 100            | 300            | 500             |
| Gas              | Gas           | 5              | 25             | 50              |
| Gas              | Liquid        | 15             | 50             | 150             |
| Water            | Water         | 800            | 1200           | 1800            |
| Crude oil        | Water         | 100            | 300            | 500             |
| Steam condensing | Water         | 1000           | 2500           | 4000            |
| Steam condensing | Light organic | 250            | 750            | 1200            |

**Public interface:**

```python
def get_U_assumption(hot_fluid: str, cold_fluid: str) -> dict:
    """Returns {"U_low": float, "U_mid": float, "U_high": float} in W/m²·K."""

def classify_fluid_type(fluid_name: str, properties: FluidProperties = None) -> str:
    """Classify as 'water', 'light_organic', 'heavy_organic', 'gas', 'steam', 'crude'."""
```

**Testing Plan (8 tests):**

| #   | Test                                     | What it validates                              | Physics check                              |
| --- | ---------------------------------------- | ---------------------------------------------- | ------------------------------------------ |
| 1   | `test_water_water_U_high`                | Water-water → U_mid ≈ 1200                     | High h on both sides                       |
| 2   | `test_crude_water_U_moderate`            | Crude-water → U_mid ≈ 300                      | Crude viscosity limits U                   |
| 3   | `test_gas_gas_U_very_low`                | Gas-gas → U_mid ≈ 25                           | Low h for gases                            |
| 4   | `test_U_low_lt_mid_lt_high`              | All entries: U_low < U_mid < U_high            | Range is ordered                           |
| 5   | `test_all_U_positive`                    | Every U value > 0                              | Heat transfer coefficient must be positive |
| 6   | `test_classify_water`                    | "water", "cooling water" → "water"             | Name matching works                        |
| 7   | `test_classify_crude`                    | "crude oil" → "crude"                          | Crude classification                       |
| 8   | `test_unknown_pair_returns_conservative` | Unknown pair → returns liquid-liquid mid range | Graceful fallback                          |

---

## Implementation Order & Dependencies

```
Pre-Piece 0 (Model Updates)  ← First — adds tema_type to DesignState, n_tubes/n_passes/pitch_layout to GeometrySpec
    ↓
Piece 1 (BWG Gauge)          ← No dependencies, pure data
Piece 2 (TEMA Tables)        ← No dependencies, pure data
Piece 3 (Fouling Factors)    ← No dependencies, pure data
Piece 10 (U Assumptions)     ← No dependencies, pure data
    ↓                            (All 4 data files can be done in parallel)
Piece 4 (Fluid Allocation)   ← Depends on Piece 3 (needs fouling classification)
    ↓
Piece 5 (TEMA Selection)     ← Depends on Piece 4 (needs allocation result)
    ↓
Piece 6 (Geometry Heuristics) ← Depends on Pieces 1, 2, 5, 10 (needs tables + TEMA type)
    ↓
Piece 7 (execute() Core)     ← Wires Pieces 4 + 5 + 6 together
    ↓
Piece 8 (Validation Rules)   ← Independent — can parallel with 7
    ↓
Piece 9 (Escalation Logic)   ← Depends on Piece 7 (adds hints to execute outputs)
```

**Recommended build order:**

```
Phase A (Parallel — Pure Data):
  0 → 1, 2, 3, 10    (model updates, then all data files)

Phase B (Sequential — Core Logic):
  4 → 5 → 6

Phase C (Assembly):
  7 → 8, 9  (wire together, then rules + escalation)
```

---

## Total Test Count: 101 tests

| Piece | Description                 | Tests | Cumulative |
| ----- | --------------------------- | ----- | ---------- |
| 0     | Model Updates               | 8     | 8          |
| 1     | BWG Gauge Table             | 7     | 15         |
| 2     | TEMA Tube Count Tables      | 10    | 25         |
| 3     | Fouling Factors             | 8     | 33         |
| 4     | Fluid Allocation            | 10    | 43         |
| 5     | TEMA Type Selection         | 14    | 57         |
| 6     | Initial Geometry Heuristics | 12    | 69         |
| 7     | Core execute() Logic        | 10    | 79         |
| 8     | Layer 2 Validation Rules    | 14    | 93         |
| 9     | AI Escalation Logic         | 8     | 101        |
| 10    | U Assumptions               | 8     | 109        |

**(109 total including Piece 10)**

---

## Physics Guard Rails (Cross-Cutting Invariants)

These invariants must hold across **ALL** tests:

1. **Thermal expansion safety:** BEM is NEVER selected when max ΔT between streams > 50°C
2. **Fouling allocation:** Fouling fluid is ALWAYS tube-side (unless higher priority rule overrides)
3. **Pressure containment:** Higher-pressure fluid ALWAYS goes tube-side when ΔP > 30 bar
4. **Geometry bounds:** Every GeometrySpec field is within Pydantic CG3A validator ranges
5. **Tube ID < Tube OD:** Invariant in every test that produces geometry
6. **Monotonicity:** Larger shell diameter → more tubes (for same tube OD and pitch)
7. **No mutation:** `execute()` never modifies the input `DesignState`
8. **Standard values only:** Tube OD matches a BWG standard; shell diameter matches a TEMA standard
9. **Positive heat duty:** Q_W > 0 is a pre-condition (Step 2 guarantees this)
10. **TEMA compliance:** pitch_ratio, baffle_cut, baffle_spacing all within TEMA specified ranges

---

## Files Created/Modified Summary

| File                                           | Action                                | Piece         |
| ---------------------------------------------- | ------------------------------------- | ------------- |
| `hx_engine/app/models/design_state.py`         | MODIFY (add tema_type, n_tubes, etc.) | 0             |
| `hx_engine/app/data/__init__.py`               | CREATE                                | 1             |
| `hx_engine/app/data/bwg_gauge.py`              | CREATE                                | 1             |
| `hx_engine/app/data/tema_tables.py`            | CREATE                                | 2             |
| `hx_engine/app/data/fouling_factors.py`        | CREATE                                | 3             |
| `hx_engine/app/data/u_assumptions.py`          | CREATE                                | 10            |
| `hx_engine/app/steps/step_04_tema_geometry.py` | CREATE                                | 4, 5, 6, 7, 9 |
| `hx_engine/app/steps/step_04_rules.py`         | CREATE                                | 8             |
| `tests/unit/test_step_04_model_updates.py`     | CREATE                                | 0             |
| `tests/unit/test_bwg_gauge.py`                 | CREATE                                | 1             |
| `tests/unit/test_tema_tables.py`               | CREATE                                | 2             |
| `tests/unit/test_fouling_factors.py`           | CREATE                                | 3             |
| `tests/unit/test_u_assumptions.py`             | CREATE                                | 10            |
| `tests/unit/test_step_04_allocation.py`        | CREATE                                | 4             |
| `tests/unit/test_step_04_tema_selection.py`    | CREATE                                | 5             |
| `tests/unit/test_step_04_geometry.py`          | CREATE                                | 6             |
| `tests/unit/test_step_04_execute.py`           | CREATE                                | 7             |
| `tests/unit/test_step_04_rules.py`             | CREATE                                | 8             |
| `tests/unit/test_step_04_escalation.py`        | CREATE                                | 9             |

---

## Risk Notes

1. **TEMA table data accuracy:** The tube count tables must match published TEMA values. Incorrect table data cascades into wrong shell sizing. **Mitigation:** Cross-validate against at least 2 independent sources (Perry's + Kern + Coulson).

2. **Fouling factor coverage:** The fouling factor table may not cover every fluid in the thermo_adapter. **Mitigation:** Conservative default (0.000352) for unknown fluids + warning.

3. **Decision tree edge cases:** The TEMA selection tree has many branches. Some combinations (e.g., high pressure + high fouling + high ΔT) require careful priority ordering. **Mitigation:** 14 tests cover all branches; integration tests exercise the full pipeline.

4. **GeometrySpec model changes:** Adding `n_tubes`, `n_passes`, `pitch_layout` requires checking that existing tests (Steps 1–3) still pass since they create `GeometrySpec` objects. **Mitigation:** Run all existing tests after model changes (Pre-Piece 0).

5. **Shell diameter estimation accuracy:** The rough area estimate in Piece 6 uses estimated LMTD (not the exact value from Step 5). This is intentional — Step 4 runs before Step 5. The convergence loop (Step 12) corrects any sizing error. **Mitigation:** Test that estimate is within ±100% of eventual converged value for benchmark case.
