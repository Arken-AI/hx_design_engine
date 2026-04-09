"""PipelineRunner — orchestrates Steps 1-5 with SSE emission.

Creates a DesignState from the user request, runs each step in sequence
through run_with_review_loop(), emits SSE events, and handles
ESCALATED pauses (awaiting user response via SSEManager future).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Optional

from hx_engine.app.core.ai_engineer import AIEngineer
from hx_engine.app.core.exceptions import CalculationError, StepHardFailure
from hx_engine.app.core.session_store import SessionStore
from hx_engine.app.core.sse_manager import SSEManager
from hx_engine.app.core.state_utils import apply_outputs
from hx_engine.app.core.validation_rules import check as check_validation_rules
from hx_engine.app.adapters.thermo_adapter import get_fluid_properties
from hx_engine.app.models.design_state import DesignState
from hx_engine.app.models.sse_events import (
    DesignCompleteEvent,
    IterationProgressEvent,
    StepApprovedEvent,
    StepCorrectedEvent,
    StepErrorEvent,
    StepEscalatedEvent,
    StepStartedEvent,
    StepWarningEvent,
)
from hx_engine.app.models.step_result import AIDecisionEnum, StepResult
from hx_engine.app.steps.base import _serialize_outputs
from hx_engine.app.steps.step_01_requirements import Step01Requirements
from hx_engine.app.steps.step_02_heat_duty import Step02HeatDuty
from hx_engine.app.steps.step_03_fluid_props import Step03FluidProperties
from hx_engine.app.steps.step_04_tema_geometry import Step04TEMAGeometry
from hx_engine.app.steps.step_05_lmtd import Step05LMTD
from hx_engine.app.steps.step_06_initial_u import Step06InitialU
from hx_engine.app.steps.step_07_tube_side_h import Step07TubeSideH
from hx_engine.app.steps.step_08_shell_side_h import Step08ShellSideH
from hx_engine.app.steps.step_09_overall_u import Step09OverallU
from hx_engine.app.steps.step_10_pressure_drops import Step10PressureDrops
from hx_engine.app.steps.step_11_area_overdesign import Step11AreaOverdesign
from hx_engine.app.steps.step_12_convergence import Step12Convergence
from hx_engine.app.steps.step_13_vibration import Step13VibrationCheck

logger = logging.getLogger(__name__)

# Ordered pipeline — steps run sequentially
PIPELINE_STEPS = [
    Step01Requirements,
    Step02HeatDuty,
    Step03FluidProperties,
    Step04TEMAGeometry,
    Step05LMTD,
    Step06InitialU,
    Step07TubeSideH,
    Step08ShellSideH,
    Step09OverallU,
    Step10PressureDrops,
    Step11AreaOverdesign,
]

# How long (seconds) to wait for user response on ESCALATE
USER_RESPONSE_TIMEOUT = 3600  # 1 hour — gives user time to refresh and return

# How long (seconds) to wait for user response on actionable WARNING
# (shorter than ESCALATE — auto-proceeds with current values on timeout)
WARNING_PAUSE_TIMEOUT = 120


def _refresh_fluid_props_for_shell_side(state: DesignState) -> None:
    """Re-fetch fluid properties for the shell-side fluid at the mean shell temperature.

    This ensures that after a fluid-swap or viscosity-verification escalation,
    Step 8 re-runs with the correct (fresh) thermophysical properties rather
    than the stale values cached by Step 3.
    """
    from hx_engine.app.models.design_state import FluidProperties

    shell_side = state.shell_side_fluid  # "hot" or "cold"
    if shell_side == "hot":
        fluid_name = state.hot_fluid_name
        T_in = state.T_hot_in_C
        T_out = state.T_hot_out_C
        pressure = state.P_hot_Pa
    else:
        fluid_name = state.cold_fluid_name
        T_in = state.T_cold_in_C
        T_out = state.T_cold_out_C
        pressure = state.P_cold_Pa

    if fluid_name is None or T_in is None or T_out is None:
        logger.warning("Cannot refresh shell-side fluid props — missing fluid name or temps")
        return

    T_mean = (T_in + T_out) / 2.0
    effective_pressure = pressure if pressure is not None else 101325.0  # fallback: atmospheric
    try:
        new_props = get_fluid_properties(fluid_name, T_mean, effective_pressure)
        if shell_side == "hot":
            state.hot_fluid_props = new_props
        else:
            state.cold_fluid_props = new_props
        logger.info(
            "Refreshed %s-side (shell) fluid props for %s at T_mean=%.1f°C: "
            "mu=%.6f Pa·s, rho=%.1f kg/m³",
            shell_side, fluid_name, T_mean,
            new_props.viscosity_Pa_s, new_props.density_kg_m3,
        )
    except Exception:
        logger.exception("Failed to refresh shell-side fluid properties for %s", fluid_name)


class PipelineRunner:
    """Runs the 5-step HX design pipeline for a single session."""

    def __init__(
        self,
        session_store: SessionStore,
        sse_manager: SSEManager,
        ai_engineer: AIEngineer,
    ) -> None:
        self.session_store = session_store
        self.sse_manager = sse_manager
        self.ai_engineer = ai_engineer

    async def run(self, state: DesignState) -> DesignState:
        """Execute the full pipeline, emitting SSE events for each step.

        This is designed to be called in a background task so the HTTP
        response returns immediately with the session_id.
        """
        session_id = state.session_id
        state.pipeline_status = "running"

        try:
            for step_cls in PIPELINE_STEPS:
                step = step_cls()

                # --- orphan check ---
                if await self.session_store.is_orphaned(session_id):
                    logger.warning(
                        "Session %s orphaned at step %d, aborting pipeline",
                        session_id, step.step_id,
                    )
                    state.pipeline_status = "orphaned"
                    break

                # --- heartbeat ---
                await self.session_store.heartbeat(session_id)

                # --- emit step_started ---
                await self.sse_manager.emit(
                    session_id,
                    StepStartedEvent(
                        session_id=session_id,
                        step_id=step.step_id,
                        step_name=step.step_name,
                    ).model_dump(),
                )

                # --- execute step with AI review loop (re-runs on ESCALATE/WARNING) ---
                max_escalations = 2
                escalation_count = 0
                max_actionable_warnings = 1
                warning_pause_count = 0
                while True:
                    start_ms = time.monotonic()
                    try:
                        result: StepResult = await step.run_with_review_loop(
                            state, self.ai_engineer
                        )
                    except CalculationError as exc:
                        state.pipeline_status = "error"
                        await self._emit_step_error(
                            session_id, step, str(exc),
                            recommendation="Check input parameters and retry.",
                        )
                        return state
                    except StepHardFailure as exc:
                        state.pipeline_status = "error"
                        await self._emit_step_error(
                            session_id, step,
                            "; ".join(exc.validation_errors),
                            recommendation="Hard validation failure — cannot continue.",
                        )
                        return state
                    except Exception as exc:
                        logger.exception(
                            "Unexpected error in step %d", step.step_id
                        )
                        state.pipeline_status = "error"
                        await self._emit_step_error(
                            session_id, step, str(exc),
                            recommendation="An unexpected error occurred.",
                        )
                        return state

                    duration_ms = int((time.monotonic() - start_ms) * 1000)

                    # --- Layer 2: hard validation rules ---
                    vr = check_validation_rules(step.step_id, result)
                    result.validation_passed = vr.passed
                    result.validation_errors = vr.errors
                    if not vr.passed:
                        logger.error(
                            "[PIPELINE] Layer 2 validation failed for step %d: %s",
                            step.step_id, vr.errors,
                        )
                        state.pipeline_status = "error"
                        await self._emit_step_error(
                            session_id, step,
                            "; ".join(vr.errors),
                            recommendation="Hard validation failure — cannot continue.",
                        )
                        return state

                    # --- log step result ---
                    self._log_step_result(step, result, duration_ms)

                    # --- apply outputs to state ---
                    self._apply_outputs(state, result)
                    state.current_step = step.step_id
                    if step.step_id not in state.completed_steps:
                        state.completed_steps.append(step.step_id)

                    # --- emit decision-based event ---
                    await self._emit_decision_event(
                        session_id, step, result, duration_ms
                    )

                    # --- handle ESCALATE: pause, wait for user, then re-run ---
                    if (
                        result.ai_review
                        and result.ai_review.decision == AIDecisionEnum.ESCALATE
                        and escalation_count < max_escalations
                    ):
                        escalation_count += 1
                        state.waiting_for_user = True
                        await self.session_store.save(session_id, state)
                        updated_state, user_response_text = await self._wait_for_user(
                            session_id, state, step, result
                        )
                        if updated_state is None:
                            # Timeout — pipeline already emitted StepErrorEvent
                            state.pipeline_status = "error"
                            return state
                        state = updated_state
                        state.waiting_for_user = False

                        # Record this escalation attempt in history so the AI
                        # gets context on the next call and avoids repeating itself.
                        step_key = str(step.step_id)
                        if step_key not in state.escalation_history:
                            state.escalation_history[step_key] = []
                        state.escalation_history[step_key].append({
                            "attempt": escalation_count,
                            "options": result.ai_review.options,
                            "recommendation": result.ai_review.recommendation,
                            "user_chose": user_response_text or "(no text — accepted recommendation)",
                        })

                        # Refresh heartbeat — it may have expired while waiting
                        await self.session_store.heartbeat(session_id)

                        # Drop the step record from the escalated run so the
                        # re-run's record is the only one persisted for this step.
                        state.step_records = [
                            r for r in state.step_records
                            if r.step_id != step.step_id
                        ]
                        # Re-emit step_started so the frontend resets the card
                        await self.sse_manager.emit(
                            session_id,
                            StepStartedEvent(
                                session_id=session_id,
                                step_id=step.step_id,
                                step_name=step.step_name,
                            ).model_dump(),
                        )
                        logger.info(
                            "[ESCALATE] Re-running step %d (%s) after user response "
                            "(attempt %d/%d)",
                            step.step_id, step.step_name,
                            escalation_count, max_escalations,
                        )
                        continue  # Re-run the step with updated state

                    # --- handle actionable WARNING: pause, wait for user, then re-run ---
                    if (
                        result.ai_review
                        and result.ai_review.decision == AIDecisionEnum.WARN
                        and result.ai_review.options  # actionable (has choices)
                        and warning_pause_count < max_actionable_warnings
                    ):
                        warning_pause_count += 1
                        state.waiting_for_user = True
                        await self.session_store.save(session_id, state)
                        updated_state, _ = await self._wait_for_user(
                            session_id, state, step, result,
                            timeout=WARNING_PAUSE_TIMEOUT,
                            on_timeout="proceed",
                        )
                        state = updated_state
                        state.waiting_for_user = False

                        # Refresh heartbeat — it may have expired while waiting
                        await self.session_store.heartbeat(session_id)

                        # Drop the step record from the warning run so the
                        # re-run's record is the only one persisted for this step.
                        state.step_records = [
                            r for r in state.step_records
                            if r.step_id != step.step_id
                        ]
                        # Re-emit step_started so the frontend resets the card
                        await self.sse_manager.emit(
                            session_id,
                            StepStartedEvent(
                                session_id=session_id,
                                step_id=step.step_id,
                                step_name=step.step_name,
                            ).model_dump(),
                        )
                        logger.info(
                            "[WARNING-PAUSE] Re-running step %d (%s) after user response "
                            "(warning attempt %d/%d)",
                            step.step_id, step.step_name,
                            warning_pause_count, max_actionable_warnings,
                        )
                        continue  # Re-run the step with updated state

                    # Step completed (non-ESCALATE, or escalations exhausted).
                    # If escalations were exhausted (still ESCALATE here), the step
                    # has failed — halt the pipeline instead of silently continuing.
                    if (
                        result.ai_review
                        and result.ai_review.decision == AIDecisionEnum.ESCALATE
                    ):
                        state.pipeline_status = "error"
                        # Build a detailed observation from escalation history
                        step_key = str(step.step_id)
                        history = state.escalation_history.get(step_key, [])
                        history_lines = []
                        for entry in history:
                            user_chose = entry.get("user_chose", "")
                            history_lines.append(
                                f"Attempt {entry['attempt']}: user chose \"{user_chose}\""
                            )
                        history_summary = " | ".join(history_lines) if history_lines else "No user corrections were applied."

                        await self.sse_manager.emit(
                            session_id,
                            StepErrorEvent(
                                session_id=session_id,
                                step_id=step.step_id,
                                step_name=step.step_name,
                                message=(
                                    f"Step {step.step_id} ({step.step_name}) — "
                                    f"max escalation attempts ({max_escalations}) reached with unresolved conflict. "
                                    + (result.ai_review.reasoning or "Engineering decision could not be resolved.")[:200]
                                ),
                                observation=(
                                    result.ai_review.reasoning
                                    or "Engineering decision could not be resolved."
                                ),
                                recommendation=(
                                    f"Escalation history: {history_summary}. "
                                    f"The pipeline was halted because the conflict could not be resolved "
                                    f"after {max_escalations} attempts. Please review the input parameters "
                                    f"(fluid assignments, fluid properties, geometry) and re-run the design."
                                ),
                            ).model_dump(mode="json"),
                        )
                        await self.session_store.save(session_id, state)
                        return state
                    break

                logger.info(
                    "[PIPELINE] Step %d (%s) finished — continuing to next step",
                    step.step_id, step.step_name,
                )
                # --- persist state after each step ---
                await self.session_store.save(session_id, state)

            # --- Step 12: Convergence Loop ---
            if state.pipeline_status == "running":
                state = await self._run_convergence_loop(state, session_id)

            # --- Step 13: Vibration Check (post-convergence) ---
            if state.pipeline_status == "running":
                state = await self._run_post_convergence_step(
                    state, session_id, Step13VibrationCheck(),
                )

            # --- pipeline complete ---
            # Only mark complete if pipeline wasn't aborted by orphan/error
            if state.pipeline_status == "running":
                logger.info(
                    "[PIPELINE] All steps done — completed_steps=%s",
                    state.completed_steps,
                )
                state.pipeline_status = "completed"
                state.is_complete = True
                await self.session_store.save(session_id, state)
                await self.sse_manager.emit(
                    session_id,
                    DesignCompleteEvent(
                        session_id=session_id,
                        summary=self._build_summary(state),
                    ).model_dump(),
                )

        except asyncio.CancelledError:
            logger.info("Pipeline cancelled for session %s", session_id)
            state.pipeline_status = "cancelled"
        except Exception:
            logger.exception("Pipeline failed for session %s", session_id)
            state.pipeline_status = "error"
            await self.sse_manager.emit(
                session_id,
                StepErrorEvent(
                    session_id=session_id,
                    step_id=state.current_step,
                    step_name="pipeline",
                    message="Internal pipeline error",
                    recommendation="Please try again.",
                ).model_dump(),
            )
        finally:
            await self.session_store.save(session_id, state)

        return state

    # ------------------------------------------------------------------
    # Step 12 convergence loop
    # ------------------------------------------------------------------

    async def _run_convergence_loop(
        self,
        state: DesignState,
        session_id: str,
    ) -> DesignState:
        """Execute Step 12 convergence loop with restart handling."""
        max_restarts = 2

        while True:
            step12 = Step12Convergence()

            await self.sse_manager.emit(
                session_id,
                StepStartedEvent(
                    session_id=session_id,
                    step_id=12,
                    step_name="Convergence Loop",
                ).model_dump(),
            )

            try:
                result = await step12.run(
                    state, self.ai_engineer, self.sse_manager, session_id,
                )
            except Exception as exc:
                logger.exception("Step 12 convergence loop failed")
                state.pipeline_status = "error"
                await self._emit_step_error(
                    session_id, step12, str(exc),
                    recommendation="Convergence loop encountered an error.",
                )
                return state

            # Apply convergence outputs
            self._apply_outputs(state, result)
            state.current_step = 12
            if 12 not in state.completed_steps:
                state.completed_steps.append(12)

            # Check for restart request
            if result.outputs.get("convergence_action") == "restart":
                restart_from = result.outputs.get("restart_from_step")
                state.convergence_restart_count += 1

                if state.convergence_restart_count > max_restarts:
                    logger.warning(
                        "Max convergence restarts (%d) exceeded", max_restarts,
                    )
                    state.pipeline_status = "error"
                    await self._emit_step_error(
                        session_id, step12,
                        f"Max convergence restarts ({max_restarts}) exceeded. "
                        "Design cannot converge with current configuration.",
                        recommendation="Review thermal requirements and geometry constraints.",
                    )
                    return state

                # Handle ESCALATE — wait for user decision
                if (
                    result.ai_review
                    and result.ai_review.decision == AIDecisionEnum.ESCALATE
                ):
                    await self._emit_decision_event(session_id, step12, result, 0)
                    state.waiting_for_user = True
                    await self.session_store.save(session_id, state)
                    updated_state, user_response = await self._wait_for_user(
                        session_id, state, step12, result,
                    )
                    if updated_state is None:
                        state.pipeline_status = "error"
                        return state
                    state = updated_state
                    state.waiting_for_user = False

                    # If user chose "keep best result", don't restart
                    if user_response and "keep" in user_response.lower():
                        logger.info("User chose to keep best result — skipping restart")
                        state.warnings.append(
                            "Design not fully converged — user accepted best iteration."
                        )
                        break

                # Re-run from restart step
                logger.info(
                    "Convergence restart #%d from Step %d",
                    state.convergence_restart_count, restart_from,
                )
                restart_steps = [
                    s for s in PIPELINE_STEPS if s().step_id >= restart_from
                ]
                for step_cls in restart_steps:
                    step = step_cls()
                    await self.sse_manager.emit(
                        session_id,
                        StepStartedEvent(
                            session_id=session_id,
                            step_id=step.step_id,
                            step_name=step.step_name,
                        ).model_dump(),
                    )
                    try:
                        r = await step.run_with_review_loop(state, self.ai_engineer)
                    except (CalculationError, StepHardFailure) as exc:
                        state.pipeline_status = "error"
                        await self._emit_step_error(
                            session_id, step,
                            str(exc) if isinstance(exc, CalculationError)
                            else "; ".join(exc.validation_errors),
                        )
                        return state
                    self._apply_outputs(state, r)
                    state.current_step = step.step_id
                    await self.session_store.save(session_id, state)

                # Re-run convergence loop (continues the while loop)
                state.convergence_trajectory.clear()
                continue

            # Normal completion (converged or accept_best)
            await self._emit_decision_event(session_id, step12, result, 0)
            await self.session_store.save(session_id, state)
            break

        return state

    # ------------------------------------------------------------------
    # Post-convergence steps (Step 13+)
    # ------------------------------------------------------------------

    async def _run_post_convergence_step(
        self,
        state: DesignState,
        session_id: str,
        step: "BaseStep",
    ) -> DesignState:
        """Run a single post-convergence BaseStep (e.g. Step 13 Vibration)."""
        await self.sse_manager.emit(
            session_id,
            StepStartedEvent(
                session_id=session_id,
                step_id=step.step_id,
                step_name=step.step_name,
            ).model_dump(),
        )

        try:
            result = await step.run_with_review_loop(state, self.ai_engineer)
        except (CalculationError, StepHardFailure) as exc:
            state.pipeline_status = "error"
            await self._emit_step_error(
                session_id, step,
                str(exc) if isinstance(exc, CalculationError)
                else "; ".join(exc.validation_errors),
                recommendation=f"Step {step.step_id} ({step.step_name}) failed.",
            )
            return state
        except Exception as exc:
            logger.exception("Step %d (%s) failed", step.step_id, step.step_name)
            state.pipeline_status = "error"
            await self._emit_step_error(
                session_id, step, str(exc),
                recommendation="An unexpected error occurred.",
            )
            return state

        self._apply_outputs(state, result)
        state.current_step = step.step_id
        if step.step_id not in state.completed_steps:
            state.completed_steps.append(step.step_id)

        await self._emit_decision_event(session_id, step, result, 0)
        await self.session_store.save(session_id, state)

        return state

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _log_step_result(step: Any, result: StepResult, duration_ms: int) -> None:
        """Log a readable summary of each step's outputs and AI decision."""
        review = result.ai_review
        sep = "=" * 64

        lines = [
            sep,
            f"STEP {step.step_id} COMPLETE — {step.step_name}  ({duration_ms} ms)",
        ]

        # AI call indicator
        if review is None:
            lines.append("AI called    : NO  (threshold not met / convergence loop)")
        else:
            lines.append(f"AI called    : YES")
            lines.append(f"  decision   : {review.decision.value}")
            lines.append(f"  confidence : {review.confidence:.2f}")
            if review.reasoning:
                lines.append(f"  reasoning  : {review.reasoning[:160]}")

        # Outputs
        lines.append(f"Outputs ({len(result.outputs)}):")
        for key, val in result.outputs.items():
            display = repr(val)
            if len(display) > 80:
                display = display[:77] + "..."
            lines.append(f"  {key:<36} = {display}")

        # Validation errors (if any)
        if result.validation_errors:
            lines.append("Validation errors:")
            for err in result.validation_errors:
                lines.append(f"  ✗ {err}")

        lines.append(sep)
        logger.info("\n" + "\n".join(lines))

    def _apply_outputs(self, state: DesignState, result: StepResult) -> None:
        """Apply step outputs to DesignState fields.

        Delegates to the module-level ``apply_outputs`` in state_utils so
        that Step 12 (convergence loop) can reuse the same logic.
        """
        apply_outputs(state, result)

    async def _emit_decision_event(
        self,
        session_id: str,
        step: Any,
        result: StepResult,
        duration_ms: int,
    ) -> None:
        """Emit the right SSE event based on AI decision."""
        review = result.ai_review
        decision = review.decision if review else AIDecisionEnum.PROCEED
        safe_outputs = _serialize_outputs(result.outputs)

        if decision == AIDecisionEnum.PROCEED:
            # Only surface reasoning when AI was actually called with a real review.
            # An empty string causes the frontend <Reasoning> component to render
            # nothing, hiding the pointless "▸ view reasoning" toggle.
            _reasoning = ""
            if review and review.ai_called and review.reasoning:
                _reasoning = review.reasoning
            event = StepApprovedEvent(
                session_id=session_id,
                step_id=step.step_id,
                step_name=step.step_name,
                confidence=review.confidence if review else 1.0,
                reasoning=_reasoning,
                user_summary=f"Step {step.step_id} ({step.step_name}) completed.",
                duration_ms=duration_ms,
                outputs=safe_outputs,
            )

        elif decision == AIDecisionEnum.CORRECT:
            event = StepCorrectedEvent(
                session_id=session_id,
                step_id=step.step_id,
                step_name=step.step_name,
                confidence=review.confidence if review else 0.0,
                reasoning=review.reasoning if review else "",
                user_summary=f"Step {step.step_id} corrected by AI engineer.",
                correction={
                    c.field: {"old": c.old_value, "new": c.new_value}
                    for c in (review.corrections if review else [])
                },
                duration_ms=duration_ms,
                outputs=safe_outputs,
            )

        elif decision == AIDecisionEnum.WARN:
            # Mirror the routing rule in base.py: corrections present = real concern,
            # no corrections = informational observation only.
            severity = "warning" if (review and review.corrections) else "note"
            short_summary = (
                f"Step {step.step_id} approved with warning."
                if severity == "warning"
                else f"Step {step.step_id} — AI note."
            )
            # warning_message is a short one-liner shown above the KV table;
            # reasoning is the full AI review text shown in the collapsible
            # section.  Previously both were set to review.reasoning, which
            # caused the same long text to render twice on the frontend.
            warn_msg = (
                review.recommendation
                or review.observation
                or short_summary
            ) if review else ""
            event = StepWarningEvent(
                session_id=session_id,
                step_id=step.step_id,
                step_name=step.step_name,
                confidence=review.confidence if review else 0.0,
                reasoning=review.reasoning if review else "",
                user_summary=short_summary,
                warning_message=warn_msg,
                severity=severity,
                duration_ms=duration_ms,
                outputs=safe_outputs,
                options=review.options if review else [],
                option_ratings=review.option_ratings if review else [],
                recommendation=review.recommendation if review else None,
            )

        elif decision == AIDecisionEnum.ESCALATE:
            event = StepEscalatedEvent(
                session_id=session_id,
                step_id=step.step_id,
                step_name=step.step_name,
                message=review.reasoning if review else "AI requests user input.",
                options=review.options if review else [],
                option_ratings=review.option_ratings if review else [],
                recommendation=review.recommendation if review else None,
            )

        else:
            return

        await self.sse_manager.emit(session_id, event.model_dump(mode="json"))

    async def _emit_step_error(
        self,
        session_id: str,
        step: Any,
        message: str,
        *,
        recommendation: str = "",
    ) -> None:
        await self.sse_manager.emit(
            session_id,
            StepErrorEvent(
                session_id=session_id,
                step_id=step.step_id,
                step_name=step.step_name,
                message=message,
                recommendation=recommendation,
            ).model_dump(),
        )

    async def _wait_for_user(
        self,
        session_id: str,
        state: DesignState,
        step: Any,
        result: StepResult,
        *,
        timeout: int = USER_RESPONSE_TIMEOUT,
        on_timeout: str = "abort",
    ) -> tuple[Optional[DesignState], str]:
        """Block the pipeline until the user responds via POST /respond.

        Returns (updated_state, user_input_text).
        updated_state is None on timeout when on_timeout='abort' (caller must abort).
        When on_timeout='proceed', returns (current_state, "") on timeout.

        Response types:
          accept  — user accepts the AI's recommendation; apply suggested
                    corrections from result.ai_review.corrections to state.
          override — user provided free-text; parse values.user_input and
                     map recognised fields (e.g. tema_type) onto state.
          skip    — user wants to proceed with current outputs unchanged.
        """
        future = self.sse_manager.create_user_response_future(session_id)
        user_input = ""
        try:
            response = await asyncio.wait_for(
                future, timeout=timeout
            )
            if isinstance(response, dict):
                response_type = response.get("type", "accept")
                values = response.get("values") or {}
                user_input_raw = values.get("user_input", "").strip()
                user_input = user_input_raw.lower()
                option_index = int(values.get("option_index", -1))

                if response_type == "accept" or self._sounds_like_acceptance(user_input):
                    # Apply AI-recommended corrections so the re-run doesn't conflict
                    review = result.ai_review
                    if review and review.corrections:
                        for correction in review.corrections:
                            if hasattr(state, correction.field):
                                setattr(state, correction.field, correction.new_value)
                                logger.info(
                                    "User accepted AI suggestion: %s = %r",
                                    correction.field,
                                    correction.new_value,
                                )
                    # Apply recommendation hint only when corrections didn't
                    # already cover tema_preference to avoid overwriting the
                    # user's explicit choice with a hint from the AI's text.
                    if review and review.recommendation:
                        correction_fields = {c.field for c in (review.corrections or [])}
                        if "tema_preference" not in correction_fields:
                            self._apply_recommendation_hint(state, review.recommendation)

                elif response_type == "override":
                    # User typed a specific value or clicked an option button.
                    # Check for multi-shell keywords in the full response text
                    # (covers both option-click text and typed free text).
                    self._apply_user_text_override(
                        state, user_input,
                        step_id=step.step_id,
                        option_index=option_index,
                    )

                # "skip" — don't touch state; re-run will see unchanged inputs

        except asyncio.TimeoutError:
            logger.warning(
                "User response timeout for session %s step %d (on_timeout=%s)",
                session_id,
                step.step_id,
                on_timeout,
            )
            if on_timeout == "proceed":
                # Actionable WARNING timeout — proceed with current values
                logger.info(
                    "[WARNING-TIMEOUT] Proceeding with current values for step %d",
                    step.step_id,
                )
                return state, ""
            # Default: abort pipeline (ESCALATE behavior)
            await self.sse_manager.emit(
                session_id,
                StepErrorEvent(
                    session_id=session_id,
                    step_id=step.step_id,
                    step_name=step.step_name,
                    message="User response timeout — aborting pipeline.",
                ).model_dump(),
            )
            return None, ""  # Signal caller to abort
        return state, user_input_raw

    # ------------------------------------------------------------------
    # User response interpretation helpers
    # ------------------------------------------------------------------

    _NEGATION_WORDS = frozenset(
        ("no", "not", "don't", "dont", "do not", "never", "disagree", "reject",
         "keep", "stay", "remain", "cancel", "abort", "stop")
    )

    @classmethod
    def _sounds_like_acceptance(cls, text: str) -> bool:
        """Return True if free-text input signals acceptance of the AI suggestion.

        Checks for explicit negation first so phrases like "don't proceed"
        or "I don't agree" are correctly treated as rejections.
        """
        # Explicit negation takes priority
        if any(word in text for word in cls._NEGATION_WORDS):
            return False
        accept_phrases = (
            "as per suggestion", "use suggestion", "use your suggestion",
            "yes", "ok", "okay", "accept", "agree", "go ahead",
            "use that", "sounds good", "looks good",
        )
        return any(phrase in text for phrase in accept_phrases)

    @staticmethod
    def _apply_recommendation_hint(state: DesignState, recommendation: str) -> None:
        """Extract TEMA type hints from the AI's recommendation text."""
        # Match patterns like "Use AES" / "recommend AEP" / "switch to AEU"
        match = re.search(
            r"\b(AES|AEP|AEU|AEL|AEW|BEM|NEN|BEU)\b",
            recommendation,
            re.IGNORECASE,
        )
        if match:
            suggested = match.group(1).upper()
            logger.info(
                "Applying recommendation hint: tema_preference = %r", suggested
            )
            state.tema_preference = suggested

    @staticmethod
    def _apply_user_text_override(
        state: DesignState,
        text: str,
        *,
        step_id: int = 0,
        option_index: int = -1,
    ) -> None:
        """Parse free-text override for known field names.

        option_index is the 0-based index of the button the user clicked (-1 = typed free text).
        When option_index >= 0 and step_id matches, use deterministic index dispatch instead of
        regex so the action is reliable regardless of how the AI phrases the option.
        """
        # --- Step 8: index-based dispatch (deterministic, regex-independent) ---
        if step_id == 8 and option_index >= 0:
            if option_index == 0:
                # Option A: verify/re-fetch viscosity for the current shell-side fluid
                logger.info("[Step8-OptionA] Refreshing shell-side fluid properties")
                _refresh_fluid_props_for_shell_side(state)
                return
            if option_index == 1:
                # Option B: swap fluid-side assignments (oil→tube, water→shell)
                old_val = state.shell_side_fluid
                state.shell_side_fluid = "cold" if old_val == "hot" else "hot"
                logger.info(
                    "[Step8-OptionB] shell_side_fluid swapped %r → %r",
                    old_val, state.shell_side_fluid,
                )
                _refresh_fluid_props_for_shell_side(state)
                return

        # --- Regex fallback for typed free text and non-indexed steps ---

        # --- Fluid-side swap (Step 8 escalation: swap shell/tube assignment) ---
        if re.search(r"swap.*fluid|fluid.*swap|oil.*tube.*side|water.*shell.*side", text, re.IGNORECASE):
            old_val = state.shell_side_fluid
            state.shell_side_fluid = "cold" if old_val == "hot" else "hot"
            logger.info(
                "User override: shell_side_fluid swapped from %r to %r",
                old_val, state.shell_side_fluid,
            )
            # After swapping, re-fetch fluid properties at shell-side mean temp
            # so Step 8 re-run uses the correct fluid's viscosity.
            _refresh_fluid_props_for_shell_side(state)
            return

        # --- Viscosity verification (Step 8 escalation: re-fetch fluid props) ---
        if re.search(r"verif.*viscosity|viscosity.*verif|re-?run.*step\s*8.*viscosity|force.*mu", text, re.IGNORECASE):
            logger.info("User override: refreshing shell-side fluid properties")
            _refresh_fluid_props_for_shell_side(state)
            return

        # Multi-shell arrangement — check this first so "series"/"parallel"
        # in the text is acted on before looking for TEMA type codes.
        if re.search(r"\bseries\b", text, re.IGNORECASE):
            state.multi_shell_arrangement = "series"
            logger.info("User override: multi_shell_arrangement = 'series'")
            return
        if re.search(r"\bparallel\b", text, re.IGNORECASE):
            state.multi_shell_arrangement = "parallel"
            logger.info("User override: multi_shell_arrangement = 'parallel'")
            return

        # TEMA type mentioned explicitly
        match = re.search(
            r"\b(AES|AEP|AEU|AEL|AEW|BEM|NEN|BEU)\b", text, re.IGNORECASE
        )
        if match:
            state.tema_preference = match.group(1).upper()
            logger.info(
                "User override: tema_preference = %r", state.tema_preference
            )

    @staticmethod
    def _build_summary(state: DesignState) -> dict[str, Any]:
        """Build a compact design summary from final state."""
        return {
            "session_id": state.session_id,
            "pipeline_status": state.pipeline_status,
            "completed_steps": state.completed_steps,
            "Q_W": state.Q_W,
            "LMTD_K": state.LMTD_K,
            "F_factor": state.F_factor,
            "U_W_m2K": state.U_W_m2K,
            "A_m2": state.A_m2,
            "tema_type": state.tema_type,
            "tema_class": state.tema_class,
            "multi_shell_arrangement": state.multi_shell_arrangement,
            "n_shells": state.geometry.n_shells if state.geometry else None,
            "warnings": state.warnings,
            "notes": state.notes,
            "geometry": state.geometry.model_dump() if state.geometry else None,
        }
