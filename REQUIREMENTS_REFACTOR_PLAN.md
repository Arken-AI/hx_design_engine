# Requirements Refactor — Implementation Plan

## 1. Root Causes

### 1.1 NL Parser Corrupts Explicit API Inputs (P_hot_Pa Bug)

**What happened:**
The MCP tool correctly passed `P_hot_Pa = 500,000 Pa (5 bar)` and `P_cold_Pa = 300,000 Pa (3 bar)`
as explicit structured fields. The engine correctly seeded `DesignState` with these values.
Then Step 1 ran its NL parser on `raw_request` and overwrote both values with `300,000 Pa`.

**Why:**
In `step_01_requirements.py → _from_natural_language()`, the pressure side-detection
uses a 30-character context window:

```python
ctx = text[max(0, m.start() - 30):m.end()].lower()
```

The phrase "Hot side:" appears ~55 chars before "5 bar" in the request string:
```
"Hot side: crude oil, flow rate 10 kg/s, inlet pressure 5 bar"
 ↑ 55 chars away                                           ↑ regex match here
```

The 30-char window cannot reach "Hot side:" so both pressure matches fall into
the `else` branch, which applies the value to both sides:

```python
else:
    p_hot_pa = p_pa   # last pressure found wins
    p_cold_pa = p_pa  # overwrites any previously correct value
```

The last pressure matched was 3 bar → both sides stored as 300,000 Pa.
After Step 1 completes, `_apply_outputs()` in `pipeline_runner.py` writes these
wrong values back onto `DesignState`, permanently losing the 5 bar hot-side value.

**Root cause in one line:**
Step 1's NL parser runs even when structured inputs are already provided,
and overwrites them with fragile regex-derived values.

---

### 1.2 No Physics Feasibility Gate Before Pipeline Starts

**What happened:**
The pipeline accepts any structured input and begins computation from Step 2
without checking whether the design is thermodynamically feasible.

**Why:**
There is no pre-pipeline validation layer. Physical checks (temperature cross,
minimum driving force, R-factor sanity) are scattered across individual steps
or left entirely to the AI reviewer.

**Consequence:**
- A temperature cross is not caught until Step 5 (LMTD), after Steps 2–4 have
  already run and wasted compute.
- Clearly infeasible inputs (e.g. T_cold_out > T_hot_in) reach the AI reviewer,
  which is expensive and unreliable for what should be a deterministic check.
- Claude has no structured feedback to give the user when inputs are physically
  impossible — it either gets a mid-pipeline error or a misleading result.

---

### 1.3 Step 1 Mixes Concerns (Parse + Validate + AI Review)

**What happened:**
Step 1 does three things: parse NL, validate physics, and run a full AI review.
In the MCP context, Claude has already done the NL extraction before calling
the tool — so the engine is parsing twice.

**Root cause in one line:**
The engine was designed as a standalone NL tool, but is now used as a
structured API backend behind an AI layer that already handles NL.

---

## 2. Solution Overview

### 2.1 Architecture

```
User types in chat
"Cool crude oil from 150°C to 80°C using water, 10 kg/s"
        │
        ▼
  Claude (MCP)
  reads NL, extracts structured params
        │
        ▼
  POST /api/v1/hx/requirements          ← NEW: stateless, no session
        │  Layer 1: schema + completeness
        │  Layer 2: physics feasibility (deterministic only, no AI)
        │
        ├── valid: false
        │     { errors: [{ field, message, suggestion, valid_range }] }
        │           │
        │           ▼
        │     Claude formulates specific question for user:
        │     "Hot outlet 80°C ≥ inlet 30°C — did you mean cool FROM 150°C?"
        │           │
        │           ▼
        │     User corrects → loop back
        │
        └── valid: true
              { token: "hmac-...", user_message: "...", design_input: {...} }
                    │
                    ▼
              Claude tells user:
              "Requirements valid. Q≈1606 kW. Starting design..."
                    │
                    ▼
              POST /api/v1/hx/design (with token)
                    │
                    ▼
              Step 1: state hydration (no parsing, no AI)
              Step 2: Heat Duty
              Step 3: Fluid Properties
              Step 4: TEMA Geometry  ← AI review lives here
              Step 5: LMTD & F-Factor
                    │
                    ▼
              SSE stream → live progress in chat
```

### 2.2 Key Design Decisions

1. **Claude handles all NL and conversation.** Reads user text, extracts numbers,
   formulates follow-up questions. The engine never sees raw text again.

2. **Engine only checks physics.** Is this design thermodynamically possible?
   Yes or no, with a specific structured reason. Pure deterministic math.

3. **Pipeline only runs on clean inputs.** The HMAC token proves `/requirements`
   ran on these exact inputs. No token = engine re-validates inline before
   creating a session (defense in depth for direct API callers and tests).

4. **One shared schema.** `DesignRequest` (currently in `design.py`) moves to
   `models/requirements.py` and is imported by both routers. No duplicate schemas.

5. **SSE session opens only after validation passes.** No wasted sessions from
   bad inputs.

---

## 3. Implementation

### 3.1 New Endpoint — POST /api/v1/hx/requirements

**File:** `hx_engine/app/routers/requirements.py` (new file)

**Request body:** `DesignRequest` (moved from `design.py` to `models/requirements.py`)

#### Field contract — derived from Step 2 pre-condition check

```
REQUIRED — pipeline raises CalculationError without these:
  hot_fluid_name      str     Step 2 needs it for Cp lookup via thermo adapter
  cold_fluid_name     str     Step 2 needs it for Cp lookup via thermo adapter
  T_hot_in_C          float   always needed
  T_cold_in_C         float   Step 2 requires at least one cold-side temp
  m_dot_hot_kg_s      float   Step 2 requires at least one flow rate

OPTIONAL — Step 2 derives missing values via energy balance:
  T_hot_out_C         float   derived if cold side fully known + m_dot_cold given
  T_cold_out_C        float   derived if hot side fully known (most common case)
  m_dot_cold_kg_s     float   derived if all 4 temps known

  Derivation rules (Step 2 handles exactly ONE missing value):
    Case 1: T_hot_in + T_hot_out + T_cold_in + m_dot_hot
            → derives T_cold_out and m_dot_cold
    Case 2: T_hot_in + T_hot_out + T_cold_in + T_cold_out + m_dot_hot
            → derives m_dot_cold
    Case 3: all 4 temps + both flow rates
            → Step 2 just verifies energy balance

OPTIONAL with defaults:
  P_hot_Pa            float   default 101325 Pa (atmospheric)
  P_cold_Pa           float   default 101325 Pa (atmospheric)

PURELY OPTIONAL — never required:
  tema_preference     str     Step 4 auto-selects; validate only IF provided
                              allowed: {AES, BEM, AEU, AEP, AEL, AEW}
  raw_request         str     stored for audit only, never parsed by any step
```

#### Fluid name validation

`/requirements` does NOT call the thermo adapter (stateless endpoint).
Fluid name validation works as follows:
- If name is in `_KNOWN_FLUIDS` (from `step_01_requirements.py`) → accepted silently
- If name is NOT in `_KNOWN_FLUIDS` → **warning** (not error):
  `"'bunker fuel' not in known fluid list — thermo lookup may fail in Step 2"`
- Real failure surfaces in Step 2 if `get_fluid_properties()` cannot resolve the name

**Response on success (200):**
```json
{
  "valid": true,
  "token": "hmac-sha256-base64...",
  "user_message": "Requirements valid. Crude oil 150→80°C, water 25→45°C, Q≈1606 kW. Ready to design.",
  "design_input": { ...all canonicalised fields... },
  "warnings": [ "R=3.5 is high — F-factor will be checked in Step 5" ]
}
```

**Response on failure (422):**
```json
{
  "valid": false,
  "errors": [
    {
      "field": "T_hot_out_C",
      "message": "Hot outlet (80°C) >= hot inlet (30°C) — fluid cannot cool",
      "suggestion": "T_hot_out_C must be less than T_hot_in_C (30°C)",
      "valid_range": "< 30°C"
    }
  ]
}
```

The `suggestion` and `valid_range` fields give Claude exactly what it needs to
formulate a precise, actionable question for the user.

**No session created. No DB write. Stateless.**

---

### 3.2 HMAC Token

**Purpose:** Proof that `/requirements` ran on these exact inputs. Stateless — no
Redis, no DB, no token storage.

**Implementation** (`hx_engine/app/core/requirements_validator.py`):

```python
import hmac, hashlib, json, time

APP_SECRET = settings.app_secret  # from .env, already exists

def sign_token(design_input: dict) -> str:
    """HMAC-SHA256 of canonical JSON + unix-minute."""
    minute = str(int(time.time()) // 60)
    payload = json.dumps(design_input, sort_keys=True) + minute
    return hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()

def verify_token(token: str, design_input: dict) -> bool:
    """Accept tokens from current minute or previous (±1 min tolerance)."""
    for offset in (0, -1):
        minute = str(int(time.time()) // 60 + offset)
        payload = json.dumps(design_input, sort_keys=True) + minute
        expected = hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(token, expected):
            return True
    return False
```

Token is valid for ~2 minutes. No storage needed. `hmac.compare_digest` prevents
timing attacks.

---

### 3.3 Validation Rules

#### Layer 1 — Schema / Completeness

**Required field checks (hard errors):**

| Rule | Error field | Message |
|------|-------------|---------|
| `hot_fluid_name` present and non-empty | `hot_fluid_name` | "hot_fluid_name is required" |
| `cold_fluid_name` present and non-empty | `cold_fluid_name` | "cold_fluid_name is required" |
| `T_hot_in_C` present | `T_hot_in_C` | "T_hot_in_C is required" |
| `T_cold_in_C` present | `T_cold_in_C` | "T_cold_in_C is required" |
| `m_dot_hot_kg_s` present and > 0 | `m_dot_hot_kg_s` | "m_dot_hot_kg_s is required (hot-side flow rate)" |

**Range checks on any provided value (hard errors):**

| Rule | Error field | Message |
|------|-------------|---------|
| All temperatures in [-50, 1000] °C | field name | "{field}={v} outside physical range [-50, 1000]°C" |
| All flow rates > 0 | field name | "{field} must be positive" |
| All pressures > 0 | field name | "{field} must be positive" |

**Optional field validation (only when provided):**

| Rule | Error field | Message |
|------|-------------|---------|
| `tema_preference` in allowed set | `tema_preference` | "Unknown TEMA type '{v}' — allowed: AES, BEM, AEU, AEP, AEL, AEW" |
| Fluid name in `_KNOWN_FLUIDS` | `hot_fluid_name` / `cold_fluid_name` | WARNING only: "'{v}' not in known fluid list — thermo lookup may fail in Step 2" |

**Note on optional temps/flows:** `T_hot_out_C`, `T_cold_out_C`, `m_dot_cold_kg_s` are
all optional. Step 2 derives the missing values via energy balance. At least one
of these must be present alongside the required fields so the system is not
underdetermined — this is caught by the Layer 2 energy balance feasibility check.

#### Layer 2 — Physics Feasibility (conditional: rules only fire when all required fields are present)

| Rule | Fires when | Error message |
|------|-----------|---------------|
| T_hot_out_C < T_hot_in_C | both present | "Hot fluid must cool: T_hot_out ({v}) >= T_hot_in ({v})" |
| T_cold_out_C > T_cold_in_C | both present | "Cold fluid must heat: T_cold_out ({v}) <= T_cold_in ({v})" |
| No temp cross: T_cold_out < T_hot_in | both present | "Temperature cross: T_cold_out ({v}) >= T_hot_in ({v})" |
| No temp cross: T_cold_in < T_hot_out | both present | "Temperature cross: T_cold_in ({v}) >= T_hot_out ({v})" |
| min(ΔT₁, ΔT₂) >= 3°C | all 4 temps present | "Min approach {v}°C < 3°C — HX would be infinitely large" |
| R = ΔT_hot/ΔT_cold <= 20 (warning) | all 4 temps present | WARNING: "R={v} is very high — may need multiple shells" |

**Note:** Energy imbalance check (`Q_hot ≈ Q_cold`) is NOT in `/requirements`
because it requires Cp (fluid property, available only in Step 3). This check
stays in Step 2 where Cp is already computed.

---

### 3.4 Defense in Depth — POST /design

`POST /design` must also be protected for direct callers (tests, backend
integration, future services that skip `/requirements`).

```python
# in start_design() handler, before session creation:
if req.token:
    if not verify_token(req.token, req.model_dump(exclude={"token", "raw_request"})):
        raise HTTPException(status_code=400, detail="Invalid requirements token — re-run /requirements")
else:
    # No token: re-run validator inline (defense in depth)
    errors = validate_requirements(req)
    if errors:
        raise HTTPException(status_code=422, detail={"valid": False, "errors": errors})
```

**Add `token` as optional field to `DesignRequest`:**
```python
token: Optional[str] = None   # HMAC from /requirements; if absent, inline validation runs
```

---

### 3.5 Refactor Step 1 — State Hydration Only

**File:** `hx_engine/app/steps/step_01_requirements.py`

**Remove entirely:**
- `_from_natural_language()` and all regex patterns
- `_from_structured()` (logic moves to `requirements_validator.py`)
- `DesignInput` schema (moves to `models/requirements.py`)
- AI review: `ai_mode = AIModeEnum.FULL` → `AIModeEnum.NONE`

**New `execute()` — read from DesignState, emit outputs, done:**

```python
async def execute(self, state: DesignState) -> StepResult:
    outputs = {
        "hot_fluid_name":      state.hot_fluid_name,
        "cold_fluid_name":     state.cold_fluid_name,
        "T_hot_in_C":          state.T_hot_in_C,
        "T_hot_out_C":         state.T_hot_out_C,
        "T_cold_in_C":         state.T_cold_in_C,
        "T_cold_out_C":        state.T_cold_out_C,
        "m_dot_hot_kg_s":      state.m_dot_hot_kg_s,
        "m_dot_cold_kg_s":     state.m_dot_cold_kg_s,
        "P_hot_Pa":            state.P_hot_Pa,
        "P_cold_Pa":           state.P_cold_Pa,
        "missing_T_cold_out":  state.T_cold_out_C is None,
        "missing_m_dot_cold":  state.m_dot_cold_kg_s is None,
    }
    return StepResult(
        step_id=self.step_id,
        step_name=self.step_name,
        outputs=outputs,
    )
```

Step 1 is now a pure audit record — confirms what entered the pipeline.

---

### 3.6 Update MCP Tool (hx_mcp/server.py)

**New tool: `hx_validate_requirements`**

```
Claude's chat flow:
1. User types design description
2. Claude extracts structured params
3. Claude calls hx_validate_requirements(params)
   → valid: false  → Claude relays specific error, asks user to correct
   → valid: true   → Claude shows user_message, calls hx_design(token=token, ...params)
4. hx_design streams pipeline progress back
```

**Tool response Claude uses:**
```json
{
  "valid": true,
  "token": "hmac...",
  "user_message": "Requirements valid. Q≈1606 kW. Starting design...",
  "warnings": ["R=3.5 — F-factor will be verified in Step 5"]
}
```

Claude relays `user_message` to the chat, surfaces `warnings` if any,
then immediately calls `hx_design` with the token.

---

### 3.7 Update Existing Tests

| File | Change |
|------|--------|
| `tests/unit/test_step_01_nl.py` | DELETE — NL parser is gone |
| `tests/unit/test_step_01_structured.py` | DELETE — structured parsing moves to validator |
| `tests/unit/test_step_01_validation.py` | DELETE — validation moves to validator |
| `tests/unit/test_step_01_integration.py` | REWRITE — hydration-only tests |
| `tests/unit/test_requirements_validator.py` | CREATE — all Layer 1 + Layer 2 rules |
| `tests/unit/test_requirements_token.py` | CREATE — sign/verify, expired token, tampered token |
| `tests/integration/test_requirements_endpoint.py` | CREATE — full endpoint happy path + error cases |
| `tests/integration/test_design_no_token.py` | CREATE — direct /design call triggers inline validation |

---

## 4. Files Affected

| File | Action |
|------|--------|
| `hx_engine/app/models/requirements.py` | CREATE — `DesignRequest` (moved from design.py), `RequirementsResponse` |
| `hx_engine/app/core/requirements_validator.py` | CREATE — Layer 1 + Layer 2 rules, `sign_token()`, `verify_token()` |
| `hx_engine/app/routers/requirements.py` | CREATE — `POST /api/v1/hx/requirements` |
| `hx_engine/app/routers/design.py` | UPDATE — import `DesignRequest` from models, add token verify + inline fallback |
| `hx_engine/app/steps/step_01_requirements.py` | REWRITE — hydration only |
| `hx_engine/app/main.py` | ADD — register requirements router |
| `hx_mcp/server.py` | ADD — `hx_validate_requirements` tool, pass token into `hx_design` |
| `tests/unit/test_step_01_*.py` (3 files) | DELETE |
| `tests/unit/test_step_01_integration.py` | REWRITE |
| `tests/unit/test_requirements_validator.py` | CREATE |
| `tests/unit/test_requirements_token.py` | CREATE |
| `tests/integration/test_requirements_endpoint.py` | CREATE |
| `tests/integration/test_design_no_token.py` | CREATE |

---

## 5. What Does NOT Change

- Steps 2–5: unchanged
- Pipeline runner: unchanged
- Session store, SSE manager: unchanged
- AI review in Step 4: unchanged
- `DesignState` model: unchanged (add optional `token` field only)
- SSE stream contract: unchanged

---

## 6. Rollout Order

1. Create `requirements_validator.py` — Layer 1 + Layer 2 rules + token sign/verify + unit tests
2. Create `models/requirements.py` — move `DesignRequest`, add `RequirementsResponse`
3. Create `routers/requirements.py` — register in `main.py`
4. Update `routers/design.py` — token verify + inline validation fallback
5. Rewrite `step_01_requirements.py` — hydration only, delete NL tests
6. Update MCP server — `hx_validate_requirements` tool + pass token into `hx_design`
7. Integration tests

---

## 7. Review Issues — Resolved

All issues identified during plan review. Each applied to the sections above.

| # | Issue | Severity | Status | Applied in |
|---|-------|----------|--------|------------|
| 7.1 | `T_hot_out_C` incorrectly required | HIGH | RESOLVED | Section 3.1 — optional; only T_hot_in, T_cold_in, m_dot_hot are required |
| 7.2 | Physics rules assume all 4 temps present | MEDIUM | RESOLVED | Section 3.3 — all Layer 2 rules conditional on field presence |
| 7.3 | Energy imbalance check needs Cp | MEDIUM | RESOLVED | Section 3.3 — dropped from /requirements; stays in Step 2 where Cp is available |
| 7.4 | `tema_preference` unvalidated | LOW | RESOLVED | Section 3.1 + 3.3 — purely optional; validated only IF provided (allow-list) |
| 7.5 | Fluid name validation method unspecified | LOW | RESOLVED | Section 3.1 — `_KNOWN_FLUIDS` warning only; real validation in Step 2 thermo adapter |
| 7.6 | `raw_request` fate unspecified | LOW | RESOLVED | Section 3.1 — optional, audit only, never parsed |
| 7.7 | Two identical schemas (DRY violation) | MEDIUM | RESOLVED | Section 2.2 — one shared `DesignRequest` |
| 7.8 | No defense in depth for direct /design callers | MEDIUM | RESOLVED | Section 3.4 — inline validator fallback |
| 7.9 | Token needed for production (multiple callers) | MEDIUM | RESOLVED | Section 3.2 — HMAC token, stateless |

---

## 8. Data Flow Diagram

```
┌─────────────┐     NL text      ┌───────────────────────────────────────────┐
│    User     │ ───────────────▶ │              Claude (MCP)                  │
│   (chat)    │                  │  extracts structured params from NL text   │
└─────────────┘                  └───────────────────┬───────────────────────┘
       ▲                                             │ structured params
       │ user_message / question                     ▼
       │                          ┌──────────────────────────────┐
       │                          │  POST /api/v1/hx/requirements │
       │                          │  Layer 1: schema              │
       │                          │  Layer 2: physics             │
       │                          │  sign_token(inputs)           │
       │                          └──────────┬───────────────────┘
       │                                     │
       │              ┌──────────────────────┴──────────────────────┐
       │              │ valid: false                   valid: true   │
       │              │ errors[{field,msg,suggestion}] token + msg   │
       │              ▼                                │             │
       └──── Claude asks                               ▼
             specific question          ┌─────────────────────────┐
                                        │  POST /api/v1/hx/design  │
                                        │  verify_token() OR       │
                                        │  inline validate()       │
                                        │  create session          │
                                        └────────────┬────────────┘
                                                     │
                                        Step 1: hydration
                                        Step 2: heat duty
                                        Step 3: fluid props
                                        Step 4: TEMA + AI review
                                        Step 5: LMTD
                                                     │
                                        SSE stream ──▶ chat progress
```
