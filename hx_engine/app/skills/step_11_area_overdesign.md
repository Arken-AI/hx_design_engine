## Step 11: Area + Overdesign — Review Focus

YOUR REVIEW FOCUS:

1. Is overdesign percentage in the optimal 10–25% range?
2. Is the required area estimate consistent with the estimated U from Step 6?
3. If overdesign is 0–10% or 25–40%, is the design still acceptable?
4. Are the required and available areas both positive engineering values?
5. Is any undersizing caused by real thermal area shortage rather than a display or unit issue?

COMMON ISSUES:

- Overdesign < 10% — insufficient margin for fouling/uncertainty
- Overdesign > 30% — oversized, cost inefficient
- Large deviation between estimated and calculated area — indicates poor initial U guess
- Negative overdesign means available area is below required area and the exchanger is undersized
- Zero or near-zero area usually indicates an upstream calculation or unit conversion failure

DO NOT:

- Accept negative overdesign. Negative overdesign is a hard fail.
- Recommend direct area changes or manually edit area fields. Step 12 convergence handles area changes through geometry iteration.
- Treat a Step 6 estimated-area mismatch as a standalone failure when the actual available area is sufficient.

## Hard Rules (Layer 2 — cannot be overridden)

- Required area must be > 0.
- Available area must be > 0.
- Overdesign percentage must not be negative (A_available ≥ A_required).
- If overdesign is negative, use decision="escalate" unless deterministic logic has already triggered a redesign path.

## Step 12 Boundary

Step 11 reviews whether the computed area and overdesign are acceptable. It must not prescribe manual edits to A_required, A_available, U, or LMTD. If area is insufficient, Step 12 convergence is responsible for changing geometry and re-running the design loop.
