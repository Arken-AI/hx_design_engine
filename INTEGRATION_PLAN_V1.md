# ARKEN AI — Frontend + Backend + HX Engine Integration Plan (v1)

**Target:** Early release connecting all three services through Steps 1–5.
**Date:** 2026-03-27
**Scope:** Chat → parameter extraction → HX pipeline → live step cards in UI
**Updated:** 2026-03-29 — review pass 1: two-step validate→design flow, tool dispatch loop, MCP standalone
**Updated:** 2026-03-29 — review pass 2: BaseEvent model for hx_design_started, SSE ordering trap, escalation payload shape, EscalatedBody field name

---

## 1. What's Already Built (No Changes Needed)

| Component | Status | Notes |
|-----------|--------|-------|
| HX Engine Steps 1–5 | ✅ Complete | 450/450 tests passing |
| `POST /api/v1/hx/requirements` | ✅ Ready | Physics feasibility gate, returns token |
| `POST /api/v1/hx/design` | ✅ Ready | Returns `{session_id, stream_url}`. Token optional — runs inline validation if absent |
| `GET /api/v1/hx/design/{id}/stream` | ✅ Ready | SSE endpoint |
| `GET /api/v1/hx/design/{id}/status` | ✅ Ready | Poll fallback |
| `POST /api/v1/hx/design/{id}/respond` | ✅ Ready | Escalation response |
| `HXEngineClient` (backend) | ✅ Ready | Singleton in dependencies.py — needs `validate_requirements()` + `**kwargs` on `start_design()` |
| `ClaudeProvider.create_message_stream(tools=...)` | ✅ Ready | Already accepts tool schemas |
| `engines.yaml` tool registry | ⚠️ Stale | Schema needs update — see Piece 1 |
| `useHXStream` hook | ⚠️ Needs fixes | Missing `sessionId` state, wrong URL resolution — see Piece 5 |
| `HXPanel` + `StepCard` components | ✅ Ready | Just unwired from real data |
| `StepCard` escalation UI (`EscalatedBody`) | ⚠️ Needs fix | Reads `data.question` but SSE emits `data.message` — see Piece 5 |
| nginx routing `/api/v1/hx/` → HX engine | ✅ Ready | Direct, no backend in path |
| **`hx_mcp/server.py`** | ✅ Done | Standalone repo, FastMCP, 3 tools — working with Claude Desktop |

---

## 2. Architecture: Two Paths, One HX Engine

Both paths use the same validate → design two-step flow against the same HX Engine.
Path 1 (MCP) is complete and working. Path 2 (browser chat) is the remaining work.

```
┌─────────────────────────────────────────────────────────────────┐
│  PATH 1: Testing via Claude Desktop  ✅ DONE                    │
│                                                                 │
│  Claude Desktop                                                 │
│       │  MCP stdio transport                                   │
│       ▼                                                         │
│  MCP Server  (hx_mcp/server.py — standalone repo)              │
│       │                                                         │
│  Step 1: POST /api/v1/hx/requirements → { valid, token }       │
│       │  valid=false → relay errors to user → loop             │
│       │  valid=true  → immediately POST /api/v1/hx/design      │
│       ▼                                                         │
│  HX Engine :8100  →  { session_id, stream_url }                │
│                                                                 │
│  Claude Desktop: "Design started (session: abc123)."           │
│  Engineer: "what's the status?"                                 │
│  Claude Desktop calls get_design_status(session_id)            │
│       │  GET /api/v1/hx/design/{id}/status                     │
│       ▼                                                         │
│  Returns: step 3/5 complete, waiting_for_user: false           │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  PATH 2: Production via Browser Chat  ← REMAINING WORK         │
│                                                                 │
│  Frontend Chat → Backend :8001                                 │
│       │  Anthropic API with tool schemas (engines.yaml)        │
│       │  Tool dispatch loop (max 5 turns):                     │
│       │    Turn 1: Claude calls hx_validate_requirements       │
│       │    Turn 2: valid=true → Claude calls hx_design         │
│       │    Turn 3: backend emits hx_design_started → Chat SSE  │
│       │    Turn 4: Claude streams confirmation text            │
│       ▼                                                         │
│  HXEngineClient.validate_requirements() + start_design()       │
│       ├── emit hx_design_started → Chat SSE → Frontend         │
│       └── Frontend opens HX Engine SSE stream directly         │
│              /api/v1/hx/design/{id}/stream  (via nginx)        │
│              StepCards update live in HXPanel                   │
└─────────────────────────────────────────────────────────────────┘

SHARED LAYER
  engines.yaml  ──→  ToolRegistry (backend, Path 2)
  MCP server reads its own type annotations (FastMCP — no YAML needed)
  HX Engine :8100  ←  both paths call the same endpoints
```

### Why MCP + native tool use (not MCP only)

MCP stdio transport is designed for Claude agents (Claude Desktop, Claude Code) that run
tools as subprocesses. The production backend is a Python service calling the Anthropic API
directly — passing tool schemas in `messages.create()` is the right pattern there. MCP adds
an extra process hop with no benefit in that context.

### Why MCP server is standalone (not inside backend/)

The MCP server (`hx_mcp/`) is a local dev/testing tool that engineers run alongside the HX
Engine. It has no dependency on the backend package — only `mcp`, `httpx`. Keeping it
standalone means it can be run, updated, and distributed independently.

---

## 3. User Flows

### Happy path — browser chat (production)
```
User: "design an HX for steam 180°C → 100°C, cooling water 25°C → 45°C, 12 kg/s"
  ↓
Claude: extracts all params → calls hx_validate_requirements tool
  ↓
Backend: HXEngineClient.validate_requirements(**params) → { valid: true, token }
  ↓
tool_result(valid=true, token) → Claude calls hx_design tool with same params + token
  ↓
Backend: HXEngineClient.start_design(**params, token=token) → { session_id, stream_url }
  ↓
Backend: emit hx_design_started { session_id, stream_url } via Chat SSE
  ↓
Claude: streams "Starting your design — watch the progress panel on the right."
  ↓
Frontend: ChatContainer receives hx_design_started → connectStream(stream_url, session_id)
  ↓
HX Engine SSE: step_started → step_approved / step_corrected / step_warning
  ↓
StepCards update live → design_complete → DesignSummary shown
```

### Validation failure — browser chat
```
User: "design an HX for steam 200°C → 100°C, water 25°C → 45°C, 12 kg/s"
  (but T_cold_out > T_hot_out — thermodynamic violation)
  ↓
Claude: calls hx_validate_requirements
  ↓
Backend: validate_requirements() → { valid: false, errors: [{ field: "T_cold_out_C",
         message: "Cold outlet (45°C) cannot exceed hot outlet (100°C) in counterflow" }] }
  ↓
tool_result(valid=false) → Claude relays error to user:
  "The cold outlet temperature (45°C) is below the hot outlet (100°C) so this
   is physically feasible, but let me re-check — did you mean 85°C on the cold side?"
  ↓
User corrects → Claude calls hx_validate_requirements again → valid=true → hx_design
```

### Happy path — Claude Desktop (testing, Path 1 complete ✅)
```
Engineer: "design an HX for steam 180°C → 100°C, cooling water 25°C → 45°C, 12 kg/s"
  ↓
Claude Desktop: calls MCP tool hx_validate_requirements(hot_fluid_name="steam", ...)
  ↓
MCP Server: POST /api/v1/hx/requirements → { valid: true, token: "..." }
  ↓
Claude Desktop: (same turn) calls hx_design(same params + token)
  ↓
MCP Server: POST /api/v1/hx/design → { session_id, stream_url }
  ↓
Claude Desktop: "Design started (session: abc123).
  Stream at http://localhost:8100/api/v1/hx/design/abc123/stream
  Ask me for status updates anytime."
  ↓
Engineer: "what's the status?"
  ↓
Claude Desktop: calls get_design_status("abc123")
  ↓
MCP Server: GET /api/v1/hx/design/abc123/status
  ↓
Claude Desktop: "Step 3/5 complete. Current: Fluid Properties (APPROVED).
  Q = 2.41 MW, LMTD = 87.3 K. No warnings."
```

### Missing parameters (both paths)
```
User/Engineer: "design a heat exchanger for steam cooling"
  ↓
Claude: missing params → asks in one message:
  "I need a few more details to start your design:
   - Hot side: inlet/outlet temperatures
   - Cold side: fluid, inlet/outlet temperatures
   - Flow rate (at least one side)"
  ↓
User provides → Claude calls hx_validate_requirements → pipeline starts
```

### Escalation — browser chat only
```
HX Engine: step_escalated { step_id, message: "Cannot resolve fluid props..." }
  ↓
StepCard shows ESCALATED state with inline response form
  ↓
User types answer → respondToEscalation(session_id, response)
  ↓
POST /api/v1/hx/design/{id}/respond → pipeline resumes
```

---

## 4. Implementation Pieces

### Piece 0 — MCP Server for Claude Desktop ✅ DONE

**Location:** `hx_mcp/` (standalone repo — NOT in backend/)
**Status:** Working with Claude Desktop. No further changes needed for v1.

Three tools exposed via FastMCP:
- `hx_validate_requirements` — validates physics feasibility, returns token on success
- `hx_design` — starts the pipeline (requires token from validate, or runs inline validation)
- `get_design_status` — polls step progress with full output detail

**Flow enforced by MCP server instructions:**
1. Claude always calls `hx_validate_requirements` first
2. If `valid=false`: relay field-level errors to user, ask for corrections, loop
3. If `valid=true`: immediately call `hx_design` in the same turn (no user confirmation needed)

**Run:**
```bash
cd hx_mcp
python server.py
```

**Claude Desktop config** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "arken-hx": {
      "command": "/path/to/hx_mcp/.venv/bin/python",
      "args": ["server.py"],
      "cwd": "/path/to/workspace/hx_mcp",
      "env": {
        "HX_ENGINE_URL": "http://localhost:8100"
      }
    }
  }
}
```

**MCP tests to write** (`hx_mcp/tests/test_server.py` — write before demos):
```
test_validate_valid_params_returns_token      — valid params → "VALID — token: ..." in reply
test_validate_invalid_params_relays_errors    — T_hot < T_cold → error message with field detail
test_validate_engine_down_returns_message     — ConnectError → "Cannot connect" (not exception)
test_design_happy_path_returns_session_id     — valid call → session_id + stream_url in reply
test_design_engine_down_returns_message       — ConnectError → "Cannot connect" (not exception)
test_get_status_returns_step_progress         — running session → current_step/5 + outputs
test_get_status_404_returns_friendly_message  — 404 → "Session not found" (not exception)
test_flatten_output_nested_dict               — nested dict → all keys as dotted paths
```
Use `respx` to mock `httpx.AsyncClient`. Tools are plain async functions — call directly,
no FastMCP harness needed.

---

### Piece 1 — Backend: `ToolRegistry` service
**File:** `backend/app/services/tool_registry.py` (NEW)

Reads `engines.yaml` at startup. Provides Anthropic-formatted tool schemas to
`OrchestrationService`.

```python
from pathlib import Path

_DEFAULT_YAML = Path(__file__).parent.parent / "engines.yaml"

class ToolRegistry:
    def __init__(self, yaml_path: Path = _DEFAULT_YAML):
        self._load(yaml_path)

    def get_tools_for_claude(self) -> list[dict]:
        """Returns Anthropic-formatted tool schemas for enabled engines."""

    def get_tool_endpoint(self, name: str) -> dict | None:
        """Returns {endpoint, method, streaming} for a named tool."""
```

`ToolRegistry` is instantiated **once at startup** (singleton in `dependencies.py`),
not per-request.

**Updated `engines.yaml` — both tools, correct required fields:**

```yaml
engines:
  hx_engine:
    name: "Heat Exchanger Design Engine"
    base_url: "${HX_ENGINE_URL:-http://hx-engine:8100}"
    enabled: true
    health_endpoint: "/health"
    tools:
      - name: hx_validate_requirements
        description: >
          Validate heat exchanger design requirements before starting the pipeline.
          ALWAYS call this before hx_design. If valid=false, relay the errors to the
          user and ask for corrections. If valid=true, immediately call hx_design.
        endpoint: "/api/v1/hx/requirements"
        method: POST
        streaming: false
        input_schema:
          type: object
          properties:
            hot_fluid_name:   { type: string,  description: "Hot side fluid (e.g. steam, crude oil)" }
            cold_fluid_name:  { type: string,  description: "Cold side fluid (e.g. cooling water)" }
            T_hot_in_C:       { type: number,  description: "Hot side inlet temperature (°C)" }
            T_cold_in_C:      { type: number,  description: "Cold side inlet temperature (°C)" }
            m_dot_hot_kg_s:   { type: number,  description: "Hot side mass flow rate (kg/s)" }
            T_hot_out_C:      { type: number,  description: "Hot side outlet temperature (°C)" }
            T_cold_out_C:     { type: number,  description: "Cold side outlet temperature (°C)" }
            m_dot_cold_kg_s:  { type: number,  description: "Cold side mass flow rate (kg/s)" }
            P_hot_Pa:         { type: number,  description: "Hot side pressure (Pa)" }
            P_cold_Pa:        { type: number,  description: "Cold side pressure (Pa)" }
            tema_preference:  { type: string,  description: "Preferred TEMA type (AEL, BEM, etc.)" }
          required: [hot_fluid_name, cold_fluid_name, T_hot_in_C, T_cold_in_C, m_dot_hot_kg_s]

      - name: hx_design
        description: >
          Start a full heat exchanger design (Steps 1–5). Call AFTER
          hx_validate_requirements returns valid=true. Pass the token.
        endpoint: "/api/v1/hx/design"
        method: POST
        streaming: true
        input_schema:
          type: object
          properties:
            hot_fluid_name:   { type: string,  description: "Hot side fluid" }
            cold_fluid_name:  { type: string,  description: "Cold side fluid" }
            T_hot_in_C:       { type: number,  description: "Hot side inlet temperature (°C)" }
            T_cold_in_C:      { type: number,  description: "Cold side inlet temperature (°C)" }
            m_dot_hot_kg_s:   { type: number,  description: "Hot side mass flow rate (kg/s)" }
            token:            { type: string,  description: "Validation token from hx_validate_requirements" }
            raw_request:      { type: string,  description: "Full user request verbatim (optional)" }
            T_hot_out_C:      { type: number,  description: "Hot side outlet temperature (°C)" }
            T_cold_out_C:     { type: number,  description: "Cold side outlet temperature (°C)" }
            m_dot_cold_kg_s:  { type: number,  description: "Cold side mass flow rate (kg/s)" }
            P_hot_Pa:         { type: number,  description: "Hot side pressure (Pa)" }
            P_cold_Pa:        { type: number,  description: "Cold side pressure (Pa)" }
            tema_preference:  { type: string,  description: "Preferred TEMA type" }
          required: [hot_fluid_name, cold_fluid_name, T_hot_in_C, T_cold_in_C, m_dot_hot_kg_s]
```

---

### Piece 2 — Backend: Update `OrchestrationService` + `HXEngineClient`
**File:** `backend/app/services/orchestration_service.py`
**File:** `backend/app/core/engine_client.py`

#### 2a. `HXEngineClient` changes

Add `validate_requirements()`. Update `start_design()` to accept `**kwargs`.

```python
async def validate_requirements(self, **kwargs) -> dict:
    """
    POST /api/v1/hx/requirements → { valid, token, errors, warnings }.
    Returns the raw JSON dict — caller decides how to format for Claude.
    """
    if self._client is None:
        raise RuntimeError("HXEngineClient not connected")
    payload = {"user_id": "backend", **kwargs}
    resp = await self._client.post("/api/v1/hx/requirements", json=payload)
    resp.raise_for_status()
    return resp.json()

async def start_design(self, user_id: str, **kwargs) -> dict:
    """
    POST /api/v1/hx/design → { session_id, stream_url }.
    Pass all fields extracted by Claude via **kwargs (token, fluid names, temps, etc.)
    """
    if self._client is None:
        raise RuntimeError("HXEngineClient not connected")
    payload = {"user_id": user_id, **kwargs}
    resp = await self._client.post("/api/v1/hx/design", json=payload)
    resp.raise_for_status()
    return resp.json()
```

#### 2b. `OrchestrationService` changes

1. Accept `engine_client` and `tool_registry` in constructor
2. Update system prompt — two-tool capability + missing-param behavior
3. Pass `tool_registry.get_tools_for_claude()` to `create_message_stream()`
4. Replace one-shot tool dispatch with a **tool dispatch loop** (max 5 turns)

**Tool dispatch loop:**
```python
MAX_TOOL_TURNS = 5
tools = tool_registry.get_tools_for_claude()
tool_turns = 0
design_started = False
full_response = ""

while tool_turns < MAX_TOOL_TURNS:
    # Pass tools only until a design is started; after that Claude just confirms
    active_tools = tools if not design_started else []

    async with provider.create_message_stream(
        messages, tools=active_tools, system=SYSTEM_PROMPT
    ) as stream:
        async for text in stream.text_stream:
            full_response += text
            await event_emitter.emit_message_delta(request_id=request_id, delta=text, ...)
        final = await stream.get_final_message()

    if final.stop_reason != "tool_use":
        break  # Confirmation text done — exit loop

    tool_block = next(b for b in final.content if b.type == "tool_use")
    messages.append({"role": "assistant", "content": final.content})

    # ── Dispatch by tool name ────────────────────────────────────────────
    if tool_block.name == "hx_validate_requirements":
        try:
            result = await engine_client.validate_requirements(**tool_block.input)
            tool_result_content = _format_validate_result(result)  # human-readable string
            is_error = False
        except Exception as exc:
            tool_result_content = f"HX Engine unavailable: {exc}"
            is_error = True
            await event_emitter.emit_app_error(
                request_id=request_id,
                error_type="hx_engine_unavailable",
                error_message="The design engine is currently unavailable. Please try again.",
                details={"exception": str(exc)},
                recoverable=True,
            )

    elif tool_block.name == "hx_design":
        try:
            result = await engine_client.start_design(
                user_id=user_id, **tool_block.input
            )
            await event_emitter.emit_hx_design_started(
                request_id, result["session_id"], result["stream_url"]
            )
            tool_result_content = (
                f"Design started. Session: {result['session_id']}. "
                f"Stream: {result['stream_url']}"
            )
            is_error = False
            design_started = True  # Stop passing tools — next turn is confirmation only
        except Exception as exc:
            tool_result_content = f"HX Engine unavailable: {exc}"
            is_error = True
            await event_emitter.emit_app_error(
                request_id=request_id,
                error_type="hx_engine_unavailable",
                error_message="The design engine is currently unavailable. Please try again.",
                details={"exception": str(exc)},
                recoverable=True,
            )

    else:
        # Unknown tool — return error, let Claude recover
        tool_result_content = f"Unknown tool: {tool_block.name}"
        is_error = True

    messages.append({"role": "user", "content": [{
        "type": "tool_result",
        "tool_use_id": tool_block.id,
        "content": tool_result_content,
        "is_error": is_error,
    }]})
    tool_turns += 1

# full_response now contains all streamed text across turns
```

**`_format_validate_result()` helper** (module-level, not on the class):
```python
def _format_validate_result(result: dict) -> str:
    """Convert validate response dict to a string Claude can reason about."""
    if result.get("valid"):
        token = result.get("token", "")
        warnings = result.get("warnings", [])
        lines = [f"VALID — token: {token}"]
        if warnings:
            lines.append("Notes: " + "; ".join(warnings))
        lines.append("PROCEED: call hx_design now with the same parameters and token above.")
        return "\n".join(lines)
    else:
        errors = result.get("errors", [])
        lines = ["Requirements validation failed:"]
        for err in errors:
            field = err.get("field", "")
            message = err.get("message", "")
            suggestion = err.get("suggestion", "")
            lines.append(f"  • {field}: {message}")
            if suggestion:
                lines.append(f"    Suggestion: {suggestion}")
        lines.append("Ask the user to correct the above values.")
        return "\n".join(lines)
```

**Updated system prompt addition:**
```
You have access to two heat exchanger design tools:

  1. hx_validate_requirements — always call this first with the extracted parameters.
     If valid=false: relay the specific errors to the user and ask for corrections.
     If valid=true: IMMEDIATELY call hx_design in the same response — do NOT wait.

  2. hx_design — call this only after hx_validate_requirements returns valid=true.
     Pass the token from the validation result along with the same parameters.

Required minimum before calling either tool:
  - hot_fluid_name and cold_fluid_name
  - T_hot_in_C and T_cold_in_C (both inlet temps required)
  - m_dot_hot_kg_s (hot-side flow rate required)
  - at least one of: T_hot_out_C, T_cold_out_C, or m_dot_cold_kg_s

If any required parameter is missing, ask for ALL missing parameters in a single message.
Do NOT call any tool until you have the minimum required fields.
Once hx_design is called and the design starts, tell the user to watch the right panel.
```

---

### Piece 3 — Backend: `HXDesignStartedEvent` model + `emit_hx_design_started()`
**File:** `backend/app/models/events.py` (UPDATE)
**File:** `backend/app/services/event_emitter.py` (UPDATE)

#### 3a. Add to `events.py`

`EventEmitter._emit_event()` expects a `BaseEvent` instance — it calls `event.sequence = ...`
and `event.to_redis_dict()`. Passing a plain dict crashes with `AttributeError`.

Four additions needed in `events.py`:

```python
# 1. Add to EventType enum
class EventType(str, Enum):
    ...
    HX_DESIGN_STARTED = "hx_design_started"   # ADD

# 2. Add event model
#    No to_redis_dict() override needed — base class calls model_dump_json()
#    which already serializes all Pydantic fields including session_id + stream_url.
class HXDesignStartedEvent(BaseEvent):
    event_type: Literal[EventType.HX_DESIGN_STARTED] = EventType.HX_DESIGN_STARTED
    session_id: str   # explicit field — frontend reads this directly
    stream_url: str   # frontend uses this to open EventSource

# 3. Add to EVENT_TYPE_MAP so from_redis_dict() deserializes correctly on SSE replay.
#    Without this entry, from_redis_dict() falls back to BaseEvent and
#    session_id + stream_url are silently lost if the client reconnects.
EVENT_TYPE_MAP: Dict[str, Type[BaseEvent]] = {
    ...
    EventType.HX_DESIGN_STARTED: HXDesignStartedEvent,   # ADD
}

# 4. Add to Event union so type checkers recognize it
Event = Union[
    ...,
    HXDesignStartedEvent,   # ADD
]
```

#### 3b. Add to `event_emitter.py`

```python
async def emit_hx_design_started(
    self,
    request_id: str,
    session_id: str,
    stream_url: str,
) -> int:
    """Notify frontend that HX pipeline has started and where to stream from."""
    event = HXDesignStartedEvent(
        session_id=session_id,
        stream_url=stream_url,
    )
    return await self._emit_event(request_id, event)
    # session_id is a first-class field, NOT derived by parsing stream_url.
    # Any URL format change would silently break a regex approach.
```

**Known risk:** If Redis is down at emit time, `hx_design_started` is never sent to the
frontend. The design runs on the HX Engine but StepCards never update. Log at ERROR level;
consider retry or fallback in v1.1.

---

### Piece 4 — Backend: Wire dependencies
**File:** `backend/app/dependencies.py`

`ToolRegistry` is a **module-level singleton** (loaded once at startup, not per-request):

```python
_tool_registry: ToolRegistry | None = None

def get_tool_registry() -> ToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry

async def get_orchestration_service(
    redis_client  = Depends(get_redis_client),
    mongo_client  = Depends(get_mongo_client),
    event_emitter = Depends(get_event_emitter),
    engine_client = Depends(get_engine_client),    # already wired
) -> OrchestrationService:
    orchestration = OrchestrationService(
        context_manager = context_manager,
        event_emitter   = event_emitter,
        llm_provider    = get_llm_provider(),
        redis_client    = redis_client,
        engine_client   = engine_client,           # ADD
        tool_registry   = get_tool_registry(),     # ADD (singleton)
    )
```

---

### Piece 5 — Frontend: Fix `useHXStream`, remove demo, wire real HX state

#### 5a. Fix `useHXStream.js`
**File:** `frontend/src/hooks/useHXStream.js`

Two fixes required before any other frontend work:

**Fix 1 — Add `sessionId` state:**
```js
const [sessionId, setSessionId] = useState(null);

// connectStream now takes (streamUrl, sid) — both come from hx_design_started event
const connectStream = useCallback((streamUrl, sid) => {
  setSessionId(sid);          // set from event.session_id — NOT parsed from URL
  eventSourceRef.current?.close();
  setSteps(makeInitialSteps());
  setIsRunning(true);
  setCurrentStep(null);
  setDesignResult(null);
  setError(null);
  // ... rest of existing EventSource setup
}, [handleEvent]);

return { ..., sessionId, connectStream, ... };
```

**Fix 3 — Escalation payload shape:**
`respondToEscalation` currently sends the raw answer string. The HX Engine's
`POST /design/{id}/respond` expects `UserResponse`:
```python
class UserResponse(BaseModel):
    type: str           # "accept" | "override" | "skip"
    values: dict | None = None
```

Update `respondToEscalation` to wrap the answer:
```js
const respondToEscalation = useCallback(async (sessionId, response) => {
  await fetch(`${API_BASE}/v1/hx/design/${sessionId}/respond`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    // Wrap raw answer string in the UserResponse shape the HX Engine expects
    body:    JSON.stringify({ type: "override", values: { user_input: response } }),
  });
}, []);
```

**Fix 2 — URL resolution via `VITE_HX_ENGINE_URL`:**
```js
const HX_BASE = import.meta.env.VITE_HX_ENGINE_URL || '';

// Replace the existing window.location.origin line:
const fullUrl = streamUrl.startsWith('http')
  ? streamUrl
  : `${HX_BASE}${streamUrl}`;
```

Production: `VITE_HX_ENGINE_URL` is empty → relative URL → nginx → HX engine.
Dev: `VITE_HX_ENGINE_URL=http://localhost:8100` → absolute URL → HX engine directly.

#### 5b. Wire `ChatPage.jsx`
**File:** `frontend/src/pages/ChatPage.jsx`

```jsx
import { useHXStream } from '../hooks/useHXStream';

export default function ChatPage() {
  const {
    steps, isRunning, currentStep, designResult,
    sessionId, connectStream, respondToEscalation
  } = useHXStream();

  return (
    <Layout>
      <ChatPanel onHXDesignStarted={connectStream} />
      <HXPanel
        steps={steps}
        isRunning={isRunning}
        currentStep={currentStep}
        design={designResult}
        sessionId={sessionId}
        onRespond={respondToEscalation}
      />
    </Layout>
  );
}
```

#### 5c. Remove demo stub from `HXPanel.jsx`
**File:** `frontend/src/components/hx/HXPanel.jsx`

Remove:
- `DEMO_SEQUENCE` constant
- `DEMO_DESIGN` constant
- `useDemoHX` hook
- All demo mode logic in render
- Demo footer (reset button)

Replace idle state:
```jsx
{/* Idle */}
<div className="flex flex-col items-center justify-center h-full gap-3">
  <p style={{ color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)' }}
     className="text-xs text-center">
    Send a heat exchanger design request in the chat<br/>to start the pipeline
  </p>
</div>
```

Pass `sessionId` and `onRespond` to StepCard for ESCALATED steps:
```jsx
<StepCard
  ...
  data={s.state === 'ESCALATED'
    ? { ...s.data, onRespond: (answer) => onRespond(sessionId, answer) }
    : s.data}
/>
```

**EscalatedBody field name fix:** `EscalatedBody` reads `data.question` but the HX Engine
SSE emits `step_escalated` with `data.message`. Map `message → question` in `handleEvent`
when storing ESCALATED state:

```js
// In useHXStream.handleEvent, for terminal states:
updateStep(stepId, {
  state:   newState,
  elapsed: data.elapsed_s ?? null,
  data: newState === "ESCALATED"
    ? { ...data, question: data.message }   // EscalatedBody reads .question
    : data,
});
```

---

### Piece 6 — Frontend: Thread `onHXDesignStarted` callback
**File:** `frontend/src/components/chat/ChatPanel.jsx`

```jsx
export default function ChatPanel({ onHXDesignStarted }) {
  return <ChatContainer onHXDesignStarted={onHXDesignStarted} />;
}
```

**File:** `frontend/src/components/chat/ChatContainer.jsx`

Accept `onHXDesignStarted` prop. Add to `onSSEEvent` useCallback AND its dependency array:
```js
const onSSEEvent = useCallback((event) => {
  // ⚠️  ORDERING MATTERS: hx_design_started MUST come BEFORE any event-type whitelist
  //     filter. ChatContainer passes known events through a whitelist
  //     (thinking_start, message_delta, etc.). If the early-return below is placed
  //     AFTER the whitelist check, hx_design_started is silently swallowed.
  if (event.event_type === 'hx_design_started') {
    // Pass both stream_url AND session_id — session_id is explicit in the event,
    // not parsed from the URL. connectStream signature: (streamUrl, sessionId)
    onHXDesignStarted?.(event.stream_url, event.session_id);
    return;  // ← must return here, before the whitelist check below
  }
  // ... existing whitelist check + handleSSEEvent dispatch
}, [onHXDesignStarted, dispatch, ...existingDeps]);
// ⚠️  onHXDesignStarted MUST be in the dep array. If omitted, the callback
//     captures a stale closure and connectStream silently does nothing.
```

`onHXDesignStarted?.()` uses optional chaining — safe if prop not passed.

---

### Piece 7 — Frontend: Local dev environment
**File:** `frontend/.env.local` (NEW — do not commit)

```
VITE_HX_ENGINE_URL=http://localhost:8100
```

---

## 5. File Change Summary

| File | Change Type | Piece |
|------|-------------|-------|
| `hx_mcp/tests/test_server.py` | NEW (tests) | 0 |
| `backend/engines.yaml` | UPDATE (schema) | 1 |
| `backend/app/services/tool_registry.py` | NEW | 1 |
| `backend/app/core/engine_client.py` | UPDATE (add validate_requirements, **kwargs) | 2 |
| `backend/app/services/orchestration_service.py` | UPDATE (tool dispatch loop) | 2 |
| `backend/app/models/events.py` | UPDATE (add EventType.HX_DESIGN_STARTED + HXDesignStartedEvent) | 3 |
| `backend/app/services/event_emitter.py` | UPDATE (add emit_hx_design_started) | 3 |
| `backend/app/dependencies.py` | UPDATE (wire engine_client + tool_registry) | 4 |
| `frontend/src/hooks/useHXStream.js` | UPDATE (sessionId + URL fix) | 5 |
| `frontend/src/components/hx/HXPanel.jsx` | UPDATE (remove demo) | 5 |
| `frontend/src/pages/ChatPage.jsx` | UPDATE (wire useHXStream) | 5 |
| `frontend/src/components/chat/ChatPanel.jsx` | UPDATE (onHXDesignStarted prop) | 6 |
| `frontend/src/components/chat/ChatContainer.jsx` | UPDATE (hx_design_started handler) | 6 |
| `frontend/.env.local` | NEW | 7 |

**Not touched:** HX engine, nginx config, docker-compose, StepCard, `hx_mcp/server.py` (done).

---

## 6. SSE Event Flow Diagram

```
PATH 2 — Backend Chat SSE (Redis → /api/v1/chat/{id}/stream)
  thinking_start
  message_delta × N          ← Claude typing (Turn 1: before validate tool call)
  [tool dispatch: hx_validate_requirements]
  [tool dispatch: hx_design]
  hx_design_started           ← NEW: triggers HX stream connection in frontend
  message_delta × N          ← Claude typing (confirmation text)
  message_final
  thinking_end

  On validation failure:
  message_delta × N          ← Claude relaying errors to user (no hx_design_started)

PATH 1 & 2 — HX Engine SSE (/api/v1/hx/design/{id}/stream)
  step_started  { step_id: 1, step_name: "Parse & Validate Requirements" }
  step_approved { step_id: 1, outputs: {...}, confidence: 0.92 }
  step_started  { step_id: 2, step_name: "Calculate Heat Duty" }
  step_approved { step_id: 2, outputs: { Q_W: 2410000 } }
  step_started  { step_id: 3, step_name: "Fluid Properties" }
  step_escalated { step_id: 3, message: "Cannot resolve fluid for 'crude oil'..." }
    → PATH 2: user responds inline in StepCard
    → PATH 1: engineer asks Claude Desktop → calls get_design_status
  design_complete { summary: { Q_W, LMTD_K, A_m2, tema_type, ... } }
```

---

## 7. Open Questions / Deferred

| Item | Decision |
|------|----------|
| MCP escalation response tool | Deferred. `get_design_status` covers read. A `respond_to_escalation` MCP tool (POST `/respond`) can be added in v1.1 once we know how engineers want to answer escalations from Claude Desktop. |
| `hx_get_fluid_properties`, `hx_suggest_geometry` in engines.yaml | Not wired in v1. Only `hx_validate_requirements` and `hx_design` dispatched. Others ignored. |
| Session persistence (resume after page reload) | Deferred. Frontend polls `/design/{id}/status` on reload — wired later. |
| Tool call history not persisted to MongoDB | By design for v1. `OrchestrationService` saves only the final text (`full_response`) as the assistant message. Tool use blocks and tool result blocks are in-memory only. If the user reloads, Claude loses context about the previous design run (won't know a session is already running). Acceptable for private beta — track session state separately in v1.1. |
| Multi-HX designs in one conversation | Deferred. `useHXStream` holds one stream at a time. |
| Auth on HX stream URL | EventSource from frontend can't send headers. nginx doesn't require auth on stream path. Fine for private beta. |
| `emit_hx_design_started` Redis failure | Log at ERROR level for v1. If Redis is down, design runs on HX engine but frontend never connects — add retry or fallback in v1.1. |
| MCP server packaging | Currently run via `python server.py`. Could be packaged as a standalone binary later for easier Claude Desktop distribution. |
| Max tool turns hit (validate loop) | If `MAX_TOOL_TURNS=5` is reached without `design_started=True`, the loop exits. Claude's last message_delta tells the user what happened. No silent failure. |

---

## 8. Build Order

Path 1 (MCP) is done. Build in this sequence:

```
Step 0 (do first): Write MCP server tests
  hx_mcp/tests/test_server.py — 8 tests, respx mocks
  → Validates the working MCP path before touching production backend

Backend (run HX Engine first: uvicorn hx_engine.app.main:app --port 8100):

1. engines.yaml update         (no deps — do first, schema is source of truth)
2. tool_registry.py            (depends on 1)
3. event_emitter.py update     (no deps)
4. engine_client.py update     (no deps — add validate_requirements + **kwargs)
5. orchestration_service.py    (depends on 2 + 3 + 4)
6. dependencies.py             (depends on 2 + 5)
   → Test with curl/Postman before touching frontend

Frontend (no backend dependency to start):

7. useHXStream.js fixes        (sessionId + URL — do before anything else)
8. HXPanel.jsx cleanup         (remove demo)
9. ChatPage.jsx                (depends on 7 + 8)
10. ChatPanel + ChatContainer  (depends on 9)
11. .env.local                 (independent)
```

**Parallel lanes:**
- Lane A (Backend): steps 1–6
- Lane B (Frontend): steps 7–11
- Lane C (Tests): MCP tests (step 0), fully independent
- Launch A + B + C in parallel. Merge. Then integration smoke test.

---

## 9. Test Plan

### MCP server tests (write first — live code, no tests)

**`hx_mcp/tests/test_server.py`** (NEW)
Use `respx` to mock `httpx.AsyncClient`. Call async tool functions directly.
```
test_validate_valid_params_returns_token      — valid params → "VALID — token: ..." in reply
test_validate_invalid_params_relays_errors    — T_hot < T_cold → field-level error message
test_validate_engine_down_returns_message     — ConnectError → "Cannot connect" (not exception)
test_design_happy_path_returns_session_id     — valid call → session_id + stream_url in reply
test_design_engine_down_returns_message       — ConnectError → "Cannot connect" (not exception)
test_get_status_returns_step_progress         — running session → current_step/5 + step outputs
test_get_status_404_returns_friendly_message  — 404 → "Session 'x' not found" message
test_flatten_output_nested_dict               — nested dict → all keys as dotted paths in output
```

### Backend tests (pytest, existing infrastructure)

**`backend/tests/unit/test_tool_registry.py`** (NEW)
```
test_loads_hx_validate_requirements    — ToolRegistry reads hx_validate_requirements from engines.yaml
test_loads_hx_design                   — ToolRegistry reads hx_design from engines.yaml
test_filters_disabled_tools            — engine with enabled=false not included
test_missing_yaml_raises               — FileNotFoundError when YAML not found
test_get_tool_endpoint_found           — returns {endpoint, method, streaming}
test_get_tool_endpoint_not_found       — returns None for unknown tool name
```

**`backend/tests/unit/test_orchestration_tool_path.py`** (NEW)
Uses `unittest.mock` to stub `AsyncAnthropic` and `HXEngineClient`.
```
test_no_hx_params_no_tool_call
  — mock returns stop_reason="end_turn" → text_stream flows, no engine call

test_validate_called_on_tool_use
  — mock returns stop_reason="tool_use", name="hx_validate_requirements"
  → engine_client.validate_requirements() called once

test_valid_true_calls_hx_design_next_turn
  — validate returns valid=true + token → next mock turn has name="hx_design"
  → engine_client.start_design() called once

test_valid_false_relays_errors_no_design
  — validate returns valid=false → no start_design() call
  → message_delta streamed with error text

test_emits_hx_design_started_event
  — start_design() succeeds → event_emitter.emit_hx_design_started() called with session_id + stream_url

test_engine_down_on_validate_emits_app_error
  — validate_requirements() raises RuntimeError → emit_app_error called

test_engine_down_on_design_emits_app_error
  — start_design() raises RuntimeError → emit_app_error called, no hx_design_started

test_max_tool_turns_guard
  — mock always returns stop_reason="tool_use" → loop exits after MAX_TOOL_TURNS=5
  → no infinite loop

test_confirmation_streamed_after_design_starts
  — after hx_design_started emitted, next turn has no tools, streams confirmation text
```

**`backend/tests/unit/test_event_emitter_hx.py`** (NEW)
```
test_emit_hx_design_started_fields
  — emitted event has event_type="hx_design_started", session_id, stream_url as explicit fields

test_hx_design_started_event_model
  — HXDesignStartedEvent serializes session_id and stream_url via model_dump_json()
  — EventType.HX_DESIGN_STARTED == "hx_design_started"
  — EVENT_TYPE_MAP[EventType.HX_DESIGN_STARTED] is HXDesignStartedEvent
  — from_redis_dict() round-trips session_id and stream_url correctly (SSE replay)
```

**`backend/tests/unit/test_engine_client_hx.py`** (NEW)
Uses `respx` to mock httpx.
```
test_validate_requirements_happy_path   — POST /requirements → returns dict
test_validate_requirements_raises_on_4xx — 422 → raises HTTPStatusError
test_start_design_passes_all_kwargs     — all structured fields included in POST body
test_start_design_raises_when_not_connected — RuntimeError if client is None
```

### Frontend tests (Vitest — per TODOS.md "Frontend Test Infrastructure")

**`frontend/src/hooks/__tests__/useHXStream.test.js`** (NEW)
```
test_connectStream_stores_session_id         — connectStream(url, "abc123") → sessionId === "abc123"
test_full_url_built_with_vite_env_var        — VITE_HX_ENGINE_URL=http://host:8100 prepended to relative URL
test_absolute_url_unchanged                  — http://... passes through as-is
test_session_id_reset_on_new_connect         — second connectStream("...", "xyz") → sessionId === "xyz"
test_escalated_event_maps_message_to_question — step_escalated data.message → stored as data.question
test_respond_escalation_sends_correct_shape  — respondToEscalation posts { type: "override", values: { user_input: "..." } }
```

### Integration smoke test (backend, requires HX Engine running)

**`backend/tests/integration/test_integration_hx_wiring.py`** (NEW)
Marked `@pytest.mark.integration` — requires live HX Engine at `HX_ENGINE_URL`.
```
test_full_wiring_smoke
  Given: HX Engine running, valid design params in chat message
  When:  POST /api/v1/chat with full HX params
  Then:  a) hx_design_started SSE event emitted (session_id + stream_url present)
         b) GET /api/v1/hx/design/{session_id}/status returns current_step >= 1
  Proves validate → design → hx_design_started are wired correctly end-to-end.

test_engine_down_returns_error_event
  Given: HX_ENGINE_URL points to a non-running port
  When:  POST /api/v1/chat with full HX params
  Then:  app_error SSE event emitted, no hx_design_started event
```

Run with: `pytest tests/integration/ -m integration --hx-engine-url=http://localhost:8100`

### E2E browser tests (deferred — flag for post-v1)
```
[→E2E] Full browser flow: user provides params → validate → design starts → 5 StepCards complete
[→E2E] Validation failure: user provides bad params → error relayed → user corrects → design starts
[→E2E] ESCALATED step → user responds inline → pipeline resumes
```

---

## 10. Dependencies to Add

```bash
# backend — no new dependencies needed
# HXEngineClient already uses httpx; ToolRegistry uses pyyaml (already installed)

# hx_mcp — add test dependencies
pip install pytest pytest-asyncio respx
```

Add `pytest`, `pytest-asyncio`, `respx` to `hx_mcp/pyproject.toml` dev dependencies.

---

*This plan supersedes the integration notes in ARKEN_MASTER_PLAN.md §11 (Backend Changes) for the v1 scope.*

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 3+review2 | CLEAR (PLAN) | 7+7 issues found and resolved |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |

**CROSS-MODEL (2026-03-29):** Outside voice raised 8 findings. 2 critical bugs surfaced and resolved (tool dispatch loop, missing validate_requirements() on HXEngineClient). 1 false positive (nginx SSE — already handled). 5 acknowledged/deferred.

**ISSUES RESOLVED IN REVIEW PASS 1 (2026-03-29):**
1. Two-step validate→design flow adopted for Path 2 — `hx_validate_requirements` added to `engines.yaml` + `ToolRegistry`
2. `HXEngineClient.start_design()` updated to `**kwargs` — all structured fields pass through
3. `engines.yaml` schema updated — required fields now match MCP server type annotations
4. `useHXStream.connectStream()` fixed to `(streamUrl, sessionId)` — sessionId tracked in hook state
5. URL resolution fixed — `VITE_HX_ENGINE_URL` replaces `window.location.origin`
6. MCP server tests spec added — 8 tests, write before demos
7. **(CRITICAL)** OrchestrationService tool dispatch loop — `while tool_turns < MAX_TOOL_TURNS`, `tools=[]` after design starts

**ISSUES RESOLVED IN REVIEW PASS 2 (2026-03-29):**
8. **(BUG)** `emit_hx_design_started` passed a plain dict — now uses `HXDesignStartedEvent(BaseEvent)` model; `EventType.HX_DESIGN_STARTED` added to enum; `EVENT_TYPE_MAP` and `Event` union updated so SSE replay doesn't lose `session_id`/`stream_url`
9. **(BUG)** `respondToEscalation` sent raw string — now wraps in `{ type: "override", values: { user_input: response } }` to match HX Engine `UserResponse` model
10. **(GAP)** `EscalatedBody` reads `data.question`, SSE emits `data.message` — `handleEvent` now maps `message → question` when storing ESCALATED state
11. **(ORDERING TRAP)** `hx_design_started` interception in `onSSEEvent` documented explicitly above the whitelist filter — silently swallowed if placed after it
12. **(GAP)** `events.py` changes (EventType enum + HXDesignStartedEvent + EVENT_TYPE_MAP + Event union) added to File Change Summary and test plan
13. Tool call history not persisted to MongoDB — acknowledged and deferred to v1.1 in Open Questions

**VERDICT:** ENG CLEARED — plan updated, ready to implement.
