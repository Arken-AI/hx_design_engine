# ARKEN AI — Master Plan (Single Source of Truth)

## Heat Exchanger Design Platform

**Version 8.0 | March 2026**

> Deterministic calculation + bounded AI judgment + hard rule safety net + user escalation.
> Every step reviewed. Every decision explained. Every correction visible.

**Consolidates:** DEVELOPMENT_PLAN.md (v6.0), End-to-End Build Plan, CEO Review, Engineering Reviews (3 passes), Test Plans (4 passes), Office Hours Design Doc, TODOS.md, Office Hours Session (2026-03-19, Trust-Calibration-First). All prior documents are superseded by this file.

---

## Table of Contents

1. [Vision & Problem Statement](#1-vision--problem-statement)
2. [System Architecture](#2-system-architecture)
3. [The Four Layers](#3-the-four-layers)
4. [The Three Loops](#4-the-three-loops)
5. [The AI Senior Engineer](#5-the-ai-senior-engineer)
6. [AI Review Protocol — All 16 Steps](#6-ai-review-protocol--all-16-steps)
7. [Key Contracts & Data Models](#7-key-contracts--data-models)
8. [Supermemory — Complete Integration](#8-supermemory--complete-integration)
9. [Real-Time Event Streaming](#9-real-time-event-streaming)
10. [HX Engine Microservice](#10-hx-engine-microservice)
11. [Backend Changes](#11-backend-changes)
12. [Autoresearch — Loop 3](#12-autoresearch--loop-3)
13. [Frontend Design Specification](#13-frontend-design-specification)
14. [Build Sequence (Week-by-Week)](#14-build-sequence-week-by-week)
15. [Test Plan](#15-test-plan)
16. [Benchmark Validation Points (Hard Gates)](#16-benchmark-validation-points-hard-gates)
17. [Drawback Mitigations](#17-drawback-mitigations)
18. [Corner Cases & Edge Conditions](#18-corner-cases--edge-conditions)
19. [Extensibility](#19-extensibility)
20. [Post-Development & Deferred Items](#20-post-development--deferred-items)
21. [Decision Log](#21-decision-log)
22. [Open Questions](#22-open-questions)
23. [Success Criteria](#23-success-criteria)

---

## 1. Vision & Problem Statement

### 1.1 What We Are Building

ARKEN AI is a conversational platform that designs industrial shell-and-tube heat exchangers. The user describes their problem in natural language ("Design a heat exchanger for cooling 50 kg/s of crude oil from 150°C to 90°C using cooling water at 30°C"). The system performs all engineering calculations, validates every result with AI engineering judgment, and returns a complete, fabrication-ready design with full transparency into the reasoning at every step.

### 1.2 This Is NOT a Chatbot

A chatbot retrieves and rephrases information. ARKEN is a **computational engineering platform with a conversational interface**. Behind the conversation sits a real calculation engine executing Bell-Delaware correlations, iterating on geometry, checking vibration safety, running ASME pressure vessel code, and estimating costs. The conversation is the front door (5% of value). The engineering engine is the product (80%). The optimization is the bonus (15%).

### 1.3 The Two Modes

- **Design Mode (Sizing):** User knows process conditions, system determines geometry. "What exchanger do I need?"
- **Rating Mode (Performance Check):** User knows process conditions AND geometry, system checks if it works. "Can this existing exchanger handle 20% more flow?"

### 1.4 What Goes In → What Comes Out

**Inputs (from user):**
- Fluid identities and compositions
- Flow rates (kg/s)
- Inlet/outlet temperatures (at least 3 of 4)
- (Optional) Pressures, material preferences, TEMA class, constraints

**Outputs (from system):**
- Complete geometry (shell, tubes, baffles)
- Thermal performance (U, Q, LMTD, overdesign)
- Pressure drops (tube-side and shell-side)
- Vibration safety assessment
- Mechanical design (wall thicknesses)
- Cost estimate
- Confidence score (0.0 to 1.0) with breakdown
- Step-by-step reasoning for every decision

### 1.5 10x Vision (12-month)

```
CURRENT STATE          THIS PLAN (8 weeks)         12-MONTH IDEAL
─────────────────      ────────────────────────    ──────────────────────────────
No product.            16-step Bell-Delaware       20 paying engineers.
No users.              pipeline + chat UI +        HTRI calibration data feeds
No validation.         Supermemory + autores.      accuracy improvement loops.
                       Auth + org_id ready.        API tier for integrators.
                       Confidence breakdown        Multi-HX session memory.
                       visible to engineers.       TEMA library of past designs.
```

### 1.6 Target User & Narrowest Wedge

**Target user (refined, Office Hours 2026-03-19):** Any process engineer at a mid-size EPC or refinery blocked by the HTRI license bottleneck — either a junior engineer without a seat, or a senior engineer (15+ designs/year) for whom HTRI setup takes 1–2 hours even with full access. Both archetypes feel this pain. The senior engineer is the one with purchasing authority.

**The structural constraint:** A team of 15 engineers typically has 1–2 concurrent HTRI seats and 1 specialist who can operate it confidently. Designs pile up. Schedules slip. This is not a niche complaint — the HTRI concurrent-license model structurally guarantees this bottleneck at every mid-size firm.

**Narrowest wedge that's worth paying for today:** A complete 16-step first-pass design tool with confidence score and step-by-step reasoning for every decision. Engineers need the full audit trail — the number alone is not enough. A stripped-down sizing tool without the reasoning layer will not be trusted by a trained engineer.

### 1.7 Status Quo

Engineers use one or more of:
- **HTRI Xchanger Suite** — industry gold standard, ~$30k/yr, limited concurrent seats, steep learning curve (weeks of training), effectively black-box results
- **Excel + Serth/Kern textbooks** — common at smaller firms, fully manual, error-prone, no audit trail
- **Outsourcing to specialist consultants** — expensive, slow

**The bottleneck in practice:** When a junior or mid-level engineer needs a heat exchanger design, they (1) write up the process conditions, (2) wait for the HTRI specialist's calendar to open up, (3) the specialist runs HTRI and returns the result, (4) the engineer reviews the output. The bottleneck is step 2. Even senior engineers with HTRI access spend 1–2 hours on setup for a single case. ARKEN removes this bottleneck by giving any engineer a trusted first-pass in minutes.

### 1.8 Constraints

- Pre-product; no external users yet
- Calculation accuracy must match or approach HTRI/textbook benchmarks (Serth Example 5.1 ±5% on U, ±10% on dP)
- AI must be bounded (deterministic calc + rule safety net precedes AI review) — engineers will not trust an AI that controls the math
- Phase 1: single-phase liquids only; two-phase deferred

### 1.9 Demand Evidence

_Not yet formally validated (pre-product)._ The strongest proxies are:
- **Industry insider signal:** Builder has direct domain experience observing this bottleneck in real EPC / refinery environments. Not a hypothetical.
- **Market structure signal:** The HTRI concurrent-license model (~$30k/yr) structurally guarantees this bottleneck at every mid-size firm. 1–2 seats for 15 engineers, 1 specialist. The constraint is not going away.
- **Plan iteration signal:** v8.0 of the master plan. Deep conviction, significant iteration over prior attempts. Not someone who just had the idea.

**Gap:** No direct user conversations yet. No one has been asked to pay.

**Assignment:** Before writing a single line of code, find one process engineer — someone from prior work, school, or industry contact — and ask them to walk through their last heat exchanger design. Listen. Don't pitch. Ask: "What took the longest?" "What would have made it faster?" "How did you check if the design was right?" If they say "I waited for the HTRI specialist" — get their email. They are the first beta user.

### 1.10 Premises

All confirmed:
1. Shell-and-tube heat exchangers are the right starting wedge (most common type in oil & gas / refining)
2. Process engineers will trust AI-assisted calculations for real designs, especially with full reasoning transparency
3. The conversational interface adds value over a traditional form (lower barrier to entry, better UX for experienced engineers)
4. B2B SaaS is the right initial model (vs. API-first for integrators)

**Additional premises confirmed in Office Hours session (2026-03-19):**

5. The HTRI license bottleneck is the primary pain — not HTRI's accuracy. Engineers trust HTRI's results; the problem is access and setup time.
6. Engineers will trust a first-pass tool if they can see every calculation step and the reasoning behind each decision. Transparency earns trust faster than claims of accuracy.
7. The full 16-step pipeline (confidence score + audit trail + AI review) is the minimum version worth paying for. A stripped-down sizing tool without the reasoning layer will not be trusted.
8. The right initial customer is a team (a firm), not an individual engineer paying out of pocket. The license bottleneck is an org-level problem that needs an org-level purchase.

### 1.11 Effort Estimate

**Estimated effort:** XL (human: ~6 months / CC: ~3 weeks). **Trust-Calibration-First** build sequence selected (Office Hours 2026-03-19) — see §1.12 and Decision Log §21 for rationale. This reorders the original 8-week plan without changing total scope: HTRI Comparison workflow moved from post-beta to Week 5, providing real accuracy validation mid-build.

### 1.12 Approaches Considered

**Original build-sequence approaches (v6.0 → v7.0):**

| Approach | Description | Rejected Because |
|----------|-------------|------------------|
| **A** | Full v6.0: 16-step pipeline + AI review + Supermemory + autoresearch, 8-week build, then find users | Demand validated at Week 8, not Week 1 |
| **B — Ship Fast** | Minimal 10-day build: Steps 1–5 + simple UI, no AI review, no optimization | Misses the 10× value prop; no confidence scoring, no audit trail, indistinguishable from a spreadsheet |
| **C — API-First** | REST API for integrators before building a UI | No demand signal yet; API without a reference UI is hard to sell; B2B SaaS premise (#4 in §1.10) favors end-user product first |

**Office Hours approaches (2026-03-19) — Trust-Calibration-First selected:**

| Approach | Description | Status |
|----------|-------------|--------|
| **A — Build-First** | Complete all 16 steps end-to-end, then bring in beta users. Product is polished when engineers first see it. | Not selected — 8 weeks without a user feedback loop |
| **B — Trust-Calibration-First (selected)** | Build Steps 1–8, then HTRI Comparison workflow (Week 5), then Steps 9–16. Beta users compare ARKEN to their HTRI results while the product is being completed. | **Selected** — accuracy and demand validated mid-build, not post-build |
| **C — Open Benchmark First** | Publish Serth Example 5.1 validation results publicly before recruiting users. Let the benchmark recruit beta users. | Not selected — distribution risk; doesn't demonstrate the conversational interface |

---

## 2. System Architecture

### 2.1 High-Level Architecture

**Current flow (being removed):** Frontend → Backend → MCP Client (SSE) → MCP Servers → Calculation Engine
**New flow:** Frontend → Backend → HX Engine (direct HTTP REST / SSE streaming via nginx)

Three services, each its own Docker container, fronted by nginx reverse proxy [Decision CEO-1A]:

```
                          nginx (:80)
                           │
            ┌──────────────┼──────────────┐
            │              │              │
Frontend (React/Vite)   Backend        HX Engine
  served as static      (FastAPI        (FastAPI
  assets via nginx       :8001)          :8100)

  1. POST /api/chat ──────────────────────────────►
     (user message)         │  Loop 1: Claude orchestration
                            │  Claude calls hx_design tool
                            │  POST /api/v1/hx/start ─────────────►
                            │           ◄── { session_id, stream_url }
  2. ◄── chat response ─────┘  tool_executions: [{ tool_name: "hx_design",
     (with tool_executions)         result: { session_id, stream_url } }]

  3. Frontend reads stream_url from tool_executions
     GET /api/v1/hx/design/{id}/stream ──────────────────────────►
     [EventSource via nginx proxy]   Loop 2: 16-step Bell-Delaware
     ◄── SSE events (step_started, step_approved, ..., design_complete)

                    ◄── POST /internal/design-complete
                    [HX Engine webhook on completion]
```

```
Infrastructure: MongoDB :27017, Redis :6379 (AOF persistence)
Reverse Proxy: nginx :80 (routes /api/v1/hx/ → HX Engine, everything else → Backend/Frontend)
```

**Key routing [Decision CEO-1A]:** nginx reverse proxy provides one public origin. Frontend constructs SSE URL from relative path: `${window.location.origin}${streamUrl}`. No cross-origin issues.

### 2.2 Architecture Principles

1. **Deterministic calculation** — All engineering math runs in pure Python functions. No AI in the calculation path.
2. **Bounded AI judgment** — AI reviews outputs but can only: proceed, correct a parameter, warn, or escalate. Cannot skip steps, override safety rules, or act without constraint.
3. **Hard rule safety net** — Engineering limits checked BEFORE AI review. AI cannot override these.
4. **User escalation** — When AI cannot resolve something, it pauses and asks the user. User is always the final authority.
5. **Full transparency** — Every step streams to the frontend. User sees what happened, why, and what was corrected.

### 2.3 Secrets Management [Decision CEO-2A]

- `.env` file for all secrets (ANTHROPIC_API_KEY, SUPERMEMORY_API_KEY, INTERNAL_SECRET, HX_ENGINE_SECRET, JWT_SECRET, MONGODB_URI, REDIS_URL)
- `.env.example` committed with placeholder values
- `.env` in `.gitignore`
- docker-compose.yml references `env_file: .env`

---

## 3. The Four Layers

Every step in the 16-step pipeline passes through four layers:

### Layer 1: Step Executor
- **What:** Pure Python calculation for one step
- **Implementation:** 16 pure functions — no side effects, fully testable in isolation
- **Speed:** 1–50ms per step
- **Rule:** Reads from design_state, returns StepResult. Never modifies state directly.

### Layer 2: Validation Router (Hard Rules)
- **What:** Pass/fail engineering checks — runs BEFORE AI review
- **Implementation:** Pure Python rule functions, instant
- **Speed:** <1ms
- **Rule:** AI CANNOT override these. If F < 0.75, it fails regardless of what the AI thinks.
- **Examples:** `F_t >= 0.75`, `dP_tube < limit`, `velocity > 0.5 m/s`, `J_l > 0.40`

### Layer 3: AI Senior Engineer
- **What:** Reviews step output, applies engineering judgment, suggests corrections
- **Implementation:** Single Anthropic API call per review (NOT an agent — see Section 5)
- **Speed:** 1–3 seconds per call
- **Rule:** Can only do four things: proceed, correct, warn, escalate. Never modifies values directly — suggests corrections that Layer 1 re-executes.
- **Retry logic [Decision CEO-3A]:** Retry 2× with backoff on failure. If all 3 attempts fail → WARN + proceed with `ai_called=False`.

### Layer 4: Design State
- **What:** Shared Pydantic model that accumulates all outputs, corrections, warnings, review notes, and confidence scores across all 16 steps
- **Implementation:** Initialized from request, grows with each step, serialized to JSON for frontend
- **Speed:** Instant
- **Rule:** Every step reads from it and writes to it. By Step 16, it contains the complete design.

### How They Work Together (at every step):

```
Layer 1: execute_step(design_state) → StepResult
    ↓
Layer 2: validation_rules.check(step, result) → PASS/FAIL
    ↓ (if FAIL → retry with geometry fix, max 3 retries)
Layer 3: ai_engineer.review(step, result, design_state, context) → Decision
    ↓
    ├── PROCEED → commit to design_state, next step
    ├── CORRECT → apply correction, re-run Layer 1, verify
    ├── WARN → record warning, proceed
    └── ESCALATE → pause, ask user, resume after response
    ↓
Layer 4: design_state.update(step, result, review)
    ↓
Emit SSE event to frontend
```

### Complete 4-Layer Code Flow (Step 9 Example)

```python
# pipeline_runner.py — Step 9 showing all 4 layers orchestrated

async def run_step_9(design_state, ai_engineer, memory):

    # Layer 1: Execute pure calculation
    result = step09_overall_u.execute(design_state)

    # Layer 2: Hard rules check (AI CANNOT override)
    validation = validation_rules.check(step=9, result=result)
    if validation.fails:
        return handle_hard_failure(step=9, validation)

    # Your code fetches context from Supermemory (NOT the AI)
    hot = design_state.shell_fluid.name
    cold = design_state.tube_fluid.name
    book_ctx, past_ctx = await asyncio.gather(
        _safe_memory_call(memory.search_books(f"overall U {hot} {cold} typical range")),
        _safe_memory_call(memory.search_past_designs(f"{hot} {cold} heat exchanger U value"))
    )

    # Layer 3 + 4: AI review via shared correction loop [Decision ENG-1A, ENG-1B]
    # Full loop logic lives in BaseStep.run_with_review_loop() — see §7.5.
    review = await self.run_with_review_loop(
        result, design_state, ai_engineer, book_ctx, past_ctx
    )

    design_state.update(step=9, result=result, review=review)
```

---

## 4. The Three Loops

### Loop 1: Backend Orchestration (existing, upgraded in Week 6)

- **Location:** `backend/app/services/orchestration_service.py`
- **Owner:** Claude LLM (decides what to do)
- **Purpose:** Conversational agent that picks the right tool based on user intent
- **Duration:** 10–60 seconds total
- **Parameters (unchanged):**
  - MAX_ITERATIONS: 10
  - MAX_TOOL_CALLS: 15
  - MAX_REPEATED_ERRORS: 3
  - Default model: claude-sonnet-4-6
  - Max tokens: 4096

**Current state (Weeks 1–5):** Plain streaming Claude, no tools, no agentic loop. The comment in `orchestration_service.py` says "When HX Engine tools become available, they will be added here." Do not add HX tool calls before Week 6 — the HX Engine pipeline must be accurate first (HTRI gate §15.8).

**Week 6 upgrade:** Promote to a proper agentic loop with tool support:
- Register `hx_design`, `hx_rate`, `hx_get_fluid_properties` as Claude tools (schema from `engine_client.py`)
- Claude decides intent — no frontend keyword matching or parallel requests
- Tool executor calls `engine_client.start_design()` → gets `{ session_id, stream_url }` → returns as tool result
- `process_message()` returns `tool_calls` list; `chat.py` maps it to `tool_executions` in the HTTP response
- Frontend reads `tool_executions`, finds `hx_design`, calls `connectStream(result.stream_url)`

**Critical rule:** The frontend NEVER calls `POST /api/v1/hx/start` directly. The only path from browser to HX Engine trigger is: chat message → Claude tool call → backend tool executor → HX Engine.

### Loop 2: HX Engine Step Pipeline (new)

- **Location:** `hx_engine/app/core/pipeline_runner.py`
- **Owner:** Deterministic Python code + AI reviewer
- **Purpose:** Execute 16-step HX design with AI review at every step
- **Duration:** 15–25 seconds
- **Key:** Steps always run in order 1→16. AI does NOT control the flow.

### Loop 3: Autoresearch Optimization

**Status: DEFERRED TO POST-BETA [Eng Review, 2026-03-21]**
See §20 P2 for implementation plan. Beta ships with Loop 1 + Loop 2 only.

- **Purpose:** Explore 200+ geometry variants, return Pareto front of cost/performance trade-offs.
- **Why deferred:** Core value is Loop 2 (accurate 16-step design). Autoresearch adds optimization on top. Better to validate Loop 2 accuracy with beta engineers first — optimization is only useful if the base calculation is trusted. Also avoids the GIL/ThreadPoolExecutor parallelism question until we have timing data from real Bell-Delaware builds.

### How They Nest:

```
User message
  ↓
LOOP 1 (Backend — Claude orchestration):
  Claude calls hx_get_fluid_properties → HX Engine (instant, no Loop 2)
  Claude calls hx_design → HX Engine → LOOP 2 runs (15-25 seconds)
  # hx_optimize → LOOP 3 (post-beta, not in 7-week beta build)
  Claude presents results to user
```

### Timing Expectations:

| Tool | Loop 2 Behavior | Expected Time |
|------|----------------|---------------|
| `hx_get_fluid_properties` | No loop, direct calculation | < 100ms |
| `hx_suggest_geometry` | No loop, heuristic lookup | < 100ms |
| `hx_design` | Full 16-step + AI review | 15–25 seconds |
| `hx_rate` | Steps 2-11 only (no sizing) | 5–15 seconds |
| `hx_optimize` | 200 experiments, Steps 7-11 | 30–60 seconds | **POST-BETA** |

---

## 5. The AI Senior Engineer

### 5.1 It Is a Single API Call, NOT an Agent

This is critical. The AI reviewer does NOT:
- Decide its own next action
- Call tools (including Supermemory)
- Loop or iterate
- Have a multi-turn conversation

It IS:
- A single `client.messages.create()` call to the Anthropic API
- Prompt in (calculation result + context), JSON out (decision)
- Your code (`pipeline_runner.py`) controls the flow entirely

```python
# ai_engineer.py — the entire AI review mechanism
response = await client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1000,
    messages=[{"role": "user", "content": prompt}]
)
return json.loads(response.content[0].text)
```

### 5.2 Retry Logic [Decision CEO-3A]

```python
# ai_engineer.py
for attempt in range(3):
    try:
        response = await client.messages.create(...)
        return json.loads(response.content[0].text)
    except (APIError, JSONDecodeError, TimeoutError) as e:
        if attempt < 2:
            await asyncio.sleep(2 ** attempt)  # backoff: 1s, 2s
            continue
        # All 3 attempts failed
        return AIDecision(action="WARN", ai_called=False,
                         reasoning="AI review unavailable — proceeding with hard rules only")
```

- Claude refusal (no tool_use / garbled response) → treated as WARN, `ai_called=False`
- Rate limit (429) → retried with backoff, then WARN after 3 failures

### 5.3 The Four Decisions

| Decision | Meaning | Action | User Sees |
|----------|---------|--------|-----------|
| **PROCEED** | Correct and reasonable | Commit to design state, next step | Green check + summary |
| **CORRECT** | Passes hard rules but suboptimal | Modify parameter, re-run step | Wrench + before/after values |
| **WARN** | Borderline but acceptable | Record warning, proceed | Yellow triangle + concern |
| **ESCALATE** | Needs human judgment | Pause, ask user | Red circle + question |

### 5.4 Full Context Via Design State

Each AI review call receives the COMPLETE design_state — all outputs from all previous steps. By Step 9, the AI sees everything from Steps 1–8, including all corrections and warnings.

Additionally, a `review_notes` field carries forward key engineering observations:

```python
design_state["review_notes"] = [
    {
        "step": 3,
        "note": "Crude oil viscosity from thermo library was suspiciously low. Corrected 0.45→0.80 mPa·s. If actual crude is heavier, properties could shift significantly.",
        "affects_steps": [7, 8, 9, 12]
    },
    {
        "step": 8,
        "note": "Baffle clearance tightened to fix J_l. Watch shell-side dP at Step 10.",
        "affects_steps": [10, 12]
    },
]
```

Each note is 30–50 tokens. By Step 16, review_notes adds 300–800 tokens to the prompt (upper bound when all 16 steps add a note; typical is 300–500) — small cost for cross-step reasoning.

### 5.5 What the AI Review Prompt Contains

Every AI review call sends four sections:

1. **Calculation Result** — what Layer 1 just computed
2. **Book Context** — relevant paragraphs from Supermemory (books)
3. **Past Design Data** — similar past designs from Supermemory
4. **Full Design State** — all outputs + review_notes from all previous steps

Example prompt for Step 9:

```
You are a senior process engineer reviewing Step 9:
Overall Heat Transfer Coefficient.

CALCULATION RESULT:
  U_calculated = 378 W/m²K
  Resistance breakdown: shell_film 28%, tube_film 29%, ...
  Cross-check: Kern method U = 410 W/m²K (deviation: 8%)

BOOK REFERENCE (from Supermemory):
  "For crude oil / cooling water, typical U: 300-500 W/m²K"
  — Serth & Lestina, Table 3.5

PAST DESIGNS (from Supermemory):
  - Run #42: crude/water, Q=5800kW, U=365
  - Run #47: crude/water, Q=6500kW, U=412
  Average past U: 385 W/m²K

PREVIOUS REVIEW NOTES:
  Step 3: viscosity corrected (affects this step)
  Step 8: baffle clearance tightened

FULL DESIGN STATE:
  {complete JSON of all previous step outputs}

Respond with JSON: {decision, confidence, reasoning, correction, user_summary}
```

**Prompt injection mitigation [CEO Amendment]:** Add system-level instruction to `engineer_review.txt` that constrains the AI to only respond with the expected JSON schema and reject any embedded instructions in the design state or book context.

**Try-first instruction [Decision ENG-1A]:** `engineer_review.txt` must include this instruction before the JSON schema:
> "Before choosing `escalate`, attempt to resolve the issue using sound engineering judgment — apply the conservative standard, select the safer geometry, or use the TEMA default. Only choose `escalate` if you have genuinely exhausted all reasonable options and cannot proceed without user input. When you do escalate, populate `attempts`, `observation`, `recommendation`, and `options` so the user has full context."

**Confidence gate [Decision ENG-1B]:** After every AI review (initial + each correction re-review), check `confidence`. If `confidence < 0.70`, treat the decision as `escalate` regardless of what the AI returned. This prevents low-confidence corrections from silently degrading the design.

### 5.6 The AI Returns Structured JSON

**proceed / correct / warn:**
```json
{
  "decision": "proceed",
  "confidence": 0.91,
  "reasoning": "U=378 within book range (300-500) and close to past avg (385). Kern deviation 8% is well within 15% threshold. Tube-side film controls at 29% — expected for crude oil.",
  "correction": null,
  "user_summary": "Overall U = 378 W/m²K — consistent with past designs and reference data. Tube-side film resistance dominates at 29%."
}
```

**escalate** — extended payload required [Decision ENG-1A]:
```json
{
  "decision": "escalate",
  "confidence": 0.31,
  "reasoning": "Tried BEM and BEU configurations. Neither satisfies both ΔP and bundle fit constraints at 610mm shell.",
  "correction": null,
  "attempts": [
    "BEM (fixed tubesheet): shell-side ΔP = 0.82 bar, exceeds 0.70 bar limit",
    "BEU (U-tube): bundle diameter 632mm, exceeds 610mm shell ID"
  ],
  "observation": "610mm shell cannot accommodate the required tube count at acceptable pressure drop for either bundle type.",
  "recommendation": "Upsize to 762mm shell (next TEMA standard). Adds ~$3,200 to fabrication cost but satisfies both constraints.",
  "options": [
    "Proceed with 762mm shell (recommended)",
    "Keep 610mm shell and accept ΔP = 0.82 bar (above limit — requires sign-off)",
    "Reduce duty by splitting into two shells in series"
  ],
  "user_summary": "Cannot fit design in 610mm shell. Recommend upsizing to 762mm."
}
```

**Confidence gate [Decision ENG-1B]:** `pipeline_runner.py` checks `confidence` after every AI call. If `confidence < 0.70`, override the decision to `escalate` regardless of what the AI returned. Log `confidence_gate_triggered=True` in the step record.

### 5.7 Helper Function Contracts

These functions are called by `BaseStep.run_with_review_loop()` and must have stable contracts so all 16 steps behave consistently.

```python
def apply_correction(state: DesignState, correction: AICorrection) -> None:
    """
    Write AI-proposed correction values into DesignState.
    Only mutates fields listed in correction.affected_fields.
    Called AFTER snapshot_fields(), BEFORE re-running Layer 1.

    correction.affected_fields: list[str]  — e.g. ["shell_id_mm", "baffle_spacing_mm"]
    correction.values: dict[str, Any]       — new values keyed by field name
    """

def apply_user_response(state: DesignState, response: UserResponse) -> None:
    """
    Apply user's ESCALATED decision to DesignState.

    response.type:
      'accept'   — AI's recommendation accepted; apply correction.values to state
      'override' — user typed their own values; apply response.values to state
      'skip'     — user approves step as-is; no state mutation, just mark step reviewed

    After this call, pipeline_runner re-runs Layer 1 + Layer 2 + AI review [Decision ENG-2A].
    """

# DesignState methods (defined on the Pydantic model):
def snapshot_fields(self, field_names: list[str]) -> dict[str, Any]:
    """Return {field: current_value} for the listed fields. Called before apply_correction."""

def restore(self, snapshot: dict[str, Any]) -> None:
    """Write snapshot values back to DesignState fields. Called on Layer 2 hard fail."""
```

---

## 6. AI Review Protocol — All 16 Steps

### 6.1 Tiered Review Depth

| Tier | When Used | AI Call | Steps |
|------|-----------|---------|-------|
| **Full AI Review** | Engineering judgment required — no formula can replace it | Always called (1–3s) | Steps 1, 4, 8, 9, 13, 16 |
| **Conditional Review** | Local Python check first; AI called ONLY if anomaly detected | Called 30–50% of the time | Steps 2, 3, 5, 6, 7, 10, 11, 14, 15 |
| **No AI Review** | Pure convergence loop — too fast for AI latency | Never called | Step 12 (inner iteration) |

**Expected per design:** 6 always + 3–5 conditional = 9–11 AI calls. Total: 15–25 seconds.

**AI Call Count Breakdown (per design):**

| Source | Count | Details |
|--------|-------|--------|
| Loop 1 (Backend Claude) | ~3 calls | Orchestration: tool selection + narrative generation |
| Loop 2 (HX Engine AI reviews) | 6–8 calls | 6 FULL steps always + 0–2 CONDITIONAL triggers |
| **Total AI calls** | **~9–11** | |
| Supermemory reads | ~8 calls | Steps 1, 4, 6, 8, 9, 13, 16 (books + past designs + profile) |
| Supermemory writes | ~2 calls | Step 16: save design + store conversation |
| **Total Supermemory** | **~10** | |

### 6.2 AI Mode Summary Table

| Step | Name | AI Mode | Key Rule |
|------|------|---------|----------|
| 1 | Process Requirements | FULL always | Escalate if fluid ambiguous |
| 2 | Heat Duty | CONDITIONAL | AI if Q balance error > 2% |
| 3 | Fluid Properties | CONDITIONAL | AI if Pr < 0.5 or > 1000 |
| 4 | TEMA Type + Geometry | FULL always | Escalate if two types equally valid |
| 5 | LMTD + F-Factor | CONDITIONAL (F < 0.85) | Hard fail if F < 0.75 |
| 6 | Initial U + Size | CONDITIONAL + Supermemory | asyncio.gather books + past |
| 7 | Tube-side h | CONDITIONAL (check loop flag) | Skip AI if in_convergence_loop |
| 8 | Shell-side h (Bell-Delaware) | FULL always | Serth 5.1 validated |
| 9 | Overall U + Resistances | FULL + parallel Supermemory | asyncio.gather books + past |
| 10 | Pressure Drops | CONDITIONAL (check loop flag) | Skip AI if in_convergence_loop |
| 11 | Area + Overdesign | CONDITIONAL (check loop flag) | Skip AI if in_convergence_loop |
| 12 | Convergence Loop (7→11) | NONE (try/finally) | Max 20 iterations, CG1A reset |
| 13 | Vibration (5 mechanisms) | FULL always (safety) | Connors pre-filter in autoresearch |
| 14 | Mechanical (ASME VIII) | CONDITIONAL | AI if P > 30 bar |
| 15 | Cost (Turton + CEPCI) | CONDITIONAL | AI if cost anomalous vs past |
| 16 | Final Validation + Confidence | FULL + all 3 Supermemory | asyncio.gather all three |

### 6.3 Complete Step-by-Step Protocol

#### Step 1: Gather Process Requirements
- **Tier:** FULL AI — Always called
- **Layer 1:** Extract structured data from request (fluids, temps, flows)
- **Layer 2:** Check all blocking inputs present (fluid names, 3+ temps, flow rates)
- **Supermemory:** Fetch user profile (preferences, industry, past patterns)
- **AI checks:** Are defaults reasonable? Should pressure be higher (phase change risk)? Industry-specific rules (TEMA Class R for refinery)?
- **Can correct:** Override default pressure, set TEMA class from context, flag ambiguous fluids
- **Escalates when:** Fluid identity ambiguous, less than 3 temperatures, flow rate missing
- **Corner cases:**
  - User says "oil" — could be crude, thermal, vegetable. AI must ask.
  - User provides temps in °F — system must handle unit conversion
  - User provides 4 temperatures that don't satisfy energy balance — flag error
  - User says "same as last time" — fetch from Supermemory user profile

#### Step 2: Calculate Heat Duty
- **Tier:** CONDITIONAL — AI called only if anomaly
- **Layer 1:** Q = m × Cp × ΔT using thermo library for Cp. Calculate 4th temperature from energy balance.
- **Layer 2:** Q > 0, energy balance closure |Q_hot − Q_cold|/Q_hot < 1%, T_cold_out > T_cold_in, T_cold_out < T_hot_in
- **Local checks (trigger AI if fail):** Q seems unusually high/low for flow rate, Cp from library anomalous, T_cold_out very close to T_hot_in (tight approach)
- **Can correct:** Adjust Cp if library returns anomalous value
- **Corner cases:**
  - Very small ΔT (< 5°C) — LMTD will be tiny, huge area needed. Warn early.
  - Cp that varies dramatically across temperature range (heavy oil) — single-point Cp may be inadequate
  - User provides all 4 temperatures that don't balance — which one to recalculate?
  - Q = 0 (identical inlet/outlet temps) — reject with clear message
  - Phase change likely at atmospheric pressure — flag need for higher pressure input

#### Step 3: Collect Fluid Properties
- **Tier:** CONDITIONAL — AI called if property anomaly
- **Layer 1:** Call thermo/CoolProp/iapws for ρ, μ, k, Cp, σ at bulk average temperature
- **Layer 2:** All properties > 0, density 500–1500 kg/m³ (liquids), viscosity > 0
- **Local checks (trigger AI):** Viscosity outside typical range for fluid type, properties change dramatically inlet→outlet, Pr outside 0.5–2000
- **Can correct:** Override viscosity with industry value if library result clearly wrong, add Sieder-Tate wall correction if viscosity ratio large
- **Corner cases:**
  - Fluid not in thermo library database — must handle gracefully, suggest similar fluid
  - Mixture with unknown interaction parameters — warn about property uncertainty
  - Properties at conditions near critical point — libraries may give erratic results
  - Supercooled or superheated conditions — verify phase is as expected
  - User specifies "crude oil" without API gravity — assume medium (API 29) and flag
  - Water properties near 0°C or >100°C at atmospheric — check for phase change

#### Step 4: Select TEMA Type and Initial Geometry
- **Tier:** FULL AI — Always called
- **Layer 1:** Decision tree for TEMA type based on process conditions. Heuristic selection of tube OD, pitch, layout angle, passes, length, baffle cut.
- **Layer 2:** Selected geometry parameters within TEMA standards
- **Supermemory:** Search books for TEMA selection rules. Search past designs for similar service.
- **AI checks:** TEMA type vs thermal expansion (ΔT > 50°C → floating head), tube allocation (fouling fluid tube-side), pitch angle (90° for cleaning), industry rules
- **Can correct:** Switch BEM→AES if expansion problematic, switch to square pitch if fouling, change tube allocation if high-pressure on wrong side
- **Escalates when:** Two TEMA types equally valid — present trade-offs to user
- **Corner cases:**
  - Very high pressure on one side (> 100 bar) — must go tube-side, consider type D head
  - Both fluids foul heavily — square pitch needed but cleaning access limited. Escalate.
  - Very small duty (< 50 kW) — standard TEMA sizes may be overkill. Consider hairpin.
  - Very large duty (> 50 MW) — may need multiple shells in series/parallel
  - Corrosive fluid — 316SS or titanium tubes, affects tube count tables
  - User specifies a TEMA type that conflicts with service (e.g., BEM with 80°C ΔT) — warn

#### Step 5: Determine LMTD and F-Factor
- **Tier:** CONDITIONAL — AI called if F < 0.85
- **Layer 1:** LMTD from 4 temperatures. R, P, F-factor from analytical expressions.
- **Layer 2:** F ≥ 0.75 (hard rule), LMTD > 0, R and P within valid domain
- **Local checks:** F < 0.85 (borderline), R > 4 (highly asymmetric)
- **Can correct:** Increment shell passes from 1→2 if F < 0.80. Warn about temperature cross risk.
- **Corner cases:**
  - F < 0.75 — HARD FAIL. Must increase shell passes. If still < 0.75 with 2 shells, need different approach.
  - Pure counter-current (F = 1.0) — only possible with 1 tube pass. Rare in practice.
  - Temperature cross (T_cold_out > T_hot_out) — F-factor formula may give imaginary result. Detect and handle.
  - R = 1.0 exactly — special case in F-factor formula (L'Hôpital's rule needed to avoid division by zero)
  - Very small LMTD (< 3°C) — huge area required. May not be economically viable. Warn.
  - ΔT1 = ΔT2 exactly — LMTD formula has 0/0. Use arithmetic mean instead.

#### Step 6: Estimate Initial U and Size
- **Tier:** CONDITIONAL — AI called if U outside typical range or past designs available
- **Layer 1:** Look up typical U for fluid pair. Compute A = Q/(U×F×LMTD). Compute N_tubes = A/(π×d_o×L). Look up shell diameter from TEMA tube count tables.
- **Layer 2:** U > 0, A > 0, tube count maps to a standard shell size
- **Supermemory:** Search past designs for empirical U average (better than book midpoint). Uses asyncio.gather [Decision 9A].
- **Can correct:** Use past design avg U instead of book midpoint. Adjust shell to next standard size if tube count between table entries.
- **Corner cases:**
  - Required tube count exceeds largest single shell — need shells in series or parallel
  - Tube count maps exactly between two standard shells — choose larger (conservative)
  - No past designs available for this fluid pair — fall back to book midpoint with wider uncertainty
  - Estimated area < 5 m² — very small exchanger, consider if shell-and-tube is the right type

#### Step 7: Tube-Side Heat Transfer Coefficient
- **Tier:** CONDITIONAL — AI called if velocity or Re problematic
- **Layer 1:** Compute velocity, Re, Pr. Select correlation (Gnielinski/Hausen/transition blend). Compute h_i.
- **Layer 2:** h_i > 0, velocity within physical bounds
- **Local checks:** Velocity < 0.8 m/s (fouling risk), velocity > 2.5 m/s (erosion risk), Re in transition zone (2300–10000)
- **Can correct:** Increase tube passes if velocity < 0.5 m/s, decrease if > 3.0 m/s
- **Convergence-loop aware:** Skip AI when `in_convergence_loop=True` [Decision 3A]
- **Corner cases:**
  - Laminar flow (Re < 2300) — Gnielinski invalid. Switch to Hausen/Sieder-Tate. Much lower h_i.
  - Transition flow (2300 < Re < 10000) — must blend laminar and turbulent. No single correlation is accurate.
  - Very viscous fluid (μ > 10 mPa·s) — Sieder-Tate wall correction becomes significant. Need wall temperature estimate.
  - Single tube pass with very low velocity — may need to reconsider geometry
  - Non-circular tubes (e.g., enhanced/finned) — standard correlations don't apply directly

#### Step 8: Shell-Side Heat Transfer Coefficient (Bell-Delaware)
- **Tier:** FULL AI — Always called (most complex calculation)
- **Layer 1:** Compute all geometric areas (cross-flow, leakage A_sb, A_tb, bypass A_bp). Compute ideal h. Compute 5 J-factors. h_o = h_ideal × J_c × J_l × J_b × J_s × J_r.
- **Layer 2:** h_o > 0, all J-factors in range (0.2–1.2)
- **Supermemory:** Search books for J-factor diagnostic ranges
- **review_protocol.py thresholds:**
  - J_l: warn_below 0.55, correct_below 0.45
  - J_b: warn_below 0.60, correct_below 0.50
  - J_c: warn_below 0.70, correct_below 0.60
  - Product J_c×J_l×J_b: warn_below 0.40, correct_below 0.30
- **AI checks:** Are J-factors physically reasonable? Does h_o make sense for this fluid? Cross-flow velocity vs vibration risk?
- **Can correct:** Tighten baffle-tube clearance (for J_l), add sealing strips (for J_b), adjust baffle cut (for J_c)
- **Corner cases:**
  - J_l < 0.3 — extreme leakage. May indicate wrong shell-to-baffle clearance or very small shell.
  - J_r < 0.6 — adverse temperature gradient in laminar flow. Consider turbulence promoters.
  - No tubes in window (NTIW) — J_c formula different. Must detect and handle.
  - Double-segmental baffles — Bell-Delaware needs modified geometric calculations
  - Baffle spacing < 0.2×D_s — unrealistically close, fabrication impossible
  - Baffle spacing > 1.0×D_s — very wide, poor shell-side distribution
  - Shell-side Reynolds < 100 — Bell-Delaware correlations may not be valid

#### Step 9: Overall U and Resistance Breakdown
- **Tier:** FULL AI — Always called
- **Layer 1:** 1/U = 1/h_o + R_f,o + t_w/k_w + R_f,i + (d_o/d_i)/h_i. Compute each resistance as percentage.
- **Layer 2:** U > 0, all resistances > 0, percentages sum to 100%
- **Supermemory:** Search books for typical U range. Search past designs for empirical comparison. Uses asyncio.gather [Decision 9A].
- **AI checks:** U in typical range? Resistance breakdown makes physical sense? Kern cross-check deviation < 15%? Controlling resistance identified correctly?
- **Can correct:** Flag if U far from expected — likely indicates a problem upstream
- **Corner cases:**
  - U_calculated very different from U_estimated (Step 6) — geometry is wrong size. Need significant iteration.
  - One resistance dominates at > 60% — design is severely limited by one factor
  - Fouling resistance > film resistance — over-fouled design, consider reducing fouling factor if plant data available
  - Kern vs Bell-Delaware deviation > 20% — unusual, investigate why (often a geometric parameter error)
  - Wall resistance > 10% — only happens with very thick walls or low-conductivity materials (titanium)

#### Step 10: Pressure Drops
- **Tier:** CONDITIONAL — AI called if margin < 15%
- **Layer 1:** Tube-side: Darcy-Weisbach + return losses (4 velocity heads/pass) + nozzle losses. Shell-side: Bell-Delaware dP method with R_l, R_b, R_s corrections.
- **Layer 2:** dP_tube < limit, dP_shell < limit, nozzle ρv² < 2230 kg/m·s² (liquid). Hard limits: dP_shell < 1.4 bar, dP_tube < 0.7 bar.
- **review_protocol.py:** If margin < 15% on either side → auto-correct before AI call
- **Convergence-loop aware:** Skip AI when `in_convergence_loop=True` [Decision 3A]
- **Can correct:** Increase baffle spacing if shell dP tight, reduce tube passes if tube dP tight
- **Corner cases:**
  - Nozzle pressure drop dominates (> 30% of total) — nozzles too small. Increase nozzle diameter.
  - Shell-side dP very low (< 10% of limit) — may indicate poor shell-side flow distribution
  - Tube-side dP very low with low velocity — consider increasing passes for better heat transfer
  - Two-phase flow — dP correlations completely different (Lockhart-Martinelli). Not applicable for Phase 1.
  - Very viscous fluid — dP dominated by friction, return losses negligible

#### Step 11: Area and Overdesign
- **Tier:** CONDITIONAL — AI called if overdesign outside 8–30%
- **Layer 1:** A_required = Q/(U_calc × F × LMTD). A_available = N_tubes × π × d_o × L_effective. Overdesign = (A_available − A_required)/A_required × 100%.
- **Layer 2:** Overdesign > −5% (not critically undersized). Hard fail: overdesign < 0%.
- **Target range:** 10–25% (ideal), 0–40% (acceptable)
- **Convergence-loop aware:** Skip AI when `in_convergence_loop=True` [Decision 3A]
- **Can correct:** Increase tube count/length if undersized, decrease if oversized
- **Corner cases:**
  - Overdesign > 50% — waste of money. Step 12 should reduce geometry.
  - Overdesign exactly 0% — no safety margin. Minimum 10% needed for fouling and uncertainty.
  - Negative overdesign after convergence — may need to jump to next standard shell size
  - Very high overdesign in rating mode — exchanger is oversized for current duty. Report but don't "fix."

#### Step 12: Geometry Iteration (Convergence Loop)
- **Tier:** NO AI — Pure convergence loop, too fast for AI latency
- **Layer 1:** Run Steps 7→11 in a tight loop. Adjust geometry based on constraint violations.
- **Convergence criteria:** |U_calc − U_assumed| ≤ tolerance (ΔU < 1%), overdesign 10–25%, all dP within limits, velocity in range
- **Max iterations:** 20
- **Adjustment priority:** Fix dP violations first → overdesign → velocity
- **Implementation [CG1A]:** try/finally flag reset ensures `in_convergence_loop` is always cleared:

```python
state = state.model_copy(update={"in_convergence_loop": True})
try:
    for iteration in range(1, 21):
        # run Steps 7–11 (no AI due to flag)
        ...
        if converged: break
finally:
    state = state.model_copy(update={"in_convergence_loop": False})
    # CG1A: resets even if exception raised mid-iteration
```

- **AI called ONLY if:** Loop fails to converge after 20 iterations. AI then analyzes why and suggests structural change (different TEMA type, different baffle type).
- **SSE:** Emits `iteration_progress` event each iteration.
- **Corner cases:**
  - Oscillation between two geometries (shell diameter up then down) — implement damping
  - Conflicting constraints (lower dP requires wider spacing, but wider spacing gives low h_o) — may need trade-off
  - Convergence to overdesign = 0% exactly — on the edge, may oscillate. Accept if stable for 3 iterations.
  - Very small shell (< 200mm) — tube count tables may not have exact match. Interpolate.
  - Tube count doesn't match TEMA table exactly — round to nearest table entry

#### Step 13: Vibration Check
- **Tier:** FULL AI — Always called (safety-critical)
- **Layer 1:** Natural frequency at each span. Cross-flow velocity at each baffle compartment. Check 5 mechanisms: fluidelastic instability (Connors), vortex shedding, turbulent buffeting, acoustic resonance (gas only), fluid-elastic whirling.
- **Layer 2:** u_cross/u_crit < 0.5 at every span (Connors criterion with safety factor)
- **Supermemory:** Search books for vibration safety criteria
- **AI checks:** All 5 mechanisms at every span. Inlet/outlet spans (longest) are most critical.
- **Can correct:** Reduce baffle spacing (shorter span = higher natural frequency), add intermediate supports, add impingement baffle at inlet
- **Escalates when:** Vibration fix conflicts with dP limit — present trade-off (rod baffles, helical baffles, or accept higher dP)
- **Corner cases:**
  - Gas service — acoustic resonance possible. Must check acoustic frequency vs vortex frequency.
  - Inlet span is 1.5× central span — most likely vibration failure location
  - U-tube bundle — natural frequency calculation different (different end conditions)
  - Frequency ratio 0.8–1.2 (lock-in zone) — even if velocity is below Connors threshold, resonance risk
  - Very long tubes (> 6m) with few baffles — may need intermediate supports
  - Two-phase flow — velocity varies dramatically along shell length. Check at every compartment.

#### Step 14: Mechanical Design Check
- **Tier:** CONDITIONAL — AI called if borderline thickness or high expansion
- **Layer 1:** ASME VIII tube thickness, shell thickness. Thermal expansion differential.
- **Layer 2:** Actual wall thickness ≥ minimum required. Expansion within tolerance for selected rear head type.
- **Can correct:** Change rear head type (BEM→AES) if expansion exceeds tolerance. Increase tube BWG if thickness borderline.
- **Corner cases:**
  - External pressure on tubes (shell-side pressure > tube-side) — different ASME formula
  - Very high pressure (> 100 bar) — may need special high-pressure closures (type D head)
  - Differential expansion > 5mm — U-tube or floating head mandatory
  - Corrosion allowance reduces effective thickness significantly for thin tubes
  - Tubesheet thickness not checked in Phase 1 — flag as limitation

#### Step 15: Cost Estimate
- **Tier:** CONDITIONAL — AI called if cost anomalous
- **Layer 1:** Turton correlations. CEPCI adjustment. Material and pressure correction factors.
- **Layer 2:** Cost > 0, cost per m² within reasonable range for material
- **CEPCI [CEO Amendment]:** Use 2026 index (~816), not "2024 ≈ 800". CEPCI_INDEX constant with `last_updated` timestamp; log warning if > 90 days old.
- **Can correct:** Verify CEPCI is current year, cross-check material factor
- **Corner cases:**
  - Exotic materials (titanium, Hastelloy) — material factor > 5×. Verify factor is correct for the specific alloy.
  - Very large area (> 1000 m²) — Turton correlation may extrapolate. Flag as approximate.
  - Very small area (< 10 m²) — minimum fabrication cost may dominate
  - Pressure factor for very high pressure designs can triple the cost
  - CEPCI index must be for the correct year — using old index underestimates cost

#### Step 16: Final Validation and Confidence
- **Tier:** FULL AI — Always called (final sign-off)
- **Layer 1:** Run all final checks. Compute confidence score.
- **Supermemory:** Full context search — books + past designs + user profile. Uses asyncio.gather for all 3 [Decision 9A].
- **Confidence Score [CEO-CP2]:**
  - `confidence_breakdown` dict with 4 keys:
    - `geometry_convergence`: float [0.0, 1.0]
    - `ai_agreement_rate`: float [0.0, 1.0]
    - `supermemory_similarity`: float [0.0, 1.0]
    - `validation_passes`: float [0.0, 1.0]
  - `CONFIDENCE_WEIGHTS` constant: equal weights 0.25 each [Decision CEO-7A], tunable
  - `confidence_score` = weighted sum of breakdown × weights
  - Both stored in DesignState and shown in DesignSummary card (breakdown expandable)
- **AI produces:**
  1. Confidence score via breakdown formula
  2. Plain-English summary of the design and trade-offs
  3. List of all assumptions made and their impact
  4. Recommendations if confidence < 0.80
- **Save to Supermemory:** If confidence ≥ 0.75, store design summary to past_designs
- **Corner cases:**
  - Confidence < 0.70 — design may be unreliable. Strong warning to user.
  - Multiple corrections made — compound uncertainty. Reduce confidence.
  - Key input was assumed (viscosity, fouling factor) — note in assumptions list
  - Cross-method deviation > 15% but U in typical range — conflicting signals. AI must interpret.

---

## 7. Key Contracts & Data Models

### 7.1 FluidProperties [Decision 3R-4A]

```python
# hx_engine/app/models/design_state.py
class FluidProperties(BaseModel):
    name: str
    density_kg_m3: float          # [50, 2000]
    viscosity_Pa_s: float         # [1e-6, 1.0]
    cp_J_kgK: float               # [500, 10000]
    k_W_mK: float                 # [0.01, 100]
    Pr: float                     # [0.5, 1000]
    phase: str = "liquid"         # "liquid" | "gas"
    mean_temp_C: Optional[float] = None
```

### 7.2 StepRecord [Decision 3R-5A]

```python
# hx_engine/app/models/step_result.py
class StepRecord(BaseModel):
    """Persisted audit log entry appended to DesignState.step_records after each step."""
    step_id: int
    step_name: str
    result: StepResult
    timestamp: datetime
    duration_ms: int
    ai_called: bool
```

### 7.3 DesignState [Decision 2B + CG3A + CEO Amendments]

```python
# hx_engine/app/models/design_state.py
class GeometrySpec(BaseModel):
    shell_diameter_m: Optional[float] = None
    tube_od_m: Optional[float] = None
    tube_id_m: Optional[float] = None
    tube_length_m: Optional[float] = None
    baffle_spacing_m: Optional[float] = None   # validator: [0.05, 2.0] m
    pitch_ratio: Optional[float] = None        # validator: [1.2, 1.5]
    n_tubes: Optional[int] = None
    n_passes: Optional[int] = None
    pitch_layout: str = "triangular"
    # @field_validator on all length/ratio fields — CG3A

class DesignState(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))  # CEO Amendment
    user_id: str
    org_id: Optional[str] = None        # CEO-CP4: forward compat for team accounts
    raw_request: str
    shell_fluid: Optional[FluidProperties] = None
    tube_fluid: Optional[FluidProperties] = None
    geometry: GeometrySpec = GeometrySpec()
    Q_W: Optional[float] = None
    LMTD_C: Optional[float] = None
    F_factor: Optional[float] = None
    U_overall_W_m2K: Optional[float] = None
    h_tube_W_m2K: Optional[float] = None
    h_shell_W_m2K: Optional[float] = None
    area_required_m2: Optional[float] = None
    area_provided_m2: Optional[float] = None
    overdesign_pct: Optional[float] = None
    dP_tube_Pa: Optional[float] = None
    dP_shell_Pa: Optional[float] = None
    vibration_safe: Optional[bool] = None
    cost_usd: Optional[float] = None
    confidence_score: Optional[float] = None
    confidence_breakdown: Optional[dict] = None   # CEO-CP2: explainability
    # confidence_breakdown keys: geometry_convergence, ai_agreement_rate,
    #   supermemory_similarity, validation_passes — all floats [0.0, 1.0]
    tema_type: Optional[str] = None
    warnings: List[str] = []
    step_records: List[StepRecord] = Field(default_factory=list)  # CEO Amendment: default_factory
    in_convergence_loop: bool = False    # Decision 3A / CG1A
    convergence_iteration: int = 0
    waiting_for_user: bool = False       # True while pipeline is paused at ESCALATE; excludes session from orphan detection
    review_notes: List[str] = Field(default_factory=list)
    # review_notes: AI forward-looking observations appended after each step review.
    # Distinct from warnings (warnings = Layer 2 hard-rule violations).
    # review_notes = AI's 30-50 token observations for future steps, e.g.:
    #   "Shell-side Re is low (650). Step 10 pressure drop will be sensitive to baffle spacing."
    # Passed to subsequent steps in the AI prompt context [§17.2, Eng Review].
```

**Important [CEO Amendment]:** Use `Field(default_factory=list)` for `step_records` and `warnings` to prevent mutable default sharing across instances. Test: `DesignState().step_records is not DesignState().step_records` → True.

**Note [CEO Review 3]:** `/btw` context injection (BTW-1A/2A/3A) deferred to post-beta. See §20 P2 for post-beta implementation plan. `ContextNote` model removed from build scope.

### 7.4 StepProtocol [Decision 6A]

```python
# hx_engine/app/steps/__init__.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class StepProtocol(Protocol):
    step_id: int
    step_name: str
    def execute(self, state: DesignState) -> StepResult: ...
```

### 7.5 BaseStep — 4-layer template + convergence guard [Decision 3A]

```python
# hx_engine/app/steps/base.py
class BaseStep(ABC):
    step_id: int
    step_name: str
    ai_mode: AIModeEnum  # CEO Amendment: use enum, not bare str

    @abstractmethod
    def execute(self, state: DesignState) -> StepResult: ...

    def _should_call_ai(self, state: DesignState, result: StepResult) -> bool:
        if self.ai_mode == AIModeEnum.FULL:   return True
        if self.ai_mode == AIModeEnum.NONE:   return False
        if state.in_convergence_loop: return False   # Decision 3A
        return self._conditional_ai_trigger(state, result)

    async def run_with_review_loop(
        self,
        result: StepResult,
        state: DesignState,
        ai_engineer,
        book_ctx: str,
        past_ctx: str,
    ) -> AIReview:
        """
        Shared correction loop [Decision ENG-1A, ENG-1B].
        All 16 steps call this — written once, not copy-pasted.

        Flow:
          review → correct → re-run Layer 1 → re-review  (attempt 1)
                → correct → re-run Layer 1 → re-review  (attempt 2)
                → correct → re-run Layer 1 → re-review  (attempt 3)
                → escalate (with all 3 attempts in payload)

        Confidence gate: after every review, if confidence < 0.70 → force escalate.
        Snapshot/restore: take DesignState snapshot before each correction;
        restore on Layer 2 hard fail so state is never left partially mutated.
        """
        MAX_CORRECTIONS = 3
        correction_attempts = []

        for attempt in range(MAX_CORRECTIONS + 1):
            review = await ai_engineer.review(
                step=self.step_id, result=result, design_state=state,
                book_context=book_ctx, past_designs=past_ctx,
                prior_attempts=correction_attempts,
            )

            # Confidence gate [Decision ENG-1B]
            if review.confidence < 0.70:
                review.decision = "escalate"
                review.observation = (
                    f"Confidence {review.confidence:.2f} below threshold (0.70) — escalating."
                )

            if review.decision == "correct" and attempt < MAX_CORRECTIONS:
                snapshot = state.snapshot_fields(review.correction.affected_fields)
                apply_correction(state, review.correction)
                result = self.execute(state)          # re-run Layer 1
                validation = validation_rules.check(step=self.step_id, result=result)
                if validation.fails:
                    state.restore(snapshot)           # rollback on hard fail
                correction_attempts.append({
                    "attempt": attempt + 1,
                    "correction": review.correction,
                    "reasoning": review.reasoning,
                    "confidence": review.confidence,
                    "layer2_passed": not validation.fails,
                })
                if validation.fails:
                    continue   # re-review with restored state

            elif review.decision == "correct" and attempt == MAX_CORRECTIONS:
                # 3 corrections exhausted — convert to escalate and fall through to
                # the shared re-escalation loop below [Eng Review — full parity fix].
                # Both correction-exhaustion and direct-escalate use the same
                # MAX_USER_RESPONSES=3 loop; no asymmetry in user attempt handling.
                review.decision = "escalate"
                review.attempts = correction_attempts
                review.observation = "Three correction attempts did not resolve the issue."
                review.recommendation = review.reasoning
                # ↓ falls through to elif review.decision == "escalate"

            elif review.decision == "warn":
                record_warning(state, step=self.step_id, warning=review)
                emit_event("step_warning", step=self.step_id, review=review)
                break

            elif review.decision == "escalate":
                review.attempts = correction_attempts
                # Re-escalate up to 2 more times before halting [Decision ENG-2A]
                MAX_USER_RESPONSES = 3  # first escalation + up to 2 re-escalations
                last_review = review
                for user_attempt in range(MAX_USER_RESPONSES):
                    emit_event("step_escalated", step=self.step_id, review=last_review)
                    user_response = await wait_for_user(state.session_id)
                    # [Decision ENG-2A]: re-run full step after user response
                    apply_user_response(state, user_response)
                    result = self.execute(state)
                    validation = validation_rules.check(step=self.step_id, result=result)
                    if not validation.fails:
                        review2 = await ai_engineer.review(
                            step=self.step_id, result=result, design_state=state,
                            book_context=book_ctx, past_designs=past_ctx,
                            prior_attempts=[],
                        )
                        emit_event("step_approved", step=self.step_id, review=review2)
                        review = review2
                        break
                    # Still failing — build re-escalation review with full context
                    last_review = last_review.model_copy(update={
                        "observation": f"Layer 2 hard rules still violated after user input (attempt {user_attempt + 1}).",
                        "recommendation": last_review.recommendation,  # preserve original
                        "options": last_review.options,                 # preserve original
                    })
                else:
                    # All 3 user attempts exhausted — halt pipeline
                    emit_event("step_error", step=self.step_id,
                               message=f"Step {self.step_id} could not be resolved after 3 user inputs.",
                               observation=last_review.observation,
                               recommendation=last_review.recommendation,
                               options=last_review.options)
                    raise StepHardFailure(step=self.step_id, validation=validation)
                break

            else:  # proceed / approved
                if correction_attempts:
                    emit_event("step_corrected", step=self.step_id, review=review,
                               attempts=correction_attempts)
                else:
                    emit_event("step_approved", step=self.step_id, review=review)
                # Append AI's forward-looking observation to review_notes [§17.2, Eng Review].
                # Only append if the AI produced a non-empty observation with future relevance.
                if review.observation and len(review.observation) <= 200:
                    note = f"[Step {self.step_id}] {review.observation}"
                    state = state.model_copy(update={
                        "review_notes": state.review_notes + [note]
                    })
                break

        return review
```

Each step's `run_step_N()` in `pipeline_runner.py` is now just:
1. Record `step_start_time = datetime.utcnow()`
2. Emit `step_started` SSE event (step_id, step_name)
3. Execute Layer 1 (`self.execute(state)`)
4. Check Layer 2 hard rules
5. Fetch Supermemory context
6. Call `review = await self.run_with_review_loop(result, state, ai_engineer, book_ctx, past_ctx)`
7. **Append StepRecord** [Eng Review — ownership specified here]:
   ```python
   record = StepRecord(
       step_id=step.step_id, step_name=step.step_name,
       result=result, timestamp=step_start_time,
       duration_ms=int((datetime.utcnow() - step_start_time).total_seconds() * 1000),
       ai_called=step._should_call_ai(state, result),
   )
   state = state.model_copy(update={"step_records": state.step_records + [record]})
   ```
8. Call `await session_store.heartbeat(session_id)` [CEO Review 3 — orphan detection]
9. Save updated state to Redis

### 7.6 Bell-Delaware Public Interface

```python
# hx_engine/app/correlations/bell_delaware.py
def shell_side_h(fluid: FluidProperties, geom: GeometrySpec,
                 baffle_cut: float = 0.25) -> tuple[float, dict]:
    """Returns (h_W_m2K, {J_b, J_c, J_l, J_s, J_r, h_ideal})"""

def shell_side_dP(fluid: FluidProperties, geom: GeometrySpec,
                  baffle_cut: float = 0.25) -> tuple[float, dict]:
    """Returns (dP_Pa, intermediates)"""
```

### 7.7 SSE Event Schemas

```python
# hx_engine/app/models/sse_events.py — All 8 SSE event types
# step_started, step_approved, step_corrected, step_warning,
# step_escalated, step_error, iteration_progress, design_complete
#
# step_error payload: step, message, observation, recommendation, options
# Emitted when a step cannot be resolved after 3 user inputs. Pipeline halts.
# StepHardFailure exception is raised in pipeline_runner after this event.
#
# Note: context_note_ack removed — /btw deferred to post-beta [CEO Review 3]
```

### 7.8 SSE Architecture [Decision 1B + CEO-1A nginx]

```
POST /api/v1/hx/design              → {session_id, stream_url (relative path), token}  [instant, < 100ms]
GET  /api/v1/hx/design/{id}/stream  [EventSource via nginx proxy → HX Engine]
GET  /api/v1/hx/design/{id}/status  [poll fallback, CG2A]
POST /api/v1/hx/design/{id}/respond [user response to ESCALATED step]
```

- `stream_url` is a relative path (not absolute URL with :8100)
- Frontend constructs: `${window.location.origin}${streamUrl}`
- nginx routes `/api/v1/hx/` → HX Engine

### 7.9 Internal Webhook Auth [Decision 3R-1A]

```python
# hx_engine calls backend on design completion:
headers = {"X-Internal-Token": settings.internal_secret}
await http.post(f"{settings.backend_url}/internal/design-complete", headers=headers, json=result)

# backend/app/routers/internal.py — verifies before storing:
if req.headers.get("X-Internal-Token") != settings.internal_secret:
    raise HTTPException(403, "Unauthorized")
```

**Retry [Eng Decision 2]:** If backend returns 500, retry 2× with backoff. If all 3 fail, log CRITICAL; result still retrievable via GET /status for 24h from Redis.

### 7.10 Redis Session Store [Decision 3R-2A]

```python
# hx_engine/app/core/session_store.py
SESSION_TTL_SECONDS = 86400  # 24h

async def save(session_id: str, state: DesignState) -> None:
    await redis.setex(session_id, SESSION_TTL_SECONDS, state.model_dump_json())

# docker-compose.yml — Redis with AOF persistence + healthcheck:
# command: redis-server --appendonly yes
# volumes: - redis-data:/data
# healthcheck:
#   test: ["CMD", "redis-cli", "ping"]
#   interval: 10s
#   timeout: 5s
#   retries: 5
#   start_period: 5s

# docker-compose.yml — HX Engine healthcheck:
# healthcheck:
#   test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
#   interval: 30s
#   timeout: 10s
#   retries: 3
#   start_period: 10s

# docker-compose.yml — Backend healthcheck:
# healthcheck:
#   test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
#   interval: 30s
#   timeout: 10s
#   retries: 3
#   start_period: 10s

# docker-compose.yml — MongoDB healthcheck:
# healthcheck:
#   test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
#   interval: 30s
#   timeout: 10s
#   retries: 5
#   start_period: 30s

# docker-compose.yml — nginx healthcheck:
# healthcheck:
#   test: ["CMD", "curl", "-f", "http://localhost/health"]
#   interval: 30s
#   timeout: 10s
#   retries: 3
#   start_period: 5s

# Note: MongoDB startup healthcheck triggers exponential backoff in lifespan() [CEO Review 3].
# HX Engine depends_on: [redis, mongodb] with condition: service_healthy.
# Backend depends_on: [hx_engine, mongodb] with condition: service_healthy.
```

### 7.11 Parallel Supermemory Calls [Decision 9A] with Safe Wrapper [Decision CEO-4A]

```python
# _safe_memory_call wrapper replaces direct asyncio.gather
async def _safe_memory_call(coro, default=""):
    """Wrap every Supermemory call with 5s timeout and error handling."""
    try:
        return await asyncio.wait_for(coro, timeout=5.0)
    except (TimeoutError, ConnectionError) as e:
        logger.warning(f"Supermemory call failed: {e}")
        return default

# Steps 6, 9, 16 — pattern:
book_ctx, past_ctx = await asyncio.gather(
    _safe_memory_call(memory.search_books(step_6_book_query(state))),
    _safe_memory_call(memory.search_past_designs(step_6_past_query(state)))
)
# Step 16 adds user profile:
book_ctx, past_ctx, profile = await asyncio.gather(
    _safe_memory_call(memory.search_books(...)),
    _safe_memory_call(memory.search_past_designs(...)),
    _safe_memory_call(memory.get_user_profile(state.user_id, ...))
)
```

### 7.12 wait_for_user() Implementation [CEO Review 3]

```python
# hx_engine/app/core/sse_manager.py — escalation future management
_escalation_futures: dict[str, asyncio.Future] = {}

def create_escalation_future(session_id: str) -> asyncio.Future:
    """Called by pipeline when entering wait_for_user()."""
    future = asyncio.get_event_loop().create_future()
    _escalation_futures[session_id] = future
    return future

def resolve_escalation(session_id: str, response: UserResponse) -> None:
    """Called by POST /api/v1/hx/design/{id}/respond handler."""
    future = _escalation_futures.pop(session_id, None)
    if future and not future.done():
        future.set_result(response)

# hx_engine/app/core/pipeline_runner.py — wait_for_user():
async def wait_for_user(session_id: str) -> UserResponse:
    """Waits indefinitely until the user responds via POST /respond.
    No timeout — the pipeline is paused until the engineer makes a deliberate decision.
    waiting_for_user=True excludes this session from orphan detection [CEO Review 3].
    [Eng Review — no-timeout decision: engineering decisions should not be made by default;
     better to wait than to silently apply a conservative assumption the engineer didn't approve.]
    """
    state = await session_store.load(session_id)
    state = state.model_copy(update={"waiting_for_user": True})
    await session_store.save(session_id, state)
    future = sse_manager.create_escalation_future(session_id)
    try:
        return await future  # no timeout — waits until resolve_escalation() is called
    finally:
        state = await session_store.load(session_id)
        state = state.model_copy(update={"waiting_for_user": False})
        await session_store.save(session_id, state)
```

### 7.13 Pipeline Orphan Detection [CEO Review 3]

```python
# hx_engine/app/core/session_store.py — additions
PIPELINE_ORPHAN_THRESHOLD_SECONDS = 120  # in config.py

async def heartbeat(session_id: str) -> None:
    """Called at END of each step completion, after DesignState Redis write, before SSE emit."""
    await redis.hset(f"{session_id}:meta", "last_heartbeat", datetime.utcnow().isoformat())

async def is_orphaned(session_id: str) -> bool:
    """Called by GET /status. Returns True if pipeline appears dead (not waiting for user)."""
    hb = await redis.hget(f"{session_id}:meta", "last_heartbeat")
    if not hb:
        return False  # never heartbeated = just started, not orphaned
    age = (datetime.utcnow() - datetime.fromisoformat(hb.decode())).total_seconds()
    if age <= PIPELINE_ORPHAN_THRESHOLD_SECONDS:
        return False
    # Check if pipeline is intentionally paused waiting for user input
    state = await load(session_id)
    if state and state.waiting_for_user:
        return False  # paused at ESCALATE — not dead
    return True

# GET /status handler addition:
if await session_store.is_orphaned(session_id):
    return {"status": "failed", "message": "Pipeline timeout — please retry."}
```

### 7.14 Connors Pre-filter [Decision 10A]

```python
# hx_engine/app/autoresearch/connors_prefilter.py
def connors_quick_check(state: DesignState) -> bool:
    """~10ms, no AI. Returns False if geometry clearly fails Connors."""
    # Simplified natural frequency + gap velocity estimate
    # Threshold: stability_ratio < 0.8 → reject
```

### 7.13 Frontend Reconnect [CG2A]

```typescript
// frontend/src/hooks/useHXStream.ts
eventSource.onerror = () => {
    eventSource.close();
    const poll = setInterval(async () => {
        const status = await hxEngineApi.getStatus(sessionId);
        if (status.status === 'complete') { clearInterval(poll); setResult(status.result); }
        if (status.status === 'failed')   { clearInterval(poll); setError(); }
    }, 2000);
};
```

### 7.14 engines.yaml [Decision 4A]

```yaml
engines:
  - engine_id: hx_engine
    name: "Shell-and-Tube Heat Exchanger Design Engine"
    base_url: "${HX_ENGINE_URL:-http://localhost:8100}"
    enabled: true
    health_endpoint: "/health"
    tools_endpoint: "/api/v1/hx/tools"
    timeout_seconds: 300
    tools: [hx_design, hx_rate, hx_optimize, hx_get_fluid_properties]
  # Future — just add entries here
  - engine_id: pump_engine
    base_url: "${PUMP_ENGINE_URL:-http://localhost:8101}"
    enabled: false
```

### 7.15 JWT Stream Auth [Decision 3R-6A + CEO-5A]

- POST /design generates short-lived JWT (1hr, HX_ENGINE_SECRET)
- JWT payload includes `user_id` and `session_id` [Decision CEO-5A]
- GET /stream validates JWT: checks signature, expiry, user_id, session_id match
- Unauthorized → 401

---

## 8. Supermemory — Complete Integration

### 8.1 What Supermemory Is (and Is NOT)

> **Supermemory is a storage and retrieval system. It does NOT calculate, does NOT judge, does NOT decide. All intelligence comes from the AI Senior Engineer (Layer 3). Supermemory is the library shelf. Your code is the librarian. The AI is the engineer.**

| Component | Role | Analogy |
|-----------|------|---------|
| **Supermemory** | Stores text, returns search results by meaning | The bookshelf and filing cabinet |
| **Your Code** (pipeline_runner.py) | Builds queries from design_state, calls Supermemory at hardcoded points | The junior engineer who pulls the right book |
| **AI Reviewer** (Layer 3) | Reads search results, compares with calculation, makes judgment | The senior engineer who reads and decides |

**Critical rule:** The AI does NOT call Supermemory. Your code calls Supermemory, builds the query, and passes results INTO the AI's review prompt.

### 8.2 We Do NOT Build RAG

Supermemory IS the RAG infrastructure. We do NOT build:
- Chunking pipeline
- Embedding model deployment
- Vector database (no Pinecone, Qdrant, Weaviate, Chroma)
- Retrieval service
- Document ingestion service

Total code for the entire knowledge layer: ~100 lines.

### 8.3 Three Knowledge Sources

| Source | Stored When | Contents | Retrieved At |
|--------|------------|----------|-------------|
| **Engineering Books** | Once (ingestion script, ~10 min) | 16+ PDFs: Serth, Coulson, Perry's, TEMA, ASME, Kern, Incropera | Steps 4, 8, 9, 13, 16 |
| **Past Designs** | After every completed design (conf ≥ 0.75) | Final summary: fluids, Q, U, geometry, corrections, confidence | Steps 6, 9, 16 |
| **User Profiles** | After every conversation (auto-extracted) | Static facts + dynamic context | Step 1 |

### 8.4 Book Ingestion (run once)

```python
# scripts/ingest_books.py — 15 lines, run once
from supermemory import Supermemory
from pathlib import Path

client = Supermemory()
books = [
    ("serth_process_heat_transfer.pdf", "serth"),
    ("coulson_richardson_vol6.pdf", "coulson"),
    ("perrys_handbook.pdf", "perrys"),
    ("tema_standards_10th.pdf", "tema"),
    ("kern_process_heat_transfer.pdf", "kern"),
    ("incropera_heat_mass_transfer.pdf", "incropera"),
    ("asme_bpvc_section_viii.pdf", "asme"),
]
for filename, tag in books:
    client.documents.upload_file(
        file=Path(f"books/{filename}"),
        container_tags=["engineering_books"],
        metadata={"book": tag}
    )
```

### 8.5 Memory Client Wrapper

```python
# hx_engine/app/memory/supermemory_client.py — ~50 lines
from supermemory import AsyncSupermemory

class MemoryClient:
    def __init__(self):
        self.sm = AsyncSupermemory()

    async def search_books(self, query, limit=5):
        results = await self.sm.search.memories(
            q=query, container_tags=["engineering_books"],
            search_mode="hybrid", limit=limit
        )
        return [r.chunk or r.memory for r in results.results]

    async def search_past_designs(self, query, limit=10):
        results = await self.sm.search.memories(
            q=query, container_tags=["hx_designs"],
            search_mode="memories", limit=limit
        )
        return results.results

    async def get_user_profile(self, user_id, query):
        return await self.sm.profile(container_tag=user_id, q=query)

    async def store_design(self, user_id, run_id, summary, metadata):
        await self.sm.add(
            content=summary,
            container_tags=[user_id, "hx_designs"],
            metadata=metadata,
            custom_id=f"hx-{run_id}"
        )

    async def store_conversation(self, user_id, conversation):
        await self.sm.add(content=conversation, container_tag=user_id)
```

### 8.6 Query Templates (Built from design_state)

| Step | Searches | Query Built From | Example Query |
|------|----------|-----------------|---------------|
| 1 | User profiles | user_id + user message | "crude oil cooling water heat exchanger" |
| 4 | Books | hot_fluid + cold_fluid + delta_T | "TEMA type crude oil water 60C differential" |
| 6 | Past designs | hot_fluid + cold_fluid + duty_kW | "crude oil water U value 6300kW" |
| 8 | Books | cold_fluid + J-factor keywords | "Bell-Delaware J-factor range water shell-side" |
| 9 | Books + Past | hot_fluid + cold_fluid | "overall U crude oil water typical range" |
| 13 | Books | vibration keywords + geometry | "vibration Connors criterion baffle span" |
| 16 | All three | all key parameters | "crude oil water 6300kW U=378 AES validation" |

### 8.7 What Gets Stored After Design

**We store:** Final design summary + key corrections. ONE record per design.

```python
summary = f"""HX Design: {hot_fluid}/{cold_fluid}, Q={duty}kW,
U={U_calc} W/m²K, {tema_type}, {shell_mm}mm shell,
{n_tubes} tubes × {tube_od}mm OD, {pitch_angle}° pitch,
dP_tube={dp_t}kPa, dP_shell={dp_s}kPa, overdesign={od}%,
confidence={conf}.
Corrections: Step 3 viscosity 0.45→0.80 mPa·s (thermo underestimate).
Step 8 baffle clearance 0.8→0.4mm (low J_l). Step 10 spacing 250→275mm
(dP margin <15%)."""
```

**We do NOT store:** Intermediate calculations (Re, Pr, Nu, h_i, individual J-factor values). These are transient — computed fresh each time.

### 8.8 Data Sharing Strategy

- **Books:** Shared with all users. `container_tags=["engineering_books"]`.
- **Past designs (starting phase):** Shared anonymously. `container_tags=["hx_designs"]`. Builds knowledge faster.
- **Past designs (later):** Dual-tagged. `container_tags=[user_id, "hx_designs"]`. Private + shared.
- **User profiles/conversations:** Always private. `container_tag=user_id`.

### 8.9 Learning Over Time

| Designs | Supermemory Returns | Impact |
|---------|-------------------|--------|
| 0 | Book ranges: 300–500 W/m²K | Baseline generic guidance |
| 20 | Books + 8 past designs, avg U=382 | Better seed U, faster convergence |
| 50 | Patterns: "thermo underestimates crude viscosity" | Proactive anomaly catch |
| 100+ | Statistical trends + user preferences | Designs match expectations from start |

---

## 9. Real-Time Event Streaming

### 9.1 Architecture

```
HX Engine (pipeline_runner)
  ├── Step 1 completes → emit SSE event → nginx proxy → Frontend renders
  ├── Step 2 completes → emit SSE event → nginx proxy → Frontend renders
  ├── Step 3 + AI correction → emit SSE event → Frontend shows correction
  ...
  └── Step 16 completes → emit final event → Frontend shows result
                        → webhook POST /internal/design-complete → Backend stores in MongoDB
```

### 9.2 Event Types

| Event | When | Payload |
|-------|------|---------|
| `step_started` | Step begins | step_number, step_name, phase |
| `step_approved` | AI: PROCEED | key_outputs, user_summary, confidence |
| `step_corrected` | AI: CORRECT | parameter, old_value, new_value, reasoning |
| `step_warning` | AI: WARN | concern, impact, user_summary |
| `step_escalated` | AI: ESCALATE or re-escalate | question_for_user, options, observation, recommendation |
| `step_error` | 3 user inputs fail Layer 2 | step, message, observation, recommendation, options |
| `iteration_progress` | Step 12 loop | iteration_number, current_U, constraints_met |
| `design_complete` | All 16 done | final_design_state, confidence, all_events |

### 9.3 SSE Manager

```python
# hx_engine/app/core/sse_manager.py
# asyncio.Queue per session, stream_events() generator
```

---

## 10. HX Engine Microservice

### 10.1 Repository Structure

```
arken-ai/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Chat/            # ChatWindow, MessageBubble, InputBar
│   │   │   └── HXProgress/      # StepCard, IterationBadge, DesignSummary, ParetoChart
│   │   ├── hooks/
│   │   │   ├── useHXStream.ts   # SSE + poll fallback [Decision CG2A]
│   │   │   └── useChat.ts
│   │   ├── services/
│   │   │   ├── backendApi.ts    # calls backend via nginx
│   │   │   └── hxEngineApi.ts   # calls HX Engine via nginx
│   │   └── types/hxEvents.ts    # mirrors sse_events.py
│   ├── package.json
│   └── Dockerfile
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py            # + hx_engine_url [Decision 4A]
│   │   ├── dependencies.py      # + get_engine_registry() [Decision 4A]
│   │   ├── routers/
│   │   │   ├── chat.py
│   │   │   ├── auth.py          # POST /auth/login, GET /auth/me [CEO-CP5]
│   │   │   └── internal.py      # POST /internal/design-complete [3R-1A]
│   │   ├── models/user.py       # User Pydantic model [CEO-CP5]
│   │   ├── core/
│   │   │   ├── engine_client.py # NEW [Decision 4A]
│   │   │   ├── auth.py          # JWT issue/verify, get_current_user [CEO-CP5]
│   │   │   └── password.py      # bcrypt hash/verify [CEO-CP5]
│   │   ├── services/orchestration_service.py  # 3 call sites → engine_registry
│   │   └── scripts/create_user.py  # Admin CLI [CEO-CP5]
│   ├── engines.yaml             # NEW
│   ├── tests/test_orchestration.py  # 5 golden cases [Decision 7A]
│   └── Dockerfile
│
├── hx_engine/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── dependencies.py
│   │   ├── routers/
│   │   │   ├── design.py        # POST /design, GET /design/{id}/status [CG2A]
│   │   │   └── stream.py        # GET /design/{id}/stream (SSE) [Decision 1B]
│   │   ├── models/
│   │   │   ├── design_state.py  # Pydantic DesignState [Decision 2B + CG3A]
│   │   │   ├── step_result.py   # StepResult, AIDecision enum
│   │   │   └── sse_events.py    # All 7 SSE event schemas
│   │   ├── steps/
│   │   │   ├── __init__.py      # StepProtocol [Decision 6A]
│   │   │   ├── base.py          # BaseStep (4-layer template + in_convergence_loop guard)
│   │   │   ├── step_01_requirements.py    through
│   │   │   └── step_16_final_validation.py
│   │   ├── core/
│   │   │   ├── ai_engineer.py   # Layer 3: single Anthropic API call per review + retry [CEO-3A]
│   │   │   ├── review_protocol.py   # Per-step review config: thresholds, triggers, corrections (data-driven)
│   │   │   ├── calibration.py       # Bias correction factors from benchmark comparisons (Serth, etc.)
│   │   │   ├── validation_rules.py  # Layer 2: hard rules (AI cannot override)
│   │   │   ├── pipeline_runner.py   # Runs all 16 steps, manages DesignState
│   │   │   ├── session_store.py     # Redis: save/load DesignState by session_id
│   │   │   ├── sse_manager.py       # asyncio.Queue per session, stream_events()
│   │   │   ├── exceptions.py        # CalculationError(step_id, message, cause)
│   │   │   └── prompts/
│   │   │       └── engineer_review.txt  # AI engineer system prompt + injection mitigation
│   │   ├── correlations/
│   │   │   ├── bell_delaware.py  # shell_side_h(), shell_side_dP() [Decision 5]
│   │   │   ├── kern_method.py    # Kern shell-side h (for cross-validation: deviation < 15%)
│   │   │   ├── gnielinski.py     # tube_side_h()
│   │   │   ├── lmtd.py           # LMTD + F-factor
│   │   │   ├── pressure_drop.py  # Darcy-Weisbach tube-side + Bell-Delaware shell-side dP
│   │   │   ├── vibration.py      # 5 vibration mechanisms (Connors, vortex, acoustic, buffeting, whirling)
│   │   │   ├── connors.py        # connors_criterion() [used in Step 13 + autoresearch pre-filter]
│   │   │   └── turton_cost.py    # cost correlations
│   │   ├── adapters/
│   │   │   ├── thermo_adapter.py  # CoolProp → iapws → thermo, normalizes to SI
│   │   │   ├── ht_adapter.py      # ht library wrapper (correlation cross-checks, extracted from existing 1,110 lines)
│   │   │   └── units_adapter.py   # °F→°C, lb/hr→kg/s, in→m, psi→Pa
│   │   ├── memory/
│   │   │   ├── supermemory_client.py  # search_books(), search_past_designs(), etc.
│   │   │   └── memory_queries.py      # typed query builders per step
│   │   ├── autoresearch/
│   │   │   ├── experiment_runner.py  # 200-variant sweep + Connors pre-filter [10A]
│   │   │   ├── geometry_proposer.py  # Claude proposes next 10 geometries
│   │   │   ├── scorer.py             # Multi-objective scoring (cost, U, dP weighting)
│   │   │   ├── pareto.py             # non-dominated set extraction
│   │   │   ├── connors_prefilter.py  # connors_quick_check() [Decision 10A]
│   │   │   └── program.md            # Autoresearch strategy document (experiment protocol)
│   │   └── data/
│   │       ├── tema_tables.py         # Tube count tables (40+ shell IDs)
│   │       ├── standard_sizes.py      # Standard shell/tube sizes, BWG
│   │       ├── fouling_factors.py     # Fouling resistance by fluid type
│   │       ├── u_assumptions.py       # Typical U ranges by fluid pair
│   │       ├── tube_materials.py      # Material properties, allowable stress
│   │       └── cost_indices.py        # CEPCI_INDEX with last_updated [CEO Amendment]
│   ├── tests/
│   │   ├── unit/
│   │   │   ├── models/test_design_state.py  # CG3A validator tests (12 tests)
│   │   │   ├── correlations/test_bell_delaware.py  # Serth 5.1 benchmark
│   │   │   ├── correlations/test_gnielinski.py
│   │   │   ├── correlations/test_lmtd.py
│   │   │   └── steps/test_step_01.py ... test_step_16.py
│   │   ├── integration/
│   │   │   ├── test_pipeline_e2e.py
│   │   │   ├── test_sse_stream.py
│   │   │   └── test_convergence_loop.py
│   │   └── ai/
│   │       └── test_step08_reproducibility.py  # 10× run, 9/10 same decision [8A]
│   ├── scripts/
│   │   ├── ingest_books.py        # one-time Supermemory book ingestion
│   │   ├── seed_designs.py        # one-time: pre-seed 100–200 synthetic designs from textbook examples
│   │   └── audit_past_designs.py  # quarterly: re-evaluate stored designs, flag > 20% deviation
│   ├── pyproject.toml
│   └── Dockerfile
│
├── docker-compose.yml    # Redis with AOF, nginx reverse proxy [CEO-1A], .env reference
├── nginx.conf            # Routes /api/v1/hx/ → HX Engine, rest → Backend/Frontend
├── .env.example          # All secret placeholders [CEO-2A]
├── .gitignore            # Includes .env
└── scripts/
    └── create_user.py    # Admin CLI for user creation [CEO-CP5]
```

### 10.2 API Endpoints

| Method | Path | Response | Purpose |
|--------|------|----------|---------|
| GET | `/health` | JSON | Health check |
| GET | `/api/v1/hx/tools` | JSON | Tool manifest for auto-discovery |
| POST | `/api/v1/hx/design` | JSON | Trigger design, returns {session_id, stream_url, token} |
| GET | `/api/v1/hx/design/{id}/stream` | SSE stream | Live 16-step events |
| GET | `/api/v1/hx/design/{id}/status` | JSON | Poll fallback [CG2A] |
| POST | `/api/v1/hx/design/{id}/respond` | JSON | Submit user response to ESCALATED step. Body: `{type: "accept"\|"override"\|"skip", values: dict\|null}`. Response 200/404/422. |
| POST | `/api/v1/hx/rate` | SSE stream | Rate existing geometry |
| POST | `/api/v1/hx/properties` | JSON | Fluid property lookup |
| POST | `/api/v1/hx/geometry` | JSON | Suggest initial TEMA type + geometry (heuristics only) |
| POST | `/api/v1/hx/optimize` | SSE stream | Autoresearch optimization |

### 10.3 Dependencies (pyproject.toml — hx_engine)

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.27.0",
    "anthropic>=0.40.0",
    "pydantic>=2.6.0",
    "pydantic-settings>=2.1.0",
    "redis[hiredis]>=5.0.0",
    "motor>=3.3.0",
    "httpx>=0.27.0",
    "sse-starlette>=2.0.0",
    "python-jose[cryptography]>=3.3.0",   # JWT for stream tokens
    "CoolProp>=6.6.0",
    "iapws>=1.5.0",
    "thermo>=0.3.0",
    "ht>=0.2.0",                            # correlation cross-checks (Nusselt, friction factor)
    "fluids>=1.0.0",                        # fluid dynamics utilities (pipe friction, fittings)
    "supermemory>=3.27.0",
]
```

---

## 11. Backend Changes

### 11.0 What Gets Removed (Extraction Plan)

**Entire directories to delete** (after HX Engine is working end-to-end, Checkpoint 6 passed):

| Directory/File | Reason |
|---------------|--------|
| `mcp_process_server/` | MCP server — removed entirely |
| `mcp_calculation_engine_server/` | MCP wrapper — removed entirely |
| `calculation_engine/` | Generic engine — replaced by `hx_engine/` |
| `backend/app/core/mcp_client.py` | Replaced by `engine_client.py` |
| `backend/app/services/tool_registry.py` | Tools auto-discovered from engine manifests |
| `backend/app/models/tool_metadata.py` | Replaced by EngineToolDefinition |
| `backend/app/core/policy_engine.py` | MCP-era policy gating — removed |
| `backend/app/services/context_manager.py` | MCP-era context tracking — removed |
| `backend/app/services/narrative_generator.py` | MCP-era narrative — removed |

**Extract before deleting `calculation_engine/`:**

| Source File | Lines | Destination | Notes |
|-------------|-------|-------------|-------|
| `core/equipment/simple/heat_exchanger.py` | 4,361 | `hx_engine/app/correlations/*.py` + `steps/*.py` | Split monolith into focused modules. Use line 1408+ as Bell-Delaware scaffold. |
| `core/data/hx_reference.py` | ~500 | `hx_engine/app/data/*.py` | Split into tema_tables, fouling_factors, u_assumptions, tube_materials |
| `core/equipment/simple/hx_ht_adapter.py` | 1,110 | `hx_engine/app/adapters/ht_adapter.py` | Remove EquipmentBase dependency, keep ht library wrappers |
| HX-related tests | ~300 | `hx_engine/tests/` | Adapt imports to new module structure |

**Blocking dependency:** `calculation_engine/` code must be extracted to `correlations/*.py` + `steps/*.py` BEFORE Steps 6–9 can be built (Week 3). Do not delete originals until Checkpoint 6 passed.

### 11.1 Replace MCP with Engine Client

**Remove:** `backend/app/core/mcp_client.py`, `backend/app/services/tool_registry.py`, `backend/app/models/tool_metadata.py`
**Create:** `backend/app/core/engine_client.py`

```python
# engine_client.py — replaces mcp_client.py
class EquipmentEngineClient:
    """HTTP client for one engine (httpx.AsyncClient)"""
    async def connect(self):        # GET /health + GET /tools → cache tool list
    async def call_tool(self, tool, args):  # POST to tool.endpoint
    async def call_tool_streaming(self, tool, args):  # POST with SSE response
    async def health_check(self):   # GET /health

class EquipmentEngineRegistry:
    """Manages all engine connections"""
    async def initialize(self, configs):   # Connect all enabled engines
    def list_all_tools(self):              # Merge tools from all engines
    async def call_tool(self, name, args): # Route by tool name
    async def health_check_all(self):      # Check all engines
```

### 11.2 Files to Change

**Status as of 2026-03-26:** MCP is already gone. The backend is a clean FastAPI app (chat, auth, stream). The table below reflects what's already done vs what Week 6 must do.

| File | Status | Week 6 Change |
|------|--------|---------------|
| `app/core/mcp_client.py` | ✅ Already deleted | — |
| `app/services/tool_registry.py` | ✅ Already deleted | — |
| `app/models/tool_metadata.py` | ✅ Already deleted | — |
| `app/core/engine_client.py` | ✅ EXISTS — `HXEngineClient` with `start_design()`, `connect()`, `close()` | Add `rate()`, `get_fluid_properties()`, `poll_status()` |
| `app/config.py` | ✅ Has `hx_engine_url`, `hx_engine_secret` | — |
| `app/dependencies.py` | ✅ Has `get_engine_client()` + `close_engine_client()` | — |
| `app/api/hx.py` | ✅ EXISTS — `POST /api/v1/hx/start` with `min_length=1` validation, returns relative `stream_url` | Do not change — called by tool executor only |
| `app/services/orchestration_service.py` | ⚠️ Plain streaming — no tools yet. Comment says "tools coming" | **Upgrade to agentic loop** — register `hx_design` tool, add tool executor, return `tool_calls` |
| `app/core/llm_provider.py` | ✅ Already has `create_message_stream(tools=...)` support | — |
| `frontend/src/pages/ChatPage.jsx` | ✅ Clean slate — no HX wiring yet | Add `useHXStream`, scan `tool_executions` after chat response, call `connectStream` |
| `frontend/src/components/chat/ChatPanel.jsx` | ✅ Clean — no HX props | Do NOT add `onHXStart` — HX wiring stays in ChatPage only |
| `frontend/src/components/chat/ChatContainer.jsx` | ✅ Clean — no HX props | Do NOT add HX intent detection — LLM is the intent detector |

### 11.3 Auth System [CEO-CP5]

Added in Week 6. All backend endpoints except `/health` and `POST /auth/login` require `Authorization: Bearer <token>`.

- `backend/app/models/user.py` — User Pydantic model: id, email, hashed_password, org_id (nullable), created_at
- `backend/app/routers/auth.py` — POST /auth/login (email + password → JWT), GET /auth/me
- `backend/app/core/auth.py` — JWT issue/verify, `get_current_user` FastAPI dependency
- `backend/app/core/password.py` — bcrypt hash/verify
- `scripts/create_user.py` — Admin CLI: `python scripts/create_user.py --email eng@acme.com --password s3cret`
- No self-service signup for beta. Users created by admin script only.
- Frontend login screen: email + password form, stores JWT in localStorage, adds to all API requests.

---

## 12. Autoresearch — Loop 3

**Status: DEFERRED TO POST-BETA [Eng Review, 2026-03-21]**
Full implementation plan in §20 P2. This section is retained as the design spec for when it's built post-beta.

### 12.1 When It Runs

Only when user explicitly asks for optimization. NOT automatic after every design.

### 12.2 What It Does

Starts from the converged base design (Loop 2 result). Runs Steps 7→11 only (not full 16). Each experiment: ~50–200ms. Total: 200 experiments. Uses ThreadPoolExecutor(max_workers=16) [Decision 3R-3A]. Bell-Delaware is CPU-bound.

**Important [CEO Amendment]:** Experiments run in memory only — no Redis saves during sweep.

### 12.3 The Flow

1. Run 10 heuristic variations (no AI): vary tube passes, tube OD, pitch
2. Show Claude the 10 results + Pareto front
3. Claude proposes 5 targeted experiments
4. Run those 5 (no AI)
5. Show Claude updated Pareto front
6. Repeat until budget exhausted

Claude is called ~5–10 times total, not 200 times.

### 12.4 Geometry Proposer Fallback [Eng Decision 4]

- Claude returns malformed JSON → `_random_perturbations(best, n=10)` called
- Claude returns geometries failing CG3A validation → ValidationError caught, fallback triggered
- Happy path: valid proposals returned → CG3A validates each before use

### 12.5 Pareto Front

- X axis: cost_usd (thousands). Y axis: U_overall_W_m2K. Bubble size: dP_shell_Pa.
- Non-dominated set: minimize cost_usd + dP_shell_Pa, maximize U_overall.
- Only Pareto-dominant results saved (better on at least one metric, worse on none). Not all 200 experiments.

### 12.6 Corner Cases

- All 200 experiments worse than base design — return base design as best
- Pareto front has > 20 designs — cluster and return representative 5–10
- User's constraint changed during optimization — abort and restart
- Optimization finds design that violates vibration (not checked in Steps 7–11) — run Step 13 on Pareto front members before returning
- Claude proposes geometry outside TEMA standard sizes — reject, ask for standard sizes only
- Claude proposes same geometry it already tried — skip duplicate, count against budget
- User cancels mid-optimization — return current Pareto front (partial results). Note: current batch (~16 experiments in ThreadPoolExecutor) finishes before stopping; cancellation is not instant.

---

## 13. Frontend Design Specification

### 13.1 Layout: Split-Panel

```
┌───────────────────────────────────────────────────────────────────┐
│ ARKEN                                          [user@company.com] │
├──────────────────────┬────────────────────────────────────────────┤
│  CHAT  (28% width)   │  HX PROGRESS  (72% width)                  │
│                      │                                            │
│  [message bubbles    │  ► Step 1: Requirements         [✓ 0.3s]  │
│   scroll area]       │  ► Step 2: Heat Duty            [✓ 0.5s]  │
│                      │  ► Step 3: Fluid Properties     [⟳ live] │
│  User message        │    Step 4–16                    [pending] │
│  right-aligned       │                                            │
│                      │  [Iteration badge when Step 12 runs]       │
│  AI message          │                                            │
│  left-aligned        │  [DesignSummary card on completion]        │
│  (reasoning inline)  │                                            │
│                      │                                            │
│  ──────────────────  │                                            │
│  [  Type here...  ]  │                                            │
│  [         ] [Send]  │                                            │
└──────────────────────┴────────────────────────────────────────────┘
```

- Chat panel: 28% width, always visible during streaming. User can type follow-up questions while watching step progress.
- HX Progress panel: 72% width. Top: slim progress bar. Below: StepCards stream in, newest at bottom. Scroll-to-follow.
- Header: wordmark "ARKEN" left, login status right. Single-page app, no routing.
- Empty state (before first design): centered prompt in progress panel — "Describe your heat exchanger problem." + 2 example prompt chips.
- **InputBar disabled when any step is ESCALATED [Decision CEO-6A]** — prevents concurrent input confusion.
- **ChatWindow error state [CEO Frontend Amendment]** — show connection errors gracefully.

### 13.2 Progress Bar

Slim bar at top of HX Progress panel, visible only while a design is running:
```
Step 3 / 16 — Computing fluid properties
████████▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒  18%  est. ~20s
```
- Disappears on completion; DesignSummary card takes its place.
- Time estimate: `(steps_remaining × avg_step_duration)`.

### 13.3 MessageBubble Style (Engineering Terminal Aesthetic)

No rounded bubbles, no avatar icons. Precision terminal aesthetic:
- **User message:** right-aligned block, right-border accent line in `amber-500`.
- **AI response:** left-aligned block, left-border accent line in `blue-500`, starts with `▶ ARKEN —` label in muted text.
- Data values inline (temperatures, flows, coefficients) rendered in JetBrains Mono with backtick-style highlight: `` `342 W/m²K` ``
- No timestamps. No avatars. No hover reactions.

### 13.4 DesignSummary Card (Engineering Data Sheet)

Appears in HX Progress panel after Step 16 completes, above StepCards:
```
┌─ DESIGN COMPLETE ─────────────────────────────────┐
│ Confidence        ████████░░  78%                 │
│   [→ view breakdown]                               │
├───────────────────────────────────────────────────┤
│ U overall       342 W/m²K                         │
│ Area required   48.3 m²   (+18.4% overdesign)     │
│ ΔP shell        0.38 bar  [✓ < 1.4 bar limit]     │
│ ΔP tube         0.21 bar  [✓ < 0.7 bar limit]     │
│ TEMA type       BEM                                │
│ Cost estimate   $42,800                            │
│ Vibration       ✓ Safe                             │
├───────────────────────────────────────────────────┤
│ [↓ Export PDF]               [Optimize for cost →]│
└───────────────────────────────────────────────────┘
```
- All numeric values in JetBrains Mono.
- Confidence score as a filled bar (not a percentage circle).
- **Confidence breakdown expandable [CEO Amendment]** — shows the 4 components.
- Constraint check indicators: `[✓ < limit]` or `[⚠ near limit]` inline.
- "Export PDF" button: deferred to post-beta (disabled, tooltip: "Coming soon").
- "Optimize for cost →" button: deferred to post-beta (disabled, tooltip: "Coming soon — optimization runs 200 design variants"). [Autoresearch deferred — Eng Review]

### 13.5 StepCard Interaction States

Each of the 16 StepCards has 7 states. Implement all 7 before shipping any card:

```
STATE       │ LEFT INDICATOR │ HEADER STYLE   │ BODY                    │ COLOR
────────────┼────────────────┼────────────────┼─────────────────────────┼──────────────
PENDING     │ ○ (hollow)     │ muted text     │ —                       │ gray-400
RUNNING     │ ⟳ (spinning)   │ normal text    │ animated progress bar   │ blue-500
APPROVED    │ ✓ (solid)      │ bold text      │ AI reasoning (collapsed) │ green-600
CORRECTED   │ ↻ (arrows)     │ bold text      │ what changed + why      │ amber-600
WARNING     │ ⚠ (triangle)   │ bold text      │ warning message         │ yellow-500
ESCALATED   │ ? (question)   │ bold + italic  │ question to user + input │ orange-500
ERROR       │ ✗ (cross)      │ bold + strike  │ error message + retry    │ red-600
```

- CORRECTED: shows a diff — "Changed baffle_spacing from 0.20m → 0.15m because J_l was 0.38 (below 0.45 threshold)"
- ESCALATED: renders an inline response input within the card (no separate dialog)
- All states except PENDING show elapsed time in top-right: "[0.8s]"

### 13.6 AI Reasoning Display

- APPROVED cards: reasoning collapsed by default, expandable with "[→ view reasoning]" link
- CORRECTED/WARNING/ESCALATED cards: reasoning visible inline, no collapse (user must see why)
- Max 3 lines before truncation with "…show more"

### 13.7 IterationBadge (Step 12)

When Step 12 is RUNNING, the StepCard body shows:
```
  Convergence iteration  7 / 20
  ████████░░░░░░░░░░░░   ΔU = 2.3%  (target: < 1%)
```
Badge animates each iteration. On converge: "✓ Converged in 9 iterations"

### 13.8 ParetoChart (Autoresearch)

**Status: DEFERRED TO POST-BETA [Eng Review, 2026-03-21]**
Component not built in 7-week beta. "Optimize for cost" button disabled with tooltip. Spec retained for post-beta implementation.

- X axis: cost_usd (thousands). Y axis: U_overall_W_m2K. Bubble size: dP_shell_Pa.
- Hover tooltip: shows all 3 values + geometry spec summary.
- Currently-selected design highlighted in blue. Pareto members in green. Dominated in gray.
- Empty state if < 2 Pareto members: "All variants performed similarly — showing best result."
- **Loading state [CEO Frontend Amendment]** — show spinner during optimization.

### 13.9 Design System

**Typography:**
- UI text: Inter (sans-serif), sizes: 12/14/16/20px
- Data values (temperatures, pressures, U, dP): JetBrains Mono (monospace) — signals precision
- Font weights: 400 (body), 500 (labels), 700 (step names, completion)

**Color Palette (engineering precision):**
- Background: `#0f1117` (near-black)
- Surface: `#1a1d27` (card background)
- Border: `#2a2d3a`
- Text primary: `#e8eaf0`
- Text muted: `#6b7280`
- Status: green `#22c55e`, amber `#f59e0b`, yellow `#eab308`, orange `#f97316`, red `#ef4444`, blue `#3b82f6`

**Spacing:** 4px base grid. Component padding: 16px. Card gap: 8px.

### 13.10 Responsive Behavior

- **Desktop (≥1280px):** Split-panel as above.
- **Tablet (768–1279px):** Chat panel collapses to bottom sheet on tap. Progress fills full width. Chat toggle button in header.
- **Mobile (<768px):** Not a primary target (process engineers work at desks). Show a "best viewed on desktop" banner. Chat still usable, progress cards stack full-width.

### 13.11 Accessibility Baseline

- All StepCards have `role="status"` and `aria-live="polite"` so screen readers announce state changes.
- ESCALATED card input: `aria-label="Respond to step 8 question"`.
- Keyboard: Tab navigates to each expandable card, Enter/Space expands reasoning.
- Color contrast: all status colors on dark surface meet WCAG AA (4.5:1 min).
- Touch targets: Send button ≥ 44×44px. "View reasoning" link ≥ 44px height.

### 13.12 /btw Context Injection

**Status: DEFERRED to post-beta [CEO Review 3, 2026-03-21]**

`/btw` context injection has been removed from the beta build. Root cause: forward-only injection creates designs with internal inconsistency — `confidence_score` does not degrade when notes contradict already-completed steps. Post-beta implementation plan is in §20 P2.

---

## 14. Build Sequence (Week-by-Week)

### Week 1 — Foundation (Day-by-day order matters)

**Day 1 — Contracts (build nothing else until these are right)**
- `hx_engine/app/models/design_state.py` — DesignState + GeometrySpec with CG3A validators + default_factory for lists + `waiting_for_user: bool = False` field [CEO Review 3]
- `hx_engine/app/models/step_result.py` — StepResult, AIDecision enum, AIModeEnum
- `hx_engine/app/models/sse_events.py` — All 8 event types (not 9 — /btw deferred [CEO Review 3])
- `hx_engine/app/steps/__init__.py` — StepProtocol (Decision 6A)
- `frontend/src/types/hxEvents.ts` — Mirror of sse_events.py

**Day 2 — Infrastructure**
- `hx_engine/app/config.py` — pydantic-settings + `PIPELINE_ORPHAN_THRESHOLD_SECONDS = 120` [CEO Review 3]
- `hx_engine/app/core/session_store.py` — Redis save/load DesignState + `heartbeat()` + `is_orphaned()` [CEO Review 3]
- `hx_engine/app/core/sse_manager.py` — asyncio.Queue per session + refcount cleanup + escalation future management [CEO Review 3 §7.12]
- `hx_engine/app/main.py` — FastAPI + /health

**Day 3 — Base step infrastructure**
- `hx_engine/app/steps/base.py` — BaseStep with 4-layer template + Decision 3A guard + AIModeEnum
- `hx_engine/app/core/validation_rules.py` — Framework (rules populated Weeks 2–5)
- `hx_engine/app/core/ai_engineer.py` — With retry logic [Decision CEO-3A] (stub AI in Week 1, real in Week 3)
- `hx_engine/app/core/prompts/engineer_review.txt` — AI engineer system prompt + prompt injection mitigation [CEO Amendment]
- `hx_engine/app/core/exceptions.py` — CalculationError(step_id, message, cause)

**Day 4 — API endpoints**
- `hx_engine/app/routers/design.py` — POST /design → {session_id, stream_url (relative path), token}; GET /design/{id}/status [CG2A] + orphan detection; POST /design/{id}/respond [CEO Review 3 §7.12]
- `hx_engine/app/routers/stream.py` — GET /design/{id}/stream SSE [Decision 1B]
- `hx_engine/app/core/pipeline_runner.py` — Skeleton (runs 0 steps, just scaffolding) + `wait_for_user()` impl [CEO Review 3 §7.12]

**Day 5 — Backend + Frontend + Docker + nginx**
- `backend/app/core/engine_client.py` — Stub (real in Week 6)
- `backend/engines.yaml` — HX engine config
- `backend/app/config.py` — Add hx_engine_url
- Frontend: `npm create vite@latest frontend -- --template react-ts`, install deps
- `docker-compose.yml` — All 5 services wired + nginx + .env reference
- `nginx.conf` — Routes /api/v1/hx/ → HX Engine [Decision CEO-1A]
- `.env.example` — All secret placeholders [Decision CEO-2A]

**Week 1 Tests (must pass before Week 2)**
- `tests/unit/models/test_design_state.py` — 12 tests for CG3A validators (all geometry fields: valid boundary, below-min raises ValueError, above-max raises ValueError, None accepted) + default_factory isolation test
- `tests/unit/test_step_protocol.py` — Protocol compliance check

---

### Week 2 — Steps 1–5 + Adapters

Build adapters FIRST (steps depend on them):

> **Pre-requisite:** Week 1 contracts (DesignState, StepResult, SSE events) must be finalized and passing 12 CG3A validator tests before starting Week 2. Adapter tests depend on FluidProperties schema from Day 1.
- `hx_engine/app/adapters/thermo_adapter.py` — Priority: iapws (water) → CoolProp → thermo. Returns FluidProperties in SI.
- `hx_engine/app/adapters/units_adapter.py` — All unit conversions to SI.
- `hx_engine/app/correlations/lmtd.py` — LMTD, F-factor (Bowman 1940 analytical)

Then steps:
- `step_01_requirements.py` — ai_mode=FULL. Parse raw_request → FluidProperties stubs.
- `step_02_heat_duty.py` — ai_mode=CONDITIONAL. Q = m_dot × cp × ΔT. Validation: Q > 0, < 500 MW.
- `step_03_fluid_props.py` — ai_mode=CONDITIONAL. ThermoAdapter for both fluids at mean T. Trigger AI if Pr outside [0.5, 1000].
- `step_04_tema_geometry.py` — ai_mode=FULL. Rule-based TEMA selection + initial geometry heuristics.
- `step_05_lmtd.py` — ai_mode=CONDITIONAL (F < 0.85). Hard fail F < 0.75 → retry with more passes.

**Week 2 Tests**
- `tests/unit/correlations/test_lmtd.py` — 6 cases incl. temperature cross detection, ΔT1=ΔT2 edge case
- `tests/unit/steps/test_step_02.py` through `test_step_05.py` — execute() + validation + conditional trigger
- `tests/unit/adapters/test_thermo_adapter.py` — Water at 25°C vs NIST
- `tests/integration/test_pipeline_steps_1_5.py` — Steps 1–5 with mock AI (always PROCEED)

---

### Week 3 — Steps 6–9: Bell-Delaware Core (GATE WEEK)

**DO THIS FIRST before Steps 6–9:**
- `hx_engine/app/correlations/bell_delaware.py` — Implement in isolation. Wrap in try/except for CalculationError.
- `tests/unit/correlations/test_bell_delaware.py` — Serth 5.1 benchmark test
- **Note:** Use existing `calculation_engine/core/equipment/simple/heat_exchanger.py:1408` as scaffold — extend J-factor rigour, don't start from scratch.

**Serth Example 5.1 reference geometry (must pass < 5% deviation):**
```
shell_diameter=0.5906m, tube_od=0.01905m, tube_id=0.01575m
tube_length=4.877m, baffle_spacing=0.127m, pitch_ratio=1.333
n_tubes=324, n_passes=2, triangular pitch, baffle_cut=0.25
Shell fluid: water at mean temperature
Expected: h_shell within 5% of Serth textbook answer
Expected: J_b, J_c, J_l each within 10% of Serth values
```

**If Serth validation fails, do not proceed to Steps 6–9. Debug bell_delaware.py first.**

**Bell-Delaware vs Kern auto-conservative rule [Decision 3R-7B, resolved CEO Review 3]:**
Add to `hx_engine/app/core/validation_rules.py` (used in Step 8 Layer 2):
```python
def check_bd_kern_divergence(bd_h: float, kern_h: float) -> AutoCorrectResult | None:
    """If BD/Kern divergence > 20%, return lower value as auto-correction. Layer 2 only."""
    if abs(bd_h - kern_h) / bd_h > 0.20:
        conservative = min(bd_h, kern_h)
        return AutoCorrectResult(
            use_value=conservative,
            reason=f"BD/Kern divergence {abs(bd_h-kern_h)/bd_h*100:.1f}% > 20% — using conservative lower value {conservative:.1f} W/m²K"
        )
    return None
```
Step 8 AI prompt receives both values + the override reason. AI annotates reasoning (which method likely under-predicts and why) — does not override the conservative choice.

Then:
- `hx_engine/app/correlations/gnielinski.py` — tube_side_h (turbulent, laminar, transition blend)
- `step_06_initial_u.py` — asyncio.gather books + past [9A] via _safe_memory_call [CEO-4A]
- `step_07_tube_side_h.py` — ai_mode=CONDITIONAL, convergence-loop aware
- `step_08_shell_side_h.py` — ai_mode=FULL, calls bell_delaware.shell_side_h()
- `step_09_overall_u.py` — ai_mode=FULL, asyncio.gather books + past [9A] via _safe_memory_call. **Calibration correction point [Decision OH-4A]:** After computing U_calculated, query `calibration_records` for CalibrationKey = (fluid_pair, tema_type, shell_diameter_class). If ≥ 5 comparisons exist, apply correction: `U_corrected = U_calculated × (1 - avg_delta_U_pct/100)`. Pass both U_calculated and U_corrected to AI review. AI reasoning shows: "Calibration factor applied: −8.2% from 7 HTRI comparisons (crude_oil/water, BEM, medium)." If < 5 comparisons, proceed without correction and note in AI reasoning.

**Week 3 Tests**
- `tests/ai/test_step08_reproducibility.py` [Decision 8A] — 10× identical Step 8 inputs, assert ≥ 9/10 same decision. Tagged `@pytest.mark.nightly`.
- `tests/unit/correlations/test_gnielinski.py` — 5 cases incl. turbulent water vs Dittus-Boelter crosscheck
- `tests/unit/steps/test_step_07.py` — verify AI skipped when in_convergence_loop=True

---

### Week 4 — Steps 10–12: Pressure Drops + Convergence Loop

- `step_10_pressure_drops.py` — Tube dP (Churchill friction) + bell_delaware.shell_side_dP(). Convergence-loop aware. Hard limits: dP_shell < 1.4 bar, dP_tube < 0.7 bar.
- `step_11_area_overdesign.py` — Overdesign check. Convergence-loop aware. Hard fail: overdesign < 0%.
- `step_12_convergence.py` — CG1A try/finally. Runs Steps 7–11 × max 20 iterations. Emits `iteration_progress` SSE. Convergence criterion: ΔU < 1%.

**Week 4 Tests**
- `tests/integration/test_convergence_loop.py`:
  1. Normal convergence → verify in_convergence_loop=False after
  2. Exception in iteration 5 → verify in_convergence_loop=False (finally works)
  3. 20-iteration limit hit → returns result with warning
  4. Steps 7/10/11 skip AI when in_convergence_loop=True
  5. Non-convergence (oscillating ΔU): 20 iterations hit, WARNING emitted, best result returned
- `tests/unit/steps/test_step_12.py` — try/finally specifically, using mock sub-step that raises on iteration 5

---

### Week 4 End — Pre-Week 5 Task (required before building HTRI parser)

**Before writing `htri_parser.py`:** Obtain 3 sample HTRI CSV exports from the beta engineer (ask during or after a call in Week 4). Validate: (a) column names are consistent across HTRI versions, (b) U_overall, dP_shell, dP_tube are present and labeled clearly, (c) identify any version-specific column name variations. If column names vary: build a column-name mapping table in `htri_parser.py` rather than hardcoded strings. [Decision CEO Review 3 — Open Q3 resolved: CSV first, .xrf post-beta]

---

### Week 5 — Steps 13–16: Vibration, Mechanical, Cost, Final Validation + HTRI Comparison Workflow

> **Trust-Calibration-First insertion [Decision OH-1A]:** The HTRI Comparison workflow (previously deferred to post-beta) is built in Week 5, immediately after the pipeline is complete. Recruit 1–2 beta users with HTRI access before this week. Their comparison runs validate ARKEN's accuracy mid-build, not after launch.

Pre-build:
- `hx_engine/app/correlations/connors.py` — connors_criterion() for Step 13
- `hx_engine/app/correlations/turton_cost.py` — Turton (2013) + CEPCI correction
- `hx_engine/app/data/cost_indices.py` — CEPCI_INDEX = {"value": 816.0, "year": 2026, "last_updated": "2026-03-01"} [CEO Amendment]

Then steps:
- `step_13_vibration.py` — ai_mode=FULL (safety). 5 mechanisms: Connors, vortex shedding, acoustic resonance, turbulent buffeting, jet impingement. Sets vibration_safe.
- `step_14_mechanical.py` — ASME VIII Div. 1 min wall thickness. ai_mode=CONDITIONAL (P > 30 bar).
- `step_15_cost.py` — Turton + CEPCI. ai_mode=CONDITIONAL. Check CEPCI last_updated, warn if > 90 days old.
- `step_16_final_validation.py` — ai_mode=FULL + asyncio.gather all 3 Supermemory sources via _safe_memory_call. CONFIDENCE_WEIGHTS constant (equal 0.25 each) [CEO-7A]. Save to past_designs if score ≥ 0.75.

**HTRI Comparison Workflow (moved from post-beta — [Decision OH-1A]):**
**MongoDB indexes (add at FastAPI lifespan startup, before any endpoint serves traffic) [CEO Review 3]:**
```python
# hx_engine/app/main.py — lifespan startup
await db.calibration_records.create_index(
    [("key", 1), ("archived", 1), ("model_version", 1)]
)
await db.users.create_index([("email", 1)], unique=True)
# Both are idempotent (MongoDB returns immediately if index exists)
# If creation fails: log CRITICAL, exponential backoff 1s/2s/4s, then re-raise → container restart
```

- `hx_engine/app/routers/htri_compare.py` — POST /api/v1/hx/compare endpoint. Request validated by `HTRICompareRequest` Pydantic model with physics-based bounds [OH-5A, Critical Gap B]:
  ```python
  class HTRICompareRequest(BaseModel):
      U_htri:        float = Field(..., gt=50,  lt=2000)  # W/m²K, typical S&T range
      dP_shell_htri: float = Field(..., ge=0,   lt=5.0)   # bar
      dP_tube_htri:  float = Field(..., ge=0,   lt=5.0)   # bar
  ```
  FastAPI returns 422 with field-level errors on invalid values. No bad data reaches the comparator.
- `hx_engine/app/services/htri_parser.py` — **CSV only in Week 5** [Decision CEO Review 3 — Open Q3]. Use `csv.reader()` (stdlib, no extra deps). Extract U_overall, dP_shell, dP_tube by column name (use mapping table from pre-Week 5 sample validation). 2MB file size enforced at endpoint before parser is called. Build after manual entry path is working. `.xrf` XML parser deferred to post-beta; when built, use `defusedxml` library (XXE mitigation).
- `hx_engine/app/services/htri_comparator.py` — Compute deviations (ARKEN vs HTRI): `delta_U = (U_arken - U_htri) / U_htri × 100%`. Store per CalibrationKey in `calibration_records` MongoDB collection [OH-7A]. Do not apply correction factor until ≥ 5 comparisons for that key. On successful store: update in-memory calibration cache [Critical Gap A — startup cache pattern, see below]. **Deviation sanity check before MongoDB write [Critical Gap B — second layer]:**
  ```python
  MAX_ALLOWED_DEVIATION_PCT = 50.0  # >50% means geometry mismatch or bug, not a calibration signal

  delta_U_pct = (U_arken - U_htri) / U_htri * 100

  if abs(delta_U_pct) > MAX_ALLOWED_DEVIATION_PCT:
      raise HTTPException(
          status_code=422,
          detail=f"Deviation {delta_U_pct:.1f}% exceeds 50% — verify inputs or contact support"
      )
  ```
  Pydantic catches format/range errors at the endpoint (layer 1). This check catches semantic errors inside the comparator — both U values in-range individually but deviation implausible, e.g. geometry inputs don't match the HTRI case (layer 2). Neither record reaches MongoDB.
- `hx_engine/app/data/calibration.py` — Calibration cache module. Loaded from MongoDB at HX Engine startup. Step 9 reads from this in-memory dict — MongoDB is never in the critical path during a live design run [Critical Gap A]:
  ```python
  # calibration.py — loaded once at startup, refreshed on each /compare submission
  CURRENT_MODEL_VERSION = "1.0"  # bump when Bell-Delaware implementation changes significantly

  _cache: dict[CalibrationKey, CalibrationRecord] = {}

  async def load_from_mongo(db):
      """Called once at startup via FastAPI lifespan. Populates _cache.
      Only loads active (non-archived) records matching the current model version.
      Archived records and records from prior model versions are excluded — they
      do not contribute to correction factors."""
      records = await db.calibration_records.find({
          "archived": False,
          "model_version": CURRENT_MODEL_VERSION,
      }).to_list(None)
      _cache.update({r["key"]: r for r in records})

  def get(key: CalibrationKey) -> CalibrationRecord | None:
      """Step 9 calls this. Always reads from memory — never hits MongoDB."""
      return _cache.get(key)

  def update(key: CalibrationKey, record: CalibrationRecord):
      """Called by htri_comparator after successful MongoDB write.
      Only called for non-archived records — bad data rejected before this point."""
      _cache[key] = record
  ```
  **Failure behaviour:** If MongoDB is down at startup, `_cache` stays empty → Step 9 proceeds without correction (logs WARNING). MongoDB going down mid-pipeline has zero impact on running designs.

  **CalibrationRecord schema (MongoDB document):**
  ```python
  # CalibrationKey — defined in hx_engine/app/data/calibration.py [Decision OH-6A, Eng Review]
  class CalibrationKey(BaseModel):
      """Compound lookup key for calibration records.
      All fields available from DesignState after Step 4 completes.
      fluid_pair is always sorted (alphabetical) so (crude_oil, water) == (water, crude_oil).
      """
      fluid_pair:           tuple[str, str]  # sorted alphabetically, e.g. ("cooling_water", "crude_oil")
      tema_type:            str              # e.g. "BEM", "BEU", "AES"
      shell_diameter_class: Literal["small", "medium", "large"]
      # small  = shell_diameter_m < 0.5
      # medium = 0.5 <= shell_diameter_m <= 1.0
      # large  = shell_diameter_m > 1.0

      @classmethod
      def from_state(cls, state: "DesignState") -> "CalibrationKey":
          fluids = tuple(sorted([state.shell_fluid.name, state.tube_fluid.name]))
          d = state.geometry.shell_diameter_m or 0
          diam_class = "small" if d < 0.5 else ("large" if d > 1.0 else "medium")
          return cls(fluid_pair=fluids, tema_type=state.tema_type or "unknown",
                     shell_diameter_class=diam_class)

  class CalibrationRecord(BaseModel):
      key:               CalibrationKey
      delta_U_pct:       float
      delta_dP_shell_pct: float
      delta_dP_tube_pct:  float
      comparison_count:  int
      last_updated:      datetime
      model_version:     str = CURRENT_MODEL_VERSION
      archived:          bool = False
      archived_reason:   str | None = None
      archived_at:       datetime | None = None
  ```
  Hard deletion is never used on calibration records. Soft archive (`archived: true`) is set via an admin endpoint when process conditions change or a Bell-Delaware bug fix makes old comparisons unrepresentative. TTL index (30 days) applied only to temporary design session documents, not to calibration records [Decision OH-9A].
- Frontend: HTRI comparison form on DesignSummary card (enabled only after Step 16 completes). Two input modes:
  - **Primary — Manual entry:** `U_htri`, `dP_shell_htri`, `dP_tube_htri` input fields. No file handling. Build this first. Fastest path to first calibration run.
  - **Secondary — File upload:** `.xrf` (XML) or CSV, 2MB hard limit (`File(..., max_size=2_000_000)`). Error message: "Export a single exchanger only — max 2MB." Build after manual entry is working.
  - Both modes show the same deviation table output: U, dP_shell, dP_tube, geometry fields side-by-side.

**Week 5 Tests**
- `tests/unit/correlations/test_connors.py` — safe, unsafe, near-threshold, missing fields
- `tests/unit/steps/test_step_13.py` — all 5 mechanisms; vibration_safe=False if any fails
- `tests/integration/test_pipeline_e2e.py` (first full run with mock AI):
  - Input: crude oil cooling request (fixed)
  - Assert: DesignState populated after Step 16
  - Assert: 0 < confidence_score ≤ 1
  - Assert: confidence_breakdown has 4 keys, CONFIDENCE_WEIGHTS sum to 1.0
  - Assert: all 7 SSE event types emitted, design_complete last
- `tests/unit/services/test_htri_comparator.py` — deviation calculation, calibration record storage, minimum-5-comparisons gate, CalibrationKey compound key construction [OH-6A]; deviation > 50% raises 422 before MongoDB write [Critical Gap B layer 2]; archived records excluded from correction factor; model_version mismatch excludes record from cache load [OH-9A]
- `tests/unit/services/test_htri_parser.py` — **CSV only in Week 5** [CEO Review 3, .xrf deferred]: parse valid CSV with correct columns, missing required column raises ParseError with column name in message, empty CSV (headers only) raises ParseError, file > 2MB rejected before parser called [OH-8A], column name variations handled by mapping table (verify at least 2 variant names map to canonical names)
- `tests/integration/test_htri_compare_e2e.py` — end-to-end: POST /compare (manual entry) → compute deviation → store calibration record → verify MongoDB insert; POST /compare (file upload, valid .xrf) → same; POST /compare before Step 16 complete → 409; invalid token → 401 [OH-5A]
- `tests/unit/steps/test_step_09_calibration.py` — Step 9 with ≥5 calibration records: verify U_corrected applied; Step 9 with <5 records: verify U_calculated used unchanged; Step 9 with no records for key: verify proceeds without correction [OH-4A]

---

### Week 6 — Backend Integration + Frontend SSE Split + Auth

**Architectural decision [2026-03-26]:** The frontend NEVER calls the HX Engine directly or fires a parallel start-design request. The only entry point from the browser is `POST /api/chat`. The backend's Claude (Loop 1) decides whether the message is an HX design request and calls the `hx_design` tool if so. The tool result (session_id + stream_url) comes back in `tool_executions` on the chat response. The frontend reads that field and opens the SSE stream. Intent detection belongs to the LLM, not the frontend.

```
User message
  ↓
POST /api/chat  (single request — same as always)
  ↓
orchestration_service.py — Claude reads conversation + tool list
  Claude decides: calls hx_design({raw_request, user_id})
    ↓
  tool executor: POST /api/v1/hx/start → HX Engine
    ← { session_id, stream_url: "/api/v1/hx/design/{id}/stream" }
  Claude writes response: "Starting your 16-step design..."
  ↓
Chat response:
  { message: "...", tool_executions: [{ tool_name: "hx_design",
    result: { session_id, stream_url } }] }
  ↓
frontend/src/pages/ChatPage.jsx — after chat response received:
  finds tool_executions entry with tool_name === "hx_design"
  calls connectStream(result.stream_url)
  ↓
useHXStream → EventSource → nginx → HX Engine → HXPanel streams live
```

**What this means for the codebase:**
- `ChatPage.jsx` owns HX state (`useHXStream`). After each chat response, it scans `tool_executions` for `hx_design` and calls `connectStream`. No `onHXStart` prop, no parallel fetch, no frontend intent detection.
- `ChatPanel` / `ChatContainer` — no HX awareness at all. They only send chat messages and render responses.
- `backend/app/api/hx.py` — `POST /api/v1/hx/start` stays but is called only by the tool executor inside `orchestration_service.py`, never by the frontend.
- `stream_url` returned as a relative path (`/api/v1/hx/design/{id}/stream`). `useHXStream` prepends `window.location.origin`; nginx routes to HX Engine.

**Auth (CEO-CP5 — add first, everything else depends on it):**
- `backend/app/models/user.py` — User Pydantic model: id, email, hashed_password, org_id (nullable), created_at
- `backend/app/routers/auth.py` — POST /auth/login (email + password → JWT), GET /auth/me
- `backend/app/core/auth.py` — JWT issue/verify, `get_current_user` FastAPI dependency
- `backend/app/core/password.py` — bcrypt hash/verify
- `scripts/create_user.py` — Admin CLI: `python scripts/create_user.py --email eng@acme.com --password s3cret`
- No self-service signup for beta. Users created by admin script only.
- Frontend login screen: email + password form, stores JWT in localStorage, adds to all API requests.
- All backend endpoints except `/health` and `POST /auth/login` require `Authorization: Bearer <token>`.

**Backend:**
- `backend/app/core/engine_client.py` — Full implementation (was stub). HXEngineClient with `start_design()`, `rate()`, `optimize()`, `get_fluid_properties()`, `poll_status()`.
- `backend/app/api/hx.py` — `POST /api/v1/hx/start` endpoint. Called by the tool executor in `orchestration_service.py`. Returns `{ session_id, stream_url (relative path) }`. `raw_request` validated `min_length=1, max_length=5000`. Frontend never calls this directly.
- `backend/app/services/orchestration_service.py` — Upgraded from plain streaming to agentic loop with tool support. Registers `hx_design` (and later `hx_rate`, `hx_get_fluid_properties`) as Claude tools. Tool executor calls `engine_client.start_design()` when Claude invokes `hx_design`. Returns `tool_calls` list in the process_message result so `chat.py` can populate `tool_executions` in the response.
- `backend/app/dependencies.py` — `get_engine_client()` singleton (already exists).
- HX Engine webhook handler: `POST /internal/design-complete` → store result in MongoDB.

**Frontend:**
- `frontend/src/pages/ChatPage.jsx` — Owns `useHXStream`. After every `handleSendMessage` response, checks `response.tool_executions` for `tool_name === "hx_design"`. If found, calls `connectStream(execution.result.stream_url)`. Passes `error` from `useHXStream` to `HXPanel`. No `onHXStart` prop anywhere.
- `frontend/src/hooks/useHXStream.js` — Full SSE + 2s poll fallback [CG2A]. 8 event types. Exposes `error` state for SSE connection failures.
- `frontend/src/components/hx/HXPanel.jsx` — Accepts `error` prop; shows red banner when set.
- `frontend/src/components/hx/StepCard.jsx` — Live step card with status badge + AI reasoning.
- `frontend/src/components/hx/IterationBadge.jsx` — Step 12 convergence progress.
- `frontend/src/components/hx/DesignSummary.jsx` — With confidence_breakdown expandable.

**HX Engine — token security [Decision 3R-6A + CEO-5A]:**
- POST /design generates short-lived JWT (1hr, HX_ENGINE_SECRET). Payload includes user_id + session_id.
- GET /stream validates JWT: signature, expiry, user_id, session_id match. Unauthorized → 401.

**Week 6 Tests**
- `backend/tests/test_orchestration.py` [Decision 7A] — 5 golden cases (VCR cassettes for determinism):
  1. "Design crude oil cooler" → hx_get_fluid_properties → hx_design → tool_executions contains stream_url
  2. "Rate this exchanger [+geometry]" → hx_rate
  3. "Optimize for cost" (after design in session) → hx_optimize
  4. "Water properties at 80°C?" → hx_get_fluid_properties only
  5. "Same as last time but inlet 160°C" → hx_design with profile
- `backend/tests/test_hx_proxy.py` — Unit tests for `POST /api/v1/hx/start`:
  - Valid request → 200 + `{ session_id, stream_url }` where `stream_url` starts with `/api/v1/hx/`
  - Empty `raw_request` → 422 validation error
  - HX Engine unreachable → 502
- `tests/integration/test_sse_stream.py` — httpx AsyncClient, full SSE event sequence + JWT auth cases [Decision 3R-6A]:
  - No token → 401
  - Expired token (1s TTL) → 401
  - Wrong secret → 401
  - Token missing user_id claim → 401
  - Token with mismatched session_id → 401
  - Valid token with correct user_id and session_id → 200 + events

---

### Week 7 — Supermemory Integration

- `hx_engine/app/memory/supermemory_client.py` — search_books(), search_past_designs(), get_user_profile(), save_design(), update_user_profile()
- `hx_engine/app/memory/memory_queries.py` — Query builders for Steps 6, 9, 16
- Wire asyncio.gather calls in Steps 6, 9, 16 to real SupermemoryClient via _safe_memory_call (replace mocks)
- Step 16: save to past_designs if confidence ≥ 0.75
- `hx_engine/scripts/ingest_books.py` — One-time PDF ingestion (Serth, Kern, Perry's, TEMA, ASME VIII)

**Week 7 Tests**
- `tests/unit/memory/test_supermemory_client.py` — Mock HTTP, all 5 methods
- `tests/unit/memory/test_memory_queries.py` — Query string validation
- `tests/integration/test_memory_integration.py` — Sandbox collection, ingest 3 synthetic designs, verify retrieval

---

### Week 8 — DEFERRED (Autoresearch / Loop 3)

**Autoresearch deferred to post-beta [Eng Review, 2026-03-21].** The beta build is 7 weeks. Week 7 (Supermemory) is the final beta week. Full autoresearch implementation plan in §20 P2. See §12 for the design spec.

**Beta build ends at Week 7. Ship checkpoint is Integration Checkpoint 7 (Supermemory live).**

---

## 15. Test Plan

### 15.0 Test Infrastructure (conftest.py) [Eng Review]

Build `tests/conftest.py` in Week 1 Day 2, alongside the infrastructure files. All test files import fixtures from here — no local mock duplication.

```python
# tests/conftest.py

import pytest
from unittest.mock import AsyncMock
import fakeredis.aioredis

@pytest.fixture
def fake_redis():
    """In-memory Redis for all session_store tests. No network, no AOF."""
    return fakeredis.aioredis.FakeRedis()

@pytest.fixture
def mock_mongo():
    """mongomock motor client for calibration_records + users tests."""
    # use mongomock or motor AsyncMock depending on motor version
    ...

@pytest.fixture
def base_design_state():
    """Factory: returns a DesignState with required fields populated for step tests."""
    def _factory(**overrides):
        return DesignState(
            session_id="test-session-001",
            user_id="test-user-001",
            raw_request="Design a crude oil cooler",
            **overrides
        )
    return _factory

@pytest.fixture
def mock_ai_engineer():
    """Configurable AI engineer mock. Default: returns 'proceed' with confidence=0.85.
    Override per-test: mock_ai_engineer.review.return_value = AIReview(decision='correct', ...)
    """
    engineer = AsyncMock()
    engineer.review.return_value = AIReview(
        decision="proceed", confidence=0.85, reasoning="All checks pass."
    )
    return engineer

@pytest.fixture
def mock_supermemory():
    """All 5 Supermemory methods return empty strings (safe default for most tests)."""
    sm = AsyncMock()
    sm.search_books.return_value = ""
    sm.search_past_designs.return_value = ""
    sm.get_user_profile.return_value = ""
    sm.save_design.return_value = None
    sm.update_user_profile.return_value = None
    return sm
```

**Usage contract:** Import these fixtures in any test file that needs them. Never create local `AsyncMock()` versions of the AI engineer or Redis — always use these. This ensures consistent mock behavior across 20+ test files.

### 15.1 Affected Routes/Endpoints (nginx-proxied)

- POST /api/v1/hx/design — trigger design, returns {session_id, stream_url (relative path), token}
- GET /api/v1/hx/design/{session_id}/stream — SSE stream via nginx proxy
- GET /api/v1/hx/design/{session_id}/status — poll fallback when SSE disconnects [CG2A]
- POST /internal/design-complete — HX Engine webhook to backend (X-Internal-Token) [3R-1A]
- POST /api/v1/hx/rate — rate existing geometry
- POST /api/v1/hx/properties — fluid property lookup
- POST /api/v1/hx/optimize — autoresearch optimization [3R-3A]
- GET /health — health check (all 3 services via nginx)
- GET /api/v1/hx/tools — tool discovery endpoint (engine self-describes capabilities)
- POST /api/v1/hx/geometry — geometry suggestion/validation endpoint

### 15.2 Unit Tests (per step)

- Each of 16 step functions with known inputs → expected StepResult
- All input/output fields match Pydantic DesignState schema [Decision 2B]
- StepProtocol compliance: all 16 steps implement execute(DesignState) → StepResult [Decision 6A]
- AIMode enum: AIMode.FULL / CONDITIONAL / NONE — verify typo at import time raises AttributeError
- FluidProperties field validators: Pr in [0.5, 1000], phase in ["liquid", "gas"] [3R-4A]
  - Pr boundary: separate assertions for Pr=0.5 (pass), Pr=0.499 (fail), Pr=1000 (pass), Pr=1001 (fail)
- FluidProperties.name validator: non-empty string required — `FluidProperties(name="")` raises ValidationError
- StepRecord populated correctly after each step: ai_called flag, duration_ms > 0 [3R-5A]
- DesignState default_factory: `DesignState().step_records is not DesignState().step_records` → True

### 15.3 AI Engineer Tests [Decision CEO-3A — retry logic]

- Retry success on 3rd attempt: mock 2 failures then success → verify success returned, call_count == 3
- Retry exhausted: mock always fails → verify AIDecision(action='WARN', ai_called=False)
- Step 8 reproducibility: 10 identical runs → 9/10 same decision @pytest.mark.nightly [Decision 8A]
- PROCEED path: in-range inputs → proceed + confidence
- CORRECT path: low J_l (< 0.45) → correct + parameter change
- WARN path: borderline J_l (0.45–0.55) → warn decision
- ESCALATE path: ambiguous fluid name → escalate + question
- Claude refusal (no tool_use in response) → treated as WARN, ai_called=False
- Rate limit (429) → retried, then WARN after 3 failures
- AI response > 10 seconds: mock asyncio.sleep(11) inside AI call → verify timeout triggers retry [CEO-3A], after 3 timeouts → WARN + proceed with hard rules only

### 15.3b Correction Loop Tests [Decision ENG-1A, ENG-1B, ENG-2A]

**`tests/unit/steps/test_correction_loop.py`** — tests `BaseStep.run_with_review_loop()`:

- Proceed first try: mock AI → 'proceed' (confidence=0.85) → verify `step_approved` emitted, no correction_attempts
- Single correction + re-review: mock AI → 'correct' attempt 1, then 'proceed' → verify `step_corrected` emitted with attempts=[1 entry]
- 3 corrections exhausted [ENG-1A]: mock AI always 'correct' → verify force-escalate on attempt 3, `review.attempts` has 3 entries, `step_escalated` emitted
- **3 corrections exhausted + user response fails Layer 2 [CEO Review 3 gap fix]:** mock correction exhaustion → escalate → mock user response that still fails Layer 2 → verify `step_error` SSE emitted + `StepHardFailure` raised. Confirms the `else` branch in the correction-exhaustion path (not the direct-escalate path).
- Correction + Layer 2 hard fail → rollback: mock correction that causes validation fail → verify `state.shell_id_mm` restored to pre-correction value
- Confidence gate override [ENG-1B]: mock AI returns `decision='correct', confidence=0.65` → verify overridden to `decision='escalate'`, `confidence_gate_triggered=True` logged
- Confidence gate on re-review: mock AI proceed on attempt 1 but confidence=0.65 → verify force escalate even on 'proceed'
- Warn path: mock AI → 'warn' → verify `step_warning` emitted, no `wait_for_user` called
- Direct escalate: mock AI → 'escalate' → verify `wait_for_user` called exactly once
- **review_notes propagation [Eng Review]:** pre-populate `state.review_notes = ["[Step 7] Shell-side Re=650, baffle spacing sensitive"]` before calling `run_with_review_loop()` → verify that `ai_engineer.review()` is called with a `book_context` or `past_designs` string that contains the review note text (or that `_build_prompt()` embeds it — spy on `_build_prompt` if needed). Ensures review_notes reach the AI prompt and aren't silently dropped.

**`tests/unit/steps/test_apply_helpers.py`** — tests helper contracts from §5.7:

- `apply_correction` type='accept': verify `correction.values` written to DesignState fields
- `apply_user_response` type='accept': verify `correction.values` written to state
- `apply_user_response` type='override': verify `user_response.values` written to state (not correction.values)
- `apply_user_response` type='skip': verify state unchanged after call

**`tests/unit/steps/test_user_response_loop.py`** — tests ENG-2A post-escalation flow:

- User response → Layer 2 passes → `ai_engineer.review` called → `step_approved` emitted
- User response → Layer 2 fails → `step_escalated` emitted again (re-escalation 1)
- User response attempt 2 → Layer 2 passes → resolves
- 3 user attempts all fail Layer 2 → `step_error` SSE emitted + `StepHardFailure` raised, pipeline halts

**`tests/unit/models/test_design_state.py`** additions:

- `snapshot_fields(['shell_id_mm'])` returns `{'shell_id_mm': current_value}`
- `restore(snapshot)` after field mutation: original value restored
- `restore(snapshot)` after partial mutation: only snapshotted fields restored, other fields unchanged

### 15.4 Supermemory / _safe_memory_call [Decision CEO-4A]

- Timeout: asyncio.wait_for raises TimeoutError → empty string returned, no exception propagated
- ConnectError: service down → empty string returned, WARNING logged
- Both calls fail simultaneously in asyncio.gather → step proceeds with empty context
- store_design(): confidence ≥ 0.75 stores, < 0.75 does not store
- search_books(): returns results above 0.6 similarity threshold
- search_past_designs(): fluid pair matching — query "crude oil / cooling water" returns designs with same fluid pair ranked first; unrelated pairs (e.g. "steam / ammonia") excluded or ranked below 0.6 threshold
- Supermemory fully down (all 3 gather calls timeout): design completes with empty context, confidence_score reduced vs. same design with Supermemory available (standalone comparison test)

### 15.5 JWT Stream Auth [Decision CEO-5A — user_id in token]

- No token → 401
- Expired token (manufactured with 1s TTL) → 401
- Token signed with wrong secret → 401
- Token missing user_id claim → 401
- Token with mismatched session_id → 401
- Valid token with correct user_id and session_id → 200 + events stream

### 15.6 Internal Webhook Auth [3R-1A]

- Missing X-Internal-Token header → 403
- Wrong token value → 403
- Correct token → 200, result stored in MongoDB

### 15.7 Webhook Retry [Eng Decision 2]

- Backend returns 500 three times → verify CRITICAL log, design still complete in Redis
- Backend down on first call, up on second → verify retry succeeds silently
- All 3 retries fail → result retrievable via GET /status for 24h

### 15.8 Bell-Delaware Accuracy (Week 3 — hard gate)

- Serth Example 5.1: U within 5%, all 5 J-factors within 10%, dP within 10%
- Run against implementation BEFORE wiring into Steps 6–9
- Note: use existing `calculation_engine/core/equipment/simple/heat_exchanger.py:1408` as scaffold
- **Bell-Delaware auto-conservative rule [CEO Review 3 — Decision 3R-7B resolved]:** test `check_bd_kern_divergence()` in isolation: (a) 10% divergence → None returned (no correction); (b) 25% divergence → AutoCorrectResult with `use_value = min(bd_h, kern_h)`; (c) Step 8 integration test: inject mock Kern result 30% below BD result → verify `h_o` in DesignState uses the lower Kern value + reason logged.

**Contingency path [Decision CEO-R-1A]:** If Serth 5.1 U misses ±5% after 3 days of iteration:
1. Activate Kern fallback — use simplified Kern correlation (Kern, *Process Heat Transfer*, 1950) for shell-side h in Step 8. Document the deviation in `bell_delaware.py` with a `# KERN_FALLBACK_ACTIVE` comment.
2. Proceed to Weeks 4-5 with Kern fallback active. Continue debugging Bell-Delaware in parallel as a background track.
3. Escalation: if Bell-Delaware remains unresolved after 3 days, ring-fence a week-long deep dive during Weeks 4-5 (does not block frontend/HTRI comparison work on separate tracks).
4. **Hard gate before Week 7:** Bell-Delaware must be passing ±5% on U before Supermemory integration begins. Note: Autoresearch is deferred to post-beta — the original gate was "before Week 8." Supermemory does not depend on Bell-Delaware accuracy, but the gate still applies: do not proceed past Week 6 with Kern fallback active, as post-beta autoresearch will require accurate shell-side h.
5. Kern fallback is deactivated as soon as Bell-Delaware passes the Serth 5.1 gate.

### 15.9 Validation Rules

- All boundary values: F=0.75 (pass), F=0.74 (fail), velocity=0.5 (pass), velocity=0.499 (fail)
- LMTD edge: ΔT1 = ΔT2 → verify arithmetic mean, no divide-by-zero
- F-factor edge: R = 1.0 → verify L'Hôpital formula branch
- GeometrySpec validators: baffle_spacing_m < 0.05 → ValueError, > 2.0 → ValueError [CG3A]

### 15.10 Convergence Loop (Step 12)

- in_convergence_loop=True: verify Steps 7/10/11 skip conditional AI [Decision 3A]
- Loop terminates in < 20 iterations on standard case
- Exception in iteration 5 → in_convergence_loop=False via finally [CG1A]
- Non-convergence (oscillating ΔU): 20 iterations hit, WARNING emitted, best result returned
- Post-convergence AI review: after Step 12 converges, Steps 13–16 run with ai_mode=FULL (not CONDITIONAL) — verify AI is called in Step 13 and Step 16 even though in_convergence_loop was recently True
- Oscillation damping: mock ΔU that alternates [+5%, −4%, +3%, −2%…] → verify convergence detects damped oscillation and terminates early when amplitude < 1%, not after 20 iterations

### 15.11 Geometry Proposer Fallback [Eng Decision 4] — POST-BETA

**Deferred with autoresearch [Eng Review].** See §12 and §20 P2. Tests written when autoresearch is built.

### 15.12 Autoresearch Parallelism [3R-3A] — POST-BETA

**Deferred with autoresearch [Eng Review].** Note for post-beta: measure single Bell-Delaware + Gnielinski + dP call time before choosing ThreadPoolExecutor vs ProcessPoolExecutor. If pure Python math, ProcessPoolExecutor(8) for true CPU parallelism. See §20 P2.

### 15.13 Loop 1 Orchestration Regression [Decision 7A]

- "Design a crude oil cooler" → hx_get_fluid_properties → hx_design
- "Rate this existing exchanger [with geometry]" → hx_rate (not hx_design)
- "Optimize for cost" → hx_optimize (only after design exists in session)
- "What fluid properties does ethylene glycol have?" → hx_get_fluid_properties only
- "Same as last time but hotter inlet" → hx_design with Supermemory profile fetch

### 15.14 Confidence Breakdown [CEO scope accepted]

- Step 16 populates all 4 keys: geometry_convergence, ai_agreement_rate, supermemory_similarity, validation_passes — all floats in [0.0, 1.0]
- CONFIDENCE_WEIGHTS sum to 1.0
- confidence_score == weighted sum of breakdown × weights (equal 0.25 each)
- confidence_score ∈ [0.0, 1.0] always

### 15.15 Redis / Session Store

- Keys expire after 24h (verify setex TTL)
- Key still present after 23h
- Redis connection lost mid-save → logged, pipeline continues
- AOF file written in docker volume (verify redis-data volume exists after restart)

**Orphan detection [CEO Review 3 + Eng Review]:**
- `is_orphaned()` — heartbeat < 120s ago → False
- `is_orphaned()` — heartbeat > 120s ago, `waiting_for_user=False` → True (normal orphan case)
- `is_orphaned()` — heartbeat > 200s ago, `waiting_for_user=True` → **False** (ESCALATED pipeline must NOT be marked dead; this is the critical regression guard)
- `is_orphaned()` — no heartbeat at all → False (just started, not orphaned)
- `heartbeat()` — updates `{session_id}:meta` key; verify TTL matches session TTL so both expire together

### 15.16 stream_url Format [Decision CEO-1A]

- POST /design returns stream_url as relative path string (not absolute URL with :8100)
- Frontend: `${window.location.origin}${streamUrl}` constructs valid EventSource URL
- nginx routes /api/v1/hx/ → HX Engine successfully

### 15.17 Edge Cases

- User disconnects mid-design: HX Engine completes, result stored for retrieval via poll
- Fluid not in thermo library: graceful error, suggest similar fluid
- Q = 0 (identical temps): reject at Step 2 with clear message
- F < 0.75 after shell pass increment: escalate, cannot resolve
- Step 12 doesn't converge in 20 iterations: return best result with convergence warning
- AI returns unknown decision type: treat as "proceed", log error
- Redis TTL expired mid-session: SSE stream → 404 on status poll, client shows error
- Internal webhook with missing/wrong token → 403, result not stored

### 15.18 Critical Paths (end-to-end must work)

1. Frontend → POST /design (nginx) → session_id + relative stream_url → EventSource → 16 steps → design_complete
2. Standard crude oil / cooling water design: convergence in < 25s, all events received
3. ~~Full autoresearch: 200 experiments in < 30s, Pareto front, vibration check on winners~~ **POST-BETA (deferred)**
4. Failed AI review with fallback: AI down → WARN cards → design completes with reduced confidence
5. SSE disconnect → poll fallback → reconnect on completion [CG2A]
6. Internal webhook failure → 3 retries → CRITICAL log → result retrievable via GET /status
7. Supermemory down → all 3 gather calls timeout in 5s → design completes with empty context
8. SSE event-order verification: record all SSE events in order → assert `step_started(N)` before any terminal event for step N (`step_approved`/`step_corrected`/`step_warning`/`step_escalated`/`step_error`), all 16 steps present in order, `design_complete` is the final event, no terminal event for step N without a preceding `step_started(N)` [regression test; note: `step_started` is emitted by `pipeline_runner.py` before each step's execute(), not inside BaseStep]
9. Webhook happy path (full flow): HX Engine completes Step 16 → POST /internal/design-complete with X-Internal-Token → Backend stores result in MongoDB → GET /api/v1/hx/design/{session_id}/status returns complete result with all 16 step records

---

## 16. Benchmark Validation Points (Hard Gates)

### Gate 1 — Week 3 Day 1: Serth Example 5.1 (Bell-Delaware)
Do not proceed to Steps 6–9 until all pass:
- h_shell within 5% of textbook answer
- J_b, J_c, J_l each within 10%
- dP_shell within 10%

### Gate 2 — Week 3: Gnielinski
- Turbulent water (Re=50000, Pr=7): Nu within 2% of analytical

### Gate 3 — Week 2: LMTD
- Counter-current equal ΔT: LMTD = ΔT (exact)
- Temperature cross: F < 1.0 and detectable

### Gate 4 — Week 5 End-to-End Envelope Check (crude oil cooling)
Input: 50 kg/s crude oil, 150°C → 90°C, cooling water at 30°C
Expected envelope:
- Q ≈ 6–7 MW
- shell_diameter: 0.6–1.2 m
- U_overall: 200–400 W/m²K
- overdesign: 10–25%
- confidence_score ≥ 0.70

### Integration Checkpoints

| Checkpoint | When | Pass Criteria |
|---|---|---|
| 1 | End Week 1 | All 3 services start, /health 200, docker-compose clean, 12 validator tests pass |
| 2 | End Week 2 | Steps 1–5 run with mock AI; water properties within 1% of NIST |
| 3 (GATE) | End Week 3 | Serth 5.1 within 5%; Step 8 reproducibility ≥ 9/10 |
| 4 | End Week 4 | Convergence loop: standard case converges ≤ 15 iterations; CG1A try/finally verified |
| 5 | End Week 5 | All 16 steps complete; crude oil design envelope check passes; all 7 SSE types emitted |
| 6 (SYSTEM) | End Week 6 | Frontend types → Backend Loop 1 → HX Engine 16 steps → live StepCards; 5 orchestration tests pass |
| 7 | End Week 7 | Supermemory book context returned; past design saved after Step 16; user profile non-empty |
| 8 (POST-BETA) | End Week 8 | **Deferred.** Autoresearch / Loop 3. See §20 P2. |

### Benchmark Targets Summary

| Benchmark | Target | Measured Against |
|-----------|--------|-----------------|
| Serth Example 5.1 U value | Within 5% | Published textbook |
| Serth Example 5.1 dP (both sides) | Within 10% | Published textbook |
| All 5 J-factors vs Serth | Within 10% each | Published textbook |
| Design from scratch convergence | < 20 iterations | Iteration count |
| Full design wall time (with AI) | < 30 seconds | Wall clock |
| Step event latency | < 500ms per event | Frontend timestamp delta |
| Optimization (200 experiments) | < 30 seconds | Wall clock |
| AI review reproducibility | > 90% same decision | 10 identical runs |

---

## 17. Drawback Mitigations

### 17.1 AI Inconsistency → Data-Driven Review Protocol

**Problem:** Same inputs can produce different AI decisions.
**Solution:** `review_protocol.py` defines explicit thresholds. Your code checks thresholds BEFORE calling AI. AI confirms corrections, doesn't decide them.

```python
STEP_8_CHECKS = {
    "J_l": {"warn_below": 0.55, "correct_below": 0.45},
    "J_b": {"warn_below": 0.60, "correct_below": 0.50},
    "h_o_range": {"min": 100, "max": 5000},
}
```

80% of decisions become perfectly reproducible (rule-based). AI handles only the 20% that genuinely needs judgment.

### 17.2 Lost Context → Review Notes Field

**Problem:** Each AI call is stateless. Earlier observations lost.
**Solution:** `review_notes: List[str]` in `DesignState` (added to §7.3). After each step's AI review, `run_with_review_loop()` appends the AI's observation (≤200 chars) as `"[Step N] {observation}"`. Passed to subsequent steps in the AI prompt context. Distinct from `warnings` (Layer 2 hard-rule violations). Example: `"[Step 8] Shell-side Re=650. Step 10 dP sensitive to baffle spacing."` — Step 10 AI receives this as additional context. [Wired in §7.5, Eng Review]

### 17.3 Accuracy Ceiling → Multi-Layer Calibration

**Problem:** Open-literature correlations may have systematic bias.
**Solution:**
1. **Cross-method:** Run Kern parallel with Bell-Delaware. Flag if deviation > 20%.
2. **Calibration factors:** Run 20–50 textbook examples, compute bias per correlation. Store in `calibration.py`.
3. **HTRI comparison:** Let users upload HTRI results. Accumulate correction factors per fluid pair. (Post-beta — see Section 20.)

### 17.4 Cold Start → Seed Design Database

**Problem:** First 10–20 designs have no past data.
**Solution:** Pre-seed with 100–200 synthetic designs from textbook examples. `scripts/seed_designs.py`.

### 17.5 Garbage In → Confidence-Gated Storage + Audit

**Problem:** Incorrect designs pollute Supermemory.
**Solution:**
1. Only store designs with confidence ≥ 0.75
2. Store confidence as metadata, AI weights results accordingly
3. Quarterly audit: re-evaluate old designs, flag > 20% deviation

### 17.6 Phase Change → Same Pipeline, Different Internals

**Problem:** Condensers/reboilers need different correlations.
**Solution:** Step functions dispatch based on `service_type`. Pipeline stays identical.

### 17.7 Prompt Quality → Data-Driven Prompt Builder

**Problem:** Bad prompts = bad reviews.
**Solution:** `review_protocol.py` defines checks declaratively. Prompt builder constructs AI prompt automatically from protocol. Engineering expert edits the dict, not prose.

---

## 18. Corner Cases & Edge Conditions

### 18.1 API and Infrastructure Failures

| Failure | Behavior | User Impact |
|---------|----------|-------------|
| Anthropic API down | Retry 2× [CEO-3A], then WARN+proceed (ai_called=False) | Design completes but with reduced confidence. Flag: "AI review unavailable, manual review recommended." |
| Supermemory API down | _safe_memory_call timeout 5s [CEO-4A], returns empty | AI reviewer falls back to training knowledge. Flag: "Reference data unavailable." |
| HX Engine crashes mid-design | Backend receives HTTP error | "Design calculation failed at Step N. Please retry." |
| Step 12 doesn't converge | After 20 iterations, return best result | Flag: "Did not fully converge. Best result shown. Consider different TEMA type." |
| User disconnects during design | Design continues, result stored | User can retrieve result from conversation history on reconnect |
| Redis down mid-pipeline | Catch ConnectionError, emit warning SSE, continue in memory | "Download your results now — session may not be recoverable" |
| Internal webhook fails 3× | CRITICAL log, result in Redis for 24h | Retrievable via GET /status |
| MongoDB down at startup | Exponential backoff 1s/2s/4s, then CRITICAL + re-raise → container restart via healthcheck | Container restart (5 services, calibration cache empty but safe — Step 9 proceeds without correction) |
| MongoDB down during session | /auth/login + all protected endpoints return 503. Running pipelines continue (Redis only). Calibration cache (loaded at startup) still works from memory. | 503 on new logins; active sessions unaffected. |
| Pipeline orphan (HX Engine OOM mid-pipeline) | GET /status after 120s of no heartbeat + `waiting_for_user=False` → returns `{"status": "failed"}` | "Pipeline timeout — please retry." |

### 18.2 Input Edge Cases

| Input | Handling |
|-------|----------|
| Same fluid both sides (water/water) | Valid — common in HVAC. Process normally. |
| Very high viscosity (> 100 mPa·s) | Laminar flow likely. Warn about poor heat transfer. Consider enhanced tubes. |
| Very low flow rate (< 0.1 kg/s) | Tiny exchanger. May not be practical as shell-and-tube. Suggest plate HX. |
| Very high flow rate (> 500 kg/s) | Multiple shells likely needed. Flag in Step 6. |
| Temperatures in different units | Detect and convert. Always work in SI internally. |
| Negative gauge pressure (vacuum) | External pressure on tubes. Different ASME formula. |
| Supercritical fluid | Properties change dramatically. CoolProp handles but warn about uncertainty. |
| User specifies impossible conditions (T_cold_out > T_hot_in) | Reject at Step 2 with clear explanation. |
| User specifies 0 flow rate on one side | Reject at Step 1 — cannot design without flow on both sides. |

### 18.3 Calculation Edge Cases

| Case | Handling |
|------|----------|
| LMTD formula ΔT1 = ΔT2 | Use arithmetic mean (L'Hôpital's rule). Both code and tests must handle this. |
| F-factor formula R = 1.0 | Special case — simplified formula. Must detect and use alternate expression. |
| Re exactly 2300 or 10000 | Transition boundary. Use blending function, not if/else discontinuity. |
| Tube count not in TEMA table | Interpolate between nearest entries. Never extrapolate beyond table range. |
| Zero fouling factor | Valid (clean service). R_f = 0 means no fouling resistance in series sum. |
| Wall conductivity very high (copper: 385 W/mK) | Wall resistance ≈ 0%. Valid but unusual for process HX. |
| Shell diameter < smallest in tube count table | Design is too small for standard S&T. Suggest hairpin or plate. |
| Degenerate geometry in autoresearch (n_tubes=0) | CalculationError caught, experiment skipped [CalculationError wrapper] |

### 18.4 AI Review Edge Cases

| Case | Handling |
|------|----------|
| AI returns invalid JSON | Retry 2× [CEO-3A]. If still invalid, proceed with hard rules only. Log error. |
| AI returns decision not in {proceed, correct, warn, escalate} | Treat as "proceed" with warning logged. |
| AI suggests correction that violates hard rules | Reject correction. Proceed without it. |
| AI takes > 10 seconds to respond | Timeout → retry [CEO-3A]. After 3 attempts, proceed with hard rules. |
| AI suggests correcting a parameter that doesn't exist | Ignore correction. Log error. Proceed. |
| AI confidence < 0.70 | Confidence gate triggered [Decision ENG-1B]. Override decision to `escalate` regardless of what AI returned. Log `confidence_gate_triggered=True`. |
| User doesn't respond to escalation | Pipeline waits indefinitely (`waiting_for_user=True`). No timeout — engineering decisions require deliberate input. Session excluded from orphan detection while waiting. Resume when user submits via POST /respond. [Eng Review] |
| Layer 2 still fails after user response (re-escalation) | Re-escalate to user with same observation + recommendation + options (up to 2 more times). After 3 total user attempts, emit `step_error` and raise `StepHardFailure` — pipeline halts. |

### 18.5 Supermemory Edge Cases

| Case | Handling |
|------|----------|
| Search returns 0 results | Proceed without context. AI reviewer relies on training knowledge. |
| Search returns irrelevant results (low similarity) | Filter by similarity threshold (> 0.6). Pass only relevant results to AI. |
| Past design data contradicts book data | Pass both to AI. Let AI weigh them. Note: past designs may be more accurate for specific conditions. |
| User profile contains contradictory facts | Supermemory handles contradiction resolution automatically ("moved to SF" supersedes "lives in NYC"). |
| Stored design later found to be incorrect | Quarterly audit script flags it. Manual review and delete/downgrade. |
| Book PDF has poor OCR quality | Some chunks will be garbled. Retrieval quality degrades for that book. Re-upload with better scan. |

### 18.6 Autoresearch Edge Cases

| Case | Handling |
|------|----------|
| All 200 experiments worse than base | Return base design as optimal. |
| Pareto front has > 20 members | Cluster by similarity, return representative 5–10. |
| Optimization violates constraint not checked in Steps 7–11 | Run Step 13 (vibration) on all Pareto front members before returning. |
| Claude proposes geometry outside TEMA standard sizes | Reject proposal. Ask Claude to use standard sizes only. |
| Claude proposes same geometry it already tried | Skip duplicate. Count against budget. |
| User cancels mid-optimization | Return current Pareto front (partial results). |
| Claude returns malformed proposals | Fallback to _random_perturbations(best, n=10) [Eng Decision 4]. |

---

## 19. Extensibility

### 19.1 Adding New Equipment Types

1. Create microservice following `hx_engine/` pattern
2. Add entry to `engines.yaml`
3. Start service + restart backend
4. No backend code changes — tools auto-discovered

### 19.2 Engine Contract

Every engine must implement:
```
GET  /health              → {"status": "ok", "engine": "...", "version": "..."}
GET  /api/v1/{prefix}/tools → {"engine_id": "...", "tools": [...]}
POST /api/v1/{prefix}/{action} → JSON or SSE stream
```

### 19.3 Tool Naming Convention

- HX: `hx_design`, `hx_rate`, `hx_get_fluid_properties`, `hx_suggest_geometry`, `hx_optimize`
- Pump: `pump_design`, `pump_rate`, `pump_curve_lookup`
- Distillation: `distillation_design`, `distillation_rate`

---

## 20. Post-Development & Deferred Items

Items flagged during CEO review, eng review, and development planning that are **not** part of the 8-week build but must be addressed before or after launch.

### P1 — Before Public Launch

#### JWT httpOnly Cookie Migration
**What:** Migrate frontend JWT storage from `localStorage` to an `httpOnly` cookie set by the backend on `POST /auth/login`. The browser never reads the cookie via JavaScript — it's sent automatically on each request.
**Why:** `localStorage` is readable by any JavaScript on the page, including third-party scripts and XSS payloads. An `httpOnly` cookie is immune to XSS token theft. For beta with 5 trusted engineers this is acceptable risk; for public launch it is not.
**Depends on:** Week 6 JWT auth complete.
**Context:** Backend: `response.set_cookie('access_token', token, httponly=True, secure=True, samesite='lax')`. Frontend: remove `Authorization: Bearer` header injection, rely on cookie. All backend endpoints check cookie OR header during transition period.

#### Regulatory / Liability Stance
**What:** One-page internal document clarifying ARKEN's position on liability when designs are used in fabricated equipment. Determines disclaimer language and product positioning.
**Why:** Process engineers stamp and seal drawings. If ARKEN-designed equipment fails in service, the company needs a clear, intentional position. Decision needed before first paying customer.
**Depends on:** Legal counsel.
**Context:** If "decision support," results labeled "FOR REVIEW ONLY — verify with licensed engineer" and confidence score is a suggestion. If "fabrication-ready," higher accuracy bar with different exposure. This decision affects Step 16 output formatting, marketing, UX copy.

#### Pricing Model Decision
**What:** Decide the pricing model before building billing: usage-based (per design run), monthly seat, or annual seat.
**Why:** The auth layer (Week 6) will need billing hooks. Usage-based requires `design_count` field in user document + check in Step 16. Seat license requires `subscription_active` check at login.
**Depends on:** Ideally one conversation with a potential customer.
**Context:** For beta: "free for beta, decide before first paid user." Auth layer should support any model (add a subscription check function that returns True for all users in beta).
**Consequence if deferred past Week 6:** The auth layer ships without billing hooks. Retrofitting requires modifying the `get_current_user` dependency and every endpoint that checks subscription status. Cost: ~2 days rework. Acceptable for beta but creates tech debt.

### P2 — Post-Beta

#### HTRI Comparison Workflow
**Status: MOVED TO WEEK 5 [Decision OH-1A, 2026-03-19]**
**Why moved:** Originally deferred as post-beta. Office Hours session identified this as the single most important trust-building mechanism. Moving it to Week 5 means accuracy is validated by real engineers mid-build, not after launch. See §14 Week 5 for full implementation details.
**What remains post-beta:** Calibration factor dashboard (deviation trend over time). After ≥ 5 comparisons per fluid pair, correction factors are automatically applied in `calibration.py`.

#### PDF Export Report
**What:** "Export PDF" button on the DesignSummary card that generates a formatted engineering report: all 16 step outputs, AI reasoning, final geometry spec, confidence justification, disclaimer footer.
**Why:** Process engineers need to share designs with their team and file them in project records. A plain screen is not a deliverable.
**Depends on:** Step 16 complete (Week 5). Use `weasyprint` or `reportlab`.
**Details:** Font: use a serif body font (e.g. Noto Serif) for print readability, monospace for data tables. PDF bookmarks for each of the 16 steps so engineers can jump directly to a section. Footer: ARKEN logo + disclaimer + confidence_score + date. Page size: A4 (international standard for engineering docs).

#### CI/CD Pipeline
**What:** GitHub Actions CI with two jobs: (1) unit tests on every push, (2) nightly job running `@pytest.mark.nightly` tests (Step 8 AI reproducibility, Serth 5.1).
**Why:** Without CI, the Serth 5.1 hard gate is only enforced when someone remembers to run pytest manually.
**Depends on:** Week 1 complete.
**Priority:** Add before Week 3 Bell-Delaware gate.
**Commands:**
```bash
# Job 1 — on every push (fast, no AI calls)
pytest hx_engine/tests/ -m "not nightly" --tb=short -q
# Job 2 — nightly (requires ANTHROPIC_API_KEY secret)
pytest hx_engine/tests/ -m nightly --tb=long -v
```

#### TypeScript Type Generation from Pydantic Models
**What:** Auto-generate `frontend/src/types/hxEvents.ts` from `hx_engine/app/models/sse_events.py` using `datamodel-codegen` or `pydantic2ts`.
**Why:** `hxEvents.ts` manually mirrors `sse_events.py`. Every schema change must be updated by hand. Drift is silent.
**Depends on:** `sse_events.py` finalized (Day 1, Week 1). Run setup before Week 6.
**Command:**
```bash
# Using datamodel-codegen (preferred — handles Pydantic v2 natively)
datamodel-codegen --input hx_engine/app/models/sse_events.py --output frontend/src/types/hxEvents.ts --output-model-type typescript
# Add to pre-commit or CI to catch drift
```

#### Delete Decommissioned Code
**What:** Remove all MCP-era code: `mcp_calculation_engine_server/`, `mcp_process_server/`, `calculation_engine/` (sugar/adsorption/distillation modules), `backend/app/core/policy_engine.py`, `backend/app/services/context_manager.py`, `backend/app/services/narrative_generator.py`.
**Why:** Dead code accumulates confusion.
**Depends on:** Week 8 Checkpoint 6 passed (full system working). Run pytest after deletion.

#### Bell-Delaware CalculationError Wrapper
**What:** Add `CalculationError(step_id, message, cause)` exception class. Wrap `bell_delaware.shell_side_h()` and `shell_side_dP()` in try/except for ZeroDivisionError and ValueError from degenerate geometry inputs.
**Why:** CG3A validators prevent most degenerate geometries, but autoresearch proposes 200 variants including edge cases.
**Priority:** Build inline with Week 3 Bell-Delaware implementation.
**Test guidance:** Unit test with degenerate inputs (n_tubes=0, baffle_spacing=0, tube_od=tube_id) → verify CalculationError raised with correct step_id. Integration test in autoresearch: inject 1 degenerate geometry in 20 → verify it’s caught and excluded, other 19 complete.

#### Redis Mid-Pipeline Save Failure Handling
**What:** If Redis goes down mid-pipeline, emit WARN SSE event so user knows reconnect won't work. Catch `redis.ConnectionError` in `session_store.save()`.
**Why:** Without the WARN, user sees design_complete but gets 404 on reconnect.
**Priority:** Add after Week 2 infrastructure complete.
**Test methodology:** Use `fakeredis` or mock `session_store.save()` to raise `redis.ConnectionError` at Step 8. Verify: (1) WARN SSE event emitted with message containing "session may not be recoverable", (2) pipeline continues to Step 16, (3) design_complete event still fires.

#### CEPCI Index Maintenance
**What:** Staleness warning when CEPCI `last_updated` > 90 days old. Config constant in `data/cost_indices.py`.
**Why:** A 2-year-old index underestimates cost by 10–20%.
**Priority:** Build inline with Step 15 (Week 5). Update takes 2 minutes per quarter.
**Source:** Chemical Engineering Plant Cost Index, published monthly in _Chemical Engineering_ magazine. Use official annual average. 2025 estimate: ~816. Fallback: interpolate from last 3 years if current year unavailable.

#### Autoresearch — Loop 3 [Eng Review — Deferred from Beta]
**Status: Post-beta [Eng Review, 2026-03-21]**
**Why deferred:** Core value is Loop 2 accuracy. Autoresearch adds optimization on top — only useful once engineers trust the base calculation (validated via HTRI comparison in Week 5). GIL/parallelism question also deferred until we have real Bell-Delaware timing data.

**Build sequence when ready:**
1. Measure a single Bell-Delaware + Gnielinski + dP calculation time on target hardware. If > 30ms, use `ProcessPoolExecutor(8)` for true CPU parallelism (not ThreadPoolExecutor). If < 30ms, ThreadPoolExecutor or sequential is fine (200 × 30ms = 6s).
2. `hx_engine/app/correlations/connors_prefilter.py` — `connors_quick_check()`: simplified natural frequency + gap velocity, ~10ms, returns False if stability_ratio < 0.8. Pre-screen variants before running full Steps 7–11.
3. `hx_engine/app/autoresearch/experiment_runner.py` — 200-variant sweep. Per variant: validate CG3A, run connors_quick_check(), run Steps 7–11 (no AI). Memory only — no Redis saves during sweep.
4. `hx_engine/app/autoresearch/geometry_proposer.py` — Claude analyzes 10 results, proposes 10 new GeometrySpecs. CG3A validates all proposals. Fallback: `_random_perturbations(best, n=10)`.
5. `hx_engine/app/autoresearch/pareto.py` — Non-dominated set: minimize cost_usd + dP_shell_Pa, maximize U_overall. If > 20 Pareto members, cluster to 5–10 representatives.
6. Run Step 13 (vibration) on all Pareto front members before returning — autoresearch only runs Steps 7–11, not 13.
7. `POST /api/v1/hx/optimize` endpoint + `frontend/src/components/HXProgress/ParetoChart.tsx`

**Tests:** §15.11, §15.12 (marked post-beta) — activate when building.
**Effort:** M (human: ~1 week / CC: ~3 hours)
**Depends on:** Beta complete + HTRI comparison validation showing Loop 2 accuracy is trusted.

#### /btw Context Injection [CEO Review 3 — Deferred from Beta]
**Status: Post-beta [CEO-R-7A, 2026-03-21]**
**Root cause for deferral:** Forward-only /btw creates designs with internal inconsistency — `confidence_score` does not degrade when a context note contradicts already-completed steps. Injecting "fouling factor = 0.0003" at Step 12 means Steps 1–11 are now calculated with the wrong fouling assumption, but their confidence scores remain untouched. This is a silent correctness gap.

**Post-beta build sequence (two phases):**

**Phase 1 — Pre-run notes only (no pipeline changes needed)**
- Scope: `/btw` only accepted before `POST /api/v1/hx/design` is called (i.e., before the pipeline starts).
- Notes stored as `applied_from_step=1` — injected at every step from the beginning.
- No confidence gap: all 16 steps see the note from the start. Internal consistency maintained.
- Implementation: `ContextNote` model in `DesignState`, stored in a separate Redis list key `{session_id}:context_notes` (avoids race condition with pipeline read-modify-write on main state key). Prompt injection in `BaseStep._build_prompt()`.
- Frontend: detect `/btw` prefix in `MessageInput.jsx`; disable during active pipeline with tooltip "Pipeline running — add context before starting your next design".
- SSE: add `context_note_ack` as the 9th event type (removed in beta, restored here).
- Prompt injection mitigation: strip lines beginning with "Ignore", "Disregard", "System:", "Assistant:" before injection.

**Phase 2 — Mid-pipeline injection (v2, requires parameter dependency graph)**
- Scope: `/btw` accepted at any point, including mid-pipeline.
- Requires: parameter dependency graph (which steps depend on which DesignState fields). When a note changes a field touched by already-completed steps, those steps are flagged for re-run. confidence_score degraded for affected steps.
- Alternative to full re-run: emit `step_warning` SSE with message "Context note may affect steps 3, 7, 9 — confidence adjusted" and degrade those steps' scores by a fixed factor (e.g., 0.85× per contradicted step).
- This is the architecturally clean version but requires significant DesignState graph metadata. Do not ship Phase 2 without a complete solution — partial mid-pipeline injection without confidence tracking is worse than Phase 1.

**Effort:** Phase 1 — S (human: ~1 day / CC: ~30 min). Phase 2 — L (human: ~1 week / CC: ~3 hours).
**Depends on:** Beta complete + at least 3 beta engineers using pre-run notes (Phase 1) to validate demand for mid-pipeline injection before building Phase 2.

---

## 21. Decision Log

All architecture decisions from CEO review, engineering review, and convergence review sessions (2026-03-19).

### Engineering Review Decisions

| ID | Decision | Description |
|----|----------|-------------|
| ENG-1A | Try-first + 3-correction limit | AI must attempt resolution before escalating. Max 3 correction attempts per step. After 3 failures, force escalate with all attempts in payload. `escalate` JSON includes `attempts`, `observation`, `recommendation`, `options`. |
| ENG-1B | Confidence gate (threshold 0.70) | After every AI review (initial + each correction re-review), check `confidence`. If `confidence < 0.70`, override decision to `escalate`. Log `confidence_gate_triggered=True` in step record. |
| 1B | Direct SSE | Frontend connects directly to HX Engine for SSE (via nginx proxy per CEO-1A) |
| 2B | Pydantic DesignState | Single Pydantic model, not a dict |
| 3A | Convergence loop AI skip | `in_convergence_loop` flag skips conditional AI in Steps 7/10/11 |
| 4A | Engine registry | `engines.yaml` config + `engine_client.py` replaces MCP |
| 5 | Bell-Delaware | Shell-side h via Bell-Delaware method (not Kern alone) |
| 6A | StepProtocol | `@runtime_checkable Protocol` for all 16 steps |
| 7A | 5 golden orchestration tests | VCR cassette determinism |
| 8A | AI reproducibility test | 10× identical inputs → ≥ 9/10 same decision (nightly) |
| 9A | Parallel Supermemory | `asyncio.gather` for book + past design searches |
| 10A | Connors pre-filter | Quick vibration check before full autoresearch experiment |
| CG1A | try/finally flag reset | `in_convergence_loop` always cleared, even on exception |
| CG2A | Poll fallback | GET /status endpoint for SSE disconnect recovery |
| CG3A | GeometrySpec validators | Field validators on all length/ratio fields |

### Third Engineering Review Pass

| ID | Decision | Description |
|----|----------|-------------|
| 3R-1A | Internal webhook auth | `X-Internal-Token` header between HX Engine → Backend |
| 3R-2A | Redis AOF persistence | `redis-server --appendonly yes` + redis-data volume, 24h TTL |
| 3R-3A | Autoresearch parallelism | `ThreadPoolExecutor(max_workers=16)` for CPU-bound experiments |
| 3R-4A | FluidProperties schema | Explicit fields with validators (not a generic dict) |
| 3R-5A | StepRecord schema | Audit log entry with `ai_called` flag and `duration_ms` |
| 3R-6A | Stream JWT auth | Short-lived JWT for SSE stream access |

### CEO Review Decisions

| ID | Decision | Description |
|----|----------|-------------|
| CEO-1A | nginx reverse proxy | One public origin, routes /api/v1/hx/ → HX Engine |
| CEO-2A | Secrets management | `.env` + `.env.example` + `.gitignore` |
| CEO-3A | AI retry logic | Retry 2× with backoff, then WARN+proceed (ai_called=False) |
| CEO-4A | Supermemory timeout | `_safe_memory_call()` wrapper with 5s `asyncio.wait_for` timeout |
| CEO-5A | user_id in stream JWT | Stream JWT payload includes user_id for session authorization |
| CEO-6A | InputBar disable on ESCALATE | Prevent concurrent input while any step is ESCALATED |
| CEO-7A | Confidence weights | Equal weights 0.25 each via CONFIDENCE_WEIGHTS constant |
| CEO-CP2 | Confidence breakdown | `confidence_breakdown` dict in DesignState (4 keys) |
| CEO-CP4 | org_id field | `org_id: Optional[str] = None` in DesignState for future team accounts |
| CEO-CP5 | JWT auth in Week 6 | Full auth flow: login, JWT, admin create_user.py, no self-signup |

### Office Hours Session (2026-03-19)

| ID | Decision | Description |
|----|----------|-------------|
| OH-1A | Trust-Calibration-First | HTRI Comparison workflow moved from post-beta → Week 5. Build Steps 1–8, then HTRI comparison, then Steps 9–16. Rationale: validates accuracy with real engineers mid-build, not after launch. |
| OH-2A | Target user refined | Both junior engineers (no HTRI seat) and senior engineers (15+ designs/year, HTRI too slow for first-pass) are primary users. Senior engineer has purchasing authority. |
| OH-3A | Org-level sale | Initial customer is a firm (team license), not an individual. HTRI bottleneck is structural — org-level pain needs org-level purchase. Shapes pricing model decision. |
| OH-4A | Calibration feedback point | Correction factors from HTRI comparisons applied in Step 9 (Overall U) only. Single application point: U_corrected = U_calculated × (1 − avg_delta_U_pct/100). Applied only when ≥ 5 comparisons exist for the CalibrationKey. Shown in AI reasoning. |
| OH-5A | HTRI compare auth (Week 5) | Static `X-Compare-Token` bearer token on POST /api/v1/hx/compare during Week 5. Value in `.env` as `HTRI_COMPARE_TOKEN`. **Week 6 cutover:** Replace with JWT (same auth as all other protected endpoints). No dual-auth transition needed for beta (2–3 known engineers). Notify beta engineers directly when Week 6 ships. Add test: old X-Compare-Token on /compare → 401 after JWT cutover. [Eng Review] |
| OH-6A | CalibrationKey schema | Compound key: (fluid_pair: tuple[str,str] sorted, tema_type: str, shell_diameter_class: 'small'\|'medium'\|'large'). Small < 0.5m, medium 0.5–1.0m, large > 1.0m. All fields available from DesignState after Step 4. |
| OH-7A | Calibration persistence | `calibration_records` MongoDB collection. Schema: {key: CalibrationKey, delta_U_pct: float, delta_dP_shell_pct: float, delta_dP_tube_pct: float, comparison_count: int, last_updated: datetime, archived: bool, archived_reason: str\|None, archived_at: datetime\|None, model_version: str}. `calibration.py` is a query module, not a data store. Startup cache only loads `archived: false` records matching `CURRENT_MODEL_VERSION`. |
| OH-9A | Calibration data lifecycle | Three mechanisms: (1) Soft archive — never hard-delete calibration records; set `archived: true` via admin endpoint when process conditions change or a Bell-Delaware bug is fixed. Step 9 and startup cache ignore archived records. (2) Model version tag — bump `CURRENT_MODEL_VERSION` constant when Bell-Delaware implementation changes significantly; old records excluded from correction factor automatically. (3) TTL on session data — 30-day TTL index on any temporary design session documents in MongoDB (not calibration records). Hard deletion only for throwaway data, never for comparison records. |
| OH-8A | HTRI compare input modes | Two input paths: (1) Manual entry — U_htri, dP_shell_htri, dP_tube_htri fields (primary, build first); (2) File upload — .xrf XML or CSV, 2MB hard limit (secondary, build after manual). |

### CEO Review 2 — SELECTIVE EXPANSION (2026-03-20)

| ID | Decision | Description |
|----|----------|-------------|
| CEO-R-1A | Bell-Delaware contingency | If Serth 5.1 misses ±5% after 3-day debug budget: activate Kern fallback (Kern, *Process Heat Transfer*, 1950) for shell-side h in Step 8. Proceed to Weeks 4-5 with Kern active. Escalate to week-long parallel deep dive if unresolved after 3 days. Bell-Delaware must pass before Week 7 autoresearch gate. |
| CEO-R-2A | Regulatory/liability stance | "Decision support" for beta. All Step 16 output and frontend copy labeled `FOR REVIEW ONLY — verify with licensed engineer`. Confidence score is a suggestion, not a certification. Revisit "fabrication-ready" post first 10+ HTRI comparisons. |
| CEO-R-3A | Pricing model | Org/team seat license. Week 6 auth builds `subscription_active` per `org_id`; returns `True` for all beta users. If Week 6 slips, beta users default to `subscription_active=True` — no blocking. |
| CEO-R-4A | Post-beta GTM path | Three-step path: (1) first HTRI comparison < 10% deviation → ask engineer to show a colleague, (2) 2–3 engineers at one firm → org-level demo, (3) firm asks for > 2 seats → paid conversion trigger. |

### CEO Review 3 — HOLD SCOPE (2026-03-21)

| ID | Decision | Description |
|----|----------|-------------|
| CEO-R-5A | HTRI file format: CSV first | `htri_parser.py` Week 5 uses `csv.reader()` (stdlib). Pre-Week 5: obtain 3 sample CSV exports from beta engineer. `.xrf` XML parser deferred post-beta; use `defusedxml` when built. Resolves Open Question 3. |
| CEO-R-6A | Bell-Delaware vs Kern auto-conservative | If \|BD − Kern\| / BD > 20%, use lower h_o value (Layer 2 rule in `validation_rules.py`). Step 8 AI prompt includes both values and override reason. Resolves Open Question 6 (Decision 3R-7B). |
| CEO-R-7A | /btw deferred to post-beta | BTW-1A/2A/3A deferred. Root cause: forward-only /btw creates designs with internal inconsistency (confidence_score doesn't degrade when notes contradict completed steps). Post-beta: implement pre-run notes only first (applied_from_step=1, no confidence gap), then full mid-pipeline with parameter dependency tracking in v2. |
| CEO-R-8A | wait_for_user() + /respond endpoint | Specified async pattern: asyncio.Future per session in sse_manager.py, resolved by POST /api/v1/hx/design/{id}/respond. Timeout 300s + future cleanup + waiting_for_user flag. |
| CEO-R-9A | Pipeline orphan detection | heartbeat() + is_orphaned() in session_store.py. PIPELINE_ORPHAN_THRESHOLD_SECONDS=120. waiting_for_user=True excludes session from orphan detection. GET /status returns "failed" for orphaned sessions. |
| CEO-R-10A | MongoDB indexes at startup | Compound index on calibration_records, unique index on users.email. Created at FastAPI lifespan. Idempotent. Failure: exponential backoff 1s/2s/4s then CRITICAL + re-raise. |

### CEO Plan Amendments (applied to build sequence)

- Day 5: nginx service + nginx.conf in docker-compose.yml; .env + .env.example
- Day 3: ai_engineer.py retry logic; AIModeEnum (not bare str)
- All memory steps: `_safe_memory_call()` wrapper
- Week 6: stream JWT payload includes user_id; InputBar disabled when isEscalated; delete shared-password auth
- Week 5: CONFIDENCE_WEIGHTS constant; CEPCI value 2026 (~816)
- Engineer prompt: prompt injection mitigation in engineer_review.txt
- Models: session_id = Field(default_factory=lambda: str(uuid4()))
- Frontend: ChatWindow error state, ParetoChart loading state, confidence_breakdown expandable in DesignSummary
- Autoresearch: experiments run in memory only — no Redis saves during sweep

---

## 22. Open Questions

1. **Accuracy trust threshold:** At what U/dP deviation does an engineer lose trust? 5%? 10%? This determines whether calibration.py is needed from day one. The HTRI Comparison workflow (Week 5) will answer this empirically.
2. ~~**First beta user with HTRI access:**~~ **RESOLVED (2026-03-20)** — Beta engineer with HTRI access confirmed. See §24 Beta User Onboarding Checklist for pre-Week-5 coordination steps.
3. ~~**HTRI output format in the field:**~~ **RESOLVED (2026-03-21)** — **CSV first, .xrf post-beta.** `htri_parser.py` in Week 5 uses `csv.reader()` (stdlib). Pre-Week 5: obtain 3 sample CSV exports from beta engineer to validate column names. `.xrf` XML parser deferred to post-beta; when built, use `defusedxml` (XXE mitigation). See §21 Decision CEO-R-5A.
4. ~~**Regulatory/liability positioning:**~~ **RESOLVED (2026-03-20)** — **"Decision support"** for beta. All Step 16 output and frontend copy labeled `FOR REVIEW ONLY — verify with licensed engineer`. Confidence score displayed as a suggestion, not a certification. Revisit "fabrication-ready" after first 10+ HTRI comparisons and accuracy data. See §21 Decision CEO-R-2A.
5. ~~**Pricing model:**~~ **RESOLVED (2026-03-20)** — **Org/team seat license** selected. Week 6 auth builds `subscription_active` check per `org_id`; returns `True` for all beta users. If Week 6 auth slips, beta users default to `subscription_active=True` — no one is blocked. See §21 Decision CEO-R-3A.
6. ~~**Decision 3R-7B (Bell-Delaware vs. Kern cross-check divergence):**~~ **RESOLVED (2026-03-21)** — **Auto-conservative.** When |BD − Kern| / BD > 20%, use the lower of the two h_o values (Layer 2 rule in `validation_rules.py`). AI sees both values and the override reason in Step 8 prompt. See §21 Decision CEO-R-6A and §14 Week 3.

---

## 23. Success Criteria

| Milestone | Metric |
|-----------|--------|
| Week 3 engineering accuracy | Serth Example 5.1: U within 5%, dP within 10%, all J-factors within 10% |
| Week 5 end-to-end | Full 16-step design runs in < 30 seconds, all SSE events stream correctly |
| Week 5 HTRI validation | One real engineer runs the HTRI comparison and deviation is < 10% on U [Decision OH-1A]. First session run together on a call (see §24). |
| Week 8 complete | Supermemory retrieval improves seed U guess vs. book midpoint; autoresearch returns Pareto front in < 30s |
| First user trust signal | The first beta user describes the product as "an audit trail" — not "a calculator." The reasoning layer is the differentiator, not the number. |
| First user validation | One process engineer runs a real design and says the result is trustworthy |

**Post-beta GTM path [Decision CEO-R-4A]:**

| Trigger | Next Action |
|---------|-------------|
| First HTRI comparison < 10% deviation on U | Ask the engineer if he'd show it to one colleague at his firm |
| 2–3 engineers at one firm using ARKEN | The wedge is open — prepare an org-level demo |
| Firm asks for more than 2 seats | Trigger paid conversion (org/team seat license, see Decision CEO-R-3A) |

These are the three steps from first successful comparison to first revenue. The org-level pain (1–2 HTRI seats for 15 engineers) means conversion follows naturally once the product proves its accuracy within one firm.

---

## 24. Beta User Onboarding Checklist

**Engineer:** Confirmed — process engineer with HTRI access. Target first session: Week 5.

**Before Week 1 coding starts:**

0. **Demand signal call (30 minutes, do this before writing a line of code).** Call the beta engineer or another process engineer from your network. Ask them to walk through their last heat exchanger design: "What took the longest?" "What would have made it faster?" "How did you check if the design was right?" At the end, ask directly: "If a tool could give you a first-pass design in 2 minutes with a confidence score and step-by-step audit trail — what would that be worth to your team per month?" Document their answer (a number, a range, or an explicit rejection). This is not the HTRI comparison session — it is demand validation before building. If the answer is "I'd use it but we'd never pay for it" — that is signal you need before writing 3 weeks of code.

**Before the first comparison session (complete by end of Week 4):**

1. **Agree on test case** — Confirm a single-phase liquid case: crude oil cooling is the preferred test (matches ARKEN Phase 1 scope and Serth 5.1 benchmark). Provide the engineer with the input format: fluid identities, flow rates (kg/s), inlet/outlet temperatures, pressure if known. Do NOT use a two-phase, condensing, or boiling case — ARKEN Phase 1 is single-phase liquids only.

2. **Share the disclaimer** — Before the engineer sees any ARKEN output, send him the following copy:
   > *"ARKEN AI is a first-pass design decision support tool. All outputs are labeled FOR REVIEW ONLY and must be verified by a licensed process engineer before use in fabrication or procurement. This is not a substitute for HTRI Xchanger Suite or a stamped design."*
   This sets the right expectation. He is not evaluating a finished product — he is helping validate accuracy at the Step 8 (overall U) and Step 10 (pressure drop) level.

3. **Get HTRI values before the call** — Ask the engineer to run the same case in HTRI and note: `U_overall` (W/m²K), `dP_shell` (bar), `dP_tube` (bar). These are the three fields in the manual entry comparison form. He does not need to share the full `.xrf` file (though that is also accepted).

4. **Run the first session together on a call** — Do not send a link and wait async. Run the first comparison side-by-side on a screen share. If ARKEN misses by > 10% on U, you want to be there to understand why (geometry mismatch, fluid property difference, unit confusion) — not to receive a WhatsApp message saying "it was 18% off."

**Success criterion for first session:** Deviation < 10% on U. If ≥ 10%, debug live on the call — most likely cause is a geometry input mismatch, not a correlation error. See §22 Open Question #1 for the accuracy trust threshold question this session will answer.

---

## Verification (end-to-end test flow)

1. `docker-compose up`
2. Open frontend at http://localhost (via nginx)
3. Login with admin-created credentials
4. Type: "Design a heat exchanger for cooling 50 kg/s of crude oil from 150°C to 90°C using cooling water at 30°C"
5. Observe: 16 StepCards appear live (steps 1–16 streaming via nginx-proxied SSE)
6. Step 12 shows an IterationBadge counting convergence iterations
7. Final StepCard shows confidence_score ≥ 0.70 with expandable confidence_breakdown
8. Disconnect wifi during Step 9 → UI falls back to poll → reconnects on Step 14
9. Ask: "Optimize for cost" → ParetoChart appears with ≥ 3 Pareto points
10. Check MongoDB: design result stored via internal webhook
11. Check Supermemory: design summary stored (confidence ≥ 0.75)

---

*End of Document | ARKEN AI | March 2026 | Version 8.0*
*Consolidates: DEVELOPMENT_PLAN.md v6.0, End-to-End Build Plan, CEO Review, Engineering Reviews (3 passes), Test Plans (4 passes), Office Hours Design Doc, TODOS.md, Office Hours Session (2026-03-19, Trust-Calibration-First)*
