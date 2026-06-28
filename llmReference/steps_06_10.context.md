# Steps 06-10 Context (Initial Sizing to Pressure Limits)

## Purpose

This unit converts thermal targets into practical exchanger size, then computes tube/shell-side heat-transfer and hydraulic performance. It is where geometry assumptions from Step 4 are stress-tested against velocity, U, pressure-drop, and nozzle constraints. Most redesign-triggering hard failures are generated in this range.

## Key files

- hx_engine/app/steps/step_06_initial_u.py
- hx_engine/app/steps/step_07_tube_side_h.py
- hx_engine/app/steps/step_08_shell_side_h.py
- hx_engine/app/steps/step_09_overall_u.py
- hx_engine/app/steps/step_10_pressure_drops.py
- hx_engine/app/steps/step_06_rules.py
- hx_engine/app/steps/step_07_rules.py
- hx_engine/app/steps/step_08_rules.py
- hx_engine/app/steps/step_09_rules.py
- hx_engine/app/steps/step_10_rules.py

## Key classes/methods

| Symbol                                                                  | What it does                                                                                  |
| ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `Step06InitialU.execute`                                                | Picks U-assumption class, estimates area, maps to standard shell/tube geometry.               |
| `Step07TubeSideH.execute`                                               | Computes tube velocity/Re/Pr/Nu/h using Gnielinski/Hausen path and wall-viscosity correction. |
| `Step07TubeSideH.apply_user_override`                                   | Handles escalation actions such as side swap or velocity-raising geometry edits.              |
| `Step08ShellSideH.execute`                                              | Computes shell-side HTC via Bell-Delaware or Shah condensation branch.                        |
| `Step08ShellSideH._swap_shell_side_fluid`                               | Escalation helper to flip shell/tube side assignment with restart.                            |
| `Step09OverallU.execute`                                                | Aggregates resistances and computes `U_dirty`, `U_clean`, cleanliness, Kern deviation.        |
| `_compute_resistances` in `step_09_overall_u.py`                        | Builds wall/film/fouling resistance stack on common area basis.                               |
| `Step10PressureDrops.execute`                                           | Computes tube/shell ΔP, nozzle ρv² checks, and automatic nozzle upsizing.                     |
| `_tube_limit` / `_shell_limit` in `step_10_pressure_drops.py`           | Applies user-provided ΔP limits or defaults.                                                  |
| `get_default_nozzle_diameter_m` in `hx_engine/app/data/nozzle_table.py` | Maps shell size to nozzle baseline and raises envelope constraint violations.                 |

## Important flows

### Flow A: Initial sizing and geometry concretization

1. Step 6 validates required thermal inputs (`Q`, `F`, `LMTD`, geometry seeds).
2. `get_U_assumption` or override category mapping selects U range.
3. Required area and tube count estimated; `find_shell_diameter` chooses standard shell.
4. Geometry fields and area outputs are emitted for downstream transfer/hydraulic steps.

### Flow B: Coupled h/U/ΔP evaluation

1. Step 7 computes tube-side `h_tube_W_m2K`, `tube_velocity_m_s`, `Re_tube`.
2. Step 8 computes shell-side `h_shell_W_m2K`, `Re_shell`, j-factors, Kern cross-check.
3. Step 9 computes overall U and resistance breakdown.
4. Step 10 computes tube + shell pressure drops and nozzle erosion checks.

### Flow C: Constraint-to-redesign routing

1. Step10 Layer2 rules fail on tube/shell ΔP or nozzle ρv².
2. `PipelineRunner._classify_step10_mechanical_failure` converts those to `DesignConstraintViolation`.
3. `RedesignDriver` mutates legal levers and restarts from Step 1.

## Data/state touched

- Sizing fields: `U_W_m2K`, `A_m2`, `geometry.n_tubes`, `geometry.shell_diameter_m`.
- Tube-side outputs: `h_tube_W_m2K`, `tube_velocity_m_s`, `Re_tube`, `Nu_tube`.
- Shell-side outputs: `h_shell_W_m2K`, `Re_shell`, `shell_side_j_factors`, Kern diagnostics.
- Overall-U outputs: `U_clean_W_m2K`, `U_dirty_W_m2K`, `cleanliness_factor`, resistance breakdown.
- Hydraulic outputs: `dP_tube_Pa`, `dP_shell_Pa`, nozzle IDs, `rho_v2_*` fields.

## Known gotchas / past bugs

- Step7 velocity hard-fail path now supports auto `n_passes` restart before user escalation (`tests/unit/test_pipeline_runner_layer2_escalation.py`).
- Step9 should not escalate solely due to mismatch against Step6 estimated U; convergence loop handles this later (documented in Step9 skill markdown).
- Nozzle table enforces 4-42 in shell envelope and triggers redesign exception when outside range.
- Step10 shell wall-viscosity fallback (`mu_s_wall_basis=approx_bulk`) affects final confidence penalties in Step16.

## Cross-references

- [pipeline_orchestration.context.md](./pipeline_orchestration.context.md)
- [correlations_math.context.md](./correlations_math.context.md)
- [data_catalogs.context.md](./data_catalogs.context.md)
- [steps_11_16.context.md](./steps_11_16.context.md)
- [steps_01_05.context.md](./steps_01_05.context.md)
