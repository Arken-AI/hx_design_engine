# ARKEN AI — Frontend + Backend + HX Engine Integration Plan (v1)

**Target:** Early release connecting all three services through Steps 1–5.
**Date:** 2026-03-27
**Scope:** Chat → parameter extraction → HX pipeline → live step cards in UI
**Updated:** Added MCP server for Claude Desktop testing (2026-03-27)

---

## 1. What's Already Built (No Changes Needed)

| Component | Status | Notes |
|-----------|--------|-------|
| HX Engine Steps 1–5 | ✅ Complete | 450/450 tests passing |
| `POST /api/v1/hx/design` | ✅ Ready | Returns `{session_id, stream_url}` |
| `GET /api/v1/hx/design/{id}/stream` | ✅ Ready | SSE endpoint |
| `GET /api/v1/hx/design/{id}/status` | ✅ Ready | Poll fallback |
| `POST /api/v1/hx/design/{id}/respond` | ✅ Ready | Escalation response |
| `HXEngineClient.start_design()` | ✅ Ready | In backend, just unwired |
| `ClaudeProvider.create_message_stream(tools=...)` | ✅ Ready | Already accepts tool schemas |
| `convert_tools_to_anthropic()` | ✅ Ready | Already written |
| `engines.yaml` tool registry | ✅ Ready | Defines `hx_design` tool |
| `useHXStream` hook | ✅ Ready | Manages SSE state |
| `HXPanel` + `StepCard` components | ✅ Ready | Just unwired from real data |
| `StepCard` escalation UI (`EscalatedBody`) | ✅ Ready | Input + submit built |
| nginx routing `/api/v1/hx/` → HX engine | ✅ Ready | Direct, no backend in path |

---

## 2. Architecture: Two Paths, One HX Engine

Both the MCP server (testing) and the production backend (chat UI) call the same HX Engine.
Tool schemas are defined once in `engines.yaml` and shared between both paths.

```
┌─────────────────────────────────────────────────────────────┐
│  PATH 1: Testing via Claude Desktop                         │
│                                                             │
│  Claude Desktop                                             │
│       │  MCP stdio transport                               │
│       ▼                                                     │
│  MCP Server  (backend/app/mcp/server.py)                    │
│       │  HTTP  POST /api/v1/hx/design                      │
│       ▼                                                     │
│  HX Engine :8100  →  { session_id, stream_url }            │
│                                                             │
│  Claude Desktop reply:                                      │
│    "Design started (session: abc123).                       │
│     Stream: http://localhost:8100/api/v1/hx/.../stream      │
│     Ask me for status anytime."                             │
│                                                             │
│  Engineer: "what's the status?"                             │
│  Claude Desktop calls get_design_status(session_id)         │
│       │  GET /api/v1/hx/design/{id}/status                 │
│       ▼                                                     │
│  Returns: step 3/5 complete, waiting_for_user: false        │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  PATH 2: Production via Browser Chat                        │
│                                                             │
│  Frontend Chat → Backend :8001                             │
│       │  Anthropic API with tool schemas (engines.yaml)    │
│       │  Claude calls hx_design → tool_use block           │
│       ▼                                                     │
│  HXEngineClient.start_design()                              │
│       ├── emit hx_design_started → Chat SSE → Frontend     │
│       └── Frontend opens HX Engine SSE stream directly     │
│              /api/v1/hx/design/{id}/stream  (via nginx)     │
│              StepCards update live in HXPanel               │
└─────────────────────────────────────────────────────────────┘

SHARED LAYER
  engines.yaml  ──→  ToolRegistry (backend, Path 2)
               └──→  MCP Server  (Path 1, reads same YAML)
  HX Engine :8100  ←  both paths call the same endpoints
```

### Why MCP + native tool use (not MCP only)

MCP stdio transport is designed for Claude agents (Claude Desktop, Claude Code) that run
tools as subprocesses. The production backend is a Python service calling the Anthropic API
directly — passing tool schemas in `messages.create()` is the right pattern there. MCP adds
an extra process hop with no benefit in that context.

Both approaches use identical tool schemas from `engines.yaml`. The MCP server is a
thin adapter around the same `HXEngineClient` the backend already has.

---

## 3. User Flows

### Happy path — browser chat (production)
```
User: "design an HX for steam 180°C → 100°C, cooling water 25°C → 45°C, 12 kg/s"
  ↓
Claude: extracts all params → calls hx_design tool
  ↓
Backend: HXEngineClient.start_design() → { session_id, stream_url }
  ↓
Backend: emit hx_design_started { session_id, stream_url } via Chat SSE
  ↓
Claude: streams "Starting your design — watch the progress panel on the right."
  ↓
Frontend: ChatContainer receives hx_design_started → connectStream(stream_url)
  ↓
HX Engine SSE: step_started → step_approved / step_corrected / step_warning
  ↓
StepCards update live → design_complete → DesignSummary shown
```

### Happy path — Claude Desktop (testing)
```
Engineer: "design an HX for steam 180°C → 100°C, cooling water 25°C → 45°C, 12 kg/s"
  ↓
Claude Desktop: calls MCP tool hx_design (via stdio to MCP server)
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
   - Flow rate (at least one side)
   - Operating pressures (if known)"
  ↓
User provides → Claude calls tool → pipeline starts
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

### Piece 0 — MCP Server for Claude Desktop (NEW)
**File:** `backend/app/mcp/server.py` (NEW)
**File:** `backend/app/mcp/__init__.py` (NEW)
**Dependency:** `mcp` Python package (Anthropic's MCP SDK)

Two tools exposed:

**Tool 1: `hx_design`** — starts the pipeline
```python
@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "hx_design":
        resp = await http_client.post(
            f"{HX_ENGINE_URL}/api/v1/hx/design",
            json={
                "raw_request": arguments.get("raw_request", ""),
                "user_id":     "claude-desktop",
                **{k: v for k, v in arguments.items() if k != "raw_request"},
            }
        )
        data = resp.json()
        stream_url = f"{HX_ENGINE_URL}{data['stream_url']}"
        return [TextContent(type="text", text=(
            f"Design started.\n"
            f"Session ID: {data['session_id']}\n"
            f"Live stream: {stream_url}\n"
            f"Ask me for status updates."
        ))]
```

**Tool 2: `get_design_status`** — polls progress
```python
    if name == "get_design_status":
        session_id = arguments["session_id"]
        resp = await http_client.get(
            f"{HX_ENGINE_URL}/api/v1/hx/design/{session_id}/status"
        )
        status = resp.json()
        return [TextContent(type="text", text=json.dumps(status, indent=2))]
```

**Run the MCP server:**
```bash
cd backend
python -m app.mcp.server
```

**Claude Desktop config** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "arken-hx": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/path/to/workspace/backend",
      "env": {
        "HX_ENGINE_URL": "http://localhost:8100",
        "ENGINES_YAML_PATH": "/path/to/workspace/backend/engines.yaml"
      }
    }
  }
}
```

MCP server has no dependency on the backend package. Only needs `mcp`, `httpx`, and
`pyyaml` installed. Can run against any HX Engine instance — local, staging, or production
— by changing `HX_ENGINE_URL`.

**Runtime dependencies (standalone — no backend package needed):**
```
mcp       ← Anthropic MCP SDK (stdio transport)
httpx     ← call HX Engine HTTP API
pyyaml    ← read engines.yaml
```

**Schema loading** — MCP server reads `engines.yaml` directly (does NOT import ToolRegistry).
Both ToolRegistry and MCP server read the same YAML file independently. Schema is defined
once; both stay in sync automatically.

```python
import os, yaml, httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

ENGINES_YAML = os.environ.get("ENGINES_YAML_PATH", "engines.yaml")
HX_ENGINE_URL = os.environ.get("HX_ENGINE_URL", "http://localhost:8100")

def _load_tool_schema(name: str) -> dict:
    with open(ENGINES_YAML) as f:
        cfg = yaml.safe_load(f)
    for engine in cfg["engines"].values():
        for tool in engine.get("tools", []):
            if tool["name"] == name:
                return tool
    raise KeyError(f"Tool {name!r} not found in engines.yaml")
```

**Tool schemas** (read from `engines.yaml` — same file as ToolRegistry uses):
- `hx_design` — identical schema to Piece 1 (single source of truth: `engines.yaml`)
- `get_design_status` — `{ "session_id": { "type": "string" } }`

---

### Piece 1 — Backend: `ToolRegistry` service
**File:** `backend/app/services/tool_registry.py` (NEW)

Reads `engines.yaml` at startup. Used by both `OrchestrationService` (Path 2) and optionally
the MCP server (Path 1) to keep schemas in sync.

```python
from pathlib import Path

# Resolves to backend/engines.yaml regardless of working directory
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
not per-request, to avoid reading YAML on every chat message.

**Tool schema for `hx_design`:**
```json
{
  "name": "hx_design",
  "description": "Run a full heat exchanger design. Call this when the user provides enough parameters to start a design.",
  "input_schema": {
    "type": "object",
    "properties": {
      "raw_request":    { "type": "string", "description": "Full user request verbatim" },
      "T_hot_in_C":     { "type": "number", "description": "Hot side inlet temperature (°C)" },
      "T_hot_out_C":    { "type": "number", "description": "Hot side outlet temperature (°C)" },
      "T_cold_in_C":    { "type": "number", "description": "Cold side inlet temperature (°C)" },
      "T_cold_out_C":   { "type": "number", "description": "Cold side outlet temperature (°C)" },
      "hot_fluid_name": { "type": "string", "description": "Hot side fluid (e.g. steam, crude oil)" },
      "cold_fluid_name":{ "type": "string", "description": "Cold side fluid (e.g. cooling water)" },
      "m_dot_hot_kg_s": { "type": "number", "description": "Hot side mass flow rate (kg/s)" },
      "m_dot_cold_kg_s":{ "type": "number", "description": "Cold side mass flow rate (kg/s)" },
      "P_hot_Pa":       { "type": "number", "description": "Hot side pressure (Pa)" },
      "P_cold_Pa":      { "type": "number", "description": "Cold side pressure (Pa)" },
      "tema_preference":{ "type": "string", "description": "Preferred TEMA type (AEL, BEM, etc.)" }
    },
    "required": ["raw_request"]
  }
}
```

---

### Piece 2 — Backend: Update `OrchestrationService`
**File:** `backend/app/services/orchestration_service.py`

**Changes:**
1. Accept `engine_client` and `tool_registry` in constructor
2. Update system prompt — tool capability + missing-param behavior
3. Pass `tool_registry.get_tools_for_claude()` to `create_message_stream()`
4. Streaming loop: keep `text_stream` for live typing, check `stop_reason` after
5. On `tool_use` with `name == "hx_design"`:
   - Call `engine_client.start_design(...)`
   - Emit `hx_design_started` via EventEmitter
   - Send `tool_result` back to Claude
   - Stream Claude's confirmation text (second turn)
6. HX Engine down: emit `app_error` event, don't raise unhandled exception

**Streaming loop (preserves live text streaming AND catches tool calls):**
```python
# Turn 1: stream text + detect tool call
async with provider.create_message_stream(messages, tools=tools, system=...) as stream:
    async for text in stream.text_stream:          # live streaming still works
        await event_emitter.emit_message_delta(...)
    final = await stream.get_final_message()

if final.stop_reason == "tool_use":
    # Extract tool_use block, dispatch, emit hx_design_started
    tool_block = next(b for b in final.content if b.type == "tool_use")
    try:
        result = await engine_client.start_design(
            raw_request=tool_block.input.get("raw_request", ""),
            user_id=user_id,
            **{k: v for k, v in tool_block.input.items() if k != "raw_request"},
        )
        await event_emitter.emit_hx_design_started(
            request_id, result["session_id"], result["stream_url"]
        )
        tool_result_content = json.dumps(result)
        is_error = False
    except Exception as exc:
        tool_result_content = f"HX Engine unavailable: {exc}"
        is_error = True
        # Also emit SSE error toast so user sees it even if they miss the chat message
        await event_emitter.emit_app_error(
            request_id=request_id,
            error_type="hx_engine_unavailable",
            error_message="The design engine is currently unavailable. Please try again.",
            details={"exception": str(exc)},
            recoverable=True,
        )

    # Turn 2: send tool_result, get Claude's follow-up text
    messages_with_result = messages + [
        {"role": "assistant", "content": final.content},
        {"role": "user",      "content": [{"type": "tool_result",
                                            "tool_use_id": tool_block.id,
                                            "content": tool_result_content,
                                            "is_error": is_error}]},
    ]
    async with provider.create_message_stream(messages_with_result, system=...) as stream2:
        async for text in stream2.text_stream:
            await event_emitter.emit_message_delta(...)
        final2 = await stream2.get_final_message()
    full_response = final2.content[0].text
```

**Updated system prompt addition:**
```
You have access to a heat exchanger design tool (hx_design).

Call it when the user provides enough information to start a design. Required minimum:
- Hot and cold fluid names
- At least one side's inlet and outlet temperatures
- At least one flow rate

If any of these are missing, ask for ALL missing parameters in a single message.
Do NOT call the tool until you have the minimum required fields.
Once the tool is called, tell the user the design has started and to watch the right panel.
```

---

### Piece 3 — Backend: `emit_hx_design_started()` on EventEmitter
**File:** `backend/app/services/event_emitter.py`

```python
async def emit_hx_design_started(
    self,
    request_id: str,
    session_id: str,
    stream_url: str,
) -> int:
    """Notify frontend that HX pipeline has started and where to stream from."""
    return await self._emit_event(request_id, {
        "event_type": "hx_design_started",
        "session_id": session_id,   # explicit field — frontend reads this directly
        "stream_url": stream_url,   # frontend uses this to open EventSource
    })
    # session_id is a first-class field, NOT derived by parsing stream_url.
    # Any URL format change would silently break a regex approach.
```

---

### Piece 4 — Backend: Wire dependencies
**File:** `backend/app/dependencies.py`

`ToolRegistry` is a **module-level singleton** (loaded once at import time, not per-request):

```python
# Module-level singleton — reads engines.yaml once at startup
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
    engine_client = Depends(get_engine_client),    # ADD
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

### Piece 5 — Frontend: Remove demo stub, wire real HX state
**File:** `frontend/src/pages/ChatPage.jsx`

```jsx
import { useHXStream } from '../hooks/useHXStream';

export default function ChatPage() {
  const {
    steps, isRunning, currentStep, designResult,
    sessionId, connectStream, respondToEscalation
  } = useHXStream();

  // connectStream(streamUrl, sessionId) — both args from hx_design_started event
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

**File:** `frontend/src/hooks/useHXStream.js`

Add `sessionId` to returned state. Read it from the `hx_design_started` event directly
(not from the stream URL — session_id is now a first-class event field):
```js
const [sessionId, setSessionId] = useState(null);

// In connectStream — called with (streamUrl, sessionId) from ChatContainer:
const connectStream = useCallback((streamUrl, sid) => {
  setSessionId(sid);  // set from event.session_id, not URL parsing
  // ... rest of existing connectStream logic
}, [...]);

return { ..., sessionId, ... };
```

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
  if (event.event_type === 'hx_design_started') {
    // Pass both stream_url AND session_id — session_id is explicit in the event,
    // not parsed from the URL. connectStream signature: (streamUrl, sessionId)
    onHXDesignStarted?.(event.stream_url, event.session_id);
    return;
  }
  // ... rest of existing handler
}, [onHXDesignStarted, dispatch, ...existingDeps]);
// ⚠️  onHXDesignStarted MUST be in the dep array. If omitted, the callback
//     captures a stale closure and connectStream silently does nothing.
```

`onHXDesignStarted?.()` uses optional chaining — safe if prop not passed.

---

### Piece 7 — Frontend: Local dev environment
**File:** `frontend/.env.local`

```
VITE_HX_ENGINE_URL=http://localhost:8100
```

**File:** `frontend/src/hooks/useHXStream.js`

```js
const HX_BASE = import.meta.env.VITE_HX_ENGINE_URL || '';

const fullUrl = streamUrl.startsWith('http')
  ? streamUrl
  : `${HX_BASE}${streamUrl}`;
```

Production: `VITE_HX_ENGINE_URL` is empty → relative URL → nginx → HX engine.
Dev: absolute URL → HX engine at :8100 directly.

---

## 5. File Change Summary

| File | Change Type | Piece |
|------|-------------|-------|
| `backend/app/mcp/__init__.py` | NEW | 0 |
| `backend/app/mcp/server.py` | NEW | 0 |
| `backend/app/services/tool_registry.py` | NEW | 1 |
| `backend/app/services/orchestration_service.py` | UPDATE | 2 |
| `backend/app/services/event_emitter.py` | UPDATE | 3 |
| `backend/app/dependencies.py` | UPDATE | 4 |
| `frontend/src/pages/ChatPage.jsx` | UPDATE | 5 |
| `frontend/src/hooks/useHXStream.js` | UPDATE | 5 |
| `frontend/src/components/hx/HXPanel.jsx` | UPDATE (remove demo) | 5 |
| `frontend/src/components/chat/ChatPanel.jsx` | UPDATE | 6 |
| `frontend/src/components/chat/ChatContainer.jsx` | UPDATE | 6 |
| `frontend/.env.local` | NEW | 7 |

**Not touched:** HX engine, nginx config, docker-compose, StepCard, SSE event models.

---

## 6. SSE Event Flow Diagram

```
PATH 2 — Backend Chat SSE (Redis → /api/v1/chat/{id}/stream)
  thinking_start
  message_delta × N          ← Claude typing (Turn 1: before tool call)
  hx_design_started           ← NEW: triggers HX stream connection in frontend
  message_delta × N          ← Claude typing (Turn 2: confirmation text)
  message_final
  thinking_end

PATH 1 & 2 — HX Engine SSE (/api/v1/hx/design/{id}/stream)
  step_started  { step_id: 1, step_name: "Parse & Validate Requirements" }
  step_approved { step_id: 1, outputs: {...}, confidence: 0.92 }
  step_started  { step_id: 2, step_name: "Calculate Heat Duty" }
  step_approved { step_id: 2, outputs: { Q_W: 2410000 } }
  step_started  { step_id: 3, step_name: "Fluid Properties" }
  step_escalated { step_id: 3, message: "Cannot resolve fluid for 'crude oil'..." }
    → PATH 2: user responds inline in StepCard
    → PATH 1: engineer asks Claude Desktop → calls get_design_status or respond tool
  design_complete { summary: { Q_W, LMTD_K, A_m2, tema_type, ... } }
```

---

## 7. Open Questions / Deferred

| Item | Decision |
|------|----------|
| MCP escalation response tool | Deferred. `get_design_status` covers read. A `respond_to_escalation` MCP tool (POST `/respond`) can be added in v1.1 once we know how engineers want to answer escalations from Claude Desktop. |
| `tools_endpoint: /api/v1/hx/tools` in engines.yaml | Not implemented. Both ToolRegistry and MCP server read YAML directly. Dynamic tool discovery is post-beta. |
| `hx_get_fluid_properties`, `hx_suggest_geometry` in engines.yaml | Not wired in v1. Only `hx_design` dispatched. Others ignored. |
| Session persistence (resume after page reload) | Deferred. Frontend polls `/design/{id}/status` on reload — wired later. |
| Multi-HX designs in one conversation | Deferred. `useHXStream` holds one stream at a time. |
| Auth on HX stream URL | EventSource from frontend can't send headers. nginx doesn't require auth on stream path. Fine for private beta. |
| MCP server scope | **Local dev tool only** — for testing HX pipeline via Claude Desktop without a browser. Not a production path. No process supervision, restart policy, or auth needed. If this ever becomes a production path, revisit. |
| MCP server packaging | Currently run via `python -m app.mcp.server`. Could be packaged as a standalone binary later for easier Claude Desktop distribution. |

---

## 8. Build Order

Build in this sequence:

```
Backend (run HX Engine first: uvicorn hx_engine.app.main:app --port 8100):

1. tool_registry.py          (no deps)
2. event_emitter.py update   (no deps)
3. mcp/server.py             (no deps on 1-2 — can build in parallel)
   → Test immediately with Claude Desktop before touching production backend
4. orchestration_service.py  (depends on 1 + 2)
5. dependencies.py           (depends on 1 + 4)

Frontend (no backend dependency to start):

6. useHXStream.js update     (add sessionId)
7. HXPanel.jsx cleanup       (remove demo)
8. ChatPage.jsx              (depends on 6 + 7)
9. ChatPanel + ChatContainer (depends on 8)
10. .env.local               (independent)
```

**Recommended test sequence:**
1. Build MCP server (step 3) → test with Claude Desktop → validate HX pipeline end-to-end
2. Build production backend (steps 4-5) → test with curl/Postman
3. Build frontend wiring (steps 6-10) → test full browser flow

This means you can validate the entire HX pipeline via Claude Desktop BEFORE writing
a single line of frontend code.

---

## 9. Test Plan (all 24 paths)

### Backend tests (pytest, existing infrastructure)

**`backend/tests/unit/test_tool_registry.py`** (NEW)
```
test_loads_enabled_tools          — ToolRegistry reads hx_design from engines.yaml
test_filters_disabled_tools       — engine with enabled=false not included
test_missing_yaml_raises          — FileNotFoundError when YAML not found
test_get_tool_endpoint_found      — returns {endpoint, method, streaming}
test_get_tool_endpoint_not_found  — returns None for unknown tool name
```

**`backend/tests/unit/test_orchestration_tool_path.py`** (NEW)
Uses `unittest.mock` to stub `AsyncAnthropic` and `HXEngineClient`.
```
test_no_hx_params_no_tool_call        — mock Anthropic returns stop_reason="end_turn"
                                         → text_stream flows, no engine call
test_hx_params_calls_start_design     — mock Anthropic returns stop_reason="tool_use"
                                         → engine_client.start_design() called once
test_emits_hx_design_started_event    — after start_design(), event_emitter gets
                                         emit_hx_design_started(session_id, stream_url)
test_engine_down_emits_app_error      — start_design() raises RuntimeError
                                         → emit_app_error called
test_engine_down_claude_gets_error    — start_design() raises
                                         → tool_result has is_error=True
test_second_turn_streams_confirmation — after tool_result, second stream called
                                         → confirmation text emitted as message_delta
```

**`backend/tests/unit/test_event_emitter_hx.py`** (NEW)
```
test_emit_hx_design_started_fields    — event dict has event_type, session_id, stream_url
```

**`backend/tests/unit/test_mcp_server.py`** (NEW)
Uses `respx` (or `unittest.mock`) to mock `httpx.AsyncClient`.
```
test_list_tools_returns_hx_design         — list_tools() includes hx_design schema
test_list_tools_returns_get_status        — list_tools() includes get_design_status
test_hx_design_calls_engine_post          — call_tool("hx_design") POSTs correct payload
test_hx_design_happy_path_returns_text    — returns session_id + stream_url in reply
test_hx_design_engine_down_returns_error  — httpx raises → TextContent with error message
test_get_design_status_returns_json       — call_tool("get_design_status") GETs status
test_schema_loaded_from_engines_yaml      — hx_design schema matches engines.yaml (no drift)
```

### Frontend tests (Vitest — per TODOS.md "Frontend Test Infrastructure")

**`frontend/src/hooks/__tests__/useHXStream.test.js`** (NEW)
```
test_session_id_extracted_from_relative_url  — /api/v1/hx/design/abc123/stream → "abc123"
test_full_url_built_with_vite_env_var        — VITE_HX_ENGINE_URL=http://host:8100 prepended
test_absolute_url_unchanged                  — http://... passes through as-is
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
  Proves the three services are wired correctly end-to-end.

test_engine_down_returns_error_event
  Given: HX_ENGINE_URL points to a non-running port
  When:  POST /api/v1/chat with full HX params
  Then:  app_error SSE event emitted, no hx_design_started event
```

Run with: `pytest tests/integration/ -m integration --hx-engine-url=http://localhost:8100`

### E2E browser tests (deferred — flag for post-v1)
```
[→E2E] Full browser flow: user provides params → design starts → 5 StepCards complete
[→E2E] ESCALATED step → user responds inline → pipeline resumes
```

---

## 10. Dependencies to Add

```bash
# backend — MCP server
pip install mcp httpx

# Already present: httpx (used by HXEngineClient), anthropic, fastapi
```

Add `mcp` to `backend/pyproject.toml` or `requirements.txt`.

---

*This plan supersedes the integration notes in ARKEN_MASTER_PLAN.md §11 (Backend Changes) for the v1 scope.*

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 2 | CLEAR (PLAN) | 6 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |

**CROSS-MODEL:** Outside voice (Claude subagent) raised 8 findings. 2 real bugs fixed (session_id as explicit event field, integration smoke test added). 1 false positive (nginx SSE — already configured). 5 deferred/acknowledged.

**VERDICT:** ENG CLEARED — ready to implement.
