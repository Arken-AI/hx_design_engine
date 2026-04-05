# External Knowledge Registry — Steps 10–16

**Status:** Reference Document  
**Purpose:** Complete inventory of all externally sourced data required to implement Steps 10–16 of the shell-and-tube heat exchanger simulation pipeline.  
**Depends on:** STEPS_6_16_PLAN.md, ARKEN_MASTER_PLAN.md §6.3, §14

---

## Table of Contents

1. [Step 10: Pressure Drops](#step-10-pressure-drops-tube-side--shell-side)
2. [Step 11: Area Check & Overdesign](#step-11-area-check--overdesign)
3. [Step 12: Convergence Loop](#step-12-convergence-loop-steps-711)
4. [Step 13: Vibration Check](#step-13-vibration-check-5-mechanisms)
5. [Step 14: Mechanical Design](#step-14-mechanical-design-asme-viii-div-1)
6. [Step 15: Cost Estimate](#step-15-cost-estimate-turton--cepci)
7. [Step 16: Final Validation & Confidence](#step-16-final-validation--confidence-score)
8. [Cross-Cutting: Unified Material Properties](#cross-cutting-data-unified-material-properties-module)
9. [Summary: What's Missing vs What Exists](#summary-whats-missing-vs-what-exists)
10. [New Files to Create](#new-files-to-create)
11. [Library Coverage](#what-thermofluidsht-libraries-cover)

---

## Step 10: Pressure Drops (Tube-Side & Shell-Side)

### 1. Constants & Fixed Values

| Item                                           | Value                                 | Source                                    | Format            | Covered?                                                                         |
| ---------------------------------------------- | ------------------------------------- | ----------------------------------------- | ----------------- | -------------------------------------------------------------------------------- |
| Return loss coefficient (tube-side)            | 4.0 velocity heads per pass           | Kern (1950), Perry's §6                   | `float` constant  | **Custom** — hardcode                                                            |
| Nozzle ρv² limit                               | 2230 kg/m·s²                          | API 660 / TEMA RCB-4.6                    | `float` constant  | **Custom**                                                                       |
| dP_shell hard limit                            | 1.4 bar (140 kPa)                     | TEMA RCB-4.6, typical industrial practice | `float` constant  | **Custom**                                                                       |
| dP_tube hard limit                             | 0.7 bar (70 kPa)                      | TEMA RCB-4.6, typical industrial practice | `float` constant  | **Custom**                                                                       |
| Gravitational acceleration                     | 9.81 m/s²                             | —                                         | `float` constant  | stdlib / hardcode                                                                |
| Entrance/exit loss coefficients (tube nozzles) | K_in ≈ 0.5, K_out ≈ 1.0 (sharp-edged) | Idelchik (1966) or Perry's §6             | `float` constants | **Custom** — could use `fluids.fittings` but simpler to hardcode standard values |

### 2. Lookup Tables

| Item                                             | Structure                                                                         | Source                                              | Format                                      | Covered?                                           |
| ------------------------------------------------ | --------------------------------------------------------------------------------- | --------------------------------------------------- | ------------------------------------------- | -------------------------------------------------- |
| Shell-side nozzle pressure loss coefficients     | By nozzle type (impingement plate present/absent, nozzle-to-shell diameter ratio) | TEMA RCB-4.6.3, Sinnott Table 12.40                 | `dict` keyed by configuration               | **Custom**                                         |
| Tube-side entrance/exit loss coefficients vs. Re | K_c and K_e as function of Re and tube-pass geometry                              | Kays & London (1984) Fig. 5-2, or Perry's Fig. 6-16 | Interpolation table or simplified constants | **Custom** — can simplify to constants for Phase 1 |

### 3. Charts & Graphical Correlations

| Item                                                         | Description                                                                          | Source                                                | Format                                                                        | Covered?                                                                                                                                                                                          |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------ | ----------------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Bell-Delaware shell-side dP correction factors R_l, R_b, R_s | Same geometric corrections as J-factors but for pressure drop; separate coefficients | Taborek (1983) HEDH §3.3.10, Serth Ch. 5              | Hardcoded algebraic expressions (same geometry as bell_delaware.py J-factors) | **Partially covered** — the J-factor geometry from `bell_delaware.py` provides the underlying areas (S_m, S_tb, S_sb, S_w), but the R-factor formulas are distinct and need custom implementation |
| Tube-side friction factor chart (all regimes)                | Moody chart equivalent — laminar, transition, turbulent in a single equation         | Churchill (1977) — Eq. published in AIChE J. 23(1):91 | Single algebraic formula (no interpolation needed)                            | **`fluids` library has `fluids.friction.friction_factor_Churchill_1977()`** — but recommend custom for zero-dependency and auditability                                                           |

### 4. Empirical Correlations & Equations

| Item                                    | Equation                                                                                                                      | Source                                                        | Coefficients                                                                                                                                                           | Covered?                                                                                                              |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| **Churchill friction factor**           | `f = 8 × [(8/Re)^12 + (A+B)^(-1.5)]^(1/12)` where `A = [2.457 × ln(1/((7/Re)^0.9 + 0.27(ε/D)))]^16`, `B = (37530/Re)^16`      | Churchill, S.W. (1977) AIChE J. 23(1):91-92                   | Self-contained — constants embedded in formula                                                                                                                         | **`fluids` library** has it; recommend custom `churchill_friction.py` for auditability                                |
| **Bell-Delaware shell dP**              | `ΔP_s = ΔP_ideal × R_b × R_l + ΔP_w × R_l + ΔP_e` (inlet/outlet baffle spans)                                                 | Taborek (1983) HEDH §3.3.10; Serth (2007) Ch. 5 Eqs. 5.7-5.14 | R_b: same C_bh constants as J_b (1.35 for Re<100, 1.25 otherwise); R_l: exp coefficients differ from J_l (~1.33, −0.8 vs −2.2) — **must verify from Taborek Table 12** | **Custom** — not in any library                                                                                       |
| **Ideal crossflow dP per baffle space** | `ΔP_ideal = 2 × f_k × N_tc × (μ_s/μ_w)^0.14 × ρ × u_s² / 2` where `f_k` from Taborek Table 11 (analogous to Table 10 for j_i) | Taborek (1983) HEDH Table 11                                  | ~20 rows: 4 layout angles × 5 Re ranges, each with (b1, b2, b3, b4) coefficients                                                                                       | **Custom** — critically, Table 11 (friction) is different from Table 10 (heat transfer) already in `bell_delaware.py` |
| **Window dP**                           | `ΔP_w = (2 + 0.6 × N_tcw) × ρ × u_w² / 2`                                                                                     | Taborek (1983) HEDH §3.3.10.7                                 | 2.0 (constant), 0.6 (empirical multiplier), N_tcw = tube rows in window                                                                                                | **Custom**                                                                                                            |
| **Tube-side dP (Darcy-Weisbach)**       | `ΔP_t = 4f × (L/d_i) × (ρv²/2) × N_p + 4N_p × (ρv²/2)`                                                                        | Standard fluid mechanics; Serth Eq. 5.1                       | 4.0 velocity-head return loss per pass (Kern convention) — some references use 2.5                                                                                     | **Custom** — straightforward                                                                                          |

### 5. Standards & Code References

| Standard       | Section             | Governs                                                      |
| -------------- | ------------------- | ------------------------------------------------------------ |
| TEMA 10th Ed.  | RCB-4.6             | Pressure drop limits, nozzle ρv² limit                       |
| API 660 (2015) | §7.1.9              | Shell-side dP allowable for air-cooled/shell-tube            |
| ASME B31.3     | § (velocity limits) | Piping velocity guidelines (informational for nozzle checks) |

### Critical Data Gap: Taborek Table 11 (Friction Coefficients)

This is the **single most important missing dataset** for Step 10. The existing `bell_delaware.py` already has Taborek Table 10 (j-factor coefficients) in `_JI_COEFFS`. An analogous `_FI_COEFFS` table for friction is needed — same structure (layout angle → Re-range → b1,b2,b3,b4), different numerical values.

**Source:** Taborek, J. (1983). "Shell-and-Tube Heat Exchangers: Single-Phase Flow." _Heat Exchanger Design Handbook (HEDH)_, Section 3.3, Hemisphere Publishing. Table 11.

**Alternative sources:** Serth & Lestina (2014), _Process Heat Transfer_, 2nd Ed., Table 5.4 reproduces the same coefficients. Thulukkanam (2013), _Heat Exchanger Design Handbook_, 2nd Ed. also tabulates them.

---

## Step 11: Area Check & Overdesign

### 1. Constants & Fixed Values

| Item                    | Value                              | Source                             | Format                                 | Covered?   |
| ----------------------- | ---------------------------------- | ---------------------------------- | -------------------------------------- | ---------- |
| Overdesign target range | 10–25% (ideal), 0–40% (acceptable) | Industrial practice, Sinnott §12.8 | `float` constants (min/max thresholds) | **Custom** |
| Hard fail threshold     | overdesign < 0%                    | ARKEN_MASTER_PLAN §6.3             | `float` constant                       | **Custom** |

### 2–5. No Additional External Data Needed

Step 11 is purely arithmetic:

- `A_req = Q / (U_calc × F × LMTD)`
- `A_prov = N_t × π × d_o × L`
- `overdesign = (A_prov − A_req) / A_req × 100%`

All inputs come from prior steps.

---

## Step 12: Convergence Loop (Steps 7→11)

### 1. Constants & Fixed Values

| Item                           | Value                            | Source                              | Format           | Covered?   |
| ------------------------------ | -------------------------------- | ----------------------------------- | ---------------- | ---------- |
| Max iterations                 | 20                               | Engineering judgment / ARKEN plan   | `int` constant   | **Custom** |
| ΔU convergence criterion       | < 1% relative change             | Standard iterative practice         | `float` constant | **Custom** |
| Overdesign convergence band    | 10–25%                           | Same as Step 11                     | `float` range    | **Custom** |
| Velocity acceptable range      | 0.8–2.5 m/s (tube-side, liquids) | TEMA / industrial practice          | `float` range    | **Custom** |
| Damping factor for oscillation | 0.5–0.7 (under-relaxation)       | Numerical methods standard practice | `float` constant | **Custom** |

### 2. Geometry Adjustment Heuristics

| Adjustment              | When                    | How                                                                                            | Source                                       |
| ----------------------- | ----------------------- | ---------------------------------------------------------------------------------------------- | -------------------------------------------- |
| Increase tube length    | overdesign < 10%        | Step up through standard lengths: 2.438, 3.048, 3.658, 4.877, 6.096 m (8', 10', 12', 16', 20') | TEMA Table D-7                               |
| Decrease tube length    | overdesign > 40%        | Step down                                                                                      | Same                                         |
| Add/remove tube passes  | Velocity out of range   | Double or halve passes (1→2→4→6)                                                               | TEMA / Sinnott §12.9                         |
| Increase baffle spacing | dP_shell too high       | Increase by 10–20% per iteration                                                               | Bell-Delaware practice                       |
| Decrease baffle spacing | h_shell too low         | Decrease by 10–20% per iteration, floor at 0.2 × shell_id                                      | TEMA RCB-4.5 minimum                         |
| Change shell diameter   | Geometry can't converge | Step to next standard shell size                                                               | TEMA Table D-7 (already in `tema_tables.py`) |

### Standard Tube Lengths

| Length (m) | Length (ft) | Source         |
| ---------- | ----------- | -------------- |
| 2.438      | 8           | TEMA Table D-7 |
| 3.048      | 10          | TEMA Table D-7 |
| 3.658      | 12          | TEMA Table D-7 |
| 4.877      | 16          | TEMA Table D-7 |
| 6.096      | 20          | TEMA Table D-7 |

---

## Step 13: Vibration Check (5 Mechanisms)

> This is the **data-heaviest step** after Bell-Delaware. Five independent mechanisms, each with its own correlation set.

### 1. Constants & Fixed Values

| Item                                      | Value                                                                                               | Source                                                              | Format                          | Covered?                                                           |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ------------------------------- | ------------------------------------------------------------------ |
| Connors safety margin                     | u_cross/u_crit < 0.5 (50% margin)                                                                   | TEMA 10th Ed. §V-5, Pettigrew & Taylor (1991) conservative practice | `float` constant                | **Custom**                                                         |
| Inlet/outlet span multiplier              | 1.5× central baffle span                                                                            | TEMA §V-3.2.1 — unsupported spans at ends are longer                | `float` constant                | **Custom**                                                         |
| Damping coefficient (single-phase liquid) | ζ ≈ 0.03–0.05 (typical)                                                                             | Pettigrew & Taylor (2003), TEMA Table V-5.1                         | `float` or lookup by fluid type | **Custom**                                                         |
| Speed of sound in shell-side fluid        | Calculated: `c = √(1/(ρ × κ))` where κ = isentropic compressibility; or tabulated for common fluids | Perry's Table 2-191 / CoolProp `speed_of_sound()`                   | Calculated or lookup            | **CoolProp** can provide this for pure fluids; custom for mixtures |
| Tube material properties for vibration    | E (Young's modulus), I (moment of inertia), ρ_tube (metal density)                                  | ASME II Part D / Perry's Table 25-6                                 | Lookup by material              | **Custom** — see material properties table below                   |

### 2. Lookup Tables

| Item                                                 | Structure                                                          | Source                                                                  | Format                                                                                                        | Covered?                           |
| ---------------------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| **Connors constant (C_n)**                           | By tube layout angle and pitch ratio range                         | Connors (1978), Pettigrew & Taylor (1991), TEMA Table V-5.2             | `dict[layout_angle][pitch_ratio_range]` → C_n; typical values: triangular 30° = 2.8–3.3, square 90° = 3.3–3.8 | **Custom**                         |
| **End condition factor (C_e)** for natural frequency | By tube support condition (both fixed, one fixed one pinned, etc.) | Blevins (1990) Table 7-1, TEMA Table V-4.1                              | `dict[support_type]` → (λ₁, λ₂, …) eigenvalues; typical C_e for both-fixed = 22.37                            | **Custom**                         |
| **Strouhal number**                                  | By tube layout, pitch ratio, Re range                              | Žukauskas & Katinas (1988), or simplified: St ≈ 0.2 for most tube banks | `dict` or constant 0.2 ± deviation by layout                                                                  | **Custom**                         |
| **Tube material properties**                         | E (GPa), ρ (kg/m³) by material name                                | ASME II Part D, Perry's Table 25-6                                      | `dict[material]` → (E, ρ, ν)                                                                                  | **Custom** — needs new data module |

### Tube Material Properties Table (Needed for Vibration Natural Frequency)

| Material               | E (GPa) | ρ (kg/m³) | Source               |
| ---------------------- | ------- | --------- | -------------------- |
| Carbon steel (SA-179)  | 200     | 7850      | ASME II-D Table TM-1 |
| SS 304 (SA-213 TP304)  | 193     | 8000      | ASME II-D Table TM-1 |
| SS 316 (SA-213 TP316)  | 193     | 8000      | ASME II-D Table TM-1 |
| Copper (SB-111 C12200) | 117     | 8940      | ASME II-D            |
| Titanium Gr 2 (SB-338) | 105     | 4510      | ASME II-D            |
| Inconel 600 (SB-163)   | 214     | 8470      | ASME II-D            |
| Monel 400 (SB-163)     | 179     | 8830      | ASME II-D            |
| Duplex 2205            | 200     | 7800      | ASME II-D            |

> **Note:** This table overlaps with `k_w` values in Step 9 (`step_09_overall_u.py`). Consider a unified `material_properties.py` data module with thermal conductivity, Young's modulus, density, allowable stress, and cost factor per material.

### 3. Charts & Graphical Correlations

| Item                                   | Description                                                                                          | Source                                                   | Format                                                                                                               | Covered?                                                                                                           |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| **Connors stability map**              | Critical velocity ratio vs. mass-damping parameter (Scruton number)                                  | Connors (1978) Fig. 3, Pettigrew & Taylor (1991) Fig. 12 | Digitized curve: log-log piecewise fit or simplified power law `u_crit = C_n × f_n × d_o × (m × δ / (ρ × d_o²))^0.5` | **Custom** — the simplified Connors equation is standard; no digitization needed if using the single-equation form |
| **Acoustic resonance frequency chart** | f_acoustic vs. shell diameter and speed of sound, with tube bank blockage correction (Parker factor) | Parker (1978), Blevins (1990) Ch. 10, TEMA §V-6          | `f_n = n × c / (2 × D_s)` corrected by `α = 1/√(1 − σ²)` where σ = tube bank solidity                                | **Custom** — algebraic, no digitization                                                                            |

### 4. Empirical Correlations & Equations

| Item                                             | Equation                                                                                                                  | Source                                               | Coefficients                                                                                     | Covered?   |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ---------- |
| **Tube natural frequency**                       | `f_n = (λ_n² / (2π × L_span²)) × √(EI / m_L)` where m_L = mass per unit length (tube + fluid inside + added mass outside) | Blevins (1990) Eq. 7.30, TEMA §V-4                   | λ_n = eigenvalue from end-condition table (first mode: 22.37 for fixed-fixed)                    | **Custom** |
| **Added (hydrodynamic) mass**                    | `m_add = C_m × ρ_s × (π × d_o² / 4)` where C_m depends on pitch/diameter ratio                                            | Blevins (1990) Table 10.1, Žukauskas (1988)          | `C_m ≈ ((D_e/d_o)² + 1) / ((D_e/d_o)² − 1)` for triangular pitch; D_e = equivalent cell diameter | **Custom** |
| **Connors criterion (fluidelastic instability)** | `u_crit = C_n × f_n × d_o × (2π × ζ × m_total / (ρ_s × d_o²))^a` with a = 0.5 (Connors) or 0.4–0.5 (Pettigrew)            | Connors (1978), updated by Pettigrew & Taylor (2003) | C_n: 2.8–3.8 by layout; a: 0.5 (classic) or 0.4 (conservative)                                   | **Custom** |
| **Vortex shedding frequency**                    | `f_vs = St × u_cross / d_o` where St ≈ 0.2 (isolated cylinder) or layout-corrected                                        | Žukauskas & Katinas (1988), Blevins (1990) Ch. 3     | St tabulated by layout and pitch ratio — typically 0.18–0.22                                     | **Custom** |
| **Lock-in criterion**                            | Resonance if `0.8 × f_n < f_vs < 1.2 × f_n` (within ±20% band)                                                            | Blevins (1990) §3.7, TEMA §V-5.3                     | 0.8 and 1.2 multipliers                                                                          | **Custom** |
| **Turbulent buffeting frequency**                | `f_tb = (u_cross / d_o) × (3.05 × [1 − d_o/P_t]² + 0.28)` (Owen correlation)                                              | Owen (1965), quoted in TEMA §V-5.4                   | 3.05 and 0.28 empirical constants                                                                | **Custom** |
| **Acoustic resonance frequency**                 | `f_ac,n = n × c / (2 × D_eff)` where `D_eff = D_s / α`, α = Parker correction                                             | Parker (1978), TEMA §V-6                             | n = mode number (1, 2, 3…); α from tube bank blockage                                            | **Custom** |

### 5. Standards & Code References

| Standard       | Section                                       | Governs                                      |
| -------------- | --------------------------------------------- | -------------------------------------------- |
| TEMA 10th Ed.  | Section V (entire — "Flow-Induced Vibration") | Master reference for all 5 mechanisms        |
| TEMA 10th Ed.  | Table V-4.1                                   | End-condition eigenvalues                    |
| TEMA 10th Ed.  | Table V-5.2                                   | Connors constants by layout                  |
| ASME II Part D | Table TM-1                                    | Tube material elastic modulus at temperature |
| API 660 (2015) | §5.10                                         | Vibration avoidance requirements             |

---

## Step 14: Mechanical Design (ASME VIII Div 1)

### 1. Constants & Fixed Values

| Item                           | Value                                                              | Source                              | Format                           | Covered?   |
| ------------------------------ | ------------------------------------------------------------------ | ----------------------------------- | -------------------------------- | ---------- |
| Corrosion allowance (default)  | 3.175 mm (1/8") for carbon steel; 0 for corrosion-resistant alloys | ASME VIII-1 UG-25, company practice | `dict[material_class]` → float   | **Custom** |
| Weld joint efficiency (E)      | 0.85 (spot XRT), 1.0 (full XRT), 0.7 (no XRT)                      | ASME VIII-1 UW-12 Table             | `dict[examination_type]` → float | **Custom** |
| Thermal expansion coefficients | By material and temperature range (mm/m/°C)                        | ASME II Part D Table TE-1           | `dict[material][temp_range]` → α | **Custom** |
| Expansion tolerance (default)  | ±3 mm differential growth before requiring floating head           | Industrial practice, HEDH §4.2      | `float` constant                 | **Custom** |
| Design pressure margin         | 10% above operating pressure or 1.75 bar, whichever is greater     | ASME VIII-1 UG-21                   | arithmetic rule                  | **Custom** |
| Ligament efficiency            | `η = (P_t − d_o) / P_t` (for drilled plates)                       | ASME VIII-1 UG-53, TEMA RCB-7.131   | formula                          | **Custom** |

### 2. Lookup Tables

| Item                                      | Structure                                | Source                                                     | Format                                          | Covered?                                                                                  |
| ----------------------------------------- | ---------------------------------------- | ---------------------------------------------------------- | ----------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **Allowable stress at temperature (S)**   | By material grade and design temperature | ASME II Part D, Table 1A (ferrous), Table 1B (non-ferrous) | `dict[material][temp_C]` → S_MPa (interpolated) | **Custom** — this is a large dataset; consider a simplified table for common HX materials |
| **Standard shell pipe/plate thicknesses** | Available commercial thicknesses in mm   | ASME B36.10M (pipe), plate per mill standards              | `list[float]` of standard wall thicknesses      | **Custom**                                                                                |

### Allowable Stress Table (Simplified for Phase 1 — Common HX Tube/Shell Materials)

| Material      | Grade           | 100°C | 150°C | 200°C | 250°C | 300°C | Source             |
| ------------- | --------------- | ----- | ----- | ----- | ----- | ----- | ------------------ |
| Carbon steel  | SA-516 Gr 70    | 138   | 138   | 138   | 138   | 138   | ASME II-D Table 1A |
| Carbon steel  | SA-179 (tube)   | 83    | 83    | 83    | 83    | 83    | ASME II-D Table 1A |
| SS 304        | SA-240 / SA-213 | 115   | 110   | 103   | 97    | 93    | ASME II-D Table 1A |
| SS 316        | SA-240 / SA-213 | 115   | 110   | 103   | 100   | 95    | ASME II-D Table 1A |
| Titanium Gr 2 | SB-265 / SB-338 | 57    | 44    | 34    | 28    | 23    | ASME II-D Table 1B |
| Copper        | SB-111 C12200   | 41    | 28    | —     | —     | —     | ASME II-D Table 1B |
| Duplex 2205   | SA-240          | 207   | 190   | 176   | 163   | 161   | ASME II-D Table 1A |

_(Values in MPa; round numbers from ASME tables — verify exact values from the edition used)_

### Thermal Expansion Coefficients (Mean, from 20°C)

| Material      | α at 100°C | α at 200°C | α at 300°C | Units   | Source               |
| ------------- | ---------- | ---------- | ---------- | ------- | -------------------- |
| Carbon steel  | 11.7       | 12.1       | 12.7       | μm/m/°C | ASME II-D Table TE-1 |
| SS 304        | 16.0       | 16.4       | 16.9       | μm/m/°C | ASME II-D Table TE-1 |
| SS 316        | 15.9       | 16.3       | 16.8       | μm/m/°C | ASME II-D Table TE-1 |
| Titanium Gr 2 | 8.6        | 8.9        | 9.2        | μm/m/°C | ASME II-D Table TE-1 |
| Copper        | 16.9       | 17.2       | 17.5       | μm/m/°C | ASME II-D Table TE-1 |

### 3. Charts & Graphical Correlations

None required — ASME VIII Div 1 is formula-based for cylindrical shells and tubes.

### 4. Empirical Correlations & Equations

| Item                                          | Equation                                                | Source                                                                                                     | Coefficients                                                                                                | Covered?                                                                 |
| --------------------------------------------- | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | -------------------------------------------- | ---------- |
| **Cylindrical shell under internal pressure** | `t_min = (P × R) / (S × E − 0.6P) + CA`                 | ASME VIII-1 UG-27(c)(1)                                                                                    | P = design pressure, R = inner radius, S = allowable stress, E = joint efficiency, CA = corrosion allowance | **Custom**                                                               |
| **Tube minimum wall under external pressure** | `t_min = (P_ext × d_o) / (2(S × E + 0.4 × P_ext)) + CA` | ASME VIII-1 UG-28 (simplified for thin tubes — full UG-28 requires iterative chart lookup for L/D and D/t) | Same variables                                                                                              | **Custom** — simplified form acceptable for Phase 1; full UG-28 deferred |
| **Thermal expansion differential**            | `ΔL = L ×                                               | α_tube(T_tube,avg) − α_shell(T_shell,avg)                                                                  | × (T_op − T_install)`                                                                                       | Standard thermal mechanics                                               | α from table above; T_install typically 20°C | **Custom** |
| **TEMA minimum shell thickness**              | Lookup by shell diameter                                | TEMA Table R-3.13                                                                                          | diameter → min wall mm                                                                                      | **Custom**                                                               |

### 5. Standards & Code References

| Standard               | Section      | Governs                                             |
| ---------------------- | ------------ | --------------------------------------------------- |
| ASME VIII Div 1 (2023) | UG-27        | Cylindrical shell thickness under internal pressure |
| ASME VIII Div 1 (2023) | UG-28        | Shells under external pressure                      |
| ASME VIII Div 1 (2023) | UG-25        | Corrosion allowance                                 |
| ASME VIII Div 1 (2023) | UW-12        | Joint efficiency factors                            |
| ASME II Part D (2023)  | Table 1A, 1B | Allowable stress at temperature                     |
| ASME II Part D (2023)  | Table TE-1   | Thermal expansion coefficients                      |
| TEMA 10th Ed.          | Table R-3.13 | Minimum shell wall thickness                        |
| TEMA 10th Ed.          | RCB-7.131    | Ligament efficiency for tubesheets                  |

---

## Step 15: Cost Estimate (Turton + CEPCI)

### 1. Constants & Fixed Values

| Item               | Value                                                                        | Source                                    | Format                                      | Covered?                                                     |
| ------------------ | ---------------------------------------------------------------------------- | ----------------------------------------- | ------------------------------------------- | ------------------------------------------------------------ |
| CEPCI index (2026) | 816.0                                                                        | Chemical Engineering Magazine (projected) | `dict` with `value`, `year`, `last_updated` | **Custom** — `cost_indices.py` with 90-day staleness warning |
| Turton base CEPCI  | 397 (2001 base year for 3rd Ed.) or 567 (2013 base for updated correlations) | Turton et al. (2018) Table 8.2 footnote   | `float` constant                            | **Custom**                                                   |

### 2. Lookup Tables

| Item                                 | Structure                   | Source                                      | Format                             | Covered?   |
| ------------------------------------ | --------------------------- | ------------------------------------------- | ---------------------------------- | ---------- |
| **Material cost factors (F_M)**      | By material of construction | Turton et al. (2018) Table 8.4 or Fig. 8.14 | `dict[material]` → F_M             | **Custom** |
| **Pressure correction factor (F_P)** | By design pressure range    | Turton et al. (2018) Table 8.5/Eq. 8.6      | Polynomial fit (log-log) or `dict` | **Custom** |

### Material Cost Factors (Turton, Shell-and-Tube HX)

| Shell / Tube Material | F_M  | Source           |
| --------------------- | ---- | ---------------- |
| CS / CS               | 1.0  | Turton Table 8.4 |
| CS / SS 304           | 1.75 | Turton Table 8.4 |
| CS / SS 316           | 2.1  | Turton Table 8.4 |
| CS / Copper           | 1.55 | Turton Table 8.4 |
| CS / Titanium         | 5.2  | Turton Table 8.4 |
| CS / Inconel          | 3.5  | Turton Table 8.4 |
| CS / Monel            | 3.2  | Turton Table 8.4 |
| SS 304 / SS 304       | 2.7  | Turton Table 8.4 |
| SS 316 / SS 316       | 3.3  | Turton Table 8.4 |

_(Values are approximate; verify from Turton 4th or 5th Edition)_

### 3. Charts & Graphical Correlations

| Item                              | Description                                | Source                         | Format                                                                                                | Covered?                            |
| --------------------------------- | ------------------------------------------ | ------------------------------ | ----------------------------------------------------------------------------------------------------- | ----------------------------------- |
| **Bare-module cost factor chart** | C_BM = C_p × F_BM where F_BM = f(F_M, F_P) | Turton et al. (2018) Fig. 8.14 | Polynomial coefficients (digitized) — typically `log10(C_p⁰) = K₁ + K₂ × log10(A) + K₃ × [log10(A)]²` | **Custom** — see correlations below |

### 4. Empirical Correlations & Equations

| Item                             | Equation                                                                                | Source                                  | Coefficients                                                                                                                                       | Covered?                      |
| -------------------------------- | --------------------------------------------------------------------------------------- | --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| **Base purchased cost (Turton)** | `log10(C_p⁰) = K₁ + K₂ × log10(A) + K₃ × [log10(A)]²` where A = heat transfer area (m²) | Turton et al. (2018) Table 8.2          | For floating head: K₁ = 4.8306, K₂ = −0.8509, K₃ = 0.3187; for fixed tube sheet: K₁ = 4.3247, K₂ = −0.3030, K₃ = 0.1634 (verify from edition used) | **Custom** — `turton_cost.py` |
| **Pressure factor**              | `log10(F_P) = C₁ + C₂ × log10(P) + C₃ × [log10(P)]²`                                    | Turton et al. (2018) Eq. 8.6, Table 8.5 | HX-specific C₁, C₂, C₃ by equipment type; for shell-and-tube: tube-side P only (shell-side is atmospheric in many correlations)                    | **Custom**                    |
| **CEPCI adjustment**             | `C_2026 = C_base × (CEPCI_2026 / CEPCI_base)`                                           | Standard CE cost escalation             | Ratio of indices                                                                                                                                   | **Custom**                    |
| **Bare-module cost**             | `C_BM = C_p⁰ × F_BM` where `F_BM = B₁ + B₂ × F_M × F_P`                                 | Turton et al. (2018) Eq. 8.3            | B₁ = 1.63, B₂ = 1.66 for shell-and-tube HX (verify)                                                                                                | **Custom**                    |

### 5. Standards & Code References

| Standard                                                                            | Section      | Governs                               |
| ----------------------------------------------------------------------------------- | ------------ | ------------------------------------- |
| Turton et al. (2018) "Analysis, Synthesis and Design of Chemical Processes" 5th Ed. | Chapter 8    | Equipment cost estimation methodology |
| Chemical Engineering Magazine                                                       | Annual CEPCI | Cost index for inflation adjustment   |

---

## Step 16: Final Validation & Confidence Score

### 1. Constants & Fixed Values

| Item                         | Value                                                                              | Source                | Format                   | Covered?   |
| ---------------------------- | ---------------------------------------------------------------------------------- | --------------------- | ------------------------ | ---------- |
| Confidence component weights | 0.25 each (4 components)                                                           | ARKEN_MASTER_PLAN §16 | `dict[component]` → 0.25 | **Custom** |
| Supermemory save threshold   | confidence ≥ 0.75                                                                  | ARKEN_MASTER_PLAN §16 | `float` constant         | **Custom** |
| Component definitions        | geometry_convergence, ai_agreement_rate, supermemory_similarity, validation_passes | ARKEN_MASTER_PLAN §16 | `list[str]`              | **Custom** |

### 2–5. No External Data Needed

Step 16 is an aggregation step. All inputs are internal (step records, AI review history, convergence metrics). The only external interaction is the Supermemory API call to store the design if confidence ≥ 0.75.

---

## Cross-Cutting Data: Unified Material Properties Module

Multiple steps need material data (`k_w` in Step 9, E and ρ in Step 13, S and α in Step 14, F_M in Step 15). A single `data/material_properties.py` would consolidate:

| Property                   | Steps Using It | Current Location                     |
| -------------------------- | -------------- | ------------------------------------ |
| Thermal conductivity (k_w) | 9              | `step_09_overall_u.py` (inline dict) |
| Young's modulus (E)        | 13             | — (missing)                          |
| Density (ρ_metal)          | 13             | — (missing)                          |
| Allowable stress (S at T)  | 14             | — (missing)                          |
| Thermal expansion (α at T) | 14             | — (missing)                          |
| Cost factor (F_M)          | 15             | — (missing)                          |

### Recommended Structure

```python
MATERIALS = {
    "carbon_steel": {
        "k_w": 50.0,          # W/m·K
        "E": 200e9,           # Pa
        "rho": 7850,          # kg/m³
        "alpha": {100: 11.7e-6, 200: 12.1e-6, 300: 12.7e-6},  # 1/°C
        "S": {100: 138e6, 200: 138e6, 300: 138e6},             # Pa
        "F_M": 1.0,
    },
    "ss_304": {
        "k_w": 16.2,
        "E": 193e9,
        "rho": 8000,
        "alpha": {100: 16.0e-6, 200: 16.4e-6, 300: 16.9e-6},
        "S": {100: 115e6, 200: 103e6, 300: 93e6},
        "F_M": 1.75,   # CS shell / SS 304 tubes
    },
    "ss_316": {
        "k_w": 14.6,
        "E": 193e9,
        "rho": 8000,
        "alpha": {100: 15.9e-6, 200: 16.3e-6, 300: 16.8e-6},
        "S": {100: 115e6, 200: 103e6, 300: 95e6},
        "F_M": 2.1,
    },
    "copper": {
        "k_w": 385.0,
        "E": 117e9,
        "rho": 8940,
        "alpha": {100: 16.9e-6, 200: 17.2e-6},
        "S": {100: 41e6},
        "F_M": 1.55,
    },
    "titanium_gr2": {
        "k_w": 21.9,
        "E": 105e9,
        "rho": 4510,
        "alpha": {100: 8.6e-6, 200: 8.9e-6, 300: 9.2e-6},
        "S": {100: 57e6, 200: 34e6, 300: 23e6},
        "F_M": 5.2,
    },
    "inconel_600": {
        "k_w": 14.9,
        "E": 214e9,
        "rho": 8470,
        "alpha": {},  # fill from ASME II-D
        "S": {},       # fill from ASME II-D
        "F_M": 3.5,
    },
    "monel_400": {
        "k_w": 21.8,
        "E": 179e9,
        "rho": 8830,
        "alpha": {},
        "S": {},
        "F_M": 3.2,
    },
    "duplex_2205": {
        "k_w": 19.0,
        "E": 200e9,
        "rho": 7800,
        "alpha": {},
        "S": {100: 207e6, 200: 176e6, 300: 161e6},
        "F_M": 2.7,   # approximate
    },
}
```

---

## Summary: What's Missing vs What Exists

| Data Item                                      | Exists?                                                                    | Needed By             | Priority     |
| ---------------------------------------------- | -------------------------------------------------------------------------- | --------------------- | ------------ |
| Churchill friction correlation                 | ❌ No (`fluids` lib has it, recommend custom)                              | Step 10               | **High**     |
| Taborek Table 11 (friction coefficients, f_i)  | ❌ No — **critical gap**                                                   | Step 10 (shell dP)    | **Critical** |
| Bell-Delaware R-factors (R_l, R_b, R_s) for dP | ❌ Partially (geometry from J-factors reusable, but R coefficients differ) | Step 10 (shell dP)    | **Critical** |
| Standard tube lengths                          | ⚠️ Implicitly in TEMA tables                                               | Step 12               | Low          |
| Connors constants (C_n) by layout              | ❌ No                                                                      | Step 13               | **High**     |
| End-condition eigenvalues (λ_n)                | ❌ No                                                                      | Step 13               | **High**     |
| Strouhal numbers by layout                     | ❌ No                                                                      | Step 13               | **High**     |
| Added mass coefficients (C_m)                  | ❌ No                                                                      | Step 13               | **High**     |
| Tube E, ρ (material properties)                | ❌ No (k_w exists in Step 9)                                               | Step 13, 14           | **High**     |
| ASME allowable stress at temperature           | ❌ No                                                                      | Step 14               | **High**     |
| Thermal expansion coefficients                 | ❌ No                                                                      | Step 14               | **High**     |
| Weld joint efficiency factors                  | ❌ No                                                                      | Step 14               | Medium       |
| Corrosion allowance by material                | ❌ No                                                                      | Step 14               | Medium       |
| TEMA min shell thickness table                 | ❌ No                                                                      | Step 14               | Medium       |
| Turton K₁, K₂, K₃ coefficients                 | ❌ No                                                                      | Step 15               | **High**     |
| Turton B₁, B₂ bare-module factors              | ❌ No                                                                      | Step 15               | **High**     |
| Material cost factors (F_M)                    | ❌ No                                                                      | Step 15               | **High**     |
| Pressure correction coefficients               | ❌ No                                                                      | Step 15               | **High**     |
| CEPCI index                                    | ❌ No                                                                      | Step 15               | **High**     |
| TEMA clearances (shell-baffle, tube-baffle)    | ✅ `tema_tables.py`                                                        | Step 10 (via BD)      | —            |
| BWG tube dimensions                            | ✅ `bwg_gauge.py`                                                          | Step 14               | —            |
| Fouling factors                                | ✅ `fouling_factors.py`                                                    | Step 9 (already used) | —            |
| U assumption ranges                            | ✅ `u_assumptions.py`                                                      | Step 6                | —            |
| Bell-Delaware j-factors (Taborek Table 10)     | ✅ `bell_delaware.py`                                                      | Step 8                | —            |
| Gnielinski/Hausen/Petukhov                     | ✅ `gnielinski.py`                                                         | Step 7                | —            |

---

## New Files to Create

| File                                                              | Contents                                                                            | Est. Size  |
| ----------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ---------- |
| `correlations/churchill_friction.py`                              | Single equation, all flow regimes                                                   | ~40 lines  |
| `correlations/bell_delaware_dp.py` (or extend `bell_delaware.py`) | Taborek Table 11 + R_l/R_b/R_s + window dP + nozzle dP                              | ~200 lines |
| `correlations/connors.py`                                         | 5 vibration mechanisms: natural freq, Connors, vortex shedding, buffeting, acoustic | ~250 lines |
| `correlations/asme_thickness.py`                                  | UG-27/UG-28 wall thickness + expansion check                                        | ~100 lines |
| `correlations/turton_cost.py`                                     | Turton purchased cost + F_P + F_BM + CEPCI scaling                                  | ~80 lines  |
| `data/cost_indices.py`                                            | CEPCI value + staleness check                                                       | ~15 lines  |
| `data/material_properties.py`                                     | Unified: k_w, E, ρ, S(T), α(T), F_M for ~8 materials                                | ~120 lines |

---

## What `thermo`/`fluids`/`ht` Libraries Cover

| Library    | Relevant Functionality                                         | Use or Custom?                                                      |
| ---------- | -------------------------------------------------------------- | ------------------------------------------------------------------- |
| `fluids`   | `friction_factor_Churchill_1977()`, some fitting K values      | **Available** but recommend custom for auditability                 |
| `fluids`   | `nearest_pipe()` for standard pipe dimensions                  | **Use** for shell pipe sizes                                        |
| `CoolProp` | Speed of sound `PropsSI('A', ...)` for pure fluids             | **Use** for Step 13 acoustic resonance (gas service)                |
| `thermo`   | Fluid properties (ρ, μ, k, Cp) already integrated via adapters | **Already used** — no change                                        |
| `ht`       | Some shell-side and tube-side correlations                     | **Do not use** — prefer custom for traceability to published source |
