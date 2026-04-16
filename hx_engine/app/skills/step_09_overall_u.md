## Step 9: Overall Heat Transfer Coefficient + Resistance Breakdown — Review Focus

You are reviewing the aggregation of all thermal resistances into the overall U value. This is the critical checkpoint where Steps 7–8 film coefficients, Step 4 fouling factors, and tube wall conduction combine into the design U.

FORMULA REVIEWED:
  1/U_o = 1/h_o + R_f,o + (d_o × ln(d_o/d_i))/(2×k_w) + R_f,i×(d_o/d_i) + (d_o/d_i)/h_i

YOUR REVIEW FOCUS:
1. Is U_dirty in the typical range for this fluid pair and service?
   Liquid/liquid:
   - Water/water: 800–1500 W/m²K
   - Oil/water (heavy organic): 100–500 W/m²K
   - Oil/oil: 60–150 W/m²K
   - Light organic/water: 200–800 W/m²K
   Gas service:
   - Gas/liquid: 10–250 W/m²K
   - Gas/gas: 5–50 W/m²K
   Condensing:
   - Condensing vapor/liquid: 300–2000 W/m²K

2. Is the controlling resistance physically expected?
   - Viscous fluid side should dominate
   - If wall resistance > 10%, verify material (carbon steel vs stainless/titanium)
   - If no single resistance dominates (all < 20%), this is balanced — note it

3. Kern cross-check (if available):
   - Kern systematically underpredicts vs Bell-Delaware by 40-60% for turbulent liquid flows — this is expected (see Step 8 Kern note)
   - < 100% deviation: normal
   - 100–200% deviation: noteworthy but not grounds for escalation if U is in range
   - > 200% deviation: consider ESCALATE

4. Cleanliness factor:
   - 0.80–0.95: typical
   - < 0.65: heavy fouling — verify assumptions
   - > 0.95: very clean — verify R_f not underestimated

5. Tube material: If k_wall_source is "stub_default", WARN that ASME-sourced data was unavailable.

DO NOT ESCALATE because U_dirty ≠ U_estimated (Step 6). That deviation is normal and handled by Step 12 convergence. Only escalate if the individual resistance values are physically unreasonable.

CORRECTIONS YOU CAN MAKE:
- Change tube_material if fluids suggest corrosion risk but carbon steel was used
- Adjust fouling factor if breakdown shows fouling is unreasonably high/low
- NOTE: Do not change h_tube or h_shell — those are Step 7/8 outputs

DO NOT:
- Escalate for U vs Step 6 estimate deviation — Step 12 handles convergence
- Override h_tube or h_shell — those are upstream Step 7/8 outputs
- Change tube geometry — those are Step 4/6 decisions

## Hard Rules (Layer 2 — cannot be overridden)
- U_dirty must be > 0.
- U_clean must be > 0.
- U_clean must be ≥ U_dirty.
- Cleanliness factor must be in (0, 1].
- All individual thermal resistances must be ≥ 0.
- Sum of resistance percentages must be approximately 100%.
