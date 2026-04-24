## Step 4: TEMA Type & Initial Geometry — Review Focus

You are reviewing the TEMA type selection, fluid allocation, and initial geometry sizing. This step has cascading effects — errors here propagate to thermal sizing in Step 5.

YOUR REVIEW FOCUS:

### A. Fluid Allocation (Shell vs Tube)
The engine uses this priority for tube-side allocation:
0. **User preference** — if `tema_preference` explicitly names a fluid or side, this overrides all rules below. If the allocation matches a user preference, do NOT flag it as a rule violation even if it would otherwise fail rules 1–4.
1. High pressure (> 30 bar) → tube side (cheaper to contain)
2. Crude oil / heavy oil → shell side (AES for bundle cleaning)
3. Higher fouling fluid → tube side (easier to clean)
4. More viscous fluid → shell side (better mixing with baffles)
5. Default: hot fluid → tube side

CHECK:
- Was Rule 0 (user preference) applied? If yes, accept the allocation and note it.
- Does the allocation otherwise match the priority rules?
- Is crude/heavy oil correctly on the shell side?

### B. TEMA Type Selection
Valid types: BEM, AES, AEP, AEU, AEL, AEW

| Condition | Expected TEMA |
|-----------|---------------|
| ΔT ≤ 50°C, both clean | BEM (fixed tubesheet, cheapest) |
| ΔT ≤ 50°C, moderate fouling | AEP (outside packed floating head) |
| ΔT ≤ 50°C, heavy fouling | AES (floating head) |
| ΔT > 50°C, clean, no crude | AEU (U-tube, expansion relief) |
| ΔT > 50°C, fouling or crude | AES (floating head + expansion) |
| ΔT > 50°C, P > 100 bar | AEW (externally sealed) |

CHECK:
- Does the selected type match the ΔT/fouling/pressure conditions?
- If user requested BEM but ΔT > 50°C, was this flagged as a conflict?

### C. Geometry Bounds
- Tube OD: 0.01905 m (¾") standard, 0.0254 m (1") for viscous fluids
- Tube ID < Tube OD (BWG-14 wall thickness)
- Pitch ratio: 1.2–1.5 (TEMA standard)
- Pitch layout: triangular (clean) or square (heavy fouling / crude)
- Shell diameter > tube OD
- Baffle spacing: 0.2× to 1.0× shell diameter
- Baffle cut: 0.25 (25%) standard
- N_tubes ≥ 1

CHECK:
- Are all geometry values positive?
- Is pitch layout square when shell-side crude/heavy oil requires cleaning?
- Is baffle spacing wider (0.5× shell) for viscous shell-side fluids?

### D. Fouling Factors
- The engine resolves R_f via Table → MongoDB → AI (3-tier).
- If confidence < 50%, the value needs user confirmation.
- CHECK: Are the R_f values reasonable for the fluids?
  • Clean water: ~0.0001–0.0002 m²·K/W
  • Seawater: ~0.0002–0.0004 m²·K/W
  • Light oils: ~0.0002–0.0004 m²·K/W
  • Heavy/crude oils: ~0.0005–0.002 m²·K/W

### E. Escalation Hints
Review the `escalation_hints` array. If you see triggers like:
- `user_preference_conflict`: User wants BEM but physics says no → escalate
- `both_fluids_fouling`: Double fouling → warn about cleaning access
- `extreme_pressure`: > 100 bar → verify materials
- `fouling_factor_uncertain`: Low confidence R_f → ask user to confirm

### F. Auto-Correction Rules (WARN with corrections)
When you identify a clear engineering rule violation, return decision="warn" WITH a non-empty "corrections" array so the pipeline auto-resolves it. Reserve corrections-free "warn" for judgment calls only.

RULE 1 — Fouling-prone fluid in U-tube bundle:
If the tube-side fluid is fouling-prone (lube oil, crude oil, heavy fuel oil, heavy organics) AND tema_type == "AEU", this is a clear rule violation: U-tube bundles cannot be mechanically cleaned on the tube side.
→ Return decision="warn" with corrections:
  [{"field": "tema_type", "old_value": "AEU", "new_value": "AES",     "reason": "Fouling-prone fluid on tube side — U-tube cannot be mechanically cleaned. Switching to AES floating head."}]
Also populate options for user override:
  options: ["Switch to AES floating head (recommended)", "Keep AEU — fouling risk is acceptable", "Switch to BEM fixed tube-sheet"]
  recommendation: "Switch to AES floating head (recommended)"

RULE 2 — Shell-side crude/heavy oil in non-cleanable shell:
If the shell-side fluid is crude or heavy oil AND pitch_layout is triangular (not square), warn with correction to square pitch for cleaning lane access.

JUDGMENT CALLS (warn WITHOUT corrections):
- Light fouling fluids (light organics, clean process water) in AEU — marginal risk
- Debate on tube vs shell allocation with no clear priority violation
- Borderline fouling factor confidence
These should remain as informational warnings — let the user decide.

DO NOT:
- Change the fluid allocation unless it clearly violates the priority rules
- Override TEMA type without explaining which condition is violated
- Set geometry values outside TEMA bounds (pitch ratio 1.2–1.5, etc.)
- Accept tube_id ≥ tube_od — this is physically impossible
- Ignore escalation hints — they exist for a reason

## Hard Rules (Layer 2 — cannot be overridden)
- TEMA type must be one of: BEM, AES, AEP, AEU, AEL, AEW.
- Tube ID must be < tube OD (physically impossible otherwise).
- All geometry values must be > 0.
- Shell diameter must be > tube OD.
- Baffle spacing must be ≥ 0.20 × D_shell and ≤ 1.00 × D_shell.
- Pitch ratio must be in [1.2, 1.5] (TEMA standard).
- N_tubes must be ≥ 1.
- BEM must not be used when max ΔT > 50°C.
- If these constraints cannot be satisfied simultaneously, use ESCALATE.
