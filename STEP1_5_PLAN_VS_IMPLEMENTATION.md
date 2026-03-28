# ARKEN AI — Plan vs. Implementation Review (Steps 1–5)

**Scope:** Weeks 1–2 of the Master Plan (§14)
**Date:** 2026-03-27
**Source:** ARKEN_MASTER_PLAN.md v8.0 vs. codebase as-built

---

## Summary Verdict

| Area | Status |
|------|--------|
| Week 1 Foundation (contracts, infra, base) | **~85% complete** — missing 3 DesignState fields + no external prompt file |
| Week 2 Step Implementations (Steps 1–5) | **~75% complete** — Step 2 execute() not wired; correction loop state bug |
| Week 1 Tests | **Exceeds plan** — 24 tests where 12 required |
| Week 2 Tests (per-step unit) | **Complete** — all planned test files present |
| Week 2 Tests (integration pipeline) | **Missing** — no integration test folder at all |
| Extras not in plan | `fouling_ai.py`, `fouling_store.py`, `petroleum_correlations.py` |

---

## 1. Week 1 — Foundation

### 1.1 Data Models

#### DesignState (`models/design_state.py`)

| Plan Requires | In Code | Gap |
|---|---|---|
| `waiting_for_user: bool = False` | ✅ Present | — |
| `in_convergence_loop: bool = False` | ✅ Present | — |
| `org_id: Optional[str] = None` | ✅ Present | — |
| `review_notes: List[str] = Field(default_factory=list)` | ❌ Missing | No forward-looking AI observation chain |
| `confidence_breakdown: Optional[dict] = None` | ❌ Missing | Confidence explainability (CEO-CP2) not wired |
| `step_records: List[StepRecord]` (typed) | ⚠️ Partial | Exists as `list[dict[str, Any]]` — untyped |
| `default_factory=list` for mutable fields | ✅ Present | — |
| `snapshot_fields(field_names) -> dict` method | ❌ Missing | Required by correction loop in plan §7.5 |
| `restore(snapshot: dict) -> None` method | ❌ Missing | Required for rollback on Layer 2 hard fail |

**Impact of `review_notes` missing:** By Step 9, the AI is supposed to see accumulated engineering observations from Steps 1–8 (e.g., "viscosity corrected in Step 3 — affects this step"). Without this, the AI reviews each step in isolation and cannot reason across steps. This is a core feature of the plan's trust model.

**Impact of `snapshot_fields`/`restore` missing:** The correction loop in `base.py` cannot safely rollback state after a Layer 2 failure. Currently, a failed correction leaves state partially mutated — the plan explicitly requires atomic correction.

#### StepResult / AIReview / AIDecision

| Plan Requires | In Code | Gap |
|---|---|---|
| `StepResult`, `AIDecision` enum, `AIModeEnum` | ✅ Present | — |
| `StepRecord` with `step_id`, `step_name`, `result`, `timestamp`, `duration_ms`, `ai_called` | ⚠️ Partial | Exists as `dict` in step_records list, not as typed Pydantic model |

#### SSE Events (`models/sse_events.py`)

| Plan Requires | Status |
|---|---|
| 8 event types (plan explicitly says 8, not 9 — /btw deferred) | ✅ Present |
| `step_error` payload includes `observation`, `recommendation`, `options` | Needs verification |

#### StepProtocol (`steps/__init__.py`)

| Plan Requires | Status |
|---|---|
| `@runtime_checkable` Protocol with `step_id`, `step_name`, `execute()` | ✅ Present |

---

### 1.2 Infrastructure

| Plan Requires | In Code | Gap |
|---|---|---|
| `session_store.py` — `heartbeat()` + `is_orphaned()` | ✅ Present | — |
| `PIPELINE_ORPHAN_THRESHOLD_SECONDS = 120` in `config.py` | ❌ Not verified | Needs check |
| `sse_manager.py` — asyncio.Queue per session + escalation future management | ✅ Present | — |
| `main.py` with `/health` endpoint + lifespan | ✅ Present | — |
| `exceptions.py` — `CalculationError(step_id, message, cause)` | ✅ Present | — |

---

### 1.3 AI Engineer (`core/ai_engineer.py`)

| Plan Requires | In Code | Gap |
|---|---|---|
| Single `.create()` call, NOT an agent | ✅ Correct | — |
| Retry 2× with backoff on failure [CEO-3A] | ✅ Present | — |
| On 3 failures: `WARN` + `ai_called=False` | ✅ Present | — |
| Stub mode when API key missing | ✅ Present | Good for testing |
| `model="claude-sonnet-4-6"` | ✅ Present | — |
| Load system prompt from `core/prompts/engineer_review.txt` | ❌ Missing | Prompt is **built inline** in `_build_review_prompt()` |
| `engineer_review.txt` must include try-first instruction [ENG-1A] | ❌ Missing | No external prompt file |
| Prompt injection mitigation in system prompt [CEO Amendment] | ❌ Missing | No system-level constraint on AI output schema |

**Impact:** The plan specifically requires the AI to be instructed to "attempt resolution before escalating" and to constrain output to JSON-only. These guards don't exist as written. An adversarially crafted design state could embed instructions into the AI prompt.

---

### 1.4 Base Step (`steps/base.py`)

| Plan Requires | In Code | Gap |
|---|---|---|
| `BaseStep` with `execute()`, `_should_call_ai()`, `run_with_review_loop()` | ✅ Present | — |
| `in_convergence_loop` guard (Decision 3A) | ✅ Present | — |
| `AIModeEnum` (FULL / CONDITIONAL / NONE) | ✅ Present | — |
| Correction loop: `apply_correction(state, ...)` → `self.execute(state)` → Layer 2 check | ❌ Bug | Corrections applied to `result.outputs`, not to `state` before re-execution |
| `confidence < 0.5` → force ESCALATE [ENG-1B] | ✅ Present | — |
| `snapshot_fields()` before correction, `restore()` on hard fail | ❌ Missing | Depends on DesignState methods that don't exist |
| Append `review.observation` to `state.review_notes` | ❌ Missing | `review_notes` field doesn't exist on DesignState |
| `apply_user_response()` as standalone function | ❌ Missing | Not implemented |

**The correction loop bug (critical):** The plan §7.5 explicitly states:
```
apply_correction(state, review.correction)  # mutate state first
result = self.execute(state)                # then re-run with corrected state
```
The current code applies corrections to `result.outputs` but passes the **original unchanged state** to `self.execute(state)`. The step re-reads stale values and the correction has no effect.

---

### 1.5 Validation Rules (`core/validation_rules.py`)

| Plan Requires | Status |
|---|---|
| Framework with `register_rule()` + `check(step, result)` | ✅ Present |
| Rules populated from step-specific rule files | ✅ Present |
| Consistent auto-registration at module level | ❌ Inconsistent |

**Rule Registration Inconsistency:**

| File | Auto-registers at import? |
|---|---|
| `step_01_rules.py` | ❌ No — `register_step1_rules()` defined but never called |
| `step_03_rules.py` | ❌ No — same pattern |
| `step_04_rules.py` | ❌ No — same pattern |
| `step_05_rules.py` | ✅ Yes — calls `register_step5_rules()` at module level |

**Impact:** If `step_01_rules.py`, `step_03_rules.py`, or `step_04_rules.py` aren't explicitly imported and their register functions called, Steps 1/3/4 run with NO hard rules. This is a silent correctness failure — no error is raised, rules just don't fire.

---

### 1.6 API Endpoints

| Plan Requires | Status |
|---|---|
| `POST /api/v1/hx/design` → `{session_id, stream_url, token}` | ✅ Present |
| `GET /api/v1/hx/design/{id}/stream` (SSE) | ✅ Present |
| `GET /api/v1/hx/design/{id}/status` (poll fallback, CG2A) | ✅ Present |
| `POST /api/v1/hx/design/{id}/respond` (user ESCALATE response) | ✅ Present |
| JWT stream auth (1hr, HX_ENGINE_SECRET) [3R-6A] | ⚠️ Partial — stub only |

---

## 2. Week 2 — Steps 1–5

### 2.1 Step Implementations

#### Step 1: Process Requirements

| Plan Requires | Status |
|---|---|
| `ai_mode=FULL` — always called | ✅ |
| Parse raw_request → FluidProperties stubs (JSON + NL fallback) | ✅ |
| NL regex for temps, flows, pressures, TEMA preferences | ✅ |
| Detect ambiguous fluid names ("oil", "gas") → ESCALATE | ✅ |
| Heuristic temp assignment (hot/cold side) | ✅ |
| Handle unit variations (°F, lb/hr, psi) | ✅ |
| Corner case: 4 temps that don't balance → flag error | Needs verification |
| Corner case: "same as last time" → Supermemory (Week 7) | Correctly deferred |
| Layer 2 hard rules from `step_01_rules.py` | ⚠️ Only if auto-import is wired |

**Status: Fully implemented — best-executed step in the codebase.**

---

#### Step 2: Heat Duty

| Plan Requires | Status |
|---|---|
| `ai_mode=CONDITIONAL` — AI if Q balance error > 2% | ✅ Trigger logic present |
| `execute()` → Q = m_dot × Cp × ΔT | ❌ **CRITICAL: execute() raises NotImplementedError** |
| Calculate missing 4th temperature from energy balance | ⚠️ Method exists, not wired |
| Layer 2: Q > 0, energy balance \|Q_hot − Q_cold\|/Q_hot < 1%, T_cold_out > T_cold_in | ⚠️ Rules may not register |
| Corner case: Q = 0 → reject with clear message | ⚠️ Logic exists, unreachable |
| Corner case: very small ΔT (< 5°C) → warn early | Not verified |

**Status: BLOCKED. The pipeline cannot progress past Step 1. All calculation pieces exist — only the `execute()` assembly is missing. This is the #1 fix needed before anything else.**

---

#### Step 3: Fluid Properties

| Plan Requires | Status |
|---|---|
| `ai_mode=CONDITIONAL` — AI if Pr outside [0.5, 1000] | ✅ |
| ThermoAdapter: iapws → CoolProp → thermo priority chain | ✅ |
| Compute ρ, μ, k, Cp, Pr at bulk mean temperature | ✅ |
| Layer 2: all properties > 0, density 500–1500 kg/m³ | ⚠️ Rules don't auto-register |
| Prandtl consistency check (μ × Cp / k within 5%) | ✅ |
| Graceful handling of unknown fluid → suggest similar | Needs verification |
| Corner case: crude oil without API gravity → assume API 29, flag | ✅ (petroleum_correlations.py) |
| Wall correction flag for high viscosity ratio | Not found |

**Status: Substantially implemented. Rule auto-registration gap applies here.**

---

#### Step 4: TEMA Type + Initial Geometry

| Plan Requires | Status |
|---|---|
| `ai_mode=FULL` — always called | ✅ |
| Decision tree for TEMA type based on conditions | ✅ |
| Fluid allocation heuristics (fouling → tube-side, high-P → tube-side) | ✅ |
| Heuristic selection of tube OD, pitch, layout angle, passes, length, baffle cut | ✅ |
| TEMA table lookup for shell diameter | ✅ |
| AI escalates when two TEMA types equally valid | ✅ |
| Corner case: ΔT > 50°C → floating head (AES not BEM) | ✅ |
| Corner case: both fluids foul → square pitch, escalate | ✅ |
| Corner case: very small duty (< 50 kW) → consider hairpin | ✅ |
| Supermemory context (books + past) — Week 7 | Correctly deferred |
| Layer 2 hard rules | ⚠️ Rules don't auto-register |

**Status: Well-implemented. Rule auto-registration gap applies.**

---

#### Step 5: LMTD + F-Factor

| Plan Requires | Status |
|---|---|
| `ai_mode=CONDITIONAL` — AI if F < 0.85 | ✅ |
| LMTD from 4 temperatures (Bowman 1940 analytical) | ✅ |
| F-factor from analytical R, P expressions | ✅ |
| Layer 2: F ≥ 0.75 (hard rule, AI cannot override) | ✅ Auto-registers |
| Auto-increment shell passes 1→2 if F < 0.80 | ✅ |
| Corner case: temperature cross detection | ✅ |
| Corner case: ΔT1 = ΔT2 exactly → arithmetic mean (avoid 0/0) | ✅ |
| Corner case: R = 1.0 exactly → L'Hôpital's rule | ✅ |
| Corner case: F < 0.75 with 2 shells → hard fail | ✅ |

**Status: Best-tested step. Fully compliant with plan.**

---

### 2.2 Adapters and Correlations

| Plan Requires | Status |
|---|---|
| `thermo_adapter.py` — iapws → CoolProp → thermo priority | ✅ |
| `units_adapter.py` — °F, lb/hr, psi → SI | ✅ |
| `correlations/lmtd.py` — pure functions, no side effects | ✅ |
| `petroleum_correlations.py` | ✅ **Bonus** — not in plan, useful for crude oil |

---

### 2.3 Data Tables

| Plan Requires | Status |
|---|---|
| `tema_tables.py` — shell diameters, tube counts | ✅ |
| `bwg_gauge.py` — BWG tube dimensions | ✅ |
| `u_assumptions.py` — typical U ranges by fluid pair | ✅ |
| `fouling_factors.py` — TEMA fouling resistances | ✅ |

---

## 3. Tests: Plan vs. Reality

### 3.1 Week 1 Tests

| Planned Test | Status | Notes |
|---|---|---|
| `test_design_state.py` — 12 CG3A validator tests | ✅ 24 tests | Exceeds requirement |
| `test_step_protocol.py` — Protocol compliance | ✅ Present (`test_base_step.py`) | |

### 3.2 Week 2 Tests

| Planned Test | Status | Notes |
|---|---|---|
| `test_lmtd.py` — 6 cases incl. temp cross + ΔT1=ΔT2 | ✅ 17 tests | Exceeds plan |
| `test_step_02.py` — execute() + validation + trigger | ⚠️ Present | Tests individual pieces; full execute() not testable (not implemented) |
| `test_step_03*.py` — execute() + validation + trigger | ✅ 7 test files | Very thorough |
| `test_step_04*.py` — allocation, TEMA, geometry, escalation | ✅ 7 test files | Thorough |
| `test_step_05*.py` — execute() + rules + integration | ✅ 4 test files | Thorough |
| `test_thermo_adapter.py` — Water at 25°C vs NIST | ✅ Present | |
| `tests/integration/test_pipeline_steps_1_5.py` — Steps 1–5 with mock AI (PROCEED) | ❌ **Missing** | No integration test folder exists |

**The missing integration test is significant.** The plan requires a test that runs all five steps sequentially with a mock AI that always returns PROCEED. Without this, there is no automated verification that Steps 1→2→3→4→5 actually chain together correctly. The `test_step_05_integration.py` file contains some pipeline state tests (Steps 1–5 fixture), but this is not the same as the plan's required `test_pipeline_steps_1_5.py` which must run the full pipeline with a stubbed AI reviewer.

---

## 4. Items in Code Not in the Plan (Weeks 1–2)

| File | What It Is | Assessment |
|---|---|---|
| `core/fouling_ai.py` | AI-assisted fouling factor refinement | Not in Week 1–2 scope. May pre-empt Week 3+ work |
| `core/fouling_store.py` | Stores fouling AI results | Not in plan at all |
| `adapters/petroleum_correlations.py` | Crude oil property correlations (API gravity) | Good addition, not in plan |

**Risk with fouling_ai.py:** It exists but there is no evidence it is called from any step. This makes it dead code unless wired in. It also introduces a second AI call path outside the plan's controlled `ai_engineer.py` — which could break the "single `.create()` call" contract.

---

## 5. Prioritized Fix List (Steps 1–5 Only)

| # | Fix | Why | Severity |
|---|---|---|---|
| 1 | Wire `Step02.execute()` | Pipeline is blocked; no calculation can proceed past Step 1 | CRITICAL |
| 2 | Fix correction loop state update in `base.py` | AI corrections have zero effect; re-execution uses stale state | CRITICAL |
| 3 | Add `review_notes` to DesignState | AI loses cross-step context; every step reviewed in isolation | HIGH |
| 4 | Add `snapshot_fields()` + `restore()` to DesignState | Correction rollback impossible; state left partially mutated on failure | HIGH |
| 5 | Standardize rule auto-registration | Steps 1, 3, 4 run with NO Layer 2 hard rules unless manually called | HIGH |
| 6 | Add `prompts/engineer_review.txt` with try-first + JSON-only constraints | AI has no injection mitigation; may not try to resolve before escalating | HIGH |
| 7 | Create `tests/integration/test_pipeline_steps_1_5.py` | No automated proof that Steps 1–5 chain together | HIGH |
| 8 | Add `confidence_breakdown` to DesignState | CEO-CP2 explainability contract missing; Step 16 will fail when built | MEDIUM |
| 9 | Type `step_records` as `List[StepRecord]` | Type safety; `dict` allows silent schema drift | MEDIUM |
| 10 | Add `apply_correction()` + `apply_user_response()` as standalone functions | Plan §7.5 specifies these as stable contracts for all 16 steps | MEDIUM |
| 11 | Verify/wire `fouling_ai.py` or remove | Dead code adds confusion and risk | LOW |
| 12 | Verify `PIPELINE_ORPHAN_THRESHOLD_SECONDS` in `config.py` | Orphan detection may not have correct threshold | LOW |

---

## 6. What the Plan Deferred That Code Should NOT Pre-empt

The following are correctly NOT in the code for Weeks 1–2 (do not build these yet):

- Supermemory integration (Week 7)
- `bell_delaware.py` correlation (Week 3)
- `gnielinski.py` tube-side h (Week 3)
- Convergence loop / Step 12 (Week 4)
- Vibration, mechanical, cost, final validation (Steps 13–16, Week 5)
- HTRI comparison workflow (Week 5)
- Backend / frontend integration (Week 6)
- JWT auth beyond stub (Week 6)

---

## 7. Overall Assessment

The foundational architecture is faithful to the plan — the 4-layer model, BaseStep pattern, SSE streaming, Redis persistence, and AI stub mode are all present. The engineering intent is intact.

The gaps cluster in three areas:

1. **Wiring gaps** — Step 2 execute() and the correction loop state update are assembly failures, not design failures. The pieces exist but aren't connected.

2. **DesignState contract gaps** — Three plan-required fields (`review_notes`, `confidence_breakdown`, and typed `step_records`) are missing. These become load-bearing when Steps 8–16 are built. Adding them is easy now; retrofitting them later is painful.

3. **Safety contract gaps** — The rule auto-registration inconsistency and missing prompt injection mitigation are silent failures — no test will catch them because they don't throw errors, they just quietly don't fire.

Fix items 1–7 from the priority list above before starting Week 3 (Bell-Delaware). Everything from Week 3 onward depends on a working Steps 1–5 pipeline with correct state flow.
