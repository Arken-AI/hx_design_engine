## Step 7: Tube-Side Heat Transfer Coefficient — Review Focus

You are reviewing the tube-side heat transfer coefficient (h_tube) calculation.
The engine has computed velocity, Re, Pr, selected a Nusselt correlation (Hausen for laminar, Gnielinski for transition/turbulent), applied a viscosity correction, and returned h_tube.

YOUR REVIEW FOCUS:
1. VELOCITY — Is the tube-side velocity reasonable for liquid service?
   - Ideal range: 0.8–2.5 m/s
   - < 0.8 m/s: fouling risk — insufficient turbulence to keep tubes clean
   - > 2.5 m/s: erosion risk — especially for soft metals or dirty fluids
   - 0.3–0.8 m/s: acceptable but marginal (warn)
   - > 3.0 m/s: likely needs geometry change (reduce n_passes)

2. FLOW REGIME:
   - Laminar (Re < 2300): acceptable for viscous fluids (heavy oil, glycol), but h_i will be low. Verify this is realistic for the fluid.
   - Transition (2300–10000): uncertain — flag instability. Flow switches between laminar and turbulent unpredictably.
   - Turbulent (> 10000): ideal for heat transfer. Most water services fall here.

3. h_tube RANGES BY FLUID TYPE:
   - Water: 3,000–10,000 W/m²K
   - Light organics (toluene, ethanol): 500–2,000 W/m²K
   - Heavy oil / crude: 50–500 W/m²K
   - Glycols: 200–1,000 W/m²K
   If h_tube is outside these ranges for the stated fluid, investigate.

4. VISCOSITY CORRECTION (high-viscosity fluids — μ_bulk > 0.1 Pa·s):
   - For μ_bulk > 0.1 Pa·s, the Sieder-Tate wall correction applies. `viscosity_correction` should be meaningfully different from 1.0 — if it is ≈ 1.0 for a viscous fluid, the wall viscosity lookup likely failed (wall props returned bulk props as fallback).
   - If (μ_bulk / μ_wall) > 1.3 or < 0.7, note significant wall effect.
   - Heating case: μ_bulk / μ_wall > 1 (fluid thins at wall → higher h)
   - Cooling case: μ_bulk / μ_wall < 1 (fluid thickens at wall → lower h)

5. DITTUS-BOELTER CROSSCHECK:
   - Divergence > 20% warrants a comment (Gnielinski is primary, DB is check)

CORRECTION OPTIONS:
- Change n_passes (to adjust velocity): more passes → higher velocity → higher Re
- Flag fouling or erosion risk for downstream attention
- DO NOT change tube geometry (OD, ID, length) — those are Step 4 decisions
- DO NOT change n_tubes or shell diameter — those are Step 6 decisions

DECISION GUIDE:
- PROCEED: velocity in range and h_i reasonable for the fluid type
- WARN: borderline velocity or transition zone — human should be aware
- CORRECT: n_passes change needed to fix velocity
- ESCALATE: fundamentally problematic (e.g. h_i orders of magnitude off)

DO NOT:
- Change Q_W, LMTD_K, F_factor, U_W_m2K, or A_m2 — those are upstream results
- Override fluid properties — those come from Step 3
- Change tube OD, ID, or length — those are Step 4 geometry decisions
- Escalate for normal turbulent water with h_i in 3000–10000 range — use proceed

## Hard Rules (Layer 2 — cannot be overridden)
- h_tube must be > 0.
- Tube-side velocity must be in [0.3, 5.0] m/s.
- Reynolds number must be > 0.
- Prandtl number must be > 0.
- Do NOT propose velocity values outside [0.3, 5.0] m/s — Layer 2 will reject them.
