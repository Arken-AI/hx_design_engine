# Steps 01-05 Context (Intake to Thermal Driving Force)

## Purpose

This unit covers pipeline initialization through first-principles thermal closure and initial geometry choice. It transforms validated request fields into mass/energy-consistent process conditions, fluid property envelopes, shell/tube allocation decisions, and the LMTD/F-factor driving force used by all downstream sizing steps. Most early-run feasibility failures originate here.

## Key files

- hx_engine/app/steps/step_01_requirements.py
- hx_engine/app/steps/step_02_heat_duty.py
- hx_engine/app/steps/step_03_fluid_props.py
- hx_engine/app/steps/step_04_tema_geometry.py
- hx_engine/app/steps/step_05_lmtd.py
- hx_engine/app/steps/step_01_rules.py
- hx_engine/app/steps/step_03_rules.py
- hx_engine/app/steps/step_04_rules.py
- hx_engine/app/steps/step_05_rules.py

## Key classes/methods

| Symbol                                                                     | What it does                                                                                        |
| -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `Step01Requirements.execute`                                               | Emits validated intake fields into step outputs without AI.                                         |
| `Step02HeatDuty._calculate_missing_temp`                                   | Solves missing 4th temperature (or cold flow) from energy balance.                                  |
| `Step02HeatDuty.execute`                                                   | Computes `Q_W`, latent-duty branch for vapor/condensing path, and anomaly warnings.                 |
| `Step03FluidProperties.execute`                                            | Resolves hot/cold properties, phase regimes, drift/freeze checks, and property escalation payloads. |
| `Step03FluidProperties.apply_user_override`                                | Applies user-supplied or approved property corrections during escalation.                           |
| `_allocate_fluids` in `step_04_tema_geometry.py`                           | Chooses shell-side fluid using toxic/corrosive/pressure/fouling heuristics.                         |
| `_select_tema_type` in `step_04_tema_geometry.py`                          | Selects TEMA rear-end type (BEM/AES/AEU/AEP/AEW path).                                              |
| `_select_initial_geometry` in `step_04_tema_geometry.py`                   | Picks tube OD/length/passes and initial shell geometry from heuristics + tables.                    |
| `Step04TEMAGeometry.execute`                                               | Binds allocation + TEMA + geometry + fouling assumptions into outputs.                              |
| `Step05LMTD.execute`                                                       | Computes `LMTD_K`, `R`, `P`, `F_factor`; includes shell-pass autocorrection and isothermal bypass.  |
| `compute_lmtd`, `compute_f_factor` in `hx_engine/app/correlations/lmtd.py` | Core thermal driving-force calculations.                                                            |

## Important flows

### Flow A: Initial thermal closure

1. Step 1 `execute` emits intake fields from `DesignState`.
2. Step 2 `execute` calls `_calculate_missing_temp` if one thermal variable is missing.
3. Step 2 optionally triggers latent condenser path when hot side inferred vapor/condensing.
4. Outputs include `Q_W`, completed temperatures, and basis metadata.

### Flow B: Fluid properties and phase regime

1. Step 3 computes mean temperatures and resolves both streams via thermo adapter.
2. If user-provided properties exist, they take priority over adapter lookups.
3. Step 3 derives phase regime (`liquid`, `vapor`, `condensing`, `evaporating`) and viscosity/freeze warnings.
4. Layer2 rules in `step_03_rules.py` can escalate non-correctable physics issues.

### Flow C: TEMA + geometry + LMTD/F setup

1. Step 4 allocates shell side (`_allocate_fluids`) and selects TEMA type.
2. Step 4 computes initial geometry and fouling factors.
3. Step 5 computes `LMTD_K` and `F_factor` from temperatures and passes.
4. For isothermal phase-change, Step 5 bypasses F-correlation and forces `F_factor=1.0`.

## Data/state touched

- `DesignState` thermal fields: `Q_W`, temperatures, phase labels, flow rates.
- `DesignState` property fields: `hot_fluid_props`, `cold_fluid_props`, `viscosity_variation`, `flow_density_drift`.
- `DesignState` geometry and allocation fields: `geometry`, `tema_type`, `shell_side_fluid`, `R_f_*`.
- Step 5 outputs: `LMTD_K`, `F_factor`, `effective_LMTD`, `R`, `P`.

## Known gotchas / past bugs

- Step2 latent-duty regressions: missing cold-side fields in condenser branch previously caused silent fallback/runaway outputs (see `tests/unit/test_step_02_latent_duty.py`).
- Step4 expansion decision uses tubesheet differential, not global stream span (`tests/unit/test_step_04_tubesheet_differential.py`).
- Step4 toxic/corrosive allocation and pitch/layout consistency are guarded by dedicated regressions (`tests/unit/test_step_04_toxic_allocation.py`, `tests/unit/test_step_04_pitch_layout_rule.py`).
- Step5 includes isothermal phase-change bypass to avoid invalid Bowman F-factor singularities.

## Cross-references

- [intake_validation.context.md](./intake_validation.context.md)
- [adapters_and_ai.context.md](./adapters_and_ai.context.md)
- [correlations_math.context.md](./correlations_math.context.md)
- [data_catalogs.context.md](./data_catalogs.context.md)
- [steps_06_10.context.md](./steps_06_10.context.md)
