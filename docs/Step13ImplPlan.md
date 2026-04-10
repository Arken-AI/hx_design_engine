# Step 13 Implementation Plan — Flow-Induced Vibration Check

**Status:** Planning  
**Depends on:** Steps 1–12 (complete), BaseStep infrastructure (complete)  
**Reference:** STEPS_6_16_PLAN.md §Phase C, ARKEN_MASTER_PLAN.md §6.3, TEMA Standards 9th Ed. Section 6 (V-1 through V-14)  
**Date:** 2026-04-09

---

## Overview

Step 13 is a **safety-critical post-convergence check** that evaluates flow-induced tube vibration risk using the TEMA Section 6 methodology. It runs once on the final converged geometry from Step 12 and checks **four independent failure mechanisms** at each unsupported tube span.

Unlike Steps 7–11 (which iterate inside the convergence loop), Step 13 runs outside the loop as a one-shot analysis. It is **FULL AI mode** — every run gets AI engineering review because vibration failure can destroy a heat exchanger within hours of operation.

**Scope:** Single-phase shell-side liquids (Phase 1). Acoustic resonance (gas service) and two-phase damping formulas are implemented but gated on fluid phase. U-bend vibration is deferred.

---

## Primary Reference

All formulas, tables, coefficients, and empirical data are from **TEMA Standards, 9th Edition, Section 6 (V-1 through V-14)**. Unit system is English (inches, lb, ft/sec, psi, lb/ft³) — our implementation accepts SI inputs, converts internally to English for the TEMA formulas, and converts results back to SI.

> **Design note from TEMA:** "Due to the complexity of the problem, the TEMA guarantee does not cover vibration damage."

---

## Agreed Design Decisions

| #   | Decision                                                                           | Rationale                                                                                                     |
| --- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| D1  | Implement TEMA Section 6 directly, not a Connors/Blevins hybrid                    | TEMA is authoritative, self-contained, and what process engineers audit against                               |
| D2  | 4 mechanisms (not 5): fluidelastic, vortex shedding, turbulent buffeting, acoustic | TEMA treats "fluid-elastic whirling" as part of fluidelastic instability (V-10). Same criterion.              |
| D3  | Accept SI inputs, convert to English internally, convert results back to SI        | TEMA constants (10.838, 0.00545, etc.) stay untouched for easy audit against the book                         |
| D4  | Use TEMA V-9 crossflow velocity, not Bell-Delaware S_m/G_s                         | V-9 accounts for bypass redistribution and window effects; TEMA vibration criteria are calibrated to V-9      |
| D5  | Check 3 span types: inlet, central, outlet                                         | Per TEMA V-5.1 and V-3.3. Inlet/outlet are 1.5× central if not set on GeometrySpec                            |
| D6  | Default axial stress multiplier A = 1.0 for Phase 1                                | Avoids tubesheet stress calculations; conservative for tension, slightly non-conservative for compression     |
| D7  | Implement acoustic resonance fully (not stub) but gate on fluid phase              | Formulas are straightforward; avoids future rework. Returns "N/A — liquid service" for Phase 1                |
| D8  | Default pitch angle: `"triangular"` → 30°, `"square"` → 90°                        | Industry standard defaults. Add `pitch_angle_deg` to GeometrySpec as optional override for 45°/60°            |
| D9  | Hard rule: V/V_c < 0.5 (safety factor of 2 on critical velocity)                   | Per STEPS_6_16_PLAN.md and standard industry practice; TEMA says V < V_c; we use 0.5× for margin              |
| D10 | Hard rule: y_vs ≤ 0.02 × d_o AND y_tb ≤ 0.02 × d_o                                 | TEMA V-11.2 and V-11.3 recommended maximum                                                                    |
| D11 | Output format matches HTRI per-span tabular structure                              | Engineers compare directly to HTRI; eases validation and trust-building                                       |
| D12 | Vibration failure → AI recommends remedies + ESCALATE to user                      | Step 13 cannot re-converge; geometry changes require re-running Step 12                                       |
| D13 | Default baffle thickness: 6.35 mm (1/4") for all shell sizes in Phase 1            | Used only for vapor damping δ_v (V-8); minimal impact on liquid service; baffle_thickness_m added to Geometry |
| D14 | `data/material_properties.py` shared with Step 14                                  | Both steps need Young's modulus E and density ρ by tube material                                              |

---

## Computation Flow (Dependency Chain)

Every span follows this chain — each step depends on the previous:

```
1. INPUTS
   ├── Geometry: d_o, d_i, L_span, P_t, pitch_layout, D_s, B, h (baffle cut), n_baffles
   ├── Fluid: ρ_shell, μ_shell, ρ_tube (inside fluid)
   ├── Material: E, ρ_metal (from material_properties.py)
   └── Flow: W (shell-side mass flow rate, kg/s → lb/hr)

2. TUBE PROPERTIES (V-5.3, V-7)
   ├── I = π/64 × (d_o⁴ − d_i⁴)                    moment of inertia
   ├── w_t = tube metal weight per foot               from ρ_metal × cross-section area
   ├── w_fi = 0.00545 × ρ_i × d_i²                   tube-side fluid weight
   ├── C_m = f(p_t/d_o, layout)                       added mass coefficient (Table V-7.11)
   ├── H_m = C_m × 0.00545 × ρ_o × d_o²             hydrodynamic mass
   └── w_0 = w_t + w_fi + H_m                         effective tube weight

3. NATURAL FREQUENCY (V-5.3)
   ├── C = edge condition constant (9.87, 15.42, or 22.37)
   ├── A = 1.0 (axial stress multiplier, default)
   └── f_n = 10.838 × A × C / l² × √(EI/w_0)        in cycles/sec

4. DAMPING (V-8)
   ├── δ_1 = 3.41 × d_o / (w_0 × f_n)               viscous damping
   ├── δ_2 = 0.012 × d_o/w_0 × √(ρ_0 × μ / f_n)    squeeze-film damping
   └── δ_T = max(δ_1, δ_2)                            total (liquid service)

5. FLUID ELASTIC PARAMETER (V-4.2)
   └── X = 144 × w_0 × δ_T / (ρ_0 × d_o²)

6. CROSSFLOW VELOCITY (V-9.2)
   ├── Pattern constants C_4–C_8, m from Table V-9.211A/B
   ├── F_h, M, α_x correction factors
   └── V = F_h × W / (M × α_x × ρ_0 × 3600)         ft/sec

7. FOUR CHECKS
   ├── FLUIDELASTIC (V-10):    D = f(pattern, X, p_t/d_o) → V_c = D×f_n×d_o/12 → V/V_c < 0.5
   ├── VORTEX SHEDDING (V-11.2): S = f(p_t/d_o, p_l/d_o) → f_vs → y_vs → y_vs ≤ 0.02×d_o
   ├── TURBULENT BUFFETING (V-11.3): C_F → y_tb → y_tb ≤ 0.02×d_o
   └── ACOUSTIC RESONANCE (V-12): f_a vs f_vs/f_tb → 3 conditions (gas only)
```

---

## Sub-Tasks (Build Order)

### ST-1: Create `data/material_properties.py` — Material Data Table

**File:** `hx_engine/app/data/material_properties.py` (CREATE)

**What:** Physical properties for tube materials — Young's modulus E (temperature-dependent), metal density ρ, and Poisson's ratio ν. Shared data source for Steps 13 and 14.

**Material keys match existing `_DEFAULT_MATERIAL_K` in `step_09_overall_u.py`:**

```python
"""Material physical properties for tube materials.

Sources:
  - Young's modulus: ASME BPVC Section II Part D, Tables TM-1, TM-4, TM-5
  - Density: ASME BPVC Section II Part D, Table PRD
  - Poisson's ratio: ASME BPVC Section II Part D, Table PRD

Used by:
  - Step 13 (vibration): E for natural frequency, ρ for tube mass
  - Step 14 (mechanical): E for ASME VIII calculations, ν for stress
"""

# {material_key: {"E_GPa": {temp_C: E_value}, "density_kg_m3": float, "poisson": float, "label": str}}
_MATERIAL_PROPERTIES: dict[str, dict] = {
    "carbon_steel": {
        "label": "Carbon Steel (SA-179/SA-214)",
        "density_kg_m3": 7750,
        "poisson": 0.30,
        "E_GPa": {        # ASME II-D TM-1, Group: C≤0.30%
            25: 202, 100: 198, 150: 195, 200: 192, 250: 189,
            300: 185, 350: 179, 400: 171, 450: 162, 500: 151,
        },
    },
    "stainless_304": {
        "label": "Stainless Steel 304",
        "density_kg_m3": 8030,
        "poisson": 0.31,
        "E_GPa": {        # ASME II-D TM-1, Group G (Austenitic SS)
            25: 195, 100: 189, 150: 186, 200: 183, 250: 179,
            300: 176, 350: 172, 400: 169, 450: 165, 500: 160,
            550: 156, 600: 151, 650: 146, 700: 140,
        },
    },
    "stainless_316": {
        "label": "Stainless Steel 316",
        "density_kg_m3": 8030,
        "poisson": 0.31,
        "E_GPa": {        # Same Group G as 304
            25: 195, 100: 189, 150: 186, 200: 183, 250: 179,
            300: 176, 350: 172, 400: 169, 450: 165, 500: 160,
            550: 156, 600: 151, 650: 146, 700: 140,
        },
    },
    "copper": {
        "label": "Copper (C12200)",
        "density_kg_m3": 8940,
        "poisson": 0.33,
        "E_GPa": {25: 117},   # TM-3; single-point (Cu HX typically < 150°C)
    },
    "admiralty_brass": {
        "label": "Admiralty Brass (C44300)",
        "density_kg_m3": 8520,
        "poisson": 0.33,
        "E_GPa": {25: 100},   # TM-3; single-point
    },
    "titanium": {
        "label": "Titanium Gr. 2",
        "density_kg_m3": 4510,
        "poisson": 0.32,
        "E_GPa": {        # ASME II-D TM-5, Ti Gr 1/2/3/7/11/12
            25: 107, 100: 103, 150: 101, 200: 97, 250: 93,
            300: 88, 350: 84, 400: 80,
        },
    },
    "inconel_600": {
        "label": "Inconel 600 (N06600)",
        "density_kg_m3": 8410,
        "poisson": 0.31,
        "E_GPa": {        # ASME II-D TM-4, N06600
            25: 213, 100: 209, 200: 203, 300: 198, 400: 192,
            500: 186, 600: 178, 700: 170,
        },
    },
    "monel_400": {
        "label": "Monel 400 (N04400)",
        "density_kg_m3": 8860,
        "poisson": 0.31,
        "E_GPa": {        # ASME II-D TM-4, N04400
            25: 179, 100: 175, 200: 171, 300: 166, 400: 161,
            500: 155, 600: 149, 700: 142,
        },
    },
    "duplex_2205": {
        "label": "Duplex SS 2205 (S31803)",
        "density_kg_m3": 7800,
        "poisson": 0.31,
        "E_GPa": {        # ASME II-D TM-1, Group H
            25: 200, 100: 194, 200: 186, 300: 180, 400: 174,
            450: 172,
        },
    },
}
```

**Public API:**

```python
def get_elastic_modulus(material: str, temperature_C: float = 25.0) -> float:
    """Return Young's modulus in Pa (not GPa) at the specified temperature.

    Linearly interpolates between available data points.
    Clamps to nearest available temperature if out of range.
    Raises KeyError for unknown material.
    """

def get_density(material: str) -> float:
    """Return tube metal density in kg/m³. Raises KeyError for unknown material."""

def get_poisson(material: str) -> float:
    """Return Poisson's ratio. Raises KeyError for unknown material."""

def get_available_materials() -> list[str]:
    """Return list of valid material keys."""
```

**Test:** `tests/unit/test_material_properties.py`

| Test                                | Description                          | Asserts                                            |
| ----------------------------------- | ------------------------------------ | -------------------------------------------------- |
| `test_carbon_steel_E_at_25C`        | Room temperature lookup              | E = 202e9 Pa                                       |
| `test_carbon_steel_E_at_200C`       | Direct table lookup                  | E = 192e9 Pa                                       |
| `test_carbon_steel_E_interpolation` | E at 175°C (between 150 and 200)     | Interpolated between 195 and 192                   |
| `test_E_clamp_below_range`          | E at −50°C                           | Returns E at 25°C (lowest available)               |
| `test_E_clamp_above_range`          | Carbon steel E at 600°C              | Returns E at 500°C (highest available for C≤0.30%) |
| `test_copper_single_point`          | Only 25°C available                  | Returns 117e9 for any temperature                  |
| `test_all_nine_materials`           | Loop all keys                        | Each returns valid E > 0, ρ > 0, 0 < ν < 0.5       |
| `test_unknown_material_raises`      | `get_elastic_modulus("unobtainium")` | Raises `KeyError`                                  |
| `test_density_values`               | Spot check 3 materials               | Match ASME PRD table                               |

---

### ST-2: Add `pitch_angle_deg` to `GeometrySpec` and `baffle_thickness_m` to `GeometrySpec`

**File:** `hx_engine/app/models/design_state.py` (MODIFY)

**What:** Add two optional fields to `GeometrySpec`:

```python
class GeometrySpec(BaseModel):
    # ... existing fields ...

    # --- Added for Step 13 (vibration) ---
    pitch_angle_deg: Optional[int] = None
    """Tube layout angle in degrees: 30, 45, 60, or 90.
    If None, derived from pitch_layout: 'triangular' → 30, 'square' → 90.
    Set explicitly only when 45° or 60° layout is specified."""

    baffle_thickness_m: Optional[float] = None
    """Baffle plate thickness in metres. Default 0.00635 (1/4 inch) if None.
    Used for vapor damping calculation (V-8)."""

    @field_validator("pitch_angle_deg")
    @classmethod
    def _check_pitch_angle(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in (30, 45, 60, 90):
            raise ValueError(f"pitch_angle_deg must be 30, 45, 60, or 90; got {v}")
        return v

    @field_validator("baffle_thickness_m")
    @classmethod
    def _check_baffle_thickness(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and (v < 0.003 or v > 0.025):
            raise ValueError(f"baffle_thickness_m={v} outside range [0.003, 0.025]")
        return v
```

**Helper method on `GeometrySpec`:**

```python
def get_pitch_angle(self) -> int:
    """Return pitch angle in degrees. Uses pitch_angle_deg if set,
    otherwise derives from pitch_layout (triangular→30, square→90)."""
    if self.pitch_angle_deg is not None:
        return self.pitch_angle_deg
    return 90 if self.pitch_layout == "square" else 30

def get_baffle_thickness(self) -> float:
    """Return baffle thickness in metres. Defaults to 0.00635 (1/4 inch)."""
    return self.baffle_thickness_m if self.baffle_thickness_m is not None else 0.00635
```

**Impact:** No existing code breaks — both fields are Optional with None default. Step 4 does not need modification (it already sets `pitch_layout`; `pitch_angle_deg` defaults to None → derived as 30° or 90°).

**Test:** Add to existing `test_design_state.py`:

| Test                                  | Asserts                                                                           |
| ------------------------------------- | --------------------------------------------------------------------------------- |
| `test_pitch_angle_default_triangular` | `GeometrySpec(pitch_layout="triangular").get_pitch_angle() == 30`                 |
| `test_pitch_angle_default_square`     | `GeometrySpec(pitch_layout="square").get_pitch_angle() == 90`                     |
| `test_pitch_angle_explicit_45`        | `GeometrySpec(pitch_layout="square", pitch_angle_deg=45).get_pitch_angle() == 45` |
| `test_pitch_angle_invalid`            | `pitch_angle_deg=15` raises `ValueError`                                          |
| `test_baffle_thickness_default`       | `get_baffle_thickness() == 0.00635`                                               |

---

### ST-3: Add `DesignState` Fields for Vibration Results

**File:** `hx_engine/app/models/design_state.py` (MODIFY)

**New fields on `DesignState`:**

```python
# --- vibration check (populated by Step 13) ---
vibration_safe: Optional[bool] = None
vibration_details: Optional[dict] = None
```

**Add to `_OUTPUT_FIELD_MAP` in `state_utils.py`:**

```python
"vibration_safe": "vibration_safe",
"vibration_details": "vibration_details",
```

**Impact:** Minimal — two Optional fields, no validators needed (dict is opaque by design, AI and frontend consume it).

---

### ST-4: Create `correlations/tema_vibration.py` — Part 1: Unit Conversion + Tube Properties

**File:** `hx_engine/app/correlations/tema_vibration.py` (CREATE)

This is the largest sub-task, split into 4 parts. Part 1 covers the foundation.

#### 4.1 Module Docstring & Constants

```python
"""TEMA Section 6 (V-1 through V-14) flow-induced vibration correlations.

All formulas implemented per TEMA Standards, 9th Edition.
Internal calculations use English units (inches, lb/ft, ft/sec, psi, lb/ft³)
to preserve TEMA's magic constants for easy audit.

SI inputs are converted at the boundary; SI results are returned.

References:
  - TEMA 9th Ed., Section 6 (V-1 through V-14)
  - Connors (1970), ASME — fluidelastic instability
  - Owen (1965), J. Mech. Eng. Sci. — turbulent buffeting
  - Pettigrew & Taylor (1991) — damping ratios
"""
```

#### 4.2 SI ↔ English Conversion Helpers

```python
def _m_to_in(m: float) -> float:
    """Metres → inches."""
    return m * 39.3701

def _in_to_m(inches: float) -> float:
    """Inches → metres."""
    return inches / 39.3701

def _kg_m3_to_lb_ft3(rho: float) -> float:
    """kg/m³ → lb/ft³."""
    return rho * 0.062428

def _Pa_s_to_cP(mu: float) -> float:
    """Pa·s → centipoise."""
    return mu * 1000.0

def _Pa_to_psi(pa: float) -> float:
    """Pascals → psi."""
    return pa * 0.000145038

def _GPa_to_psi(gpa: float) -> float:
    """GPa → psi."""
    return gpa * 145037.738

def _kg_s_to_lb_hr(m_dot: float) -> float:
    """kg/s → lb/hr."""
    return m_dot * 7936.64

def _ft_s_to_m_s(v: float) -> float:
    """ft/sec → m/s."""
    return v * 0.3048

def _in_to_mm(inches: float) -> float:
    """Inches → mm."""
    return inches * 25.4
```

#### 4.3 Moment of Inertia (V-5.3)

```python
def compute_moment_of_inertia(d_o_m: float, d_i_m: float) -> float:
    """Tube moment of inertia. Returns I in in⁴ (English units for TEMA formulas).

    I = π/64 × (d_o⁴ − d_i⁴)   [V-5.3]
    """
    d_o = _m_to_in(d_o_m)
    d_i = _m_to_in(d_i_m)
    return math.pi / 64.0 * (d_o**4 - d_i**4)
```

#### 4.4 Effective Tube Weight (V-7)

```python
def compute_effective_tube_weight(
    d_o_m: float,
    d_i_m: float,
    rho_metal_kg_m3: float,
    rho_tube_fluid_kg_m3: float,
    rho_shell_fluid_kg_m3: float,
    pitch_ratio: float,
    pitch_angle_deg: int,
) -> dict:
    """Effective tube weight per unit length per TEMA V-7.

    Returns dict with w_0, w_t, w_fi, H_m, C_m (all in lb/ft for TEMA formulas).
    """
```

**Includes:**

- Metal weight: `w_t = ρ_metal × A_metal_cross_section` (converted from kg/m to lb/ft)
- Internal fluid: `w_fi = 0.00545 × ρ_i × d_i²` (V-7.1)
- Added mass coefficient `C_m` from Table V-7.11 (interpolated)
- Hydrodynamic mass: `H_m = C_m × 0.00545 × ρ_0 × d_o²` (V-7.11)
- Total: `w_0 = w_t + w_fi + H_m`

#### 4.5 Added Mass Coefficient C_m (Table V-7.11, Digitized)

```python
# TEMA Figure V-7.11 — Added Mass Coefficient
# Key: pitch_ratio (p_t/d_o), Values: (C_m_square, C_m_triangular)
_CM_TABLE: list[tuple[float, float, float]] = [
    # (p_t/d_o, C_m_square_45_90, C_m_triangular_30_60)
    (1.05, 2.80, 2.40),
    (1.10, 2.20, 1.92),
    (1.15, 1.88, 1.72),
    (1.20, 1.70, 1.58),
    (1.25, 1.58, 1.48),
    (1.30, 1.48, 1.40),
    (1.33, 1.42, 1.36),
    (1.40, 1.34, 1.30),
    (1.50, 1.27, 1.24),
    (1.60, 1.22, 1.20),
    (1.70, 1.18, 1.17),
    (1.80, 1.15, 1.14),
    (1.90, 1.13, 1.12),
    (2.00, 1.11, 1.10),
]

def _interpolate_Cm(pitch_ratio: float, pitch_angle_deg: int) -> float:
    """Interpolate C_m from Table V-7.11."""
```

**Test:** `tests/unit/test_tema_vibration_tube_props.py`

| Test                                 | Description                                    | Asserts                                      |
| ------------------------------------ | ---------------------------------------------- | -------------------------------------------- |
| `test_moment_of_inertia_19mm_tube`   | 3/4" OD, 16 BWG                                | I matches hand calculation                   |
| `test_effective_weight_water_filled` | Carbon steel tube, water inside, water outside | w_0 > w_t + w_fi (due to H_m)                |
| `test_Cm_at_1_25_triangular`         | Direct table lookup                            | C_m = 1.48                                   |
| `test_Cm_at_1_25_square`             | Direct table lookup                            | C_m = 1.58                                   |
| `test_Cm_interpolation`              | p_t/d_o = 1.27 (between 1.25 and 1.30)         | Interpolated between 1.58/1.48 and 1.48/1.40 |
| `test_Cm_extrapolation_low`          | p_t/d_o = 1.02                                 | Clamped to C_m at 1.05                       |

---

### ST-5: Create `correlations/tema_vibration.py` — Part 2: Natural Frequency + Damping

**File:** `hx_engine/app/correlations/tema_vibration.py` (APPEND to file from ST-4)

#### 5.1 Natural Frequency — Straight Spans (V-5.3)

```python
# Table V-5.3: Frequency constant C
_EDGE_CONDITION_C = {
    "simply-simply": 9.87,       # baffle–baffle (central spans)
    "fixed-simply": 15.42,       # tubesheet–baffle (inlet/outlet spans)
    "fixed-fixed": 22.37,        # tubesheet–tubesheet (rare, no baffles)
}

def compute_natural_frequency(
    span_m: float,
    E_Pa: float,
    I_in4: float,
    w_0_lb_ft: float,
    edge_condition: str = "simply-simply",
    A_axial: float = 1.0,
) -> float:
    """Fundamental natural frequency per TEMA V-5.3.

    f_n = 10.838 × A × C / l² × √(EI / w_0)

    Args:
        span_m: unsupported span length in metres (converted to inches internally)
        E_Pa: Young's modulus in Pascals (converted to psi internally)
        I_in4: moment of inertia in in⁴ (already in English from compute_moment_of_inertia)
        w_0_lb_ft: effective tube weight in lb/ft (already in English from compute_effective_tube_weight)
        edge_condition: key into _EDGE_CONDITION_C
        A_axial: axial stress multiplier (default 1.0)

    Returns:
        f_n in cycles/sec (Hz)
    """
```

#### 5.2 Damping — Liquid Service (V-8)

```python
def compute_damping_liquid(
    d_o_m: float,
    w_0_lb_ft: float,
    f_n_Hz: float,
    rho_shell_kg_m3: float,
    mu_shell_Pa_s: float,
) -> dict:
    """Logarithmic decrement for shell-side liquid per TEMA V-8.

    δ_T = max(δ_1, δ_2)

    δ_1 = 3.41 × d_o / (w_0 × f_n)          [viscous]
    δ_2 = 0.012 × d_o/w_0 × √(ρ_0 × μ / f_n)  [squeeze-film]

    Returns dict with delta_T, delta_1, delta_2.
    """
```

#### 5.3 Damping — Vapor Service (V-8)

```python
def compute_damping_vapor(
    n_spans: int,
    baffle_thickness_m: float,
    span_m: float,
) -> float:
    """Logarithmic decrement for shell-side vapor per TEMA V-8.

    δ_v = 0.314 × (N-1)/N × (t_b/l)^(1/2)

    Returns delta_v.
    """
```

#### 5.4 Fluid Elastic Parameter X (V-4.2)

```python
def compute_fluid_elastic_parameter(
    w_0_lb_ft: float,
    delta_T: float,
    rho_shell_kg_m3: float,
    d_o_m: float,
) -> float:
    """X = 144 × w_0 × δ_T / (ρ_0 × d_o²) per TEMA V-4.2.

    All unit conversions handled internally.
    Returns dimensionless X.
    """
```

**Test:** `tests/unit/test_tema_vibration_frequency.py`

| Test                                  | Description                          | Asserts                             |
| ------------------------------------- | ------------------------------------ | ----------------------------------- |
| `test_natural_frequency_central_span` | 19mm tube, 127mm span, carbon steel  | f_n in reasonable range (20–100 Hz) |
| `test_natural_frequency_inlet_span`   | Same tube, 190mm span (1.5× central) | f_n < central span f_n              |
| `test_fn_fixed_fixed_highest`         | Both-ends-fixed condition            | f_n > fixed-simply > simply-simply  |
| `test_damping_liquid_water`           | Water at 30°C, typical geometry      | δ_T > 0.01                          |
| `test_damping_viscous_dominates`      | High viscosity fluid (crude oil)     | δ_1 > δ_2, δ_T = δ_1                |
| `test_fluid_elastic_parameter`        | Known inputs                         | X matches hand calculation          |
| `test_damping_vapor`                  | Gas service, 10 spans, 6.35mm baffle | δ_v in reasonable range             |

---

### ST-6: Create `correlations/tema_vibration.py` — Part 3: Crossflow Velocity (V-9)

**File:** `hx_engine/app/correlations/tema_vibration.py` (APPEND)

This is the most complex single function — TEMA V-9.2 with all correction factors.

#### 6.1 Pattern Constants (Table V-9.211A)

```python
# Table V-9.211A: Pattern constants
_PATTERN_CONSTANTS = {
    #         C4    C5    C6    m
    30:  (1.26, 0.82, 1.48, 0.85),
    60:  (1.09, 0.61, 1.28, 0.87),
    90:  (1.26, 0.66, 1.38, 0.93),
    45:  (0.90, 0.56, 1.17, 0.80),
}
```

#### 6.2 C₈ Table (Table V-9.211B)

```python
# Table V-9.211B: C₈ vs baffle cut ratio h/D₁
_C8_TABLE: list[tuple[float, float]] = [
    (0.10, 0.94), (0.15, 0.90), (0.20, 0.85), (0.25, 0.80),
    (0.30, 0.74), (0.35, 0.68), (0.40, 0.62), (0.45, 0.54),
    (0.50, 0.49),
]
```

#### 6.3 Crossflow Velocity Function

```python
def compute_crossflow_velocity(
    shell_id_m: float,
    otl_m: float,              # Outer Tube Limit diameter
    tube_od_m: float,
    tube_pitch_m: float,
    baffle_spacing_m: float,
    baffle_cut: float,         # fraction (0.15–0.45)
    pitch_angle_deg: int,      # 30, 45, 60, or 90
    shell_flow_kg_s: float,
    rho_shell_kg_m3: float,
    tube_hole_dia_m: float,    # tube hole in baffle (d_o + clearance)
    n_sealing_strip_pairs: int = 0,
) -> dict:
    """Reference crossflow velocity per TEMA V-9.2.

    Complete V-9.211 calculation with all correction factors F_h, M, α_x.

    Returns:
        dict with V_ft_s, V_m_s, F_h, M, alpha_x, and all intermediates
        for transparency and debugging.
    """
```

**Implementation notes:**

- `D_1` = shell_id (inches), `D_2` = baffle OD (D_1 − clearance from TEMA tables), `D_3` = OTL (inches)
- `d_1` = tube_hole_dia (inches), `d_o` = tube_od (inches), `P` = tube_pitch (inches)
- `h` = baffle_cut × D_1 (height from cut to shell ID, inches)
- `l_3` = baffle_spacing (inches)
- Seal strip correction V-9.3: modifies C_1 when `n_sealing_strip_pairs > 0`
- Need to compute `D_2` (baffle diameter) from shell diameter and clearance — reuse `_CLEARANCE_TABLE` from `tema_tables.py`

**Dependency on existing data:** Needs `delta_sb_mm` (shell-baffle clearance) from `tema_tables.py` to compute baffle diameter `D_2 = D_1 - delta_sb_mm`. Import and reuse.

**Test:** `tests/unit/test_tema_vibration_crossflow.py`

| Test                               | Description                                          | Asserts                                  |
| ---------------------------------- | ---------------------------------------------------- | ---------------------------------------- |
| `test_crossflow_velocity_basic`    | Standard geometry (590mm shell, 19mm tubes, 30° tri) | V in range 0.5–5.0 m/s                   |
| `test_F_h_less_than_one`           | F_h is a correction factor                           | 0 < F_h ≤ 1.0                            |
| `test_seal_strips_reduce_velocity` | Same geometry, 2 seal strip pairs vs 0               | V with seals < V without seals           |
| `test_all_four_patterns`           | 30°, 45°, 60°, 90° same geometry                     | All return valid V > 0, different values |
| `test_high_baffle_cut_effect`      | baffle_cut = 0.40 vs 0.25                            | Different C_8 → different V              |
| `test_returns_all_intermediates`   | Check dict keys                                      | F_h, M, alpha_x, C1–C8 all present       |

---

### ST-7: Create `correlations/tema_vibration.py` — Part 4: Four Vibration Checks

**File:** `hx_engine/app/correlations/tema_vibration.py` (APPEND)

#### 7.1 Critical Flow Velocity Factor D (Table V-10.1)

```python
# Table V-10.1: Formulae for D (critical flow velocity factor)
def _compute_D_factor(pitch_angle_deg: int, pitch_ratio: float, X: float) -> float:
    """Dimensionless critical flow velocity factor per TEMA V-10.1.

    Piecewise formulas by tube pattern and X range.
    """
    if pitch_angle_deg == 30:
        if 0.1 <= X <= 1.0:
            return 8.86 * (pitch_ratio - 0.9) * X**0.34
        elif 1.0 < X <= 300:
            return 8.86 * (pitch_ratio - 0.9) * X**0.5
    elif pitch_angle_deg == 60:
        if 0.01 <= X <= 1.0:
            return 2.80 * X**0.17
        elif 1.0 < X <= 300:
            return 2.80 * X**0.5
    elif pitch_angle_deg == 90:
        if 0.03 <= X <= 0.7:
            return 2.10 * X**0.15
        elif 0.7 < X <= 300:
            return 2.35 * X**0.5
    elif pitch_angle_deg == 45:
        if 0.1 <= X <= 300:
            return 4.13 * (pitch_ratio - 0.5) * X**0.5
    raise ValueError(f"X={X} out of valid range for {pitch_angle_deg}° pattern")
```

#### 7.2 Fluidelastic Instability Check (V-10)

```python
def check_fluidelastic(
    V_ft_s: float,
    f_n_Hz: float,
    d_o_m: float,
    D_factor: float,
) -> dict:
    """Check fluidelastic instability per TEMA V-10.

    V_c = D × f_n × d_o / 12   (ft/sec)
    Criterion: V / V_c < 0.5  (safety factor of 2)

    Returns dict with V_crit_m_s, velocity_ratio, safe (bool).
    """
```

#### 7.3 Strouhal Number Tables (Figures V-12.2A and V-12.2B, Digitized)

```python
# Figure V-12.2A: Strouhal number for 90° tube patterns
# Key: p_t/d_o, sub-key: p_l/d_o → S
_STROUHAL_90: dict[float, dict[float, float]] = {
    # p_t/d_o: {p_l/d_o: S}
    1.0: {1.25: 0.00, 1.5: 0.00, 2.0: 0.00, 2.5: 0.00, 3.0: 0.00},
    1.1: {1.25: 0.12, 1.5: 0.06, 2.0: 0.03, 2.5: 0.02, 3.0: 0.01},
    1.2: {1.25: 0.25, 1.5: 0.14, 2.0: 0.07, 2.5: 0.05, 3.0: 0.03},
    1.3: {1.25: 0.35, 1.5: 0.20, 2.0: 0.11, 2.5: 0.08, 3.0: 0.05},
    1.4: {1.25: 0.40, 1.5: 0.25, 2.0: 0.15, 2.5: 0.10, 3.0: 0.07},
    1.5: {1.25: 0.44, 1.5: 0.28, 2.0: 0.18, 2.5: 0.13, 3.0: 0.09},
    1.7: {1.25: 0.47, 1.5: 0.33, 2.0: 0.22, 2.5: 0.16, 3.0: 0.12},
    2.0: {1.25: 0.49, 1.5: 0.37, 2.0: 0.26, 2.5: 0.20, 3.0: 0.15},
    2.5: {1.25: 0.50, 1.5: 0.40, 2.0: 0.30, 2.5: 0.24, 3.0: 0.19},
    3.0: {1.25: 0.50, 1.5: 0.42, 2.0: 0.33, 2.5: 0.27, 3.0: 0.20},
    4.0: {1.25: 0.50, 1.5: 0.44, 2.0: 0.36, 2.5: 0.30, 3.0: 0.20},
}

# Figure V-12.2B: Strouhal number for 30°, 45°, 60° tube patterns
_STROUHAL_TRI: dict[float, dict[float, float]] = {
    # p_t/d_o: {p_l/d_o: S}
    1.0: {0.625: 0.00, 1.0: 0.00, 1.315: 0.00, 1.97: 0.00, 2.625: 0.00, 3.95: 0.00},
    1.1: {0.625: 0.20, 1.0: 0.10, 1.315: 0.05, 1.97: 0.03, 2.625: 0.02, 3.95: 0.01},
    1.2: {0.625: 0.42, 1.0: 0.22, 1.315: 0.12, 1.97: 0.06, 2.625: 0.04, 3.95: 0.02},
    1.3: {0.625: 0.58, 1.0: 0.32, 1.315: 0.18, 1.97: 0.10, 2.625: 0.06, 3.95: 0.03},
    1.4: {0.625: 0.68, 1.0: 0.40, 1.315: 0.24, 1.97: 0.13, 2.625: 0.08, 3.95: 0.05},
    1.5: {0.625: 0.74, 1.0: 0.45, 1.315: 0.28, 1.97: 0.16, 2.625: 0.10, 3.95: 0.06},
    1.7: {0.625: 0.80, 1.0: 0.53, 1.315: 0.35, 1.97: 0.21, 2.625: 0.14, 3.95: 0.08},
    2.0: {0.625: 0.85, 1.0: 0.60, 1.315: 0.40, 1.97: 0.28, 2.625: 0.20, 3.95: 0.12},
    2.5: {0.625: 0.88, 1.0: 0.68, 1.315: 0.47, 1.97: 0.32, 2.625: 0.22, 3.95: 0.15},
    3.0: {0.625: 0.88, 1.0: 0.72, 1.315: 0.50, 1.97: 0.35, 2.625: 0.23, 3.95: 0.18},
    4.0: {0.625: 0.88, 1.0: 0.75, 1.315: 0.52, 1.97: 0.37, 2.625: 0.24, 3.95: 0.20},
}

def _interpolate_strouhal(pitch_angle_deg: int, pt_do: float, pl_do: float) -> float:
    """Bilinear interpolation of Strouhal number from TEMA Figures V-12.2A/B."""
```

#### 7.4 Vortex Shedding Check (V-11.2 + V-12.2)

```python
# Table V-11.2: Lift Coefficients C_L
_LIFT_COEFFICIENTS = {
    # p_t/d_o: {30: C_L, 60: C_L, 90: C_L, 45: C_L}
    1.20: {30: 0.090, 60: 0.090, 90: 0.070, 45: 0.070},
    1.25: {30: 0.091, 60: 0.091, 90: 0.070, 45: 0.070},
    1.33: {30: 0.065, 60: 0.017, 90: 0.070, 45: 0.010},
    1.50: {30: 0.025, 60: 0.047, 90: 0.068, 45: 0.049},
}

def check_vortex_shedding(
    V_ft_s: float,
    f_n_Hz: float,
    d_o_m: float,
    rho_shell_kg_m3: float,
    w_0_lb_ft: float,
    delta_T: float,
    pitch_angle_deg: int,
    pitch_ratio: float,
    pl_do: float,              # longitudinal pitch ratio (for Strouhal)
) -> dict:
    """Vortex shedding amplitude check per TEMA V-11.2.

    f_vs = 12 × S × V / d_o                    [V-12.2]
    y_vs = C_L × ρ₀ × d_o × V² / (2π² × δ_T × f_n² × w₀)  [V-11.2]
    Criterion: y_vs ≤ 0.02 × d_o

    Returns dict with f_vs_Hz, y_vs_mm, y_max_mm, amplitude_ratio, safe (bool),
    strouhal_number, C_L, and f_vs_over_f_n.
    """
```

#### 7.5 Turbulent Buffeting Check (V-11.3 + V-12.3)

```python
# Table V-11.3: Force Coefficients C_F
def _get_force_coefficient(f_n_Hz: float, is_entrance: bool) -> float:
    """Force coefficient C_F per TEMA Table V-11.3.

    Piecewise linear function of f_n.
    """
    if is_entrance:
        if f_n_Hz <= 40:
            return 0.022
        elif f_n_Hz >= 88:
            return 0.0
        else:
            return -0.00045 * f_n_Hz + 0.04
    else:  # interior tubes
        if f_n_Hz <= 40:
            return 0.012
        elif f_n_Hz >= 88:
            return 0.0
        else:
            return -0.00025 * f_n_Hz + 0.022

def check_turbulent_buffeting(
    V_ft_s: float,
    f_n_Hz: float,
    d_o_m: float,
    rho_shell_kg_m3: float,
    w_0_lb_ft: float,
    delta_T: float,
    pitch_ratio: float,        # x_t = p_t/d_o
    pl_do: float,              # x_l = p_l/d_o
    is_entrance: bool = False,
) -> dict:
    """Turbulent buffeting check per TEMA V-11.3 and V-12.3.

    f_tb = 12V / (d_o × x_l × x_t) × [3.05(1 − 1/x_t)² + 0.28]  [V-12.3]
    y_tb = C_F × ρ₀ × d_o × V² / (8π × δ_T^½ × f_n^(3/2) × w₀)  [V-11.3]
    Criterion: y_tb ≤ 0.02 × d_o

    Returns dict with f_tb_Hz, y_tb_mm, y_max_mm, amplitude_ratio, safe (bool), C_F.
    """
```

#### 7.6 Acoustic Resonance Check (V-12)

```python
def check_acoustic_resonance(
    V_ft_s: float,
    f_vs_Hz: float,
    f_tb_Hz: float,
    d_o_m: float,
    shell_id_m: float,
    pitch_ratio: float,        # x_t
    pl_do: float,              # x_l
    pitch_angle_deg: int,
    rho_shell_kg_m3: float,
    mu_shell_Pa_s: float,
    P_shell_Pa: float,         # operating shell-side pressure
    gamma: float,              # specific heat ratio (Cp/Cv)
    is_gas: bool,
    baffle_cut: float,
) -> dict:
    """Acoustic resonance check per TEMA V-12.

    Only applicable for gas service. Returns early for liquids.

    f_a = (409/w) × [P_s×γ / (ρ₀×(1+0.5/(x_l×x_t)))]^½ × i    [V-12.1]

    Three conditions checked (A, B, C):
      A: 0.8×f_vs < f_a < 1.2×f_vs  or  0.8×f_tb < f_a < 1.2×f_tb
      B: V > f_a×d_o×(x_t − 0.5)/6
      C: V > f_a×d_o/(12S)  AND  Re/(S×x_t)×(1−1/x₀)² > 2000

    Returns dict with applicable (bool), reason, f_a_modes_Hz,
    condition_A/B/C (bool each), resonance_possible (bool).
    """
```

**Test:** `tests/unit/test_tema_vibration_checks.py`

| Test                                  | Description                      | Asserts                                        |
| ------------------------------------- | -------------------------------- | ---------------------------------------------- |
| `test_D_factor_30deg_low_X`           | X=0.5, 30°, p/d=1.25             | D matches TEMA table (≈1.91)                   |
| `test_D_factor_90deg_transition`      | X at boundary (0.7)              | Correct branch selected                        |
| `test_D_factor_45deg`                 | X=1.0, 45°, p/d=1.25             | D = 4.13 × (1.25−0.5) × 1.0 = 3.10             |
| `test_fluidelastic_safe`              | V well below V_c                 | `velocity_ratio < 0.5`, `safe=True`            |
| `test_fluidelastic_unsafe`            | V > 0.5 × V_c                    | `safe=False`                                   |
| `test_vortex_shedding_amplitude`      | Known inputs                     | y_vs within physical range, y_max = 0.02 × d_o |
| `test_vortex_shedding_safe`           | Low velocity                     | `amplitude_ratio < 1.0`, `safe=True`           |
| `test_turbulent_buffeting_entrance`   | Entrance location                | Uses higher C_F = 0.022                        |
| `test_turbulent_buffeting_interior`   | Interior location                | Uses lower C_F = 0.012                         |
| `test_C_F_frequency_interpolation`    | f_n = 60 Hz, entrance            | C_F = −0.00045×60 + 0.04 = 0.013               |
| `test_C_F_above_88Hz`                 | f_n = 100 Hz                     | C_F = 0.0                                      |
| `test_acoustic_liquid_skipped`        | `is_gas=False`                   | `applicable=False`                             |
| `test_acoustic_gas_no_resonance`      | Gas, f_a far from f_vs/f_tb      | All conditions False                           |
| `test_acoustic_gas_condition_A`       | f_a ≈ f_vs                       | `condition_A=True`, `resonance_possible=True`  |
| `test_strouhal_90deg_lookup`          | p_t/d_o=1.25, p_l/d_o=1.25       | S from table (direct lookup)                   |
| `test_strouhal_30deg_interpolation`   | p_t/d_o=1.35, p_l/d_o=1.0        | Interpolated between rows                      |
| `test_lift_coefficient_lookup`        | p/d=1.25, 30°                    | C_L = 0.091                                    |
| `test_lift_coefficient_interpolation` | p/d=1.26 (between 1.25 and 1.33) | Interpolated C_L                               |

---

### ST-8: Create Top-Level `check_all_spans()` Orchestrator in `tema_vibration.py`

**File:** `hx_engine/app/correlations/tema_vibration.py` (APPEND)

**What:** A single entry-point function that Step 13 calls. Runs the full TEMA V-4 through V-12 chain for each span and assembles the complete result dict.

```python
def check_all_spans(
    # Geometry (SI)
    tube_od_m: float,
    tube_id_m: float,
    tube_pitch_m: float,
    shell_id_m: float,
    baffle_spacing_m: float,
    inlet_baffle_spacing_m: float | None,
    outlet_baffle_spacing_m: float | None,
    baffle_cut: float,
    baffle_thickness_m: float,
    n_baffles: int,
    pitch_angle_deg: int,
    pitch_ratio: float,
    n_sealing_strip_pairs: int,
    otl_m: float,
    tube_hole_clearance_m: float,

    # Material
    E_Pa: float,
    rho_metal_kg_m3: float,

    # Fluids
    rho_shell_kg_m3: float,
    mu_shell_Pa_s: float,
    rho_tube_fluid_kg_m3: float,
    shell_flow_kg_s: float,

    # Acoustic (gas only)
    is_gas: bool = False,
    P_shell_Pa: float | None = None,
    gamma: float | None = None,
) -> dict:
    """Run complete TEMA Section 6 vibration analysis.

    Checks all 4 mechanisms at 3 span locations (inlet, central, outlet).

    Returns a dict matching the HTRI-equivalent output structure:
    {
        "spans": [...],
        "acoustic_resonance": {...},
        "critical_span": str,
        "worst_velocity_ratio": float,
        "worst_amplitude_ratio": float,
        "controlling_mechanism": str,
        "all_safe": bool,
        "velocity_margin_pct": float,
        "amplitude_margin_pct": float,
    }
    """
```

**Logic:**

```python
# 1. Compute tube properties (once — same for all spans)
I = compute_moment_of_inertia(tube_od_m, tube_id_m)
tube_weight = compute_effective_tube_weight(...)

# 2. Define spans
inlet_span = inlet_baffle_spacing_m or (baffle_spacing_m * 1.5)
outlet_span = outlet_baffle_spacing_m or (baffle_spacing_m * 1.5)
spans = [
    ("inlet",  inlet_span,  "fixed-simply", True),   # (name, length, edge, is_entrance)
    ("central", baffle_spacing_m, "simply-simply", False),
    ("outlet", outlet_span,  "fixed-simply", True),
]

# 3. Compute crossflow velocity (once — same V for all checks per TEMA V-9)
V_result = compute_crossflow_velocity(...)

# 4. Compute longitudinal pitch ratio p_l/d_o
#    For triangular pitch: p_l = p_t × sin(60°) = p_t × √3/2
#    For square pitch: p_l = p_t
pl_do = _compute_longitudinal_pitch_ratio(pitch_angle_deg, pitch_ratio)

# 5. Check each span
span_results = []
for name, span_m, edge, is_entrance in spans:
    f_n = compute_natural_frequency(span_m, E_Pa, I, tube_weight["w_0"], edge)
    damping = compute_damping_liquid(...)
    X = compute_fluid_elastic_parameter(...)
    D = _compute_D_factor(pitch_angle_deg, pitch_ratio, X)

    fe_result = check_fluidelastic(V_result["V_ft_s"], f_n, tube_od_m, D)
    vs_result = check_vortex_shedding(...)
    tb_result = check_turbulent_buffeting(..., is_entrance=is_entrance)

    span_results.append({
        "location": name,
        "span_m": span_m,
        "edge_condition": edge,
        "C_frequency": _EDGE_CONDITION_C[edge],
        "f_n_Hz": f_n,
        "w_eff_kg_m": _lb_ft_to_kg_m(tube_weight["w_0"]),
        "log_decrement": damping["delta_T"],
        "X_parameter": X,
        "V_cross_m_s": V_result["V_m_s"],
        "F_h": V_result["F_h"],
        "M": V_result["M"],
        **fe_result,
        **vs_result,
        **tb_result,
    })

# 6. Acoustic resonance (once for the whole bundle)
acoustic = check_acoustic_resonance(
    V_result["V_ft_s"],
    span_results[1]["f_vs_Hz"],  # use central span f_vs
    span_results[1]["f_tb_Hz"],  # use central span f_tb
    ...,
    is_gas=is_gas,
)

# 7. Assemble summary
worst_vr = max(s["velocity_ratio"] for s in span_results)
worst_ar = max(
    max(s["amplitude_ratio_vs"], s["amplitude_ratio_tb"])
    for s in span_results
)
all_safe = all(
    s["fluidelastic_safe"] and s["vortex_shedding_safe"] and s["turbulent_buffeting_safe"]
    for s in span_results
) and not acoustic.get("resonance_possible", False)

return {
    "spans": span_results,
    "acoustic_resonance": acoustic,
    "critical_span": max(span_results, key=lambda s: s["velocity_ratio"])["location"],
    "worst_velocity_ratio": worst_vr,
    "worst_amplitude_ratio": worst_ar,
    "controlling_mechanism": _identify_controlling_mechanism(span_results, acoustic),
    "all_safe": all_safe,
    "velocity_margin_pct": (0.5 - worst_vr) / 0.5 * 100 if worst_vr < 0.5 else 0.0,
    "amplitude_margin_pct": (1.0 - worst_ar) / 1.0 * 100 if worst_ar < 1.0 else 0.0,
}
```

**Test:** `tests/unit/test_tema_vibration_integration.py`

| Test                                 | Description                                             | Asserts                                          |
| ------------------------------------ | ------------------------------------------------------- | ------------------------------------------------ |
| `test_check_all_spans_safe_design`   | Standard safe geometry (large baffle spacing, low flow) | `all_safe=True`, 3 spans in output               |
| `test_check_all_spans_unsafe_design` | Tight geometry, high flow                               | `all_safe=False`, worst span identified          |
| `test_inlet_span_default_1_5x`       | `inlet_baffle_spacing_m=None`                           | Inlet span = 1.5 × central                       |
| `test_inlet_span_explicit`           | `inlet_baffle_spacing_m=0.200`                          | Inlet span = 0.200                               |
| `test_output_structure_matches_spec` | Any geometry                                            | All expected keys present in result dict         |
| `test_acoustic_skipped_for_liquid`   | `is_gas=False`                                          | `acoustic_resonance.applicable=False`            |
| `test_worst_span_is_inlet`           | Inlet span 1.5× central                                 | `critical_span == "inlet"` (typical for real HX) |
| `test_margin_percentages`            | Known velocity_ratio                                    | `velocity_margin_pct` correct                    |

---

### ST-9: Create `steps/step_13_vibration.py`

**File:** `hx_engine/app/steps/step_13_vibration.py` (CREATE)

**What:** Standard `BaseStep` subclass, `ai_mode=FULL`. Reads geometry + fluid props from state, calls `check_all_spans()`, writes results to state.

```python
"""Step 13: Flow-Induced Vibration Check.

Safety-critical post-convergence check. Evaluates tube vibration risk
using TEMA Section 6 methodology at all unsupported spans.

AI Mode: FULL (always reviewed — safety-critical step).
"""

import hx_engine.app.steps.step_13_rules  # noqa: F401  — auto-register rules

class Step13VibrationCheck(BaseStep):
    step_id: int = 13
    step_name: str = "Vibration Check"
    ai_mode: AIModeEnum = AIModeEnum.FULL
```

#### 9.1 Preconditions

```python
@staticmethod
def _check_preconditions(state: DesignState) -> list[str]:
    """Check all inputs required for vibration analysis are present."""
    missing = []

    # Geometry
    g = state.geometry
    if g is None:
        return ["geometry (GeometrySpec not set)"]

    for field in [
        "tube_od_m", "tube_id_m", "tube_pitch_m", "shell_diameter_m",
        "baffle_spacing_m", "baffle_cut", "n_baffles", "pitch_layout",
        "pitch_ratio", "n_tubes",
    ]:
        if getattr(g, field, None) is None:
            missing.append(f"geometry.{field}")

    # Tube material (for E and ρ_metal)
    if not state.tube_material:
        missing.append("tube_material")

    # Fluid properties (shell-side)
    shell_side = state.shell_side_fluid
    if not shell_side:
        missing.append("shell_side_fluid")
    else:
        props = state.hot_fluid_props if shell_side == "hot" else state.cold_fluid_props
        if props is None:
            missing.append(f"{shell_side}_fluid_props")
        else:
            if props.density_kg_m3 is None:
                missing.append(f"{shell_side}_fluid_props.density_kg_m3")
            if props.viscosity_Pa_s is None:
                missing.append(f"{shell_side}_fluid_props.viscosity_Pa_s")

    # Tube-side fluid density (for w_fi)
    tube_side = "cold" if shell_side == "hot" else "hot"
    tube_props = state.hot_fluid_props if tube_side == "hot" else state.cold_fluid_props
    if tube_props is None or tube_props.density_kg_m3 is None:
        missing.append(f"{tube_side}_fluid_props.density_kg_m3")

    # Mass flow rate (shell-side)
    m_dot_field = f"m_dot_{shell_side}_kg_s"
    if getattr(state, m_dot_field, None) is None:
        missing.append(m_dot_field)

    return missing
```

#### 9.2 Execute Method

```python
async def execute(self, state: DesignState) -> StepResult:
    missing = self._check_preconditions(state)
    if missing:
        raise CalculationError(f"Step 13 missing inputs: {', '.join(missing)}")

    g = state.geometry
    shell_side = state.shell_side_fluid
    tube_side = "cold" if shell_side == "hot" else "hot"

    # Resolve fluid properties
    shell_props = state.hot_fluid_props if shell_side == "hot" else state.cold_fluid_props
    tube_props = state.hot_fluid_props if tube_side == "hot" else state.cold_fluid_props
    m_dot_shell = (
        state.m_dot_hot_kg_s if shell_side == "hot" else state.m_dot_cold_kg_s
    )

    # Material properties
    from hx_engine.app.data.material_properties import get_elastic_modulus, get_density
    mat_key = _resolve_material_key(state.tube_material)  # same pattern as Step 9
    E_Pa = get_elastic_modulus(mat_key, temperature_C=_estimate_tube_temp(state))
    rho_metal = get_density(mat_key)

    # Compute OTL (Outer Tube Limit) — approximate as D_s - 2×clearance
    from hx_engine.app.data.tema_tables import get_clearances
    delta_sb, delta_tb = get_clearances(g.shell_diameter_m)
    otl_m = g.shell_diameter_m - delta_sb / 1000.0  # delta_sb in mm → m
    tube_hole_clearance_m = delta_tb / 1000.0

    # Determine if shell-side is gas (Phase 1: always liquid)
    fluid_name = (
        state.hot_fluid_name if shell_side == "hot" else state.cold_fluid_name
    ) or ""
    is_gas = _is_gas_service(fluid_name)

    # Run full vibration analysis
    from hx_engine.app.correlations.tema_vibration import check_all_spans
    result = check_all_spans(
        tube_od_m=g.tube_od_m,
        tube_id_m=g.tube_id_m,
        tube_pitch_m=g.tube_pitch_m,
        shell_id_m=g.shell_diameter_m,
        baffle_spacing_m=g.baffle_spacing_m,
        inlet_baffle_spacing_m=g.inlet_baffle_spacing_m,
        outlet_baffle_spacing_m=g.outlet_baffle_spacing_m,
        baffle_cut=g.baffle_cut,
        baffle_thickness_m=g.get_baffle_thickness(),
        n_baffles=g.n_baffles,
        pitch_angle_deg=g.get_pitch_angle(),
        pitch_ratio=g.pitch_ratio,
        n_sealing_strip_pairs=g.n_sealing_strip_pairs,
        otl_m=otl_m,
        tube_hole_clearance_m=tube_hole_clearance_m,
        E_Pa=E_Pa,
        rho_metal_kg_m3=rho_metal,
        rho_shell_kg_m3=shell_props.density_kg_m3,
        mu_shell_Pa_s=shell_props.viscosity_Pa_s,
        rho_tube_fluid_kg_m3=tube_props.density_kg_m3,
        shell_flow_kg_s=m_dot_shell,
        is_gas=is_gas,
    )

    # Write to state
    state.vibration_safe = result["all_safe"]
    state.vibration_details = result

    # Build warnings
    warnings = []
    if not result["all_safe"]:
        warnings.append(
            f"VIBRATION UNSAFE: V/V_c = {result['worst_velocity_ratio']:.3f} "
            f"at {result['critical_span']} span (limit 0.500). "
            f"Controlling mechanism: {result['controlling_mechanism']}."
        )
    if result["worst_velocity_ratio"] > 0.35:
        warnings.append(
            f"Velocity ratio {result['worst_velocity_ratio']:.3f} approaching limit. "
            f"Margin: {result['velocity_margin_pct']:.1f}%."
        )

    # Build outputs (for AI review and audit trail)
    outputs = {
        "vibration_safe": result["all_safe"],
        "vibration_details": result,
        "worst_velocity_ratio": result["worst_velocity_ratio"],
        "worst_amplitude_ratio": result["worst_amplitude_ratio"],
        "critical_span": result["critical_span"],
        "controlling_mechanism": result["controlling_mechanism"],
        "velocity_margin_pct": result["velocity_margin_pct"],
        "amplitude_margin_pct": result["amplitude_margin_pct"],
        "n_spans_checked": len(result["spans"]),
        "tube_material": state.tube_material,
        "E_Pa": E_Pa,
        "rho_metal_kg_m3": rho_metal,
    }

    # Escalation hints for AI
    escalation_hints = []
    if not result["all_safe"]:
        escalation_hints.append({
            "trigger": f"V/V_c = {result['worst_velocity_ratio']:.3f} > 0.5",
            "recommendation": (
                "Reduce crossflow velocity by increasing baffle spacing, "
                "switching to double-segmental baffles, or using a J-shell (divided flow). "
                "Re-run convergence (Step 12) after geometry change."
            ),
        })

    return StepResult(
        step_id=self.step_id,
        step_name=self.step_name,
        outputs=outputs,
        warnings=warnings,
        escalation_hints=escalation_hints if escalation_hints else None,
    )
```

#### 9.3 Helper Functions

```python
def _resolve_material_key(tube_material: str) -> str:
    """Map tube_material string to a material_properties.py key.
    Handles both key format ('carbon_steel') and label format ('Carbon Steel (SA-179)').
    """

def _estimate_tube_temp(state: DesignState) -> float:
    """Estimate tube metal temperature for E(T) lookup.
    Average of shell-side and tube-side bulk temperatures.
    """

def _is_gas_service(fluid_name: str) -> bool:
    """Return True if the fluid name suggests gas/vapor service."""
```

**Test:** `tests/unit/test_step_13_execute.py`

| Test                                  | Description                      | Asserts                                                        |
| ------------------------------------- | -------------------------------- | -------------------------------------------------------------- |
| `test_preconditions_all_present`      | Full state from Step 12          | Returns empty list                                             |
| `test_preconditions_missing_geometry` | No geometry on state             | Returns list with "geometry"                                   |
| `test_preconditions_missing_material` | No tube_material                 | Returns list with "tube_material"                              |
| `test_execute_safe_design`            | Standard safe geometry           | `vibration_safe=True` in result + state                        |
| `test_execute_unsafe_design`          | Tight geometry, high flow        | `vibration_safe=False`, warnings non-empty                     |
| `test_execute_writes_state`           | Any geometry                     | `state.vibration_safe` and `state.vibration_details` populated |
| `test_outputs_dict_complete`          | Any geometry                     | All expected keys in outputs                                   |
| `test_escalation_hints_on_failure`    | Unsafe design                    | `escalation_hints` is not None                                 |
| `test_material_key_resolution`        | `"Carbon Steel (SA-179/SA-214)"` | Resolved to `"carbon_steel"`                                   |
| `test_liquid_service_not_gas`         | `fluid_name="cooling water"`     | `is_gas=False`                                                 |

---

### ST-10: Create `steps/step_13_rules.py`

**File:** `hx_engine/app/steps/step_13_rules.py` (CREATE)

**What:** Layer 2 hard rules — AI cannot override these.

```python
"""Step 13 validation rules — Flow-Induced Vibration.

Hard rules per TEMA Section 6 and STEPS_6_16_PLAN.md:
  R1: V/V_c < 0.5 at every span (fluidelastic instability)
  R2: y_vs ≤ 0.02 × d_o at every span (vortex shedding amplitude)
  R3: y_tb ≤ 0.02 × d_o at every span (turbulent buffeting amplitude)
  R4: vibration_safe must not be None (calculation must complete)
"""

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.step_result import StepResult


def _rule_velocity_ratio(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    """R1: V/V_c < 0.5 at every span."""
    details = result.outputs.get("vibration_details")
    if details is None:
        return False, "vibration_details missing from Step 13 outputs"
    for span in details.get("spans", []):
        vr = span.get("velocity_ratio")
        if vr is not None and vr >= 0.5:
            loc = span.get("location", "unknown")
            return False, (
                f"Fluidelastic instability: V/V_c = {vr:.3f} ≥ 0.500 "
                f"at {loc} span"
            )
    return True, None


def _rule_vortex_amplitude(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    """R2: Vortex shedding amplitude ≤ 0.02 × d_o at every span."""
    details = result.outputs.get("vibration_details")
    if details is None:
        return False, "vibration_details missing from Step 13 outputs"
    for span in details.get("spans", []):
        ar = span.get("amplitude_ratio_vs")
        if ar is not None and ar > 1.0:
            loc = span.get("location", "unknown")
            y = span.get("y_vs_mm", 0)
            y_max = span.get("y_max_mm", 0)
            return False, (
                f"Vortex shedding amplitude {y:.3f} mm > limit {y_max:.3f} mm "
                f"at {loc} span"
            )
    return True, None


def _rule_buffeting_amplitude(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    """R3: Turbulent buffeting amplitude ≤ 0.02 × d_o at every span."""
    details = result.outputs.get("vibration_details")
    if details is None:
        return False, "vibration_details missing from Step 13 outputs"
    for span in details.get("spans", []):
        ar = span.get("amplitude_ratio_tb")
        if ar is not None and ar > 1.0:
            loc = span.get("location", "unknown")
            y = span.get("y_tb_mm", 0)
            y_max = span.get("y_max_mm", 0)
            return False, (
                f"Turbulent buffeting amplitude {y:.3f} mm > limit {y_max:.3f} mm "
                f"at {loc} span"
            )
    return True, None


def _rule_vibration_calculated(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    """R4: vibration_safe must be present (calculation completed)."""
    vs = result.outputs.get("vibration_safe")
    if vs is None:
        return False, "vibration_safe is None — vibration check did not complete"
    return True, None


def register_step13_rules() -> None:
    register_rule(13, _rule_velocity_ratio)
    register_rule(13, _rule_vortex_amplitude)
    register_rule(13, _rule_buffeting_amplitude)
    register_rule(13, _rule_vibration_calculated)


register_step13_rules()
```

**Test:** `tests/unit/test_step_13_rules.py`

| Test                             | Description             | Asserts                                |
| -------------------------------- | ----------------------- | -------------------------------------- |
| `test_R1_safe_velocity_ratio`    | All spans V/V_c < 0.5   | Rule passes                            |
| `test_R1_unsafe_inlet_span`      | Inlet span V/V_c = 0.55 | Rule fails with message naming "inlet" |
| `test_R2_safe_vortex_amplitude`  | All spans y_vs < y_max  | Rule passes                            |
| `test_R2_unsafe_vortex`          | One span y_vs > y_max   | Rule fails                             |
| `test_R3_safe_buffeting`         | All spans y_tb < y_max  | Rule passes                            |
| `test_R3_unsafe_buffeting`       | One span y_tb > y_max   | Rule fails                             |
| `test_R4_missing_vibration_safe` | `vibration_safe=None`   | Rule fails                             |
| `test_R4_vibration_calculated`   | `vibration_safe=True`   | Rule passes                            |
| `test_all_rules_registered`      | Import step_13_rules    | 4 rules registered for step 13         |

---

### ST-11: Wire Step 13 into `pipeline_runner.py` + `state_utils.py`

**File:** `hx_engine/app/core/pipeline_runner.py` (MODIFY)

**What:** Import Step 13 and add it after the Step 12 convergence loop.

```python
from hx_engine.app.steps.step_13_vibration import Step13VibrationCheck

# In the pipeline run method, after Step 12 convergence completes:
# --- Post-convergence steps (run once on final geometry) ---
POST_CONVERGENCE_STEPS = [
    Step13VibrationCheck,
    # Step14Mechanical,   (future)
    # Step15Cost,         (future)
    # Step16Validation,   (future)
]
```

**File:** `hx_engine/app/core/state_utils.py` (MODIFY)

**What:** Add output field mappings for Step 13.

```python
# In _OUTPUT_FIELD_MAP:
"vibration_safe": "vibration_safe",
"vibration_details": "vibration_details",
```

**Test:** Existing pipeline integration tests continue to pass. New test verifying Step 13 is called after Step 12.

---

### ST-12: Tests — Integration

**File:** `tests/unit/test_step_13_integration.py` (CREATE)

Full integration tests running Step 13 with realistic state from Steps 1–12.

| Test                                  | Description                                        | Asserts                                               |
| ------------------------------------- | -------------------------------------------------- | ----------------------------------------------------- |
| `test_step_13_after_convergence`      | Build full state through Step 12, then run Step 13 | `vibration_safe` set, `vibration_details` has 3 spans |
| `test_step_13_full_ai_review`         | FULL mode → AI always called                       | `ai_called=True` in step record                       |
| `test_step_13_ai_escalate_on_failure` | Unsafe design → AI escalates                       | `decision == ESCALATE`                                |
| `test_step_13_remedies_in_escalation` | Unsafe → escalation has remedies                   | `escalation_hints` non-empty                          |
| `test_step_13_serth_example`          | Serth 5.1 geometry (Ds=0.5906m, etc.)              | All spans safe (this is a well-designed HX)           |

---

## File Summary

| #   | File                                            | Action                                                                                                                 | Sub-Task                     |
| --- | ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| 1   | `hx_engine/app/data/material_properties.py`     | CREATE                                                                                                                 | ST-1                         |
| 2   | `hx_engine/app/models/design_state.py`          | MODIFY — add pitch_angle_deg, baffle_thickness_m to GeometrySpec; add vibration_safe, vibration_details to DesignState | ST-2, ST-3                   |
| 3   | `hx_engine/app/correlations/tema_vibration.py`  | CREATE — all TEMA V-4 through V-12 correlations                                                                        | ST-4, ST-5, ST-6, ST-7, ST-8 |
| 4   | `hx_engine/app/steps/step_13_vibration.py`      | CREATE — BaseStep subclass                                                                                             | ST-9                         |
| 5   | `hx_engine/app/steps/step_13_rules.py`          | CREATE — 4 hard rules                                                                                                  | ST-10                        |
| 6   | `hx_engine/app/core/pipeline_runner.py`         | MODIFY — wire Step 13 after convergence                                                                                | ST-11                        |
| 7   | `hx_engine/app/core/state_utils.py`             | MODIFY — add output field mappings                                                                                     | ST-11                        |
| 8   | `tests/unit/test_material_properties.py`        | CREATE                                                                                                                 | ST-1                         |
| 9   | `tests/unit/test_tema_vibration_tube_props.py`  | CREATE                                                                                                                 | ST-4                         |
| 10  | `tests/unit/test_tema_vibration_frequency.py`   | CREATE                                                                                                                 | ST-5                         |
| 11  | `tests/unit/test_tema_vibration_crossflow.py`   | CREATE                                                                                                                 | ST-6                         |
| 12  | `tests/unit/test_tema_vibration_checks.py`      | CREATE                                                                                                                 | ST-7                         |
| 13  | `tests/unit/test_tema_vibration_integration.py` | CREATE                                                                                                                 | ST-8                         |
| 14  | `tests/unit/test_step_13_execute.py`            | CREATE                                                                                                                 | ST-9                         |
| 15  | `tests/unit/test_step_13_rules.py`              | CREATE                                                                                                                 | ST-10                        |
| 16  | `tests/unit/test_step_13_integration.py`        | CREATE                                                                                                                 | ST-12                        |

---

## Build Sequence

```
ST-1  material_properties.py + tests          (standalone, no dependencies)
  │
  ▼
ST-2  GeometrySpec: pitch_angle_deg + baffle_thickness_m + tests
  │
  ▼
ST-3  DesignState: vibration_safe + vibration_details
  │
  ├──────────────────────────────────────────────────────────┐
  ▼                                                          │
ST-4  tema_vibration.py Part 1: conversions + tube props     │
  │                                                          │
  ▼                                                          │
ST-5  tema_vibration.py Part 2: natural frequency + damping  │
  │                                                          │
  ▼                                                          │
ST-6  tema_vibration.py Part 3: crossflow velocity (V-9)     │
  │                                                          │
  ▼                                                          │
ST-7  tema_vibration.py Part 4: four vibration checks        │
  │                                                          │
  ▼                                                          │
ST-8  tema_vibration.py Part 5: check_all_spans() orchestr.  │
  │                                                          │
  └────────────────────────────┬─────────────────────────────┘
                               ▼
                    ST-9   step_13_vibration.py
                               │
                    ST-10  step_13_rules.py
                               │
                    ST-11  pipeline_runner.py + state_utils.py wiring
                               │
                    ST-12  Integration tests
```

---

## Edge Cases

| #   | Edge Case                                                    | Expected Behaviour                                                          |
| --- | ------------------------------------------------------------ | --------------------------------------------------------------------------- |
| E1  | `inlet_baffle_spacing_m = None`                              | Default to 1.5 × `baffle_spacing_m`                                         |
| E2  | `outlet_baffle_spacing_m = None`                             | Default to 1.5 × `baffle_spacing_m`                                         |
| E3  | `pitch_angle_deg = None` with `pitch_layout = "triangular"`  | Derive 30° automatically                                                    |
| E4  | `pitch_angle_deg = None` with `pitch_layout = "square"`      | Derive 90° automatically                                                    |
| E5  | `pitch_angle_deg = 45` with `pitch_layout = "square"`        | Use 45° for all TEMA tables                                                 |
| E6  | Unknown `tube_material` string                               | `_resolve_material_key` raises → `CalculationError`; AI can suggest default |
| E7  | Material E(T) requested above max temperature in table       | Clamp to highest available T; add warning                                   |
| E8  | Material E(T) requested below 25°C                           | Clamp to 25°C value                                                         |
| E9  | pitch_ratio outside C_m table range (< 1.05 or > 2.0)        | Clamp to nearest endpoint; add warning                                      |
| E10 | X parameter outside D-factor formula range                   | Clamp and warn; log which branch was used                                   |
| E11 | Very short baffle spacing (< 50mm) → very high f_n           | Vibration almost certainly safe; allow and report                           |
| E12 | Very long unsupported span → very low f_n                    | Vibration likely unsafe; report correctly                                   |
| E13 | n_baffles = 1 (only 1 central span, no central→central span) | Check inlet, 1 central, outlet                                              |
| E14 | C_F = 0.0 (f_n ≥ 88 Hz)                                      | y_tb = 0 → turbulent buffeting safe (high-frequency tubes don't respond)    |
| E15 | Shell-side gas service (Phase 1: shouldn't happen)           | Acoustic check runs fully; vapor damping δ_v used                           |
| E16 | Vibration fails → AI ESCALATE → user prompted                | AI provides specific remedies per TEMA V-13                                 |
| E17 | Strouhal number interpolation at table boundary              | Clamp p_t/d_o and p_l/d_o to table range                                    |
| E18 | n_sealing_strip_pairs > 0                                    | V-9.3 modified C_1 used → lower crossflow velocity                          |
| E19 | All spans safe but one has V/V_c = 0.48 (near limit)         | Warning added: "approaching limit"; AI reviews margin                       |
| E20 | Copper tube at 200°C (E data only at 25°C)                   | Uses 25°C E (clamped); warning: "single-point E data"                       |

---

## TEMA Section 6 Formula Cross-Reference

Every formula in `tema_vibration.py` maps to a specific TEMA section:

| Function                          | TEMA Section      | Formula                              |
| --------------------------------- | ----------------- | ------------------------------------ |
| `compute_moment_of_inertia`       | V-5.3             | I = π/64 × (d_o⁴ − d_i⁴)             |
| `compute_effective_tube_weight`   | V-7.1             | w₀ = w_t + w_fi + H_m                |
| `_interpolate_Cm`                 | Figure V-7.11     | C_m vs p_t/d_o                       |
| `compute_natural_frequency`       | V-5.3             | f_n = 10.838 × A × C / l² × √(EI/w₀) |
| `compute_damping_liquid`          | V-8               | δ_T = max(δ₁, δ₂)                    |
| `compute_damping_vapor`           | V-8               | δ_v = 0.314 × (N−1)/N × (t_b/l)^½    |
| `compute_fluid_elastic_parameter` | V-4.2             | X = 144 × w₀ × δ_T / (ρ₀ × d_o²)     |
| `compute_crossflow_velocity`      | V-9.2             | V = F_h × W / (M × α_x × ρ₀ × 3600)  |
| `_compute_D_factor`               | Table V-10.1      | D = f(pattern, X, p_t/d_o)           |
| `check_fluidelastic`              | V-10              | V_c = D × f_n × d_o / 12             |
| `check_vortex_shedding`           | V-11.2, V-12.2    | y_vs ≤ 0.02 × d_o                    |
| `check_turbulent_buffeting`       | V-11.3, V-12.3    | y_tb ≤ 0.02 × d_o                    |
| `check_acoustic_resonance`        | V-12.1–V-12.43    | f_a vs f_vs, 3 conditions            |
| `_interpolate_strouhal`           | Figures V-12.2A/B | S vs p_t/d_o, p_l/d_o                |
| `_get_force_coefficient`          | Table V-11.3      | C_F = f(f_n, location)               |

---

## Data Tables Encoded (from TEMA Section 6)

| Table                      | Location in Code                   | Source                               |
| -------------------------- | ---------------------------------- | ------------------------------------ |
| Edge condition C           | `_EDGE_CONDITION_C`                | Table V-5.3                          |
| Added mass C_m             | `_CM_TABLE`                        | Figure V-7.11 (14 points × 2 curves) |
| Pattern constants C₄–C₆, m | `_PATTERN_CONSTANTS`               | Table V-9.211A                       |
| C₈ vs h/D₁                 | `_C8_TABLE`                        | Table V-9.211B (9 points)            |
| D factor formulas          | `_compute_D_factor()`              | Table V-10.1 (7 piecewise formulas)  |
| Lift coefficients C_L      | `_LIFT_COEFFICIENTS`               | Table V-11.2 (4×4)                   |
| Force coefficients C_F     | `_get_force_coefficient()`         | Table V-11.3 (piecewise)             |
| Strouhal 90°               | `_STROUHAL_90`                     | Figure V-12.2A (11×5)                |
| Strouhal 30°/45°/60°       | `_STROUHAL_TRI`                    | Figure V-12.2B (11×6)                |
| Confinement C_FU           | `_CFU_TABLE` (optional, two-phase) | Table V-8                            |

---

## Data Tables Encoded (from ASME BPVC II-D)

| Table                | Location in Code                             | Source                            |
| -------------------- | -------------------------------------------- | --------------------------------- |
| Young's modulus E(T) | `_MATERIAL_PROPERTIES[key]["E_GPa"]`         | ASME II-D Tables TM-1, TM-4, TM-5 |
| Metal density ρ      | `_MATERIAL_PROPERTIES[key]["density_kg_m3"]` | ASME II-D Table PRD               |
| Poisson's ratio ν    | `_MATERIAL_PROPERTIES[key]["poisson"]`       | ASME II-D Table PRD               |
