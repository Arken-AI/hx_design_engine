# Data Catalogs and Lookup Tables Context

## Purpose

This unit stores engineering lookup tables, constants, and interpolation datasets consumed by steps and correlations. These files encode standards data (TEMA, ASME, pipe schedules, cost indices) and heuristic defaults (fouling/U/nozzle assumptions). If computations are systematically biased or boundaries look wrong, inspect these datasets before touching algorithm code.

## Key files

- hx_engine/app/data/tema_tables.py
- hx_engine/app/data/fouling_factors.py
- hx_engine/app/data/u_assumptions.py
- hx_engine/app/data/bwg_gauge.py
- hx_engine/app/data/nozzle_table.py
- hx_engine/app/data/pipe_schedules.py
- hx_engine/app/data/material_properties.py
- hx_engine/app/data/asme_external_pressure.py
- hx_engine/app/data/cost_indices.py

## Key classes/methods

| Symbol                                                                                             | What it does                                                   |
| -------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `get_tube_count`, `find_shell_diameter`, `get_tema_clearances` in `tema_tables.py`                 | Standard tube-count and shell-clearance lookups.               |
| `get_fouling_factor`, `resolve_fouling_factor`, `classify_fouling` in `fouling_factors.py`         | Fouling resistance value + metadata resolution.                |
| `get_U_assumption` in `u_assumptions.py`                                                           | Initial U-range selection from fluid pair/category.            |
| `get_tube_id`, `get_wall_thickness` in `bwg_gauge.py`                                              | BWG tube dimensions for OD->ID/wall conversion.                |
| `get_default_nozzle_diameter_m`, `nozzle_rho_v_squared` in `nozzle_table.py`                       | Nozzle baseline size and erosion metric calculations.          |
| `find_minimum_schedule` in `pipe_schedules.py`                                                     | Chooses minimum ASME schedule wall meeting required thickness. |
| `get_allowable_stress`, `get_elastic_modulus`, `get_thermal_expansion` in `material_properties.py` | Material properties used by mechanical/vibration/cost checks.  |
| `lookup_factor_A`, `lookup_factor_B` in `asme_external_pressure.py`                                | External-pressure chart-factor interpolations for UG-28.       |
| `get_turton_row`, `get_k_constants`, `get_material_factor`, `get_cepci_ratio` in `cost_indices.py` | Cost constants and correction factors for Step 15.             |

## Important flows

### Flow A: Geometry/table lookups

1. Step4 and Step6 call `tema_tables` for shell/tube mapping and clearances.
2. Step4 and Step9 call fouling/U/material datasets.
3. Step10 calls nozzle defaults and may trigger nozzle-envelope redesign violations.

### Flow B: Mechanical standards lookup

1. Step14 calls `material_properties` + `pipe_schedules` + `asme_external_pressure`.
2. Correlation layer computes required thickness/allowables from these tables.

### Flow C: Cost constant resolution

1. Step15 maps TEMA type to Turton row using `cost_indices`.
2. K/C/B constants + CEPCI + material factors form final cost estimate.

## Data/state touched

- Static dict/list tables keyed by shell size, material key, TEMA type, temperature, schedule.
- No mutable runtime state beyond function returns.
- Outputs are copied into `DesignState` by step implementations.

## Known gotchas / past bugs

- Nozzle table intentionally has shell-size envelope and gap snap-up behavior; out-of-envelope raises redesign violation.
- TEMA data and pitch/layout consistency are guarded by regression tests for clearance and ratio rules.
- CEPCI staleness threshold can trigger warnings/AI review in cost step even when formulas are correct.

## Cross-references

- [correlations_math.context.md](./correlations_math.context.md)
- [steps_01_05.context.md](./steps_01_05.context.md)
- [steps_06_10.context.md](./steps_06_10.context.md)
- [steps_11_16.context.md](./steps_11_16.context.md)
- [adapters_and_ai.context.md](./adapters_and_ai.context.md)
