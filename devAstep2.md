# Dev A — Step 2: Calculate Heat Duty — Implementation Plan

## Overview

Step 2 computes **Q = ṁ × Cp × ΔT** for both fluid sides, calculates the missing 4th temperature if only 3 were provided by Step 1, and verifies energy balance closure. It's a **CONDITIONAL** AI step — AI is only called when anomalies are detected (~30-50% of designs).

### Dependencies (must exist before Step 2)

- ✅ `DesignState` model — exists
- ✅ `StepResult` / `BaseStep` framework — exists
- ✅ `Step01Requirements` — exists (provides temps, flows, fluid names)
- ✅ `units_adapter.py` — exists
- ❌ `thermo_adapter.py` — **needs to be built** (Step 2 requires Cp at mean temperature)

---

## Piece 1: Cp Retrieval — `thermo_adapter.py` (Minimal for Step 2)

**What:** Build the thermo_adapter with a `get_cp(fluid_name, temperature_C, pressure_Pa)` function. Step 2 only needs Cp; Step 3 will need all 5 fluid properties. Build the full `get_fluid_properties()` now to avoid rework.

**Files:**

- `hx_engine/app/adapters/thermo_adapter.py` — CREATE

**Logic:**

1. Priority chain: **iapws** (water/steam) → **CoolProp** (common fluids) → **thermo** (organics/mixtures)
2. If none available, fall back to a hardcoded `_FALLBACK_CP` dict for 15-20 common fluids
3. Return a `FluidProperties` model with all fields populated
4. Raise `CalculationError(step_id, msg)` on unknown fluid

**Testing Plan (8 tests):**
| # | Test | What it validates | Physics check |
|---|------|-------------------|---------------|
| 1 | `test_water_at_25C_cp` | Cp within 1% of NIST 4181 J/kg·K | Cp of water is the most well-known thermodynamic value |
| 2 | `test_water_at_25C_density` | ρ within 1% of 997.05 kg/m³ | Ensures library not returning steam properties at 25°C |
| 3 | `test_water_at_25C_viscosity` | μ within 5% of 8.9e-4 Pa·s | Cross-validates library health |
| 4 | `test_crude_oil_cp_reasonable` | Cp ∈ [1600, 2200] J/kg·K at ~120°C | Published range for medium crudes |
| 5 | `test_unknown_fluid_raises` | `get_fluid_properties("unobtanium", 50)` → `CalculationError` | Fail-fast, never silently return garbage |
| 6 | `test_all_fields_populated` | All FluidProperties fields are `not None` | Downstream steps (3, 7, 8) rely on complete props |
| 7 | `test_fluid_near_boiling` | Water at 99°C, 1 atm — returns liquid props, not gas | Phase boundary handling is critical |
| 8 | `test_fallback_chain_works` | Mock iapws=fail → CoolProp responds correctly | Fallback doesn't mask errors |

---

## Piece 2: Core Heat Duty Calculation — `_compute_Q()`

**What:** Pure function: `Q = ṁ × Cp × |ΔT|` for one fluid side. Extracted as a static method for testability.

**Files:**

- `hx_engine/app/steps/step_02_heat_duty.py` — CREATE (start with this function)

**Logic:**

```
Q_hot  = m_dot_hot  × Cp_hot  × (T_hot_in  - T_hot_out)
Q_cold = m_dot_cold × Cp_cold × (T_cold_out - T_cold_in)
```

**Testing Plan (6 tests):**
| # | Test | What it validates | Physics check |
|---|------|-------------------|---------------|
| 1 | `test_Q_known_water_case` | 50 kg/s water, ΔT=60°C → Q ≈ 12.54 MW | Hand-calculable reference: 50 × 4181 × 60 = 12,543,000 W |
| 2 | `test_Q_known_oil_case` | 50 kg/s crude, Cp=1900, ΔT=60°C → Q ≈ 5.7 MW | 50 × 1900 × 60 = 5,700,000 W |
| 3 | `test_Q_zero_delta_T` | ΔT = 0 → Q = 0, which triggers downstream hard fail | Conservation of energy: no ΔT = no heat transfer |
| 4 | `test_Q_negative_delta_T_hot` | T_hot_in < T_hot_out → Q < 0 (heat gain) → caught by validation | 2nd law: hot side must cool down |
| 5 | `test_Q_very_large` | 500 kg/s, ΔT=200°C → Q ≈ 418 MW | Must not overflow; hits the 500 MW soft cap |
| 6 | `test_Q_symmetry` | Compute hot side and cold side independently, both positive when valid | Energy is scalar and positive for heat release/gain |

---

## Piece 3: Missing 4th Temperature Calculation — `_calculate_missing_temp()`

**What:** When Step 1 extracted only 3 temperatures, compute the 4th from energy balance:

- If `T_cold_out` missing: `T_cold_out = T_cold_in + Q_hot / (m_cold × Cp_cold)`
- If `T_hot_out` missing: `T_hot_out = T_hot_in - Q_cold / (m_hot × Cp_hot)`
- Similarly for `T_cold_in` and `T_hot_in` (rare but supported)

**Files:**

- Same file: `hx_engine/app/steps/step_02_heat_duty.py`

**Logic:**

1. Detect which temperature is `None` from DesignState
2. Compute Q from the **known** side (3 temps + flow)
3. Solve for the missing temp algebraically
4. If both cold-side temps are missing → escalate (unsolvable)
5. If m_dot_cold is also missing → estimate from energy balance using assumed Cp

**Testing Plan (7 tests):**
| # | Test | What it validates | Physics check |
|---|------|-------------------|---------------|
| 1 | `test_missing_T_cold_out` | T_cold_out calculated correctly from Q_hot | Must satisfy Q_hot = Q_cold (first law) |
| 2 | `test_missing_T_hot_out` | T_hot_out back-calculated from Q_cold | Energy balance must close to < 1% |
| 3 | `test_back_calculated_T_roundtrip` | Set all 4 temps → remove one → recalculate → matches original within 0.1°C | Round-trip consistency proves the algebra |
| 4 | `test_result_temp_cross_detected` | Calculated T_cold_out > T_hot_in → flagged | Thermodynamically impossible without external work |
| 5 | `test_missing_both_cold_temps` | T_cold_in & T_cold_out both None → escalation (not solvable) | System is underdetermined |
| 6 | `test_small_missing_delta_T` | Q_hot is small → T_cold_out barely above T_cold_in (valid) | ΔT can be small but not zero |
| 7 | `test_missing_m_dot_cold_with_3_temps` | All 4 temps known, m_dot_cold missing → m_dot_cold = Q_hot / (Cp_cold × ΔT_cold) | Must be positive and physically reasonable |

---

## Piece 4: Energy Balance Verification — `_check_energy_balance()`

**What:** Compute the balance error: `|Q_hot - Q_cold| / Q_hot`. Two thresholds:

- **< 1%**: passes Layer 2 hard rule
- **1%–2%**: passes but noted
- **> 2%**: triggers AI review (conditional trigger)

**Files:**

- Same file: `hx_engine/app/steps/step_02_heat_duty.py`

**Testing Plan (5 tests):**
| # | Test | What it validates | Physics check |
|---|------|-------------------|---------------|
| 1 | `test_perfect_balance` | Q_hot ≈ Q_cold → error < 0.01% → passes | First law of thermodynamics satisfied exactly |
| 2 | `test_balance_error_0_5_pct` | 0.5% → passes hard rule, no AI trigger | Acceptable engineering tolerance |
| 3 | `test_balance_error_1_5_pct` | 1.5% → fails hard rule (> 1%), step must handle | Energy not conserved beyond tolerance |
| 4 | `test_balance_error_3_pct` | 3% → fails hard rule AND triggers AI | Significant Cp or temp inconsistency |
| 5 | `test_Q_hot_zero_division` | Q_hot = 0 → handled gracefully (not division by zero) | Edge case protection |

---

## Piece 5: Layer 2 Validation Rules — `step_02_rules.py`

**What:** Hard engineering rules that AI **cannot** override. Registered with the validation_rules framework.

**Files:**

- `hx_engine/app/steps/step_02_rules.py` — CREATE

**Rules:**
| Rule | Condition | Action |
|------|-----------|--------|
| R1: Positive heat duty | `Q_W > 0` | Hard fail |
| R2: Q within range | `Q_W < 500_000_000 (500 MW)` | Hard fail — likely input error |
| R3: Energy balance | `abs(Q_hot - Q_cold) / Q_hot < 0.01` | Hard fail |
| R4: Cold outlet > cold inlet | `T_cold_out > T_cold_in` | Hard fail — 2nd law |
| R5: Driving force exists | `T_cold_out < T_hot_in` | Hard fail — no heat transfer possible |

**Testing Plan (10 tests):**
| # | Test | What it validates | Physics check |
|---|------|-------------------|---------------|
| 1 | `test_rule_Q_positive_passes` | Q = 5 MW → passes | Heat flows from hot to cold |
| 2 | `test_rule_Q_zero_fails` | Q = 0 → hard fail | Zero Q means no heat exchange |
| 3 | `test_rule_Q_negative_fails` | Q = -100 → hard fail | Negative Q is nonsensical for design mode |
| 4 | `test_rule_Q_above_500MW_fails` | Q = 600 MW → hard fail | Likely unit error (MW vs W) |
| 5 | `test_rule_energy_balance_passes` | 0.5% error → passes | Conservation within tolerance |
| 6 | `test_rule_energy_balance_fails` | 5% error → hard fail | Energy not conserved |
| 7 | `test_rule_cold_outlet_gt_inlet_passes` | T_cold_out (70°C) > T_cold_in (30°C) → passes | Heat must flow into cold stream |
| 8 | `test_rule_cold_outlet_lt_inlet_fails` | T_cold_out (25°C) < T_cold_in (30°C) → hard fail | 2nd law violation |
| 9 | `test_rule_driving_force_passes` | T_cold_out (70°C) < T_hot_in (150°C) → passes | LMTD must be positive |
| 10 | `test_rule_driving_force_fails` | T_cold_out (160°C) > T_hot_in (150°C) → hard fail | No thermal driving force |

---

## Piece 6: Conditional AI Trigger Logic — `_conditional_ai_trigger()`

**What:** Override `BaseStep._conditional_ai_trigger()` to define when CONDITIONAL AI review fires.

**Files:**

- Same file: `hx_engine/app/steps/step_02_heat_duty.py`

**Trigger conditions (any one fires AI):**

1. Energy balance error > 2% (looser than hard 1%)
2. Very small ΔT on either side (< 5°C approach)
3. Q magnitude seems anomalous for the flow rate (Q/ṁ outside [10 kW, 10 MW] per kg/s range)

**Testing Plan (6 tests):**
| # | Test | What it validates | Physics check |
|---|------|-------------------|---------------|
| 1 | `test_ai_not_triggered_normal` | Balance 0.3%, ΔT = 60°C → AI not called | Normal operation is deterministic |
| 2 | `test_ai_triggered_balance_2_5_pct` | Balance 2.5% → AI called | Cp inconsistency needs review |
| 3 | `test_ai_triggered_tight_approach` | T_cold_out = T_hot_in - 3°C → AI called | Economically marginal, needs engineer review |
| 4 | `test_ai_not_triggered_in_convergence` | `state.in_convergence_loop = True` → AI skipped | Decision 3A: skip AI in inner loop |
| 5 | `test_ai_triggered_Q_anomalous_high` | Q per unit flow > 10 MW/(kg/s) → AI called | Likely Cp error or wrong units |
| 6 | `test_ai_triggered_Q_anomalous_low` | Q per unit flow < 10 kW/(kg/s) → AI called | Suspiciously low heat exchange |

---

## Piece 7: Step02HeatDuty Class Assembly — `execute()`

**What:** Wire all pieces together in the `execute()` method following the BaseStep pattern.

**Files:**

- `hx_engine/app/steps/step_02_heat_duty.py` — FINALIZE

**`execute()` flow:**

1. Read temps, flows, fluid names from `DesignState`
2. Get Cp_hot and Cp_cold via `thermo_adapter.get_cp(fluid, mean_T)`
3. If a temperature is missing → call `_calculate_missing_temp()`
4. Compute `Q_hot` and `Q_cold`
5. Pick `Q_W = Q_hot` as the design basis (hot side is more reliable when Cp is known)
6. Compute energy balance error
7. Build and return `StepResult` with outputs:
   - `Q_W`, `T_hot_out_C` (if calculated), `T_cold_out_C` (if calculated)
   - `Cp_hot_J_kgK`, `Cp_cold_J_kgK` (saved for Step 3 cross-check)
   - `energy_balance_error_pct`
8. Populate warnings for tight approach, phase change risk, etc.

**Testing Plan (8 tests):**
| # | Test | What it validates | Physics check |
|---|------|-------------------|---------------|
| 1 | `test_full_execute_crude_oil_water` | Standard case: crude oil 150→90°C, water 30→?°C, 50 kg/s → Q ≈ 5.7 MW, T_cold_out calculated | Reference textbook problem |
| 2 | `test_execute_all_4_temps` | All temps provided, both Q match → Q reported, no 4th temp calc | Energy balance closure confirms inputs |
| 3 | `test_execute_missing_T_cold_out` | 3 temps → 4th back-calculated, balance < 1% | First law algebraic consistency |
| 4 | `test_execute_Q_populates_state` | After execute, `result.outputs["Q_W"]` is a positive float | Step output contract |
| 5 | `test_execute_warnings_tight_approach` | Temps set so ΔT = 4°C → warning emitted | Tight approach flagged for user |
| 6 | `test_execute_identical_temps_fails` | T_hot_in = T_hot_out → validation_passed = False | Q = 0 is thermodynamically meaningless |
| 7 | `test_step_02_is_step_protocol` | `isinstance(Step02HeatDuty(), StepProtocol)` → True | Structural typing contract |
| 8 | `test_execute_stores_cp_values` | `result.outputs["Cp_hot_J_kgK"]` exists | Forward propagation to Step 3 |

---

## Piece 8: Integration — Step 1 → Step 2 Pipeline

**What:** Run Step 1 then Step 2 in sequence on a realistic input, verify the full chain.

**Files:**

- `tests/unit/test_step_02_integration.py` — CREATE

**Testing Plan (5 tests):**
| # | Test | What it validates | Physics check |
|---|------|-------------------|---------------|
| 1 | `test_step1_to_step2_structured_input` | JSON input → Step 1 parses → Step 2 computes Q | End-to-end data flow |
| 2 | `test_step1_to_step2_natural_language` | NL "cool 50 kg/s crude oil from 150°C to 90°C using water at 30°C" → Step 1 → Step 2 → Q ≈ 5.7 MW | Full NL → calculation pipeline |
| 3 | `test_step2_populates_design_state` | After Step 2, DesignState has Q_W, all 4 temps, and Cp values | State mutation contract |
| 4 | `test_step2_result_outputs_match_state` | `result.outputs["Q_W"]` matches what would be written to state | Output consistency |
| 5 | `test_step2_warnings_propagated` | Tight approach from Step 1 temps → warning in Step 2 result → accumulable in state | Warning chain doesn't drop messages |

---

## Implementation Order

```
PIECE 1  ─── thermo_adapter.py (Cp retrieval)          ─── 8 tests
    │
PIECE 2  ─── _compute_Q() pure function                ─── 6 tests
    │
PIECE 3  ─── _calculate_missing_temp()                 ─── 7 tests
    │
PIECE 4  ─── _check_energy_balance()                   ─── 5 tests
    │
PIECE 5  ─── step_02_rules.py (Layer 2)                ─── 10 tests
    │
PIECE 6  ─── _conditional_ai_trigger()                 ─── 6 tests
    │
PIECE 7  ─── Full execute() assembly                   ─── 8 tests
    │
PIECE 8  ─── Integration (Step 1 → Step 2)             ─── 5 tests
                                                        ─────────
                                              TOTAL:     55 tests
```

Each piece is independently testable. Pieces 2–4 are pure functions with zero external dependencies. Piece 1 is the only one requiring external libraries (`iapws`, `CoolProp`, `thermo`). Piece 5 uses the existing validation_rules framework. Pieces 6–7 wire into BaseStep. Piece 8 validates the full chain.

### Key Physics Invariants Every Test Guards

| Invariant                                                                             | Where enforced    |
| ------------------------------------------------------------------------------------- | ----------------- |
| **First law**: Q_hot = Q_cold (energy conservation)                                   | Pieces 4, 5, 7, 8 |
| **Second law**: heat flows hot → cold (T_cold_out < T_hot_in)                         | Pieces 5, 3       |
| **Cp is positive and bounded** (500–10,000 J/kg·K for liquids)                        | Piece 1           |
| **Q > 0** for any valid heat exchanger design                                         | Pieces 2, 5, 7    |
| **Temperature consistency**: all 4 temps are in a physically realizable configuration | Pieces 3, 5, 8    |
| **No silent failures**: unknown fluid → crash, not garbage Cp                         | Piece 1           |
