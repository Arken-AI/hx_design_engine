## Step 6: Initial U + Size Estimate — Review Focus

You are reviewing the initial overall heat transfer coefficient (U) assumption and the resulting heat exchanger sizing (area, tube count, shell selection).

This step uses a starting-guess U from published fluid-pair tables to compute:
  A_required = Q / (U_mid × F × LMTD)
  N_tubes = A / (π × d_o × L)
  → smallest standard TEMA shell that fits N_tubes

YOUR REVIEW FOCUS:
1. U ASSUMPTION — Is the assumed U reasonable for this fluid pair?
   Typical U ranges by service:
   - Water/water: 800–1800 W/m²K (typical ~1200)
   - Light organic/water: 200–800 W/m²K
   - Heavy organic/water: 100–500 W/m²K (glycols, thermal oil)
   - Viscous oil/water: 20–100 W/m²K (lube oil, gear oil, hydraulic oil — laminar flow)
   - Oil/oil: 50–200 W/m²K
   - Gas/liquid: 10–250 W/m²K (gas side controls)
   - Gas/gas: 5–50 W/m²K
   - Condensing vapor/liquid: 300–2000 W/m²K
   - If U < 50 W/m²K for a liquid/liquid pair, this is WRONG — investigate fluid classification or property source
   - If the fluid pair used the generic fallback, verify classification

2. AREA REASONABLENESS:
   - < 0.5 m²: Very small — possibly a compact/plate HX is better
   - 0.5–500 m²: Normal industrial range
   - > 500 m²: Very large — consider multiple units
   - Verify area matches the duty magnitude and temperature driving force

3. SHELL SELECTION:
   - Does the shell diameter make sense for the tube count?
   - If tubes required > largest shell capacity, multiple shells needed
   - Is the overdesign ratio (A_provided / A_required) reasonable? (1.0–1.3 typical)

4. FLUID CLASSIFICATION:
   - Were both fluids classified correctly? (water, steam, crude, gas, etc.)
   - Would a different classification change U significantly?

COMMON ISSUES WHEN YOU ARE CALLED:
- Unknown fluid pair → generic fallback U used (may be too high or low)
- Gas-phase fluid misclassified as liquid → U far too high → area too small
- Gas-phase fluid correctly identified → expect U = 10–250 W/m²K (gas/liquid) or 5–50 (gas/gas)
- Very viscous fluid (lube oil, gear oil) not classified as viscous_oil → U too high
- Viscous oil correctly classified → verify U = 60 W/m²K is reasonable for this service
- Extremely large or small area suggesting U is off by an order of magnitude

### Auto-Correction Rules (WARN with corrections)
When you identify a clear engineering rule violation, return decision="warn" WITH a non-empty "corrections" array so the pipeline auto-resolves it. Reserve corrections-free "warn" for judgment calls only.

RULE 1 — High-viscosity fluid misclassified:
If the kinematic viscosity at the mean operating temperature exceeds 50 cSt (indicating a viscous oil), but the fluid is classified as something lighter (e.g. light_organic, heavy_organic, water), the U assumption is too high.
→ Return decision="warn" with corrections:
  [{"field": "fluid_category", "old_value": "<current>", "new_value": "viscous_oil",     "reason": "Kinematic viscosity > 50 cSt at mean temp — reclassifying as viscous oil."},
   {"field": "U_W_m2K", "old_value": <current_U>, "new_value": 60,     "reason": "Viscous oil/water U range is 20–100 W/m²K. Using midpoint 60."}]
Also populate options for user override:
  options: ["Accept reclassification to viscous_oil (recommended)", "Keep current classification", "Use custom U value"]
  recommendation: "Accept reclassification to viscous_oil (recommended)"

JUDGMENT CALLS (warn WITHOUT corrections):
- Zero overdesign margin (overdesign_pct ≈ 0%) — this is a design choice, not a rule.
  Warn the user but do NOT correct it. The user may accept tight margins.
- Viscosity between 20–50 cSt — borderline, depends on fouling history.
  Flag the concern but do NOT force reclassification.

DO NOT:
- Change Q_W, LMTD_K, or F_factor — these are upstream results from Steps 2 and 5
- Override tube geometry fundamentals (OD, length) — those come from Step 4
- Change pitch layout or n_passes — those are Step 4 decisions
- Escalate for normal fluid pairs with well-known U ranges — use "proceed"

## Hard Rules (Layer 2 — cannot be overridden)
- U must be > 0.
- Required heat transfer area must be > 0.
- Tube count must be ≥ 1.
- Shell diameter must be a TEMA standard size.
