# HX Engine — 10-Design Smoke Test Report

**Date:** 2026-03-27
**Engine:** http://localhost:8100
**Test runner:** `test_10_designs.py`

---

## Summary

| Result | Count |
|--------|-------|
| ✅ Passed | 1 |
| ❌ Failed | 9 |
| **Total** | **10** |

---

## Results Table

| # | Design | Steps Done | Step Decisions | ESCALATE at | Root Cause |
|---|--------|-----------|----------------|-------------|------------|
| ✅ 1 | Crude Oil / Water (baseline) | 1→2→3→4→5 | 1:PROCEED, 4:WARN | — | — |
| ❌ 2 | Steam Condenser | 1 only | 1:WARN | — | `FluidProperties` density validator rejects steam gas (0.57 kg/m³ < min 50) |
| ❌ 3 | Gas Cooler (air / water) | 1 only | 1:PROCEED | — | `FluidProperties` density validator rejects air at 10 bar (8.6 kg/m³ < min 50) |
| ❌ 4 | Lube Oil / Water | 1, 2 | 1:WARN, 2:ESCALATE | Step 2 | Step 1 AI renames "lube oil" → "cooling water"; Step 2 sees >12% energy imbalance → AI ESCALATE |
| ❌ 5 | Ammonia / Brine | 1 only | 1:PROCEED | — | `FluidProperties` density validator rejects ammonia gas (11.2 kg/m³ < min 50) |
| ❌ 6 | Flue Gas / Steam (heat recovery) | 1 only | 1:WARN | — | `FluidProperties` density validator rejects flue gas density; pipeline stops silently |
| ❌ 7 | Glycol / Water cold climate | 1, 2 | 1:WARN, 2:ESCALATE | Step 2 | Water inlet at −10°C is frozen; large energy imbalance → AI correctly ESCALATEs |
| ❌ 8 | Diesel Fuel / Water | 1, 2 | 1:PROCEED, 2:ESCALATE | Step 2 | "diesel fuel" not in petroleum alias table — fluid lookup fails or AI reviews inconsistent data |
| ❌ 9 | Hydrogen / Nitrogen (gas-gas) | 1 only | 1:PROCEED | — | `FluidProperties` density AND cp validators reject hydrogen (ρ=2.7 kg/m³, cp=14 548 J/kg·K) |
| ❌ 10 | Heavy Fuel Oil / Seawater | 1 | 1:ESCALATE | Step 1 | Step 1 AI immediately ESCALATEs — HFO + seawater triggers over-cautious behaviour |

---

## Root Cause Analysis

### Bug 1 — `FluidProperties` density validator too strict (HIGH PRIORITY)

**File:** `hx_engine/app/models/design_state.py` ~line 39
**Validator:** `_check_density` enforces range `[50, 2000]` kg/m³

The range was written for liquids only. Every gas and vapour falls well below the 50 kg/m³ floor:

| Fluid | T (°C) | P (Pa) | Actual density (kg/m³) | Validator |
|-------|--------|--------|------------------------|-----------|
| Steam | 120 | 101 325 | 0.57 | ❌ FAIL |
| Air | 130 | 1 000 000 | 8.6 | ❌ FAIL |
| Ammonia (gas) | 45 | 1 500 000 | 11.2 | ❌ FAIL |
| Flue gas | 300 | 105 000 | ~0.6 | ❌ FAIL |
| Hydrogen | 165 | 5 000 000 | 2.7 | ❌ FAIL |
| Nitrogen | 65 | 4 500 000 | 44.6 | ❌ FAIL (just under 50) |

**What happens in the pipeline:**

`FluidProperties(density_kg_m3=8.6, ...)` raises a pydantic `ValidationError`. This error propagates **outside** the `try/except CalculationError` block in the thermo adapter because `FluidProperties(...)` is constructed after the try block, not inside it. The result:

1. The iapws/CoolProp fallback chain does NOT catch it — only catches `CalculationError`.
2. Step 2 `execute` broad `except Exception` catches it → wraps into `CalculationError`.
3. Pipeline runner catches `CalculationError` → emits `step_error` → returns early.
4. State stays at `current_step=1`. Test polls indefinitely, times out at 120 s.

**Fix:** Change the density lower bound to `0.1` kg/m³:
```python
# models/design_state.py  line ~39
if v is not None and (v < 0.1 or v > 2000):
    raise ValueError(f"density_kg_m3={v} outside physical range [0.1, 2000]")
```

---

### Bug 2 — `FluidProperties` cp validator too strict (HIGH PRIORITY)

**File:** `hx_engine/app/models/design_state.py` ~line 57
**Validator:** `_check_cp` enforces range `[500, 10000]` J/kg·K

Hydrogen (molar mass 2 g/mol) has Cp = 14 548 J/kg·K — above the 10 000 ceiling.
This blocks the hydrogen/nitrogen gas-gas design (Design 9) at Step 2.

**Fix:**
```python
# models/design_state.py  line ~57
if v is not None and (v < 100 or v > 50000):
    raise ValueError(f"cp_J_kgK={v} outside physical range [100, 50000]")
```

---

### Bug 3 — Missing fluid name aliases in the thermo adapter (HIGH PRIORITY)

**File:** `hx_engine/app/adapters/thermo_adapter.py`

Several common engineering fluid names are not recognised by any backend:

| Input name (Step 1 NL output) | Expected resolution | Actual result |
|-------------------------------|--------------------|--------------||
| `"diesel fuel"` | → petroleum `"diesel"` | ❌ Unknown fluid |
| `"lube oil"` | → petroleum `"lubricating oil"` | ❌ Unknown fluid |
| `"light oil"` | → petroleum `"gas oil"` | ❌ Unknown fluid |
| `"flue gas"` | → air approximation | ❌ Fails density check after thermo lookup |
| `"exhaust gas"` | → air approximation | ❌ Fails density check |

Working names: `"diesel"`, `"lubricating oil"`, `"fuel oil"`, `"gas oil"`.

**Fix:** Add a normalisation alias map applied before property lookup:
```python
_FLUID_ALIAS_MAP: dict[str, str] = {
    "diesel fuel":    "diesel",
    "lube oil":       "lubricating oil",
    "light oil":      "gas oil",
    "flue gas":       "air",        # approximation — log warning
    "exhaust gas":    "air",
}
# In get_fluid_properties():
normalised = _FLUID_ALIAS_MAP.get(normalised, normalised)
```

---

### Bug 4 — pydantic `ValidationError` not caught in thermo adapter fallback chain (MEDIUM)

**File:** `hx_engine/app/adapters/thermo_adapter.py`

The iapws fallback only catches `CalculationError`:
```python
try:
    return _get_props_iapws(temperature_C, pressure_Pa)
except CalculationError:        # ← misses pydantic ValidationError!
    ...
```

If iapws returns valid floats but `FluidProperties(...)` construction fails validation, the `ValidationError` escapes the entire fallback chain. This means CoolProp and thermo fallbacks are never tried.

**Fix:** Broaden the catch to `Exception` in the water/steam fallback block:
```python
except Exception:   # catches both CalculationError and ValidationError
    ...
```

---

### Bug 5 — Step 1 AI renames fluid incorrectly (MEDIUM)

**Affects:** Design 4 (Lube Oil / Water)

Step 1 AI changed `hot_fluid_name = "lube oil"` to `"cooling water"`. Step 2 then runs with both fluids as water-family, producing a ~12.7% energy imbalance (different Cp at different T). Step 2 AI ESCALATEs.

**Root cause:** The Step 1 prompt allows AI corrections to fluid names without constraining the correction to the same fluid family.

**Fix:** Add a Step 1 Layer 2 rule that rejects any AI correction that changes an oil/solvent fluid name to a water alias.

---

### Bug 6 — Step 1 ESCALATE for HFO / Seawater (MEDIUM)

**Affects:** Design 10

Step 1 AI immediately ESCALATEs (no outputs generated) for a valid offshore/marine design. HFO + seawater is a well-known combination in marine heat exchangers.

**Fix:** Add explicit examples of heavy hydrocarbon + seawater to the Step 1 prompt (`engineer_review_step01.txt`). Ensure the AI only ESCALATEs when it cannot extract any process data, not when the fluid combination seems unusual.

---

### Bug 7 — Sub-zero pure water not caught at Step 1 (LOW — AI handles it correctly)

**Affects:** Design 7 (Glycol / −10°C "water")

Pure water at −10°C is frozen. The Step 2 AI correctly identifies this and ESCALATEs. This is intended behaviour. The test case was deliberately adversarial.

**Recommendation:** Add a Step 1 Layer 2 hard rule: `T_cold_in_C < 0` with `cold_fluid_name in {"water", "cooling water", "chilled water"}` → validation error "Pure water below 0°C — specify fluid as brine or glycol-water mix."

---

## Fix Priority List

| Priority | Bug | File | Line | Designs Unblocked |
|----------|-----|------|------|-------------------|
| 🔴 HIGH | Density lower bound: `50` → `0.1` kg/m³ | `models/design_state.py` | ~39 | #2, #3, #5, #6 (steam, air, ammonia, flue gas) |
| 🔴 HIGH | cp upper bound: `10000` → `50000` J/kg·K | `models/design_state.py` | ~57 | #9 (hydrogen) |
| 🔴 HIGH | Add fluid aliases: diesel fuel, lube oil, flue gas | `adapters/thermo_adapter.py` | top | #8 (diesel), partially #4, #6 |
| 🟡 MEDIUM | Catch `Exception` in iapws fallback (not just `CalculationError`) | `adapters/thermo_adapter.py` | ~327 | Defensive — prevents silent pipeline stops |
| 🟡 MEDIUM | Prevent oil→water fluid name rename in Step 1 AI corrections | `steps/step_01_requirements.py` | — | #4 (lube oil) |
| 🟡 MEDIUM | Step 1 prompt: allow HFO + seawater without ESCALATE | `prompts/engineer_review_step01.txt` | — | #10 (HFO/seawater) |
| 🟢 LOW | Step 1 rule: sub-zero pure water → hard validation error | `steps/step_01_rules.py` | — | Better UX for #7 |

---

## Pass / Fail by Fluid Category

| Fluid category | Examples | Tested | Status |
|---------------|----------|--------|--------|
| Petroleum liquid vs cooling water | Crude oil, fuel oil, HFO | ✅ 1, partial 10 | ✅ Pass |
| Any **gas or vapour** on either side | Steam, air, ammonia, H₂, N₂, flue gas | ❌ 2, 3, 5, 6, 9 | ❌ ALL FAIL — Bug 1+2 |
| Compound petroleum names | "diesel fuel", "lube oil", "light oil" | ❌ 4, 8 | ❌ FAIL — Bug 3 |
| Specialty liquids (glycol, ethylene glycol) | Glycol | ✅ (adapter OK) | ⚠ AI may escalate for edge-case inputs |
| Physically impossible inputs | −10°C pure water | ❌ 7 | ❌ AI ESCALATE — **correct behaviour** |
| Unusual industrial combos | HFO + seawater | ❌ 10 | ❌ Over-cautious AI — Bug 6 |
