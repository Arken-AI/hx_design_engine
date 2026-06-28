# Correlations and Engineering Math Context

## Purpose

This unit contains the pure engineering correlation functions used by step implementations. These modules are side-effect free and provide the numerical core for heat transfer, pressure drop, vibration, mechanical thickness, and cost formulas. Use this context when debugging numeric output drift, formula-domain failures, or cross-check mismatches.

## Key files

- hx_engine/app/correlations/lmtd.py
- hx_engine/app/correlations/gnielinski.py
- hx_engine/app/correlations/churchill_friction.py
- hx_engine/app/correlations/bell_delaware.py
- hx_engine/app/correlations/simplified_delaware_dp.py
- hx_engine/app/correlations/shah_condensation.py
- hx_engine/app/correlations/asme_thickness.py
- hx_engine/app/correlations/tema_vibration.py
- hx_engine/app/correlations/turton_cost.py

## Key classes/methods

| Symbol                                                                                                | What it does                                                               |
| ----------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| `compute_lmtd`, `compute_R`, `compute_P`, `compute_f_factor` in `lmtd.py`                             | Core thermal driving-force equations used in Step 5.                       |
| `tube_side_h` in `gnielinski.py`                                                                      | Tube-side HTC wrapper selecting laminar/transition/turbulent correlations. |
| `churchill_friction_factor` in `churchill_friction.py`                                                | All-regime Darcy friction factor used in Step 10 tube-side ΔP.             |
| `shell_side_htc` and `shell_side_dP` in `bell_delaware.py`                                            | Bell-Delaware shell HTC and shell pressure-drop calculations.              |
| `kern_shell_side_htc` / `kern_shell_side_dP` in `bell_delaware.py`                                    | Kern cross-check implementations.                                          |
| `simplified_delaware_shell_dP` in `simplified_delaware_dp.py`                                         | Additional shell ΔP cross-check.                                           |
| `shah_condensation_h` / `shah_condensation_average_h`                                                 | Condensing shell-side HTC correlations used by Step 8 condensation branch. |
| `tube_internal_pressure_thickness` / `shell_internal_pressure_thickness` in `asme_thickness.py`       | ASME UG-27 thickness formulas.                                             |
| `external_pressure_allowable` in `asme_thickness.py`                                                  | ASME UG-28 external pressure allowable calculation.                        |
| `check_all_spans` in `tema_vibration.py`                                                              | Multi-mechanism vibration analysis used in Step 13.                        |
| `purchased_equipment_cost`, `pressure_factor`, `bare_module_cost`, `cepci_adjust` in `turton_cost.py` | Turton CAPCOST primitives used in Step 15.                                 |

## Important flows

### Flow A: Thermal/hydraulic path

1. Step5 -> `lmtd.py` functions.
2. Step7 -> `gnielinski.py` + `churchill_friction.py`.
3. Step8 -> `bell_delaware.py` or `shah_condensation.py`.
4. Step10 -> `churchill_friction.py`, `bell_delaware.py`, `simplified_delaware_dp.py`.

### Flow B: Mechanical and safety path

1. Step14 -> `asme_thickness.py` for UG-27/UG-28 + thermal expansion differential.
2. Step13 -> `tema_vibration.py` for flow-induced vibration safety margins.

### Flow C: Economic path

1. Step15 uses `turton_cost.py` to compute base, pressure/material multipliers, and CEPCI adjustment.

## Data/state touched

- No direct `DesignState` writes in this unit (pure function modules).
- Function inputs originate from step outputs and data-table lookups.
- Exception behavior (`ValueError`, boundary returns) is consumed by step-level `CalculationError` wrappers.

## Known gotchas / past bugs

- `compute_f_factor` has domain guards; invalid `R/P` conditions intentionally return 0.0.
- Bell/Kern divergence is expected at some regimes and interpreted by step-level thresholds, not immediate failures.
- ASME external pressure calculations rely on factor tables in data modules; stale/incorrect table entries propagate directly.

## Cross-references

- [steps_01_05.context.md](./steps_01_05.context.md)
- [steps_06_10.context.md](./steps_06_10.context.md)
- [steps_11_16.context.md](./steps_11_16.context.md)
- [data_catalogs.context.md](./data_catalogs.context.md)
