# Intake Validation Context

## Purpose

This unit validates user input deterministically before any design session runs. It enforces completeness and physics sanity, converts alternate flow units, and signs/verifies stateless tokens so `/design` can trust upstream validation. If bad payloads are accepted or tokens fail unexpectedly, start here.

## Key files

- hx_engine/app/core/requirements_validator.py
- hx_engine/app/core/volumetric_flow.py
- hx_engine/app/models/requirements.py
- hx_engine/app/routers/requirements.py

## Key classes/methods

| Symbol                                                                                    | What it does                                                                          |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `ValidationError`, `ValidationWarning`, `ValidationResult` in `requirements_validator.py` | Standard containers for deterministic validation output.                              |
| `_layer1` in `requirements_validator.py`                                                  | Schema/completeness/range checks and known-fluid warning checks.                      |
| `_layer2` in `requirements_validator.py`                                                  | Physics checks: temperature ordering, cross, min approach, underdetermined equations. |
| `validate_requirements` in `requirements_validator.py`                                    | Public entry combining Layer1 then Layer2.                                            |
| `sign_token` / `verify_token` in `requirements_validator.py`                              | Minute-window HMAC token generation/verification for canonical payloads.              |
| `build_user_message` in `requirements_validator.py`                                       | Human-readable summary used in requirements response.                                 |
| `resolve_mass_flow` in `volumetric_flow.py`                                               | Converts `{value, unit}` flow input to `kg/s` via fluid density and basis rules.      |
| `apply_flow_inputs` in `volumetric_flow.py`                                               | Router helper that strips `hot_flow/cold_flow` and writes resolved `m_dot_*_kg_s`.    |
| `DesignRequest.to_validation_dict` in `models/requirements.py`                            | Canonical dict excluding audit/routing fields.                                        |

## Important flows

### Flow A: Stateless validation handshake

1. Request enters `validate_design_requirements`.
2. `DesignRequest.to_validation_dict` creates canonical validation payload.
3. `apply_flow_inputs` resolves flow objects first (P2-20 behavior).
4. `validate_requirements` calls `_layer1`, then `_layer2` if Layer1 passes.
5. On success, `sign_token` creates HMAC token for `/design`.

### Flow B: Flow unit resolution

1. `resolve_mass_flow` checks unit in `SUPPORTED_VOLUMETRIC_UNITS`.
2. Liquid volumetric units call `get_fluid_properties` at inlet conditions for density.
3. Gas standard-volume units require explicit pressure and temperature.
4. Result returns `FlowResolution` with audit fields (`basis`, `density_source`, etc.).

## Data/state touched

- Request DTO: `FlowInput`, `DesignRequest`.
- Canonical token payload (sorted JSON + unix-minute).
- `FlowResolution` audit info later persisted into `DesignState.hot_flow_input` / `cold_flow_input`.
- Constants: `_MIN_APPROACH_C`, `_PETROLEUM_TEMP_LIMIT_C`, `DENSITY_DRIFT_WARN_PCT`.

## Known gotchas / past bugs

- Gas volumetric conversion intentionally rejects missing pressure; no silent 1-atm fallback.
- Token verification depends on post-flow-resolution payload shape; signing raw payload before conversion causes mismatch.
- Layer2 underdetermined checks prevent Step 2 from receiving mathematically ambiguous temperature/flow inputs.

## Cross-references

- [api_and_runtime.context.md](./api_and_runtime.context.md)
- [steps_01_05.context.md](./steps_01_05.context.md)
- [adapters_and_ai.context.md](./adapters_and_ai.context.md)
- [models_state_events.context.md](./models_state_events.context.md)
