## Step 8: Shell-Side Heat Transfer Coefficient (Bell-Delaware) — Review Focus

You are reviewing the shell-side heat transfer coefficient (h_shell) computed using the full Bell-Delaware method with five J-correction factors.

YOUR REVIEW FOCUS:
1. J-FACTOR PRODUCTS:
   - J_c (baffle cut): 0.4–1.0 typical
   - J_l (leakage): 0.5–1.0 typical
   - J_b (bundle): 0.3–1.0 typical
   - J_s (sealing): 0.7–1.0 typical
   - J_r (inlet/exit): 0.3–0.9 typical
   - **Full product J_c × J_l × J_b × J_s × J_r ≥ 0.35** — if `J_product` < 0.35, escalate with recommendation to reduce clearances or add sealing strips
   - Use `J_product` from outputs (all five factors combined) — do NOT compute a partial product from individual J values

2. h_shell RANGES — apply based on the shell-side fluid and phase:
   Single-phase liquid:
   - Water / cooling water: 2,000–8,000 W/m²K
   - Light organics (toluene, ethanol, glycol): 300–1,500 W/m²K
   - Heavy oil / crude / lube oil: 50–500 W/m²K
   Single-phase gas:
   - Gases at moderate pressure: 20–200 W/m²K
   - Gases at high pressure (>10 bar): 100–500 W/m²K
   Condensing:
   - Condensing vapor (Shah correlation): 1,000–15,000 W/m²K
   If h_shell is outside the expected range for the identified shell-side fluid AND phase, investigate.

3. KERN CROSS-CHECK:
   **IMPORTANT**: The Kern method (1950) systematically underpredicts h_o compared to Bell-Delaware by 40-60% for turbulent liquid flows. This is a well-documented limitation (Serth 2007, Thulukkanam 2013) — the Kern correlation uses a simplified equivalent diameter and does NOT account for crossflow enhancement, bypass, or leakage corrections that Bell-Delaware provides.
   - < 100% divergence: NORMAL — within expected Kern underprediction range
   - 100–200% divergence: NOTEWORTHY but still expected for high-Re liquid flows — do NOT escalate if h_shell is within the expected range for the shell-side fluid
   - > 200% divergence: ANOMALOUS — suggests geometry or property input error, ESCALATE
   - The Kern value should NEVER override the Bell-Delaware result
   - Focus your validation on whether h_shell falls in the expected range for the identified shell-side fluid (Section 2 above), NOT on the Kern divergence percentage

4. WALL TEMPERATURE EFFECT:
   - Cross-check `mu_wall_Pa_s` against expected viscosity for the shell-side fluid:
     • Water: 0.0002–0.001 Pa·s
     • Light organics: 0.001–0.005 Pa·s
     • Heavy oil / lube oil: 0.005–0.5 Pa·s
   - If `mu_wall` falls outside the expected range for the identified shell-side fluid, ESCALATE — the wall viscosity lookup used the wrong property backend (most likely thermo returning water-like values for a petroleum fluid).
   - Large viscosity ratio (μ_bulk/μ_wall > 2) indicates significant viscous heating — note this as an observation

CORRECTION OPTIONS:
- Adjust baffle cut, baffle spacing, or sealing strips to improve J-factors
- DO NOT change tube geometry or shell diameter — those are Step 4/6 decisions

DO NOT:
- Escalate for normal J-factor products in [0.35, 0.80] range
- Escalate for Kern divergence < 200% when h_shell is within the expected fluid range
- Override h_shell with Kern value — Bell-Delaware is the primary method

## Hard Rules (Layer 2 — cannot be overridden)
- h_shell must be > 0.
- Each J-factor (J_c, J_l, J_b, J_s, J_r) must be in [0.2, 1.2].
- Combined J-product (J_c × J_l × J_b) must be > 0.30.
- Shell-side Reynolds number must be > 0.
- Do NOT propose J-factor values outside [0.2, 1.2] — Layer 2 will reject them.
