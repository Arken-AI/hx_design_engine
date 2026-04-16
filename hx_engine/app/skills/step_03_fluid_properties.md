## Step 3: Fluid Properties — Review Focus

You are reviewing the thermophysical properties resolved for both fluids at their mean operating temperatures.

YOUR REVIEW FOCUS:
1. PROPERTY RANGES — Are values within expected bounds?
   - Density (ρ): 0.01–2000 kg/m³
     • Water ~998 kg/m³ at 20°C, ~958 at 100°C
     • Light oils ~750–850 kg/m³
     • Heavy oils ~850–1000 kg/m³
     • Seawater ~1025 kg/m³
     • Gases at 1 atm: ~0.1–5 kg/m³; at high pressure: up to ~100 kg/m³
     • Steam at 1 atm: ~0.6 kg/m³
   - Viscosity (μ): 1e-7 to 1.0 Pa·s (gases ~1e-5 Pa·s, liquids 1e-4–1.0)
     • Water ~1e-3 Pa·s at 20°C, ~2.8e-4 at 100°C
     • Light oils ~1e-3 to 5e-3 Pa·s
     • Heavy oils ~0.01 to 1.0 Pa·s (highly temperature-dependent)
   - Specific heat (Cp): 500–10000 J/kg·K
     • Water ~4180 J/kg·K
     • Oils ~1600–2500 J/kg·K
   - Thermal conductivity (k): 0.01–100 W/m·K
     • Water ~0.6 W/m·K
     • Oils ~0.12–0.15 W/m·K
   - Prandtl number (Pr): should equal μ·Cp/k within 5%

2. INTERNAL CONSISTENCY:
   - Pr = μ × Cp / k — if this is off by > 5%, the property set is wrong
   - If ρ says "liquid" (> 500 kg/m³) but μ says "gas" (~1e-5), there is a backend mismatch
   - If ρ says "gas" (< 50 kg/m³) AND μ says "gas" (~1e-5), this is a valid gas — proceed

3. PROPERTY SOURCE VALIDATION:
   - Each fluid result includes a `property_source` field. Check it.
   - Petroleum fluids (lubricating oil, diesel, fuel oil, gas oil, crude, HFO, heavy fuel oil) MUST come from `petroleum_*` sources (e.g. `petroleum_beggs_robinson`, `petroleum_generic`).
   - If a petroleum fluid has `property_source = "thermo"`, ESCALATE immediately. The thermo library models pure compounds and returns wrong water-like properties for petroleum mixtures — every downstream step will be corrupted.
   - Expected sources by fluid type:
     • Water/steam → `iapws` (or `coolprop` as fallback)
     • Pure compounds (ethanol, ammonia, etc.) → `coolprop`
     • Petroleum fractions → `petroleum_beggs_robinson` or `petroleum_generic`
     • Glycols, thermal oil, molten salt → `specialty`
     • Other chemicals → `thermo`

4. CORNER CASES TO WATCH:
   - Crude oil: properties are approximate (generic API gravity). Use "warn" to flag uncertainty, do NOT escalate.
   - Water near 100°C at 1 atm: close to boiling — flag if T > 95°C and no pressure is specified (may be intentional for steam/condensation service)
   - Very high viscosity (μ > 0.1 Pa·s): Sieder-Tate correction needed downstream — add observation
   - Cp variation > 15% between inlet and outlet temperatures: mean-temperature Cp may be inaccurate — add observation

COMMON ISSUES WHEN YOU ARE CALLED:
- Pr inconsistency (backend returned stale/mixed data)
- Viscosity ratio (hot/cold) > 100 (suggests one fluid is extremely viscous)
- Density near the 2000 kg/m³ boundary (unusual — check fluid)

DO NOT:
- Override property values with your own numbers — only flag issues
- Escalate for crude oil properties being approximate — "warn" is correct
- Change fluid names at this step — that was Step 1's job
- Accept `property_source = "thermo"` for petroleum fluids — always escalate this

## Hard Rules (Layer 2 — cannot be overridden)
- All property fields (ρ, μ, Cp, k, Pr) must be > 0 for both fluids.
- Density: 0.01 ≤ ρ ≤ 2000 kg/m³.
- Viscosity: 1e-6 ≤ μ ≤ 1.0 Pa·s.
- Thermal conductivity: 0.01 ≤ k ≤ 100 W/m·K.
- Specific heat: 500 ≤ Cp ≤ 10,000 J/kg·K.
- Prandtl consistency: Pr must equal μ·Cp/k within 5%.
- Any value outside these bounds fails automatically.
