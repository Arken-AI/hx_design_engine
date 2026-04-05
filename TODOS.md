# TODOS

Deferred work captured during plan reviews. Pick up with full context below.

---

## P2 — Fix `_parse_review()` regex fallback for nested JSON

**What:** Replace the `\{[^{}]*\}` regex in `_parse_review()` (ai_engineer.py lines 266–278)
with a parser that handles nested JSON (arrays, nested objects).

**Why:** The `options` field added in the prompt-split PR is a JSON array. If Claude returns
malformed JSON and the regex fallback runs, the `options` field is silently dropped —
the user sees an escalation with no options to choose from. The direct `json.loads()` path
handles 99% of cases, but the fallback is a silent data-loss path.

**How to apply:** Use `json.JSONDecoder().raw_decode()` to extract the first valid JSON object
from the response, or use a balanced-braces counter rather than a character class regex.

**Pros:** Escalation context (recommendation + options) is never silently lost.

**Cons:** Slightly more complex parsing code. Edge case (malformed Claude response) is rare.

**Depends on:** Prompt-split PR (adds recommendation + options fields to AIReview).

**Priority:** P2 — not blocking, but escalation UX is broken until this is fixed.

---

## P2 — Per-step AI accuracy metrics

**What:** After each AI review, emit a structured log line (or increment a counter) with
`step_id`, `decision` (proceed/warn/correct/escalate), and `confidence`.

**Why:** Without per-step metrics, there's no way to prove the prompt split improved accuracy.
After shipping the step-specific prompts, you want to compare Step 4 escalation rate before
vs after. Also critical for the Week 5 HTRI accuracy gate — if the AI is over-correcting
on Step 5, you'll only know from production behavior, not from unit tests.

**How to apply:** In `BaseStep._record()` (base.py:167), the `StepRecord` is already appended
to `state.step_records` with `ai_decision` and `ai_confidence`. The metrics just need to be
surfaced — either emit a `logger.info()` structured log line or write to a lightweight
in-memory counter that the pipeline summary picks up.

**Pros:** Proves the prompt split worked. Enables ongoing prompt tuning with data.
Catches prompt regressions when new step prompts ship.

**Cons:** Adds a log line per AI call (minimal overhead). Full metrics dashboard is a
bigger project (Grafana/Prometheus) — but structured logging is the minimum useful version.

**Depends on:** Prompt-split PR ships first so step_id → prompt mapping is established.

**Priority:** P2 — ship after Week 5 accuracy gate validates the basic split.

---

## P1 — External Bell-Delaware validation reference (BD-REF-002)

**What:** Find a published Bell-Delaware worked example with intermediate J-factor values
(e.g., Thulukkanam "Heat Exchanger Design Handbook", Kakaç & Liu, Coulson & Richardson
Vol 6 BD examples, or an HTRI/HTFS benchmark). Add as `tests/fixtures/bd_ref_002.json`
alongside the self-computed BD-REF-001.

**Why:** BD-REF-001 validates self-consistency (does our code match our reference calculator?),
not correctness (do our formulas match the published method?). If the Taborek formula
interpretation is systematically wrong, both the reference calculator and implementation
will agree — and both will be wrong. One external reference with published intermediate
J-factor values proves the implementation is correct, not just self-consistent.

**How to apply:** Literature search for a Bell-Delaware worked example that publishes:
geometry inputs, all 5 J-factors, h_ideal, and h_o. Add as a second gate test in
`test_bell_delaware_vs_ref.py`. Use looser tolerances (±5%) since different BD
versions (Taborek 1983 vs. 1998) may differ slightly.

**Pros:** Transforms validation from "self-consistent" to "independently verified."
Catches systematic errors in formula interpretation.

**Cons:** Requires ~1hr literature search. Published examples may use slightly different
correlation versions (different year, different coefficient source).

**Depends on:** Nothing. Can be done in parallel with Phase 0-3.

**Priority:** P1 — should be done before or during Phase 3 implementation. Highest-value
validation item identified by independent review.
