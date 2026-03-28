# Step 01 — Process Requirements

**File:** `hx_engine/app/steps/step_01_requirements.py`
**Step ID:** 1
**Step Name:** Process Requirements
**AI Mode:** `FULL` — the AI engineer always reviews Step 1 outputs

---

## Purpose

Step 1 is the **entry point** of the HX design pipeline. It takes a user's raw heat-exchanger design request — either structured JSON or free-form natural language — and extracts a validated set of:

- Hot & cold fluid names
- Inlet/outlet temperatures (°C)
- Mass flow rates (kg/s)
- Operating pressures (Pa)
- Optional TEMA type preference

The extracted parameters are written into `StepResult.outputs` and passed to Step 2 (Heat Duty) after AI review.

---

## Two Input Paths

### Path 1 — Structured JSON

If `state.raw_request` is valid JSON with the required fields, it goes through the `_from_structured()` method.

**Input schema (`DesignInput` Pydantic model):**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `hot_fluid` | `str` | ✅ | — | Hot side fluid name |
| `cold_fluid` | `str` | ✅ | — | Cold side fluid name |
| `T_hot_in` | `float` | ✅ | — | Hot side inlet temperature |
| `T_hot_out` | `float` | ❌ | `None` | Hot side outlet temperature |
| `T_cold_in` | `float` | ✅ | — | Cold side inlet temperature |
| `T_cold_out` | `float` | ❌ | `None` | Cold side outlet temperature |
| `m_dot_hot` | `float` | ✅ | — | Hot side mass flow rate |
| `m_dot_cold` | `float` | ❌ | `None` | Cold side mass flow rate |
| `temp_unit` | `str` | ❌ | `"C"` | Temperature unit (C, F, K) |
| `flow_unit` | `str` | ❌ | `"kg/s"` | Flow rate unit |
| `pressure` | `float` | ❌ | `None` | Operating pressure |
| `pressure_unit` | `str` | ❌ | `"Pa"` | Pressure unit |
| `tema_class` | `str` | ❌ | `None` | TEMA class (R, C, B) |
| `tema_preference` | `str` | ❌ | `None` | Preferred TEMA type (AES, BEM, etc.) |

**Validation:** Flow rates must be positive (enforced by `_flow_must_be_positive` validator).

**Processing:**
1. Parse JSON → `DesignInput` model (Pydantic validation)
2. Convert all temperatures to °C via `detect_and_convert_temperature()`
3. Convert all flow rates to kg/s via `detect_and_convert_flow_rate()`
4. Convert pressure to Pa via `detect_and_convert_pressure()` (default: 101325 Pa)
5. Generate physics warnings (temperature direction, cross)
6. Mark missing fields (`missing_T_cold_out`, `missing_m_dot_cold`)

---

### Path 2 — Natural Language (NL)

If `raw_request` is not valid JSON, it goes through `_from_natural_language()`.

This path uses regex-based extraction with heuristic assignment.

#### NL Extraction Pipeline

```
Raw text
  │
  ├─→ _extract_fluids()        → (hot_fluid, cold_fluid)
  ├─→ _extract_temperatures()  → [(value_C, unit), ...]
  ├─→ _extract_flows()         → [(value_kg_s, unit), ...]
  ├─→ _RE_PRESSURE matches     → P_hot_Pa, P_cold_Pa
  └─→ _RE_TEMA match           → tema_preference
```

---

## NL Extraction Details

### Fluid Extraction (`_extract_fluids`)

**Strategy:** Longest-match-first scanning against the `_KNOWN_FLUIDS` list.

1. Sort `_KNOWN_FLUIDS` by length descending (so `"crude oil"` matches before `"oil"`)
2. Scan the lowered text; for each match, record the fluid and **remove it** from the text
3. After all known fluids are found, scan for **ambiguous bare words** (`"oil"`, `"gas"`, `"fluid"`, `"liquid"`, `"chemical"`, `"solvent"`) — if found, add an error
4. Assign sides using `_assign_fluid_sides()`

**Known Fluids (76 entries):**

| Category | Examples |
|----------|----------|
| Petroleum | `crude oil`, `diesel`, `diesel fuel`, `lube oil`, `lubricating oil`, `heavy fuel oil`, `hfo`, `fuel oil`, `bunker fuel`, `naphtha`, `gasoline`, `kerosene` |
| Water family | `water`, `cooling water`, `chilled water`, `sea water`, `seawater`, `hot water`, `boiler water`, `condensate`, `brine` |
| Specialty | `thermal oil`, `vegetable oil`, `mineral oil`, `glycol`, `ethylene glycol`, `propylene glycol`, `molten salt` |
| Pure chemicals | `ethanol`, `methanol`, `ammonia`, `toluene`, `benzene`, `xylene`, `acetone`, `hexane`, `heptane`, `pentane` |
| Gases | `steam`, `nitrogen`, `air`, `hydrogen`, `oxygen` |

**Side Assignment (`_assign_fluid_sides`):**

| Condition | Hot | Cold |
|-----------|-----|------|
| One fluid is in `_COLD_INDICATORS` | The other | The cold indicator |
| "cooling" verb + ≥2 fluids | First mentioned | Second mentioned |
| Default with ≥2 fluids | First mentioned | Second mentioned |

**Cold indicators:** `cooling water`, `chilled water`, `cold water`, `sea water`, `seawater`, `brine`, `water`

---

### Temperature Extraction (`_extract_temperatures`)

**Regex patterns:**

| Pattern | Example matches |
|---------|----------------|
| `_RE_TEMP_RANGE` | `"from 150 to 90°C"`, `"from 302 to 212°F"` |
| `_RE_TEMP` | `"150°C"`, `"302 °F"`, `"373.15 K"`, `"-10°C"` |

**Priority:** Range patterns (`from X to Y`) are extracted first. Individual temperature matches that fall inside a range span are skipped to avoid double-counting.

**Supported units:** `C`, `F`, `K`, `celsius`, `fahrenheit`, `kelvin` (case-insensitive).

All values are converted to °C via `detect_and_convert_temperature()`.

---

### Temperature Assignment (`_assign_temperatures`)

Heuristic assignment based on how many temperatures were extracted:

| Count | Logic |
|-------|-------|
| **4+** | Sort descending → `[0]=T_hot_in`, `[1]=T_hot_out`, `[2]=T_cold_out`, `[3]=T_cold_in` |
| **3** + "cooling" verb | Sort desc → `[0]=T_hot_in`, `[1]=T_hot_out`, `[2]=T_cold_in` |
| **3** + "heating" verb | Sort desc → `[0]=T_hot_in`, `[1]=T_cold_out`, `[2]=T_cold_in` |
| **3** default | Sort desc → `[0]=T_hot_in`, `[1]=T_hot_out`, `[2]=T_cold_in` |
| **2** | Sort desc → `[0]=T_hot_in`, `[1]=T_cold_in` |
| **1** | `T_hot_in` only |

**Minimum required:** 3 temperatures (enforced — error if fewer).

---

### Flow Rate Extraction (`_extract_flows`)

**Regex:** `_RE_FLOW` matches `"50 kg/s"`, `"110000 lb/hr"`, `"100 m³/hr"`

**Supported units:** `kg/s`, `lb/hr`, `lbs/hr`, `m³/hr`, `m3/hr`

**Assignment:**
- 2+ flows → first = `m_dot_hot_kg_s`, second = `m_dot_cold_kg_s`
- 1 flow → `m_dot_hot_kg_s` only

**Minimum required:** 1 flow rate (enforced — error if none).

---

### Pressure Extraction

**Regex:** `_RE_PRESSURE` matches `"5 bar"`, `"100 psi"`, `"500 kPa"`, `"101325 Pa"`, `"1 atm"`

**Side assignment** — scans 100 characters before each match for context words:

| Context words found | Assigned to |
|---------------------|-------------|
| `cold`, `tube`, `cool` | `P_cold_Pa` |
| `hot`, `shell`, `heat` | `P_hot_Pa` |
| No context | Both sides (if not pre-set on state) |

**Default:** 101325.0 Pa (1 atm) if no pressure is specified.

**Pre-set values:** If `state.P_hot_Pa` or `state.P_cold_Pa` are already set (e.g., from MCP/API), they are used as starting values and only overwritten by explicit context matches.

---

### TEMA Preference Extraction

**Regex:** `_RE_TEMA` matches both descriptive terms and 3-letter codes.

**Normalisation map:**

| Input | Normalised output |
|-------|-------------------|
| `floating head` | `AES` |
| `u-tube` / `u tube` / `utube` | `AEU` |
| `fixed tubesheet` / `fixed tube sheet` | `BEM` |
| `pull-through` / `pull through` | `AEP` |
| `AES`, `BEM`, `AEU`, `AEP`, `AEL`, `AEW` | Passed through (uppercased) |

---

## Output Schema

Both paths produce a `StepResult` with these output fields:

| Output Key | Type | Description |
|------------|------|-------------|
| `hot_fluid_name` | `str \| None` | Hot side fluid name |
| `cold_fluid_name` | `str \| None` | Cold side fluid name |
| `T_hot_in_C` | `float \| None` | Hot inlet temperature (°C) |
| `T_hot_out_C` | `float \| None` | Hot outlet temperature (°C) |
| `T_cold_in_C` | `float \| None` | Cold inlet temperature (°C) |
| `T_cold_out_C` | `float \| None` | Cold outlet temperature (°C) |
| `m_dot_hot_kg_s` | `float \| None` | Hot side mass flow rate (kg/s) |
| `m_dot_cold_kg_s` | `float \| None` | Cold side mass flow rate (kg/s) |
| `P_hot_Pa` | `float` | Hot side pressure (Pa) |
| `P_cold_Pa` | `float` | Cold side pressure (Pa) |
| `missing_T_cold_out` | `bool` | Whether cold outlet temp is missing |
| `missing_m_dot_cold` | `bool` | Whether cold flow rate is missing |
| `tema_class` | `str` | *(optional)* TEMA class (R, C, B) |
| `tema_preference` | `str` | *(optional)* Preferred TEMA type |

---

## Validation & Warnings

### Errors (block pipeline)

| Condition | Error message |
|-----------|---------------|
| Empty request | `"Empty request — nothing to parse"` |
| `DesignInput` Pydantic fails | Pydantic error string |
| Fewer than 3 temperatures | `"Found only N temperature(s) — need at least 3"` |
| No flow rate found | `"No flow rate found in request"` |
| No recognisable fluids | `"No recognisable fluid names found"` |
| Only 1 fluid found | `"Only one fluid identified — need both hot and cold sides"` |
| Ambiguous bare word | `"'oil' is ambiguous — please specify (e.g. 'crude oil', 'thermal oil')"` |
| Flow rate ≤ 0 | `"Flow rate must be positive, got {v}"` |

### Warnings (non-blocking)

| Condition | Warning message |
|-----------|-----------------|
| `T_hot_in < T_hot_out` | `"Hot stream gaining heat — T_hot_in < T_hot_out"` |
| `T_cold_in > T_cold_out` | `"Cold stream losing heat — T_cold_in > T_cold_out"` |
| `T_cold_out > T_hot_in` | `"Temperature cross — T_cold_out > T_hot_in"` |

---

## Layer 2 Rules (applied after AI review)

Defined in `step_01_rules.py` — these are **hard rules the AI cannot override**:

| Rule | Check |
|------|-------|
| `_rule_both_fluids` | Both `hot_fluid_name` and `cold_fluid_name` must be present |
| `_rule_at_least_3_temps` | At least 3 of 4 temperatures must be non-None |
| `_rule_at_least_1_flow` | At least one of `m_dot_hot`, `m_dot_cold` must be non-None |
| `_rule_temps_physically_reasonable` | All temps ∈ [−273.15, 1500] °C |
| `_rule_flow_rates_positive` | All flow rates > 0 |
| `_rule_hot_inlet_gt_outlet` | `T_hot_in > T_hot_out` (hot side must lose heat) |
| `_rule_cold_out_lt_hot_in` | `T_cold_out < T_hot_in` (2nd law — no temperature cross) |

---

## AI Review (FULL mode)

Step 1 always triggers AI review via `run_with_review_loop()` in `BaseStep`.

The AI engineer receives:
- Design context (fluids, temps, pressures, duty)
- Step outputs (the extracted parameters)
- Any warnings generated

The AI can:
- **PROCEED** — outputs look correct
- **WARN** — minor concern, adds observation
- **CORRECT** — fix specific fields (e.g., normalise fluid name spelling). *Note: cross-family renaming (oil→water) is now prohibited by the system prompt*
- **ESCALATE** — cannot resolve, needs human input

**Correction loop:** Max 3 correction attempts. After each correction, Layer 1 (`execute()`) re-runs and Layer 2 rules are re-checked. If Layer 2 fails after correction, the correction is rolled back.

---

## Downstream Consumers

| Consumer | Fields used |
|----------|------------|
| **Step 2** (Heat Duty) | `T_hot_in_C`, `T_hot_out_C`, `T_cold_in_C`, `T_cold_out_C`, `m_dot_hot_kg_s`, `m_dot_cold_kg_s` |
| **Step 3** (Fluid Properties) | `hot_fluid_name`, `cold_fluid_name`, `T_hot_in_C`, `T_hot_out_C`, `T_cold_in_C`, `T_cold_out_C`, `P_hot_Pa`, `P_cold_Pa` |
| **Step 4** (Geometry) | `hot_fluid_name`, `cold_fluid_name`, `tema_preference` |
| **Step 5** (LMTD & Sizing) | All temperatures |

---

## Dependencies

| Import | Purpose |
|--------|---------|
| `units_adapter.detect_and_convert_temperature` | Convert F/K → °C |
| `units_adapter.detect_and_convert_flow_rate` | Convert lb/hr, m³/hr → kg/s |
| `units_adapter.detect_and_convert_pressure` | Convert bar, psi, kPa, atm → Pa |
| `models.design_state.DesignState` | Pipeline state bag |
| `models.step_result.StepResult` | Step output container |
| `steps.base.BaseStep` | Abstract base with AI review loop |

---

## Known Limitations

1. **Pressure side assignment** — If pressure has no side context (no "hot"/"cold"/"shell"/"tube" nearby), it defaults to both sides. This can misassign when only one pressure is mentioned generically.
2. **Temperature assignment** is purely sort-based — it doesn't consider proximity to fluid names in the text. With 4 temps, the highest two are always hot and lowest two are always cold.
3. **Flow assignment** is positional (first = hot, second = cold) — doesn't use context words like "oil flow" or "water flow" to decide.
4. **Single-phase scope** — No explicit validation rejects phase-change keywords ("condense", "boil", "evaporate") at this step. Out-of-scope requests slip through and fail later at Step 3.
