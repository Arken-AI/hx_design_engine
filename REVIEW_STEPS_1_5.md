# ARKEN HX Engine — Steps 1–5 Review
**Against:** `ARKEN_STEPS_1_5_PLAN.md`
**Date:** 2026-03-25
**Test status:** 348 passed / 82 failed (81% pass rate)

---

## EXECUTIVE SUMMARY

DEV A (HX Engine Core) is ~90% complete and well-implemented.
DEV B (Infrastructure & API) is 0% complete — nothing built.
DEV C (Frontend + Backend Integration) is 0% complete — nothing built.
The engine cannot start or serve requests without DEV B's files.

---

## ✅ WHAT IS GOOD

### All core calculation files implemented (Dev A)

| File | Plan | Status |
|------|------|--------|
| `models/design_state.py` | Day 1 | ✅ Done |
| `models/step_result.py` | Day 1 | ✅ Done |
| `models/sse_events.py` | Day 1 | ✅ Done |
| `steps/__init__.py` | Day 1 | ✅ Done |
| `steps/base.py` | Day 2 | ✅ Done (with `run_with_review_loop`) |
| `core/ai_engineer.py` | Day 2 | ✅ Done + **AHEAD** (real Anthropic API, not stub) |
| `core/validation_rules.py` | Day 2 | ✅ Done |
| `core/exceptions.py` | Day 2 | ✅ Done |
| `adapters/thermo_adapter.py` | Day 4 | ✅ Done |
| `adapters/units_adapter.py` | Day 4 | ✅ Done |
| `correlations/lmtd.py` | Day 5 | ✅ Done |
| `data/tema_tables.py` | Day 5 | ✅ Done |
| `data/fouling_factors.py` | Day 5 | ✅ Done |
| `data/u_assumptions.py` | Day 5 | ✅ Done |
| `steps/step_01_requirements.py` | Day 6 | ✅ Done |
| `steps/step_02_heat_duty.py` | Day 7 | ✅ Done |
| `steps/step_03_fluid_props.py` | Day 8 | ✅ Done |
| `steps/step_04_tema_geometry.py` | Day 9 | ✅ Done |
| `steps/step_05_lmtd.py` | Day 10 | ✅ Done |
| `tests/conftest.py` | Day 5 | ✅ Done |
| `pyproject.toml` | Day 1 | ✅ Done |
| `.gitignore` | Day 1 | ✅ Done |

### Extra files added (beyond plan — good additions)

| File | What it does |
|------|-------------|
| `data/bwg_gauge.py` | BWG tube gauge lookup — correctly used in step 04 geometry |
| `adapters/petroleum_correlations.py` | Petroleum fluid correlations |
| `core/fouling_ai.py` | **Claude-powered fouling factor lookup** for unknown fluids — impressive |
| `core/fouling_store.py` | Caches AI fouling lookups to avoid repeat API calls |
| `steps/step_01_rules.py` | Validation rules for step 01 split to own file — clean pattern |
| `steps/step_03_rules.py` | Same for step 03 |
| `steps/step_04_rules.py` | Same for step 04 |
| `steps/step_05_rules.py` | Same for step 05 |

### Test coverage is extensive

The test suite has far more tests than the plan required:

| Step | Plan test files | Actual test files |
|------|----------------|-------------------|
| Step 01 | `test_step_01.py` | `test_step_01_nl.py`, `test_step_01_structured.py`, `test_step_01_validation.py`, `test_step_01_integration.py` |
| Step 02 | `test_step_02.py` | `test_step_02_compute_q.py`, `test_step_02_missing_temp.py` |
| Step 03 | `test_step_03.py` | `test_step_03_ai_trigger.py`, `test_step_03_execute.py`, `test_step_03_integration.py`, `test_step_03_mean_temp.py`, `test_step_03_resolve_fluid.py`, `test_step_03_validation.py`, `test_step_03_warnings.py` |
| Step 04 | `test_step_04.py` | `test_step_04_allocation.py`, `test_step_04_escalation.py`, `test_step_04_execute.py`, `test_step_04_geometry.py`, `test_step_04_model_updates.py`, `test_step_04_rules.py`, `test_step_04_tema_selection.py` |
| Step 05 | `test_step_05.py` | `test_step_05_execute.py`, `test_step_05_integration.py`, `test_step_05_model.py`, `test_step_05_rules.py` |

### LMTD corner cases handled correctly

The implementation correctly handles all plan-specified corner cases:
- ΔT1 == ΔT2 → arithmetic mean (avoids 0/0)
- Temperature cross detection
- F < 0.85 → conditional AI trigger
- F < 0.75 → hard fail (Layer 2)

---

## ❌ WHAT IS BAD (Bugs in existing code)

### BUG 1 — CRITICAL: All `execute()` methods are async, tests call them synchronously

**Root cause:** Every step's `execute()` is `async def`, but every test calls it as `result = step.execute(state)` without `await`. The test gets back a coroutine object, not a `StepResult`. This causes 73 of the 82 failures.

**Affected files:**
- `steps/step_01_requirements.py:126` — `async def execute`
- `steps/step_02_heat_duty.py:51` — `async def execute`
- `steps/step_03_fluid_props.py` — `async def execute`
- `steps/step_04_tema_geometry.py` — `async def execute`
- `steps/step_05_lmtd.py` — `async def execute`
- `steps/base.py:76` — `async def run_with_review_loop`

**The plan specifies:** `def execute(self, state: DesignState) -> StepResult` (sync). The base class abstract method in the plan is also sync. Making `execute()` async is a valid architectural choice for a FastAPI app, but the **tests must all be updated to use `await` and `@pytest.mark.asyncio`**.

**Impact:** 73 tests fail (steps 01, 02, 03, 04, and base_step tests).

---

### BUG 2 — CRITICAL: `iapws` library not installed

**Error:** `CalculationError: iapws library not installed — cannot compute water properties`

**Impact:** 6 thermo_adapter tests fail. More critically, Step 03 will fail at runtime for any water-based design (the most common case in HX design).

**Fix:** `pip install iapws` and add it to `pyproject.toml` dependencies (it's listed in the plan's pyproject.toml but may not be installed in the current environment).

---

### BUG 3 — MEDIUM: `FluidProperties` missing `name`, `phase`, `mean_temp_C` fields

**Plan specifies:**
```python
class FluidProperties(BaseModel):
    name: str
    density_kg_m3: float
    viscosity_Pa_s: float
    cp_J_kgK: float
    k_W_mK: float
    Pr: float
    phase: str = "liquid"
    mean_temp_C: Optional[float] = None
```

**Implementation has:** Only `density_kg_m3`, `viscosity_Pa_s`, `cp_J_kgK`, `k_W_mK`, `Pr`. Missing `name`, `phase`, `mean_temp_C`.

**Impact:** Downstream steps (06–16) that need phase to select correlations (gas vs liquid) will need these fields. The conftest.py fixture in the plan also sets `name="water"` — that fixture will fail.

---

### BUG 4 — MEDIUM: Confidence threshold mismatch

**CLAUDE.md (global mandate):** `Confidence < 0.5 = escalate (even if AI says PROCEED)`

**Implementation:** `CONFIDENCE_THRESHOLD = 0.7` in `core/ai_engineer.py:35`

**Impact:** AI will auto-proceed on steps where confidence is 0.5–0.7, when it should escalate. This is a trust-calibration violation — the core principle of the ARKEN architecture.

---

### BUG 5 — LOW: Test directory structure differs from plan

**Plan specifies:**
```
tests/unit/models/test_design_state.py
tests/unit/steps/test_step_protocol.py
tests/unit/correlations/test_lmtd.py
tests/unit/adapters/test_thermo_adapter.py
```

**Actual:** All tests are flat in `tests/unit/` with no subdirectory organization. The tests exist (good), but the structure doesn't match the plan. Not a functional issue, but worth noting.

---

## ❌ WHAT IS MISSING (Never built)

### Dev B — Infrastructure & API (100% missing)

The engine cannot start. There is no main.py, no FastAPI app, no HTTP endpoints.

| File | Plan Day | Status |
|------|----------|--------|
| `app/main.py` | Day 2 | ❌ Missing |
| `app/config.py` | Day 2 | ❌ Missing |
| `app/dependencies.py` | Day 2 | ❌ Missing |
| `app/routers/__init__.py` | Day 3 | ❌ Missing |
| `app/routers/design.py` | Day 3 | ❌ Missing — POST /api/v1/hx/design |
| `app/routers/stream.py` | Day 3 | ❌ Missing — GET /api/v1/hx/design/{id}/stream |
| `app/core/session_store.py` | Day 2 | ❌ Missing — Redis session persistence |
| `app/core/sse_manager.py` | Day 2 | ❌ Missing — SSE event queues |
| `app/core/pipeline_runner.py` | Day 3 | ❌ Missing — Step orchestrator |
| `app/core/prompts/engineer_review.txt` | Day 2 | ❌ Missing |
| `Dockerfile` | Day 4 | ❌ Missing |
| `.env.example` | Day 4 | ❌ Missing |
| `docker-compose.yml` | Day 4 | ❌ Missing |
| `nginx.conf` | Day 4 | ❌ Missing |
| `tests/integration/test_pipeline_steps_1_5.py` | Day 10 | ❌ Missing |

### Dev C — Frontend + Backend Integration (100% missing)

| File | Plan Day | Status |
|------|----------|--------|
| `frontend/src/hooks/useHXStream.js` | Day 1 | ❌ Missing |
| `frontend/src/types/hxEvents.js` | Day 2 | ❌ Missing |
| `frontend/src/components/hx/*` | Days 6–10 | ❌ Missing |
| `frontend/src/utils/sseClient.js` | Day 3 | ❌ Missing |
| `backend/app/core/engine_client.py` | Day 1 | ❌ Missing |
| `backend/app/config.py` additions | Day 2 | ❌ Missing |
| `backend/app/dependencies.py` additions | Day 2 | ❌ Missing |
| `backend/engines.yaml` | Day 2 | ❌ Missing |

---

## DIFFERENCE TABLE: Plan vs Implementation

| Category | Plan | Implemented | Delta |
|----------|------|-------------|-------|
| Dev A core files | 22 files | 22 files + 8 extra | ✅ Ahead |
| Dev A step files | 5 steps | 5 steps (all async) | ⚠️ Async mismatch |
| Dev A tests | ~10 test files | ~35 test files | ✅ Far ahead |
| Dev A test passing | All must pass | 348/430 (81%) | ❌ 82 failing |
| `iapws` library | Required | Not installed | ❌ Missing dep |
| `FluidProperties.name/phase/mean_temp_C` | Required | Missing | ❌ Schema gap |
| Confidence threshold | 0.5 (CLAUDE.md) | 0.7 | ❌ Wrong value |
| AI engineer | Stub (weeks 1–2) | Real API call | ✅ Ahead of schedule |
| Dev B infrastructure | All 14 files | 0 files | ❌ Not started |
| Dev C frontend | All files | 0 files | ❌ Not started |
| Docker/nginx | Required | Not present | ❌ Not started |
| Integration tests | 1 file | 0 files | ❌ Not started |

---

## PRIORITY ACTION LIST

### P0 — Fix before any other work

1. **Fix async/await mismatch** — Add `@pytest.mark.asyncio` and `await` to every test that calls `execute()` or `run_with_review_loop()`. This unblocks 73 tests. (~1 hour with CC)

2. **Install iapws** — `pip install iapws` and verify it's in `pyproject.toml`. Unblocks 6 more tests. (~5 min)

3. **Fix confidence threshold** — Change `CONFIDENCE_THRESHOLD = 0.7` to `CONFIDENCE_THRESHOLD = 0.5` in `core/ai_engineer.py` per CLAUDE.md mandate.

### P1 — Required for running service

4. **Build Dev B infrastructure** — `main.py`, `config.py`, `dependencies.py`, `routers/`, `session_store.py`, `sse_manager.py`, `pipeline_runner.py`. The plan has full specs for all of these. (~2 hours with CC)

5. **Add `name`, `phase`, `mean_temp_C` to `FluidProperties`** — Needed for downstream steps 6–16 and for the plan's fixture compatibility.

### P2 — Week 5 gate blocker

6. **Build integration test** — `tests/integration/test_pipeline_steps_1_5.py` is the gate test for the Serth Example 5.1 HTRI comparison (±5% on U, ±10% on dP). Without this, the Week 5 accuracy gate cannot be verified.

### P3 — Deferred (Dev C, Week 6+)

7. **Frontend + backend integration** — Dev C work is all Week 5–6 per the original timeline. Not yet blocking.

---

## TEST FAILURE BREAKDOWN

| Root cause | Failures |
|-----------|----------|
| `execute()` called without `await` (step_01, step_02, step_03, step_04) | 58 |
| `run_with_review_loop()` called without `await` (base_step, ai_engineer) | 9 |
| `iapws` not installed (thermo_adapter) | 6 |
| `execute()` not awaited in step_04 escalation tests | 3 |
| `execute()` not awaited + step_03 thermo fallback | 6 |
| **Total** | **82** |

---

*Generated by `/review` against `ARKEN_STEPS_1_5_PLAN.md` on 2026-03-25*
