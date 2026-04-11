# Step 16 Implementation Plan — Final Validation + Confidence Score

**Status:** Planning  
**Depends on:** Steps 1–15 (complete), BaseStep infrastructure (complete)  
**Reference:** STEPS_6_16_PLAN.md §Phase D, ARKEN_MASTER_PLAN.md §6.3 Step 16, §5.6 [CEO-CP2], §6.2 [CEO-7A]  
**Date:** 2026-04-11

---

## Overview

Step 16 is a **meta-analysis step** — it does not compute any engineering quantity. Instead it introspects the pipeline's own telemetry (all 15 prior `StepRecord` entries, convergence trajectory, warnings, corrections) to produce:

1. **Deterministic confidence score** (Layer 1) — 4-component weighted breakdown from pipeline data
2. **AI final sign-off** (Layer 3) — holistic design review producing a plain-English summary, assumptions list, strengths, risks, and recommendations

**AI Mode: FULL** — always called. This is the final engineering sign-off on the entire design.

**No external libraries, no textbook correlations, no new data tables required.** Everything comes from data already on `DesignState` and `step_records`.

**Scope:** Completes the 16-step pipeline. Also enriches `_build_summary()` and wires Step 16 into `pipeline_runner.py`.

---

## Agreed Design Decisions

| #   | Decision                                                                                                                                                                    | Rationale                                                                                         |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| D1  | Confidence score is **deterministic** — computed from pipeline telemetry, not from AI                                                                                       | Reproducible, testable, transparent                                                               |
| D2  | 4 equal-weight components (0.25 each) via `CONFIDENCE_WEIGHTS` constant in `step_16_final_validation.py`                                                                    | Per ARKEN_MASTER_PLAN.md [CEO-7A]; tunable later                                                  |
| D3  | `supermemory_similarity` defaults to **0.5** (neutral) — placeholder until Supermemory is integrated                                                                        | Supermemory has zero integration in codebase; 0.5 is neutral and doesn't inflate/deflate score    |
| D4  | "First-attempt validation pass" is **inferred** from existing data: `validation_passed == True` AND (no `ai_review`, or `ai_review.decision == PROCEED` with no `attempts`) | Avoids adding a new field to `StepRecord`; data is already available                              |
| D5  | Geometry convergence score: `1.0` if converged in ≤10 iters, linear degrade to `0.5` at 20 iters, `0.0` if did not converge                                                 | Rewards clean convergence without being binary                                                    |
| D6  | `_build_summary()` is **enriched** as part of Step 16 sub-task to include confidence, cost, vibration, mechanical results                                                   | Current summary is bare-bones; engineers need the full picture in the `design_complete` SSE event |
| D7  | AI prompts added for **all missing steps (10–16)** in this implementation — not just Step 16                                                                                | Steps 10–15 currently log a warning "No step-specific prompt defined"; tech debt cleaned up now   |
| D8  | `CONFIDENCE_WEIGHTS` lives as a **module-level constant** in `step_16_final_validation.py`                                                                                  | Single consumer; avoids over-abstracting into a config file                                       |
| D9  | If `confidence_score ≥ 0.75` → future Supermemory save (stub/TODO for now)                                                                                                  | Per ARKEN_MASTER_PLAN.md; actual save deferred to Supermemory integration                         |
| D10 | Step 16 `_conditional_ai_trigger()` always returns `True` — FULL mode, always called                                                                                        | AI final sign-off is the core value of this step                                                  |
| D11 | AI produces `design_summary`, `assumptions`, `design_strengths`, `design_risks`, and optionally `recommendations`                                                           | These become the "executive summary" the engineer reads                                           |

---

## Confidence Score Formula

### 4-Component Breakdown

$$\text{confidence\_score} = \sum_{i=1}^{4} w_i \cdot c_i$$

Where all $w_i = 0.25$ and $c_i \in [0.0, 1.0]$:

| Component                  | Variable                 | How Computed                                             |
| -------------------------- | ------------------------ | -------------------------------------------------------- |
| **Geometry Convergence**   | `geometry_convergence`   | See formula below                                        |
| **AI Agreement Rate**      | `ai_agreement_rate`      | `n_proceed / n_ai_called` (steps where `ai_called=True`) |
| **Supermemory Similarity** | `supermemory_similarity` | `0.5` (placeholder — neutral)                            |
| **Validation Pass Rate**   | `validation_passes`      | `n_first_attempt_pass / n_total_steps`                   |

### Geometry Convergence Score

$$
c_{geo} = \begin{cases}
1.0 & \text{if converged AND iterations} \leq 10 \\
1.0 - 0.5 \times \frac{\text{iterations} - 10}{10} & \text{if converged AND } 10 < \text{iterations} \leq 20 \\
0.0 & \text{if not converged}
\end{cases}
$$

**Data source:** `state.convergence_converged` (bool), `state.convergence_iteration` (int)

### AI Agreement Rate

$$c_{ai} = \frac{\text{count of StepRecords where } ai\_called{=}True \text{ AND } ai\_decision{=}PROCEED}{\text{count of StepRecords where } ai\_called{=}True}$$

- If no steps called AI (`n_ai_called == 0`): default to `0.5`
- `CORRECT` that succeeded counts as a partial pass — but for simplicity, only `PROCEED` counts as full agreement

**Data source:** `state.step_records` → filter `ai_called == True` → count `ai_decision == "proceed"`

### Validation Pass Rate (First-Attempt)

$$c_{val} = \frac{\text{steps that passed validation without corrections}}{\text{total steps with records}}$$

A step "passed on first attempt" when:

- `validation_passed == True` AND
- No corrections were applied (either `ai_review is None`, or `ai_review.decision == PROCEED`)

A step that received CORRECT/WARN-with-correction and then passed after correction does NOT count as first-attempt.

**Data source:** `state.step_records` → check `validation_passed` and `ai_decision`

### Score Interpretation

| Score Range | Meaning                           | Action                                          |
| ----------- | --------------------------------- | ----------------------------------------------- |
| ≥ 0.80      | High confidence — design is solid | No recommendations needed                       |
| 0.70–0.80   | Good — minor concerns             | List recommendations                            |
| 0.50–0.70   | Moderate — review flagged issues  | Strong recommendations, manual review suggested |
| < 0.50      | Low — significant concerns        | Warn engineer, flag specific problems           |

---

## Inputs (from DesignState)

```
1. PIPELINE TELEMETRY
   ├── step_records: list[StepRecord]   — all 15 prior step records
   ├── warnings: list[str]              — accumulated pipeline warnings
   ├── review_notes: list[dict]         — AI observations from all steps
   └── applied_corrections: list[dict]  — correction history

2. CONVERGENCE DATA (Step 12)
   ├── convergence_converged: bool
   ├── convergence_iteration: int
   └── convergence_trajectory: list[dict]

3. POST-CONVERGENCE RESULTS
   ├── vibration_safe: bool
   ├── vibration_details: dict
   ├── tube_thickness_ok: bool
   ├── shell_thickness_ok: bool
   ├── expansion_mm: float
   ├── mechanical_details: dict
   ├── cost_usd: float
   └── cost_breakdown: dict

4. DESIGN PERFORMANCE
   ├── U_overall_W_m2K: float
   ├── overdesign_pct: float
   ├── dP_tube_Pa, dP_shell_Pa: float
   ├── tube_velocity_m_s: float
   └── Q_W, LMTD_K, F_factor: float

5. IDENTITY
   ├── tema_type, tema_class
   ├── hot_fluid_name, cold_fluid_name
   ├── tube_material, shell_material
   └── geometry: GeometrySpec
```

---

## Computation Flow

```
1. PRECONDITION CHECK
   ├── step_records must contain records for steps 1–15
   ├── convergence_converged must not be None
   ├── vibration_safe must not be None
   ├── tube_thickness_ok, shell_thickness_ok must not be None
   └── cost_usd must not be None

2. COMPUTE geometry_convergence
   ├── If convergence_converged == False → 0.0
   ├── If convergence_iteration <= 10 → 1.0
   └── Else → 1.0 - 0.5 × (iteration - 10) / 10

3. COMPUTE ai_agreement_rate
   ├── Filter step_records where ai_called == True
   ├── Count those with ai_decision == "proceed"
   ├── If none called AI → 0.5
   └── Else → n_proceed / n_ai_called

4. SET supermemory_similarity
   └── 0.5 (placeholder)

5. COMPUTE validation_passes
   ├── For each step_record:
   │   ├── first_attempt = validation_passed AND
   │   │     (ai_decision is None OR ai_decision == "proceed")
   │   └── count first_attempt passes
   └── validation_passes = n_first_attempt / len(step_records)

6. COMPUTE confidence_score
   ├── breakdown = {
   │     "geometry_convergence": c_geo,
   │     "ai_agreement_rate": c_ai,
   │     "supermemory_similarity": 0.5,
   │     "validation_passes": c_val,
   │   }
   ├── score = sum(w * breakdown[k] for k, w in CONFIDENCE_WEIGHTS.items())
   └── Clamp to [0.0, 1.0]

7. COLLECT design context for AI
   ├── All warnings from pipeline
   ├── All review_notes
   ├── Post-convergence pass/fail summary
   ├── Key performance metrics (U, overdesign, dP, velocity, cost)
   └── Convergence trajectory

8. OUTPUTS → DesignState
   ├── confidence_score: float
   ├── confidence_breakdown: dict[str, float]
   ├── design_summary: str      (from AI)
   ├── assumptions: list[str]   (from AI)
   ├── design_strengths: list[str]  (from AI)
   └── design_risks: list[str]     (from AI)
```

---

## AI Prompt Design

Step 16's AI review is fundamentally different from all other steps. Other steps review a single calculation. Step 16 reviews the **entire design holistically**.

### What the AI Receives

1. **Deterministic confidence breakdown** (computed in Layer 1 — shown to AI as context)
2. **Complete design performance metrics** — U, Q, LMTD, F, overdesign, dP, velocity, cost
3. **Post-convergence status** — vibration (pass/fail + details), mechanical (pass/fail + details)
4. **All warnings accumulated** across 15 steps
5. **All `review_notes`** from AI observations at each step
6. **Convergence trajectory** — how did the geometry iterate
7. **Full `DesignState` JSON** (as with all steps)

### What the AI Produces

```json
{
  "decision": "proceed | warn | escalate",
  "confidence": 0.85,
  "reasoning": "Design meets all engineering criteria...",
  "design_summary": "Shell-and-tube heat exchanger (BEM, TEMA Class R) for cooling crude oil from 150°C to 90°C using cooling water...",
  "assumptions": [
    "Fouling factors from TEMA standards (not site-specific)",
    "Single-phase liquid operation assumed",
    "Turton cost correlations extrapolated for area > 500 m²"
  ],
  "design_strengths": [
    "Clean convergence in 7 iterations",
    "Overdesign of 18% — well within optimal range",
    "All vibration mechanisms safe with margin"
  ],
  "design_risks": [
    "Tube velocity 2.3 m/s — near erosion threshold for this service",
    "Shell-side pressure drop at 85% of limit"
  ],
  "recommendations": [
    "Consider increasing tube count to reduce velocity below 2.0 m/s",
    "Verify fouling factors against site-specific data before fabrication"
  ],
  "user_summary": "Design confidence: 0.82/1.0 — solid first-pass design ready for detailed engineering review."
}
```

### AI Cannot Do

- Modify the confidence score (it's deterministic)
- Override any previous step's calculations
- Change geometry or re-run convergence
- The AI **reviews and summarizes** — it doesn't compute

---

## Layer 2 Validation Rules (Hard Rules)

| Rule  | Check                                                             | Failure Message                                                                                                         |
| ----- | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| R16.1 | `confidence_score` is not None and `0.0 ≤ confidence_score ≤ 1.0` | "Confidence score must be between 0.0 and 1.0"                                                                          |
| R16.2 | `confidence_breakdown` is not None and has exactly 4 keys         | "Confidence breakdown must have exactly 4 components"                                                                   |
| R16.3 | Each value in `confidence_breakdown` is in `[0.0, 1.0]`           | "Each confidence component must be between 0.0 and 1.0"                                                                 |
| R16.4 | `design_summary` is not None and length > 0                       | "Design summary must be non-empty"                                                                                      |
| R16.5 | `confidence_breakdown` keys match expected names                  | "Confidence breakdown keys must be: geometry_convergence, ai_agreement_rate, supermemory_similarity, validation_passes" |

---

## Sub-Tasks

### ST-1: Add Missing Fields to `DesignState`

**File:** `hx_engine/app/models/design_state.py` — MODIFY  
**Action:** Add 3 fields that are planned but not yet declared

**Fields to add (near existing Step 16 fields):**

```python
# --- Step 16: Final Validation ---
confidence_score: Optional[float] = None
design_summary: Optional[str] = None
assumptions: list[str] = Field(default_factory=list)
```

**Already declared (no change needed):**

- `confidence_breakdown: Optional[dict[str, float]]`
- `design_strengths: list[str]`
- `design_risks: list[str]`

#### ST-1 Tests

| Test | Description                                                                             | Asserts               |
| ---- | --------------------------------------------------------------------------------------- | --------------------- |
| T1.1 | DesignState initializes with `confidence_score=None`                                    | Default is None       |
| T1.2 | DesignState initializes with `design_summary=None`                                      | Default is None       |
| T1.3 | DesignState initializes with `assumptions=[]`                                           | Default is empty list |
| T1.4 | `confidence_score` accepts float in [0.0, 1.0]                                          | No validation error   |
| T1.5 | Existing fields (`confidence_breakdown`, `design_strengths`, `design_risks`) still work | No regression         |

---

### ST-2: Create `step_16_final_validation.py` — Confidence Computation + AI Sign-Off

**File:** `hx_engine/app/steps/step_16_final_validation.py` — CREATE  
**Action:** Step class that computes the deterministic confidence breakdown, then returns result for AI review

**Module-level constants:**

```python
CONFIDENCE_WEIGHTS: dict[str, float] = {
    "geometry_convergence": 0.25,
    "ai_agreement_rate": 0.25,
    "supermemory_similarity": 0.25,
    "validation_passes": 0.25,
}

SUPERMEMORY_SIMILARITY_PLACEHOLDER = 0.5
```

**Class structure:**

```python
class Step16FinalValidation(BaseStep):
    step_id: int = 16
    step_name: str = "Final Validation"
    ai_mode: AIModeEnum = AIModeEnum.FULL

    def _conditional_ai_trigger(self, state: "DesignState") -> bool:
        return True  # Always call AI (FULL mode)

    @staticmethod
    def _check_preconditions(state: "DesignState") -> list[str]:
        """Verify Steps 1–15 data is present."""
        ...

    async def execute(self, state: "DesignState") -> StepResult:
        """Compute confidence breakdown deterministically."""
        ...
```

**`execute()` logic:**

1. Check preconditions → raise `CalculationError` if missing critical data
2. Compute `geometry_convergence` from `state.convergence_converged` and `state.convergence_iteration`
3. Compute `ai_agreement_rate` from `state.step_records`
4. Set `supermemory_similarity = 0.5`
5. Compute `validation_passes` from `state.step_records`
6. Build `confidence_breakdown` dict
7. Compute `confidence_score` as weighted sum
8. Write to state: `state.confidence_score`, `state.confidence_breakdown`
9. Return `StepResult` with breakdown in `outputs`

**Note:** `design_summary`, `assumptions`, `design_strengths`, `design_risks` are populated by the AI review (Layer 3), NOT by the `execute()` method (Layer 1). The `execute()` method only computes the deterministic confidence. The AI review callback in `run_with_review_loop` will extract these from the AI response and write them to state.

**Helper functions (private, testable):**

```python
def _compute_geometry_convergence(
    converged: bool | None,
    iteration: int | None,
) -> float:
    """Score convergence quality. Returns 0.0–1.0."""

def _compute_ai_agreement_rate(
    step_records: list[StepRecord],
) -> float:
    """Fraction of AI-reviewed steps that returned PROCEED."""

def _compute_validation_pass_rate(
    step_records: list[StepRecord],
) -> float:
    """Fraction of steps that passed validation on first attempt."""

def _compute_confidence_score(
    breakdown: dict[str, float],
    weights: dict[str, float],
) -> float:
    """Weighted sum, clamped to [0.0, 1.0]."""
```

#### ST-2 Tests

| Test                     | Description                                                                                      | Asserts                                  |
| ------------------------ | ------------------------------------------------------------------------------------------------ | ---------------------------------------- |
| **Geometry convergence** |                                                                                                  |                                          |
| T2.1                     | Converged in 5 iterations → `1.0`                                                                | Exact                                    |
| T2.2                     | Converged in 10 iterations → `1.0`                                                               | Exact                                    |
| T2.3                     | Converged in 15 iterations → `0.75`                                                              | Linear interpolation                     |
| T2.4                     | Converged in 20 iterations → `0.5`                                                               | Minimum converged score                  |
| T2.5                     | Not converged → `0.0`                                                                            | Hard zero                                |
| T2.6                     | `converged=None` (Step 12 didn't run) → `0.0`                                                    | Defensive                                |
| T2.7                     | `iteration=None` but `converged=True` → `1.0` (assume clean)                                     | Edge case                                |
| **AI agreement rate**    |                                                                                                  |                                          |
| T2.8                     | All 6 AI-called steps returned PROCEED → `1.0`                                                   | Perfect agreement                        |
| T2.9                     | 4 of 6 returned PROCEED, 2 CORRECT → `0.667`                                                     | Partial                                  |
| T2.10                    | No steps called AI (`ai_called=False` for all) → `0.5`                                           | Default neutral                          |
| T2.11                    | 1 PROCEED, 1 WARN, 1 CORRECT → count only PROCEED / total called                                 | `0.333`                                  |
| T2.12                    | Mixed: some `ai_called=False`, some True → only count True                                       | Correct denominator                      |
| **Validation pass rate** |                                                                                                  |                                          |
| T2.13                    | All 15 steps passed first attempt → `1.0`                                                        | Perfect                                  |
| T2.14                    | 12 of 15 passed first attempt → `0.8`                                                            | Partial                                  |
| T2.15                    | Step with `ai_decision=CORRECT` but `validation_passed=True` → NOT first attempt                 | Correct exclusion                        |
| T2.16                    | Step with `ai_decision=None` and `validation_passed=True` → first attempt                        | AI wasn't called → counts                |
| T2.17                    | Step with `ai_decision=WARN` (with corrections) and `validation_passed=True` → NOT first attempt | WARN-with-correction = not first attempt |
| T2.18                    | Empty `step_records` → `0.5` default                                                             | Defensive                                |
| **Overall confidence**   |                                                                                                  |                                          |
| T2.19                    | All components 1.0 → score = 1.0                                                                 | Maximum                                  |
| T2.20                    | All components 0.0 → score = 0.0                                                                 | Minimum                                  |
| T2.21                    | Components [1.0, 0.8, 0.5, 0.6] → score = 0.725                                                  | Weighted sum                             |
| T2.22                    | Weights sum to 1.0                                                                               | Sanity check on `CONFIDENCE_WEIGHTS`     |
| **Preconditions**        |                                                                                                  |                                          |
| T2.23                    | Missing `convergence_converged` → precondition error                                             | CalculationError raised                  |
| T2.24                    | Missing `vibration_safe` → precondition error                                                    | CalculationError raised                  |
| T2.25                    | Missing `cost_usd` → precondition error                                                          | CalculationError raised                  |
| T2.26                    | All preconditions met → no error                                                                 | Clean execution                          |
| **Full execute()**       |                                                                                                  |                                          |
| T2.27                    | execute() with complete state → returns StepResult with confidence_breakdown in outputs          | Full flow                                |
| T2.28                    | execute() writes `confidence_score` and `confidence_breakdown` to state                          | State mutation                           |
| T2.29                    | `confidence_score` always in [0.0, 1.0]                                                          | Clamped                                  |

---

### ST-3: Create `step_16_rules.py` — Layer 2 Validation Rules

**File:** `hx_engine/app/steps/step_16_rules.py` — CREATE  
**Action:** 5 hard rules auto-registered on import

**Rules:**

```python
def _rule_confidence_computed(step_id, result) -> tuple[bool, str | None]:
    """R16.1 — confidence_score exists and is in [0.0, 1.0]."""

def _rule_breakdown_complete(step_id, result) -> tuple[bool, str | None]:
    """R16.2 — confidence_breakdown has exactly 4 keys."""

def _rule_breakdown_values_valid(step_id, result) -> tuple[bool, str | None]:
    """R16.3 — each breakdown value is in [0.0, 1.0]."""

def _rule_summary_present(step_id, result) -> tuple[bool, str | None]:
    """R16.4 — design_summary is non-empty."""

def _rule_breakdown_keys_correct(step_id, result) -> tuple[bool, str | None]:
    """R16.5 — breakdown keys match expected names."""

def register_step16_rules() -> None:
    register_rule(16, _rule_confidence_computed)
    register_rule(16, _rule_breakdown_complete)
    register_rule(16, _rule_breakdown_values_valid)
    register_rule(16, _rule_summary_present)
    register_rule(16, _rule_breakdown_keys_correct)

register_step16_rules()
```

**Note on R16.4 (`design_summary`):** The summary comes from the AI response, not from `execute()`. The rule needs to check the `result.outputs` dict. If AI wasn't called (stub mode / convergence loop — shouldn't happen for FULL mode, but defensively), provide a generated fallback summary in `execute()`.

#### ST-3 Tests

| Test  | Description                                                                       | Asserts                |
| ----- | --------------------------------------------------------------------------------- | ---------------------- |
| T3.1  | Valid result with score 0.82, 4-key breakdown, non-empty summary → all rules pass | All pass               |
| T3.2  | Missing `confidence_score` → R16.1 fails                                          | Correct rule triggered |
| T3.3  | `confidence_score = 1.5` → R16.1 fails                                            | Out of range           |
| T3.4  | `confidence_score = -0.1` → R16.1 fails                                           | Out of range           |
| T3.5  | Breakdown with 3 keys → R16.2 fails                                               | Wrong count            |
| T3.6  | Breakdown with 5 keys → R16.2 fails                                               | Wrong count            |
| T3.7  | Breakdown value 1.5 → R16.3 fails                                                 | Out of range           |
| T3.8  | Empty `design_summary` → R16.4 fails                                              | Non-empty required     |
| T3.9  | Wrong breakdown key names → R16.5 fails                                           | Key mismatch           |
| T3.10 | All valid → all 5 rules pass                                                      | Comprehensive pass     |

---

### ST-4: Add AI Prompts for Steps 10–16 in `ai_engineer.py`

**File:** `hx_engine/app/core/ai_engineer.py` — MODIFY  
**Action:** Add `_STEP_10_PROMPT` through `_STEP_16_PROMPT` and entries in `_STEP_PROMPTS` dict. Also add `_build_step_context()` cases for steps 10–16.

#### Step 10 Prompt — Pressure Drops

```
## Step 10: Pressure Drops — Review Focus

YOUR REVIEW FOCUS:
1. Are tube-side and shell-side pressure drops within acceptable limits?
2. Is there sufficient margin (>15%) below the hard limits?
3. Are nozzle pressure drops reasonable (ρv² < 2230 kg/m·s²)?
4. Is pressure drop distribution reasonable between tube-side and shell-side?

COMMON ISSUES:
- Pressure drop too close to limit — recommend geometry adjustment
- Very low dP may indicate low velocity and fouling risk
- Nozzle ρv² near limit suggests nozzle diameter too small

DO NOT: Override hard dP limits. These are Layer 2 safety rules.
```

#### Step 11 Prompt — Area + Overdesign

```
## Step 11: Area + Overdesign — Review Focus

YOUR REVIEW FOCUS:
1. Is overdesign percentage in the optimal 10–25% range?
2. Is the required area estimate consistent with the estimated U from Step 6?
3. If overdesign is 0–10% or 25–40%, is the design still acceptable?

COMMON ISSUES:
- Overdesign < 10% — insufficient margin for fouling/uncertainty
- Overdesign > 30% — oversized, cost inefficient
- Large deviation between estimated and calculated area — indicates poor initial U guess

DO NOT: Accept negative overdesign (hard fail). Do not recommend area changes — Step 12 convergence handles this.
```

#### Step 12 Prompt — Convergence (only called if loop fails after 20 iterations)

```
## Step 12: Convergence Loop Failure — Review Focus

You are reviewing a convergence failure after 20 iterations.

YOUR REVIEW FOCUS:
1. Is there an oscillating pattern in the convergence trajectory?
2. What is preventing convergence — dP limits? overdesign? velocity?
3. Can a structural geometry change resolve it (different shell size, tube passes)?

This review is only called when automated convergence fails. Recommend specific geometry changes.

DO NOT: Suggest "try more iterations." The limit is 20 for good reason.
```

#### Step 13 Prompt — Vibration Check

```
## Step 13: Vibration Check (5 Mechanisms) — Review Focus

SAFETY-CRITICAL REVIEW.

YOUR REVIEW FOCUS:
1. Are all 5 vibration mechanisms safe (fluidelastic, vortex, buffeting, acoustic, whirling)?
2. Is the Connors criterion margin adequate (u_cross/u_crit < 0.5)?
3. Are inlet/outlet spans checked separately (1.5× central span — most critical)?
4. If any mechanism fails, what is the minimum safe geometry change?

COMMON ISSUES:
- Inlet span failure with safe central span — check baffle spacing
- Acoustic resonance triggered in gas service — check Strouhal number
- Marginal Connors ratio (0.4–0.5) — recommend conservative action

DO NOT: Override vibration safety limits. These are engineering safety rules.
```

#### Step 14 Prompt — Mechanical Design

```
## Step 14: Mechanical Design Check — Review Focus

YOUR REVIEW FOCUS:
1. Do tube and shell wall thicknesses meet ASME VIII Div 1 minimums (UG-27/UG-28)?
2. Is the thickness margin adequate (>20%)?
3. Is thermal expansion differential within tolerance for the TEMA type?
4. If fixed tubesheet (BEM/NEN) and expansion > 3mm — should rear head type change?

COMMON ISSUES:
- External pressure governs over internal pressure — verify vacuum condition
- Thin-wall tubes (BWG 16+) marginal under external pressure
- Large expansion differential on fixed tubesheet — needs floating head

DO NOT: Change TEMA type without flagging as ESCALATE. Geometry changes need Step 12 re-run.
```

#### Step 15 Prompt — Cost Estimate

```
## Step 15: Cost Estimate — Review Focus

YOUR REVIEW FOCUS:
1. Is the bare module cost reasonable for this size, material, and pressure?
2. Is cost/m² within the expected range for the tube material?
3. Are material factor and pressure factor reasonable?
4. Is the CEPCI index current (< 90 days old)?

COMMON ISSUES:
- Very high cost/m² may indicate expensive material where cheaper alternative exists
- Very low cost may indicate missing pressure or material correction
- Interpolated material factor (not from Turton directly) — verify reasonableness

DO NOT: Override cost calculations. Flag anomalies for user review.
```

#### Step 16 Prompt — Final Validation (the unique one)

```
## Step 16: Final Validation + Confidence Score — Review Focus

You are performing the FINAL ENGINEERING SIGN-OFF on a complete heat exchanger design.
Review the entire design holistically — not just one calculation.

THE DETERMINISTIC CONFIDENCE SCORE HAS ALREADY BEEN COMPUTED (shown below).
Your job is NOT to recompute or override it. Your job is to:

YOUR REVIEW FOCUS:
1. Produce a plain-English DESIGN SUMMARY (2–4 sentences describing the design)
2. List ALL ASSUMPTIONS made across the 16 steps — both explicit and implicit
3. Identify DESIGN STRENGTHS — what makes this design reliable
4. Identify DESIGN RISKS — what could go wrong or needs verification
5. Provide RECOMMENDATIONS if confidence < 0.80

COMMON ASSUMPTIONS TO CHECK FOR:
- Fouling factors from TEMA tables (not site-specific data)
- Single-phase liquid operation assumed throughout
- Fluid properties at bulk mean temperature (not wall temperature)
- Turton cost correlations (2001 base year, validity range)
- CEPCI projection for 2026
- Baffle-to-shell and tube-to-baffle clearances from TEMA standards
- No phase change at any point in the exchanger

WHAT MAKES A GOOD SUMMARY:
- Mention: TEMA type, fluids, duty, key geometry (shell size, tube count, length)
- State the overall U and overdesign percentage
- Note any safety concerns (vibration, mechanical)
- State the estimated cost
- Be specific — avoid vague statements

RESPOND WITH JSON including: decision, confidence, reasoning, design_summary,
assumptions (list), design_strengths (list), design_risks (list),
recommendations (list — only if confidence < 0.80), user_summary.

DO NOT: Modify the confidence score. DO NOT suggest geometry changes (design is finalized).
DO NOT produce vague summaries like "the design looks good."
```

#### `_build_step_context()` Cases for Steps 10–16

| Step | Context Built                                                                 | Data Sources             |
| ---- | ----------------------------------------------------------------------------- | ------------------------ |
| 10   | dP tube/shell with limits, margins, nozzle ρv², velocity context              | Step 10 outputs          |
| 11   | overdesign %, area estimated vs required, U estimated vs calculated deviation | Step 11 + Step 6 outputs |
| 12   | Convergence trajectory summary, constraint violations, iterations             | Step 12 outputs          |
| 13   | Per-mechanism pass/fail, Connors ratios, critical spans                       | Step 13 outputs          |
| 14   | Tube/shell t_actual vs t_min, margins, expansion mm, TEMA type                | Step 14 outputs          |
| 15   | cost_usd, cost/m², material factor, pressure factor, CEPCI staleness          | Step 15 outputs          |
| 16   | **Full dashboard — see below**                                                | All steps                |

**Step 16 `_build_step_context()`** — unique, comprehensive:

```
CONFIDENCE BREAKDOWN (deterministic):
  geometry_convergence: {c_geo}
  ai_agreement_rate:    {c_ai}
  supermemory_similarity: 0.5 (placeholder)
  validation_passes:    {c_val}
  WEIGHTED SCORE:       {score}

DESIGN PERFORMANCE:
  Q = {Q_W} W, LMTD = {LMTD_K} K, F = {F_factor}
  U_overall = {U} W/m²K, overdesign = {overdesign_pct}%
  dP_tube = {dP_tube} Pa ({pct_limit_tube}% of limit)
  dP_shell = {dP_shell} Pa ({pct_limit_shell}% of limit)
  Tube velocity = {v} m/s

POST-CONVERGENCE:
  Vibration: {vibration_safe} — {vibration_summary}
  Mechanical: tubes={tube_ok}, shell={shell_ok}, expansion={expansion_mm}mm
  Cost: ${cost_usd} (cost/m² = ${cost_per_m2})

CONVERGENCE: {converged} in {n_iter} iterations

PIPELINE WARNINGS ({n_warnings} total):
  {formatted_warnings}

AI REVIEW NOTES ({n_notes} total):
  {formatted_review_notes}
```

#### ST-4 Tests

| Test | Description                                                       | Asserts                    |
| ---- | ----------------------------------------------------------------- | -------------------------- |
| T4.1 | `_STEP_PROMPTS` dict has entries for steps 1–16 (all 16)          | `len(_STEP_PROMPTS) == 16` |
| T4.2 | Step 16 prompt contains "FINAL ENGINEERING SIGN-OFF"              | Correct prompt loaded      |
| T4.3 | `_build_step_context()` for step 16 includes confidence breakdown | Context string present     |
| T4.4 | `_build_step_context()` for step 10 includes dP values            | Context string present     |
| T4.5 | Steps 10–15 prompts each contain "Review Focus" section           | Consistent format          |
| T4.6 | No step prompt is empty string                                    | All defined                |

---

### ST-5: Handle AI Response Parsing for Step 16

**File:** `hx_engine/app/steps/step_16_final_validation.py` — MODIFY (or `base.py` / `ai_engineer.py`)  
**Action:** Ensure the AI response for Step 16 (which has extra fields: `design_summary`, `assumptions`, `design_strengths`, `design_risks`, `recommendations`) is parsed and written to `DesignState`.

**Approach:** After the AI review in `run_with_review_loop()`, if `step_id == 16` and `ai_review` is not None, extract the extra fields from the AI response and write them to state. This can be done by overriding `_post_ai_review()` in Step 16 (if that hook exists) or by doing it in `execute()` as a post-processing step.

**Actually:** Looking at the BaseStep flow, the AI review JSON is returned as `AIReview`. The `reasoning` field and raw response are accessible. The cleanest approach is:

1. Add optional fields to `AIReview` model: `design_summary`, `assumptions`, `design_strengths`, `design_risks`, `recommendations` — all `Optional`, only populated for Step 16.
2. In `ai_engineer.py` `_parse_response()` — extract these fields from the JSON response if present.
3. In `step_16_final_validation.py` — after `run_with_review_loop()` completes (or in a post-review hook), copy these from `result.ai_review` to `state`.

**Alternative (simpler):** Keep `AIReview` unchanged. In Step 16's `execute()`, return the confidence breakdown. Then add a `_post_review_hook()` override in Step 16 that parses the AI response `reasoning` field for the extra structured data. Or, override `run_with_review_loop()` in Step 16 to capture the AI response.

**Recommended approach:** Override a method in Step16 that runs after AI review. The `BaseStep` already calls `_record()` after review. We can add a `_apply_ai_extras(state, ai_review)` method that Step 16 overrides:

```python
# In BaseStep (or just in Step16 override of run_with_review_loop):
def _apply_ai_extras(self, state: "DesignState", ai_review: "AIReview") -> None:
    """Hook for steps that need to extract extra fields from AI response.
    Default: no-op. Step 16 overrides this."""
    pass
```

Then in Step 16:

```python
def _apply_ai_extras(self, state: "DesignState", ai_review: "AIReview") -> None:
    """Extract design_summary, assumptions, strengths, risks from AI response."""
    if ai_review and ai_review.raw_response:
        data = ai_review.raw_response  # or parse from reasoning
        state.design_summary = data.get("design_summary", "")
        state.assumptions = data.get("assumptions", [])
        state.design_strengths = data.get("design_strengths", [])
        state.design_risks = data.get("design_risks", [])
```

**Decision needed during implementation:** Check if `AIReview` has a `raw_response` field or if extra JSON fields are silently dropped during parsing. Adjust approach accordingly.

#### ST-5 Tests

| Test | Description                                                      | Asserts                            |
| ---- | ---------------------------------------------------------------- | ---------------------------------- |
| T5.1 | AI response with `design_summary` field → written to state       | `state.design_summary` populated   |
| T5.2 | AI response with `assumptions` list → written to state           | `state.assumptions` has entries    |
| T5.3 | AI response with `design_strengths` → written to state           | `state.design_strengths` populated |
| T5.4 | AI response with `design_risks` → written to state               | `state.design_risks` populated     |
| T5.5 | AI response missing these fields (stub mode) → fallback defaults | Empty list / generated summary     |
| T5.6 | Stub AI mode → `design_summary` gets a generated fallback string | Non-empty summary even without AI  |

---

### ST-6: Wire Step 16 into `pipeline_runner.py` + Enrich `_build_summary()`

**File:** `hx_engine/app/core/pipeline_runner.py` — MODIFY  
**Action:**

1. Import `Step16FinalValidation`
2. Add Step 16 as final post-convergence step (after Step 15, before `DesignCompleteEvent`)
3. Enrich `_build_summary()` with confidence, cost, vibration, mechanical data
4. Set `state.is_complete = True` after Step 16

**Pipeline flow after change:**

```python
# --- Step 15: Cost Estimate ---
if state.pipeline_status == "running":
    state = await self._run_post_convergence_step(
        state, session_id, Step15CostEstimate(),
    )

# --- Step 16: Final Validation + Confidence Score ---
if state.pipeline_status == "running":
    state = await self._run_post_convergence_step(
        state, session_id, Step16FinalValidation(),
    )

# --- Pipeline Complete ---
if state.pipeline_status == "running":
    state.pipeline_status = "complete"
    state.is_complete = True
    summary = self._build_summary(state)
    await self.sse_manager.emit(
        session_id,
        DesignCompleteEvent(session_id=session_id, summary=summary).model_dump(),
    )
```

**Enriched `_build_summary()`:**

```python
@staticmethod
def _build_summary(state: DesignState) -> dict[str, Any]:
    summary = {
        # --- existing fields ---
        "session_id": state.session_id,
        "pipeline_status": state.pipeline_status,
        "completed_steps": state.completed_steps,
        "Q_W": state.Q_W,
        "LMTD_K": state.LMTD_K,
        "F_factor": state.F_factor,
        "U_W_m2K": state.U_W_m2K,
        "A_m2": state.A_m2,
        "tema_type": state.tema_type,
        "tema_class": state.tema_class,
        "multi_shell_arrangement": state.multi_shell_arrangement,
        "n_shells": state.geometry.n_shells if state.geometry else None,
        "warnings": state.warnings,
        "notes": state.notes,
        "geometry": state.geometry.model_dump() if state.geometry else None,
        # --- new fields (Step 16) ---
        "confidence_score": state.confidence_score,
        "confidence_breakdown": state.confidence_breakdown,
        "design_summary": state.design_summary,
        "vibration_safe": state.vibration_safe,
        "tube_thickness_ok": state.tube_thickness_ok,
        "shell_thickness_ok": state.shell_thickness_ok,
        "cost_usd": state.cost_usd,
        "overdesign_pct": state.overdesign_pct,
        "design_strengths": state.design_strengths,
        "design_risks": state.design_risks,
    }
    return summary
```

#### ST-6 Tests

| Test | Description                                                                  | Asserts                           |
| ---- | ---------------------------------------------------------------------------- | --------------------------------- |
| T6.1 | Step 16 import present in `pipeline_runner.py`                               | No ImportError                    |
| T6.2 | Pipeline runs Step 16 after Step 15                                          | `16 in state.completed_steps`     |
| T6.3 | `state.is_complete == True` after Step 16                                    | Flag set                          |
| T6.4 | `state.pipeline_status == "complete"` after Step 16                          | Status set                        |
| T6.5 | `DesignCompleteEvent` emitted with enriched summary                          | Event contains `confidence_score` |
| T6.6 | `_build_summary()` includes `confidence_score`, `cost_usd`, `vibration_safe` | New fields present                |
| T6.7 | `_build_summary()` still includes all original fields                        | No regression                     |

---

### ST-7: Update `state_utils.py` `_OUTPUT_FIELD_MAP` (if needed)

**File:** `hx_engine/app/core/state_utils.py` — MODIFY  
**Action:** Add Step 16 output field mappings to `_OUTPUT_FIELD_MAP` so `_apply_outputs()` works correctly.

**Mappings to add:**

```python
"confidence_score": "confidence_score",
"confidence_breakdown": "confidence_breakdown",
"design_summary": "design_summary",
"assumptions": "assumptions",
"design_strengths": "design_strengths",
"design_risks": "design_risks",
```

**Note:** Check if Steps 14–15 also need their mappings added (the subagent reported they "write directly to state in their `execute()` methods"). If so, add those too for consistency, but that's technically outside Step 16 scope.

#### ST-7 Tests

| Test | Description                                                      | Asserts              |
| ---- | ---------------------------------------------------------------- | -------------------- |
| T7.1 | `_apply_outputs()` with Step 16 outputs → state fields populated | All 6 fields written |
| T7.2 | Existing mappings (Steps 1–13) still work                        | No regression        |

---

### ST-8: Integration Tests

**File:** `tests/integration/test_step_16_integration.py` — CREATE  
**Action:** Full integration test with mock AI

#### Test Cases

| Test  | Description                                                                          | Asserts                        |
| ----- | ------------------------------------------------------------------------------------ | ------------------------------ |
| T8.1  | Step 16 with fully populated state from Steps 1–15 → produces valid confidence score | `0.0 ≤ confidence_score ≤ 1.0` |
| T8.2  | `confidence_breakdown` has exactly 4 keys with correct names                         | Keys match expected            |
| T8.3  | Each breakdown component is in [0.0, 1.0]                                            | Range check                    |
| T8.4  | With all PROCEED AI decisions → `ai_agreement_rate` close to 1.0                     | High agreement                 |
| T8.5  | With mixed PROCEED/CORRECT decisions → `ai_agreement_rate` < 1.0                     | Partial agreement              |
| T8.6  | Converged in 5 iterations → `geometry_convergence == 1.0`                            | Clean convergence              |
| T8.7  | Not converged → `geometry_convergence == 0.0`                                        | Failure path                   |
| T8.8  | All validation passed first attempt → `validation_passes == 1.0`                     | Perfect path                   |
| T8.9  | Some steps with corrections → `validation_passes < 1.0`                              | Partial path                   |
| T8.10 | Stub AI mode → still produces fallback summary                                       | Non-empty `design_summary`     |
| T8.11 | Layer 2 rules all pass on valid output                                               | No validation errors           |
| T8.12 | Step 16 `StepRecord` stored in `state.step_records`                                  | Record present                 |

---

### ST-9: Regression Tests

**File:** `tests/integration/test_step_16_regression.py` — CREATE  
**Action:** Property-based edge case coverage

| Test | Description                                                                     | Asserts                      |
| ---- | ------------------------------------------------------------------------------- | ---------------------------- |
| T9.1 | State with 0 step_records → still computes (defaults to 0.5 for pass rates)     | No crash                     |
| T9.2 | State with only 5 step_records (partial pipeline) → still computes              | Graceful                     |
| T9.3 | All components at extremes (all 0.0 vs all 1.0) → score clamped correctly       | [0.0, 1.0]                   |
| T9.4 | `convergence_iteration = 0` → treated as 1 (converged trivially)                | `geometry_convergence = 1.0` |
| T9.5 | Very large warnings list (100+) → no performance issue                          | Completes in < 1s            |
| T9.6 | `design_summary` with special characters (unicode, newlines) → rules still pass | No encoding issue            |
| T9.7 | Confidence score exactly 0.75 → Supermemory save path (stub/TODO) triggered     | Logic correct                |

---

## Implementation Order

```
ST-1: Add missing DesignState fields (confidence_score, design_summary, assumptions)
  ↓
ST-2: Create step_16_final_validation.py (confidence computation)
  ↓
ST-3: Create step_16_rules.py (Layer 2 validation)
  ↓
ST-4: Add AI prompts for Steps 10–16 in ai_engineer.py
  ↓
ST-5: Handle AI response parsing for Step 16 extra fields
  ↓
ST-7: Update state_utils.py output field map
  ↓
ST-6: Wire into pipeline_runner.py + enrich _build_summary()
  ↓
ST-8: Integration tests
  ↓
ST-9: Regression tests
```

**ST-1 → ST-2 → ST-3** are the core path (can test independently).  
**ST-4** is large but independent of ST-2/ST-3.  
**ST-5** depends on ST-2 + understanding of `AIReview` response parsing.  
**ST-6** depends on all prior sub-tasks.  
**ST-8/ST-9** run last.

---

## Files Created / Modified

| File                                              | Action                                   | Sub-Task  |
| ------------------------------------------------- | ---------------------------------------- | --------- |
| `hx_engine/app/models/design_state.py`            | MODIFY — add 3 fields                    | ST-1      |
| `hx_engine/app/steps/step_16_final_validation.py` | CREATE                                   | ST-2      |
| `hx_engine/app/steps/step_16_rules.py`            | CREATE                                   | ST-3      |
| `hx_engine/app/core/ai_engineer.py`               | MODIFY — add 7 prompts + 7 context cases | ST-4      |
| `hx_engine/app/steps/step_16_final_validation.py` | MODIFY — AI extras parsing               | ST-5      |
| `hx_engine/app/core/pipeline_runner.py`           | MODIFY — wire Step 16 + enrich summary   | ST-6      |
| `hx_engine/app/core/state_utils.py`               | MODIFY — add output field mappings       | ST-7      |
| `tests/unit/test_step_16_final_validation.py`     | CREATE                                   | ST-2/ST-3 |
| `tests/integration/test_step_16_integration.py`   | CREATE                                   | ST-8      |
| `tests/integration/test_step_16_regression.py`    | CREATE                                   | ST-9      |

---

## Risk Register

| Risk                                                                | Impact                 | Mitigation                                                                                  |
| ------------------------------------------------------------------- | ---------------------- | ------------------------------------------------------------------------------------------- |
| AI response doesn't include `design_summary` / `assumptions` fields | Missing data in output | Fallback generation in `_apply_ai_extras` — build summary from state data deterministically |
| `AIReview` model silently drops unknown JSON fields                 | AI extras never parsed | Check model config (`extra = "allow"` or add explicit Optional fields) during ST-5          |
| Steps 10–15 AI prompts untested with real Claude                    | Poor review quality    | Each prompt follows the established pattern; prompts are additive, not breaking             |
| Supermemory placeholder (0.5) inflates/deflates score               | Misleading confidence  | 0.5 is deliberately neutral — equal weight means it shifts score by ±0.125 at most          |
| `_build_summary()` changes break frontend expectations              | Frontend regression    | Summary only adds new keys — existing keys unchanged                                        |

---

## Out of Scope

- Supermemory integration (past_designs save, similarity scoring)
- Supermemory book context for Step 16 AI prompt
- Frontend changes to display confidence breakdown
- E2E 16-step pipeline test (separate task once all steps are wired)
- `_build_step_context()` cases for Steps 10–15 (only Step 16 context is critical for correct review)

**Wait — per D7, we are adding prompts for Steps 10–16. But `_build_step_context()` cases are also useful for Steps 10–15.** Decision: Add `_build_step_context()` cases for Steps 10–16 as part of ST-4. The prompts without context would still work (they'd use the default empty string), but context makes reviews higher quality.
