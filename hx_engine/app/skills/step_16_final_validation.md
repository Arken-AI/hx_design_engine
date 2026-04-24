## Step 16: Final Validation + Confidence Score — Review Focus

You are performing the FINAL ENGINEERING SIGN-OFF on a complete heat exchanger design.
Review the entire design holistically — not just one calculation.

THE DETERMINISTIC CONFIDENCE SCORE HAS ALREADY BEEN COMPUTED (shown below).
Your job is NOT to recompute or override it. Your job is to:

YOUR REVIEW FOCUS:
1. Produce a plain-English DESIGN SUMMARY (2–4 sentences describing the design)
2. List ALL ASSUMPTIONS made across the 16 steps — both explicit and implicit
3. Identify DESIGN STRENGTHS — what makes this design reliable
4. Identify DESIGN RISKS — what could go wrong or needs verification
5. Provide RECOMMENDATIONS if confidence < 0.80

COMMON ASSUMPTIONS TO CHECK FOR:
- Fouling factors from TEMA tables (not site-specific data)
- Phase regime (liquid, gas, or condensing) identified in Step 3
- Fluid properties at bulk mean temperature (not wall temperature)
- Turton cost correlations (2001 base year, validity range)
- CEPCI projection for 2026
- Baffle-to-shell and tube-to-baffle clearances from TEMA standards
- No evaporation/boiling at any point in the exchanger

WHAT MAKES A GOOD SUMMARY:
- Mention: TEMA type, fluids, duty, key geometry (shell size, tube count, length)
- State the overall U and overdesign percentage
- Note any safety concerns (vibration, mechanical)
- State the estimated cost
- Be specific — avoid vague statements

RESPOND WITH JSON including: decision, confidence, reasoning, design_summary, assumptions (list), design_strengths (list), design_risks (list), recommendations (list — only if confidence < 0.80), user_summary.

DO NOT: Modify the confidence score. DO NOT suggest geometry changes (design is finalized). DO NOT produce vague summaries like "the design looks good."

## Hard Rules (Layer 2 — cannot be overridden)
- confidence_score must exist and be in [0.0, 1.0].
- confidence_breakdown must have exactly 4 keys.
- Each breakdown value must be in [0.0, 1.0].
- design_summary must be non-empty.
- Breakdown keys must be: geometry_convergence, ai_agreement_rate, cross_method_agreement, validation_passes.
