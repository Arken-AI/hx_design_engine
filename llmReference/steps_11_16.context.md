# Steps 11-16 Context (Convergence, Safety, Mechanical, Cost, Final Signoff)

## Purpose

This unit handles post-sizing optimization and final engineering checks: area/overdesign targets, convergence loop adjustments, vibration safety, ASME thickness checks, CAPCOST estimates, and confidence scoring. It contains the highest-value ship/no-ship decision logic. Failures here often indicate feasible thermal design but non-viable mechanical/economic envelope.

## Key files

- hx_engine/app/steps/step_11_area_overdesign.py
- hx_engine/app/steps/step_12_convergence.py
- hx_engine/app/steps/step_13_vibration.py
- hx_engine/app/steps/step_14_mechanical.py
- hx_engine/app/steps/step_15_cost.py
- hx_engine/app/steps/step_16_final_validation.py
- hx_engine/app/steps/step_11_rules.py
- hx_engine/app/steps/step_13_rules.py
- hx_engine/app/steps/step_14_rules.py
- hx_engine/app/steps/step_15_rules.py
- hx_engine/app/steps/step_16_rules.py

## Key classes/methods

| Symbol                                                          | What it does                                                                                                 |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `Step11AreaOverdesign.execute`                                  | Computes required/provided area and overdesign with service-aware bands.                                     |
| `_low_velocity_fouling_paradox` in `step_11_area_overdesign.py` | Flags high-overdesign + low-velocity fouling paradox (warn/escalate).                                        |
| `Step12Convergence.run`                                         | Iteratively runs Steps 7-11 and applies geometry adjustments until convergence or restart/accept-best logic. |
| `Step12Convergence._compute_adjustment`                         | Chooses geometry update strategy (proportional/damped) by violations trajectory.                             |
| `Step13VibrationCheck.execute`                                  | Runs TEMA Section 6 vibration checks across spans/mechanisms.                                                |
| `Step14MechanicalCheck.execute`                                 | Executes ASME UG-27/UG-28 checks and thermal expansion compatibility.                                        |
| `Step15CostEstimate.execute`                                    | Computes bare-module cost using Turton + CEPCI adjustment and material/pressure factors.                     |
| `Step16FinalValidation.execute`                                 | Computes deterministic confidence breakdown and final risk summary scaffolding.                              |
| `_compute_confidence_score` in `step_16_final_validation.py`    | Weighted score from convergence/AI agreement/validation metrics with penalties.                              |

## Important flows

### Flow A: Overdesign and convergence

1. Step 11 computes `area_required_m2`, `area_provided_m2`, and `overdesign_pct`.
2. Step 12 enters loop over Steps 7->11 and tracks trajectory snapshots.
3. If constraints fail, Step12 applies geometry adjustments and repeats.
4. On structural dead-end, Step12 can request restart from earlier step.

### Flow B: Post-convergence integrity checks

1. Step13 vibration check evaluates fluidelastic, vortex, buffeting, and acoustic modes.
2. Step14 checks tube/shell thickness and expansion margins against TEMA type.
3. Step15 estimates cost with Turton constants, pressure factor, and material factor.
4. Step16 calculates final confidence and appends thermal penalty reasons.

### Flow C: Convergence and redesign interaction

1. Step12 convergence may emit restart request (`convergence_action=restart`).
2. `PipelineRunner._run_convergence_loop` reruns from requested step via `_rerun_steps_from`.
3. Persistent hard constraints eventually route to redesign loop or terminal error.

## Data/state touched

- Overdesign/convergence: `overdesign_pct`, `convergence_iteration`, `convergence_trajectory`, `convergence_converged`.
- Vibration/mechanical: `vibration_safe`, `vibration_details`, `tube_thickness_ok`, `shell_thickness_ok`, `mechanical_details`.
- Cost/final: `cost_usd`, `cost_breakdown`, `confidence_score`, `confidence_breakdown`, `design_summary`.

## Known gotchas / past bugs

- Step11 undersized exchanger failures must route into redesign loop instead of terminal stop (`tests/unit/test_pipeline_runner_layer2_escalation.py`).
- Step14 regression coverage exists for backward-compat behavior (`tests/integration/test_step_14_regression.py`).
- Step16 has edge-case regression tests around confidence computation and AI agreement ratio (`tests/integration/test_step_16_regression.py`, `tests/unit/test_step_16_final_validation.py`).
- Convergence can intentionally end with user-accepted best iteration instead of strict convergence.

## Cross-references

- [steps_06_10.context.md](./steps_06_10.context.md)
- [pipeline_orchestration.context.md](./pipeline_orchestration.context.md)
- [correlations_math.context.md](./correlations_math.context.md)
- [data_catalogs.context.md](./data_catalogs.context.md)
- [models_state_events.context.md](./models_state_events.context.md)
