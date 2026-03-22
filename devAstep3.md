# Dev A — Step 3: Collect Fluid Properties — Implementation Plan

## Context Summary

Step 3 takes the fluid names and temperatures from Steps 1–2, calls `thermo_adapter.get_fluid_properties()` for both fluids at their bulk mean temperature, validates the results, and populates `hot_fluid_props` and `cold_fluid_props` on the `DesignState`.

**What already exists:**

- `thermo_adapter.py` — fully implemented with 5-tier fallback chain + 25+ tests
- `FluidProperties` model — with Pydantic bound validators (density, viscosity, Cp, k, Pr)
- `BaseStep` — with `run_with_review_loop()` pattern
- `DesignState` fields — `hot_fluid_props`, `cold_fluid_props`, `P_hot_Pa`, `P_cold_Pa`
- Reference implementation — Step 2 pattern to follow

**What needs to be built:**

- `hx_engine/app/steps/step_03_fluid_props.py` — the step class
- Tests for every piece

---

## Piece Breakdown

### Piece 1 — Mean Temperature Calculation

**File:** `step_03_fluid_props.py`
**What:** Static method `_compute_mean_temp(T_in_C, T_out_C) -> float`

**Logic:**

- `T_mean = (T_in + T_out) / 2.0`
- If either temp is `None` → raise `CalculationError(3, "...")`

**Why it matters:** All property lookups are temperature-dependent. Wrong mean temp = wrong properties = cascading errors through Steps 4–16.

**Testing Plan (5 tests):**

| #   | Test                   | Input                | Expected           | Physics Assertion                           |
| --- | ---------------------- | -------------------- | ------------------ | ------------------------------------------- |
| 1   | Symmetric hot side     | T_in=150, T_out=90   | 120.0              | Mean is arithmetic midpoint                 |
| 2   | Symmetric cold side    | T_in=30, T_out=60    | 45.0               | Same formula both sides                     |
| 3   | Identical temps (ΔT=0) | T_in=80, T_out=80    | 80.0               | Degenerate case still valid                 |
| 4   | Missing T_in           | T_in=None, T_out=90  | `CalculationError` | Can't compute properties without both temps |
| 5   | Missing T_out          | T_in=150, T_out=None | `CalculationError` | Same guard                                  |

---

### Piece 2 — Single-Fluid Property Retrieval Wrapper

**File:** `step_03_fluid_props.py`
**What:** Static method `_resolve_fluid(fluid_name, T_mean_C, pressure_Pa) -> FluidProperties`

**Logic:**

- Delegates to `thermo_adapter.get_fluid_properties(fluid_name, T_mean_C, pressure_Pa)`
- If pressure is `None`, default to 101325.0 Pa (1 atm) — thermo_adapter already handles this
- Catches `CalculationError` from adapter and re-raises with step_id=3 and a user-friendly message suggesting similar fluid names
- Special handling: if fluid_name is `"crude oil"` or `"crude"` with no API gravity qualifier, log a warning and assume API 29 (medium crude)

**Why it matters:** This is the bridge between the step and the adapter. Ensures errors from the adapter are properly contextualized as Step 3 errors.

**Testing Plan (7 tests):**

| #   | Test                    | Input               | Expected                                | Physics Assertion                               |
| --- | ----------------------- | ------------------- | --------------------------------------- | ----------------------------------------------- |
| 1   | Water at 35°C           | "water", 35.0       | FluidProperties with cp≈4178, ρ≈994     | NIST values within 2%                           |
| 2   | Crude oil at 120°C      | "crude oil", 120.0  | FluidProperties populated               | All 5 properties > 0, density ~800–900          |
| 3   | Unknown fluid           | "unobtanium", 50.0  | `CalculationError` with helpful message | System rejects fantasy fluids                   |
| 4   | Default pressure        | "water", 35.0, None | Same as P=101325                        | 1 atm default doesn't change result             |
| 5   | High pressure           | "water", 35.0, 1e6  | FluidProperties (slight density change) | Pressure affects properties correctly           |
| 6   | Empty fluid name        | "", 50.0            | `CalculationError`                      | Guard against blank input from Step 1           |
| 7   | Crude with no qualifier | "crude", 120.0      | FluidProperties (API 29 assumed)        | Falls through to petroleum tier, warning logged |

---

### Piece 3 — Core `execute()` Logic

**File:** `step_03_fluid_props.py`
**What:** The `execute(self, state: DesignState) -> StepResult` method

**Logic (sequential):**

1. **Pre-condition check:** Verify required state fields exist:
   - `state.hot_fluid_name` — must not be None
   - `state.cold_fluid_name` — must not be None
   - `state.T_hot_in_C`, `state.T_hot_out_C` — both required
   - `state.T_cold_in_C`, `state.T_cold_out_C` — both required
   - If any missing → `CalculationError(3, "Step 3 requires ... from Steps 1-2")`
2. **Compute mean temperatures:**
   - `T_mean_hot = _compute_mean_temp(T_hot_in_C, T_hot_out_C)`
   - `T_mean_cold = _compute_mean_temp(T_cold_in_C, T_cold_out_C)`
3. **Resolve hot fluid properties:**
   - `hot_props = _resolve_fluid(hot_fluid_name, T_mean_hot, P_hot_Pa)`
4. **Resolve cold fluid properties:**
   - `cold_props = _resolve_fluid(cold_fluid_name, T_mean_cold, P_cold_Pa)`
5. **Return StepResult:**
   - `outputs = {"hot_fluid_props": hot_props, "cold_fluid_props": cold_props, "T_mean_hot_C": T_mean_hot, "T_mean_cold_C": T_mean_cold}`
   - These outputs get applied to `DesignState.hot_fluid_props` and `cold_fluid_props` by the pipeline runner

**Class attributes:**

```
step_id = 3
step_name = "Fluid Properties"
ai_mode = AIModeEnum.CONDITIONAL
```

**Testing Plan (8 tests):**

| #   | Test                           | Scenario                                     | Expected                                                | Physics Assertion                                 |
| --- | ------------------------------ | -------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------- |
| 1   | Benchmark case                 | Crude oil 150→90°C + water 30→60°C           | Both FluidProperties populated                          | Both have 5 non-None properties, all > 0          |
| 2   | Missing hot fluid name         | `state.hot_fluid_name = None`                | `CalculationError`                                      | Step won't proceed without input                  |
| 3   | Missing cold fluid name        | `state.cold_fluid_name = None`               | `CalculationError`                                      | Same guard                                        |
| 4   | Missing temperatures           | `state.T_hot_in_C = None`                    | `CalculationError`                                      | Can't compute mean temp                           |
| 5   | Outputs dict keys              | Normal run                                   | `"hot_fluid_props"` and `"cold_fluid_props"` in outputs | Outputs match DesignState field names             |
| 6   | StepResult metadata            | Normal run                                   | `step_id=3`, `step_name="Fluid Properties"`             | Audit trail correct                               |
| 7   | State is not mutated           | Normal run, compare state before/after       | State unchanged                                         | execute() is pure — Layer 1 must not mutate state |
| 8   | Both fluids same (water–water) | hot="water", cold="water" at different temps | Two different FluidProperties (different T_mean)        | Properties are temperature-dependent              |

---

### Piece 4 — Conditional AI Trigger Logic

**File:** `step_03_fluid_props.py`
**What:** Override `_conditional_ai_trigger(self, state: DesignState) -> bool`

**Logic — AI should be called when:**

1. **Prandtl number anomaly:** Hot or cold Pr is outside typical engineering range [0.7, 500]
   - (Note: Pydantic allows [0.5, 1000] but the AI trigger range is stricter)
2. **Viscosity ratio warning:** If `viscosity_hot / viscosity_cold > 100` or vice versa — extreme viscosity difference may indicate one fluid needs special correlations (Sieder-Tate)
3. **Property anomaly flag:** If any property is suspiciously close to the Pydantic bound edges (density < 100 or > 1800)

**Why it matters:** The CONDITIONAL mode prevents unnecessary AI calls (saving cost/latency) but catches cases where human review adds value.

**Testing Plan (6 tests):**

| #   | Test                    | Scenario                           | Expected                 | Physics Assertion                                 |
| --- | ----------------------- | ---------------------------------- | ------------------------ | ------------------------------------------------- |
| 1   | Normal fluids           | Water + crude oil (typical Pr)     | Returns `False` (no AI)  | Normal cases don't trigger AI                     |
| 2   | Pr boundary hot=0.6     | Hot Pr just above 0.5              | Returns `True` (trigger) | Liquid metals / extreme gases warrant review      |
| 3   | Pr boundary cold=600    | Cold Pr high (very viscous)        | Returns `True` (trigger) | High Pr fluids need careful correlation selection |
| 4   | Extreme viscosity ratio | Hot visc 0.5 Pa·s, cold 0.001      | Returns `True` (trigger) | 500:1 ratio is extreme                            |
| 5   | Both sides normal       | Ethanol + water                    | Returns `False`          | No anomalies                                      |
| 6   | In convergence loop     | `state.in_convergence_loop = True` | Returns `False`          | Decision 3A: skip AI during convergence           |

---

### Piece 5 — Layer 2 Validation Rules

**File:** `step_03_fluid_props.py` (register rules at module level)
**What:** Hard engineering rules that AI **cannot** override

**Rules to register via `validation_rules.register_rule(3, rule_fn)`:**

| Rule                         | Check                                   | Failure Mode                                         |
| ---------------------------- | --------------------------------------- | ---------------------------------------------------- |
| R1 — All properties positive | Every field in both FluidProperties > 0 | Hard fail — non-physical                             |
| R2 — Density bounds          | 50 ≤ ρ ≤ 2000 kg/m³ for both            | Hard fail — outside any real fluid                   |
| R3 — Viscosity bounds        | 1e-6 ≤ μ ≤ 1.0 Pa·s                     | Hard fail — gases ~1e-5, heavy oil ~0.5              |
| R4 — Thermal conductivity    | 0.01 ≤ k ≤ 100 W/m·K                    | Hard fail — air ~0.025, metals in liquid range       |
| R5 — Cp sanity               | 500 ≤ Cp ≤ 10000 J/kg·K                 | Hard fail — covers gases through water               |
| R6 — Pr consistency          | Pr ≈ μ·Cp/k within 5%                   | Hard fail — ensures Pr is self-consistent, not stale |

**Note:** Rules R1–R5 overlap with Pydantic validators on `FluidProperties`, but registering them as Layer 2 rules ensures double-validation + proper audit trail through the pipeline. Rule R6 is **new** — catches cases where the adapter returned a stale Pr that doesn't match the other three properties.

**Testing Plan (10 tests):**

| #   | Test               | Scenario                                   | Expected             | Physics Assertion                        |
| --- | ------------------ | ------------------------------------------ | -------------------- | ---------------------------------------- |
| 1   | Valid benchmark    | Water + crude oil                          | All rules pass       | Known-good fluids pass all checks        |
| 2   | Negative density   | ρ = -100                                   | R1 fails             | Density can't be negative                |
| 3   | Zero viscosity     | μ = 0                                      | R1 fails             | Only superfluids have μ=0 (out of scope) |
| 4   | Density too high   | ρ = 3000                                   | R2 fails             | Only mercury/molten metals exceed 2000   |
| 5   | Density too low    | ρ = 10                                     | R2 fails             | Too low for any liquid/dense gas in HX   |
| 6   | Viscosity too high | μ = 5.0                                    | R3 fails             | Beyond heavy bitumen range               |
| 7   | k too low          | k = 0.001                                  | R4 fails             | Even vacuum insulation >0.01 in practice |
| 8   | Cp out of range    | Cp = 50000                                 | R5 fails             | No engineering fluid has Cp this high    |
| 9   | Pr self-consistent | μ=0.001, Cp=4180, k=0.6 → Pr should ≈ 6.97 | R6 passes if Pr=6.97 | Thermodynamic consistency                |
| 10  | Pr inconsistent    | μ=0.001, Cp=4180, k=0.6, Pr=50             | R6 fails             | Pr doesn't match μ·Cp/k — stale value    |

---

### Piece 6 — Corner Cases & Warnings

**File:** `step_03_fluid_props.py`
**What:** Non-fatal warnings appended to `StepResult.warnings` — don't block the pipeline but surface to the user

**Corner cases to handle:**

| #   | Case                                              | Detection                                                | Action                                                                                              |
| --- | ------------------------------------------------- | -------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| C1  | Fluid not in library                              | `CalculationError` from adapter                          | Re-raise with suggestion (e.g., "Did you mean 'ethylene glycol'?")                                  |
| C2  | Crude oil without API gravity                     | fluid_name is "crude oil" / "crude"                      | Assume API 29 (medium), add warning: "Assuming API 29 for crude oil. Specify gravity for accuracy." |
| C3  | Water near 0°C or >100°C at 1 atm                 | `T_mean < 5` or `T_mean > 95` at P ≤ 101325              | Warning: "Water may be near phase change at this temperature. Verify single-phase operation."       |
| C4  | Very high viscosity fluid                         | μ > 0.1 Pa·s                                             | Warning: "High viscosity fluid detected — Sieder-Tate wall correction may be needed in Step 7."     |
| C5  | Properties at inlet vs outlet differ dramatically | Compute props at T_in and T_out, check if Cp varies >15% | Warning: "Cp varies >15% across temperature range. Consider segmented calculation."                 |
| C6  | Near-critical conditions                          | T_mean near critical temp of fluid (if available)        | Warning: "Operating near critical point — properties may be erratic."                               |

**Testing Plan (6 tests):**

| #   | Test                        | Scenario                    | Expected                            | Physics Assertion                                 |
| --- | --------------------------- | --------------------------- | ----------------------------------- | ------------------------------------------------- |
| 1   | Crude with no API           | fluid_name="crude oil"      | Warning contains "API 29"           | Assumption is documented                          |
| 2   | Water near boiling          | T_mean_hot = 98°C, P=101325 | Warning about phase change          | Phase transitions break single-phase correlations |
| 3   | Water below 5°C             | T_mean = 3°C                | Warning about phase change          | Ice formation risk                                |
| 4   | High viscosity oil          | Heavy fuel oil at 50°C      | Warning about Sieder-Tate           | Step 7 will need wall correction                  |
| 5   | Normal case no warnings     | Water at 35°C               | No warnings                         | Clean cases stay clean                            |
| 6   | Unknown fluid error message | "unobtanium"                | CalculationError message is helpful | User gets actionable feedback                     |

---

### Piece 7 — Full Integration (Wire Everything Together)

**File:** `step_03_fluid_props.py`
**What:** Assemble Pieces 1–6 into the final working step. Register validation rules at module import.

**Final class structure:**

```
class Step03FluidProperties(BaseStep):
    step_id = 3
    step_name = "Fluid Properties"
    ai_mode = AIModeEnum.CONDITIONAL

    @staticmethod _compute_mean_temp(...)     # Piece 1
    @staticmethod _resolve_fluid(...)         # Piece 2
    def execute(self, state) -> StepResult    # Piece 3 + Piece 6 warnings
    def _conditional_ai_trigger(...)          # Piece 4

# Module-level registration of Layer 2 rules  # Piece 5
```

**Testing Plan — Integration (8 tests):**

| #   | Test                          | Scenario                                            | Expected                                | Physics Assertion                |
| --- | ----------------------------- | --------------------------------------------------- | --------------------------------------- | -------------------------------- |
| 1   | Full benchmark                | 50 kg/s crude oil 150→90°C, water 30→60°C           | Both props populated, validation passes | Industry-standard benchmark      |
| 2   | Water–water                   | Water both sides, different temps                   | Two FluidProperties, different values   | Temperature dependence           |
| 3   | Ethanol–water                 | ethanol 80→40°C, water 20→55°C                      | Both populated                          | CoolProp + iapws paths both work |
| 4   | StepResult round-trip         | Execute, serialize outputs, check JSON              | All fields serializable                 | Pipeline runner can persist this |
| 5   | Immutability                  | Execute, check original state unchanged             | state.hot_fluid_props still None        | Layer 1 purity contract          |
| 6   | Step protocol                 | `isinstance(Step03FluidProperties(), StepProtocol)` | True                                    | Structural typing contract       |
| 7   | With `run_with_review_loop()` | Normal case + AI stub (PROCEED)                     | StepResult with ai_review populated     | End-to-end including AI review   |
| 8   | Pipeline sequence             | Step1 → Step2 → Step3 on benchmark state            | Step3 outputs valid                     | Steps compose correctly          |

---

## Implementation Order & Dependencies

```
Piece 1 (mean temp)    ← No dependencies, pure math
    ↓
Piece 2 (fluid resolve) ← Depends on thermo_adapter (already built)
    ↓
Piece 3 (execute core)  ← Depends on Pieces 1+2
    ↓
Piece 4 (AI trigger)    ← Depends on Piece 3 (needs result to inspect)
    ↓
Piece 5 (validation)    ← Independent — can be done in parallel with 3/4
    ↓
Piece 6 (corner cases)  ← Depends on Piece 3 (adds warnings to execute)
    ↓
Piece 7 (integration)   ← Wires Pieces 1–6 together, final assembly
```

**Recommended build order:** 1 → 2 → 5 → 3 → 4 → 6 → 7

(Putting validation rules (5) before execute (3) lets you test rules in isolation with mock data before the execute method exists.)

---

## Total Test Count: 50 tests

| Piece                | Tests | Cumulative |
| -------------------- | ----- | ---------- |
| 1 — Mean Temp        | 5     | 5          |
| 2 — Fluid Resolve    | 7     | 12         |
| 3 — Execute Core     | 8     | 20         |
| 4 — AI Trigger       | 6     | 26         |
| 5 — Validation Rules | 10    | 36         |
| 6 — Corner Cases     | 6     | 42         |
| 7 — Integration      | 8     | 50         |

---

## Physics Guard Rails (Cross-Cutting)

These invariants must hold across ALL tests:

1. **Energy conservation:** Properties retrieved at mean temp must be physically consistent (μ·Cp/k = Pr ± 5%)
2. **Temperature dependence:** Properties at 30°C ≠ properties at 120°C for same fluid
3. **No mutation:** `execute()` never modifies the input `DesignState`
4. **Monotonicity:** For water, density decreases with temperature (ρ(30°C) > ρ(90°C))
5. **Unit consistency:** All outputs in SI (kg/m³, Pa·s, J/kg·K, W/m·K, dimensionless Pr)
6. **NIST baseline:** Water properties at 25°C within 2% of NIST reference values (ρ=997.0, Cp=4181.3, μ=8.90e-4, k=0.607)
