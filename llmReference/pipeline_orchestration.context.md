# Pipeline Orchestration Context

## Purpose

This unit orchestrates step execution, AI review loops, escalation handling, restart logic, and redesign retries. It is the control-plane of the engine: step math can succeed but the run still fails here due to flow-control logic, timeouts, or restart semantics. Use this context when symptoms involve unexpected reruns, escalations, or pipeline status transitions.

## Key files

- hx_engine/app/core/pipeline_runner.py
- hx_engine/app/core/redesign_loop.py
- hx_engine/app/core/sse_manager.py
- hx_engine/app/core/session_store.py
- hx_engine/app/core/validation_rules.py
- hx_engine/app/core/design_intent.py
- hx_engine/app/core/exceptions.py
- hx_engine/app/steps/base.py

## Key classes/methods

| Symbol                                                             | What it does                                                                         |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| `PipelineRunner.run` in `pipeline_runner.py`                       | Main orchestrator for Steps 1-11 plus post-convergence Steps 13-16.                  |
| `_classify_redesignable_layer2_failure` in `pipeline_runner.py`    | Routes Step10/Step11 hard-rule failures to redesign loop instead of user escalation. |
| `_adjust_n_passes_for_velocity` in `pipeline_runner.py`            | Step7 autonomous velocity recovery by changing `geometry.n_passes`.                  |
| `_run_convergence_loop` in `pipeline_runner.py`                    | Executes Step12 and handles structural restart requests.                             |
| `_wait_for_user` in `pipeline_runner.py`                           | Blocks on escalation response future, applies accept/override/skip behavior.         |
| `RedesignDriver.run` in `redesign_loop.py`                         | Wraps pipeline with iterative lever changes after `DesignConstraintViolation`.       |
| `apply_lever` in `redesign_loop.py`                                | Applies discrete ladder/toggle mutations on geometry and arrangement levers.         |
| `SSEManager.create_user_response_future` / `resolve_user_response` | Synchronizes step escalation pauses with API responses.                              |
| `SessionStore.save/load/heartbeat/is_orphaned`                     | Persistence + orphan detection with Redis or in-memory fallback.                     |
| `validation_rules.check`                                           | Runs Layer2 hard rules and tags failures as correctable/uncorrectable.               |
| `BaseStep.run_with_review_loop`                                    | Layer1->Layer2->Layer3 loop with correction retries and escalation trail.            |

## Important flows

### Flow A: Standard run with Layer2 and AI review

1. `PipelineRunner.run` iterates over `PIPELINE_STEPS`.
2. Each step runs `step.run_with_review_loop(state, ai_engineer)`.
3. `validation_rules.check` applies hard rules.
4. If Layer2 fails and is redesignable (Step10/Step11 patterns), raise `DesignConstraintViolation`.
5. Otherwise attempt `step.run_with_layer2_recovery(...)` or escalate user.
6. On success, outputs applied, SSE emitted, state persisted.

### Flow B: Escalation pause/resume

1. Step result with decision `ESCALATE` emits `StepEscalatedEvent`.
2. `_wait_for_user` creates future via `SSEManager.create_user_response_future`.
3. `/respond` resolves future; accepted corrections or override text are applied.
4. Step reruns or earlier steps rerun via `_rerun_steps_from` when restart target exists.
5. `is_termination_intent` can terminate run gracefully.

### Flow C: Redesign loop after constraint violation

1. `RedesignDriver.run` catches `DesignConstraintViolation` from pipeline.
2. `_ask_ai` currently returns none (`AIEngineer.recommend_redesign` fallback path).
3. Deterministic fallback picks legal lever/direction.
4. `apply_lever` mutates state, `clear_state_from_step(state, 1)` clears downstream values.
5. Pipeline restarts; loop stops on success or budget exhaustion.

## Data/state touched

- `DesignState.pipeline_status`, `waiting_for_user`, `completed_steps`, `step_records`.
- `DesignState.escalation_history` and `DesignState.redesign_history`.
- Step decision payloads in `AIReview` and `StepEscalatedEvent`.
- Redis keys: `hx:session:*`, `hx:heartbeat:*` (or in-memory mirrors).

## Known gotchas / past bugs

- Layer2+ESCALATE routing bug: Layer2 failure must not discard AI escalation path (covered by `tests/unit/test_pipeline_runner_layer2_escalation.py`).
- User-facing error text must not leak internal max-escalation counters.
- Step7 velocity auto-restart exists specifically to prevent hard-stop on recoverable velocity bound issues.
- 410-on-click race fixed by checking pending future, not only persisted waiting flag.

## Cross-references

- [models_state_events.context.md](./models_state_events.context.md)
- [steps_06_10.context.md](./steps_06_10.context.md)
- [steps_11_16.context.md](./steps_11_16.context.md)
- [api_and_runtime.context.md](./api_and_runtime.context.md)
- [adapters_and_ai.context.md](./adapters_and_ai.context.md)
