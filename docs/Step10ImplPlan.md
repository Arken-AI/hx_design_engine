# Step 10: Pressure Drops — Implementation Plan

**Status:** Ready to implement  
**Depends on:** Steps 1–9 (complete), BaseStep infrastructure (complete)  
**References:** Serth Ch. 5 (Appendix 5.A for SI), Sinnott Ch. 12 (Bell's method §12.9.4)

---

## Overview

Step 10 computes tube-side and shell-side pressure drops for the converged geometry. It uses:

- **Churchill correlation** for tube-side Darcy friction factor (all flow regimes)
- **Bell's method** (Sinnott §12.9.4) for shell-side ΔP with F'\_b, F'\_L correction factors
- **Kern method** (Sinnott Eq. 12.26) as shell-side cross-check
- **Simplified Delaware** (Serth Eqs. 5.6–5.11) as a second shell-side cross-check

**AI Mode:** CONDITIONAL — AI called only when ΔP margin < 15% of hard limit. Skipped when `in_convergence_loop=True`.

---

## Sub-Steps (Build Order)

| #     | Sub-Step                          | File                                                | Depends On                    | Est. Complexity |
| ----- | --------------------------------- | --------------------------------------------------- | ----------------------------- | --------------- |
| 10.1  | Churchill friction correlation    | `correlations/churchill_friction.py`                | None                          | Small           |
| 10.2  | Nozzle sizing data table          | `data/nozzle_table.py`                              | None                          | Small           |
| 10.3  | Shell-side ΔP in bell_delaware.py | `correlations/bell_delaware.py` (add functions)     | Existing `compute_geometry()` | Medium          |
| 10.4  | Simplified Delaware cross-check   | `correlations/simplified_delaware_dp.py`            | None                          | Small           |
| 10.5  | DesignState fields                | `models/design_state.py` (add fields)               | None                          | Small           |
| 10.6  | Pipeline runner mapping           | `core/pipeline_runner.py` (extend `_apply_outputs`) | 10.5                          | Small           |
| 10.7  | Step 10 executor                  | `steps/step_10_pressure_drops.py`                   | 10.1–10.6                     | Large           |
| 10.8  | Step 10 validation rules          | `steps/step_10_rules.py`                            | 10.5, 10.7                    | Small           |
| 10.9  | Pipeline wiring                   | `core/pipeline_runner.py` (add to PIPELINE_STEPS)   | 10.7, 10.8                    | Small           |
| 10.10 | Unit tests                        | `tests/unit/test_step_10_*.py`                      | All above                     | Medium          |

---

## Sub-Step 10.1: Churchill Friction Correlation

**File:** `hx_engine/app/correlations/churchill_friction.py`

### Purpose

Single equation covering laminar, transition, and turbulent Darcy friction factor. Critical for the convergence loop (Step 12) where Re may shift regimes iteration-to-iteration.

### Source

Churchill, S.W. (1977). _Chemical Engineering_, 84(24), 91–92.

### Function Signature

```python
def churchill_friction_factor(Re: float, roughness_ratio: float = 0.0) -> float:
    """Churchill (1977) — Darcy friction factor for all flow regimes.

    Args:
        Re: Reynolds number (> 0).
        roughness_ratio: ε/D (dimensionless). Default 0.0 = smooth tube.
            For commercial HE tubes, typically 0.0 (drawn tubing).

    Returns:
        Darcy friction factor (dimensionless).

    Raises:
        ValueError: If Re <= 0.
    """
```

### Formula

$$f = 8\left[\left(\frac{8}{Re}\right)^{12} + \frac{1}{(A+B)^{3/2}}\right]^{1/12}$$

$$A = \left[-2.457 \ln\left(\left(\frac{7}{Re}\right)^{0.9} + 0.27\frac{\varepsilon}{D}\right)\right]^{16}$$

$$B = \left(\frac{37530}{Re}\right)^{16}$$

### Validation Points

| Re      | ε/D | Expected f | Cross-check                                          |
| ------- | --- | ---------- | ---------------------------------------------------- |
| 500     | 0.0 | 0.1280     | 64/Re = 0.128 (laminar)                              |
| 3000    | 0.0 | ~0.044     | Serth Eq. 5.2 → 0.04349                              |
| 10,000  | 0.0 | ~0.031     | Serth Eq. 5.2 → 0.03282                              |
| 100,000 | 0.0 | ~0.018     | Serth Eq. 5.2 → 0.01931                              |
| 12,149  | 0.0 | ~0.030     | Serth Example 5.1 first trial (f=0.03638 for Eq.5.2) |

**Note:** Churchill gives Fanning-equivalent when written some ways — our version uses the `8×[...]^(1/12)` form which gives **Darcy** directly. Verify by checking f=64/Re at low Re.

### Tests File

`tests/unit/correlations/test_churchill_friction.py`

- `test_laminar_matches_64_over_re()` — Re=100,200,500,1000 → f ≈ 64/Re ±0.5%
- `test_turbulent_matches_serth()` — Re=3000,10000,100000 → within ±5% of Serth Eq. 5.2
- `test_smooth_tube_default()` — roughness_ratio=0.0 gives same as explicit smooth
- `test_invalid_re_raises()` — Re≤0 → ValueError
- `test_transition_region_smooth()` — Re=2000–4000 → f is continuous (no discontinuity)

---

## Sub-Step 10.2: Nozzle Sizing Data Table

**File:** `hx_engine/app/data/nozzle_table.py`

### Purpose

Default nozzle diameter lookup when user doesn't specify nozzle size. Source: Serth Table 5.3.

### Data

```python
# (shell_size_lower_in, shell_size_upper_in, nozzle_diameter_in)
_NOZZLE_TABLE: list[tuple[float, float, float]] = [
    (4.0,   10.0,   2.0),
    (12.0,  17.25,  3.0),
    (19.25, 21.25,  4.0),
    (23.0,  29.0,   6.0),
    (31.0,  37.0,   8.0),
    (39.0,  42.0,  10.0),
]
```

### Function Signatures

```python
def get_default_nozzle_diameter_m(shell_id_m: float) -> float:
    """Look up default nozzle ID from Serth Table 5.3.

    Converts shell_id_m to inches, finds matching range,
    returns nozzle diameter in meters (Schedule 40 nominal → actual ID).

    Raises ValueError if shell_id outside table range.
    """

def nozzle_rho_v_squared(
    mass_flow_kg_s: float,
    density_kg_m3: float,
    nozzle_id_m: float,
    n_nozzles: int = 1,
) -> float:
    """Compute ρv² at the nozzle (kg/m·s²).

    ρv² = ρ × (ṁ / (ρ × A_nozzle))² = ṁ² / (ρ × A² × n²)
    Hard limit: 2230 kg/m·s² (= TEMA 1500 lbm/ft·s²).
    """
```

### Schedule 40 Nominal-to-ID Mapping (embedded constant)

| Nominal (in.) | Actual ID (in.) | Actual ID (m) |
| ------------- | --------------- | ------------- |
| 2             | 2.067           | 0.05250       |
| 3             | 3.068           | 0.07793       |
| 4             | 4.026           | 0.10226       |
| 6             | 6.065           | 0.15405       |
| 8             | 7.981           | 0.20272       |
| 10            | 10.020          | 0.25451       |

### Tests File

`tests/unit/data/test_nozzle_table.py`

- `test_each_shell_range()` — 6 cases mapping shell size → correct nozzle
- `test_meters_to_inches_conversion()` — 0.489 m shell → 19.25 in. → 4-in. nozzle
- `test_out_of_range_raises()` — shell < 4 in. or > 42 in. → ValueError
- `test_rho_v_squared_basic()` — known inputs → expected ρv²
- `test_rho_v_squared_under_limit()` — verify < 2230 for typical designs

---

## Sub-Step 10.3: Shell-Side ΔP in bell_delaware.py

**File:** `hx_engine/app/correlations/bell_delaware.py` (additions to existing file)

### Purpose

Add the pressure drop functions analogous to the existing HTC functions. Reuses `compute_geometry()` output.

### New Functions

#### 10.3a: `ideal_bank_jf()` — Ideal cross-flow friction factor

```python
def ideal_bank_jf(Re: float, layout_angle_deg: int) -> float:
    """Ideal tube-bank friction factor from Sinnott Figure 12.36.

    Uses interpolation of digitized data for 1.25 pitch ratio,
    triangular and square layouts.

    Args:
        Re: Shell-side Reynolds number (> 0).
        layout_angle_deg: 30/60 → triangular curve, 45/90 → square curve.

    Returns:
        j_f (dimensionless, Fanning×2 convention matching Sinnott).
    """
```

**Data source:** Digitized Figure 12.36 from Sinnott:

| Re      | 1.25 △ j_f | 1.25 □ j_f |
| ------- | ---------- | ---------- |
| 10      | 2.0        | 1.6        |
| 100     | 0.38       | 0.32       |
| 1,000   | 0.10       | 0.094      |
| 10,000  | 0.052      | 0.052      |
| 100,000 | 0.046      | 0.046      |
| 500,000 | 0.044      | 0.044      |

**Implementation:** Log-log interpolation between digitized points (same approach as if we had a table — `numpy.interp` on log-transformed data, or pure-Python equivalent).

#### 10.3b: `compute_Fb_pressure()` — Bypass correction for ΔP

```python
def compute_Fb_pressure(
    A_b_m2: float,
    A_s_m2: float,
    N_ss: int,
    N_cv: float,
    Re: float,
) -> float:
    """Sinnott Eq. 12.30: Bypass correction F'_b for pressure drop.

    F'_b = exp[-α × (A_b/A_s) × (1 - √(2×N_ss/N_cv))]
    α = 4.0 (Re > 100), α = 5.0 (Re < 100)

    Compare to HTC version (J_b): α = 1.25/1.35 — same form, larger ΔP penalty.
    """
```

**Mapping from existing `compute_geometry()` outputs:**

- `A_b_m2` = `S_b_m2`
- `A_s_m2` = `S_m_m2`
- `N_cv` = `N_c`

#### 10.3c: `compute_FL_pressure()` — Leakage correction for ΔP

```python
def compute_FL_pressure(
    A_tb_m2: float,
    A_sb_m2: float,
) -> float:
    """Sinnott Eq. 12.31 + Figure 12.38: Leakage correction F'_L for ΔP.

    A_L = A_tb + A_sb
    β'_L = interpolated from digitized Figure 12.38
    F'_L = 1 − β'_L × (A_tb + 2×A_sb) / A_L

    Compare to HTC version (F_L): uses β_L (smaller values).
    """
```

**β'\_L digitized table (Figure 12.38):**

| A_tb/(A_tb+A_sb) | β'\_L |
| ---------------- | ----- |
| 0.0              | 0.68  |
| 0.2              | 0.58  |
| 0.4              | 0.48  |
| 0.6              | 0.38  |
| 0.8              | 0.30  |
| 1.0              | 0.24  |

#### 10.3d: `shell_side_dP()` — Main orchestrator

```python
def shell_side_dP(
    # Geometry (same params as shell_side_htc)
    shell_id_m: float,
    tube_od_m: float,
    tube_pitch_m: float,
    layout_angle_deg: int,
    n_tubes: int,
    tube_passes: int,
    baffle_cut_pct: float,
    baffle_spacing_central_m: float,
    baffle_spacing_inlet_m: float,
    baffle_spacing_outlet_m: float,
    n_baffles: int,
    n_sealing_strip_pairs: int,
    # Clearances
    delta_tb_m: float,
    delta_sb_m: float,
    delta_bundle_shell_m: float,
    # Fluid props
    density_kg_m3: float,
    viscosity_Pa_s: float,
    viscosity_wall_Pa_s: float,
    mass_flow_kg_s: float,
    # Pitch ratio
    pitch_ratio: float,
) -> dict:
    """Compute shell-side pressure drop using Bell's method (Sinnott §12.9.4).

    Three zones: crossflow + window + end zones, corrected by F'_b and F'_L.

    Returns dict with keys:
        dP_shell_Pa, dP_crossflow_Pa, dP_window_Pa, dP_end_Pa,
        dP_ideal_Pa, Fb_prime, FL_prime, j_f,
        u_s_m_s (shell-side velocity), warnings
    """
```

**Total ΔP Assembly (Sinnott Eq. 12.37):**

$$\Delta P_s = 2\,\Delta P_e + \Delta P_c \cdot (N_b - 1) + N_b \cdot \Delta P_w$$

Where:

| Zone                | Formula                                                                                  | Sinnott Eq. |
| ------------------- | ---------------------------------------------------------------------------------------- | ----------- |
| Ideal crossflow     | $\Delta P_i = 8\,j_f \cdot N_{cv} \cdot \frac{\rho\,u_s^2}{2} \cdot (\mu/\mu_w)^{-0.14}$ | 12.33       |
| Corrected crossflow | $\Delta P_c = \Delta P_i \cdot F'_b \cdot F'_L$                                          | 12.32       |
| Window              | $\Delta P_w = F'_L \cdot (2 + 0.6\,N_{wv}) \cdot \frac{\rho\,u_z^2}{2}$                  | 12.34       |
| End zones           | $\Delta P_e = \Delta P_i \cdot \frac{N_{cv}+N_{wv}}{N_{cv}} \cdot F'_b$                  | 12.36       |

**Where:** $u_z = \sqrt{u_w \cdot u_s}$ (geometric mean), $u_w = \dot{m}/(A_w \cdot \rho)$, $u_s = G_s/\rho$

### Tests File

`tests/unit/correlations/test_bell_delaware_dP.py`

- `test_ideal_bank_jf_triangular()` — 5+ Re values against digitized table
- `test_ideal_bank_jf_square()` — 5+ Re values against digitized table
- `test_Fb_pressure_no_sealing_strips()` — N_ss=0 → large penalty
- `test_Fb_pressure_adequate_sealing()` — N_ss/N_cv ≥ 0.5 → F'\_b = 1.0
- `test_FL_pressure_bounds()` — F'\_L ∈ (0, 1]
- `test_shell_side_dP_all_zones()` — full orchestrator with known inputs
- `test_dP_increases_with_flow()` — higher mass flow → higher ΔP (sanity)

---

## Sub-Step 10.4: Simplified Delaware Cross-Check

**File:** `hx_engine/app/correlations/simplified_delaware_dp.py`

### Purpose

Implements Serth's Simplified Delaware shell-side ΔP (Eqs. 5.6–5.11, SI from 5.A.5) as a cross-check against Bell's method. Analogous to how Kern cross-checks Bell-Delaware for HTC in Step 8.

### Function Signature

```python
def simplified_delaware_shell_dP(
    shell_id_m: float,
    tube_od_m: float,
    tube_pitch_m: float,
    layout_angle_deg: int,
    baffle_spacing_m: float,
    n_baffles: int,
    mass_flow_kg_s: float,
    density_kg_m3: float,
    viscosity_Pa_s: float,
    viscosity_wall_Pa_s: float,
) -> dict:
    """Serth Simplified Delaware shell-side pressure drop (Eqs. 5.A.5, 5.7-5.11).

    Returns dict with keys:
        dP_shell_Pa, f_dimensionless, f1, f2, B_over_ds, Re_shell,
        method ("simplified_delaware")
    """
```

### Key Formulas (SI — Appendix 5.A)

**Friction factor interpolation (Eq. 5.7):**
$f = 144\{f_1 - 1.25(1 - B/d_s)(f_1 - f_2)\}$

where $d_s$ is in **inches** for Eqs. 5.8–5.11 (convert m → in. internally).

**For Re ≥ 1000 (Eqs. 5.8, 5.9):**

- $f_1 = (0.0076 + 0.000166\,d_s)\,Re^{-0.125}$
- $f_2 = (0.0016 + 5.8 \times 10^{-5}\,d_s)\,Re^{-0.157}$

**For Re < 1000 (Eqs. 5.10, 5.11):**

- $f_1 = \exp[-0.092(\ln Re)^2 - 1.48\ln Re - 0.000526\,d_s^2 + 0.0478\,d_s - 0.338]$
- $f_2 = \exp[-0.123(\ln Re)^2 - 1.78\ln Re - 0.00132\,d_s^2 + 0.0678\,d_s - 1.34]$

**Note:** Cap $d_s = 23.25$ in. for $f_2$ when shell > 23.25 in.

**ΔP (SI, Eq. 5.A.5):**
$\Delta P_f = \frac{f \cdot G^2 \cdot d_s \cdot (n_b + 1)}{2000 \cdot D_e \cdot s \cdot \phi}$

### Tests File

`tests/unit/correlations/test_simplified_delaware_dp.py`

- `test_serth_example_5_1_first_trial()` — dP_shell ≈ 1.06 psi (7.3 kPa)
- `test_serth_example_5_1_second_trial()` — dP_shell ≈ 2.03 psi (14.0 kPa)
- `test_serth_example_5_2()` — dP_shell ≈ 3.20 psi (22.1 kPa)
- `test_friction_factor_continuity()` — no discontinuity at Re=1000 boundary
- `test_ds_cap_for_f2()` — d_s > 23.25 → uses 23.25

---

## Sub-Step 10.5: DesignState Fields

**File:** `hx_engine/app/models/design_state.py` (modify existing)

### New Fields to Add

```python
# --- pressure drops (populated by Step 10) ---
dP_tube_Pa: Optional[float] = None
dP_shell_Pa: Optional[float] = None
dP_tube_friction_Pa: Optional[float] = None
dP_tube_minor_Pa: Optional[float] = None
dP_tube_nozzle_Pa: Optional[float] = None
dP_shell_crossflow_Pa: Optional[float] = None
dP_shell_window_Pa: Optional[float] = None
dP_shell_end_Pa: Optional[float] = None
dP_shell_nozzle_Pa: Optional[float] = None

# Shell-side ΔP correction factors
Fb_prime_dP: Optional[float] = None   # bypass correction (ΔP)
FL_prime_dP: Optional[float] = None   # leakage correction (ΔP)

# Nozzle data
nozzle_id_tube_m: Optional[float] = None
nozzle_id_shell_m: Optional[float] = None
rho_v2_tube_nozzle: Optional[float] = None  # kg/m·s²
rho_v2_shell_nozzle: Optional[float] = None  # kg/m·s²

# Cross-check values
dP_shell_simplified_delaware_Pa: Optional[float] = None
dP_shell_kern_Pa: Optional[float] = None
dP_shell_bell_vs_kern_pct: Optional[float] = None
```

### Placement

After the Step 9 block (after `U_vs_estimated_deviation_pct`), before pipeline state fields.

---

## Sub-Step 10.6: Pipeline Runner Mapping

**File:** `hx_engine/app/core/pipeline_runner.py` (modify `_apply_outputs`)

### Add to `mapping` dict

```python
# Step 10 pressure drops
"dP_tube_Pa": "dP_tube_Pa",
"dP_shell_Pa": "dP_shell_Pa",
"dP_tube_friction_Pa": "dP_tube_friction_Pa",
"dP_tube_minor_Pa": "dP_tube_minor_Pa",
"dP_tube_nozzle_Pa": "dP_tube_nozzle_Pa",
"dP_shell_crossflow_Pa": "dP_shell_crossflow_Pa",
"dP_shell_window_Pa": "dP_shell_window_Pa",
"dP_shell_end_Pa": "dP_shell_end_Pa",
"dP_shell_nozzle_Pa": "dP_shell_nozzle_Pa",
"Fb_prime_dP": "Fb_prime_dP",
"FL_prime_dP": "FL_prime_dP",
"nozzle_id_tube_m": "nozzle_id_tube_m",
"nozzle_id_shell_m": "nozzle_id_shell_m",
"rho_v2_tube_nozzle": "rho_v2_tube_nozzle",
"rho_v2_shell_nozzle": "rho_v2_shell_nozzle",
"dP_shell_simplified_delaware_Pa": "dP_shell_simplified_delaware_Pa",
"dP_shell_kern_Pa": "dP_shell_kern_Pa",
"dP_shell_bell_vs_kern_pct": "dP_shell_bell_vs_kern_pct",
```

---

## Sub-Step 10.7: Step 10 Executor

**File:** `hx_engine/app/steps/step_10_pressure_drops.py`

### Class Definition

```python
class Step10PressureDrops(BaseStep):
    step_id: int = 10
    step_name: str = "Pressure Drops"
    ai_mode: AIModeEnum = AIModeEnum.CONDITIONAL
```

### AI Call Logic

```python
def _should_call_ai(self, state: "DesignState") -> bool:
    if state.in_convergence_loop:
        return False
    return self._conditional_ai_trigger(state)

def _conditional_ai_trigger(self, state: "DesignState") -> bool:
    """Call AI when pressure drop margin is tight (< 15% below limit)."""
    # Will be evaluated after execute() populates outputs
    # Check against hard limits:
    #   dP_tube_Pa > 59,500 (85% of 70,000 Pa = 0.7 bar)
    #   dP_shell_Pa > 119,000 (85% of 140,000 Pa = 1.4 bar)
    #   Either nozzle ρv² > 1895 (85% of 2230)
    # Also trigger if Bell/Kern divergence > 30%
    return False  # Default: no AI needed
```

### Preconditions

Required from Steps 1–9:

- `state.geometry` — full GeometrySpec (shell diameter, tubes, baffles, pitch, passes)
- `state.tube_velocity_m_s` — from Step 7
- `state.Re_tube` — from Step 7
- `state.Re_shell` — from Step 8
- `state.shell_side_fluid` — "hot" or "cold" (from Step 4)
- `state.hot_fluid_props` / `state.cold_fluid_props` — ρ, μ (from Step 3)
- `state.m_dot_hot_kg_s` / `state.m_dot_cold_kg_s` — flow rates (from Step 1)

### Execute Method — Calculation Flow

```
1. Check preconditions → raise CalculationError if missing

2. RESOLVE FLUID SIDES
   - Map shell_side_fluid → which FluidProperties is shell/tube
   - Get ρ, μ, mass flow for each side

3. TUBE-SIDE PRESSURE DROP
   a. Friction factor: churchill_friction_factor(Re_tube, roughness_ratio=0.0)
   b. Friction loss:
      ΔP_f = f × n_passes × L × G² / (2 × ρ × D_i)
      where G = ṁ_tube_per_tube / A_tube_cross_section
   c. Minor losses (Table 5.1):
      α_r = 2×n_p − 1.5 (turbulent) or 3.25×n_p − 1.5 (laminar, Re ≤ 500)
      ΔP_r = α_r × ρ × v² / 2
   d. Nozzle losses:
      - Get nozzle_id from nozzle_table or state override
      - v_nozzle = ṁ / (ρ × A_nozzle)
      - ΔP_n = 1.0 × ρ × v_nozzle² (turbulent, Serth 5.A.3 simplified)
      - ρv²_nozzle for hard rule check
   e. Total: ΔP_tube = ΔP_f + ΔP_r + ΔP_n

4. SHELL-SIDE PRESSURE DROP (Bell's Method)
   a. Call compute_geometry() (reuse from Step 8 — same inputs)
   b. Get j_f from ideal_bank_jf(Re_shell, layout_angle)
   c. Compute F'_b = compute_Fb_pressure(S_b, S_m, N_ss, N_c, Re)
   d. Compute F'_L = compute_FL_pressure(S_tb, S_sb)
   e. Ideal ΔP: ΔP_i = 8 × j_f × N_c × ρ × u_s² / 2 × (μ/μ_w)^(-0.14)
   f. Crossflow: ΔP_c = ΔP_i × F'_b × F'_L
   g. Window: ΔP_w = F'_L × (2 + 0.6×N_cw) × ρ×u_z²/2
   h. End zones: ΔP_e = ΔP_i × (N_c+N_cw)/N_c × F'_b
   i. Total (Eq. 12.37): ΔP_shell = 2×ΔP_e + ΔP_c×(N_b−1) + N_b×ΔP_w
   j. Add shell nozzle losses (same formula as tube nozzles)

5. CROSS-CHECKS
   a. Simplified Delaware (Serth): dP_shell_simplified_delaware_Pa
   b. Kern (Sinnott Eq. 12.26): dP_shell_kern_Pa
   c. Divergence: bell_vs_kern_pct = |Bell - Kern| / Bell × 100

6. WARNINGS
   - If Bell/Kern divergence > 30% → warning
   - If dP margin < 15% → warning (and AI trigger)
   - If tube velocity < 0.8 m/s → "fouling risk" note
   - If tube velocity > 2.5 m/s → "erosion risk" note
   - If nozzle ρv² > 1500 → "impingement plate recommended"

7. RETURN StepResult
   outputs = {
       "dP_tube_Pa": ...,
       "dP_shell_Pa": ...,
       "dP_tube_friction_Pa": ...,
       "dP_tube_minor_Pa": ...,
       "dP_tube_nozzle_Pa": ...,
       "dP_shell_crossflow_Pa": ...,
       "dP_shell_window_Pa": ...,
       "dP_shell_end_Pa": ...,
       "dP_shell_nozzle_Pa": ...,
       "Fb_prime_dP": ...,
       "FL_prime_dP": ...,
       "nozzle_id_tube_m": ...,
       "nozzle_id_shell_m": ...,
       "rho_v2_tube_nozzle": ...,
       "rho_v2_shell_nozzle": ...,
       "dP_shell_simplified_delaware_Pa": ...,
       "dP_shell_kern_Pa": ...,
       "dP_shell_bell_vs_kern_pct": ...,
   }
```

### Wall Viscosity for Shell ΔP

Step 8 already computed μ_wall for the shell-side fluid during its wall-temperature iteration. For Step 10, we need μ_wall again. Options:

1. **Store μ_wall on state** during Step 8 (requires adding field) — cleanest
2. **Approximate** μ_wall ≈ μ_bulk (correction factor ≈ 1.0 for moderate viscosity ratios) — simplest for v1
3. **Re-compute** wall temperature and μ_wall — duplicates Step 8 logic

**Decision:** Use option 2 for initial implementation (set `viscosity_wall_Pa_s = viscosity_Pa_s` as default, add `shell_viscosity_wall_Pa_s` field to DesignState later). The viscosity correction $(μ/μ_w)^{-0.14}$ is a small factor (typically 0.95–1.05 for moderate oils). Step 8 already validated the wall-temperature iteration.

---

## Sub-Step 10.8: Validation Rules

**File:** `hx_engine/app/steps/step_10_rules.py`

### Hard Rules (Layer 2 — AI Cannot Override)

```python
def register_step10_rules() -> None:
    register_rule(10, _rule_dp_tube_within_limit)
    register_rule(10, _rule_dp_shell_within_limit)
    register_rule(10, _rule_nozzle_rho_v2_tube)
    register_rule(10, _rule_nozzle_rho_v2_shell)
    register_rule(10, _rule_dp_tube_positive)
    register_rule(10, _rule_dp_shell_positive)
```

| Rule | Check                        | Hard Limit                            |
| ---- | ---------------------------- | ------------------------------------- |
| R1   | `dP_tube_Pa > 0`             | Must be positive                      |
| R2   | `dP_shell_Pa > 0`            | Must be positive                      |
| R3   | `dP_tube_Pa < 70,000`        | 0.7 bar (Serth/TEMA typical max)      |
| R4   | `dP_shell_Pa < 140,000`      | 1.4 bar (Serth/TEMA typical max)      |
| R5   | `rho_v2_tube_nozzle < 2230`  | TEMA erosion limit (= 1500 lbm/ft·s²) |
| R6   | `rho_v2_shell_nozzle < 2230` | TEMA erosion limit (= 1500 lbm/ft·s²) |

**Note on limits:** The 0.7 bar / 1.4 bar limits are **defaults** from the STEPS_6_16_PLAN. In practice, these should eventually be configurable per-design (user may specify different max allowed ΔP). For now, use these as hard-coded limits matching the plan.

---

## Sub-Step 10.9: Pipeline Wiring

**File:** `hx_engine/app/core/pipeline_runner.py` (modify)

### Changes

1. Add import:

```python
from hx_engine.app.steps.step_10_pressure_drops import Step10PressureDrops
```

2. Add to `PIPELINE_STEPS` list after `Step09OverallU`:

```python
PIPELINE_STEPS = [
    Step01Requirements,
    Step02HeatDuty,
    Step03FluidProperties,
    Step04TEMAGeometry,
    Step05LMTD,
    Step06InitialU,
    Step07TubeSideH,
    Step08ShellSideH,
    Step09OverallU,
    Step10PressureDrops,  # ← NEW
]
```

---

## Sub-Step 10.10: Unit Tests

### Test Files

#### `tests/unit/steps/test_step_10_execute.py`

| Test                                   | Description                                         |
| -------------------------------------- | --------------------------------------------------- |
| `test_precondition_missing_geometry`   | Missing geometry → CalculationError                 |
| `test_precondition_missing_velocity`   | Missing tube_velocity → CalculationError            |
| `test_basic_execution_returns_outputs` | Full mock state → all output keys present           |
| `test_tube_dp_components_sum`          | friction + minor + nozzle = total tube ΔP           |
| `test_shell_dp_components_sum`         | crossflow + window + end + nozzle ≈ total shell ΔP  |
| `test_fluid_side_mapping_hot_shell`    | shell_side_fluid="hot" → hot props used for shell   |
| `test_fluid_side_mapping_cold_shell`   | shell_side_fluid="cold" → cold props used for shell |
| `test_cross_checks_populated`          | kern and simplified delaware values present         |
| `test_warnings_on_tight_margin`        | ΔP at 90% of limit → warning emitted                |
| `test_bell_kern_divergence_warning`    | Divergence > 30% → warning                          |

#### `tests/unit/steps/test_step_10_convergence_skip.py`

| Test                                       | Description                                            |
| ------------------------------------------ | ------------------------------------------------------ |
| `test_ai_skipped_in_convergence_loop`      | `in_convergence_loop=True` → `_should_call_ai()=False` |
| `test_ai_called_outside_loop_tight_margin` | Tight margin → AI triggered                            |
| `test_ai_not_called_comfortable_margin`    | Margin > 15% → no AI                                   |

#### `tests/unit/steps/test_step_10_rules.py`

| Test                           | Description                                  |
| ------------------------------ | -------------------------------------------- |
| `test_dp_tube_positive_pass`   | dP_tube = 50000 → pass                       |
| `test_dp_tube_positive_fail`   | dP_tube = -100 → fail                        |
| `test_dp_tube_over_limit`      | dP_tube = 80000 → fail ("exceeds 0.7 bar")   |
| `test_dp_shell_over_limit`     | dP_shell = 150000 → fail ("exceeds 1.4 bar") |
| `test_nozzle_tube_over_limit`  | ρv² = 2500 → fail                            |
| `test_nozzle_shell_over_limit` | ρv² = 2500 → fail                            |
| `test_all_rules_pass`          | Healthy outputs → all 6 rules pass           |

---

## Key Architecture Decisions

| #   | Decision                                                                  | Rationale                                                                                                                                                                                                            |
| --- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | Use Sinnott/Bell j_f (Figure 12.36 digitized) instead of Taborek fi table | We have the digitized data; Taborek fi coefficients not available. Bell's method is the same underlying physics.                                                                                                     |
| D2  | Churchill for tube-side friction (not Serth Eq. 5.2)                      | Churchill covers all regimes in one equation — critical for convergence loop stability. Serth Eq. 5.2 is turbulent-only.                                                                                             |
| D3  | Wall viscosity approximation (μ_w ≈ μ_bulk) for v1                        | Small correction factor (~±5%). Step 8 already validated wall temp iteration for HTC. Can add exact μ_w later.                                                                                                       |
| D4  | Nozzle diameter from Serth Table 5.3 as default                           | Only used when user doesn't specify. Based on shell size → standard Schedule 40 nozzle.                                                                                                                              |
| D5  | Three cross-check methods for shell ΔP                                    | Bell (primary), Kern (quick check), Simplified Delaware (independent Serth check). Mirrors Step 8's BD/Kern dual approach for HTC.                                                                                   |
| D6  | Detailed ΔP breakdown in outputs                                          | AI needs component-level data (friction/minor/nozzle, crossflow/window/end) to reason about which adjustment would help. Convergence loop needs this to decide fix priority (dP violations → overdesign → velocity). |

---

## File Inventory

### New Files (6)

| File                                                   | Lines (est.) |
| ------------------------------------------------------ | ------------ |
| `hx_engine/app/correlations/churchill_friction.py`     | ~60          |
| `hx_engine/app/data/nozzle_table.py`                   | ~80          |
| `hx_engine/app/correlations/simplified_delaware_dp.py` | ~120         |
| `hx_engine/app/steps/step_10_pressure_drops.py`        | ~300         |
| `hx_engine/app/steps/step_10_rules.py`                 | ~100         |
| `tests/unit/correlations/test_churchill_friction.py`   | ~60          |

### Modified Files (3)

| File                                          | Change                                                                                                  |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `hx_engine/app/correlations/bell_delaware.py` | Add `ideal_bank_jf()`, `compute_Fb_pressure()`, `compute_FL_pressure()`, `shell_side_dP()` (~200 lines) |
| `hx_engine/app/models/design_state.py`        | Add ~18 Optional fields for ΔP outputs                                                                  |
| `hx_engine/app/core/pipeline_runner.py`       | Add import + PIPELINE_STEPS entry + ~18 mapping entries                                                 |

### Test Files (6)

| File                                                     | Tests (est.) |
| -------------------------------------------------------- | ------------ |
| `tests/unit/correlations/test_churchill_friction.py`     | 5            |
| `tests/unit/correlations/test_bell_delaware_dP.py`       | 7            |
| `tests/unit/correlations/test_simplified_delaware_dp.py` | 5            |
| `tests/unit/steps/test_step_10_execute.py`               | 10           |
| `tests/unit/steps/test_step_10_convergence_skip.py`      | 3            |
| `tests/unit/steps/test_step_10_rules.py`                 | 7            |
| `tests/unit/data/test_nozzle_table.py`                   | 5            |

**Total:** ~42 tests

---

## Build Order (Sequential)

```
10.1  churchill_friction.py  +  tests     ← standalone, no deps
10.2  nozzle_table.py        +  tests     ← standalone, no deps
      ↓
10.3  bell_delaware.py additions + tests  ← uses compute_geometry() (existing)
10.4  simplified_delaware_dp.py + tests   ← standalone
      ↓
10.5  DesignState fields                  ← quick edit
10.6  pipeline_runner mapping             ← quick edit
      ↓
10.7  step_10_pressure_drops.py           ← main step, uses 10.1-10.6
10.8  step_10_rules.py                    ← uses StepResult from 10.7
      ↓
10.9  Pipeline wiring                     ← final integration
10.10 Integration tests                   ← verify end-to-end
```

Steps 10.1/10.2 can be built in parallel. Steps 10.3/10.4 can be built in parallel. Steps 10.5/10.6 are quick serial edits. Then 10.7→10.8→10.9→10.10 sequential.

---

## Validation Benchmarks

### Serth Example 5.1 (Second Trial — Final Design)

| Parameter            | Expected Value                          |
| -------------------- | --------------------------------------- |
| Shell                | 19.25-in. (0.489 m), AES                |
| Tubes                | 124 × 1-in. OD, 14 BWG, 14 ft, 4 passes |
| Baffle spacing       | 3.85 in. (0.0978 m)                     |
| Tube-side ΔP_f       | 7.83 psi (54.0 kPa)                     |
| Tube-side ΔP_minor   | 1.66 psi (11.4 kPa)                     |
| Tube-side ΔP_nozzle  | 0.68 psi (4.7 kPa)                      |
| **Tube-side total**  | **10.2 psi (70.3 kPa)**                 |
| Shell-side ΔP_f      | 2.03 psi (14.0 kPa)                     |
| Shell-side ΔP_nozzle | 0.20 psi (1.4 kPa)                      |
| **Shell-side total** | **2.2 psi (15.2 kPa)**                  |

**Acceptance:** Tube-side within ±15% (Churchill vs. Serth Eq. 5.2 will differ slightly). Shell-side within ±30% (Bell vs. Simplified Delaware expected divergence).

### Serth Example 5.2

| Side       | Expected Total     |
| ---------- | ------------------ |
| Tube-side  | 5.1 psi (35.2 kPa) |
| Shell-side | 3.5 psi (24.1 kPa) |
