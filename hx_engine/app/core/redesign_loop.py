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


_DIRECTION_INCREASE = "increase"
_DIRECTION_DECREASE = "decrease"


def _bracket_value(value: Any, ladder: list[Any], direction: str) -> Optional[Any]:
    """Pick the smallest larger (increase) or largest smaller (decrease)
    rung when ``value`` is not on the ladder. ``None`` ⇒ first rung
    matching the direction's bias."""
    if direction == _DIRECTION_INCREASE:
        return next((v for v in ladder if value is None or v > value), None)
    if direction == _DIRECTION_DECREASE:
        return next((v for v in reversed(ladder) if value is None or v < value), None)
    return None


def _step_on_ladder(value: Any, ladder: list[Any], direction: str) -> Optional[Any]:
    """Move one rung from a value already on the ladder."""
    idx = ladder.index(value)
    if direction == _DIRECTION_INCREASE:
        return ladder[idx + 1] if idx + 1 < len(ladder) else None
    if direction == _DIRECTION_DECREASE:
        return ladder[idx - 1] if idx - 1 >= 0 else None
    return None


def _next_in_ladder(value: Any, ladder: list[Any], direction: str) -> Optional[Any]:
    """Return the next value up/down a discrete ladder, or None at the cap."""
    if value is None or value not in ladder:
        return _bracket_value(value, ladder, direction)
    return _step_on_ladder(value, ladder, direction)


_BINARY_TOGGLES: dict[str, tuple[str, str]] = {
    # lever -> (preferred_when_increase, preferred_when_decrease)
    "pitch_layout": ("square", "triangular"),
    "multi_shell_arrangement": ("series", "parallel"),
}


def _apply_ladder_on_geom(
    geom: Any,
    attr: str,
    ladder: list[Any],
    direction: str,
    *,
    cast: type,
    require_existing: bool = True,
    default_when_missing: Any = None,
    side_effect: callable | None = None,
) -> tuple[Any, Any] | None:
    """Move a numeric ``geom.<attr>`` one step along ``ladder``.

    ``require_existing=True`` aborts when the attribute is None.
    ``side_effect`` is called after a successful mutation (used to null
    dependent fields like ``tube_id_m`` when ``tube_od_m`` changes).
    """
    if geom is None:
        return None
    raw_old = getattr(geom, attr, None)
    current = raw_old if raw_old is not None else default_when_missing
    if current is None:
        # require_existing=True path: nothing to bump.
        return None
    if raw_old is None and require_existing:
        return None
    new = _next_in_ladder(current, ladder, direction)
    if new is None:
        return None
    setattr(geom, attr, cast(new))
    if side_effect is not None:
        side_effect(geom)
    # Preserve historical old-value semantics: surface the actual previous
    # attribute value, even when we synthesised a default to seed the ladder.
    return raw_old, cast(new)


def _apply_binary_toggle(
    holder: Any,
    attr: str,
    direction: str,
    options: tuple[str, str],
) -> tuple[Any, Any] | None:
    """Flip a categorical attribute between two values."""
    old = getattr(holder, attr)
    if direction == "swap":
        new = options[1] if old == options[0] else options[0]
    elif direction == "increase":
        new = options[0]
    elif direction == "decrease":
        new = options[1]
    else:
        return None
    if new == old:
        return None
    setattr(holder, attr, new)
    return old, new


def _apply_baffle_spacing(geom: Any, direction: str) -> tuple[Any, Any] | None:
    """Multiplicative bump within GeometrySpec validator bounds."""
    if geom is None or geom.baffle_spacing_m is None:
        return None
    old = geom.baffle_spacing_m
    if direction == "increase":
        new = min(old * 1.4, 2.0)        # validator caps at 2.0 m
    elif direction == "decrease":
        new = max(old * 0.7, 0.05)       # validator floors at 0.05 m
    else:
        return None
    if abs(new - old) < 1e-6:
        return None
    geom.baffle_spacing_m = float(new)
    return old, float(new)


def _null_tube_id(geom: Any) -> None:
    geom.tube_id_m = None


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

    ladder_levers: dict[str, dict[str, Any]] = {
        "n_passes": dict(attr="n_passes", ladder=_N_PASSES_LADDER, cast=int),
        "tube_length_m": dict(
            attr="tube_length_m", ladder=_TUBE_LENGTH_LADDER_M, cast=float,
        ),
        "tube_od_m": dict(
            attr="tube_od_m", ladder=_TUBE_OD_LADDER_M, cast=float,
            side_effect=_null_tube_id,
        ),
        "baffle_cut": dict(
            attr="baffle_cut", ladder=_BAFFLE_CUT_LADDER, cast=float,
        ),
        "n_shells": dict(
            attr="n_shells", ladder=_N_SHELLS_LADDER, cast=int,
            require_existing=False, default_when_missing=1,
        ),
        "shell_passes": dict(
            attr="shell_passes", ladder=_SHELL_PASSES_LADDER, cast=int,
            require_existing=False, default_when_missing=1,
        ),
    }

    if lever in ladder_levers:
        return _apply_ladder_on_geom(geom, direction=direction, **ladder_levers[lever])

    if lever == "pitch_layout":
        return _apply_binary_toggle(geom, "pitch_layout", direction, _BINARY_TOGGLES[lever]) if geom else None

    if lever == "baffle_spacing_m":
        return _apply_baffle_spacing(geom, direction)

    if lever == "multi_shell_arrangement":
        return _apply_binary_toggle(
            state, "multi_shell_arrangement", direction, _BINARY_TOGGLES[lever],
        )

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
        while True:
            try:
                state = await self.runner.run(state)
                return state
            except DesignConstraintViolation as violation:
                should_continue = await self._handle_violation(state, violation)
                if not should_continue:
                    return state

    # ------------------------------------------------------------------
    # Violation handling — split into focused helpers (SRP)
    # ------------------------------------------------------------------

    async def _handle_violation(
        self, state: DesignState, violation: DesignConstraintViolation,
    ) -> bool:
        """Process one constraint violation. Returns True iff the caller
        should re-run the pipeline; False means the driver is done."""
        logger.info(
            "[REDESIGN] caught violation at Step %d (%s): %s",
            violation.step_id, violation.constraint, violation.message,
        )

        budget = self._current_budget()
        if state.redesign_attempt_count >= budget:
            await self._surface_budget_exhausted(state, violation, budget)
            return False

        ai_choice = await self._ask_ai(state, violation)
        choice = await self._resolve_choice(state, violation, ai_choice)
        if choice is None:
            await self._surface_budget_exhausted(
                state, violation, budget,
                note="No untried legal levers remain.",
            )
            return False

        applied = await self._apply_choice_with_retry(state, violation, choice)
        if applied is None:
            await self._surface_budget_exhausted(
                state, violation, budget,
                note=f"Could not apply any further lever change "
                     f"(last tried {choice['lever']!r}/{choice['direction']}).",
            )
            return False

        await self._record_and_restart(state, violation, choice, applied, budget)
        return True

    def _current_budget(self) -> int:
        """Per-run iteration cap, tighter when AI is unavailable."""
        return (
            self.max_attempts
            if self.ai_engineer.is_available
            else self.max_fallback_attempts
        )

    async def _ask_ai(
        self, state: DesignState, violation: DesignConstraintViolation,
    ) -> dict[str, Any] | None:
        return await self.ai_engineer.recommend_redesign(
            state=state,
            failed_step_id=violation.step_id,
            constraint=violation.constraint,
            failure_message=violation.message,
            failing_value=violation.failing_value,
            allowed_range=violation.allowed_range,
            legal_levers=self._legal_levers_for(violation),
            history=self._history_payload(state),
        )

    async def _resolve_choice(
        self,
        state: DesignState,
        violation: DesignConstraintViolation,
        ai_choice: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Pick (lever, direction, rationale, …) — AI first, fallback otherwise.

        Returns ``None`` only when neither AI nor the deterministic
        fallback can produce a fresh (lever, direction) pair.
        """
        if ai_choice is not None and not self._already_tried(
            state, ai_choice["lever"], ai_choice.get("direction", ""),
        ):
            return {
                "lever": ai_choice["lever"],
                "direction": ai_choice.get("direction") or "increase",
                "rationale": ai_choice.get("rationale", ""),
                "ai_excerpt": ai_choice.get("ai_response_excerpt", ""),
                "ai_called": True,
                "fallback_used": False,
            }

        fb = self._pick_fallback(state, violation)
        if fb is None:
            return None
        lever, direction = fb
        return {
            "lever": lever,
            "direction": direction,
            "rationale": (
                "Deterministic fallback: AI unavailable or repeated "
                "previous suggestion."
            ),
            "ai_excerpt": "",
            "ai_called": self.ai_engineer.is_available and ai_choice is not None,
            "fallback_used": True,
        }

    async def _apply_choice_with_retry(
        self,
        state: DesignState,
        violation: DesignConstraintViolation,
        choice: dict[str, Any],
    ) -> tuple[Any, Any] | None:
        """Apply the chosen lever. If it can't move and we used AI, try the
        deterministic fallback once before giving up on this iteration."""
        applied = apply_lever(state, choice["lever"], choice["direction"])
        if applied is not None:
            return applied
        if choice["fallback_used"]:
            return None
        fb = self._pick_fallback(state, violation)
        if fb is None:
            return None
        choice["lever"], choice["direction"] = fb
        choice["fallback_used"] = True
        choice["rationale"] += (
            " (AI lever could not be applied; using deterministic fallback.)"
        )
        return apply_lever(state, choice["lever"], choice["direction"])

    async def _record_and_restart(
        self,
        state: DesignState,
        violation: DesignConstraintViolation,
        choice: dict[str, Any],
        applied: tuple[Any, Any],
        budget: int,
    ) -> None:
        """Append history, emit SSE, reset state, persist — in that order."""
        old_value, new_value = applied
        attempt_number = state.redesign_attempt_count + 1

        attempt = self._build_attempt_record(
            attempt_number, state, violation, choice, old_value, new_value,
        )
        state.redesign_history.append(attempt)
        state.redesign_attempt_count = attempt_number

        await self._emit_attempt_event(
            state, violation, choice, old_value, new_value,
            attempt_number, budget,
        )
        self._reset_state_for_restart(state)
        state.notes.append(
            f"[REDESIGN attempt {attempt_number}/{budget}] "
            f"Step {violation.step_id} {violation.constraint!r} → "
            f"{choice['lever']}: {old_value!r} → {new_value!r} "
            f"({choice['direction']}). {choice['rationale']}"
        )
        await self.session_store.save(state.session_id, state)

    @staticmethod
    def _build_attempt_record(
        attempt_number: int,
        state: DesignState,
        violation: DesignConstraintViolation,
        choice: dict[str, Any],
        old_value: Any,
        new_value: Any,
    ) -> RedesignAttempt:
        return RedesignAttempt(
            attempt_number=attempt_number,
            failed_step_id=violation.step_id,
            constraint=violation.constraint,
            failing_value=violation.failing_value,
            allowed_range=list(violation.allowed_range),
            failure_message=violation.message,
            lever=choice["lever"],
            old_value=old_value,
            new_value=new_value,
            direction=choice["direction"],
            rationale=choice["rationale"],
            ai_called=choice["ai_called"],
            ai_response_excerpt=choice["ai_excerpt"],
            fallback_used=choice["fallback_used"],
            outcome="in_progress",
            completed_steps=list(state.completed_steps),
        )

    async def _emit_attempt_event(
        self,
        state: DesignState,
        violation: DesignConstraintViolation,
        choice: dict[str, Any],
        old_value: Any,
        new_value: Any,
        attempt_number: int,
        budget: int,
    ) -> None:
        await self.sse_manager.emit(
            state.session_id,
            RedesignAttemptEvent(
                session_id=state.session_id,
                attempt_number=attempt_number,
                max_attempts=budget,
                failed_step_id=violation.step_id,
                constraint=violation.constraint,
                failure_message=violation.message,
                lever=choice["lever"],
                old_value=old_value,
                new_value=new_value,
                direction=choice["direction"],
                rationale=choice["rationale"],
                ai_called=choice["ai_called"],
                fallback_used=choice["fallback_used"],
                outcome="in_progress",
            ).model_dump(mode="json"),
        )

    @staticmethod
    def _reset_state_for_restart(state: DesignState) -> None:
        """``clear_state_from_step(state, 1)`` nulls geometry (Step 4 owns it),
        but we just intentionally mutated geometry. Snapshot, clear, restore."""
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
