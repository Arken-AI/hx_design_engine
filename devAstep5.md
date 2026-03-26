# Dev A — Step 5: Determine LMTD and F-Factor — Implementation Plan

## Overview

Step 5 takes the four terminal temperatures from Step 1/2 and the geometry (shell passes, tube passes) from Step 4 to compute the **Log Mean Temperature Difference (LMTD)** and its **correction factor F**. The product `F × LMTD` is the effective temperature driving force used in all downstream sizing calculations (Steps 6–16).

This is a **CONDITIONAL AI** step — AI is only called when any of these conditions are met:

1. **F < 0.85** (borderline region) — but if auto-correction bumped shell_passes 1→2, only trigger if the _corrected_ F is still **< 0.80**
2. **R > 4.0** (highly asymmetric duty — F-P curve is steep and sensitive to small P changes)
3. **Approach temperature < 3°C** (T_hot_out − T_cold_out < 3°C — temperature cross risk)

**AI constraint (Option C):** The auto-correction within `execute()` handles the shell_passes 1→2 bump entirely. AI review should only **WARN** or **ESCALATE** about shell passes — never **CORRECT** them. This avoids the state mutation timing issue where `BaseStep.run_with_review_loop()` applies corrections to `result.outputs` but not to `state.geometry` before re-execution.

### Dependencies (must exist before Step 5)

- ✅ `DesignState` model — exists
- ✅ `StepResult` / `BaseStep` framework — exists
- ✅ `Step01Requirements` — exists (provides T_hot_in_C, T_hot_out_C, T_cold_in_C, T_cold_out_C)
- ✅ `Step02HeatDuty` — exists (provides Q_W)
- ✅ `Step03FluidProperties` — exists (provides fluid_props)
- ✅ `Step04TEMAGeometry` — exists (provides geometry with shell_passes, n_passes)
- ✅ `GeometrySpec.shell_passes` — exists, validated to {1, 2}
- ✅ `GeometrySpec.n_passes` — exists, validated to {1, 2, 4, 6, 8}
- ✅ `DesignState.LMTD_K` — exists (field to populate)
- ❌ `DesignState.F_factor` — **needs to be added**
- ❌ `hx_engine/app/correlations/` directory — **needs to be created**
- ❌ `correlations/lmtd.py` — **needs to be created** (pure math functions)
- ❌ `steps/step_05_lmtd.py` — **needs to be created**
- ❌ `steps/step_05_rules.py` — **needs to be created**

### What Step 5 Produces (outputs dict)

```python
{
    "LMTD_K": float,           # Log Mean Temperature Difference (K or °C — same magnitude)
    "F_factor": float,          # Correction factor (0, 1.0]
    "effective_LMTD": float,    # F × LMTD — the actual driving force
    "R": float,                 # Dimensionless heat capacity ratio
    "P": float,                 # Dimensionless effectiveness
    "shell_passes": int,        # Possibly updated from 1→2 if auto-corrected
    "auto_corrected": bool,     # True if shell_passes was changed
    "escalation_hints": list,    # Context hints for AI review (F borderline, high R, temp cross)
}
```

### Computation Flow Summary

```
Temperatures (Steps 1-2) + Geometry (Step 4)
    ↓
┌─ LMTD Calculation ──┐    ┌─ R & P Ratios ──┐    ┌─ F-Factor ──────────┐
│ ΔT₁ = Th,in - Tc,out│    │ R = ΔT_hot /    │    │ Bowman formula      │
│ ΔT₂ = Th,out - Tc,in│ →  │     ΔT_cold     │ →  │ (analytical, exact) │
│ LMTD = (ΔT₁-ΔT₂) / │    │ P = ΔT_cold /   │    │ Corner cases: R=1,  │
│        ln(ΔT₁/ΔT₂)  │    │     (Th,in-Tc,in)│    │ domain violation    │
└──────────────────────┘    └──────────────────┘    └──────────┬──────────┘
                                                               │
                                                    F < 0.80 and shell_passes=1?
                                                       Yes → try shell_passes=2
                                                               │
                                                    ┌──────────▼──────────┐
                                                    │ Output:             │
                                                    │  LMTD_K, F_factor,  │
                                                    │  effective_LMTD,     │
                                                    │  R, P, shell_passes  │
                                                    └─────────────────────┘
```

---

## Piece 0: Model Update — Add `F_factor` to DesignState

**What:** Add the `F_factor` field to `DesignState` so Step 5 can persist it for consumption by Steps 6–16.

**File to modify:**

- `hx_engine/app/models/design_state.py`

**Changes to `DesignState`:**

| Field      | Type              | Default | Location                | Why                               |
| ---------- | ----------------- | ------- | ----------------------- | --------------------------------- |
| `F_factor` | `Optional[float]` | `None`  | Thermal results section | F-factor for downstream area calc |

Add immediately after `LMTD_K`:

```python
    # --- thermal results (populated by later steps) ---
    Q_W: Optional[float] = None
    LMTD_K: Optional[float] = None
    F_factor: Optional[float] = None          # ← NEW
    U_W_m2K: Optional[float] = None
    A_m2: Optional[float] = None
```

**Why not store R and P on DesignState?**

R and P are intermediate values derived entirely from the 4 temperatures. No downstream step needs them directly — Steps 6–16 use `F_factor` and `LMTD_K`. Storing them would bloat the state with redundant data. They go in `StepResult.outputs` only (for audit logging).

**Testing Plan (3 tests):**

| #   | Test                                       | What it validates                            | Physics check                        |
| --- | ------------------------------------------ | -------------------------------------------- | ------------------------------------ |
| 1   | `test_design_state_f_factor_default_none`  | `DesignState().F_factor is None`             | Not set until Step 5 runs            |
| 2   | `test_design_state_f_factor_accepts_valid` | `DesignState(F_factor=0.92)` → no error      | Valid F value stored                 |
| 3   | `test_design_state_f_factor_roundtrips`    | Set F_factor, dump to JSON, load back → same | Serialization doesn't lose the field |

**Regression gate:** Run `pytest tests/unit/test_design_state.py` — all existing tests must still pass (adding an Optional field with default None changes nothing for existing consumers).

---

## Piece 1: Create `correlations/lmtd.py` — Pure Math Functions

**What:** Create the `correlations/` directory and `lmtd.py` containing 4 pure math functions. These have **zero side effects**, **zero imports from models**, and are independently testable.

**Files to create:**

- `hx_engine/app/correlations/__init__.py` — empty
- `hx_engine/app/correlations/lmtd.py`

### Function 1: `compute_lmtd`

```python
def compute_lmtd(T_hot_in: float, T_hot_out: float,
                 T_cold_in: float, T_cold_out: float) -> float:
    """Log Mean Temperature Difference for counter-current flow.

    Args:
        T_hot_in, T_hot_out: Hot stream inlet/outlet (°C or K)
        T_cold_in, T_cold_out: Cold stream inlet/outlet (°C or K)

    Returns:
        LMTD in same units as input temperatures (°C difference = K difference)

    Raises:
        ValueError: Temperature cross (ΔT₁ ≤ 0 or ΔT₂ ≤ 0)
    """
```

**Formula:**

$$\text{LMTD} = \frac{\Delta T_1 - \Delta T_2}{\ln\!\left(\frac{\Delta T_1}{\Delta T_2}\right)}$$

where $\Delta T_1 = T_{h,in} - T_{c,out}$ and $\Delta T_2 = T_{h,out} - T_{c,in}$ (counter-current arrangement).

**Corner cases:**

| Condition                       | Handling                                 | Why                            |
| ------------------------------- | ---------------------------------------- | ------------------------------ |
| ΔT₁ = ΔT₂ (within 1e-6)         | Return arithmetic mean `(ΔT₁ + ΔT₂) / 2` | Avoids `0 / ln(1) = 0/0`       |
| ΔT₁ ≤ 0 or ΔT₂ ≤ 0              | Raise `ValueError("Temperature cross")`  | No heat transfer driving force |
| ΔT₁ or ΔT₂ very small (< 1e-10) | Raise `ValueError`                       | Numerically unstable           |

### Function 2: `compute_R`

```python
def compute_R(T_hot_in: float, T_hot_out: float,
              T_cold_in: float, T_cold_out: float) -> float:
    """Dimensionless heat capacity ratio.

    R = (T_hot_in - T_hot_out) / (T_cold_out - T_cold_in)

    R > 0 always (both ΔTs are positive for valid designs).
    R = 1.0 means equal heat capacity rates (symmetric duty).
    R > 1 means hot side has smaller ΔT range (larger mass flow × Cp).
    """
```

**Corner case:** If `T_cold_out == T_cold_in` (zero cold-side ΔT), raise `ValueError("Cold side ΔT is zero — cannot compute R")`. This would mean no heat was absorbed by the cold stream, which is physically invalid.

### Function 3: `compute_P`

```python
def compute_P(T_hot_in: float, T_hot_out: float,
              T_cold_in: float, T_cold_out: float) -> float:
    """Dimensionless thermal effectiveness.

    P = (T_cold_out - T_cold_in) / (T_hot_in - T_cold_in)

    P ∈ (0, 1) always. P = 0 means no heat transferred.
    P → 1 means cold outlet approaches hot inlet (maximum theoretical).
    """
```

**Corner case:** If `T_hot_in == T_cold_in`, raise `ValueError`. This means no initial temperature difference — no driving force.

### Function 4: `compute_f_factor`

This is the core — the Bowman-Nagle-Underwood analytical formula.

```python
def compute_f_factor(R: float, P: float, n_shell_passes: int = 1) -> float:
    """F-factor correction for multi-pass shell-and-tube exchangers.

    Uses the Bowman (1940) analytical formula. Works for ANY even number
    of tube passes (2, 4, 6, 8). F depends ONLY on R, P, and
    n_shell_passes — tube pass count does NOT affect F.

    Args:
        R: Heat capacity ratio (> 0)
        P: Thermal effectiveness (0 < P < 1)
        n_shell_passes: Number of shell passes (1 or 2)

    Returns:
        F in range [0.0, 1.0]. Returns 0.0 for infeasible configurations.
    """
```

**Mathematical specification:**

**Case 1: n_shell_passes = 2 (or N) — Convert P to equivalent single-shell P₁ first:**

For $R \neq 1$:

$$P_1 = \frac{1 - \left(\frac{1-RP}{1-P}\right)^{1/N}}{R - \left(\frac{1-RP}{1-P}\right)^{1/N}}$$

For $R = 1$ (within 1e-6):

$$P_1 = \frac{P}{N - (N-1) \cdot P}$$

Then proceed with the 1-shell formula using $P_1$ instead of $P$.

**Case 2: Standard Bowman formula (1 shell pass, R ≠ 1):**

$$F = \frac{\sqrt{R^2 + 1} \cdot \ln\!\left(\frac{1 - P}{1 - RP}\right)}{(R - 1) \cdot \ln\!\left(\frac{2 - P\!\left(R + 1 - \sqrt{R^2+1}\right)}{2 - P\!\left(R + 1 + \sqrt{R^2+1}\right)}\right)}$$

**Case 3: R = 1.0 exactly (L'Hôpital limit):**

$$F\big|_{R=1} = \frac{\sqrt{2} \cdot \dfrac{P}{1-P}}{\ln\!\left(\dfrac{2 - P(2 - \sqrt{2})}{2 - P(2 + \sqrt{2})}\right)}$$

**Case 4: Domain violation — ln argument ≤ 0:**

When evaluating the denominator `ln(...)`, if the argument is ≤ 0, the configuration is physically infeasible for this flow arrangement. Return `F = 0.0`.

**Case 5: F < 0 or F > 1.0 (numerical artifact):**

Clamp: if `F < 0`, return `0.0`. If `F > 1.0` (by tiny floating-point overshoot), return `1.0`.

**Implementation pseudocode:**

```python
def compute_f_factor(R: float, P: float, n_shell_passes: int = 1) -> float:
    if P <= 0 or P >= 1:
        return 0.0  # No heat transfer or exceeds maximum effectiveness

    if R <= 0:
        return 0.0  # Invalid

    # --- Multi-shell: convert P to equivalent single-shell P₁ ---
    if n_shell_passes > 1:
        P = _equivalent_P1(R, P, n_shell_passes)
        if P <= 0 or P >= 1:
            return 0.0

    # --- R ≈ 1.0: L'Hôpital limit ---
    if abs(R - 1.0) < 1e-6:
        return _f_factor_R_equals_1(P)

    # --- General Bowman formula ---
    sqrt_term = math.sqrt(R**2 + 1)

    # Numerator
    num_ln_arg = (1 - P) / (1 - R * P)
    if num_ln_arg <= 0:
        return 0.0  # RP ≥ 1 → infeasible
    numerator = sqrt_term * math.log(num_ln_arg)

    # Denominator
    A = 2 - P * (R + 1 - sqrt_term)
    B = 2 - P * (R + 1 + sqrt_term)
    if B == 0 or A / B <= 0:
        return 0.0  # Domain violation
    denominator = (R - 1) * math.log(A / B)

    if abs(denominator) < 1e-15:
        return 0.0  # Degenerate

    F = numerator / denominator

    # Clamp to valid range
    return max(0.0, min(1.0, F))
```

**Private helpers:**

```python
def _equivalent_P1(R: float, P: float, N: int) -> float:
    """Convert overall effectiveness P to single-shell equivalent P₁."""
    if abs(R - 1.0) < 1e-6:
        return P / (N - (N - 1) * P)

    ratio = ((1 - R * P) / (1 - P)) ** (1.0 / N)
    denom = R - ratio
    if abs(denom) < 1e-15:
        return 0.0  # Degenerate
    return (1 - ratio) / denom


def _f_factor_R_equals_1(P: float) -> float:
    """F-factor when R = 1.0 (L'Hôpital limit)."""
    sqrt2 = math.sqrt(2)
    numer = sqrt2 * P / (1 - P)

    A = 2 - P * (2 - sqrt2)
    B = 2 - P * (2 + sqrt2)
    if B == 0 or A / B <= 0:
        return 0.0
    denom = math.log(A / B)

    if abs(denom) < 1e-15:
        return 0.0
    return numer / denom
```

**Testing Plan (14 tests):**

| #   | Test                                       | Input                                | Expected                           | Physics assertion                                  |
| --- | ------------------------------------------ | ------------------------------------ | ---------------------------------- | -------------------------------------------------- |
| 1   | `test_lmtd_benchmark_countercurrent`       | 150/90°C hot, 30/55°C cold           | LMTD ≈ 76.1°C (within 0.1%)        | Hand-calculated reference value                    |
| 2   | `test_lmtd_equal_delta_t`                  | ΔT₁ = ΔT₂ = 60°C                     | Returns 60.0 exactly               | Arithmetic mean fallback — no NaN                  |
| 3   | `test_lmtd_temperature_cross_raises`       | T_cold_out > T_hot_in                | `ValueError`                       | Temperature cross = physics violation              |
| 4   | `test_lmtd_negative_delta_t_raises`        | T_hot_out < T_cold_in                | `ValueError`                       | Negative ΔT₂ is invalid                            |
| 5   | `test_lmtd_very_small_valid`               | ΔT₁=4, ΔT₂=3                         | ≈ 3.47°C (within 0.5%)             | Small LMTD is valid, just expensive                |
| 6   | `test_lmtd_between_min_max_delta_t`        | Various temp sets                    | min(ΔT₁,ΔT₂) ≤ LMTD ≤ max(ΔT₁,ΔT₂) | Log mean always lies between the two ΔTs           |
| 7   | `test_R_normal_computation`                | 150/90, 30/55                        | R = 60/25 = 2.4                    | Direct from definition                             |
| 8   | `test_P_normal_computation`                | 150/90, 30/55                        | P = 25/120 ≈ 0.2083                | Direct from definition                             |
| 9   | `test_P_always_between_0_and_1`            | Multiple temp sets                   | 0 < P < 1                          | P is bounded by thermodynamic limits               |
| 10  | `test_f_factor_1_shell_normal`             | R=2.4, P=0.208, 1 shell              | F ≈ 0.945 (within 1%)              | Textbook value for 1-2 exchanger                   |
| 11  | `test_f_factor_R_equals_1_no_crash`        | R=1.0 exactly, P=0.3, 1 shell        | F ∈ (0.75, 1.0] and not NaN        | L'Hôpital limit works correctly                    |
| 12  | `test_f_factor_2_shells_improves`          | Same R, P with 1 shell vs 2 shells   | F₂ₛₕₑₗₗ > F₁ₛₕₑₗₗ                  | More shells = more counter-current = higher F      |
| 13  | `test_f_factor_domain_violation_returns_0` | R, P that makes ln argument negative | F = 0.0                            | Infeasible config detected gracefully              |
| 14  | `test_f_factor_clamped_to_0_1`             | Various edge cases                   | 0.0 ≤ F ≤ 1.0                      | F cannot exceed 1.0 (pure counter-current ceiling) |

**Cross-cutting physics invariants for ALL Piece 1 tests:**

1. LMTD is always between min(ΔT₁, ΔT₂) and max(ΔT₁, ΔT₂) — the log mean lies between the two terminal differences
2. LMTD is symmetric in units — if inputs are °C, output is °C; if inputs are K, output is K (same magnitude since it's a difference)
3. F is dimensionless and bounded: `0.0 ≤ F ≤ 1.0`
4. F = 1.0 only for pure counter-current (1 tube pass, 1 shell pass)
5. Increasing shell passes never decreases F (more counter-current character)
6. R > 0 and 0 < P < 1 for all physically valid cases

---

## Piece 2: Create `step_05_rules.py` — Layer 2 Hard Rules

**What:** Validation rules that AI **cannot** override. These are absolute thermodynamic and engineering constraints. Registered for `step_id=5`.

**File to create:**

- `hx_engine/app/steps/step_05_rules.py`

**Rules:**

| Rule | Check              | Threshold             | Error message                                      | Why it's a hard rule                                     |
| ---- | ------------------ | --------------------- | -------------------------------------------------- | -------------------------------------------------------- |
| R1   | `LMTD_K > 0`       | LMTD must be positive | "LMTD must be > 0, got {val}"                      | No heat transfer driving force if LMTD ≤ 0               |
| R2   | `F_factor >= 0.75` | Hard minimum          | "F-factor {val} < 0.75 — design infeasible"        | Below 0.75 the exchanger is too thermally inefficient    |
| R3   | `F_factor <= 1.0`  | Hard maximum          | "F-factor {val} > 1.0 — mathematically impossible" | F > 1.0 violates thermodynamics (counter-current is max) |
| R4   | `R > 0`            | Must be positive      | "R must be > 0, got {val}"                         | Both ΔTs must be positive for valid heat exchange        |
| R5   | `P > 0 and P < 1`  | Strict bounds         | "P={val} outside valid range (0, 1)"               | P = 0 means no heat transfer, P ≥ 1 violates 2nd law     |

**Implementation pattern** (follows `step_04_rules.py` exactly):

```python
"""Layer 2 validation rules for Step 5 (LMTD + F-Factor).

These are hard thermodynamic rules that AI **cannot** override.
"""

from hx_engine.app.core.validation_rules import register_rule
from hx_engine.app.models.step_result import StepResult


def _rule_lmtd_positive(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    val = result.outputs.get("LMTD_K")
    if val is None:
        return False, "LMTD_K is missing from Step 5 outputs"
    if val <= 0:
        return False, f"LMTD must be > 0, got {val:.4f} — no heat transfer driving force"
    return True, None


def _rule_f_factor_minimum(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    val = result.outputs.get("F_factor")
    if val is None:
        return False, "F_factor is missing from Step 5 outputs"
    if val < 0.75:
        return False, (
            f"F-factor = {val:.4f} < 0.75 — exchanger configuration is thermally "
            f"infeasible. Even with 2 shell passes, F is too low. Consider: "
            f"(1) reducing temperature cross, (2) different TEMA configuration, "
            f"or (3) splitting into multiple units."
        )
    return True, None


def _rule_f_factor_maximum(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    val = result.outputs.get("F_factor")
    if val is not None and val > 1.0 + 1e-9:
        return False, f"F-factor = {val:.4f} > 1.0 — mathematically impossible"
    return True, None


def _rule_R_positive(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    val = result.outputs.get("R")
    if val is not None and val <= 0:
        return False, f"R = {val:.4f} must be > 0 — invalid temperature data"
    return True, None


def _rule_P_in_range(step_id: int, result: StepResult) -> tuple[bool, str | None]:
    val = result.outputs.get("P")
    if val is not None:
        if val <= 0 or val >= 1:
            return False, f"P = {val:.4f} outside valid range (0, 1) — check temperatures"
    return True, None


def register_step5_rules() -> None:
    """Register all Step 5 hard rules. Call at module import."""
    register_rule(5, _rule_lmtd_positive)
    register_rule(5, _rule_f_factor_minimum)
    register_rule(5, _rule_f_factor_maximum)
    register_rule(5, _rule_R_positive)
    register_rule(5, _rule_P_in_range)


# Auto-register on import
register_step5_rules()
```

**Testing Plan (10 tests):**

| #   | Test                             | Input                | Expected  | Physics assertion                           |
| --- | -------------------------------- | -------------------- | --------- | ------------------------------------------- |
| 1   | `test_rule_lmtd_positive_passes` | LMTD_K = 73.1        | Passes    | Valid driving force                         |
| 2   | `test_rule_lmtd_zero_fails`      | LMTD_K = 0.0         | Hard fail | No driving force                            |
| 3   | `test_rule_lmtd_negative_fails`  | LMTD_K = -5.0        | Hard fail | Negative LMTD is physically impossible      |
| 4   | `test_rule_lmtd_missing_fails`   | No LMTD_K in outputs | Hard fail | Step must produce LMTD                      |
| 5   | `test_rule_f_above_075_passes`   | F_factor = 0.92      | Passes    | Good thermal efficiency                     |
| 6   | `test_rule_f_below_075_fails`    | F_factor = 0.70      | Hard fail | Design is infeasible                        |
| 7   | `test_rule_f_above_1_fails`      | F_factor = 1.05      | Hard fail | Violates thermodynamics                     |
| 8   | `test_rule_R_positive_passes`    | R = 2.4              | Passes    | Valid heat capacity ratio                   |
| 9   | `test_rule_P_in_range_passes`    | P = 0.208            | Passes    | Valid effectiveness                         |
| 10  | `test_rule_P_out_of_range_fails` | P = 1.1              | Hard fail | P ≥ 1 violates second law of thermodynamics |

---

## Piece 3: Create `step_05_lmtd.py` — Core Step Logic

**What:** The main `Step05LMTD` class. This is the Layer 1 calculation + auto-correction + conditional AI trigger. Follows the same pattern as `Step04TEMAGeometry`.

**File to create:**

- `hx_engine/app/steps/step_05_lmtd.py`

### Pre-condition Checks

Step 5 requires these fields from Steps 1–4:

| Field                   | Source   | Check                                       |
| ----------------------- | -------- | ------------------------------------------- |
| `T_hot_in_C`            | Step 1   | Must not be None                            |
| `T_hot_out_C`           | Step 1/2 | Must not be None                            |
| `T_cold_in_C`           | Step 1   | Must not be None                            |
| `T_cold_out_C`          | Step 1/2 | Must not be None                            |
| `Q_W`                   | Step 2   | Must not be None and > 0                    |
| `geometry`              | Step 4   | Must not be None                            |
| `geometry.n_passes`     | Step 4   | Must not be None (needed for F=1.0 check)   |
| `geometry.shell_passes` | Step 4   | Must not be None (needed for F computation) |

If any are missing, raise `CalculationError(5, "Step 5 requires ... from Steps 1-4")` with a clear message listing the missing fields.

### Algorithm (execute method)

```python
class Step05LMTD(BaseStep):
    step_id: int = 5
    step_name: str = "LMTD & F-Factor"
    ai_mode: AIModeEnum = AIModeEnum.CONDITIONAL

    async def execute(self, state: DesignState) -> StepResult:
        # 1. Pre-condition checks
        missing = self._check_preconditions(state)
        if missing:
            raise CalculationError(5, f"Missing from prior steps: {', '.join(missing)}")

        warnings = []

        # 2. Compute LMTD
        LMTD = compute_lmtd(
            state.T_hot_in_C, state.T_hot_out_C,
            state.T_cold_in_C, state.T_cold_out_C,
        )

        # 3. Very small LMTD warning
        if LMTD < 3.0:
            warnings.append(
                f"LMTD = {LMTD:.2f}°C is very small (< 3°C). "
                f"This requires a very large heat transfer area. "
                f"May not be economically viable."
            )

        # 4. Pure counter-current short circuit
        n_passes = state.geometry.n_passes
        shell_passes = state.geometry.shell_passes or 1

        if n_passes == 1 and shell_passes == 1:
            # True counter-current — F = 1.0 exactly
            return self._build_result(
                LMTD_K=LMTD, F_factor=1.0, R=None, P=None,
                shell_passes=shell_passes, auto_corrected=False,
                warnings=warnings,
            )

        # 5. Compute R and P
        R = compute_R(
            state.T_hot_in_C, state.T_hot_out_C,
            state.T_cold_in_C, state.T_cold_out_C,
        )
        P = compute_P(
            state.T_hot_in_C, state.T_hot_out_C,
            state.T_cold_in_C, state.T_cold_out_C,
        )

        # 6. Compute F-factor
        F = compute_f_factor(R, P, n_shell_passes=shell_passes)

        # 7. Auto-correction: try 2 shell passes if F is poor
        auto_corrected = False
        if F < 0.80 and shell_passes == 1:
            F_2shell = compute_f_factor(R, P, n_shell_passes=2)
            if F_2shell >= 0.75:  # Improvement worth taking
                warnings.append(
                    f"F-factor with 1 shell pass = {F:.4f} (< 0.80). "
                    f"Increased to 2 shell passes → F = {F_2shell:.4f}."
                )
                F = F_2shell
                shell_passes = 2
                auto_corrected = True
            else:
                warnings.append(
                    f"F-factor = {F:.4f} with 1 shell pass, "
                    f"{F_2shell:.4f} with 2 shell passes. "
                    f"Both below 0.80 — design may be infeasible."
                )

        # 8. Highly asymmetric warning
        if R is not None and R > 4.0:
            warnings.append(
                f"R = {R:.2f} is highly asymmetric. "
                f"Consider if a different exchanger arrangement "
                f"(e.g., multiple shells in series) would be more effective."
            )

        # 9. Cache values for _conditional_ai_trigger (same pattern as Step 3)
        self._F_factor = F
        self._R = R
        self._auto_corrected = auto_corrected

        # 10. Build escalation hints for AI context
        escalation_hints = []
        if F < 0.85:
            escalation_hints.append({
                "trigger": "F_factor_borderline",
                "recommendation": "Consider 2 shell passes or verify TEMA selection"
            })
        if R is not None and R > 4.0:
            escalation_hints.append({
                "trigger": "high_R_sensitivity",
                "recommendation": (
                    "F-factor is sensitive to small P changes at this R. "
                    "Verify temperature spec accuracy."
                )
            })
        if (state.T_cold_out_C is not None and state.T_hot_out_C is not None
                and (state.T_hot_out_C - state.T_cold_out_C) < 3.0):
            escalation_hints.append({
                "trigger": "temperature_cross_risk",
                "recommendation": (
                    "Approach temperature < 3°C. May need multiple shells "
                    "in series or revised outlet temperatures."
                )
            })

        # 11. Build result
        return self._build_result(
            LMTD_K=LMTD, F_factor=F, R=R, P=P,
            shell_passes=shell_passes, auto_corrected=auto_corrected,
            warnings=warnings, escalation_hints=escalation_hints,
        )

    def _conditional_ai_trigger(self, state: DesignState) -> bool:
        """Trigger AI review when borderline F, high R, or temperature cross risk.

        Three triggers (any one is sufficient):
        1. F < 0.85 — but if auto-correction happened (1→2 shells),
           only trigger if corrected F is still < 0.80
        2. R > 4.0 — asymmetric duty, steep F-P curve
        3. Approach temperature < 3°C — temperature cross risk

        Values are cached on self during execute() (same pattern as Step 3).
        """
        F = getattr(self, "_F_factor", None)
        R = getattr(self, "_R", None)
        auto_corrected = getattr(self, "_auto_corrected", False)

        # Trigger 1: F-factor borderline
        if F is not None:
            if auto_corrected:
                # Auto-correction already bumped 1→2 shells.
                # Only call AI if the corrected F is still concerning.
                if F < 0.80:
                    return True
            else:
                if F < 0.85:
                    return True

        # Trigger 2: Highly asymmetric duty (steep F-P curve)
        if R is not None and R > 4.0:
            return True

        # Trigger 3: Temperature cross risk (approach < 3°C)
        if (state.T_cold_out_C is not None and state.T_hot_out_C is not None):
            approach = state.T_hot_out_C - state.T_cold_out_C
            if approach < 3.0:
                return True

        return False

    def _check_preconditions(self, state: DesignState) -> list[str]:
        """Return list of missing fields."""
        missing = []
        for field in ("T_hot_in_C", "T_hot_out_C", "T_cold_in_C", "T_cold_out_C", "Q_W"):
            if getattr(state, field) is None:
                missing.append(field)
        if state.geometry is None:
            missing.append("geometry")
        elif state.geometry.n_passes is None:
            missing.append("geometry.n_passes")
        elif state.geometry.shell_passes is None:
            missing.append("geometry.shell_passes")
        return missing

    def _build_result(self, *, LMTD_K, F_factor, R, P,
                      shell_passes, auto_corrected, warnings,
                      escalation_hints=None) -> StepResult:
        """Build the StepResult with outputs dict."""
        effective_LMTD = F_factor * LMTD_K

        outputs = {
            "LMTD_K": LMTD_K,
            "F_factor": F_factor,
            "effective_LMTD": effective_LMTD,
            "R": R,
            "P": P,
            "shell_passes": shell_passes,
            "auto_corrected": auto_corrected,
        }
        if escalation_hints:
            outputs["escalation_hints"] = escalation_hints

        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
            warnings=warnings,
        )
```

### State Mutations

After `execute()` returns, the pipeline runner applies:

| DesignState field             | Value from outputs        | Notes                                   |
| ----------------------------- | ------------------------- | --------------------------------------- |
| `state.LMTD_K`                | `outputs["LMTD_K"]`       | Already exists on DesignState           |
| `state.F_factor`              | `outputs["F_factor"]`     | Added in Piece 0                        |
| `state.geometry.shell_passes` | `outputs["shell_passes"]` | Only changed if auto-corrected from 1→2 |

**Important:** Step 5 must NOT modify `Q_W`, `T_hot_in_C`, `T_hot_out_C`, `T_cold_in_C`, `T_cold_out_C`, `hot_fluid_props`, `cold_fluid_props`, `tema_type`, or any geometry fields other than `shell_passes`.

**AI Constraint (Option C — agreed 2026-03-24):** The auto-correction within `execute()` handles the shell_passes 1→2 bump entirely. The AI review (when triggered) should only **WARN** or **ESCALATE** for shell_passes issues — it must **never return a CORRECT decision for `shell_passes`**. This avoids the state mutation timing issue in `BaseStep.run_with_review_loop()`, where corrections are applied to `result.outputs` but `state.geometry.shell_passes` is not updated before re-execution. The escalation hints guide the AI toward WARN/ESCALATE behavior by providing context about what auto-correction already did.

**Testing Plan (12 tests):**

| #   | Test                                       | What it validates                                  | Physics assertion                                            |
| --- | ------------------------------------------ | -------------------------------------------------- | ------------------------------------------------------------ |
| 1   | `test_step05_benchmark_crude_oil_water`    | 150/90°C hot, 30/55°C cold, 2 tube passes, 1 shell | LMTD ≈ 76.1°C, F ≈ 0.94, effective_LMTD ≈ 71.5°C             |
| 2   | `test_step05_missing_T_hot_in_raises`      | T_hot_in_C = None                                  | `CalculationError` with "T_hot_in_C" in message              |
| 3   | `test_step05_missing_T_cold_out_raises`    | T_cold_out_C = None                                | `CalculationError`                                           |
| 4   | `test_step05_missing_Q_W_raises`           | Q_W = None                                         | `CalculationError`                                           |
| 5   | `test_step05_missing_geometry_raises`      | geometry = None                                    | `CalculationError`                                           |
| 6   | `test_step05_pure_countercurrent_F_is_1`   | 1 tube pass, 1 shell pass                          | F = 1.0 exactly, R and P are None (not computed)             |
| 7   | `test_step05_auto_correct_1_to_2_shells`   | Temps giving F=0.78 with 1 shell                   | shell_passes updated to 2, F improves, `auto_corrected=True` |
| 8   | `test_step05_auto_correct_still_below_075` | Extreme temps where 2 shells still < 0.75          | `auto_corrected=False`, warning emitted, F left as-is        |
| 9   | `test_step05_small_lmtd_warning`           | Temps giving LMTD < 3°C                            | Warning about large area requirement                         |
| 10  | `test_step05_high_R_warning`               | R > 4.0 (very asymmetric)                          | Warning about asymmetric duty                                |
| 11  | `test_step05_equal_delta_t_no_crash`       | ΔT₁ = ΔT₂ exactly                                  | Returns valid LMTD (arithmetic mean), no exception           |
| 12  | `test_step05_R_equals_1_no_crash`          | Symmetric case R = 1.0                             | F computed correctly, no NaN/inf                             |

**Physics invariants the tests enforce:**

1. `effective_LMTD = F × LMTD` — always true
2. `effective_LMTD ≤ LMTD` — because F ≤ 1.0
3. Auto-correction only increases shell_passes — never decreases
4. Auto-correction only triggers when F < 0.80 AND current shell_passes == 1
5. Pure counter-current (1-1) always gives F = 1.0 — the formula is never called
6. Temperatures and Q_W are never modified by this step

---

## Piece 4: Pipeline Wiring — State Application

**What:** Ensure the pipeline runner correctly applies Step 5 outputs to `DesignState`, including the nested `geometry.shell_passes` update when auto-corrected.

**File to check/modify:**

- Pipeline runner `_apply_result()` method — needs to handle nested geometry updates, not just flat `DesignState` fields.

### Key concern: Nested geometry update

The current `_apply_result()` iterates over `result.outputs` and sets flat DesignState fields:

```python
for key, value in result.outputs.items():
    if hasattr(state, key):
        update[key] = value
```

This works for `LMTD_K` and `F_factor` (flat fields), but `shell_passes` is nested inside `state.geometry`. Step 5's `execute()` outputs `shell_passes` as a top-level key.

**Two options:**

**Option A (recommended):** Step 5's `execute()` produces both the flat fields AND explicitly patches the geometry if auto-corrected. The state application logic in the pipeline applies `LMTD_K` and `F_factor` normally. The shell_passes update on geometry is done inside `execute()` since the step itself knows the correction happened.

**Option B:** The pipeline runner has special handling for nested geometry updates.

**Recommendation: Option A** — keep the pipeline runner simple and generic. Step 5 handles its own geometry mutation.

To implement Option A, `execute()` should directly update `state.geometry.shell_passes` when auto-correcting, since the step has write access to state (same pattern as Steps 1–4 that populate state fields).

Alternatively, the `outputs` dict can include `"geometry_shell_passes": 2` and the pipeline runner can detect the `geometry_` prefix and route it to the nested object. But this adds framework complexity for a single case — simpler to let the step handle it.

**Testing Plan (5 tests):**

| #   | Test                                            | What it validates                                     | Physics assertion                             |
| --- | ----------------------------------------------- | ----------------------------------------------------- | --------------------------------------------- |
| 1   | `test_state_lmtd_populated_after_step5`         | `state.LMTD_K` is not None and > 0                    | Driving force exists                          |
| 2   | `test_state_f_factor_populated_after_step5`     | `state.F_factor` is not None and ∈ (0, 1.0]           | Valid correction factor                       |
| 3   | `test_state_shell_passes_updated_on_correction` | If auto-corrected, `state.geometry.shell_passes == 2` | Correction persisted to state                 |
| 4   | `test_state_Q_W_unchanged_after_step5`          | `state.Q_W` identical before and after Step 5         | Step 5 is read-compute-write, no side effects |
| 5   | `test_state_temps_unchanged_after_step5`        | All 4 temperatures identical before and after Step 5  | No temperature mutation                       |

---

## Piece 5: Integration Test — Steps 1→5 Pipeline

**What:** End-to-end test running the full benchmark case through all 5 steps with the mock AI (always PROCEED). Validates that Steps 1–5 produce a fully consistent, physically valid DesignState.

**File to create:**

- `tests/unit/test_step_05_integration.py`

### Benchmark case

```
Input:  "Design a heat exchanger for cooling 50 kg/s of crude oil
         from 150°C to 90°C using cooling water at 30°C"

After Step 1: fluids, temperatures, flow rates populated
After Step 2: Q_W calculated, T_cold_out_C computed from energy balance
After Step 3: fluid properties populated
After Step 4: TEMA type selected, geometry populated
After Step 5: LMTD_K, F_factor populated, effective_LMTD available
```

**Testing Plan (6 tests):**

| #   | Test                                            | What it validates                                                           | Physics assertion                               |
| --- | ----------------------------------------------- | --------------------------------------------------------------------------- | ----------------------------------------------- |
| 1   | `test_pipeline_1_through_5_benchmark_completes` | All 5 steps run without exception                                           | Pipeline is wired correctly                     |
| 2   | `test_pipeline_all_thermal_fields_populated`    | Q_W, LMTD_K, F_factor all not None                                          | Steps 2 and 5 both succeeded                    |
| 3   | `test_pipeline_5_step_records`                  | `len(state.step_records) == 5`                                              | All steps logged                                |
| 4   | `test_pipeline_lmtd_between_delta_ts`           | min(ΔT₁,ΔT₂) ≤ LMTD_K ≤ max(ΔT₁,ΔT₂)                                        | Log mean is between the two terminal ΔTs        |
| 5   | `test_pipeline_effective_lmtd_le_lmtd`          | F_factor × LMTD_K ≤ LMTD_K                                                  | F ≤ 1.0                                         |
| 6   | `test_pipeline_no_regression_steps_1_4`         | Q_W, fluid names, temps, geometry basics unchanged from their Step 4 values | Step 5 didn't mutate anything it shouldn't have |

**Extended physics checks embedded in test 1:**

- `state.LMTD_K > 0`
- `0 < state.F_factor ≤ 1.0`
- `state.Q_W > 0`
- `state.hot_fluid_props is not None`
- `state.cold_fluid_props is not None`
- `state.geometry is not None`
- `state.tema_type in VALID_TEMA_TYPES`

---

## Piece 6: Regression Safety — Full Test Suite

**What:** After all Pieces 0–5 are implemented, run the complete test suite to verify zero regressions.

**Execution:**

```bash
# Run ALL tests (Steps 1–5 + models + adapters + data)
cd hx_design_engine
pytest tests/ -v --tb=short

# Expected: ALL existing tests pass + all new Step 5 tests pass
```

**Regression risk assessment:**

| Risk                                  | Likelihood | Impact | Mitigation                                          |
| ------------------------------------- | ---------- | ------ | --------------------------------------------------- |
| Adding `F_factor` to DesignState      | Very Low   | Low    | Optional field with `None` default — no breakage    |
| Creating `correlations/` directory    | None       | None   | New directory, touches nothing existing             |
| New `step_05_rules.py` auto-registers | Very Low   | Low    | Only registers rules for step_id=5                  |
| `step_05_lmtd.py` imports             | Very Low   | Low    | New file, no existing code changed                  |
| conftest.py fixture changes           | Low        | Medium | May need new fixture for Step 5 pre-populated state |

**Testing Plan (1 meta-test):**

| #   | Test                                 | What it validates                                    |
| --- | ------------------------------------ | ---------------------------------------------------- |
| 1   | `pytest tests/ -v` exits with code 0 | Zero regressions across all ~40+ existing test files |

---

## Implementation Order

```
Piece 0  ─── Model change (F_factor on DesignState)
   │         3 tests → run test_design_state.py
   ▼
Piece 1  ─── correlations/lmtd.py (pure math, zero deps)
   │         14 tests → run test_lmtd_correlation.py
   ▼
Piece 2  ─── step_05_rules.py (depends on Piece 1 output shape)
   │         10 tests → run test_step_05_rules.py
   ▼
Piece 3  ─── step_05_lmtd.py (depends on Pieces 0, 1, 2)
   │         12 tests → run test_step_05_execute.py
   ▼
Piece 4  ─── Pipeline wiring (depends on Piece 3)
   │         5 tests → run test_step_05_state.py
   ▼
Piece 5  ─── Integration tests (depends on all above)
   │         6 tests → run test_step_05_integration.py
   ▼
Piece 6  ─── Full regression (final gate)
   │         pytest tests/ -v → all pass
   ▼
   ✅ Step 5 complete
```

**Recommended build phases:**

```
Phase A (Parallel — no dependencies on each other):
  Piece 0 (model) + Piece 1 (correlations)

Phase B (Sequential — depends on Phase A):
  Piece 2 (rules) → Piece 3 (step class)

Phase C (Sequential — depends on Phase B):
  Piece 4 (wiring) → Piece 5 (integration) → Piece 6 (regression)
```

---

## Total Test Count: 50 tests

| Piece | Description               | Tests | Cumulative |
| ----- | ------------------------- | ----- | ---------- |
| 0     | Model Update (F_factor)   | 3     | 3          |
| 1     | correlations/lmtd.py      | 14    | 17         |
| 2     | step_05_rules.py          | 10    | 27         |
| 3     | step_05_lmtd.py (execute) | 12    | 39         |
| 4     | Pipeline wiring           | 5     | 44         |
| 5     | Integration (Steps 1→5)   | 6     | 50         |
| 6     | Full regression           | 0\*   | 50         |

\*Piece 6 re-runs ALL existing tests (~40+), not new tests.

---

## Physics Guard Rails (Cross-Cutting Invariants)

These invariants must hold across **ALL** Step 5 tests:

1. **LMTD bounded by terminal ΔTs:** $\min(\Delta T_1, \Delta T_2) \leq \text{LMTD} \leq \max(\Delta T_1, \Delta T_2)$
2. **F bounded:** $0 \leq F \leq 1.0$ — F = 1.0 only for pure counter-current
3. **Effective LMTD bounded:** $F \times \text{LMTD} \leq \text{LMTD}$
4. **Energy conservation:** Q_W is identical before and after Step 5
5. **Temperature immutability:** All 4 temperatures unchanged by Step 5
6. **Monotonicity of F with shells:** $F(\text{2 shells}) \geq F(\text{1 shell})$ for same R, P
7. **R and P ranges:** $R > 0$, $0 < P < 1$ for all physically valid cases
8. **No tube geometry mutation:** Step 5 only touches `shell_passes` — never tube OD, ID, length, n_tubes, etc.
9. **Auto-correction only increases:** shell_passes can go 1→2, never 2→1
10. **Consistent with Step 4:** If Step 4 set shell_passes=1 and Step 5 doesn't auto-correct, it stays 1

---

## Files Created/Modified Summary

| File                                     | Action | Piece |
| ---------------------------------------- | ------ | ----- |
| `hx_engine/app/models/design_state.py`   | MODIFY | 0     |
| `hx_engine/app/correlations/__init__.py` | CREATE | 1     |
| `hx_engine/app/correlations/lmtd.py`     | CREATE | 1     |
| `hx_engine/app/steps/step_05_rules.py`   | CREATE | 2     |
| `hx_engine/app/steps/step_05_lmtd.py`    | CREATE | 3     |
| `tests/unit/test_step_05_model.py`       | CREATE | 0     |
| `tests/unit/test_lmtd_correlation.py`    | CREATE | 1     |
| `tests/unit/test_step_05_rules.py`       | CREATE | 2     |
| `tests/unit/test_step_05_execute.py`     | CREATE | 3     |
| `tests/unit/test_step_05_state.py`       | CREATE | 4     |
| `tests/unit/test_step_05_integration.py` | CREATE | 5     |

---

## Risk Notes

1. **F-factor formula precision:** The Bowman formula involves nested logarithms and square roots. Near R = 1.0 or at extreme P values, floating-point cancellation can cause loss of precision. **Mitigation:** L'Hôpital limit form for R ≈ 1.0 (abs tolerance 1e-6); domain checks before every `math.log()` call; tests verify against hand-calculated values to 0.1%.

2. **Auto-correction side effects:** Changing `shell_passes` from 1→2 affects Step 6 (area sizing) and Step 11 (overdesign). This is intentional — the convergence loop (Step 12) handles propagation. **Mitigation:** Integration tests verify downstream steps see the updated shell_passes.

3. **Temperature cross detection:** If T_cold_out > T_hot_out (from Step 2 energy balance), ΔT₂ may be negative. `compute_lmtd` will raise `ValueError`, which Step 5 should catch and convert to a `CalculationError` with a clear diagnostic message. **Mitigation:** Explicit try/except around `compute_lmtd` in `execute()`.

4. **correlations/ directory creation:** This is a new package. The `__init__.py` must exist or imports will fail. **Mitigation:** Piece 1 creates both files.

5. **Field name consistency:** DesignState uses `LMTD_K` (Kelvin), but LMTD computed from °C temperatures is identical in magnitude (temperature differences are the same in K and °C). **Mitigation:** Document this explicitly in `compute_lmtd` docstring. No unit conversion needed.

---

## Benchmark Validation Values

For verification against hand calculations and textbook values:

```
Benchmark: Crude oil 150→90°C, Water 30→55°C

ΔT₁ = T_hot_in − T_cold_out  = 150 − 55  = 95°C
ΔT₂ = T_hot_out − T_cold_in  = 90 − 30   = 60°C

LMTD = (95 − 60) / ln(95/60) = 35 / ln(1.5833) = 35 / 0.4595 ≈ 76.17°C

R = (150 − 90) / (55 − 30) = 60 / 25 = 2.400
P = (55 − 30) / (150 − 30) = 25 / 120 = 0.2083

For 1-2 exchanger (1 shell, 2 tube passes):
  √(R²+1) = √(5.76 + 1) = √6.76 = 2.6
  F ≈ 0.945  (textbook value for R=2.4, P=0.208)

effective_LMTD = 0.945 × 76.17 ≈ 71.98°C
```

These values serve as the ground-truth anchor for test assertions.

---

_Plan authored 2026-03-24. Depends on: Steps 1–4 (complete), ARKEN_STEPS_1_5_PLAN.md, ARKEN_MASTER_PLAN.md v8.0_
