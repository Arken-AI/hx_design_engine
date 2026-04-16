## Step 15: Cost Estimate — Review Focus

YOUR REVIEW FOCUS:
1. Is the bare module cost reasonable for this size, material, and pressure?
2. Is cost/m² within the expected range for the tube material?
3. Are material factor and pressure factor reasonable?
4. Is the CEPCI index current (< 90 days old)?

COMMON ISSUES:
- Very high cost/m² may indicate expensive material where cheaper alternative exists
- Very low cost may indicate missing pressure or material correction
- Interpolated material factor (not from Turton directly) — verify reasonableness

DO NOT: Override cost calculations. Flag anomalies for user review.

## Hard Rules (Layer 2 — cannot be overridden)
- cost_usd must be present and > 0.
- cost_breakdown must be present.
- Material factor (F_M) must be > 0.
- Pressure factor (F_P) must be ≥ 1.0.
- cost_per_m2 must be within the per-material validation range.
