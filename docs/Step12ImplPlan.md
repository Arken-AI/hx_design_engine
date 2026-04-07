# Step 12 Implementation Plan — Convergence Loop (Geometry Iteration)

**Status:** Planning  
**Depends on:** Steps 7–11 (complete), BaseStep infrastructure (complete)  
**Reference:** STEPS_6_16_PLAN.md §Phase B, ARKEN_MASTER_PLAN.md §6.3  
**Date:** 2026-04-07

---

## Overview

Step 12 is an **orchestrator**, not a calculation step. It repeatedly runs Steps 7→8→9→10→11 in a tight loop, adjusting geometry between iterations until four convergence criteria are satisfied simultaneously. No new correlations or external data are needed.

**Why it exists:** After Step 11, the initial pass uses an _estimated_ U (Step 6). The _calculated_ U (Step 9) almost certainly differs. Step 12 iterates until U stabilises and the geometry matches the calculated thermal-hydraulic reality.

---

## Agreed Design Decisions

| #   | Decision                                                                                        | Rationale                                                       |
| --- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| D1  | Move `in_convergence_loop` check before AI mode in `_should_call_ai`                            | Skips AI for FULL-mode steps (8, 9) too; Layer 1 math unchanged |
| D2  | Sub-steps called via `run_with_review_loop()`                                                   | Reuses existing infra; Layer 2 hard rules still fire            |
| D3  | Extract `_apply_outputs` to a module-level utility                                              | Step 12 can import it without coupling to PipelineRunner        |
| D4  | Hybrid adjustment algorithm (proportional → damped)                                             | No accuracy impact; 4–8 iterations typical                      |
| D5  | TEMA table lookup for shell constraint; auto-upsize                                             | Real fabrication sizes only                                     |
| D6  | Baffle spacing recalculated proportionally on shell upsize only                                 | 0.4×D_shell ratio preserved                                     |
| D7  | Step 8 re-runs every iteration                                                                  | n_tubes change affects cross-flow area, J_b, J_l                |
| D8  | Post-convergence: Steps 7–11 re-run with full AI review                                         | Final geometry gets AI sign-off                                 |
| D9  | Non-convergence → AI suggests structural change → ESCALATE → user decides → restart from Step N | Max 2 restarts                                                  |
| D10 | n_passes auto-adjustable within the loop                                                        | Fixes velocity problems without user friction                   |
| D11 | Enhanced `IterationProgressEvent` per iteration; no sub-step events                             | Clean frontend UX                                               |

---

## Sub-Tasks (Build Order)

### Sub-Task 1: Modify `_should_call_ai` in `base.py`

**File:** `hx_engine/app/steps/base.py`

**Change:** Move the `in_convergence_loop` check to the top of `_should_call_ai`, before the `FULL` mode check.

```python
# BEFORE
def _should_call_ai(self, state):
    if self.ai_mode == AIModeEnum.FULL:
        return True
    if self.ai_mode == AIModeEnum.NONE:
        return False
    if state.in_convergence_loop:
        return False
    return self._conditional_ai_trigger(state)

# AFTER
def _should_call_ai(self, state):
    if state.in_convergence_loop:
        return False                   # ← Overrides even FULL-mode steps
    if self.ai_mode == AIModeEnum.FULL:
        return True
    if self.ai_mode == AIModeEnum.NONE:
        return False
    return self._conditional_ai_trigger(state)
```

**Impact:** Steps 8 (FULL) and 9 (FULL) now skip AI inside the convergence loop. Layer 1 calculations and Layer 2 rules are unchanged.

**Side effect on Steps 7, 10, 11:** None — they already had `_should_call_ai` overridden locally to check `in_convergence_loop`. The base class change now makes their local overrides redundant (but harmless to keep).

**Test:** Unit test that `_should_call_ai` returns `False` for a FULL-mode step when `state.in_convergence_loop = True`.

---

### Sub-Task 2: Extract `_apply_outputs` to a Utility Function

**File:** `hx_engine/app/core/pipeline_runner.py` → extract to `hx_engine/app/core/state_utils.py`

**What:** Currently `_apply_outputs` is a method on `PipelineRunner`. It's a pure function (takes `state` + `result`, mutates `state`). Extract to a module-level function so Step 12 can import it.

**New file:** `hx_engine/app/core/state_utils.py`

```python
def apply_outputs(state: DesignState, result: StepResult) -> None:
    """Apply step outputs to DesignState fields.

    Extracted from PipelineRunner so convergence_loop (Step 12) can reuse it.
    """
    # ... exact same mapping logic currently in PipelineRunner._apply_outputs ...
```

**Changes to `pipeline_runner.py`:**

- Remove `_apply_outputs` method from `PipelineRunner`
- Import `apply_outputs` from `state_utils`
- Replace all `self._apply_outputs(state, result)` calls with `apply_outputs(state, result)`

**Test:** Existing pipeline tests must still pass (no behavioural change).

---

### Sub-Task 3: Add DesignState Fields for Convergence Tracking

**File:** `hx_engine/app/models/design_state.py`

**New fields on `DesignState`:**

```python
# --- convergence loop tracking (populated by Step 12) ---
convergence_iteration: Optional[int] = None       # Which iteration converged (None if not run yet)
convergence_converged: Optional[bool] = None       # True = converged, False = hit max iterations
convergence_max_iterations: int = 20               # Configurable max
convergence_trajectory: list[dict] = Field(default_factory=list)
    # Per-iteration snapshot: [{"iteration": 1, "U_dirty": 378.2, "delta_U_pct": None,
    #   "overdesign_pct": 18.3, "dP_tube_Pa": 45000, "dP_shell_Pa": 95000,
    #   "velocity_m_s": 1.4, "n_tubes": 324, "adjustment": "proportional +12 tubes"}, ...]
convergence_restart_count: int = 0                 # How many structural restarts so far
```

**No new validators needed** — these are tracking fields, not engineering parameters.

---

### Sub-Task 4: Enhance `IterationProgressEvent`

**File:** `hx_engine/app/models/sse_events.py`

**Add fields to existing `IterationProgressEvent`:**

```python
class IterationProgressEvent(SSEBaseEvent):
    event_type: str = "iteration_progress"
    iteration_number: int
    max_iterations: int = 20
    current_U: Optional[float] = None
    delta_U_pct: Optional[float] = None
    constraints_met: bool = False
    # NEW fields:
    overdesign_pct: Optional[float] = None
    dP_tube_pct_of_limit: Optional[float] = None    # (dP_tube / 70000) × 100
    dP_shell_pct_of_limit: Optional[float] = None   # (dP_shell / 140000) × 100
    velocity_m_s: Optional[float] = None
    adjustment_made: Optional[str] = None            # e.g. "increased n_tubes 324→340"
```

**No breaking change** — all new fields are Optional with defaults.

---

### Sub-Task 5: Create `step_12_convergence.py` — Core Logic

**File:** `hx_engine/app/steps/step_12_convergence.py`

This is the main implementation. It does NOT subclass `BaseStep` — it's a special orchestrator step with its own class structure.

#### 5.1 Class Structure

```python
class Step12Convergence:
    """Step 12: Convergence Loop — iterates Steps 7→11 until geometry converges.

    Not a BaseStep subclass. Has its own execution model:
    - No execute() → rules → AI pattern
    - Manages sub-steps directly
    - Only calls AI on convergence failure (post-loop)
    """
    step_id: int = 12
    step_name: str = "Convergence Loop"

    # Constants
    MAX_ITERATIONS: int = 20
    DELTA_U_THRESHOLD: float = 1.0       # %
    OVERDESIGN_LOW: float = 10.0         # %
    OVERDESIGN_HIGH: float = 25.0        # %
    DP_TUBE_LIMIT: float = 70_000.0      # Pa (0.7 bar)
    DP_SHELL_LIMIT: float = 140_000.0    # Pa (1.4 bar)
    VELOCITY_LOW: float = 0.8            # m/s
    VELOCITY_HIGH: float = 2.5           # m/s
```

#### 5.2 Main `run()` Method

```python
async def run(
    self,
    state: DesignState,
    ai_engineer: AIEngineer,
    sse_manager: SSEManager,
    session_id: str,
) -> StepResult:
```

Flow:

```
1. Snapshot pre-loop state (for rollback on structural change)
2. Set state.in_convergence_loop = True
3. TRY:
   a. For iteration = 1 to MAX_ITERATIONS:
      i.   Run Steps 7→8→9→10→11 via run_with_review_loop() + apply_outputs()
      ii.  Extract convergence metrics from state
      iii. Compute delta_U_pct (vs previous iteration)
      iv.  Store iteration snapshot in state.convergence_trajectory
      v.   Emit IterationProgressEvent
      vi.  Check convergence criteria — if ALL met → break
      vii. Compute geometry adjustment (see Sub-Task 6)
      viii. Apply adjustment to state.geometry
   b. If converged: record success
   c. If not converged: call AI once, ESCALATE with structural suggestion
4. FINALLY:
   a. Set state.in_convergence_loop = False   (CG1A guarantee)
```

#### 5.3 Sub-Step Execution (Inside Loop)

```python
SUB_STEPS = [
    Step07TubeSideH,
    Step08ShellSideH,
    Step09OverallU,
    Step10PressureDrops,
    Step11AreaOverdesign,
]

for step_cls in SUB_STEPS:
    step = step_cls()
    result = await step.run_with_review_loop(state, ai_engineer)
    apply_outputs(state, result)

    # If Layer 2 hard fail inside sub-step → break iteration,
    # record which step failed, attempt smaller adjustment
    if not result.validation_passed:
        break
```

**Layer 2 failures inside the loop:** If a sub-step fails Layer 2 (e.g., velocity out of [0.3, 5.0] m/s), the iteration is abandoned and the geometry adjustment for the next iteration takes this failure into account. This is NOT a pipeline-stopping error — it's a signal that the adjustment overshot.

#### 5.4 Convergence Check

```python
def _check_convergence(self, state: DesignState, delta_U_pct: Optional[float]) -> bool:
    """Return True when ALL four criteria are met simultaneously."""
    return (
        (delta_U_pct is not None and delta_U_pct < self.DELTA_U_THRESHOLD)
        and (self.OVERDESIGN_LOW <= state.overdesign_pct <= self.OVERDESIGN_HIGH)
        and (state.dP_tube_Pa <= self.DP_TUBE_LIMIT)
        and (state.dP_shell_Pa <= self.DP_SHELL_LIMIT)
        and (self.VELOCITY_LOW <= state.tube_velocity_m_s <= self.VELOCITY_HIGH)
    )
```

**Note:** First iteration has `delta_U_pct = None` (no previous U to compare). Convergence cannot be declared on iteration 1 — minimum 2 iterations required.

#### 5.5 Post-Convergence AI Re-Review

After the loop converges (or after restoring from structural change), run Steps 7–11 **one more time** with `state.in_convergence_loop = False`:

```python
# Clear the flag — AI is now enabled
state.in_convergence_loop = False

# Re-run with full AI review on final converged geometry
for step_cls in SUB_STEPS:
    step = step_cls()
    result = await step.run_with_review_loop(state, ai_engineer)
    apply_outputs(state, result)

    # Emit step events normally (frontend sees the final AI-reviewed pass)
    await emit_decision_event(session_id, step, result, ...)
```

This ensures:

- Steps 8 (FULL) and 9 (FULL) get AI judgment on the final geometry
- Any anomaly introduced by the loop is caught
- The step_records contain the AI-reviewed versions

#### 5.6 Non-Convergence → AI Structural Suggestion

If the loop exhausts 20 iterations:

```python
# Call AI ONCE to suggest structural change
prompt = f"""
Convergence failed after {MAX_ITERATIONS} iterations.
Trajectory: {json.dumps(state.convergence_trajectory[-5:])}
Current geometry: {state.geometry.model_dump()}
Best iteration: #{best_iteration} (overdesign={best_overdesign:.1f}%, ΔU={best_delta:.2f}%)

What structural change would resolve this? Options:
A) Increase shell passes (1→2) — restart from Step 5
B) Switch TEMA type — restart from Step 4
C) Multi-shell configuration — restart from Step 6
D) Swap tube allocation — restart from Step 4
E) Change pitch layout — restart from Step 4
F) No structural change possible — accept best result

Respond with JSON: {{
  "suggestion": "A"|"B"|"C"|"D"|"E"|"F",
  "reasoning": "...",
  "restart_from_step": 4|5|6|null,
  "confidence": 0.0-1.0
}}
"""
```

Then ESCALATE to user with:

- AI's recommendation and reasoning
- The best-iteration result as a fallback
- Options: Accept recommendation, Keep best result, Modify suggestion

#### 5.7 Restart-from-Step-N Logic

When user accepts a structural change:

```python
# Return a special StepResult that signals pipeline_runner to restart
return StepResult(
    step_id=12,
    step_name="Convergence Loop",
    outputs={
        "convergence_action": "restart",
        "restart_from_step": restart_step_id,   # 4, 5, or 6
        "structural_change": change_description,
        "convergence_restart_count": state.convergence_restart_count + 1,
    },
    warnings=[f"Convergence restart #{state.convergence_restart_count + 1}: {change_description}"],
)
```

Pipeline runner handles this by re-running from the indicated step (see Sub-Task 8).

---

### Sub-Task 6: Geometry Adjustment Algorithm

**Location:** Private method `_compute_adjustment()` inside `step_12_convergence.py`

#### 6.1 Violation Detection (Priority Order)

```python
def _detect_violations(self, state: DesignState) -> list[str]:
    """Return list of violation types in priority order."""
    violations = []

    # Priority 1: Pressure drop violations (hard constraint)
    if state.dP_tube_Pa > self.DP_TUBE_LIMIT:
        violations.append("dP_tube_high")
    if state.dP_shell_Pa > self.DP_SHELL_LIMIT:
        violations.append("dP_shell_high")

    # Priority 2: Overdesign (primary convergence signal)
    if state.overdesign_pct < self.OVERDESIGN_LOW:
        violations.append("underdesign")
    elif state.overdesign_pct > self.OVERDESIGN_HIGH:
        violations.append("overdesign")

    # Priority 3: Velocity
    if state.tube_velocity_m_s < self.VELOCITY_LOW:
        violations.append("velocity_low")
    elif state.tube_velocity_m_s > self.VELOCITY_HIGH:
        violations.append("velocity_high")

    return violations
```

#### 6.2 Adjustment Strategy per Violation

| Violation       | Primary Lever                               | Secondary Lever             | Effect                                |
| --------------- | ------------------------------------------- | --------------------------- | ------------------------------------- |
| `dP_tube_high`  | Reduce `n_passes` (4→2→1)                   | Increase `n_tubes`          | Lower tube velocity → lower friction  |
| `dP_shell_high` | Increase `baffle_spacing_m` (up to 1.0×D_s) | Increase `shell_diameter_m` | Lower shell velocity → lower shell dP |
| `underdesign`   | Increase `n_tubes`                          | Increase `tube_length_m`    | More area                             |
| `overdesign`    | Decrease `n_tubes`                          | —                           | Less area (conservative, small steps) |
| `velocity_low`  | Increase `n_passes` (1→2→4)                 | Decrease `n_tubes`          | Higher tube velocity                  |
| `velocity_high` | Increase `n_tubes`                          | Decrease `n_passes`         | Lower tube velocity                   |

#### 6.3 Hybrid Scaling Logic

```python
def _compute_adjustment(
    self,
    state: DesignState,
    iteration: int,
    violations: list[str],
    last_direction: dict[str, int],  # {"n_tubes": +1 or -1, "n_passes": ...}
) -> dict:
    """Return geometry changes to apply.

    Iterations 1-2: Proportional scaling (fast convergence)
    Iterations 3+:  Damped steps (stability)
    """
    changes = {}
    g = state.geometry

    if not violations:
        return changes  # Converged or close — no adjustment needed

    primary_violation = violations[0]  # Highest priority

    # --- PROPORTIONAL MODE (iterations 1-2) ---
    if iteration <= 2:
        if primary_violation in ("underdesign", "overdesign"):
            # Scale n_tubes by area ratio
            ratio = state.area_required_m2 / state.area_provided_m2
            new_n_tubes = int(round(g.n_tubes * ratio))
            changes["n_tubes"] = max(1, new_n_tubes)

        elif primary_violation == "dP_tube_high":
            # Scale n_tubes to reduce velocity: v ∝ 1/n_tubes
            # dP ∝ v² ∝ 1/n_tubes², so n_tubes_new = n_tubes × sqrt(dP/limit)
            ratio = math.sqrt(state.dP_tube_Pa / self.DP_TUBE_LIMIT)
            new_n_tubes = int(round(g.n_tubes * ratio))
            changes["n_tubes"] = max(1, new_n_tubes)

        # ... similar for other violations

    # --- DAMPED MODE (iterations 3+) ---
    else:
        step_pct = 0.05  # 5% base step

        # Oscillation damping: if direction reversed, halve the step
        direction = +1 if primary_violation in ("underdesign", "dP_tube_high") else -1
        if "n_tubes" in last_direction and last_direction["n_tubes"] != direction:
            step_pct *= 0.5  # Dampen on reversal

        if primary_violation in ("underdesign", "dP_tube_high", "velocity_high"):
            delta = max(1, int(round(g.n_tubes * step_pct)))
            changes["n_tubes"] = g.n_tubes + delta
        elif primary_violation in ("overdesign", "velocity_low"):
            delta = max(1, int(round(g.n_tubes * step_pct)))
            changes["n_tubes"] = max(1, g.n_tubes - delta)

    return changes
```

#### 6.4 n_passes Adjustment Rules

`n_passes` is discrete: {1, 2, 4, 6, 8}. Auto-adjustment within the loop:

```python
PASSES_SEQUENCE = [1, 2, 4, 6, 8]

# Increase passes (velocity too low or dP has margin):
if violation == "velocity_low" and n_tubes adjustment alone insufficient:
    current_idx = PASSES_SEQUENCE.index(g.n_passes)
    if current_idx < len(PASSES_SEQUENCE) - 1:
        changes["n_passes"] = PASSES_SEQUENCE[current_idx + 1]

# Decrease passes (dP_tube too high):
if violation == "dP_tube_high" and n_tubes adjustment alone insufficient:
    current_idx = PASSES_SEQUENCE.index(g.n_passes)
    if current_idx > 0:
        changes["n_passes"] = PASSES_SEQUENCE[current_idx - 1]
```

**Important:** When `n_passes` changes, `n_tubes` must be revalidated against the TEMA table (different pass counts have different max tube counts for the same shell).

#### 6.5 Shell Upsize Logic

```python
from hx_engine.app.data.tema_tables import find_shell_diameter, get_tube_count

def _apply_adjustment(self, state: DesignState, changes: dict) -> str:
    """Apply geometry changes. Returns description string."""
    g = state.geometry
    description_parts = []

    new_n_tubes = changes.get("n_tubes", g.n_tubes)
    new_n_passes = changes.get("n_passes", g.n_passes)

    # Check if desired tubes fit in current shell
    max_in_shell = get_tube_count(
        g.shell_diameter_m, g.tube_od_m, g.pitch_layout, new_n_passes
    )

    if new_n_tubes > max_in_shell:
        # Must upsize shell
        new_shell_m, actual_n_tubes = find_shell_diameter(
            new_n_tubes, g.tube_od_m, g.pitch_layout, new_n_passes
        )
        old_shell = g.shell_diameter_m
        g.shell_diameter_m = new_shell_m
        g.n_tubes = actual_n_tubes  # TEMA standard count, not arbitrary

        # Recalculate baffle spacing proportionally
        if g.baffle_spacing_m is not None and old_shell > 0:
            ratio = new_shell_m / old_shell
            g.baffle_spacing_m = g.baffle_spacing_m * ratio
            # Also update inlet/outlet baffle spacing
            if g.inlet_baffle_spacing_m is not None:
                g.inlet_baffle_spacing_m = g.inlet_baffle_spacing_m * ratio
            if g.outlet_baffle_spacing_m is not None:
                g.outlet_baffle_spacing_m = g.outlet_baffle_spacing_m * ratio

        # Recalculate n_baffles
        if g.tube_length_m and g.baffle_spacing_m:
            g.n_baffles = max(1, int(g.tube_length_m / g.baffle_spacing_m) - 1)

        description_parts.append(
            f"shell upsize {old_shell*1000:.0f}mm→{new_shell_m*1000:.0f}mm, "
            f"n_tubes→{actual_n_tubes}"
        )
    else:
        # Tubes fit — just update count
        if new_n_tubes != g.n_tubes:
            # Snap to nearest valid TEMA count (can't have arbitrary tube counts)
            # Use the TEMA table count that's >= desired count for this shell
            actual = get_tube_count(
                g.shell_diameter_m, g.tube_od_m, g.pitch_layout, new_n_passes
            )
            # If desired > actual, use actual (max for this shell)
            g.n_tubes = min(new_n_tubes, actual)
            description_parts.append(f"n_tubes→{g.n_tubes}")

    if new_n_passes != g.n_passes:
        g.n_passes = new_n_passes
        description_parts.append(f"n_passes→{new_n_passes}")

    return ", ".join(description_parts) or "no change"
```

**Critical accuracy point:** `n_tubes` is ALWAYS snapped to valid TEMA table values. We never have an arbitrary tube count like 327 — it's always a standard count from the TEMA table for the given shell/OD/pitch/passes combination.

**Note on TEMA table limitation:** The current `get_tube_count` returns the exact count for a shell/OD/pitch/passes combination. When the desired `n_tubes` falls between two shell sizes, `find_shell_diameter` returns the smallest shell that fits. The actual tube count used is the TEMA standard count for that shell — not the desired count. This is physically correct.

---

### Sub-Task 7: Create `step_12_rules.py`

**File:** `hx_engine/app/steps/step_12_rules.py`

Step 12 is an orchestrator — it has **no Layer 2 hard rules of its own**. However, we register an empty rule set for consistency:

```python
"""Step 12 validation rules — Convergence Loop.

Step 12 is an orchestrator (loop over Steps 7-11).
No hard rules — Layer 2 checking happens inside sub-steps.
Registered empty for consistency with the validation_rules framework.
"""

from hx_engine.app.core.validation_rules import register_rule

# No rules to register for Step 12.
# Sub-steps (7-11) each have their own Layer 2 rules that fire
# inside the convergence loop on every iteration.
```

---

### Sub-Task 8: Wire Step 12 into `pipeline_runner.py`

**File:** `hx_engine/app/core/pipeline_runner.py`

#### 8.1 Import Changes

```python
from hx_engine.app.steps.step_12_convergence import Step12Convergence
from hx_engine.app.core.state_utils import apply_outputs
```

#### 8.2 Pipeline Steps List Update

Step 12 is NOT added to `PIPELINE_STEPS` — it's handled as a special case because it doesn't follow the `BaseStep` pattern:

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
    Step11AreaOverdesign,
    # Step12 handled separately — it's an orchestrator, not a BaseStep
]
```

#### 8.3 Pipeline Runner `run()` Modification

After the normal `PIPELINE_STEPS` loop completes Step 11, call Step 12:

```python
# After the PIPELINE_STEPS for-loop completes (Steps 1-11)...

# --- Step 12: Convergence Loop ---
step12 = Step12Convergence()
await self.sse_manager.emit(
    session_id,
    StepStartedEvent(
        session_id=session_id,
        step_id=12,
        step_name="Convergence Loop",
    ).model_dump(),
)

step12_result = await step12.run(
    state, self.ai_engineer, self.sse_manager, session_id
)

# Handle convergence restart
if step12_result.outputs.get("convergence_action") == "restart":
    restart_from = step12_result.outputs["restart_from_step"]
    state.convergence_restart_count += 1

    if state.convergence_restart_count > 2:
        # Max restarts exceeded — accept best result
        state.pipeline_status = "error"
        await self._emit_step_error(session_id, step12,
            "Max convergence restarts (2) exceeded")
        return state

    # Re-run pipeline from restart_from step
    restart_steps = [s for s in PIPELINE_STEPS if s().step_id >= restart_from]
    for step_cls in restart_steps:
        # ... same step execution logic as the main loop ...

    # Then re-run Step 12
    # ... recursive or loop-based restart logic ...
```

**Implementation choice:** A `while` loop around the pipeline run, with a `restart_from_step` variable that defaults to 1 and can be set by Step 12. This avoids recursion.

#### 8.4 \_apply_outputs Migration

Replace `self._apply_outputs(state, result)` → `apply_outputs(state, result)` throughout the file.

---

### Sub-Task 9: Add Step 12 Convergence Fields to `_apply_outputs`

**File:** `hx_engine/app/core/state_utils.py` (the extracted utility)

Add mappings for Step 12's output fields:

```python
# Step 12 convergence tracking
"convergence_iteration": "convergence_iteration",
"convergence_converged": "convergence_converged",
"convergence_restart_count": "convergence_restart_count",
```

The `convergence_trajectory` list is written directly to `state` inside Step 12 (not via `_apply_outputs`), since it's built incrementally during the loop.

---

### Sub-Task 10: Tests

**Files to create:**

#### 10.1 `tests/unit/test_step_12_convergence.py`

| Test                                  | Description                                                       | Asserts                                                                         |
| ------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `test_convergence_happy_path`         | Sub-steps mocked to return values that converge in 3–4 iterations | `convergence_converged=True`, `convergence_iteration<=5`                        |
| `test_try_finally_flag_reset`         | Mock sub-step that raises on iteration 5                          | `state.in_convergence_loop=False` after exception                               |
| `test_max_iterations_hit`             | Sub-steps return values that never converge                       | `convergence_iteration=20`, `convergence_converged=False`, WARNING emitted      |
| `test_ai_skipped_in_loop`             | Check that Steps 7,8,9,10,11 don't call AI inside loop            | `ai_called=False` on all inner-loop step records                                |
| `test_oscillation_damping`            | alternating overdesign/underdesign signals                        | Direction reversal detected, step size halved                                   |
| `test_shell_upsize`                   | n_tubes exceeds shell capacity                                    | `shell_diameter_m` increases to next TEMA size, `n_tubes` snapped to TEMA count |
| `test_n_passes_adjustment`            | velocity too low → passes increased                               | `n_passes` incremented, tubes revalidated                                       |
| `test_proportional_then_damped`       | First 2 iterations use ratio scaling, then 5% steps               | Adjustment magnitude decreases                                                  |
| `test_layer2_fail_in_substep`         | A sub-step fails Layer 2 inside the loop                          | Iteration abandoned, next iteration adjusts                                     |
| `test_baffle_spacing_on_shell_upsize` | Shell upsized                                                     | `baffle_spacing_m` scaled proportionally                                        |

#### 10.2 `tests/unit/test_step_12_post_convergence.py`

| Test                                    | Description                                                    | Asserts                                               |
| --------------------------------------- | -------------------------------------------------------------- | ----------------------------------------------------- |
| `test_post_convergence_ai_runs`         | After loop, Steps 7-11 re-run with `in_convergence_loop=False` | `ai_called=True` for FULL-mode steps (8, 9)           |
| `test_post_convergence_results_applied` | Final AI-reviewed values are on state                          | `state.h_shell_W_m2K` etc. match post-convergence run |

#### 10.3 `tests/unit/test_step_12_non_convergence.py`

| Test                             | Description                                       | Asserts                                 |
| -------------------------------- | ------------------------------------------------- | --------------------------------------- |
| `test_non_convergence_ai_called` | Loop exhausted → AI called once with trajectory   | AI prompt contains trajectory data      |
| `test_non_convergence_escalate`  | AI suggests structural change → ESCALATE returned | `result.ai_review.decision == ESCALATE` |
| `test_restart_from_step_4`       | TEMA type change → restart from Step 4            | `outputs["restart_from_step"] == 4`     |
| `test_restart_from_step_5`       | Shell passes change → restart from Step 5         | `outputs["restart_from_step"] == 5`     |
| `test_restart_from_step_6`       | Multi-shell → restart from Step 6                 | `outputs["restart_from_step"] == 6`     |
| `test_max_restarts_exceeded`     | 3rd restart attempted                             | Pipeline returns error                  |
| `test_user_accepts_best_result`  | User picks "keep best"                            | Pipeline continues with WARNING         |

#### 10.4 `tests/unit/test_base_step_convergence_flag.py`

| Test                                   | Description                                     | Asserts                           |
| -------------------------------------- | ----------------------------------------------- | --------------------------------- |
| `test_full_mode_skips_ai_in_loop`      | FULL-mode step with `in_convergence_loop=True`  | `_should_call_ai` returns `False` |
| `test_full_mode_calls_ai_outside_loop` | FULL-mode step with `in_convergence_loop=False` | `_should_call_ai` returns `True`  |

#### 10.5 `tests/unit/test_state_utils.py`

| Test                           | Description                       | Asserts                                   |
| ------------------------------ | --------------------------------- | ----------------------------------------- |
| `test_apply_outputs_unchanged` | Same mapping as before extraction | All fields applied correctly              |
| `test_apply_outputs_geometry`  | Geometry dict → GeometrySpec      | `state.geometry` is GeometrySpec instance |

#### 10.6 `tests/integration/test_convergence_loop.py`

| Test                                 | Description                                         | Asserts                                                                     |
| ------------------------------------ | --------------------------------------------------- | --------------------------------------------------------------------------- |
| `test_full_pipeline_through_step_12` | Run Steps 1-12 with mock AI, realistic fluid inputs | `convergence_converged=True`, `state.overdesign_pct` in [10, 25]            |
| `test_sse_events_emitted`            | Check SSE emission order                            | `step_started(12)`, then N × `iteration_progress`, then `step_approved(12)` |

---

## File Summary

| #   | File                                            | Action                                        | Sub-Task   |
| --- | ----------------------------------------------- | --------------------------------------------- | ---------- |
| 1   | `hx_engine/app/steps/base.py`                   | MODIFY — reorder `_should_call_ai`            | ST-1       |
| 2   | `hx_engine/app/core/state_utils.py`             | CREATE — extracted `apply_outputs`            | ST-2       |
| 3   | `hx_engine/app/core/pipeline_runner.py`         | MODIFY — import `apply_outputs`, wire Step 12 | ST-2, ST-8 |
| 4   | `hx_engine/app/models/design_state.py`          | MODIFY — add convergence fields               | ST-3       |
| 5   | `hx_engine/app/models/sse_events.py`            | MODIFY — enhance `IterationProgressEvent`     | ST-4       |
| 6   | `hx_engine/app/steps/step_12_convergence.py`    | CREATE — main Step 12 logic                   | ST-5, ST-6 |
| 7   | `hx_engine/app/steps/step_12_rules.py`          | CREATE — empty rule set                       | ST-7       |
| 8   | `tests/unit/test_step_12_convergence.py`        | CREATE                                        | ST-10.1    |
| 9   | `tests/unit/test_step_12_post_convergence.py`   | CREATE                                        | ST-10.2    |
| 10  | `tests/unit/test_step_12_non_convergence.py`    | CREATE                                        | ST-10.3    |
| 11  | `tests/unit/test_base_step_convergence_flag.py` | CREATE                                        | ST-10.4    |
| 12  | `tests/unit/test_state_utils.py`                | CREATE                                        | ST-10.5    |
| 13  | `tests/integration/test_convergence_loop.py`    | CREATE                                        | ST-10.6    |

---

## Build Sequence

```
ST-1  base.py _should_call_ai reorder           (5 min — 1 line change + 2 tests)
  │
  ▼
ST-2  Extract _apply_outputs to state_utils.py   (15 min — refactor + verify existing tests pass)
  │
  ▼
ST-3  DesignState convergence fields             (5 min — add 5 optional fields)
  │
  ├── ST-4  Enhance IterationProgressEvent       (5 min — add 5 optional fields)
  │
  ▼
ST-5  step_12_convergence.py — core class        (main work)
  │   ├── 5.1  Class structure + constants
  │   ├── 5.2  run() method with try/finally
  │   ├── 5.3  Sub-step execution
  │   ├── 5.4  Convergence check
  │   ├── 5.5  Post-convergence AI re-review
  │   ├── 5.6  Non-convergence AI + ESCALATE
  │   └── 5.7  Restart signal
  │
  ├── ST-6  Geometry adjustment algorithm        (inside step_12_convergence.py)
  │   ├── 6.1  Violation detection
  │   ├── 6.2  Adjustment strategy per violation
  │   ├── 6.3  Hybrid scaling (proportional → damped)
  │   ├── 6.4  n_passes adjustment rules
  │   └── 6.5  Shell upsize logic
  │
  ├── ST-7  step_12_rules.py (empty)             (2 min)
  │
  ▼
ST-8  Wire into pipeline_runner.py               (special-case Step 12 + restart logic)
  │
  ▼
ST-9  Add convergence fields to apply_outputs    (5 min)
  │
  ▼
ST-10 Tests                                      (write alongside each sub-task)
  ├── 10.1  Unit: convergence happy/unhappy paths
  ├── 10.2  Unit: post-convergence AI re-review
  ├── 10.3  Unit: non-convergence + restart
  ├── 10.4  Unit: base_step flag check
  ├── 10.5  Unit: state_utils extraction
  └── 10.6  Integration: full pipeline through Step 12
```

---

## Edge Cases to Handle

| Edge Case                                                                      | Expected Behaviour                                                                              |
| ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| Converges on iteration 1 metrics but `delta_U_pct` is `None` (first iteration) | Minimum 2 iterations — continue to iteration 2                                                  |
| Sub-step throws `CalculationError` inside loop                                 | Catch, log, adjust geometry more conservatively, continue                                       |
| Sub-step throws unexpected exception inside loop                               | Caught by `try/finally`; `in_convergence_loop` cleared; pipeline error                          |
| `n_tubes` adjustment results in 0 or negative                                  | `max(1, new_n_tubes)` guard always present                                                      |
| Shell upsize exceeds largest TEMA shell (37")                                  | `find_shell_diameter` returns 37" shell with max count; if still insufficient → non-convergence |
| `n_passes` already at max (8) and velocity still too low                       | Mark as non-convergence violation, proceed to AI structural suggestion                          |
| `n_passes` already at min (1) and dP still too high                            | Shell upsize or structural change needed                                                        |
| Overdesign oscillates between 8% and 27%                                       | Damping kicks in after iteration 2; step size halves on direction reversal                      |
| All criteria met EXCEPT velocity (outside 0.8–2.5)                             | Does NOT converge — velocity is a hard criterion                                                |
| `baffle_spacing_m` after shell upsize exceeds TEMA max (2.0m)                  | Clamp to `min(new_spacing, 2.0)`                                                                |
| `baffle_spacing_m` after shell downsize (rare) below TEMA min (0.05m)          | Clamp to `max(new_spacing, 0.05)`                                                               |
| User rejects structural change AND rejects best result                         | Pipeline error — cannot proceed                                                                 |

---

## Accuracy Guarantees

1. **Layer 1 math is unchanged** — Gnielinski, Bell-Delaware, Churchill, area calculations all run identically inside and outside the loop
2. **Layer 2 hard rules fire every iteration** — catches geometry that violates physical bounds
3. **TEMA table tube counts only** — no arbitrary tube counts
4. **Post-convergence AI re-review** — final geometry gets full AI judgment (Steps 8, 9 reviewed)
5. **No approximations in sub-steps** — each iteration is a complete recalculation, not an interpolation
