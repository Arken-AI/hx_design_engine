# Step 4 Extension: AI-Powered Fouling Factor Lookup

> **Context:** This is NOT part of the original `devAstep4.md` plan. It was designed
> and added as an enhancement after the base Step 4 implementation was complete
> (all 10 pieces, 116 tests passing). This document covers everything added beyond
> the original plan.

---

## Problem Statement

The original fouling factor lookup (`fouling_factors.py`) has two limitations:

1. **Location-dependent fluids** — River water, seawater, cooling tower water, etc.
   have R_f values that vary significantly by geographic location, water quality,
   and season. A single hardcoded TEMA mid-range value is often wrong.

2. **Unknown fluids** — If a user enters a fluid not in the table (e.g.
   "phosphoric acid solution", "molten polymer resin"), the engine silently
   uses a conservative default (R_f = 0.000352) with no indication that the
   value is a guess.

## Solution: 3-Tier Fouling Factor Resolution

```
Tier 1: Hardcoded TEMA Tables     → fast, free, authoritative
    ↓ (not found, or location-dependent)
Tier 2: MongoDB Cache              → fast, free, learned from past lookups
    ↓ (not found, or expired)
Tier 3: Claude Sonnet 4.6 API     → slow, costs $, but handles anything
    ↓
   confidence ≥ 0.7 → auto-accept, save to MongoDB
   confidence < 0.7 → ESCALATE to user with options:
                       [A] Accept AI value  |  [M] Enter manually
```

---

## Architecture Decisions

| Decision             | Choice                                                                 | Rationale                                                                                             |
| -------------------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| LLM                  | Claude Sonnet 4.6                                                      | Already tested in backend, good at structured JSON output                                             |
| AI call location     | Inside `AIEngineer.review()` (Option A)                                | Matches the ARKEN master plan review loop; fouling uncertainty is just one of many things AI reviews  |
| API key source       | `hx_design_engine/.env` via `python-dotenv`                            | Simple, standard, gitignored                                                                          |
| Database             | Same MongoDB (`arken_process_db`), new collection `ai_fouling_factors` | Shared infra, no new services                                                                         |
| Sync/Async           | Full async migration                                                   | Matches master plan; `execute()`, `run_with_review_loop()`, `AIEngineer.review()` are all `async` now |
| Confidence threshold | ≥ 0.7 auto-proceed, < 0.7 escalate to user                             | Balances safety vs. friction                                                                          |
| Cache TTL            | 90 days for AI values; user overrides never expire                     | Location conditions change seasonally                                                                 |
| Escalation           | StepResult with `decision=ESCALATE`                                    | Engine doesn't block; backend/frontend handles the UX prompt                                          |
| Graceful degradation | MongoDB down → skip cache; API key missing → stub mode (auto-approve)  | Engine never hard-fails due to external service issues                                                |

---

## Files Created

### `hx_engine/app/core/fouling_ai.py`

Claude-powered fouling factor lookup.

- **`get_fouling_from_ai(fluid_name, temperature_C, additional_context)`** → `dict`
  - Calls Claude with a structured prompt asking for R_f in m²·K/W
  - System prompt instructs Claude to respond ONLY with JSON:
    ```json
    {
      "rf_value": 0.00044,
      "confidence": 0.85,
      "reasoning": "Based on TEMA Table RGP-T-2.4...",
      "classification": "moderate"
    }
    ```
  - Response parser handles: direct JSON, markdown code blocks, embedded JSON
  - Validates R_f range (0 < R_f ≤ 0.01 m²·K/W), clamps if out of range
  - On API failure → returns fallback `{rf: 0.000352, confidence: 0.0, error: "..."}`
  - Uses `temperature=0.0` (deterministic) for engineering values

### `hx_engine/app/core/fouling_store.py`

MongoDB persistence for AI-provided fouling factors.

- **Collection:** `ai_fouling_factors` in `arken_process_db`
- **`get_db()`** — lazy singleton connection, creates index on first connect
- **`close_db()`** — clean shutdown
- **`find_cached_fouling(fluid_name, temperature_C)`** → `dict | None`
  - Normalized name matching
  - Temperature range match: ±10°C
  - Expiry: AI values expire after 90 days; user overrides never expire
- **`save_fouling_factor(...)`** — insert document after AI or user provides value

**Document schema:**

```json
{
  "_id": "ObjectId",
  "fluid_name": "phosphoric acid solution",
  "temperature_C": 80.0,
  "rf_value": 0.00044,
  "confidence": 0.85,
  "reasoning": "Based on TEMA RGP-T-2.4...",
  "source": "claude-sonnet-4-20250514",
  "accepted_by": "ai | user",
  "user_override": null,
  "created_at": "2026-03-22T..."
}
```

### `hx_engine/app/core/ai_engineer.py` (rewritten)

Replaced the stub with a real Claude-powered reviewer.

- **Stub mode** — activates when `ANTHROPIC_API_KEY` is not set. Returns auto-approve
  so tests and local dev work without an API key.
- **Real mode** — builds a detailed review prompt including:
  - Design context (fluids, temperatures, pressures, duty)
  - Step outputs (JSON serialized)
  - Warnings from the step
  - Escalation hints (from deterministic logic)
  - **Fouling metadata** (source, needs_ai flag, reason) ← this is the key link
- **Response parser** — handles direct JSON, code blocks, embedded JSON
- **Decision mapping** — maps Claude's string decisions to `AIDecisionEnum` enum
- **Error handling** — on API failure, returns `WARN` (don't block the pipeline)

---

## Files Modified

### `hx_engine/app/data/fouling_factors.py`

Added alongside the original TEMA table lookup:

- **`_LOCATION_DEPENDENT`** set — fluids whose R_f varies by location/conditions:
  `river water`, `seawater`, `cooling tower water`, `cooling water`, `city water`,
  `brine`, `crude oil`, `crude`

- **`get_fouling_factor_with_source(fluid_name, temperature_C)`** → `dict`
  - Returns `{rf, source, needs_ai, reason}`
  - `source`: `"exact"` | `"temp_dependent"` | `"partial_match"` | `"ai_recommended"`
  - `needs_ai = True` when fluid is **unknown** or **location-dependent**
  - `reason`: human-readable explanation for AI prompt and UI

- **`is_location_dependent(fluid_name)`** → `bool`
  - Only matches when a known location-dependent key appears _within_ the name
    (e.g. "dirty river water" matches "river water")
  - Does NOT match the reverse ("water" does NOT match "cooling water")

- **`"water"` added to `_FOULING_SIMPLE`** — prevents spurious partial-matching

### `hx_engine/app/steps/step_04_tema_geometry.py`

- **Imports added:** `get_fouling_factor_with_source`, `is_location_dependent`
- **`_build_escalation_hints()`** — now checks both fluids via
  `get_fouling_factor_with_source()`. If `needs_ai=True`, adds a
  `"fouling_factor_uncertain"` hint with the fluid name, current R_f, and
  a prompt asking AI to provide the correct value.
- **`execute()`** — collects `fouling_metadata` for both fluids and includes
  it in `StepResult.outputs["fouling_metadata"]`. The AI review loop sees this
  and knows exactly which values need refinement.

### `hx_engine/app/steps/base.py`

- **`StepProtocol.execute()`** — changed to `async def execute()`
- **`BaseStep.run_with_review_loop()`** — changed to `async def`, `await`s execute and review
- All step implementations updated to `async def execute()`

### `pyproject.toml`

New dependencies:

```toml
"anthropic>=0.40",
"motor>=3.3",
"pymongo>=4.6",
"python-dotenv>=1.0",
```

New pytest config:

```toml
asyncio_mode = "auto"
```

---

## How It Works End-to-End

### Scenario 1: Known stable fluid (e.g. gasoline → methanol)

```
fouling_factors.py → exact match, needs_ai=False
    → Step 4 uses table R_f
    → fouling_metadata shows source="exact", needs_ai=False
    → AI reviews step, sees no fouling uncertainty → "proceed"
```

### Scenario 2: Location-dependent fluid (e.g. river water)

```
fouling_factors.py → exact match, BUT needs_ai=True (location-dependent)
    → Step 4 uses table R_f as starting value
    → fouling_metadata shows needs_ai=True, reason="varies by location..."
    → escalation_hints includes "fouling_factor_uncertain"
    → AI reviews step, sees fouling hint → may "correct" with better R_f
       or "escalate" if uncertain
```

### Scenario 3: Unknown fluid (e.g. "phosphoric acid solution")

```
fouling_factors.py → no match, returns default R_f=0.000352
    → fouling_metadata shows source="ai_recommended", needs_ai=True
    → escalation_hints includes "fouling_factor_uncertain"
    → AI reviews → either:
       a) confidence ≥ 0.7: auto-corrects with CORRECT decision
       b) confidence < 0.7: ESCALATE to user
          → user sees: "AI suggests R_f=0.00044 (55% confidence).
             Accept or enter manually?"
```

### Scenario 4: Repeated lookup for same unknown fluid

```
fouling_factors.py → no match
    → fouling_store.py checks MongoDB → FOUND (cached from previous run)
       → uses cached R_f, skips AI API call entirely
```

---

## MongoDB Index

```python
await db.ai_fouling_factors.create_index(
    [("fluid_name", 1), ("temperature_C", 1)],
)
```

---

## Environment Configuration

File: `hx_design_engine/.env` (gitignored)

```env
ANTHROPIC_API_KEY=sk-ant-api03-...
MONGODB_URI=mongodb://arken_app:<password>@localhost:27017/arken_process_db?authSource=admin
MONGODB_DB_NAME=arken_process_db
```

---

## Test Coverage

### New tests in `tests/unit/test_fouling_factors.py`

| Test Class                    | Tests | What It Covers                                                                                                     |
| ----------------------------- | ----- | ------------------------------------------------------------------------------------------------------------------ |
| `TestFoulingFactorWithSource` | 13    | get_fouling_factor_with_source for exact, temp-dependent, unknown, location-dependent fluids; dict keys validation |
| `TestIsLocationDependent`     | 6     | river water, seawater, gasoline, steam, partial match, case insensitive                                            |

### New tests in `tests/unit/test_step_04_escalation.py`

| Test                                          | What It Covers                                                  |
| --------------------------------------------- | --------------------------------------------------------------- |
| `test_escalation_unknown_fluid`               | Unknown fluid → `fouling_factor_uncertain` hint with fluid name |
| `test_escalation_location_dependent_fluid`    | River water → `fouling_factor_uncertain` hint                   |
| `test_no_fouling_escalation_for_known_stable` | Gasoline + methanol → no fouling hint                           |
| `test_fouling_metadata_in_execute_output`     | execute() includes `fouling_metadata` in outputs                |
| `test_fouling_metadata_flags_unknown`         | Unknown fluid → `needs_ai=True`, `source="ai_recommended"`      |

### Total: 27 new tests added

---

## What's NOT Done Yet (In Progress)

The async migration is partially complete. These items are tracked in the
current todo list:

- [ ] Async migration for all 4 step files (step_01 through step_04)
- [ ] Wire the 3-tier lookup (table → MongoDB → AI) into `fouling_factors.py`
      public API so it's called automatically
- [ ] Update all 10+ test files for async (add `async def`, `await`)
- [ ] Integration test with live Claude API call
- [ ] Integration test with MongoDB
- [ ] Full regression test suite passing

---

## How to Test (Once Complete)

```bash
# Unit tests (no API key needed — uses stub mode)
cd hx_design_engine
python -m pytest tests/ -v

# Live AI test (requires ANTHROPIC_API_KEY in .env)
python -c "
import asyncio
from dotenv import load_dotenv
load_dotenv()
from hx_engine.app.core.fouling_ai import get_fouling_from_ai
result = asyncio.run(get_fouling_from_ai('phosphoric acid solution', 80))
print(result)
"

# MongoDB test (requires running MongoDB)
python -c "
import asyncio
from dotenv import load_dotenv
load_dotenv()
from hx_engine.app.core.fouling_store import find_cached_fouling, save_fouling_factor
asyncio.run(save_fouling_factor('test fluid', 50, 0.0003, 0.9, 'test', 'test'))
result = asyncio.run(find_cached_fouling('test fluid', 50))
print(result)
"
```
