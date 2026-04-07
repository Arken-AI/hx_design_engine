"""Step 12 validation rules — Convergence Loop.

Step 12 is an orchestrator (loop over Steps 7-11).
No hard rules — Layer 2 checking happens inside sub-steps.
Registered empty for consistency with the validation_rules framework.
"""

from hx_engine.app.core.validation_rules import register_rule  # noqa: F401

# No rules to register for Step 12.
# Sub-steps (7-11) each have their own Layer 2 rules that fire
# inside the convergence loop on every iteration.
