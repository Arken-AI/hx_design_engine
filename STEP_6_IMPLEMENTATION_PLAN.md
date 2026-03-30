# Step 6 Implementation Plan: Initial U + Size Estimate

**Status:** Ready to Implement  
**Depends on:** Steps 1–5 (complete), all prerequisites verified  
**Reference:** STEPS_6_16_PLAN.md §Phase A

---

## 1. Purpose

Step 6 bridges thermal/geometry setup (Steps 1–5) and detailed heat transfer calculations (Steps 7–9). It takes a starting-guess U (overall heat transfer coefficient) for the fluid pair, calculates the required heat transfer area, and maps that area to a real TEMA-standard shell + tube count.

**Core formula:**

```
A = Q / (U_mid × F × LMTD)
N_tubes = A / (π × d_o × L)
→ find smallest standard shell that fits N_tubes
```

---

## 2. Prerequisites — All Satisfied

### State Fields (populated by earlier steps)

| Field | Populated By | Status |
|---|---|---|
| `Q_W` | Step 2 (heat duty) | ✅ Exists |
| `LMTD_K` | Step 5 (LMTD) | ✅ Exists |
| `F_factor` | Step 5 (F-factor) | ✅ Exists |
| `hot_fluid_name` | Step 1 (requirements) | ✅ Exists |
| `cold_fluid_name` | Step 1 (requirements) | ✅ Exists |
| `hot_fluid_props` | Step 3 (fluid properties) | ✅ Exists |
| `cold_fluid_props` | Step 3 (fluid properties) | ✅ Exists |
| `geometry` (full GeometrySpec) | Step 4 (TEMA + geometry) | ✅ Exists |

### Data / Utility Functions

| Function | File | Status |
|---|---|---|
| `get_U_assumption()` | `hx_engine/app/data/u_assumptions.py` | ✅ Exists |
| `classify_fluid_type()` | `hx_engine/app/data/u_assumptions.py` | ✅ Exists |
| `find_shell_diameter()` | `hx_engine/app/data/tema_tables.py` | ✅ Exists |
| `get_tube_count()` | `hx_engine/app/data/tema_tables.py` | ✅ Exists |

### Infrastructure

| Component | Status |
|---|---|
| `BaseStep` + 4-layer review loop | ✅ Exists |
| `validation_rules.register_rule()` | ✅ Exists |
| `DesignState.U_W_m2K` field | ✅ Exists |
| `DesignState.A_m2` field | ✅ Exists |
| `pipeline_runner._apply_outputs` mapping for U_W_m2K, A_m2, geometry | ✅ Exists |
| `CalculationError` exception | ✅ Exists |
| `_STEP_PROMPTS` dict in ai_engineer.py | ✅ Exists — needs new entry for key `6` |

### New Correlations Needed

**None.** Step 6 relies entirely on existing lookup tables and basic arithmetic.

---

## 3. Inputs (from state after Steps 1–5)

| Field | Source Step | Type | Used For |
|---|---|---|---|
| `Q_W` | Step 2 | `float` | Heat duty (W) |
| `LMTD_K` | Step 5 | `float` | Log mean temperature difference |
| `F_factor` | Step 5 | `float` | LMTD correction factor |
| `hot_fluid_name` | Step 1 | `str` | U lookup classification |
| `cold_fluid_name` | Step 1 | `str` | U lookup classification |
| `hot_fluid_props` | Step 3 | `FluidProperties` | Fallback fluid classification |
| `cold_fluid_props` | Step 3 | `FluidProperties` | Fallback fluid classification |
| `geometry` | Step 4 | `GeometrySpec` | tube_od_m, tube_id_m, tube_length_m, pitch_ratio, pitch_layout, n_passes, shell_passes |

**Note:** Step 4 populates a full GeometrySpec. Step 6 will **override** `n_tubes`, `shell_diameter_m`, and `baffle_spacing_m` with values derived from the area calculation, preserving all other fields.

---

## 4. Outputs (written to state)

| Output Key | State Field | Type | Description |
|---|---|---|---|
| `U_W_m2K` | `U_W_m2K` | `float` | Starting-guess U (W/m²K) — uses `U_mid` from lookup |
| `A_m2` | `A_m2` | `float` | Required heat transfer area (m²) |
| `U_range` | *(outputs only)* | `dict` | `{U_low, U_mid, U_high}` for AI context |
| `hot_fluid_type` | *(outputs only)* | `str` | Classified fluid type used in lookup |
| `cold_fluid_type` | *(outputs only)* | `str` | Classified fluid type used in lookup |
| `n_tubes_required` | *(outputs only)* | `int` | Calculated tubes needed before TEMA rounding |
| `A_provided_m2` | *(outputs only)* | `float` | Actual area with TEMA tube count |
| `geometry` | `geometry` | `GeometrySpec` | Updated with new n_tubes, shell_diameter_m, baffle_spacing_m |

The `_apply_outputs` in `pipeline_runner.py` already has mappings for `U_W_m2K`, `A_m2`, and `geometry` — **no changes needed there**.

---

## 5. Files to Create

### 5a. `hx_engine/app/steps/step_06_initial_u.py`

**Class:** `Step06InitialU(BaseStep)`

**Properties:**
```python
step_id = 6
step_name = "Initial U + Size Estimate"
ai_mode = AIModeEnum.CONDITIONAL
```

**`execute(state)` logic — 9 sub-steps:**

```
1. Pre-condition checks
   → Verify Q_W, LMTD_K, F_factor, geometry, hot_fluid_name, cold_fluid_name
   → Raise CalculationError(6, ...) if any missing

2. Compute effective LMTD
   → eff_LMTD = F_factor × LMTD_K
   → Guard: if eff_LMTD ≤ 0, raise CalculationError

3. Lookup U assumption
   → Call get_U_assumption(hot_fluid_name, cold_fluid_name)
   → Call classify_fluid_type() for both fluids (for AI context)
   → Use U_mid as the design value

4. Calculate required area
   → A_required = Q_W / (U_mid × eff_LMTD)

5. Calculate required tube count
   → N_tubes_required = A_required / (π × tube_od_m × tube_length_m)
   → Round up to integer (math.ceil)

6. Find standard shell
   → Call find_shell_diameter(N_tubes_required, tube_od_m, pitch_layout, n_passes)
   → Returns (shell_diameter_m, actual_n_tubes)

7. Update geometry
   → Mutate existing GeometrySpec with new n_tubes, shell_diameter_m
   → Recalculate baffle_spacing_m (0.4–0.5 × shell_diameter, same heuristic as Step 4)
   → Compute A_provided = actual_n_tubes × π × tube_od_m × tube_length_m

8. Collect warnings
   → actual_n_tubes at max shell (37") → warn size limit
   → A > 500 m² → warn very large exchanger
   → A < 0.5 m² → warn very small exchanger
   → U_mid from generic fallback → warn unclassified fluid

9. Build StepResult with outputs dict and warnings
```

**`_conditional_ai_trigger(state)` — returns True if ANY of:**
- U_mid came from the default fallback (fluid pair not in table)
- Required area > 200 m² (unusually large)
- Required area < 1 m² (unusually small)
- `N_tubes_required` exceeds largest available shell capacity
- U_mid outside typical range (< 50 or > 3000 W/m²K)

---

### 5b. `hx_engine/app/steps/step_06_rules.py`

**Layer 2 hard rules (AI cannot override):**

| Rule | Check | Error Message |
|---|---|---|
| R1 | `U_W_m2K > 0` | "U must be positive" |
| R2 | `A_m2 > 0` | "Heat transfer area must be positive" |
| R3 | `n_tubes >= 1` (from geometry in outputs) | "Tube count must be at least 1" |
| R4 | Shell diameter maps to TEMA standard | "Shell diameter must be a TEMA standard size" |

**Pattern:** Same registration pattern as `step_05_rules.py`:
```python
def _rule_u_positive(step_id, result): ...
def _rule_area_positive(step_id, result): ...
def _rule_n_tubes_minimum(step_id, result): ...
def _rule_shell_standard(step_id, result): ...

def register_step6_rules():
    register_rule(6, _rule_u_positive)
    register_rule(6, _rule_area_positive)
    register_rule(6, _rule_n_tubes_minimum)
    register_rule(6, _rule_shell_standard)

# Auto-register on import
register_step6_rules()
```

---

### 5c. AI Prompt — `_STEP_6_PROMPT` in `ai_engineer.py`

Add entry `6: _STEP_6_PROMPT` to `_STEP_PROMPTS` dict.

**Prompt content should cover:**
- **Purpose:** Initial sizing from U assumption
- **Review focus:** Is assumed U reasonable for this fluid pair? Is the area realistic? Does the shell size make sense?
- **CORRECT when:** U value unreasonable for the service (e.g., gas-gas using liquid-liquid U), fluid misclassified
- **WARN when:** Area is borderline large/small, U at extreme of typical range
- **ESCALATE when:** Completely unknown fluid pair, U off by order of magnitude
- **DO NOT:** Change Q, LMTD, or F_factor (upstream results); override tube geometry fundamentals (OD, length)

---

### 5d. Step Context Builder in `ai_engineer.py`

Add `step_id == 6` branch to `_build_step_context_inner()`:

**Derived values to compute for AI:**
- `eff_LMTD = F × LMTD`
- `A_ratio = A_provided / A_required` (overdesign preview)
- Fluid classifications used
- U range (low, mid, high) for context

---

## 6. Files to Modify

### 6a. `hx_engine/app/core/pipeline_runner.py`

1. **Import:** `from hx_engine.app.steps.step_06_initial_u import Step06InitialU`
2. **PIPELINE_STEPS:** Append `Step06InitialU` to the list
3. **`_apply_outputs`:** Already maps `U_W_m2K`, `A_m2`, `geometry` — **no change needed**

### 6b. `hx_engine/app/models/design_state.py`

**No new fields needed.** The existing `U_W_m2K` and `A_m2` fields serve Step 6's purpose. Step 9 will later overwrite `U_W_m2K` with the calculated value (estimate → refine).

### 6c. Rule Import

Import `step_06_rules` inside `step_06_initial_u.py` so auto-registration fires when the step class is loaded (following Step 5 pattern).

---

## 7. Tests to Create

### 7a. `tests/unit/test_step_06_execute.py`

| # | Test Case | Assert |
|---|---|---|
| 1 | Happy path — water/water | U ~1200, area calculated, shell found |
| 2 | Happy path — crude oil / cooling water | U ~300 |
| 3 | Gas/gas pair | Very low U → large area → potentially largest shell |
| 4 | Pre-condition failure — missing `Q_W` | `CalculationError` raised |
| 5 | Pre-condition failure — missing `geometry` | `CalculationError` raised |
| 6 | Pre-condition failure — missing `LMTD_K` | `CalculationError` raised |
| 7 | Small exchanger — high U + small Q | Tiny area → smallest shell |
| 8 | Outputs populated | U_W_m2K, A_m2, geometry, U_range, fluid types all in result.outputs |
| 9 | Geometry updated correctly | n_tubes, shell_diameter_m overwritten; tube_od_m, tube_length_m, pitch_layout, n_passes preserved |

### 7b. `tests/unit/test_step_06_rules.py`

| # | Test Case | Assert |
|---|---|---|
| 1 | U > 0 | passes |
| 2 | U = 0 | fails |
| 3 | U < 0 | fails |
| 4 | A > 0 | passes |
| 5 | A = 0 | fails |
| 6 | Missing U_W_m2K | fails |
| 7 | Missing A_m2 | fails |
| 8 | n_tubes ≥ 1 | passes |
| 9 | n_tubes = 0 | fails |

### 7c. `tests/unit/test_step_06_ai_trigger.py`

| # | Test Case | Assert |
|---|---|---|
| 1 | Normal fluid pair, normal area | `_conditional_ai_trigger` → `False` |
| 2 | Unknown fluid (fallback U) | → `True` |
| 3 | Very large area (> 200 m²) | → `True` |
| 4 | Very small area (< 1 m²) | → `True` |
| 5 | `in_convergence_loop = True` | `_should_call_ai` → `False` (inherited) |

---

## 8. Verification Strategy

| Check | Expected Result |
|---|---|
| All unit tests pass | 18+ test cases green |
| Integration: Steps 1–6 with mock AI | State has `U_W_m2K`, `A_m2`, and updated `geometry` after Step 6 |
| Sanity: water/water, Q=1MW, LMTD=30K, F=0.9 | U ~1200, A ~37 m², reasonable shell size |
| Edge: gas/gas | Very large area (U ~25 W/m²K) |

---

## 9. Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| Fluid misclassified → wrong U | Medium | `_conditional_ai_trigger` catches fallback; AI reviews |
| Area so large no standard shell fits | Low | `find_shell_diameter` returns largest available + warning; AI reviews |
| Step 4 geometry overwritten incorrectly | Low | Only change n_tubes, shell_diameter_m, baffle_spacing_m — preserve all other fields |
| U_mid too conservative/aggressive | Expected | Starting guess only — Steps 7–9 + convergence (Step 12) will refine |

---

## 10. Build Order

```
1. Create step_06_rules.py            ← Layer 2 rules (standalone, no deps)
2. Create step_06_initial_u.py        ← Step class (imports rules)
3. Add _STEP_6_PROMPT to ai_engineer.py
4. Add step 6 context builder to ai_engineer.py
5. Wire Step06InitialU into pipeline_runner.py
6. Create test_step_06_execute.py
7. Create test_step_06_rules.py
8. Create test_step_06_ai_trigger.py
9. Run all tests, fix any issues
```

---

## 11. Dependency Graph

```
Steps 1–5 (done)
    │
    ▼
 Step 6: Initial U + Size Estimate
    │
    ├── reads: Q_W, LMTD_K, F_factor, geometry, fluid names
    ├── uses:  u_assumptions.py, tema_tables.py (both exist)
    ├── writes: U_W_m2K, A_m2, updated geometry
    │
    ▼
 Step 7: Tube-Side h (needs Step 6's geometry + U)
```
