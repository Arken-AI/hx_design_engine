"""PipelineRunner — orchestrates Steps 1-5 with SSE emission.

Creates a DesignState from the user request, runs each step in sequence
through run_with_review_loop(), emits SSE events, and handles
ESCALATED pauses (awaiting user response via SSEManager future).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from hx_engine.app.core.ai_engineer import AIEngineer
from hx_engine.app.core.exceptions import CalculationError, StepHardFailure
from hx_engine.app.core.session_store import SessionStore
from hx_engine.app.core.sse_manager import SSEManager
from hx_engine.app.models.design_state import DesignState
from hx_engine.app.models.sse_events import (
    DesignCompleteEvent,
    StepApprovedEvent,
    StepCorrectedEvent,
    StepErrorEvent,
    StepEscalatedEvent,
    StepStartedEvent,
    StepWarningEvent,
)
from hx_engine.app.models.step_result import AIDecisionEnum, StepResult
from hx_engine.app.steps.step_01_requirements import Step01Requirements
from hx_engine.app.steps.step_02_heat_duty import Step02HeatDuty
from hx_engine.app.steps.step_03_fluid_props import Step03FluidProperties
from hx_engine.app.steps.step_04_tema_geometry import Step04TEMAGeometry
from hx_engine.app.steps.step_05_lmtd import Step05LMTD

logger = logging.getLogger(__name__)

# Ordered pipeline — steps run sequentially
PIPELINE_STEPS = [
    Step01Requirements,
    Step02HeatDuty,
    Step03FluidProperties,
    Step04TEMAGeometry,
    Step05LMTD,
]

# How long (seconds) to wait for user response on ESCALATE
USER_RESPONSE_TIMEOUT = 300


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

        try:
            for step_cls in PIPELINE_STEPS:
                step = step_cls()

                # --- orphan check ---
                if await self.session_store.is_orphaned(session_id):
                    logger.warning("Session %s orphaned, aborting", session_id)
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

                # --- execute step with AI review loop ---
                start_ms = time.monotonic()
                try:
                    result: StepResult = await step.run_with_review_loop(
                        state, self.ai_engineer
                    )
                except CalculationError as exc:
                    await self._emit_step_error(
                        session_id, step, str(exc),
                        recommendation="Check input parameters and retry.",
                    )
                    return state
                except StepHardFailure as exc:
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
                    await self._emit_step_error(
                        session_id, step, str(exc),
                        recommendation="An unexpected error occurred.",
                    )
                    return state

                duration_ms = int((time.monotonic() - start_ms) * 1000)

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

                # --- handle ESCALATE: pause and wait for user ---
                if (
                    result.ai_review
                    and result.ai_review.decision == AIDecisionEnum.ESCALATE
                ):
                    state.waiting_for_user = True
                    await self.session_store.save(session_id, state)
                    state = await self._wait_for_user(session_id, state, step)
                    state.waiting_for_user = False

                # --- persist state after each step ---
                await self.session_store.save(session_id, state)

            # --- pipeline complete ---
            await self.sse_manager.emit(
                session_id,
                DesignCompleteEvent(
                    session_id=session_id,
                    summary=self._build_summary(state),
                ).model_dump(),
            )

        except asyncio.CancelledError:
            logger.info("Pipeline cancelled for session %s", session_id)
        except Exception:
            logger.exception("Pipeline failed for session %s", session_id)
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
        """Apply step outputs to DesignState fields."""
        mapping: dict[str, str] = {
            "Q_W": "Q_W",
            "LMTD_K": "LMTD_K",
            "F_factor": "F_factor",
            "U_W_m2K": "U_W_m2K",
            "A_m2": "A_m2",
            "T_hot_in_C": "T_hot_in_C",
            "T_hot_out_C": "T_hot_out_C",
            "T_cold_in_C": "T_cold_in_C",
            "T_cold_out_C": "T_cold_out_C",
            "m_dot_hot_kg_s": "m_dot_hot_kg_s",
            "m_dot_cold_kg_s": "m_dot_cold_kg_s",
            "hot_fluid_name": "hot_fluid_name",
            "cold_fluid_name": "cold_fluid_name",
            "P_hot_Pa": "P_hot_Pa",
            "P_cold_Pa": "P_cold_Pa",
            "tema_type": "tema_type",
            "tema_preference": "tema_preference",
            "shell_side_fluid": "shell_side_fluid",
            "R_f_hot_m2KW": "R_f_hot_m2KW",
            "R_f_cold_m2KW": "R_f_cold_m2KW",
        }
        for out_key, state_field in mapping.items():
            if out_key in result.outputs:
                setattr(state, state_field, result.outputs[out_key])

        # FluidProperties (nested)
        if "hot_fluid_props" in result.outputs:
            from hx_engine.app.models.design_state import FluidProperties
            val = result.outputs["hot_fluid_props"]
            if isinstance(val, dict):
                state.hot_fluid_props = FluidProperties(**val)
            elif isinstance(val, FluidProperties):
                state.hot_fluid_props = val

        if "cold_fluid_props" in result.outputs:
            from hx_engine.app.models.design_state import FluidProperties
            val = result.outputs["cold_fluid_props"]
            if isinstance(val, dict):
                state.cold_fluid_props = FluidProperties(**val)
            elif isinstance(val, FluidProperties):
                state.cold_fluid_props = val

        # Geometry (nested)
        if "geometry" in result.outputs:
            from hx_engine.app.models.design_state import GeometrySpec
            val = result.outputs["geometry"]
            if isinstance(val, dict):
                state.geometry = GeometrySpec(**val)
            elif isinstance(val, GeometrySpec):
                state.geometry = val

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

        if decision == AIDecisionEnum.PROCEED:
            event = StepApprovedEvent(
                session_id=session_id,
                step_id=step.step_id,
                step_name=step.step_name,
                confidence=review.confidence if review else 0.85,
                reasoning=review.reasoning if review else "",
                user_summary=f"Step {step.step_id} ({step.step_name}) completed.",
                duration_ms=duration_ms,
                outputs=result.outputs,
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
                outputs=result.outputs,
            )

        elif decision == AIDecisionEnum.WARN:
            event = StepWarningEvent(
                session_id=session_id,
                step_id=step.step_id,
                step_name=step.step_name,
                confidence=review.confidence if review else 0.0,
                reasoning=review.reasoning if review else "",
                user_summary=f"Step {step.step_id} approved with warning.",
                warning_message=review.reasoning if review else "",
                duration_ms=duration_ms,
                outputs=result.outputs,
            )

        elif decision == AIDecisionEnum.ESCALATE:
            event = StepEscalatedEvent(
                session_id=session_id,
                step_id=step.step_id,
                step_name=step.step_name,
                message=review.reasoning if review else "AI requests user input.",
            )

        else:
            return

        await self.sse_manager.emit(session_id, event.model_dump())

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
    ) -> DesignState:
        """Block the pipeline until the user responds via POST /respond."""
        future = self.sse_manager.create_user_response_future(session_id)
        try:
            response = await asyncio.wait_for(
                future, timeout=USER_RESPONSE_TIMEOUT
            )
            # Apply any user-provided overrides
            if isinstance(response, dict):
                for key, val in response.items():
                    if hasattr(state, key):
                        setattr(state, key, val)
        except asyncio.TimeoutError:
            logger.warning(
                "User response timeout for session %s step %d",
                session_id,
                step.step_id,
            )
            await self.sse_manager.emit(
                session_id,
                StepErrorEvent(
                    session_id=session_id,
                    step_id=step.step_id,
                    step_name=step.step_name,
                    message="User response timeout — aborting pipeline.",
                ).model_dump(),
            )
        return state

    @staticmethod
    def _build_summary(state: DesignState) -> dict[str, Any]:
        """Build a compact design summary from final state."""
        return {
            "session_id": state.session_id,
            "completed_steps": state.completed_steps,
            "Q_W": state.Q_W,
            "LMTD_K": state.LMTD_K,
            "F_factor": state.F_factor,
            "U_W_m2K": state.U_W_m2K,
            "A_m2": state.A_m2,
            "tema_type": state.tema_type,
            "warnings": state.warnings,
            "geometry": state.geometry.model_dump() if state.geometry else None,
        }
