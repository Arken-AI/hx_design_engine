# Adapters and AI Review Context

## Purpose

This unit wraps external thermophysical backends, petroleum correlations, unit conversion helpers, and AI review orchestration. It decides where fluid property values come from and how AI decisions are parsed/fallbacked when auth or model calls fail. If outputs look physically implausible or AI behavior changes unexpectedly, inspect this unit first.

## Key files

- hx_engine/app/adapters/thermo_adapter.py
- hx_engine/app/adapters/petroleum_correlations.py
- hx_engine/app/adapters/units_adapter.py
- hx_engine/app/core/ai_engineer.py
- hx_engine/app/core/fouling_ai.py
- hx_engine/app/skills/base.md
- hx_engine/app/skills/step_02_heat_duty.md
- hx_engine/app/skills/step_03_fluid_properties.md
- hx_engine/app/skills/step_04_tema_geometry.md
- hx_engine/app/skills/step_05_lmtd_f_factor.md
- hx_engine/app/skills/step_06_initial_u.md
- hx_engine/app/skills/step_07_tube_side_htc.md
- hx_engine/app/skills/step_08_shell_side_htc.md
- hx_engine/app/skills/step_09_overall_u.md
- hx_engine/app/skills/step_10_pressure_drops.md
- hx_engine/app/skills/step_11_area_overdesign.md
- hx_engine/app/skills/step_12_convergence.md
- hx_engine/app/skills/step_13_vibration.md
- hx_engine/app/skills/step_14_mechanical.md
- hx_engine/app/skills/step_15_cost.md
- hx_engine/app/skills/step_16_final_validation.md

## Key classes/methods

| Symbol                                                                      | What it does                                                                            |
| --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `get_fluid_properties_sync` / `get_fluid_properties` in `thermo_adapter.py` | Main property resolution chain (IAPWS -> CoolProp -> Petroleum -> Specialty -> thermo). |
| `get_saturation_props` in `thermo_adapter.py`                               | Retrieves saturation data for phase-change logic.                                       |
| `get_two_phase_props` in `thermo_adapter.py`                                | Computes two-phase property envelope when required by steps.                            |
| `resolve_petroleum_name` in `petroleum_correlations.py`                     | Maps crude/fraction names to API-based characterization.                                |
| `get_petroleum_properties` in `petroleum_correlations.py`                   | Computes Cp/density/viscosity/k for petroleum fluids from API correlations.             |
| `AlternativeGenerator.generate` in `ai_engineer.py`                         | Deterministic fallback options when Claude is unavailable.                              |
| `AIEngineer.review`                                                         | Orchestrates per-step AI review call/fallback path.                                     |
| `AIEngineer._anthropic_request_with_retry`                                  | Handles auth disablement, retries, and response extraction.                             |
| `AIEngineer._parse_review_with_status`                                      | Parses model JSON (direct, fenced, raw decode fallback).                                |
| `AIEngineer.recommend_redesign`                                             | Currently returns none; redesign loop relies on deterministic fallback.                 |

## Important flows

### Flow A: Property backend selection

1. Fluid name normalized and phase suffix stripped.
2. Water/steam path checks IAPWS.
3. Pure compounds try CoolProp.
4. Petroleum names route to API-based petroleum correlations before thermo.
5. Specialty fits used for glycol/oils/molten salt.
6. Final fallback uses `thermo.Chemical` where applicable.

### Flow B: Step review call

1. `BaseStep.run_with_review_loop` calls `AIEngineer.review`.
2. `AIEngineer._build_review_prompt` composes step outputs, notes, and failure context.
3. `_anthropic_request_with_retry` executes model call with auth/429/5xx handling.
4. `_parse_review_with_status` maps JSON to `AIReview`/corrections/options.
5. Low confidence is forced to escalation by confidence gate in `BaseStep`.

### Flow C: AI unavailable path

1. Missing API key or auth failure sets stub/unavailable mode.
2. `AIEngineer.review` returns deterministic proceed/warn behavior.
3. Budget-exhausted option proposals use `AlternativeGenerator` recipes.

## Data/state touched

- `FluidProperties.property_source`, `property_confidence`, approval timestamps.
- AI telemetry metrics emitted from `_emit_review_metric`.
- Skill markdown files consumed by `_build_system_prompt` per step.

## Known gotchas / past bugs

- Petroleum fluids must not fall through to generic pure-compound thermo lookup; dedicated branch exists to avoid water-like nonsense for mixtures.
- AI auth failures intentionally disable AI for the rest of the run after one banner log.
- Redesign advice from AI is currently disabled (`recommend_redesign` returns none), so redesign loop is deterministic unless this method is implemented.

## Cross-references

- [steps_01_05.context.md](./steps_01_05.context.md)
- [steps_06_10.context.md](./steps_06_10.context.md)
- [pipeline_orchestration.context.md](./pipeline_orchestration.context.md)
- [correlations_math.context.md](./correlations_math.context.md)
- [data_catalogs.context.md](./data_catalogs.context.md)
