# Step 11: Area + Overdesign — Implementation Plan

**Status:** Ready to implement  
**Depends on:** Steps 1–10 (complete), BaseStep infrastructure (complete)  
**References:** Serth Ch. 3 (area expressions), Sinnott §12.1 (overdesign practice)

---

## Overview

Step 11 computes the **required heat transfer area** (from the calculated U) and compares
it to the **provided heat transfer area** (from the physical geometry). The ratio yields
the **overdesign percentage** — the primary convergence signal for Step 12.

No new correlations, no external data, no Supermemory calls. Pure arithmetic on existing
DesignState fields.

**AI Mode:** CONDITIONAL — AI called only when overdesign < 8% or > 30%.
Skipped when `in_convergence_loop=True`.

---

## Formulas

### Required Area

$$A_{\text{required}} = \frac{Q}{U_{\text{dirty}} \times F \times \text{LMTD}}$$

Where:

- `Q` = heat duty [W] — from Step 2 (`Q_W`)
- `U_dirty` = fouled overall HTC [W/m²K] — from Step 9 (`U_dirty_W_m2K`)
- `F` = LMTD correction factor — from Step 5 (`F_factor`)
- `LMTD` = log-mean temperature difference [K] — from Step 5 (`LMTD_K`)

### Provided Area (outer-tube basis)

$$A_{\text{provided}} = \pi \times d_o \times L \times N_t$$

Where:

- `d_o` = tube outer diameter [m] — from `geometry.tube_od_m`
- `L` = full tube length [m] — from `geometry.tube_length_m` (no tubesheet subtraction)
- `N_t` = number of tubes — from `geometry.n_tubes`

**Convention:** Both areas use the outer-tube surface basis, consistent with Step 9's
U calculation (standard TEMA/Bell-Delaware convention).

### Overdesign Percentage

$$\text{overdesign} = \frac{A_{\text{provided}} - A_{\text{required}}}{A_{\text{required}}} \times 100\%$$

### Step 6 vs Step 11 Deviation (diagnostic)

$$\text{deviation} = \frac{A_{\text{m2}} - A_{\text{required}}}{A_{\text{required}}} \times 100\%$$

Where `A_m2` is Step 6's initial area estimate (from assumed U).

---

## Overdesign Thresholds (Hardcoded Constants)

| Range  | Meaning                    | Action                          |
| ------ | -------------------------- | ------------------------------- |
| < 0%   | **Undersized** — HARD FAIL | Layer 2 rejects, cannot proceed |
| 0–8%   | Low margin                 | AI triggered                    |
| 8–10%  | Acceptable, tight          | No AI needed                    |
| 10–25% | **Ideal working range**    | No AI needed                    |
| 25–30% | Acceptable, generous       | No AI needed                    |
| 30–40% | Over-engineered            | AI triggered                    |
| > 40%  | Excessive                  | AI triggered + warning          |

---

## Sub-Steps (Build Order)

| #    | Sub-Step                 | File                                                | Depends On | Est. Complexity |
| ---- | ------------------------ | --------------------------------------------------- | ---------- | --------------- |
| 11.1 | DesignState fields       | `models/design_state.py` (add fields)               | None       | Small           |
| 11.2 | Pipeline runner mapping  | `core/pipeline_runner.py` (extend `_apply_outputs`) | 11.1       | Small           |
| 11.3 | Step 11 executor         | `steps/step_11_area_overdesign.py`                  | 11.1       | Medium          |
| 11.4 | Step 11 validation rules | `steps/step_11_rules.py`                            | 11.1, 11.3 | Small           |
| 11.5 | Pipeline wiring          | `core/pipeline_runner.py` (add to PIPELINE_STEPS)   | 11.3, 11.4 | Small           |
| 11.6 | Unit tests               | `tests/unit/test_step_11_*.py`                      | All above  | Medium          |

---

## Sub-Step 11.1: DesignState Fields

**File:** `hx_engine/app/models/design_state.py` (modify existing)

### New Fields to Add

```python
# --- area + overdesign (populated by Step 11) ---
area_required_m2: Optional[float] = None       # Q / (U_dirty × F × LMTD)
area_provided_m2: Optional[float] = None       # π × d_o × L × N_t
overdesign_pct: Optional[float] = None          # (A_provided - A_required) / A_required × 100
A_estimated_vs_required_pct: Optional[float] = None  # (A_m2 - area_required_m2) / area_required_m2 × 100
```

### Placement

After the Step 10 pressure drop fields block, before the pipeline state fields
(`current_step`, `completed_steps`, etc.).

---

## Sub-Step 11.2: Pipeline Runner Mapping

**File:** `hx_engine/app/core/pipeline_runner.py` (modify `_apply_outputs`)

### Add to `mapping` dict

```python
# Step 11 area + overdesign
"area_required_m2": "area_required_m2",
"area_provided_m2": "area_provided_m2",
"overdesign_pct": "overdesign_pct",
"A_estimated_vs_required_pct": "A_estimated_vs_required_pct",
```

Place after the Step 10 pressure drop mappings.

---

## Sub-Step 11.3: Step 11 Executor

**File:** `hx_engine/app/steps/step_11_area_overdesign.py`

### Class Definition

```python
class Step11AreaOverdesign(BaseStep):
    step_id: int = 11
    step_name: str = "Area and Overdesign"
    ai_mode: AIModeEnum = AIModeEnum.CONDITIONAL
```

### Module-Level Constants

```python
# Overdesign thresholds
_OVERDESIGN_AI_LOW = 8.0      # AI trigger below this %
_OVERDESIGN_AI_HIGH = 30.0    # AI trigger above this %
_OVERDESIGN_IDEAL_LOW = 10.0  # Ideal range lower bound %
_OVERDESIGN_IDEAL_HIGH = 25.0 # Ideal range upper bound %
_OVERDESIGN_WARN_HIGH = 40.0  # Warning threshold %
```

### AI Call Logic

```python
def _should_call_ai(self, state: "DesignState") -> bool:
    if state.in_convergence_loop:
        return False
    return self._conditional_ai_trigger(state)

def _conditional_ai_trigger(self, state: "DesignState") -> bool:
    """Call AI when overdesign is outside the 8–30% comfort zone."""
    if state.overdesign_pct is None:
        return False
    if state.overdesign_pct < _OVERDESIGN_AI_LOW:
        return True
    if state.overdesign_pct > _OVERDESIGN_AI_HIGH:
        return True
    return False
```

### Precondition Checks

Step 11 requires outputs from prior steps. Check for:

| Field           | Source   | Why Needed                                       |
| --------------- | -------- | ------------------------------------------------ |
| `Q_W`           | Step 2   | Numerator of A_required                          |
| `LMTD_K`        | Step 5   | Denominator of A_required                        |
| `F_factor`      | Step 5   | Denominator of A_required                        |
| `U_dirty_W_m2K` | Step 9   | Denominator of A_required                        |
| `geometry`      | Step 4/6 | tube_od_m, tube_length_m, n_tubes for A_provided |

```python
@staticmethod
def _check_preconditions(state: "DesignState") -> list[str]:
    missing: list[str] = []
    if state.Q_W is None:
        missing.append("Q_W (Step 2)")
    if state.LMTD_K is None:
        missing.append("LMTD_K (Step 5)")
    if state.F_factor is None:
        missing.append("F_factor (Step 5)")
    if state.U_dirty_W_m2K is None:
        missing.append("U_dirty_W_m2K (Step 9)")
    if state.geometry is None:
        missing.append("geometry (Step 4/6)")
    else:
        g = state.geometry
        if g.tube_od_m is None:
            missing.append("geometry.tube_od_m")
        if g.tube_length_m is None:
            missing.append("geometry.tube_length_m")
        if g.n_tubes is None:
            missing.append("geometry.n_tubes")
    return missing
```

### Execute Method — Calculation Flow

```
1. Precondition check → raise CalculationError if missing
2. Compute A_required = Q / (U_dirty × F × LMTD)
3. Compute A_provided = π × d_o × L × N_t
4. Compute overdesign_pct = (A_provided - A_required) / A_required × 100
5. Compute A_estimated_vs_required_pct = (A_m2 - A_required) / A_required × 100
   (only if state.A_m2 is not None — Step 6 estimate)
6. Generate warnings:
   - overdesign < 0% → "Exchanger is undersized"
   - overdesign > 40% → "Excessive overdesign — cost concern"
   - |A_estimated_vs_required_pct| > 30% → "Initial U estimate significantly off"
7. Write to state (area_required_m2, area_provided_m2, overdesign_pct, A_estimated_vs_required_pct)
8. Return StepResult with all outputs
```

### Outputs Dict Keys

```python
{
    "area_required_m2":             float,  # always
    "area_provided_m2":             float,  # always
    "overdesign_pct":               float,  # always (can be negative)
    "A_estimated_vs_required_pct":  float,  # only if A_m2 exists
}
```

### Edge Cases to Handle

1. **U_dirty is very small** → A_required becomes very large → overdesign is deeply negative.
   Not a bug — the geometry genuinely undersizes the duty. Let Layer 2 catch it.

2. **F_factor × LMTD is near zero** → Division by near-zero in A_required.
   Guard: if `F_factor * LMTD_K < 1e-6`, raise `CalculationError` with message
   explaining that effective temperature driving force is essentially zero.

3. **Overdesign is negative on first pass** — This is expected before Step 12 converges.
   Don't raise an error in execute; let Layer 2 rule handle the hard fail.

4. **A_m2 is None** — Step 6 failed or was skipped. `A_estimated_vs_required_pct`
   should be `None`, not an error.

---

## Sub-Step 11.4: Step 11 Validation Rules

**File:** `hx_engine/app/steps/step_11_rules.py`

### Rules

Follow the exact pattern from `step_10_rules.py`:

| Rule ID | Check                                            | Severity  |
| ------- | ------------------------------------------------ | --------- |
| R1      | `area_required_m2` > 0                           | Hard fail |
| R2      | `area_provided_m2` > 0                           | Hard fail |
| R3      | `overdesign_pct` >= 0 (exchanger not undersized) | Hard fail |

#### R1 — Required area must be positive

```python
def _rule_area_required_positive(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    val = result.outputs.get("area_required_m2")
    if val is None:
        return False, "area_required_m2 is missing from Step 11 outputs"
    if val <= 0:
        return False, f"Required area must be positive, got {val:.4f} m²"
    return True, None
```

#### R2 — Provided area must be positive

```python
def _rule_area_provided_positive(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    val = result.outputs.get("area_provided_m2")
    if val is None:
        return False, "area_provided_m2 is missing from Step 11 outputs"
    if val <= 0:
        return False, f"Provided area must be positive, got {val:.4f} m²"
    return True, None
```

#### R3 — Overdesign must not be negative (exchanger must not be undersized)

```python
def _rule_overdesign_not_negative(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    val = result.outputs.get("overdesign_pct")
    if val is None:
        return False, "overdesign_pct is missing from Step 11 outputs"
    if val < 0:
        return False, (
            f"Overdesign is {val:.1f}% — exchanger is undersized. "
            f"Need more area or higher U."
        )
    return True, None
```

### Registration

```python
def register_step11_rules() -> None:
    register_rule(11, _rule_area_required_positive)
    register_rule(11, _rule_area_provided_positive)
    register_rule(11, _rule_overdesign_not_negative)

register_step11_rules()
```

### Auto-Registration

Import `step_11_rules` in `step_11_area_overdesign.py` at module level
(same pattern as Step 10):

```python
import hx_engine.app.steps.step_11_rules  # noqa: F401
```

---

## Sub-Step 11.5: Pipeline Wiring

**File:** `hx_engine/app/core/pipeline_runner.py`

### Changes

1. **Import:**

   ```python
   from hx_engine.app.steps.step_11_area_overdesign import Step11AreaOverdesign
   ```

2. **Add to `PIPELINE_STEPS`:**

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
       Step10PressureDrops,
       Step11AreaOverdesign,    # ← new
   ]
   ```

3. **Add output mapping** (per Sub-Step 11.2 above).

---

## Sub-Step 11.6: Unit Tests

**File:** `tests/unit/test_step_11_area_overdesign.py`

### Test Cases

#### T1: `test_basic_overdesign_calculation`

- **Setup:** Mock state with known Q, LMTD, F, U_dirty, geometry (n_tubes, d_o, L)
- **Expected:** A_required, A_provided, overdesign_pct all correct to ±0.1%
- **Validates:** Core arithmetic is right

**Worked example:**

- Q = 500,000 W, LMTD = 30 K, F = 0.9, U_dirty = 300 W/m²K
- A_required = 500000 / (300 × 0.9 × 30) = 61.73 m²
- Geometry: 200 tubes, d_o = 0.01905 m, L = 6.0 m
- A_provided = π × 0.01905 × 6.0 × 200 = 71.82 m²
- overdesign = (71.82 − 61.73) / 61.73 × 100 = 16.34%

#### T2: `test_undersized_exchanger_negative_overdesign`

- **Setup:** Geometry that provides less area than required
- **Expected:** `overdesign_pct` is negative; Layer 2 rule R3 fails
- **Validates:** Negative overdesign is not an error in execute(), but fails validation

#### T3: `test_perfect_sizing_zero_overdesign`

- **Setup:** A_provided exactly equals A_required
- **Expected:** `overdesign_pct` = 0.0; Layer 2 passes (≥ 0)
- **Validates:** Edge case at boundary

#### T4: `test_excessive_overdesign_warning`

- **Setup:** overdesign > 40%
- **Expected:** Warning in result.warnings about excessive overdesign
- **Validates:** Warning generation

#### T5: `test_a_estimated_vs_required_diagnostic`

- **Setup:** state.A_m2 = 50 (from Step 6), area_required = 62
- **Expected:** A_estimated_vs_required_pct ≈ -19.4%
- **Validates:** Diagnostic field captures how far off the initial estimate was

#### T6: `test_a_estimated_none_when_step6_missing`

- **Setup:** state.A_m2 = None
- **Expected:** A_estimated_vs_required_pct is None, no error
- **Validates:** Graceful handling when Step 6 estimate is absent

#### T7: `test_ai_triggered_low_overdesign`

- **Setup:** overdesign = 5% (below 8% threshold)
- **Expected:** `_should_call_ai()` returns True (not in convergence loop)
- **Validates:** AI trigger threshold — low side

#### T8: `test_ai_triggered_high_overdesign`

- **Setup:** overdesign = 35% (above 30% threshold)
- **Expected:** `_should_call_ai()` returns True
- **Validates:** AI trigger threshold — high side

#### T9: `test_ai_skipped_in_convergence_loop`

- **Setup:** overdesign = 5% (would trigger AI), `in_convergence_loop=True`
- **Expected:** `_should_call_ai()` returns False
- **Validates:** Convergence loop AI skip

#### T10: `test_ai_not_triggered_ideal_range`

- **Setup:** overdesign = 18% (within 8–30%)
- **Expected:** `_should_call_ai()` returns False
- **Validates:** AI not called when everything is fine

#### T11: `test_precondition_missing_u_dirty`

- **Setup:** state.U_dirty_W_m2K = None
- **Expected:** `CalculationError` raised listing the missing field
- **Validates:** Precondition check catches missing Step 9 output

#### T12: `test_precondition_missing_geometry`

- **Setup:** state.geometry = None
- **Expected:** `CalculationError` raised
- **Validates:** Precondition check catches missing geometry

#### T13: `test_near_zero_driving_force_guard`

- **Setup:** F_factor = 0.75, LMTD = 0.001 (near-zero product)
- **Expected:** `CalculationError` with meaningful message about zero driving force
- **Validates:** Guard against division by near-zero

#### T14: `test_outputs_written_to_state`

- **Setup:** Run full execute, check state fields after
- **Expected:** `state.area_required_m2`, `state.area_provided_m2`,
  `state.overdesign_pct`, `state.A_estimated_vs_required_pct` all populated
- **Validates:** State mutation happens correctly

### Rules Tests

**File:** `tests/unit/test_step_11_rules.py` (or included in same file)

| Test                               | Input          | Expected |
| ---------------------------------- | -------------- | -------- |
| `test_rule_area_required_positive` | area_req = 50  | PASS     |
| `test_rule_area_required_zero`     | area_req = 0   | FAIL     |
| `test_rule_area_required_missing`  | key absent     | FAIL     |
| `test_rule_area_provided_positive` | area_prov = 60 | PASS     |
| `test_rule_overdesign_positive`    | od = 15%       | PASS     |
| `test_rule_overdesign_negative`    | od = -5%       | FAIL     |
| `test_rule_overdesign_zero`        | od = 0%        | PASS     |

---

## File Dependency Graph

```
Sub-Step 11.1 (DesignState fields)
    │
    ├── Sub-Step 11.2 (pipeline runner mapping)
    │
    └── Sub-Step 11.3 (executor)
            │
            ├── Sub-Step 11.4 (rules)
            │
            └── Sub-Step 11.5 (pipeline wiring)
                    │
                    └── Sub-Step 11.6 (tests)
```

---

## Implementation Checklist

- [ ] **11.1** Add 4 new fields to `DesignState` (`area_required_m2`, `area_provided_m2`, `overdesign_pct`, `A_estimated_vs_required_pct`)
- [ ] **11.2** Add 4 output mappings to `_apply_outputs` in `pipeline_runner.py`
- [ ] **11.3** Create `step_11_area_overdesign.py` with `Step11AreaOverdesign` class
- [ ] **11.4** Create `step_11_rules.py` with 3 hard rules + registration
- [ ] **11.5** Wire Step 11 into `PIPELINE_STEPS` + import
- [ ] **11.6** Create unit tests (14 executor tests + 7 rules tests)
- [ ] Run full test suite — ensure Steps 1–10 tests still pass
- [ ] Run Step 11 tests — all green
