"""RedesignDriver — global redesign loop on top of PipelineRunner.

When a downstream step raises :class:`DesignConstraintViolation`, this
driver picks one upstream lever (via the AI advisor or a deterministic
fallback), mutates the design state, and restarts the pipeline from
Step 1. It tracks every attempt in ``state.redesign_history`` so the AI
prompt avoids repeating itself, and gives up after a configurable
budget — at which point it surfaces the closest-feasible design and a
clean explanation instead of a stack trace.

See ``artifacts/bugs/enhancement_xstack_design_constraint_redesign_loop.md``
for the design intent and the original spec.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from hx_engine.app.core.ai_engineer import AIEngineer
from hx_engine.app.core.exceptions import DesignConstraintViolation
from hx_engine.app.core.pipeline_runner import PipelineRunner
from hx_engine.app.core.session_store import SessionStore
from hx_engine.app.core.sse_manager import SSEManager
from hx_engine.app.core.state_utils import clear_state_from_step
from hx_engine.app.models.design_state import DesignState
from hx_engine.app.models.sse_events import RedesignAttemptEvent, StepErrorEvent
from hx_engine.app.models.step_result import RedesignAttempt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Global iteration budget for the redesign loop (per-run, not per-failure).
#: The 8-attempt default matches the user's product decision recorded in
#: the enhancement spec; override via ``RedesignDriver(max_attempts=…)``.
MAX_REDESIGN_ATTEMPTS = 8

#: Tighter budget when the AI is unavailable. Deterministic fallback levers
#: are dumb (round-robin over a fixed sequence) — keep the loop short to
#: avoid burning compute on repeated bad guesses, then surface the
#: closest-feasible design.
MAX_FALLBACK_ATTEMPTS = 2


# ---------------------------------------------------------------------------
# Canonical lever set (per user product decision: "minimal hardcoded set")
# ---------------------------------------------------------------------------

#: All levers the redesign loop is allowed to vary. Names are exactly the
#: ``DesignState`` / ``GeometrySpec`` field names so the AI prompt and the
#: deterministic mutator agree on the wire.
LEGAL_LEVERS: list[str] = [
    "n_passes",
    "tube_length_m",
    "tube_od_m",
    "pitch_layout",
    "baffle_cut",
    "baffle_spacing_m",
    "n_shells",
    "shell_passes",
    "multi_shell_arrangement",
]

#: Standard tube lengths (m) — 6, 8, 10, 12, 16, 20 ft.
_TUBE_LENGTH_LADDER_M: list[float] = [1.83, 2.44, 3.05, 3.66, 4.88, 6.10]
#: Standard tube ODs (m) — 3/4", 1", 1¼".
_TUBE_OD_LADDER_M: list[float] = [0.01905, 0.02540, 0.03175]
#: Tube-pass options — TEMA caps at 8.
_N_PASSES_LADDER: list[int] = [1, 2, 4, 6, 8]
#: Baffle cut options (fraction of shell ID).
_BAFFLE_CUT_LADDER: list[float] = [0.20, 0.25, 0.30, 0.35]
#: Shell-passes options.
_SHELL_PASSES_LADDER: list[int] = [1, 2]
#: Number-of-shells-in-series options.
_N_SHELLS_LADDER: list[int] = [1, 2, 3]

#: Deterministic fallback sequence — ordered list of (lever, direction)
#: tuples used round-robin per constraint family. Direction is "increase",
#: "decrease", or "swap". The driver applies the next *unseen* combo.
_FALLBACK_SEQUENCE: list[tuple[str, str]] = [
    ("n_passes", "increase"),
    ("tube_length_m", "increase"),
    ("n_shells", "increase"),
    ("baffle_spacing_m", "decrease"),
    ("pitch_layout", "swap"),
    ("baffle_cut", "increase"),
    ("tube_od_m", "increase"),
    ("shell_passes", "increase"),
    ("multi_shell_arrangement", "swap"),
]


# ---------------------------------------------------------------------------
# Lever application
# ---------------------------------------------------------------------------


def _next_in_ladder(value: Any, ladder: list[Any], direction: str) -> Optional[Any]:
    """Return the next value up/down a discrete ladder, or None at the cap."""
    if value is None or value not in ladder:
        # Pick the smallest larger value when increasing, largest smaller when
        # decreasing — handles the "geometry not yet set" edge case.
        if direction == "increase":
            for v in ladder:
                if value is None or v > value:
                    return v
            return None
        if direction == "decrease":
            for v in reversed(ladder):
                if value is None or v < value:
                    return v
            return None
        return None

    idx = ladder.index(value)
    if direction == "increase":
        return ladder[idx + 1] if idx + 1 < len(ladder) else None
    if direction == "decrease":
        return ladder[idx - 1] if idx - 1 >= 0 else None
    return None


def apply_lever(
    state: DesignState,
    lever: str,
    direction: str,
) -> tuple[Any, Any] | None:
    """Mutate ``state`` according to (lever, direction).

    Returns ``(old_value, new_value)`` on success, or ``None`` when the
    requested change is infeasible (already at cap/floor, lever not
    applicable to current state, etc.). All mutations are local to
    ``state.geometry`` and a small set of top-level fields — the
    redesign driver always pairs this with ``clear_state_from_step(state, 1)``
    so downstream cached values are wiped before the pipeline restart.
    """
    geom = state.geometry

    if lever == "n_passes":
        if geom is None or geom.n_passes is None:
            return None
        new = _next_in_ladder(geom.n_passes, _N_PASSES_LADDER, direction)
        if new is None:
            return None
        old = geom.n_passes
        geom.n_passes = int(new)
        return old, int(new)

    if lever == "tube_length_m":
        if geom is None:
            return None
        new = _next_in_ladder(geom.tube_length_m, _TUBE_LENGTH_LADDER_M, direction)
        if new is None:
            return None
        old = geom.tube_length_m
        geom.tube_length_m = float(new)
        return old, float(new)

    if lever == "tube_od_m":
        if geom is None:
            return None
        new = _next_in_ladder(geom.tube_od_m, _TUBE_OD_LADDER_M, direction)
        if new is None:
            return None
        old = geom.tube_od_m
        geom.tube_od_m = float(new)
        # tube_id_m would now be inconsistent — null it so Step 4 recomputes.
        geom.tube_id_m = None
        return old, float(new)

    if lever == "pitch_layout":
        if geom is None:
            return None
        old = geom.pitch_layout
        if direction == "swap":
            new = "square" if old == "triangular" else "triangular"
        elif direction == "increase":
            new = "square"
        elif direction == "decrease":
            new = "triangular"
        else:
            return None
        if new == old:
            return None
        geom.pitch_layout = new
        return old, new

    if lever == "baffle_cut":
        if geom is None:
            return None
        new = _next_in_ladder(geom.baffle_cut, _BAFFLE_CUT_LADDER, direction)
        if new is None:
            return None
        old = geom.baffle_cut
        geom.baffle_cut = float(new)
        return old, float(new)

    if lever == "baffle_spacing_m":
        if geom is None or geom.baffle_spacing_m is None:
            return None
        old = geom.baffle_spacing_m
        if direction == "increase":
            new = min(old * 1.4, 2.0)   # GeometrySpec validator caps at 2.0 m
        elif direction == "decrease":
            new = max(old * 0.7, 0.05)  # GeometrySpec validator floors at 0.05 m
        else:
            return None
        if abs(new - old) < 1e-6:
            return None
        geom.baffle_spacing_m = float(new)
        return old, float(new)

    if lever == "n_shells":
        if geom is None or geom.n_shells is None:
            # Initialise to 1 so the ladder works.
            current = 1
        else:
            current = geom.n_shells
        new = _next_in_ladder(current, _N_SHELLS_LADDER, direction)
        if new is None:
            return None
        old = geom.n_shells if geom else None
        if geom is None:
            return None
        geom.n_shells = int(new)
        return old, int(new)

    if lever == "shell_passes":
        if geom is None or geom.shell_passes is None:
            current = 1
        else:
            current = geom.shell_passes
        new = _next_in_ladder(current, _SHELL_PASSES_LADDER, direction)
        if new is None:
            return None
        old = geom.shell_passes if geom else None
        if geom is None:
            return None
        geom.shell_passes = int(new)
        return old, int(new)

    if lever == "multi_shell_arrangement":
        old = state.multi_shell_arrangement
        if direction == "swap":
            new = "parallel" if old == "series" else "series"
        elif direction in ("increase", "decrease"):
            new = "series" if old != "series" else "parallel"
        else:
            return None
        if new == old:
            return None
        state.multi_shell_arrangement = new
        return old, new

    logger.warning("[REDESIGN] unknown lever %r — ignoring", lever)
    return None


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


class RedesignDriver:
    """Wraps :class:`PipelineRunner` with a constraint-violation redesign loop.

    Usage::

        driver = RedesignDriver(runner, ai_engineer, sse_manager, session_store)
        await driver.run(state)
    """

    def __init__(
        self,
        runner: PipelineRunner,
        ai_engineer: AIEngineer,
        sse_manager: SSEManager,
        session_store: SessionStore,
        *,
        max_attempts: int = MAX_REDESIGN_ATTEMPTS,
        max_fallback_attempts: int = MAX_FALLBACK_ATTEMPTS,
    ) -> None:
        self.runner = runner
        self.ai_engineer = ai_engineer
        self.sse_manager = sse_manager
        self.session_store = session_store
        self.max_attempts = max_attempts
        self.max_fallback_attempts = max_fallback_attempts

    async def run(self, state: DesignState) -> DesignState:
        """Execute the pipeline with redesign-loop wrapping.

        Returns when either the pipeline completes successfully, the
        redesign budget is exhausted, or an unrecoverable error occurs.
        """
        session_id = state.session_id

        while True:
            try:
                state = await self.runner.run(state)
                # No violation raised → pipeline either completed, errored
                # for some other reason, or was orphaned. Either way the
                # redesign driver is done.
                return state

            except DesignConstraintViolation as violation:
                logger.info(
                    "[REDESIGN] caught violation at Step %d (%s): %s",
                    violation.step_id, violation.constraint, violation.message,
                )

                # Cap check — global per-run budget.
                budget = (
                    self.max_attempts
                    if self.ai_engineer.is_available
                    else self.max_fallback_attempts
                )
                if state.redesign_attempt_count >= budget:
                    await self._surface_budget_exhausted(
                        state, violation, budget,
                    )
                    return state

                # Decide what to tweak.
                attempt_number = state.redesign_attempt_count + 1
                history_payload = self._history_payload(state)
                legal = self._legal_levers_for(violation)

                ai_choice = await self.ai_engineer.recommend_redesign(
                    state=state,
                    failed_step_id=violation.step_id,
                    constraint=violation.constraint,
                    failure_message=violation.message,
                    failing_value=violation.failing_value,
                    allowed_range=violation.allowed_range,
                    legal_levers=legal,
                    history=history_payload,
                )

                fallback_used = False
                if ai_choice is not None and not self._already_tried(
                    state, ai_choice["lever"], ai_choice.get("direction", "")
                ):
                    lever = ai_choice["lever"]
                    direction = ai_choice.get("direction") or "increase"
                    rationale = ai_choice.get("rationale", "")
                    ai_excerpt = ai_choice.get("ai_response_excerpt", "")
                    ai_called = True
                else:
                    fallback_used = True
                    fb = self._pick_fallback(state, violation)
                    if fb is None:
                        # No remaining lever to try.
                        await self._surface_budget_exhausted(
                            state, violation, budget,
                            note="No untried legal levers remain.",
                        )
                        return state
                    lever, direction = fb
                    rationale = (
                        "Deterministic fallback: AI unavailable or repeated "
                        "previous suggestion."
                    )
                    ai_excerpt = ""
                    ai_called = self.ai_engineer.is_available and ai_choice is not None

                # Apply the lever.
                applied = apply_lever(state, lever, direction)
                if applied is None:
                    # Lever can't move — try the deterministic fallback once
                    # more before giving up on this iteration.
                    if not fallback_used:
                        fb = self._pick_fallback(state, violation)
                        if fb is not None:
                            lever, direction = fb
                            applied = apply_lever(state, lever, direction)
                            fallback_used = True
                            rationale += (
                                " (AI lever could not be applied; using "
                                "deterministic fallback.)"
                            )
                    if applied is None:
                        await self._surface_budget_exhausted(
                            state, violation, budget,
                            note=f"Could not apply any further lever change "
                                 f"(last tried {lever!r}/{direction}).",
                        )
                        return state

                old_value, new_value = applied

                # Record the attempt.
                attempt = RedesignAttempt(
                    attempt_number=attempt_number,
                    failed_step_id=violation.step_id,
                    constraint=violation.constraint,
                    failing_value=violation.failing_value,
                    allowed_range=list(violation.allowed_range),
                    failure_message=violation.message,
                    lever=lever,
                    old_value=old_value,
                    new_value=new_value,
                    direction=direction,
                    rationale=rationale,
                    ai_called=ai_called,
                    ai_response_excerpt=ai_excerpt,
                    fallback_used=fallback_used,
                    outcome="in_progress",
                    completed_steps=list(state.completed_steps),
                )
                state.redesign_history.append(attempt)
                state.redesign_attempt_count = attempt_number

                # Emit SSE so the frontend can update its timeline.
                await self.sse_manager.emit(
                    session_id,
                    RedesignAttemptEvent(
                        session_id=session_id,
                        attempt_number=attempt_number,
                        max_attempts=budget,
                        failed_step_id=violation.step_id,
                        constraint=violation.constraint,
                        failure_message=violation.message,
                        lever=lever,
                        old_value=old_value,
                        new_value=new_value,
                        direction=direction,
                        rationale=rationale,
                        ai_called=ai_called,
                        fallback_used=fallback_used,
                        outcome="in_progress",
                    ).model_dump(mode="json"),
                )

                # Reset state for the restart. ``clear_state_from_step(state, 1)``
                # nulls every step-owned field (including ``state.geometry``,
                # which Step 4 owns) — but we just *intentionally* mutated
                # geometry to apply the lever. Snapshot the lever-touched
                # fields, clear, then restore so the restart honors the
                # redesign decision.
                geom_snapshot = state.geometry.model_copy() if state.geometry else None
                arrangement_snapshot = state.multi_shell_arrangement
                clear_state_from_step(state, 1)
                state.geometry = geom_snapshot
                state.multi_shell_arrangement = arrangement_snapshot
                state.completed_steps = []
                state.current_step = 0
                state.pipeline_status = "running"
                state.is_complete = False
                state.waiting_for_user = False
                state.notes.append(
                    f"[REDESIGN attempt {attempt_number}/{budget}] "
                    f"Step {violation.step_id} {violation.constraint!r} → "
                    f"{lever}: {old_value!r} → {new_value!r} ({direction}). "
                    f"{rationale}"
                )
                await self.session_store.save(session_id, state)
                # Loop back and re-run the pipeline.
                continue

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _history_payload(self, state: DesignState) -> list[dict[str, Any]]:
        """Compact history list for the AI prompt."""
        return [
            {
                "attempt_number": a.attempt_number,
                "lever": a.lever,
                "old_value": a.old_value,
                "new_value": a.new_value,
                "direction": a.direction,
                "outcome": a.outcome,
                "constraint": a.constraint,
            }
            for a in state.redesign_history
        ]

    def _legal_levers_for(self, violation: DesignConstraintViolation) -> list[str]:
        """Combine the violation's suggested levers with the global legal set.

        The violation can hint at the most relevant levers (e.g. "n_passes"
        for a tube-velocity failure) — we put those first so the AI is
        biased toward them, but never block any lever from the canonical
        set.
        """
        suggested = [s for s in violation.suggested_levers if s in LEGAL_LEVERS]
        rest = [l for l in LEGAL_LEVERS if l not in suggested]
        return suggested + rest

    def _already_tried(
        self, state: DesignState, lever: str, direction: str,
    ) -> bool:
        for a in state.redesign_history:
            if a.lever == lever and a.direction == direction:
                return True
        return False

    def _pick_fallback(
        self, state: DesignState, violation: DesignConstraintViolation,
    ) -> Optional[tuple[str, str]]:
        """Pick the next untried (lever, direction) from the fallback sequence.

        Prefer levers that the violation itself suggested (typed-in priority).
        """
        suggested_first: list[tuple[str, str]] = []
        for s in violation.suggested_levers:
            if s in LEGAL_LEVERS:
                # Default direction = "increase" except for swaps.
                d = "swap" if s in ("pitch_layout", "multi_shell_arrangement") else "increase"
                suggested_first.append((s, d))

        for combo in suggested_first + _FALLBACK_SEQUENCE:
            lever, direction = combo
            if not self._already_tried(state, lever, direction):
                return combo
        return None

    async def _surface_budget_exhausted(
        self,
        state: DesignState,
        violation: DesignConstraintViolation,
        budget: int,
        note: str = "",
    ) -> None:
        """Emit a clean failure with the closest-feasible design + reason.

        "Closest feasible" = the redesign attempt that completed the most
        pipeline steps before its own failure. If no attempt completed any
        steps, we fall back to the original pre-loop snapshot — which
        means there is nothing to surface beyond the violation message.
        """
        session_id = state.session_id

        closest = max(
            state.redesign_history,
            key=lambda a: len(a.completed_steps),
            default=None,
        )

        if closest is not None:
            closest_summary = (
                f"Closest feasible attempt: #{closest.attempt_number} "
                f"({closest.lever}: {closest.old_value!r} → {closest.new_value!r}) "
                f"reached Step {max(closest.completed_steps) if closest.completed_steps else 0} "
                f"of 16 before failing on '{closest.constraint}'."
            )
        else:
            closest_summary = (
                "No prior attempt completed any steps — the very first run "
                "tripped this constraint."
            )

        state.pipeline_status = "error"
        state.is_complete = False
        await self.session_store.save(session_id, state)

        await self.sse_manager.emit(
            session_id,
            StepErrorEvent(
                session_id=session_id,
                step_id=violation.step_id,
                step_name=f"Step {violation.step_id}",
                message=(
                    f"Redesign budget ({budget} attempts) exhausted while "
                    f"trying to satisfy '{violation.constraint}'. "
                    f"{violation.message}"
                ),
                observation=closest_summary,
                recommendation=(
                    note
                    or "Review the redesign history and adjust the input "
                       "specification (fluid choice, temperatures, allowed "
                       "TEMA type) before re-running."
                ),
            ).model_dump(mode="json"),
        )
