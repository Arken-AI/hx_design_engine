# LLM Reference Index

## How to use this index

1. Start here.
2. Match the user question/symptom to the closest row in the lookup table.
3. Open the mapped context file.
4. Jump directly to the listed source files/methods.
5. Only expand to neighboring context files when cross-references indicate dependency.

## Topic / Feature / Symptom Lookup

| Topic / Feature / Symptom                                            | Open this context file                                                   | Key source files to jump to                                                                                                                                                              |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| App fails to start / dependency init / Redis wiring                  | [api_and_runtime.context.md](./api_and_runtime.context.md)               | `hx_engine/app/main.py`, `hx_engine/app/dependencies.py`, `hx_engine/app/config.py`                                                                                                      |
| `/requirements` rejects payload unexpectedly                         | [intake_validation.context.md](./intake_validation.context.md)           | `hx_engine/app/routers/requirements.py`, `hx_engine/app/core/requirements_validator.py`, `hx_engine/app/core/volumetric_flow.py`                                                         |
| `/design` token verification mismatch                                | [intake_validation.context.md](./intake_validation.context.md)           | `hx_engine/app/core/requirements_validator.py`, `hx_engine/app/routers/design.py`                                                                                                        |
| `/respond` returns 410 too early or racey behavior                   | [api_and_runtime.context.md](./api_and_runtime.context.md)               | `hx_engine/app/routers/design.py`, `hx_engine/app/core/sse_manager.py`, `tests/test_http_endpoints.py`                                                                                   |
| Session state fields missing or not persisted                        | [models_state_events.context.md](./models_state_events.context.md)       | `hx_engine/app/models/design_state.py`, `hx_engine/app/core/session_store.py`, `hx_engine/app/core/state_utils.py`                                                                       |
| Wrong SSE payload shape / frontend event mismatch                    | [models_state_events.context.md](./models_state_events.context.md)       | `hx_engine/app/models/sse_events.py`, `hx_engine/app/core/pipeline_runner.py`, `hx_engine/app/routers/stream.py`                                                                         |
| Pipeline reruns unexpectedly / escalation loops / status transitions | [pipeline_orchestration.context.md](./pipeline_orchestration.context.md) | `hx_engine/app/core/pipeline_runner.py`, `hx_engine/app/core/redesign_loop.py`, `hx_engine/app/steps/base.py`                                                                            |
| Step 1-5 thermal closure issues (Q, phase, TEMA, LMTD/F)             | [steps_01_05.context.md](./steps_01_05.context.md)                       | `hx_engine/app/steps/step_02_heat_duty.py`, `hx_engine/app/steps/step_03_fluid_props.py`, `hx_engine/app/steps/step_04_tema_geometry.py`, `hx_engine/app/steps/step_05_lmtd.py`          |
| Condensing/vapor heat-duty path gives strange temperature            | [steps_01_05.context.md](./steps_01_05.context.md)                       | `hx_engine/app/steps/step_02_heat_duty.py`, `tests/unit/test_step_02_latent_duty.py`                                                                                                     |
| Fluid property source/confidence disputes                            | [adapters_and_ai.context.md](./adapters_and_ai.context.md)               | `hx_engine/app/adapters/thermo_adapter.py`, `hx_engine/app/steps/step_03_fluid_props.py`, `hx_engine/app/services/property_provenance.py`                                                |
| Tube/shell side allocation seems wrong (toxic/corrosive/fouling)     | [steps_01_05.context.md](./steps_01_05.context.md)                       | `hx_engine/app/steps/step_04_tema_geometry.py`, `tests/unit/test_step_04_toxic_allocation.py`, `tests/unit/test_step_04_corrosive_allocation.py`                                         |
| Step 6-10 performance issues (U, h, ΔP, nozzle)                      | [steps_06_10.context.md](./steps_06_10.context.md)                       | `hx_engine/app/steps/step_06_initial_u.py`, `hx_engine/app/steps/step_07_tube_side_h.py`, `hx_engine/app/steps/step_08_shell_side_h.py`, `hx_engine/app/steps/step_10_pressure_drops.py` |
| Step 7 velocity bound failures and restart behavior                  | [pipeline_orchestration.context.md](./pipeline_orchestration.context.md) | `hx_engine/app/core/pipeline_runner.py`, `hx_engine/app/steps/step_07_tube_side_h.py`, `tests/unit/test_pipeline_runner_layer2_escalation.py`                                            |
| Step 10 nozzle envelope / ρv² failures                               | [steps_06_10.context.md](./steps_06_10.context.md)                       | `hx_engine/app/steps/step_10_pressure_drops.py`, `hx_engine/app/data/nozzle_table.py`                                                                                                    |
| Convergence doesn’t settle / oscillates                              | [steps_11_16.context.md](./steps_11_16.context.md)                       | `hx_engine/app/steps/step_12_convergence.py`, `hx_engine/app/core/pipeline_runner.py`                                                                                                    |
| Overdesign paradox or undersized exchanger behavior                  | [steps_11_16.context.md](./steps_11_16.context.md)                       | `hx_engine/app/steps/step_11_area_overdesign.py`, `hx_engine/app/steps/step_11_rules.py`                                                                                                 |
| Vibration safety failures                                            | [steps_11_16.context.md](./steps_11_16.context.md)                       | `hx_engine/app/steps/step_13_vibration.py`, `hx_engine/app/correlations/tema_vibration.py`                                                                                               |
| Mechanical thickness/external pressure failures                      | [steps_11_16.context.md](./steps_11_16.context.md)                       | `hx_engine/app/steps/step_14_mechanical.py`, `hx_engine/app/correlations/asme_thickness.py`, `hx_engine/app/data/asme_external_pressure.py`                                              |
| Cost estimate outliers / CEPCI concerns                              | [steps_11_16.context.md](./steps_11_16.context.md)                       | `hx_engine/app/steps/step_15_cost.py`, `hx_engine/app/data/cost_indices.py`, `hx_engine/app/correlations/turton_cost.py`                                                                 |
| Final confidence score suspicious                                    | [steps_11_16.context.md](./steps_11_16.context.md)                       | `hx_engine/app/steps/step_16_final_validation.py`, `hx_engine/app/steps/step_16_rules.py`                                                                                                |
| Numeric formula validation across modules                            | [correlations_math.context.md](./correlations_math.context.md)           | `hx_engine/app/correlations/*.py`                                                                                                                                                        |
| Lookup table/source-data correctness                                 | [data_catalogs.context.md](./data_catalogs.context.md)                   | `hx_engine/app/data/*.py`                                                                                                                                                                |
| AI decision parsing/retry/auth disable behavior                      | [adapters_and_ai.context.md](./adapters_and_ai.context.md)               | `hx_engine/app/core/ai_engineer.py`, `hx_engine/app/steps/base.py`                                                                                                                       |

## Keyword / Alias Map

| Keyword / Alias / Ticket phrase                             | Route to context                                                         |
| ----------------------------------------------------------- | ------------------------------------------------------------------------ |
| `P1-5`, `latent duty`, `vapor outlet runaway`               | [steps_01_05.context.md](./steps_01_05.context.md)                       |
| `P1-6`, `gas pressure required`, `volumetric gas flow`      | [intake_validation.context.md](./intake_validation.context.md)           |
| `P2-11`, `corrosive allocation`                             | [steps_01_05.context.md](./steps_01_05.context.md)                       |
| `P2-12`, `toxic allocation`, `double tubesheet review`      | [steps_01_05.context.md](./steps_01_05.context.md)                       |
| `P2-14`, `tubesheet differential`                           | [steps_01_05.context.md](./steps_01_05.context.md)                       |
| `P2-15`, `L/D band`                                         | [steps_01_05.context.md](./steps_01_05.context.md)                       |
| `P2-17`, `pitch ratio layout`                               | [steps_01_05.context.md](./steps_01_05.context.md)                       |
| `P2-18`, `viscosity variation`                              | [steps_01_05.context.md](./steps_01_05.context.md)                       |
| `P2-19`, `freezing margin`                                  | [steps_01_05.context.md](./steps_01_05.context.md)                       |
| `P2-20`, `flow object`, `sm3_h`, `Nm3_h`                    | [intake_validation.context.md](./intake_validation.context.md)           |
| `P2-22`, `transition Re`, `Gnielinski penalty`              | [steps_11_16.context.md](./steps_11_16.context.md)                       |
| `P2-23`, `service-aware overdesign band`                    | [steps_11_16.context.md](./steps_11_16.context.md)                       |
| `P2-24`, `low-velocity fouling paradox`                     | [steps_11_16.context.md](./steps_11_16.context.md)                       |
| `P2-25`, `mu_s_wall_basis`, `approx_bulk`                   | [steps_06_10.context.md](./steps_06_10.context.md)                       |
| `410-on-click`, `respond race`                              | [api_and_runtime.context.md](./api_and_runtime.context.md)               |
| `Layer2 discarded escalation`, `max escalation wording bug` | [pipeline_orchestration.context.md](./pipeline_orchestration.context.md) |
| `nozzle envelope`, `rho v2`                                 | [steps_06_10.context.md](./steps_06_10.context.md)                       |
| `budget exhausted redesign`, `fallback lever`               | [pipeline_orchestration.context.md](./pipeline_orchestration.context.md) |
| `Turton`, `CEPCI`, `bare module cost`                       | [steps_11_16.context.md](./steps_11_16.context.md)                       |

## Directory map

- [api_and_runtime.context.md](./api_and_runtime.context.md): FastAPI app lifecycle, dependency wiring, design/requirements/stream routers.
- [intake_validation.context.md](./intake_validation.context.md): Layer1/Layer2 requirements validation, flow-unit resolution, HMAC token logic.
- [models_state_events.context.md](./models_state_events.context.md): DesignState, step result contracts, SSE event schemas, output mapping and provenance build.
- [pipeline_orchestration.context.md](./pipeline_orchestration.context.md): Pipeline runner, escalation wait/resume, redesign loop, session/SSE orchestration.
- [steps_01_05.context.md](./steps_01_05.context.md): Steps 1-5 (requirements hydration, heat duty, fluid props, TEMA/geometry, LMTD/F).
- [steps_06_10.context.md](./steps_06_10.context.md): Steps 6-10 (initial U sizing, tube/shell HTC, overall U, pressure drops/nozzles).
- [steps_11_16.context.md](./steps_11_16.context.md): Steps 11-16 (overdesign, convergence, vibration, mechanical, cost, final validation).
- [adapters_and_ai.context.md](./adapters_and_ai.context.md): Thermo/petroleum/unit adapters, AI review call chain, skill prompts.
- [correlations_math.context.md](./correlations_math.context.md): Pure correlation/formula modules used by step implementations.
- [data_catalogs.context.md](./data_catalogs.context.md): Lookup tables/constants (TEMA, fouling, materials, ASME curves, nozzle, cost indices).
