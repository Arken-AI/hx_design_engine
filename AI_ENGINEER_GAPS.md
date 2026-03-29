# AI Engineer — Gaps Between Implementation and Master Plan

**Created:** 2026-03-27 | **Status:** To be addressed after core AI logic is finalized

---

## A. No Retry with Backoff (Plan §5.2)

**Plan says:** 3 attempts with exponential backoff (1s, 2s) on API errors. If all fail → WARN + proceed with `ai_called=False`.  
**Current code:** Single try/except in `_call_claude()` — returns WARN on any failure, no retries.

## B. No Supermemory Context in Prompts (Plan §5.5)

**Plan says:** Each AI review gets 4 sections: calculation result, book context (Supermemory), past design data (Supermemory), full design state.  
**Current code:** `_build_review_prompt()` includes design context, step outputs, warnings, escalation hints, fouling metadata. No Supermemory integration yet (expected — later build phase).

## C. No `review_notes` Forwarding (Plan §5.4)

**Plan says:** Forward-looking observations from earlier steps get passed to later steps (e.g., Step 3's viscosity concern → Step 9). Each note is 30–50 tokens; 300–800 tokens total by Step 16.  
**Current code:** AI returns `observation` field, but nothing collects or forwards these across steps. Critical for Steps 5+ where cross-step reasoning matters.

## D. Missing Prompt Injection Mitigation (Plan CEO Amendment)

**Plan says:** System-level instruction to reject embedded instructions in design state or book context.  
**Current code:** System prompt doesn't include this safeguard. Attack surface: malicious fluid names or injected context.

## E. Missing "Try-First" Instruction (Decision ENG-1A)

**Plan says:** Prompt must instruct AI to attempt resolution before escalating — "apply the conservative standard, select the safer geometry, or use the TEMA default."  
**Current code:** Escalate description just says "cannot resolve automatically — needs human judgment." Doesn't push AI to try first.

## F. No `apply_correction` / `apply_user_response` Helpers (Plan §5.7)

**Plan says:** Proper `apply_correction(state, correction)` with `snapshot_fields()` and `restore()` for rollback on hard fail.  
**Current code:** Correction loop directly writes `result.outputs[c.field] = c.new_value` then re-runs `execute()`. No snapshot/rollback. Also: `execute()` reads from `state`, not `result.outputs` — corrections may not propagate correctly.

## G. Confidence Gate Edge Case (Decision ENG-1B)

**Plan says:** If `confidence < 0.5`, override to ESCALATE regardless of AI's stated decision.  
**Current code:** `MIN_AI_CONFIDENCE = 0.5` check in `run_with_review_loop()` does this, but only on first pass. Need to verify it also applies after correction re-reviews.

---

## Priority Order (suggested)

1. **F** — Correction propagation bug (functional correctness)
2. **A** — Retry with backoff (reliability)
3. **E** — Try-first instruction (reduces unnecessary escalations)
4. **C** — Review notes forwarding (cross-step reasoning)
5. **D** — Prompt injection mitigation (security)
6. **B** — Supermemory context (deferred with Supermemory)
7. **G** — Confidence gate verification (likely already correct)

---

## Finalized Decisions (2026-03-27)

| Question                         | Decision                                                                                                                      | Rationale                                                                                                                |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Correction propagation           | Write corrections to `DesignState`, not `result.outputs`. Snapshot before, restore on hard fail.                              | `execute()` reads from state — corrections to result.outputs are silently ignored.                                       |
| Escalation pause/resume          | **Option A: In-memory async** (`asyncio.Event` wait). 300s timeout.                                                           | Beta has single container, user is watching in real-time (10-60s response). Migration to Redis Option B later if needed. |
| AI cost tracking                 | Track per-call `{step_id, model, input_tokens, output_tokens, latency_ms, decision}` in StepRecord. Sum at design completion. | Plan estimates 9-11 Claude calls/design (~$0.03-0.11). Need visibility.                                                  |
| Stub mode                        | Keep as degradation fallback — API outage = proceed on hard rules only, `ai_called=False`.                                    | Pipeline must never block on AI unavailability.                                                                          |
| Persist state at step boundaries | Save `DesignState` to Redis after each step (observability, not resume).                                                      | Debugging aid + head start on Option B serialization.                                                                    |
