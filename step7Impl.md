# Step 7 Implementation Plan — Tube-Side Heat Transfer Coefficient

**Status:** Ready to implement  
**Depends on:** Steps 1–6 (complete)  
**Reference:** STEPS_6_16_PLAN.md §Phase A, Step 7

---

## Decision Log

All design decisions were discussed and finalized before this plan was written.

| #   | Question              | Decision                                                             | Confidence |
| --- | --------------------- | -------------------------------------------------------------------- | :--------: |
| 1   | Laminar correlation   | **Hausen** (no wall temp needed)                                     |    9/10    |
| 2   | Transition zone       | **Gnielinski down to Re=2300**, Hausen below                         |    8/10    |
| 3   | Friction factor       | **Petukhov now**, Churchill deferred to Step 10                      |    9/10    |
| 4   | Viscosity correction  | **Option B** — rough T_wall estimate, exponent 0.14 universally      |    8/10    |
| 5   | Tube-side fluid ID    | **Simple inversion** of `shell_side_fluid`                           |   10/10    |
| 6   | DesignState fields    | **Add Re, Pr, Nu, regime** to state (6 new fields + 2 T_mean fields) |    9/10    |
| 7   | Velocity limits       | **Hardcode liquid** (0.3–5.0 m/s), defer gas to Phase B              |    9/10    |
| 8   | DB crosscheck         | **Warning at >20%**, no AI escalation                                |    8/10    |
| 9   | Module structure      | **Dict return**, stateless pure-math functions                       |    9/10    |
| 10  | Test data             | **Incropera + Serth** + boundary cases                               |    7/10    |
| F1  | gnielinski.py purity  | **Option A** — pure math, Step 7 passes μ_wall in                    |   10/10    |
| F2  | Phase detection       | **Hardcode liquid**, defer gas to Phase B                            |    9/10    |
| F3  | T_mean on DesignState | **Persist via pipeline_runner mapping** (Path 1 — no Step 3 changes) |    9/10    |
| F4  | Viscosity exponent    | **0.14 universally**, ratio self-corrects for heating/cooling        |    8/10    |
| F5  | Hausen floor          | **Explicit `max(3.66, Nu)`** defensive floor                         |    9/10    |

---

## Overview

**4 new files**, **3 files modified**, structured in 8 phases.

```
New files:
  hx_engine/app/correlations/gnielinski.py       (correlation math)
  hx_engine/app/steps/step_07_tube_side_h.py     (step logic)
  hx_engine/app/steps/step_07_rules.py           (hard validation rules)
  tests/unit/test_step_07_execute.py              (tests)

Modified files:
  hx_engine/app/models/design_state.py            (new fields)
  hx_engine/app/core/pipeline_runner.py           (wiring + output mapping)
  hx_engine/app/core/ai_engineer.py               (Step 7 AI prompt)
```

---

## Phase 1: DesignState Model Updates

**File:** `hx_engine/app/models/design_state.py`

### 1.1 — Add 2 mean-temperature fields

Location: below the `T_cold_out_C` field, in the temperatures block.

```python
T_mean_hot_C: Optional[float] = None
T_mean_cold_C: Optional[float] = None
```

No validators needed — these are simple arithmetic means of validated inlet/outlet temps.

### 1.2 — Add 6 tube-side HTC fields

Location: new section after the `A_m2` field, in the "thermal results" block.

```python
# --- tube-side heat transfer (populated by Step 7) ---
h_tube_W_m2K: Optional[float] = None
tube_velocity_m_s: Optional[float] = None
Re_tube: Optional[float] = None
Pr_tube: Optional[float] = None
Nu_tube: Optional[float] = None
flow_regime_tube: Optional[str] = None   # "laminar" | "transition" | "turbulent"
```

No validators on these — Step 7's Layer 2 rules handle bounds checking.

**Total: 8 new Optional fields on DesignState.**

---

## Phase 2: Gnielinski Correlation Module

**File:** `hx_engine/app/correlations/gnielinski.py` (NEW)

Pure-math module, zero imports beyond `math`. Follows `lmtd.py` pattern.

### 2.1 — `petukhov_friction(Re)` → `float`

- Formula: `f = (0.790 × ln(Re) − 1.64)^(−2)`
- Valid for Re > 2300.
- Guard: if Re ≤ 0, raise `ValueError`.

### 2.2 — `hausen_nu(Re, Pr, D, L)` → `float`

- Formula: `Nu = 3.66 + (0.0668 × Gz) / (1 + 0.04 × Gz^(2/3))` where `Gz = Re × Pr × D/L`
- Defensive floor: `return max(3.66, Nu)`
- Guard: L must be > 0, D must be > 0.

### 2.3 — `gnielinski_nu(Re, Pr, f)` → `float`

- Formula: `Nu = ((f/8)(Re − 1000) × Pr) / (1 + 12.7 × sqrt(f/8) × (Pr^(2/3) − 1))`
- Valid for Re ≥ 2300, 0.5 ≤ Pr ≤ 2000.
- Guard: denominator > 0 check.

### 2.4 — `dittus_boelter_nu(Re, Pr)` → `float`

- Formula: `Nu = 0.023 × Re^0.8 × Pr^0.4`
- Used only as crosscheck, not primary correlation.

### 2.5 — `tube_side_h(Re, Pr, D_i, L, k, mu_bulk, mu_wall)` → `dict`

Main entry point. Logic:

1. **Determine regime:**
   - Re < 2300 → `"laminar"`, use Hausen
   - 2300 ≤ Re < 10000 → `"transition"`, use Gnielinski
   - Re ≥ 10000 → `"turbulent"`, use Gnielinski

2. **Compute Nu** from selected correlation

3. **Apply viscosity correction:**

   ```
   Nu_corrected = Nu × (mu_bulk / mu_wall)^0.14
   ```

   Guard: if `mu_wall` is None or ≤ 0, skip correction (ratio = 1.0), add warning

4. **Compute h_i:**

   ```
   h_i = Nu_corrected × k / D_i
   ```

5. **Dittus-Boelter crosscheck** (only for Re ≥ 10000):
   - Compute DB Nu, compute divergence %
   - If divergence > 20%, include in warnings

6. **Return dict:**
   ```python
   {
       "h_i": float,                          # W/m²K — the primary result
       "Nu": float,                           # corrected Nusselt number
       "Nu_uncorrected": float,               # before viscosity correction
       "f_petukhov": float | None,            # friction factor (None for laminar)
       "method": str,                         # "gnielinski" | "hausen"
       "flow_regime": str,                    # "laminar" | "transition" | "turbulent"
       "viscosity_correction": float,         # (mu_b/mu_w)^0.14
       "dittus_boelter_Nu": float | None,
       "dittus_boelter_divergence_pct": float | None,
       "warnings": list[str],                 # any warnings generated
   }
   ```

---

## Phase 3: Step 7 Validation Rules

**File:** `hx_engine/app/steps/step_07_rules.py` (NEW)

Follows `step_06_rules.py` pattern exactly.

### 3.1 — Rule R1: `h_i > 0`

- Check `result.outputs.get("h_tube_W_m2K")`
- Fail message: `"h_tube must be positive, got {val}"`

### 3.2 — Rule R2: Velocity within liquid bounds

- Check `result.outputs.get("tube_velocity_m_s")`
- Hard limits: 0.3 ≤ v ≤ 5.0 m/s
- Fail message includes actual value and limit violated
- TODO comment for future gas support:
  ```python
  # TODO Phase B: Add gas velocity limits (5.0–30.0 m/s) when gas-phase
  # support is added. Currently engine is single-phase liquid only;
  # FluidProperties validator enforces ρ ∈ [50, 2000] kg/m³.
  V_HARD_MIN, V_HARD_MAX = 0.3, 5.0
  ```

### 3.3 — Rule R3: `Re > 0`

- Check `result.outputs.get("Re_tube")`

### 3.4 — Rule R4: `Pr > 0`

- Check `result.outputs.get("Pr_tube")`

### 3.5 — Registration

```python
register_rule(7, _rule_h_positive)
register_rule(7, _rule_velocity_bounds)
register_rule(7, _rule_re_positive)
register_rule(7, _rule_pr_positive)
```

Module-level registration — fires on import (same pattern as `step_06_rules.py`).

---

## Phase 4: Step 7 Step Class

**File:** `hx_engine/app/steps/step_07_tube_side_h.py` (NEW)

Class `Step07TubeSideH(BaseStep)` with `step_id=7`, `ai_mode=AIModeEnum.CONDITIONAL`.

### 4.1 — Imports

- `BaseStep` from `steps.base`
- `StepResult`, `AIModeEnum` from `models.step_result`
- `CalculationError` from `core.exceptions`
- `gnielinski.tube_side_h` from `correlations.gnielinski`
- `get_fluid_properties` from `adapters.thermo_adapter`
- Auto-register rules: `import hx_engine.app.steps.step_07_rules`

### 4.2 — `_check_preconditions(state)` → `list[str]`

Required from prior steps:

| Field                                                      | Source Step |
| ---------------------------------------------------------- | ----------- |
| `state.shell_side_fluid`                                   | Step 4      |
| `state.geometry.tube_id_m`                                 | Step 6      |
| `state.geometry.n_tubes`                                   | Step 6      |
| `state.geometry.n_passes`                                  | Step 4/6    |
| `state.geometry.tube_length_m`                             | Step 4      |
| Tube-side `m_dot_*_kg_s`                                   | Step 1/2    |
| Tube-side `*_fluid_props` (density, viscosity, k, Pr)      | Step 3      |
| Tube-side `*_fluid_name`                                   | Step 1      |
| `T_hot_in_C`, `T_hot_out_C`, `T_cold_in_C`, `T_cold_out_C` | Step 1/2    |

Returns list of missing field names. If non-empty, `execute()` raises `CalculationError`.

### 4.3 — `execute(state)` → `StepResult`

Sequence:

**Step 1 — Precondition check:**
Call `_check_preconditions`, raise if missing.

**Step 2 — Identify tube-side fluid:**

```python
tube_side = "cold" if state.shell_side_fluid == "hot" else "hot"
```

Select the appropriate `m_dot`, `fluid_props`, `fluid_name`, T_in, T_out, pressure.

**Step 3 — Compute mean temperatures:**

```python
T_mean_tube = (T_tube_in + T_tube_out) / 2.0
T_mean_shell = (T_shell_in + T_shell_out) / 2.0
```

**Step 4 — Extract geometry:**

```python
D_i = state.geometry.tube_id_m
L = state.geometry.tube_length_m
n_tubes = state.geometry.n_tubes
n_passes = state.geometry.n_passes
```

**Step 5 — Compute velocity:**

```python
A_cross_per_tube = math.pi / 4 * D_i**2
tubes_per_pass = n_tubes / n_passes
A_flow = tubes_per_pass * A_cross_per_tube
velocity = m_dot / (rho * A_flow)
```

**Step 6 — Compute Re and extract Pr:**

```python
Re = rho * velocity * D_i / mu
Pr = fluid_props.Pr
```

**Step 7 — Get μ_wall via thermo adapter:**

```python
T_wall_est = (T_mean_tube + T_mean_shell) / 2.0
wall_props = get_fluid_properties(fluid_name, T_wall_est, pressure_Pa)
mu_wall = wall_props.viscosity_Pa_s
```

**Step 8 — Call correlation:**

```python
htc_result = gnielinski.tube_side_h(Re, Pr, D_i, L, k, mu_bulk, mu_wall)
```

**Step 9 — Collect warnings** from `htc_result["warnings"]` plus regime-specific:

- If Re 2300–4000: `"Transition zone (Re={Re:.0f}): flow genuinely unstable"`
- If velocity < 0.8: `"Low velocity ({v:.2f} m/s): fouling risk"`
- If velocity > 2.5: `"High velocity ({v:.2f} m/s): erosion risk"`

**Step 10 — Cache values** for `_conditional_ai_trigger`:

```python
self._velocity = velocity
self._Re = Re
self._h_i = htc_result["h_i"]
```

**Step 11 — Write state directly** (matching Step 6 pattern):

```python
state.h_tube_W_m2K = htc_result["h_i"]
state.tube_velocity_m_s = velocity
state.Re_tube = Re
state.Pr_tube = Pr
state.Nu_tube = htc_result["Nu"]
state.flow_regime_tube = htc_result["flow_regime"]
```

**Step 12 — Build outputs dict:**

```python
outputs = {
    "h_tube_W_m2K": htc_result["h_i"],
    "tube_velocity_m_s": velocity,
    "Re_tube": Re,
    "Pr_tube": Pr,
    "Nu_tube": htc_result["Nu"],
    "flow_regime_tube": htc_result["flow_regime"],
    "method": htc_result["method"],
    "f_petukhov": htc_result["f_petukhov"],
    "viscosity_correction": htc_result["viscosity_correction"],
    "T_wall_estimated_C": T_wall_est,
    "mu_wall_Pa_s": mu_wall,
    "dittus_boelter_Nu": htc_result["dittus_boelter_Nu"],
    "dittus_boelter_divergence_pct": htc_result["dittus_boelter_divergence_pct"],
}
```

Include `escalation_hints` list if any trigger conditions are met.

**Step 13 — Return `StepResult`** with `step_id=7`, outputs, warnings.

### 4.4 — `_conditional_ai_trigger(state)` → `bool`

Note: `state.in_convergence_loop` is already checked by `BaseStep._should_call_ai()` before this method is called. No need to check it here.

Returns `True` if ANY of:

- `self._velocity < 0.8` (fouling risk)
- `self._velocity > 2.5` (erosion risk)
- `2300 < self._Re < 10000` (transition zone)
- `self._h_i` outside typical range (< 50 or > 15000 W/m²K)

---

## Phase 5: AI Engineer — Step 7 Prompt

**File:** `hx_engine/app/core/ai_engineer.py` (MODIFY)

### 5.1 — Create `_STEP_7_PROMPT` constant

Location: before the `_STEP_PROMPTS` dict.

Content must cover:

- **Context:** Reviewing the tube-side heat transfer coefficient calculation
- **Velocity ranges:** liquid 0.8–2.5 m/s ideal; < 0.8 fouling risk, > 2.5 erosion risk
- **Flow regime guidance:**
  - Laminar (Re < 2300): acceptable for viscous fluids, h_i will be low
  - Transition (2300–10000): uncertain, flag instability
  - Turbulent (> 10000): ideal
- **Typical h_i ranges by fluid type:**
  - Water: 3,000–10,000 W/m²K
  - Light organics: 500–2,000 W/m²K
  - Heavy oil/crude: 50–500 W/m²K
  - Glycols: 200–1,000 W/m²K
- **Viscosity correction:** if μ_bulk/μ_wall > 1.3 or < 0.7, note significant wall effect
- **Dittus-Boelter divergence:** > 20% warrants comment
- **Correction options:** AI can suggest changing `n_passes` (to adjust velocity) or flagging fouling/erosion risk
- **Decision guide:**
  - PROCEED: velocity in range and h_i reasonable
  - WARN: borderline velocity or transition zone
  - CORRECT: n_passes change needed
  - ESCALATE: fundamentally problematic (e.g., h_i orders of magnitude off)

### 5.2 — Register in `_STEP_PROMPTS` dict

```python
7: _STEP_7_PROMPT,
```

### 5.3 — (Optional) Add Step 7 context in `_build_step_context()`

Include: velocity, Re, Pr, flow regime, h_i, method used, viscosity correction factor, DB crosscheck divergence.

---

## Phase 6: Pipeline Runner Wiring

**File:** `hx_engine/app/core/pipeline_runner.py` (MODIFY)

### 6.1 — Add import at top

```python
from hx_engine.app.steps.step_07_tube_side_h import Step07TubeSideH
```

### 6.2 — Append to `PIPELINE_STEPS` list

```python
PIPELINE_STEPS = [
    Step01Requirements,
    Step02HeatDuty,
    Step03FluidProperties,
    Step04TEMAGeometry,
    Step05LMTD,
    Step06InitialU,
    Step07TubeSideH,     # ← NEW
]
```

### 6.3 — Add Step 7 output mappings in `_apply_outputs`

```python
"h_tube_W_m2K": "h_tube_W_m2K",
"tube_velocity_m_s": "tube_velocity_m_s",
"Re_tube": "Re_tube",
"Pr_tube": "Pr_tube",
"Nu_tube": "Nu_tube",
"flow_regime_tube": "flow_regime_tube",
```

### 6.4 — Add T_mean mappings (for Step 3's existing outputs that are currently dropped)

```python
"T_mean_hot_C": "T_mean_hot_C",
"T_mean_cold_C": "T_mean_cold_C",
```

---

## Phase 7: Tests

**File:** `tests/unit/test_step_07_execute.py` (NEW)

### 7.1 — Correlation unit tests

| Test                              | Input                                  | Expected                                 | Purpose                 |
| --------------------------------- | -------------------------------------- | ---------------------------------------- | ----------------------- |
| `test_petukhov_turbulent`         | Re=35000                               | f ≈ 0.022                                | Basic friction factor   |
| `test_hausen_laminar`             | Re=500, Pr=120, D=14.83mm, L=4.877m    | Nu > 3.66, h ~ 50–100 W/m²K              | Laminar oil (Serth Ch4) |
| `test_hausen_floor`               | Re=10, Pr=1, D=0.01, L=10              | Nu = 3.66 exactly                        | Floor works             |
| `test_gnielinski_turbulent_water` | Re=35000, Pr=3.0, D=14.83mm, k=0.65    | h ~ 7500–8500 W/m²K                      | Incropera 8.4           |
| `test_gnielinski_transition`      | Re=3500, Pr=4.5                        | method="gnielinski", regime="transition" | Correct method selected |
| `test_cutover_at_2300`            | Re=2299 → Hausen, Re=2301 → Gnielinski | Different methods                        | Boundary behavior       |
| `test_dittus_boelter_crosscheck`  | Re=35000, Pr=3.0                       | divergence < 20%                         | Crosscheck passes       |
| `test_viscosity_correction`       | mu_bulk=0.001, mu_wall=0.0005          | correction = 2.0^0.14 ≈ 1.104            | Heating case            |
| `test_viscosity_no_wall`          | mu_wall=None                           | correction = 1.0, warning emitted        | Graceful fallback       |

### 7.2 — Step 7 execution tests

| Test                                           | Scenario             | Assert                                         |
| ---------------------------------------------- | -------------------- | ---------------------------------------------- |
| `test_step07_normal_turbulent`                 | Water, Re~30000      | h_i > 0, velocity in range, regime="turbulent" |
| `test_step07_laminar_oil`                      | Heavy oil, Re~500    | h_i > 0, regime="laminar", warning about low h |
| `test_step07_low_velocity_warning`             | v < 0.8 m/s          | warning contains "fouling"                     |
| `test_step07_high_velocity_warning`            | v > 2.5 m/s          | warning contains "erosion"                     |
| `test_step07_transition_warning`               | 2300 < Re < 4000     | warning contains "transition" or "unstable"    |
| `test_step07_precondition_missing_geometry`    | state.geometry=None  | raises CalculationError                        |
| `test_step07_precondition_missing_fluid_props` | tube-side props=None | raises CalculationError                        |
| `test_step07_state_fields_populated`           | Normal run           | state.h_tube_W_m2K, Re_tube, etc. all set      |
| `test_step07_outputs_dict_complete`            | Normal run           | StepResult.outputs has all expected keys       |

### 7.3 — AI trigger tests

| Test                               | Scenario                         | Assert                                 |
| ---------------------------------- | -------------------------------- | -------------------------------------- |
| `test_ai_triggered_low_velocity`   | v=0.5 m/s                        | `_conditional_ai_trigger` returns True |
| `test_ai_triggered_high_velocity`  | v=3.0 m/s                        | returns True                           |
| `test_ai_triggered_transition`     | Re=5000                          | returns True                           |
| `test_ai_skipped_convergence_loop` | `state.in_convergence_loop=True` | `_should_call_ai` returns False        |
| `test_ai_not_triggered_normal`     | v=1.5, Re=30000                  | returns False                          |

### 7.4 — Validation rules tests

| Test                          | Input            | Assert             |
| ----------------------------- | ---------------- | ------------------ |
| `test_rule_h_positive_pass`   | h=5000           | passes             |
| `test_rule_h_positive_fail`   | h=-1             | fails with message |
| `test_rule_h_missing`         | h not in outputs | fails              |
| `test_rule_velocity_too_low`  | v=0.1            | fails              |
| `test_rule_velocity_too_high` | v=6.0            | fails              |
| `test_rule_velocity_ok`       | v=1.5            | passes             |

---

## Phase 8: Smoke Test & Verification

### 8.1 — Run Step 7 tests

```bash
pytest tests/unit/test_step_07_execute.py -v
```

### 8.2 — Run full test suite for regression check

```bash
pytest tests/ -v --tb=short
```

### 8.3 — Start server and verify Step 7 in pipeline

```bash
uvicorn hx_engine.app.main:app --host 0.0.0.0 --port 8100
# POST a design request and confirm pipeline reaches Step 7
```

---

## Build Order (strict sequence)

```
1. Phase 1  →  DesignState fields (8 new fields)
2. Phase 2  →  gnielinski.py (pure math, test independently)
3. Phase 3  →  step_07_rules.py (register rules)
4. Phase 4  →  step_07_tube_side_h.py (main step logic)
5. Phase 5  →  AI prompt in ai_engineer.py
6. Phase 6  →  Pipeline wiring in pipeline_runner.py
7. Phase 7  →  All tests
8. Phase 8  →  Smoke test + regression check
```

Phases 2 and 3 have no dependency on each other and could be done in parallel, but everything else is sequential. Phase 1 must be first because Phase 4 writes to those fields.

---

## Key Engineering References

| Reference                                                | Used For                               |
| -------------------------------------------------------- | -------------------------------------- |
| Gnielinski (1976), Int. Chem. Eng. 16(2)                 | Primary turbulent correlation          |
| Petukhov (1970), Advances in Heat Transfer 6             | Friction factor paired with Gnielinski |
| Hausen (1943)                                            | Laminar developing flow                |
| Dittus-Boelter (1930)                                    | Crosscheck only                        |
| Incropera, Fundamentals of Heat and Mass Transfer, Ch. 8 | Test case A (Example 8.4)              |
| Serth, Process Heat Transfer, Ch. 4                      | Test case B (laminar oil)              |
| VDI Heat Atlas, Section G1                               | Transition zone reference              |
| TEMA RGP-T2.4                                            | Velocity limit guidelines              |

---

## Formulas Reference

### Petukhov friction factor

```
f = (0.790 × ln(Re) − 1.64)^(−2)
```

### Gnielinski (Re ≥ 2300)

```
Nu = ((f/8)(Re − 1000) × Pr) / (1 + 12.7 × √(f/8) × (Pr^(2/3) − 1))
```

### Hausen (Re < 2300)

```
Gz = Re × Pr × D/L
Nu = 3.66 + (0.0668 × Gz) / (1 + 0.04 × Gz^(2/3))
Nu = max(3.66, Nu)    ← defensive floor
```

### Dittus-Boelter (crosscheck only)

```
Nu = 0.023 × Re^0.8 × Pr^0.4
```

### Viscosity correction

```
Nu_corrected = Nu × (μ_bulk / μ_wall)^0.14
```

### Wall temperature estimate

```
T_wall ≈ (T_mean_tube + T_mean_shell) / 2
```

### Velocity

```
A_cross = (π/4) × D_i²
tubes_per_pass = n_tubes / n_passes
A_flow = tubes_per_pass × A_cross
v = ṁ / (ρ × A_flow)
```

### Reynolds number

```
Re = ρ × v × D_i / μ
```
