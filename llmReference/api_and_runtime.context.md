# API and Runtime Context

## Purpose

This unit owns HTTP entrypoints, app lifecycle, dependency wiring, and SSE streaming for the design engine. It is the first place to inspect when requests fail before pipeline logic starts, when stream delivery is broken, or when resource startup/shutdown behavior is inconsistent. It also defines the stateless request handshake between requirements validation and design execution.

## Key files

- hx_engine/app/main.py
- hx_engine/app/config.py
- hx_engine/app/dependencies.py
- hx_engine/app/routers/requirements.py
- hx_engine/app/routers/design.py
- hx_engine/app/routers/stream.py

## Key classes/methods

| Symbol                                                                    | What it does                                                                                              |
| ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `lifespan` in `hx_engine/app/main.py`                                     | Initializes logging and shared dependencies on startup; shuts down Redis on exit.                         |
| `app.include_router(...)` in `hx_engine/app/main.py`                      | Registers `/api/v1/hx` routes for requirements, design, and stream.                                       |
| `HXEngineSettings` in `hx_engine/app/config.py`                           | Central environment-backed settings (`HX_*`) for Redis, AI, auth, and pipeline limits.                    |
| `startup` / `shutdown` in `hx_engine/app/dependencies.py`                 | Creates Redis client, `SessionStore`, and `AIEngineer`; closes Redis on shutdown.                         |
| `get_redesign_driver` in `hx_engine/app/dependencies.py`                  | Returns `RedesignDriver(PipelineRunner(...))` used by the design endpoint.                                |
| `validate_design_requirements` in `hx_engine/app/routers/requirements.py` | Runs volumetric-flow resolution + Layer1/Layer2 validation and issues HMAC token.                         |
| `start_design` in `hx_engine/app/routers/design.py`                       | Verifies token/inline validation, builds `DesignState`, persists session, starts background redesign run. |
| `get_design_status` in `hx_engine/app/routers/design.py`                  | Poll fallback endpoint returning step records and pipeline status.                                        |
| `respond_to_escalation` in `hx_engine/app/routers/design.py`              | Accepts user escalation response; resolves in-memory wait future.                                         |
| `design_stream` in `hx_engine/app/routers/stream.py`                      | SSE endpoint that forwards queued events until completion/end.                                            |

## Important flows

### Flow A: Validate requirements then start design

1. `POST /requirements` -> `validate_design_requirements`.
2. `apply_flow_inputs` resolves flow object units to `m_dot_*_kg_s` before validation.
3. `validate_requirements` runs Layer 1 and Layer 2 checks.
4. `sign_token` emits stateless HMAC token over canonical payload.
5. `POST /design` -> `start_design` verifies token via `verify_token` (or runs inline validation).
6. `start_design` builds `DesignState`, pre-creates SSE queue, stores session, then schedules `RedesignDriver.run`.

### Flow B: Stream and escalation response loop

1. Client opens `GET /design/{session_id}/stream` -> `design_stream`.
2. `SSEManager.stream_events` yields queued events (`step_started`, `step_escalated`, etc.).
3. For escalation responses, client calls `POST /design/{session_id}/respond`.
4. `respond_to_escalation` checks `state.waiting_for_user` OR pending response future via `SSEManager.has_pending_user_response_future`.
5. `SSEManager.resolve_user_response` unblocks pipeline wait.

## Data/state touched

- `DesignRequest` payload fields from `hx_engine/app/models/requirements.py`.
- Session persistence keyspace via `SessionStore` (`hx:session:*`, `hx:heartbeat:*`).
- SSE per-session queue and pending response futures via `SSEManager`.
- Token fields: canonical `design_input` + minute-based HMAC.

## Known gotchas / past bugs

- 410 response race in `/respond`: pending in-memory future is authoritative even if persisted `waiting_for_user` is false (see `tests/test_http_endpoints.py`).
- Design route runs volumetric conversion before token verification; if you compare signatures against pre-conversion payloads, verification will fail.
- Redis is optional at runtime; fallback in-memory mode can hide deployment misconfiguration if logs are ignored.

## Cross-references

- [intake_validation.context.md](./intake_validation.context.md)
- [pipeline_orchestration.context.md](./pipeline_orchestration.context.md)
- [models_state_events.context.md](./models_state_events.context.md)
- [adapters_and_ai.context.md](./adapters_and_ai.context.md)
