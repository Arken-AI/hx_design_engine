# Step 9 Implementation Plan: Overall U + Resistance Breakdown

**Status:** Planning  
**Depends on:** Steps 7 & 8 complete, MaterialPropertyAdapter (from SUPERMEMORY_IMPLEMENTATION_PLAN.md)  
**AI Mode:** FULL (always called outside convergence loop)  
**Convergence Behavior:** AI skipped when `in_convergence_loop=True`  
**Reference:** ARKEN_MASTER_PLAN.md §6.3, STEPS_6_16_PLAN.md Phase A

---

## Table of Contents

1. [What Step 9 Does](#1-what-step-9-does)
2. [Formula & Engineering Background](#2-formula--engineering-background)
3. [Inputs (from DesignState)](#3-inputs-from-designstate)
4. [Outputs (written to DesignState)](#4-outputs-written-to-designstate)
5. [Layer 1: Execute — Calculation Logic](#5-layer-1-execute--calculation-logic)
6. [Layer 2: Validation Rules](#6-layer-2-validation-rules)
7. [Layer 3: AI Review](#7-layer-3-ai-review)
8. [Layer 4: State Update](#8-layer-4-state-update)
9. [Convergence Loop Behavior](#9-convergence-loop-behavior)
10. [ht Library Usage](#10-ht-library-usage)
11. [Kern Cross-Check U](#11-kern-cross-check-u)
12. [File Inventory](#12-file-inventory)
13. [Preconditions](#13-preconditions)
14. [DesignState Changes](#14-designstate-changes)
15. [AI Prompt Template](#15-ai-prompt-template)
16. [Pipeline Runner Changes](#16-pipeline-runner-changes)
17. [Test Plan](#17-test-plan)
18. [Edge Cases](#18-edge-cases)
19. [Build Sequence](#19-build-sequence)

---

## 1. What Step 9 Does

Step 9 is the **aggregation step**. It takes the individual thermal resistances computed in Steps 4–8 and assembles them into the overall heat transfer coefficient (U). It answers three questions:

1. **What's the calculated U?** — Compare against the Step 6 initial estimate
2. **What's controlling the design?** — Which resistance is the bottleneck?
3. **Is U reasonable?** — Cross-check against Kern method and typical ranges

This is the "moment of truth" where all previous steps' outputs combine into a single design-critical number. If U_calculated differs significantly from U_estimated (Step 6), the geometry is wrong and Step 12 convergence will need to iterate.

---

## 2. Formula & Engineering Background

### 2.1 Overall U (referenced to outside tube surface)

$$\frac{1}{U_o} = \frac{1}{h_o} + R_{f,o} + \frac{d_o \ln(d_o / d_i)}{2 k_w} + R_{f,i} \cdot \frac{d_o}{d_i} + \frac{1}{h_i} \cdot \frac{d_o}{d_i}$$

Where:

- $h_o$ = shell-side film coefficient (Step 8, Bell-Delaware) [W/m²·K]
- $h_i$ = tube-side film coefficient (Step 7, Gnielinski/Hausen) [W/m²·K]
- $R_{f,o}$ = shell-side (outer) fouling resistance [m²·K/W]
- $R_{f,i}$ = tube-side (inner) fouling resistance [m²·K/W]
- $d_o$ = tube outer diameter [m]
- $d_i$ = tube inner diameter [m]
- $k_w$ = tube wall thermal conductivity [W/m·K]

### 2.2 Why the d_o/d_i Ratio?

For cylindrical geometry, inner resistances must be converted to the outer reference area. The ratio $d_o / d_i$ accounts for the area difference between inner and outer tube surfaces. This is standard per Serth Chapter 3 and Kern Chapter 11.

### 2.3 Clean vs Dirty U

- **U_clean:** Computed WITHOUT fouling terms ($R_{f,o} = R_{f,i} = 0$)
- **U_dirty:** Computed WITH fouling terms (this is the design U — `U_calculated`)
- **Cleanliness Factor:** $CF = U_{dirty} / U_{clean}$ — typical range 0.75–0.95

The cleanliness factor tells how much of U is "lost" to fouling. If CF < 0.60, fouling dominates — the exchanger is designed more for dirt than for heat transfer.

### 2.4 Wall Resistance Term

Using the `ht` library's `R_cylinder()` function:

$$R_{wall} = R\_{cylinder}(d_i, d_o, k_w, L=1)$$

This computes $\frac{\ln(d_o / d_i)}{2 \pi k_w}$ for unit length. We then convert to area-based resistance: $R_{wall, area} = R_{wall} \cdot \pi \cdot d_o$ to get the per-unit-area resistance referenced to the outer surface.

Alternatively, the direct formula $\frac{d_o \ln(d_o / d_i)}{2 k_w}$ is used. Both are equivalent — `R_cylinder` provides the validated math.

### 2.5 Resistance Breakdown

Each term in the 1/U equation is a resistance. Express each as a percentage of total 1/U:

| Resistance         | Symbol                      | Typical Range |
| ------------------ | --------------------------- | ------------- |
| Shell-side film    | $1/h_o$                     | 15–40%        |
| Tube-side film     | $(d_o/d_i)/h_i$             | 15–40%        |
| Shell-side fouling | $R_{f,o}$                   | 5–25%         |
| Tube-side fouling  | $R_{f,i} \cdot d_o/d_i$     | 5–25%         |
| Wall conduction    | $d_o \ln(d_o/d_i) / (2k_w)$ | 1–15%         |

**Engineering insight:** The controlling resistance depends on the fluid pair:

- **Oil/water:** Shell-side film + fouling dominate (oil is viscous)
- **Gas/liquid:** Gas-side film dominates (gases have low h)
- **Water/water:** Fouling often dominates (both films are high)
- **Exotic alloy tubes:** Wall resistance becomes significant (k=15 for Inconel)

---

## 3. Inputs (from DesignState)

All inputs are already on DesignState from previous steps. Step 9 reads — does not call external services in Layer 1.

| Input                  | Field on State                | Source Step               | Required?                 |
| ---------------------- | ----------------------------- | ------------------------- | ------------------------- |
| Shell-side h           | `h_shell_W_m2K`               | Step 8                    | Yes                       |
| Tube-side h            | `h_tube_W_m2K`                | Step 7                    | Yes                       |
| Shell-side fouling R_f | depends on `shell_side_fluid` | Step 4                    | Yes                       |
| Tube-side fouling R_f  | depends on `shell_side_fluid` | Step 4                    | Yes                       |
| Tube OD                | `geometry.tube_od_m`          | Step 4/6                  | Yes                       |
| Tube ID                | `geometry.tube_id_m`          | Step 4/6                  | Yes                       |
| Shell-side fluid       | `shell_side_fluid`            | Step 4                    | Yes                       |
| R_f hot                | `R_f_hot_m2KW`                | Step 4                    | Yes                       |
| R_f cold               | `R_f_cold_m2KW`               | Step 4                    | Yes                       |
| Kern shell-side h      | `h_shell_kern_W_m2K`          | Step 8                    | Optional                  |
| Initial U estimate     | `U_W_m2K`                     | Step 6                    | Optional (for comparison) |
| Tube material          | `tube_material`               | None (resolved in Step 9) | No (defaults)             |
| k_wall                 | `k_wall_W_mK`                 | None (resolved in Step 9) | No (defaults)             |

### 3.1 Fouling Mapping: Hot/Cold → Inner/Outer

This is critical. The formula uses $R_{f,o}$ (outer = shell-side) and $R_{f,i}$ (inner = tube-side). DesignState stores `R_f_hot_m2KW` and `R_f_cold_m2KW`. The mapping depends on fluid allocation:

```python
if state.shell_side_fluid == "hot":
    R_f_outer = state.R_f_hot_m2KW    # shell = hot fluid
    R_f_inner = state.R_f_cold_m2KW   # tube = cold fluid
else:  # shell_side_fluid == "cold"
    R_f_outer = state.R_f_cold_m2KW   # shell = cold fluid
    R_f_inner = state.R_f_hot_m2KW    # tube = hot fluid
```

---

## 4. Outputs (written to DesignState)

### 4.1 New Fields

| Field                          | Type    | Description                                 |
| ------------------------------ | ------- | ------------------------------------------- | ------------------------------------------ |
| `U_clean_W_m2K`                | `float` | U without fouling                           |
| `U_dirty_W_m2K`                | `float` | U with fouling (= U_calculated)             |
| `U_overall_W_m2K`              | `float` | Alias for U_dirty (the "design" U)          |
| `cleanliness_factor`           | `float` | U_dirty / U_clean, range [0, 1]             |
| `resistance_breakdown`         | `dict`  | Each resistance as % of total 1/U           |
| `controlling_resistance`       | `str`   | Name of largest resistance                  |
| `tube_material`                | `str`   | Resolved material name                      |
| `k_wall_W_mK`                  | `float` | Tube wall thermal conductivity              |
| `k_wall_source`                | `str`   | Source of k_w ("ASME..." or "stub_default") |
| `k_wall_confidence`            | `float` | Confidence in k_w value                     |
| `U_kern_W_m2K`                 | `float  | None`                                       | Kern-based overall U (if h_kern available) |
| `U_kern_deviation_pct`         | `float  | None`                                       | Deviation between BD and Kern U            |
| `U_vs_estimated_deviation_pct` | `float` | Deviation from Step 6 initial estimate      |

### 4.2 Resistance Breakdown Structure

```python
resistance_breakdown = {
    "shell_film": {
        "value_m2KW": 1 / h_o,
        "pct": ...,
    },
    "tube_film": {
        "value_m2KW": (d_o / d_i) / h_i,
        "pct": ...,
    },
    "shell_fouling": {
        "value_m2KW": R_f_outer,
        "pct": ...,
    },
    "tube_fouling": {
        "value_m2KW": R_f_inner * (d_o / d_i),
        "pct": ...,
    },
    "wall": {
        "value_m2KW": d_o * log(d_o / d_i) / (2 * k_w),
        "pct": ...,
    },
    "total_1_over_U": ...,
}
```

---

## 5. Layer 1: Execute — Calculation Logic

### 5.1 Class Definition

```python
class Step09OverallU(BaseStep):
    step_id: int = 9
    step_name: str = "Overall Heat Transfer Coefficient"
    ai_mode: AIModeEnum = AIModeEnum.FULL

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        """Check upstream outputs exist."""

    def _conditional_ai_trigger(self, state: "DesignState") -> bool:
        """
        Returns False when in_convergence_loop=True.
        This skips AI during Step 12 iterations while keeping ai_mode=FULL.
        Outside convergence, AI is always called.
        """
        return not state.in_convergence_loop

    async def execute(self, state: "DesignState") -> StepResult:
        """Layer 1: Pure calculation of overall U and resistance breakdown."""
```

### 5.2 Execute Flow (Pseudocode)

```
1. Precondition check
   - Require: h_shell_W_m2K, h_tube_W_m2K, geometry (tube_od, tube_id),
     R_f_hot_m2KW, R_f_cold_m2KW, shell_side_fluid
   - Fail with CalculationError if any missing

2. Resolve tube material and k_wall
   a. If state.k_wall_W_mK already set → use it (from prior step or convergence iteration)
   b. Else → use MaterialPropertyAdapter.get_k_wall()
      - Determines material from resolve_material_from_fluid()
      - Queries Supermemory → stub fallback
   c. Store material props on state

3. Map fouling resistances to inner/outer
   - Based on state.shell_side_fluid ("hot" or "cold")

4. Compute individual resistances (all in m²·K/W, outer reference)
   R_shell_film = 1 / h_shell
   R_tube_film  = (d_o / d_i) / h_tube
   R_shell_foul = R_f_outer
   R_tube_foul  = R_f_inner * (d_o / d_i)
   R_wall       = d_o * ln(d_o / d_i) / (2 * k_w)

5. Compute 1/U and U
   total_dirty = sum of all 5 resistances
   total_clean = total_dirty - R_shell_foul - R_tube_foul
   U_dirty = 1 / total_dirty
   U_clean = 1 / total_clean

6. Compute cleanliness factor
   CF = U_dirty / U_clean

7. Compute resistance breakdown (each as % of total)

8. Identify controlling resistance (largest %)

9. Compute Kern cross-check U (if h_shell_kern available)
   Same formula, replacing h_shell with h_shell_kern
   deviation_pct = abs(U_dirty - U_kern) / U_dirty * 100

10. Compute deviation from Step 6 estimate
    deviation_from_est = (U_dirty - U_estimated) / U_estimated * 100

11. Write k_wall results to state:
    state.tube_material = material_name
    state.k_wall_W_mK = k_w
    state.k_wall_source = source
    state.k_wall_confidence = confidence

12. Build outputs dict + warnings list
    Return StepResult
```

### 5.3 Warnings Generation

```python
warnings = []

if CF < 0.65:
    warnings.append(f"Cleanliness factor {CF:.2f} is low — fouling dominates design")

if k_wall_source == "stub_default":
    warnings.append(f"Tube wall conductivity from stub default ({k_w} W/mK) — "
                     "ASME data unavailable, verify material")

if U_kern_deviation_pct and U_kern_deviation_pct > 15:
    warnings.append(f"Bell-Delaware/Kern U deviation: {U_kern_deviation_pct:.1f}% — "
                     "check geometry assumptions")

if abs(U_vs_estimated_deviation_pct) > 30:
    warnings.append(f"Calculated U deviates {U_vs_estimated_deviation_pct:.1f}% from "
                     f"Step 6 estimate — geometry iteration likely needed")

if wall_pct > 10:
    warnings.append(f"Wall resistance is {wall_pct:.1f}% of total — "
                     "verify tube material selection")
```

### 5.4 Escalation Hints

```python
escalation_hints = []

if U_dirty < 50:
    escalation_hints.append("U < 50 W/m²K — extremely low, check for gas-side controlling")

if U_kern_deviation_pct and U_kern_deviation_pct > 25:
    escalation_hints.append(f"BD/Kern U deviation {U_kern_deviation_pct:.1f}% > 25% — "
                             "geometry may have issues")

if CF < 0.50:
    escalation_hints.append(f"CF = {CF:.2f} — fouling resistance exceeds all other "
                             "resistances combined, review fouling assumptions")
```

---

## 6. Layer 2: Validation Rules

**File:** `hx_engine/app/steps/step_09_rules.py`

| Rule ID | Check                     | Fail Message                                            |
| ------- | ------------------------- | ------------------------------------------------------- |
| R1      | `U_dirty > 0`             | "Calculated U must be positive"                         |
| R2      | `U_clean > 0`             | "Clean U must be positive"                              |
| R3      | `U_clean >= U_dirty`      | "Clean U must be ≥ dirty U (fouling reduces U)"         |
| R4      | `0.5 <= CF <= 1.0`        | "Cleanliness factor outside physical bounds [0.5, 1.0]" |
| R5      | All 5 resistances > 0     | "All individual resistances must be positive"           |
| R6      | Sum of pct ≈ 100% (±0.5%) | "Resistance percentages must sum to ~100%"              |

### Rule Signatures

```python
def _rule_u_dirty_positive(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    u = result.outputs.get("U_dirty_W_m2K")
    if u is None or u <= 0:
        return False, "Calculated U (dirty) must be positive"
    return True, None

def _rule_u_clean_ge_dirty(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    u_clean = result.outputs.get("U_clean_W_m2K")
    u_dirty = result.outputs.get("U_dirty_W_m2K")
    if u_clean is not None and u_dirty is not None and u_clean < u_dirty - 0.01:
        return False, "Clean U must be ≥ dirty U (fouling can only reduce U)"
    return True, None

def _rule_cleanliness_factor_bounds(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    cf = result.outputs.get("cleanliness_factor")
    if cf is not None and (cf < 0.5 or cf > 1.0):
        return False, f"Cleanliness factor {cf:.3f} outside bounds [0.5, 1.0]"
    return True, None

def _rule_resistances_positive(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    breakdown = result.outputs.get("resistance_breakdown", {})
    for name, data in breakdown.items():
        if name == "total_1_over_U":
            continue
        val = data.get("value_m2KW", 0) if isinstance(data, dict) else 0
        if val < 0:
            return False, f"Resistance '{name}' is negative ({val})"
    return True, None

def _rule_pct_sum(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    breakdown = result.outputs.get("resistance_breakdown", {})
    pct_sum = sum(
        data.get("pct", 0) for name, data in breakdown.items()
        if isinstance(data, dict) and name != "total_1_over_U"
    )
    if abs(pct_sum - 100.0) > 0.5:
        return False, f"Resistance percentages sum to {pct_sum:.1f}%, expected ~100%"
    return True, None

def register_step9_rules() -> None:
    register_rule(9, _rule_u_dirty_positive)
    register_rule(9, _rule_u_clean_ge_dirty)
    register_rule(9, _rule_cleanliness_factor_bounds)
    register_rule(9, _rule_resistances_positive)
    register_rule(9, _rule_pct_sum)

# Auto-register on import
register_step9_rules()
```

---

## 7. Layer 3: AI Review

### 7.1 AI Mode Behavior

```python
ai_mode = AIModeEnum.FULL

def _conditional_ai_trigger(self, state: "DesignState") -> bool:
    """
    FULL mode means AI is always called — _conditional_ai_trigger is the
    only override that can skip it. We skip during convergence iterations
    since intermediate U values are meaningless. The final converged U
    gets the full AI review after Step 12 exits.
    """
    return not state.in_convergence_loop
```

**How this works with BaseStep.\_should_call_ai():**

Looking at `base.py`:

- `ai_mode=FULL` → `_should_call_ai()` returns True always
- BUT `_conditional_ai_trigger()` is only checked for `CONDITIONAL` mode

**Important:** We need to verify the BaseStep flow. If FULL mode bypasses
`_conditional_ai_trigger()`, we have two options:

**Option A:** Override `_should_call_ai()` directly in Step09:

```python
def _should_call_ai(self, state: "DesignState") -> bool:
    if state.in_convergence_loop:
        return False
    return True  # FULL mode — always call outside convergence
```

**Option B:** Change ai_mode to CONDITIONAL and always return True from trigger except in convergence:

```python
ai_mode = AIModeEnum.CONDITIONAL

def _conditional_ai_trigger(self, state: "DesignState") -> bool:
    return not state.in_convergence_loop
```

**Decision required at implementation time:** Check BaseStep.\_should_call_ai() to determine which approach is needed. The behavior should be: AI always called outside convergence, never called inside convergence.

### 7.2 What the AI Reviews

| Judgment                         | What AI Checks                                                                                                 |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| U in typical range?              | Compare U_dirty against fluid-pair typical ranges (from book context)                                          |
| Resistance breakdown sensible?   | For oil/water, tube film + fouling should dominate. If wall is 40%, flag it.                                   |
| Controlling resistance expected? | Shell film for viscous shell-side, tube film for viscous tube-side                                             |
| Kern cross-check                 | If BD/Kern U deviation > 15%, note concern. > 25% → consider ESCALATE                                          |
| k_w source reliable?             | If stub default → WARN. If ASME → high confidence                                                              |
| CF reasonable?                   | < 0.65 → heavy fouling service, verify assumptions. > 0.95 → very clean, verify fouling factors aren't too low |
| U vs Step 6 estimate             | Large deviation signals iteration needed — note but don't escalate (Step 12 handles this)                      |

### 7.3 AI Can Correct

| Correction     | When                                                    | Effect                                                 |
| -------------- | ------------------------------------------------------- | ------------------------------------------------------ |
| Tube material  | AI sees fluid is corrosive but k_w is carbon steel      | Changes `tube_material` + `k_wall_W_mK` → re-execute   |
| Fouling factor | AI sees fouling dominates but R_f seems low for service | Changes `R_f_hot_m2KW` or `R_f_cold_m2KW` → re-execute |

### 7.4 AI Step Prompt

Add to `_STEP_PROMPTS[9]` in `ai_engineer.py`:

```
You are reviewing Step 9: Overall Heat Transfer Coefficient.

This step aggregates all thermal resistances into the overall U value.
You are checking whether:
1. The calculated U falls within the typical range for this fluid pair
2. The resistance breakdown is physically sensible
3. The controlling resistance matches expectations for this service
4. The Bell-Delaware vs Kern deviation is acceptable
5. The tube material and wall conductivity are appropriate for the fluids

IMPORTANT:
- Do NOT escalate because U differs from the Step 6 estimate.
  That deviation is expected and is handled by Step 12 convergence.
- Focus on whether the individual resistance values are physically reasonable.
- If wall resistance exceeds 10% and material is carbon steel, verify
  the service doesn't require an exotic alloy.
```

### 7.5 Step Context Builder

Add to `ai_engineer.py` `_build_step_context()`:

```python
if step.step_id == 9:
    u_est = state.U_W_m2K  # Step 6 estimate
    u_calc = result.outputs.get("U_dirty_W_m2K")
    parts = []
    if u_est and u_calc:
        dev = (u_calc - u_est) / u_est * 100
        parts.append(f"Step 6 estimated U: {u_est:.1f} W/m²K")
        parts.append(f"Deviation from estimate: {dev:+.1f}%")
    cf = result.outputs.get("cleanliness_factor")
    if cf:
        parts.append(f"Cleanliness factor: {cf:.3f}")
    ctrl = result.outputs.get("controlling_resistance")
    if ctrl:
        parts.append(f"Controlling resistance: {ctrl}")
    k_src = result.outputs.get("k_wall_source")
    if k_src:
        parts.append(f"Wall conductivity source: {k_src}")
    return "\n".join(parts)
```

---

## 8. Layer 4: State Update

### 8.1 Direct State Writes (in execute)

Step 9 writes material properties directly to state (same pattern as Step 8 writing h_shell):

```python
# In execute(), after material resolution:
state.tube_material = material_props.material_name
state.k_wall_W_mK = material_props.k_wall_W_mK
state.k_wall_source = material_props.source
state.k_wall_confidence = material_props.confidence
```

### 8.2 Output Mapping (in pipeline_runner)

The remaining outputs go through `_apply_outputs()` in pipeline_runner.py.

Add to the mapping dict:

```python
# Step 9 outputs
"U_clean_W_m2K": "U_clean_W_m2K",
"U_dirty_W_m2K": "U_dirty_W_m2K",
"U_overall_W_m2K": "U_overall_W_m2K",
"cleanliness_factor": "cleanliness_factor",
"resistance_breakdown": "resistance_breakdown",
"controlling_resistance": "controlling_resistance",
"U_kern_W_m2K": "U_kern_W_m2K",
"U_kern_deviation_pct": "U_kern_deviation_pct",
"U_vs_estimated_deviation_pct": "U_vs_estimated_deviation_pct",
```

---

## 9. Convergence Loop Behavior

### 9.1 During Step 12 Convergence (in_convergence_loop=True)

- `_should_call_ai()` or `_conditional_ai_trigger()` returns False
- Step 9 executes Layer 1 (pure math) only
- Layer 2 rules still checked
- No AI review — no 2-3s latency per iteration
- State is updated with new U values each iteration
- `k_wall_W_mK` is already on state from first iteration — NOT re-resolved

### 9.2 After Convergence (in_convergence_loop=False)

- AI is called with FULL review
- Sees the final converged U + resistance breakdown
- Can correct if needed (which would trigger another convergence cycle if in Step 12 scope)
- This is the AI's one chance to validate U — make it count

### 9.3 Material Resolution Optimization

```python
# In execute():
if state.k_wall_W_mK is not None:
    # Already resolved (from prior iteration or prior step)
    k_w = state.k_wall_W_mK
else:
    # First time — resolve via adapter
    material_props = await self._resolve_material(state)
    k_w = material_props.k_wall_W_mK
    # Write to state so convergence iterations skip this
    state.tube_material = material_props.material_name
    state.k_wall_W_mK = k_w
    state.k_wall_source = material_props.source
    state.k_wall_confidence = material_props.confidence
```

---

## 10. ht Library Usage

### 10.1 R_cylinder for Wall Resistance

The `ht` library (already installed, v1.2.0) provides `R_cylinder()`:

```python
from ht.conduction import R_cylinder

# R_cylinder(Di, Do, k, L) → thermal resistance [K/W] for unit length
R_wall_per_length = R_cylinder(d_i, d_o, k_w, L=1.0)
# = ln(d_o/d_i) / (2π × k_w) for L=1

# Convert to area-based resistance [m²·K/W] referenced to outer surface:
R_wall_area = d_o * math.log(d_o / d_i) / (2 * k_w)
```

**Note:** `R_cylinder` computes $\frac{\ln(D_o/D_i)}{2\pi k L}$ which is a total resistance in K/W. For the per-area resistance used in the U formula, we use the direct formula. `R_cylinder` serves as a cross-check:

```python
# Cross-check:
R_from_ht = R_cylinder(d_i, d_o, k_w, 1.0)  # K/W per meter length
R_from_formula = d_o * log(d_o / d_i) / (2 * k_w)  # m²·K/W per area
# Relationship: R_from_formula = R_from_ht × π × d_o  (they should match)
```

### 10.2 Why ht Over Manual Formula?

- `R_cylinder` is validated against Bergman/Incropera textbook
- Same ecosystem as `thermo` and `chemicals` (Caleb Bell)
- Already installed — no new dependency
- Provides a sanity check for our direct formula implementation

### 10.3 Implementation Strategy

Use the direct formula for the main calculation (it's what the engineering reference uses). Use `R_cylinder` as an assertion/cross-check in tests.

---

## 11. Kern Cross-Check U

### 11.1 When Available

Step 8 stores `h_shell_kern_W_m2K` if the Kern cross-check was computed. Step 9 uses it to compute a Kern-based overall U.

### 11.2 Calculation

Same formula as the main U, but with `h_shell_kern` replacing `h_shell`:

```python
if state.h_shell_kern_W_m2K is not None:
    h_o_kern = state.h_shell_kern_W_m2K
    R_shell_film_kern = 1.0 / h_o_kern
    total_dirty_kern = R_shell_film_kern + R_tube_film + R_shell_foul + R_tube_foul + R_wall
    U_kern = 1.0 / total_dirty_kern
    deviation_pct = abs(U_dirty - U_kern) / U_dirty * 100
```

### 11.3 Interpretation

| Deviation | Meaning                                                               |
| --------- | --------------------------------------------------------------------- |
| < 10%     | Good agreement — geometry is well-characterized                       |
| 10-20%    | Typical — Bell-Delaware accounts for bypass/leakage that Kern doesn't |
| 20-30%    | Notable — AI should flag this                                         |
| > 30%     | Suspicious — possible geometry error, AI should consider ESCALATE     |

---

## 12. File Inventory

### New Files

| File                                       | Purpose                        | Lines (est.) |
| ------------------------------------------ | ------------------------------ | ------------ |
| `hx_engine/app/steps/step_09_overall_u.py` | Step 9 executor                | ~200         |
| `hx_engine/app/steps/step_09_rules.py`     | Layer 2 validation rules       | ~80          |
| `tests/unit/test_step_09_execute.py`       | Unit tests for Layer 1         | ~250         |
| `tests/unit/test_step_09_rules.py`         | Rule validation tests          | ~100         |
| `tests/unit/test_step_09_convergence.py`   | Convergence loop AI skip tests | ~80          |

### Modified Files

| File                                    | Change                                                   |
| --------------------------------------- | -------------------------------------------------------- |
| `hx_engine/app/models/design_state.py`  | Add Step 9 output fields + material fields               |
| `hx_engine/app/core/pipeline_runner.py` | Add Step09 to PIPELINE_STEPS, add output mapping         |
| `hx_engine/app/core/ai_engineer.py`     | Add `_STEP_PROMPTS[9]` + step context builder for step 9 |
| `requirements.txt`                      | (ht already installed — no change needed)                |

### Dependencies (from Supermemory plan)

| File                                         | Change                  | Needed For         |
| -------------------------------------------- | ----------------------- | ------------------ |
| `hx_engine/app/adapters/material_adapter.py` | MaterialPropertyAdapter | k_w resolution     |
| `hx_engine/app/adapters/memory_client.py`    | MemoryClient            | Supermemory access |

---

## 13. Preconditions

Step 9 requires these fields on DesignState:

```python
@staticmethod
def _check_preconditions(state: "DesignState") -> list[str]:
    missing = []
    if state.h_shell_W_m2K is None:
        missing.append("h_shell_W_m2K (Step 8)")
    if state.h_tube_W_m2K is None:
        missing.append("h_tube_W_m2K (Step 7)")
    if state.geometry is None:
        missing.append("geometry (Step 4/6)")
    elif state.geometry.tube_od_m is None or state.geometry.tube_id_m is None:
        missing.append("tube dimensions (tube_od_m, tube_id_m)")
    if state.R_f_hot_m2KW is None:
        missing.append("R_f_hot_m2KW (Step 4)")
    if state.R_f_cold_m2KW is None:
        missing.append("R_f_cold_m2KW (Step 4)")
    if state.shell_side_fluid is None:
        missing.append("shell_side_fluid (Step 4)")
    return missing
```

---

## 14. DesignState Changes

Add to `DesignState` in `design_state.py`:

```python
# Step 9 outputs
U_clean_W_m2K: Optional[float] = None
U_dirty_W_m2K: Optional[float] = None
U_overall_W_m2K: Optional[float] = None
cleanliness_factor: Optional[float] = None
resistance_breakdown: Optional[dict] = None
controlling_resistance: Optional[str] = None
U_kern_W_m2K: Optional[float] = None
U_kern_deviation_pct: Optional[float] = None
U_vs_estimated_deviation_pct: Optional[float] = None

# Material properties (resolved by Step 9 via MaterialPropertyAdapter)
tube_material: Optional[str] = None
k_wall_W_mK: Optional[float] = None
k_wall_source: Optional[str] = None
k_wall_confidence: Optional[float] = None
```

---

## 15. AI Prompt Template

Full system prompt addition for Step 9 (added to `_STEP_PROMPTS[9]`):

```
Step 9: Overall Heat Transfer Coefficient + Resistance Breakdown

ROLE: You are reviewing the aggregation of all thermal resistances into
the overall U value. This is the critical checkpoint where Steps 7–8
film coefficients, Step 4 fouling factors, and tube wall conduction
combine into the design U.

FORMULA REVIEWED:
  1/U_o = 1/h_o + R_f,o + (d_o × ln(d_o/d_i))/(2×k_w) + R_f,i×(d_o/d_i) + (d_o/d_i)/h_i

KEY CHECKS:
1. Is U_dirty in the typical range for this fluid pair?
   - Water/water: 800–1500 W/m²K
   - Oil/water: 100–350 W/m²K
   - Gas/liquid: 20–250 W/m²K
   - Oil/oil: 60–150 W/m²K

2. Is the controlling resistance physically expected?
   - Viscous fluid side should dominate
   - Gas side should dominate for gas/liquid service
   - If wall resistance > 10%, verify material

3. Kern cross-check (if available):
   - < 15% deviation: normal
   - 15–25% deviation: WARN
   - > 25% deviation: consider ESCALATE

4. Cleanliness factor:
   - 0.80–0.95: typical
   - < 0.65: heavy fouling — verify assumptions
   - > 0.95: very clean — verify R_f not underestimated

5. Tube material: If k_wall_source is "stub_default", WARN that
   ASME-sourced data was unavailable.

DO NOT ESCALATE because U_dirty ≠ U_estimated (Step 6). That deviation
is normal and handled by Step 12 convergence. Only escalate if the
individual resistance values are physically unreasonable.

CORRECTIONS YOU CAN MAKE:
- Change tube_material if fluids suggest corrosion risk but carbon steel was used
- Adjust fouling factor if breakdown shows fouling is unreasonably high/low
- NOTE: Do not change h_tube or h_shell — those are Step 7/8 outputs

RESPOND WITH: {decision, confidence, reasoning, correction, user_summary}
```

---

## 16. Pipeline Runner Changes

### 16.1 Add Step to Pipeline

```python
from hx_engine.app.steps.step_09_overall_u import Step09OverallU

PIPELINE_STEPS = [
    Step01Requirements, Step02HeatDuty, Step03FluidProperties,
    Step04TEMAGeometry, Step05LMTD, Step06InitialU, Step07TubeSideH,
    Step08ShellSideH, Step09OverallU,     # <-- ADD
]
```

### 16.2 Add Output Mapping

Add to the `_apply_outputs` mapping dict:

```python
"U_clean_W_m2K": "U_clean_W_m2K",
"U_dirty_W_m2K": "U_dirty_W_m2K",
"U_overall_W_m2K": "U_overall_W_m2K",
"cleanliness_factor": "cleanliness_factor",
"resistance_breakdown": "resistance_breakdown",
"controlling_resistance": "controlling_resistance",
"U_kern_W_m2K": "U_kern_W_m2K",
"U_kern_deviation_pct": "U_kern_deviation_pct",
"U_vs_estimated_deviation_pct": "U_vs_estimated_deviation_pct",
```

**Note:** `tube_material`, `k_wall_W_mK`, `k_wall_source`, `k_wall_confidence` are written directly in `execute()` (same pattern as Step 8 writing h_shell fields directly).

---

## 17. Test Plan

### 17.1 Unit Tests: Layer 1 Calculation

**File:** `tests/unit/test_step_09_execute.py`

| Test                                   | Description                                   | Key Assertion                        |
| -------------------------------------- | --------------------------------------------- | ------------------------------------ |
| `test_water_water_u`                   | Water/water, h_o=3000, h_i=5000, carbon steel | U_dirty ≈ expected (hand-calculated) |
| `test_oil_water_u`                     | Oil shell / water tube, h_o=500, h_i=4000     | Shell film dominates (>30%)          |
| `test_gas_liquid_u`                    | Gas shell / water tube, h_o=100, h_i=4000     | Shell film dominates (>50%)          |
| `test_stainless_wall_impact`           | Same as water/water but stainless (k=16)      | Wall pct > 5% (vs ~1% for CS)        |
| `test_copper_wall_negligible`          | Copper tubes (k=385)                          | Wall pct < 0.5%                      |
| `test_clean_ge_dirty`                  | Any case                                      | U_clean >= U_dirty                   |
| `test_cf_range`                        | Any case                                      | 0.5 <= CF <= 1.0                     |
| `test_pct_sum_100`                     | Any case                                      | Sum of pct ≈ 100%                    |
| `test_fouling_mapping_hot_shell`       | shell_side_fluid="hot"                        | R_f_outer = R_f_hot                  |
| `test_fouling_mapping_cold_shell`      | shell_side_fluid="cold"                       | R_f_outer = R_f_cold                 |
| `test_kern_crosscheck_computed`        | h_shell_kern on state                         | U_kern and deviation populated       |
| `test_kern_crosscheck_missing`         | h_shell_kern=None                             | U_kern is None, no error             |
| `test_u_vs_estimate_deviation`         | U_est=400, U_calc=350                         | deviation = -12.5%                   |
| `test_material_resolved_on_first_call` | k_wall not on state                           | Adapter called, state updated        |
| `test_material_cached_on_second_call`  | k_wall already on state                       | Adapter NOT called                   |

### 17.2 Unit Tests: Layer 2 Rules

**File:** `tests/unit/test_step_09_rules.py`

| Test                                  | Description                     |
| ------------------------------------- | ------------------------------- |
| `test_rule_u_dirty_positive_pass`     | U_dirty=350 → pass              |
| `test_rule_u_dirty_positive_fail`     | U_dirty=-10 → fail              |
| `test_rule_u_clean_ge_dirty_pass`     | U_clean=500, U_dirty=350 → pass |
| `test_rule_u_clean_ge_dirty_fail`     | U_clean=300, U_dirty=350 → fail |
| `test_rule_cf_bounds_pass`            | CF=0.80 → pass                  |
| `test_rule_cf_bounds_fail_low`        | CF=0.40 → fail                  |
| `test_rule_cf_bounds_fail_high`       | CF=1.05 → fail                  |
| `test_rule_resistances_positive_pass` | All > 0 → pass                  |
| `test_rule_resistances_positive_fail` | One negative → fail             |
| `test_rule_pct_sum_pass`              | Sum=100.0 → pass                |
| `test_rule_pct_sum_fail`              | Sum=85.0 → fail                 |

### 17.3 Convergence Behavior Tests

**File:** `tests/unit/test_step_09_convergence.py`

| Test                                       | Description                                |
| ------------------------------------------ | ------------------------------------------ |
| `test_ai_skipped_in_convergence`           | `in_convergence_loop=True` → AI not called |
| `test_ai_called_outside_convergence`       | `in_convergence_loop=False` → AI called    |
| `test_k_wall_not_reresolve_in_convergence` | k_wall on state → adapter not called again |

### 17.4 Cross-Check with ht Library

**File:** Within `test_step_09_execute.py`

```python
def test_wall_resistance_matches_ht():
    """Verify our wall resistance formula matches ht.R_cylinder."""
    from ht.conduction import R_cylinder
    d_o, d_i, k_w = 0.01905, 0.01575, 50.0
    R_formula = d_o * math.log(d_o / d_i) / (2 * k_w)
    R_ht = R_cylinder(d_i, d_o, k_w, 1.0) * math.pi * d_o
    assert abs(R_formula - R_ht) / R_formula < 0.001  # < 0.1% difference
```

---

## 18. Edge Cases

| Case                         | Handling                                                                                                                    |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `d_o == d_i`                 | Precondition check: `tube_od > tube_id` required. `ln(d_o/d_i)` = 0 → zero wall resistance.                                 |
| `h_i` or `h_o` = 0           | Precondition check catches this (from Steps 7/8). Division by zero prevented.                                               |
| `R_f = 0`                    | Valid (perfectly clean service). U_clean == U_dirty. CF = 1.0.                                                              |
| Very high h (>50,000)        | Film resistance approaches zero. Other terms dominate. Physically valid for boiling/condensing (future).                    |
| Very low k_w (<10)           | Wall resistance becomes large. Warn if >15% of total. AI reviews.                                                           |
| `h_shell_kern = None`        | Skip Kern cross-check. Set `U_kern_W_m2K = None`. No error.                                                                 |
| `U_estimated = None`         | Skip deviation calculation. Set `U_vs_estimated_deviation_pct = None`.                                                      |
| Supermemory down             | MaterialPropertyAdapter falls back to stub. `k_wall_source = "stub_default"`, `needs_ai_review = True`. AI flags in review. |
| Exotic material not in stubs | Default to carbon steel + WARNING. AI should catch material mismatch.                                                       |

---

## 19. Build Sequence

```
Phase 1: Foundation (can start immediately)
  1. Add DesignState fields (Step 9 outputs + material fields)
  2. Build MaterialPropertyAdapter (stub mode only — no Supermemory wiring)
  3. Unit test MaterialPropertyAdapter

Phase 2: Core Step (depends on Phase 1)
  4. Build step_09_overall_u.py (Layer 1 execute)
  5. Build step_09_rules.py (Layer 2 rules)
  6. Unit test Layer 1 (calculation correctness)
  7. Unit test Layer 2 (rule pass/fail)

Phase 3: Integration (depends on Phase 2)
  8. Add Step 9 to pipeline_runner.py (PIPELINE_STEPS + output mapping)
  9. Add AI prompt (_STEP_PROMPTS[9] + step context builder)
  10. Convergence behavior tests
  11. Run existing pipeline tests to verify no regression

Phase 4: Supermemory Wiring (depends on SUPERMEMORY_IMPLEMENTATION_PLAN.md)
  12. Wire MaterialPropertyAdapter to live Supermemory
  13. Ingest ASME PDF
  14. Validate retrieval quality
  15. Switch from stub to live adapter
```

**Steps 1–11 can proceed now.** Steps 12–15 depend on the Supermemory pipeline being operational.
