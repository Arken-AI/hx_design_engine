# Models, State, and Events Context

## Purpose

This unit defines the canonical domain state, step result contract, and SSE event schemas used across the engine. It is the source of truth for what fields steps may read/write and how progress is serialized to clients. Use this context when tracing missing fields, schema drift, or event payload mismatches.

## Key files

- hx_engine/app/models/design_state.py
- hx_engine/app/models/step_result.py
- hx_engine/app/models/sse_events.py
- hx_engine/app/models/requirements.py
- hx_engine/app/core/state_utils.py
- hx_engine/app/services/property_provenance.py

## Key classes/methods

| Symbol                                                          | What it does                                                                   |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `DesignState` in `design_state.py`                              | Mutable state bag for all step inputs/outputs, progress, and redesign history. |
| `GeometrySpec` in `design_state.py`                             | Validated geometry model with TEMA-like constraints and helper accessors.      |
| `FluidProperties` in `design_state.py`                          | Thermophysical property DTO with bounds and provenance metadata.               |
| `StepResult` and `StepRecord` in `step_result.py`               | Per-step compute output and immutable audit trail entry.                       |
| `AIReview`, `AICorrection`, `AttemptRecord` in `step_result.py` | Layer-3 review contract used by correction/escalation loops.                   |
| `RedesignAttempt` in `step_result.py`                           | Global redesign-loop attempt record persisted in state history.                |
| `SSEBaseEvent` + concrete event models in `sse_events.py`       | Strict event schema for stream payloads.                                       |
| `clear_state_from_step` in `state_utils.py`                     | Clears stale downstream fields and step history before restart/rerun.          |
| `apply_outputs` in `state_utils.py`                             | Maps `StepResult.outputs` into `DesignState` including nested models.          |
| `PropertyProvenanceBuilder.build` in `property_provenance.py`   | Builds final hot/cold property provenance object at pipeline completion.       |

## Important flows

### Flow A: Step output application and audit trail

1. Step returns `StepResult(outputs=...)`.
2. `BaseStep._record` writes `StepRecord` into `DesignState.step_records`.
3. `PipelineRunner._apply_outputs` delegates to `state_utils.apply_outputs`.
4. Output map writes scalar fields; nested dicts become `FluidProperties`/`GeometrySpec` objects.

### Flow B: Restart-safe state clearing

1. Restart request arrives (`_rerun_steps_from`, redesign, convergence restart).
2. `clear_state_from_step` removes step records, completed steps, escalation history >= target step.
3. Step-specific output fields are nulled/reset from `_STEP_STATE_FIELDS`.

### Flow C: End-of-run provenance assembly

1. After Step 16 completion, `PropertyProvenanceBuilder.build(state)` runs.
2. Chooses user-provided properties over adapter values when present.
3. Emits per-fluid source labels and per-property metadata.

## Data/state touched

- `DesignState` fields: thermal, hydraulic, mechanical, cost, convergence, review notes, escalation history, redesign history.
- `StepResult.outputs` keys listed in `state_utils._OUTPUT_FIELD_MAP`.
- SSE event payload types (`step_started`, `step_warning`, `step_escalated`, `design_complete`, `redesign_attempt`, etc.).

## Known gotchas / past bugs

- Partial state mutation rollback is handled via `DesignState.snapshot_fields`/`restore`; bypassing this in step code can leave inconsistent state.
- `DesignState.waiting_for_user` can lag real in-process future state; API checks both persisted flag and pending future.
- Property provenance is fluid-level, not per-property-source map granularity (`// TODO: verify` future schema extension path).

## Cross-references

- [pipeline_orchestration.context.md](./pipeline_orchestration.context.md)
- [api_and_runtime.context.md](./api_and_runtime.context.md)
- [steps_01_05.context.md](./steps_01_05.context.md)
- [steps_06_10.context.md](./steps_06_10.context.md)
- [steps_11_16.context.md](./steps_11_16.context.md)
