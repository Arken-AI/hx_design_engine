# Steps 6–16 Implementation Plan

**Status:** Planning  
**Depends on:** Steps 1–5 (complete), BaseStep infrastructure (complete)  
**Reference:** ARKEN_MASTER_PLAN.md §6.3, §14

---

## Foundation (What Steps 1–5 Built)

| Asset                                                              | Status |
| ------------------------------------------------------------------ | ------ |
| `BaseStep` with 4-layer review loop (execute → rules → AI → state) | ✅     |
| AI Engineer (Claude Sonnet, retry 3×, confidence gate < 0.5)       | ✅     |
| SSE streaming (8 event types)                                      | ✅     |
| Redis session store + orphan detection                             | ✅     |
| Thermo adapter (IAPWS → CoolProp → thermo → petroleum → specialty) | ✅     |
| LMTD + F-factor (Bowman analytical)                                | ✅     |
| TEMA tables, BWG tables, fouling factors, U assumptions            | ✅     |
| `DesignState`, `StepResult`, `AIReview`, `GeometrySpec` models     | ✅     |
| `validation_rules.py` framework (rules for steps 1–5)              | ✅     |
| `pipeline_runner.py` orchestrator (steps 1–5 wired)                | ✅     |

---

## Phase A — Heat Transfer Coefficients (Steps 6–9)

> **The critical path.** Contains Bell-Delaware — the core engineering value of the product. Everything downstream depends on this.

### Gate: Bell-Delaware Validation

**Before writing any step code**, implement and validate `bell_delaware.py` against Serth Example 5.1:

```
Reference geometry:
  shell_diameter = 0.5906 m, tube_od = 0.01905 m, tube_id = 0.01575 m
  tube_length = 4.877 m, baffle_spacing = 0.127 m, pitch_ratio = 1.333
  n_tubes = 324, n_passes = 2, triangular pitch, baffle_cut = 0.25

Pass criteria:
  h_shell within ±5% of Serth textbook value
  J_b, J_c, J_l each within ±10% of Serth values
```

**If this gate fails, do not proceed. Debug bell_delaware.py first.**

### New Correlations Required

| File                            | Purpose                                                                                    | Validation                |
| ------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------- |
| `correlations/bell_delaware.py` | `shell_side_h()` — 5 J-factors → h_o; `shell_side_dP()` — pressure drop with R_l, R_b, R_s | Serth 5.1 ±5%             |
| `correlations/gnielinski.py`    | `tube_side_h()` — turbulent (Gnielinski), laminar (Hausen), transition blend               | Dittus-Boelter crosscheck |

### Steps

#### Step 6: Initial U + Size Estimate

- **AI Mode:** CONDITIONAL (U outside typical range or past designs available)
- **Calculation:** Look up typical U for fluid pair → A = Q / (U × F × LMTD) → N_tubes from TEMA tables → shell diameter
- **Data:** Uses existing `u_assumptions.py` + `tema_tables.py`
- **Files:**
  - `steps/step_06_initial_u.py`
  - `steps/step_06_rules.py` — U > 0, A > 0, tube count maps to standard shell

#### Step 7: Tube-Side Heat Transfer Coefficient

- **AI Mode:** CONDITIONAL (velocity/Re problematic); **skipped when `in_convergence_loop=True`**
- **Calculation:** velocity → Re, Pr → Gnielinski/Hausen → h_i
- **Triggers AI if:** velocity < 0.8 m/s (fouling risk) or > 2.5 m/s (erosion) or Re in transition zone
- **Files:**
  - `steps/step_07_tube_side_h.py`
  - `steps/step_07_rules.py` — h_i > 0, velocity within physical bounds

#### Step 8: Shell-Side Heat Transfer Coefficient (Bell-Delaware)

- **AI Mode:** FULL (always — most complex calculation)
- **Calculation:** geometric areas → ideal h → 5 J-factors (J_c, J_l, J_b, J_s, J_r) → h_o = h_ideal × ΠJ
- **AI reviews:** J-factor reasonableness, cross-flow velocity vs vibration risk
- **Auto-conservative rule:** If BD/Kern divergence > 20% → use the lower value, AI annotates why
- **Files:**
  - `steps/step_08_shell_side_h.py`
  - `steps/step_08_rules.py` — h_o > 0, all J-factors in [0.2, 1.2], product J_c×J_l×J_b > 0.30

#### Step 9: Overall U + Resistance Breakdown

- **AI Mode:** FULL (always)
- **Calculation:** 1/U = 1/h_o + R_f,o + t_w/k_w + R_f,i + (d_o/d_i)/h_i; each resistance as % of total
- **AI reviews:** U in typical range? Kern cross-check < 15%? Controlling resistance correct?
- **Calibration point:** If ≥ 5 HTRI comparisons exist for this CalibrationKey, apply correction factor
- **Files:**
  - `steps/step_09_overall_u.py`
  - `steps/step_09_rules.py` — U > 0, all resistances > 0, percentages sum to 100%

### Phase A Tests

- `tests/unit/correlations/test_bell_delaware.py` — Serth 5.1 benchmark (GATE)
- `tests/unit/correlations/test_gnielinski.py` — 5 cases incl. Dittus-Boelter crosscheck
- `tests/unit/steps/test_step_06.py` through `test_step_09.py`
- `tests/unit/steps/test_step_07_convergence_skip.py` — AI skipped when `in_convergence_loop=True`
- `tests/ai/test_step08_reproducibility.py` — 10× identical inputs, ≥ 9/10 same decision

---

## Phase B — Pressure Drop + Convergence (Steps 10–12)

> **The iteration engine.** Runs Steps 7–11 in a tight loop until geometry converges.

### New Correlations Required

| File                                 | Purpose                                  |
| ------------------------------------ | ---------------------------------------- |
| `correlations/churchill_friction.py` | Darcy friction factor (all flow regimes) |

### Steps

#### Step 10: Pressure Drops

- **AI Mode:** CONDITIONAL (margin < 15%); **skipped when `in_convergence_loop=True`**
- **Calculation:**
  - Tube-side: Darcy-Weisbach + return losses (4 velocity heads/pass) + nozzle losses
  - Shell-side: Bell-Delaware dP method with R_l, R_b, R_s corrections
- **Hard limits:** dP_shell < 1.4 bar, dP_tube < 0.7 bar, nozzle ρv² < 2230 kg/m·s²
- **Files:**
  - `steps/step_10_pressure_drops.py`
  - `steps/step_10_rules.py`

#### Step 11: Area + Overdesign

- **AI Mode:** CONDITIONAL (overdesign outside 8–30%); **skipped when `in_convergence_loop=True`**
- **Calculation:** A_required = Q / (U_calc × F × LMTD); overdesign = (A_available − A_required) / A_required × 100%
- **Target range:** 10–25% ideal, 0–40% acceptable. Hard fail: overdesign < 0%.
- **Files:**
  - `steps/step_11_area_overdesign.py`
  - `steps/step_11_rules.py`

#### Step 12: Convergence Loop (Geometry Iteration)

- **AI Mode:** NONE (pure iteration — too fast for AI latency)
- **Logic:** Loop Steps 7→11, max 20 iterations
- **Convergence criteria:** ΔU < 1% AND overdesign 10–25% AND all dP within limits AND velocity in range
- **Adjustment priority:** Fix dP violations first → overdesign → velocity
- **Critical implementation:** `try/finally` flag reset ensures `in_convergence_loop` is always cleared (CG1A)
- **AI called ONLY if:** Loop fails to converge after 20 iterations (structural change needed)
- **SSE:** Emits `iteration_progress` event each iteration
- **Files:**
  - `steps/step_12_convergence.py`
  - `steps/step_12_rules.py`

```python
# Core pattern (CG1A):
state = state.model_copy(update={"in_convergence_loop": True})
try:
    for iteration in range(1, 21):
        # run Steps 7–11 (no AI due to flag)
        if converged: break
finally:
    state = state.model_copy(update={"in_convergence_loop": False})
```

### Phase B Tests

- `tests/integration/test_convergence_loop.py`:
  1. Normal convergence → `in_convergence_loop=False` after
  2. Exception in iteration 5 → `in_convergence_loop=False` (finally works)
  3. 20-iteration limit hit → returns result with warning
  4. Steps 7/10/11 skip AI when `in_convergence_loop=True`
  5. Oscillating ΔU → 20 iterations hit, WARNING emitted, best result returned
- `tests/unit/steps/test_step_12.py` — try/finally with mock sub-step that raises on iteration 5

---

## Phase C — Safety + Mechanical + Cost (Steps 13–15)

> **Post-convergence checks.** These run once on the final converged geometry. Phase C is independent of Phase B — can start once Phase A is complete.

### New Correlations & Data Required

| File                             | Purpose                                                                     |
| -------------------------------- | --------------------------------------------------------------------------- |
| `correlations/connors.py`        | Connors criterion + vortex shedding + buffeting + acoustic resonance        |
| `correlations/turton_cost.py`    | Turton (2013) cost correlations                                             |
| `correlations/asme_thickness.py` | ASME VIII Div 1 minimum wall thickness                                      |
| `data/cost_indices.py`           | CEPCI index: `{"value": 816.0, "year": 2026, "last_updated": "2026-03-01"}` |

### Steps

#### Step 13: Vibration Check

- **AI Mode:** FULL (always — safety-critical)
- **Calculation:** Natural frequency at each span → cross-flow velocity → check 5 mechanisms:
  1. Fluidelastic instability (Connors) — u_cross/u_crit < 0.5
  2. Vortex shedding
  3. Turbulent buffeting
  4. Acoustic resonance (gas service only)
  5. Fluid-elastic whirling
- **Critical spans:** Inlet/outlet (1.5× central span) — most likely failure location
- **Escalates when:** Vibration fix conflicts with dP limit
- **Files:**
  - `steps/step_13_vibration.py`
  - `steps/step_13_rules.py` — u_cross/u_crit < 0.5 at every span

#### Step 14: Mechanical Design Check

- **AI Mode:** CONDITIONAL (P > 30 bar or borderline thickness)
- **Calculation:** ASME VIII tube thickness, shell thickness, thermal expansion differential
- **Can correct:** Change rear head type (BEM→AES) if expansion exceeds tolerance, increase tube BWG
- **Limitation:** Tubesheet thickness not checked in Phase 1
- **Files:**
  - `steps/step_14_mechanical.py`
  - `steps/step_14_rules.py` — actual wall ≥ min required, expansion within tolerance

#### Step 15: Cost Estimate

- **AI Mode:** CONDITIONAL (cost anomalous vs past)
- **Calculation:** Turton correlations + CEPCI 2026 adjustment + material & pressure correction factors
- **CEPCI rule:** `CEPCI_INDEX` constant with `last_updated`; warn if > 90 days old
- **Files:**
  - `steps/step_15_cost.py`
  - `steps/step_15_rules.py` — cost > 0, cost/m² within range for material

### Phase C Tests

- `tests/unit/correlations/test_connors.py` — safe, unsafe, near-threshold, missing fields
- `tests/unit/steps/test_step_13.py` — all 5 mechanisms; `vibration_safe=False` if any fails
- `tests/unit/steps/test_step_14.py` — ASME thickness, expansion differential
- `tests/unit/steps/test_step_15.py` — Turton cost, CEPCI adjustment, exotic material factors

---

## Phase D — Final Validation + Pipeline Wiring (Step 16)

> **The finish line.** Confidence scoring, full audit trail, E2E pipeline.

#### Step 16: Final Validation + Confidence Score

- **AI Mode:** FULL (always — final sign-off)
- **Confidence breakdown (4 components, equal weight 0.25 each):**
  - `geometry_convergence` — did the convergence loop succeed cleanly?
  - `ai_agreement_rate` — what fraction of AI reviews were PROCEED (no corrections)?
  - `supermemory_similarity` — how close is this design to past successful designs?
  - `validation_passes` — what fraction of Layer 2 hard rules passed on first attempt?
- **AI produces:** confidence score, plain-English summary, assumptions list, recommendations
- **Save:** If confidence ≥ 0.75 → store design to Supermemory past_designs
- **Files:**
  - `steps/step_16_final_validation.py`
  - `steps/step_16_rules.py`

### Pipeline Wiring

- Update `pipeline_runner.py` to run all 16 steps in sequence
- Step 12 internally calls Steps 7–11 in a loop
- Steps 13–16 run once on converged geometry
- Emit `design_complete` SSE event with full DesignState

### Phase D Tests

- `tests/integration/test_pipeline_e2e.py` — full 16-step run with mock AI:
  - Input: crude oil cooling request
  - Assert: DesignState fully populated after Step 16
  - Assert: 0 < confidence_score ≤ 1.0
  - Assert: confidence_breakdown has 4 keys
  - Assert: all SSE event types emitted, `design_complete` last
  - Assert: step_records has 16 entries

---

## Phase Summary

| Phase | Steps       | New Files                                                                                  | Core Challenge                                       | Depends On |
| ----- | ----------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------- | ---------- |
| **A** | 6, 7, 8, 9  | bell_delaware.py, gnielinski.py, 4 step files, 4 rule files                                | Bell-Delaware correlation (hardest math)             | Steps 1–5  |
| **B** | 10, 11, 12  | churchill_friction.py, 3 step files, 3 rule files                                          | Convergence loop + try/finally + oscillation damping | Phase A    |
| **C** | 13, 14, 15  | connors.py, asme_thickness.py, turton_cost.py, cost_indices.py, 3 step files, 3 rule files | Vibration 5 mechanisms, ASME VIII, Turton cost       | Phase A    |
| **D** | 16 + wiring | 1 step file, 1 rule file, pipeline_runner updates                                          | Confidence scoring, E2E integration                  | A + B + C  |

### Dependency Graph

```
Steps 1–5 (done)
    │
    ▼
 Phase A (Steps 6–9)
    │
    ├──────────────┐
    ▼              ▼
 Phase B        Phase C
 (Steps 10–12)  (Steps 13–15)
    │              │
    └──────┬───────┘
           ▼
        Phase D (Step 16 + wiring)
```

### Build Order (Sequential)

```
 1. bell_delaware.py  →  Serth 5.1 validation  →  GATE
 2. gnielinski.py     →  Dittus-Boelter crosscheck
 3. Step 6 → Step 7 → Step 8 → Step 9 (with tests)
 4. churchill_friction.py
 5. Step 10 → Step 11 → Step 12 (with convergence tests)
 6. connors.py + asme_thickness.py + turton_cost.py + cost_indices.py
 7. Step 13 → Step 14 → Step 15 (with tests)
 8. Step 16 + pipeline_runner wiring
 9. E2E integration test (all 16 steps)
```

---

## DesignState Fields Added by Steps 6–16

```python
# Step 6
U_estimated_W_m2K: float       # initial U assumption
A_estimated_m2: float           # Q / (U × F × LMTD)

# Step 7
h_tube_W_m2K: float             # tube-side film coefficient
tube_velocity_m_s: float        # tube-side fluid velocity
Re_tube: float                  # tube-side Reynolds number

# Step 8
h_shell_W_m2K: float            # shell-side film coefficient
J_factors: dict                 # {J_c, J_l, J_b, J_s, J_r, h_ideal}

# Step 9
U_overall_W_m2K: float          # calculated overall U
resistance_breakdown: dict      # {shell_film_pct, tube_film_pct, fouling_pct, wall_pct}

# Step 10
dP_tube_Pa: float               # tube-side pressure drop
dP_shell_Pa: float              # shell-side pressure drop

# Step 11
area_required_m2: float
area_provided_m2: float
overdesign_pct: float

# Step 12
convergence_iteration: int      # how many iterations it took
in_convergence_loop: bool       # flag for AI skip

# Step 13
vibration_safe: bool
vibration_details: dict         # per-mechanism results

# Step 14
tube_thickness_ok: bool
shell_thickness_ok: bool
expansion_mm: float

# Step 15
cost_usd: float
cost_breakdown: dict            # {base, material_factor, pressure_factor, cepci_adjusted}

# Step 16
confidence_score: float         # 0.0–1.0
confidence_breakdown: dict      # 4 keys, each 0.0–1.0
design_summary: str             # plain-English summary
assumptions: list[str]          # all assumptions made
```

---

## AI Prompt Requirements (Steps 6–16)

Each step needs a dedicated section in the AI prompt. Pattern:

```
Step {N}: {Name}
CALCULATION RESULT: {Layer 1 output}
HARD RULES STATUS: {Layer 2 pass/fail details}
PREVIOUS REVIEW NOTES: {from earlier steps that affect this one}
FULL DESIGN STATE: {complete JSON}
→ Respond with: {decision, confidence, reasoning, correction, user_summary}
```

| Step | Key AI Judgment                                          |
| ---- | -------------------------------------------------------- |
| 6    | Is assumed U reasonable for this fluid pair?             |
| 7    | Is tube velocity OK? Fouling/erosion risk?               |
| 8    | Are J-factors physically reasonable? BD/Kern divergence? |
| 9    | Is U in typical range? Resistance breakdown sensible?    |
| 10   | Are pressure drops within limits with margin?            |
| 11   | Is overdesign economically reasonable?                   |
| 12   | N/A (no AI in convergence loop)                          |
| 13   | Are all 5 vibration mechanisms safe? Trade-offs?         |
| 14   | Is mechanical design adequate? Expansion concern?        |
| 15   | Is cost reasonable for this size/material?               |
| 16   | Overall confidence — would you sign off on this design?  |

---

## Validation Rules Summary (Steps 6–16)

| Step | Hard Rules (Layer 2 — AI cannot override)                |
| ---- | -------------------------------------------------------- |
| 6    | U > 0, A > 0, tube count ≥ 1                             |
| 7    | h_i > 0, 0.3 < velocity < 5.0 m/s                        |
| 8    | h_o > 0, all J ∈ [0.2, 1.2], J_c×J_l×J_b > 0.30          |
| 9    | U > 0, all resistances > 0                               |
| 10   | dP_shell < 1.4 bar, dP_tube < 0.7 bar, nozzle ρv² < 2230 |
| 11   | overdesign ≥ 0% (hard fail if negative)                  |
| 12   | N/A (orchestrator, not a calculation step)               |
| 13   | u_cross/u_crit < 0.5 at every span                       |
| 14   | wall_actual ≥ wall_min, expansion within tolerance       |
| 15   | cost > 0, cost/m² within range for material              |
| 16   | confidence_score ∈ [0.0, 1.0], breakdown sums correctly  |
