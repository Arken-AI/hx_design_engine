"""Design router — start a design, check status, respond to escalations.

POST /api/v1/hx/design              → trigger design, return {session_id, stream_url, token}
GET  /api/v1/hx/design/{id}/status   → poll fallback
POST /api/v1/hx/design/{id}/respond  → user response to ESCALATED step
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from hx_engine.app.core.exceptions import CalculationError
from hx_engine.app.core.pipeline_runner import PipelineRunner
from hx_engine.app.core.requirements_validator import validate_requirements, verify_token
from hx_engine.app.core.session_store import SessionStore
from hx_engine.app.core.sse_manager import SSEManager
from hx_engine.app.core.volumetric_flow import (
    FlowResolution,
    apply_flow_inputs,
)
from hx_engine.app.dependencies import (
    get_pipeline_runner,
    get_session_store,
    get_sse_manager,
)
from hx_engine.app.models.design_state import DesignState
from hx_engine.app.models.requirements import DesignRequest
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(tags=["design"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class DesignResponse(BaseModel):
    """Response from POST /api/v1/hx/design."""

    session_id: str
    stream_url: str   # relative path: /api/v1/hx/design/{id}/stream
    token: str        # JWT for stream auth (stub for now)


class DesignStatusResponse(BaseModel):
    session_id: str
    current_step: int
    pipeline_status: str
    waiting_for_user: bool
    is_complete: bool
    step_records: list[dict[str, Any]]
    warnings: list[str]
    notes: list[str]
    escalation_history: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class UserResponse(BaseModel):
    """Payload for POST /design/{session_id}/respond — user answers an ESCALATE."""

    type: Literal["accept", "override", "skip"]
    values: dict[str, Any] | None = None


def _flow_audit(res: FlowResolution | None) -> dict | None:
    """Serialise a :class:`FlowResolution` for the DesignState audit field."""
    if res is None:
        return None
    return {
        "value": res.input_value,
        "unit": res.input_unit,
        "basis": res.basis,
        "m_dot_kg_s": res.m_dot_kg_s,
        "density_kg_m3": res.density_kg_m3,
        "density_source": res.density_source,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/design", response_model=DesignResponse)
async def start_design(
    req: DesignRequest,
    background_tasks: BackgroundTasks,
    session_store: SessionStore = Depends(get_session_store),
    sse_manager: SSEManager = Depends(get_sse_manager),
    pipeline_runner: PipelineRunner = Depends(get_pipeline_runner),
) -> DesignResponse:
    """Create a new HX design session and start the pipeline in the background.

    Defense in depth:
    - If a token is provided (from POST /requirements), verify it.
    - If no token (direct API call, tests), run inline validation.
    In both cases invalid inputs are rejected before a session is created.
    """
    validation_dict = req.to_validation_dict()

    # Resolve volumetric flow inputs to kg/s before token verification /
    # inline validation (P2-20). The same deterministic resolution runs in
    # /requirements, so the canonical (post-resolution) dict matches the
    # signed payload.
    try:
        validation_dict, hot_res, cold_res = await apply_flow_inputs(
            validation_dict,
            hot_flow=validation_dict.get("hot_flow"),
            cold_flow=validation_dict.get("cold_flow"),
            hot_fluid_name=req.hot_fluid_name,
            cold_fluid_name=req.cold_fluid_name,
        )
    except CalculationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "valid": False,
                "errors": [{
                    "field": "flow_input",
                    "message": exc.message,
                    "suggestion": "Provide m_dot_*_kg_s directly or fix the flow object.",
                    "valid_range": "",
                }],
            },
        )

    if req.token:
        if not verify_token(req.token, validation_dict):
            raise HTTPException(
                status_code=400,
                detail="Invalid requirements token — call POST /requirements first or re-run it",
            )
    else:
        # No token — run inline validation (direct API callers, tests, backend)
        result = validate_requirements(validation_dict)
        if not result.valid:
            raise HTTPException(
                status_code=422,
                detail={
                    "valid": False,
                    "errors": [
                        {
                            "field": e.field,
                            "message": e.message,
                            "suggestion": e.suggestion,
                            "valid_range": e.valid_range,
                        }
                        for e in result.errors
                    ],
                },
            )

    # Build initial state from request
    state = DesignState(
        raw_request=req.raw_request or "",
        user_id=req.user_id,
        org_id=req.org_id,
        mode=req.mode,
        T_hot_in_C=req.T_hot_in_C,
        T_hot_out_C=req.T_hot_out_C,
        T_cold_in_C=req.T_cold_in_C,
        T_cold_out_C=req.T_cold_out_C,
        m_dot_hot_kg_s=validation_dict.get("m_dot_hot_kg_s"),
        m_dot_cold_kg_s=validation_dict.get("m_dot_cold_kg_s"),
        hot_fluid_name=req.hot_fluid_name,
        cold_fluid_name=req.cold_fluid_name,
        P_hot_Pa=req.P_hot_Pa,
        P_cold_Pa=req.P_cold_Pa,
        tema_preference=req.tema_preference,
        hot_flow_input=_flow_audit(hot_res),
        cold_flow_input=_flow_audit(cold_res),
    )
    session_id = state.session_id

    # Pre-create SSE queue so the client can connect before the first event
    sse_manager.get_queue(session_id)

    # Persist initial state
    await session_store.save(session_id, state)
    await session_store.heartbeat(session_id)

    # Launch pipeline in background
    background_tasks.add_task(pipeline_runner.run, state)

    return DesignResponse(
        session_id=session_id,
        stream_url=f"/api/v1/hx/design/{session_id}/stream",
        token="stub-token",  # Real JWT in Week 6
    )


@router.get("/design/{session_id}/status", response_model=DesignStatusResponse)
async def get_design_status(
    session_id: str,
    session_store: SessionStore = Depends(get_session_store),
) -> DesignStatusResponse:
    """Poll fallback — return the current progress of a design session."""
    state = await session_store.load(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return DesignStatusResponse(
        session_id=state.session_id,
        current_step=state.current_step,
        pipeline_status=state.pipeline_status,
        waiting_for_user=state.waiting_for_user,
        is_complete=state.is_complete,
        step_records=[r.model_dump() for r in state.step_records],
        warnings=state.warnings,
        notes=state.notes,
        escalation_history=state.escalation_history,
    )


@router.post("/design/{session_id}/respond")
async def respond_to_escalation(
    session_id: str,
    response: UserResponse,
    session_store: SessionStore = Depends(get_session_store),
    sse_manager: SSEManager = Depends(get_sse_manager),
) -> dict[str, str]:
    """Provide user input for an ESCALATED step, resuming the pipeline."""
    state = await session_store.load(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not state.waiting_for_user:
        # Pipeline is not waiting — the timeout already fired or the step completed.
        raise HTTPException(
            status_code=410,
            detail="Response window has expired. The pipeline already timed out or completed.",
        )

    sse_manager.resolve_user_response(session_id, response.model_dump())
    return {"status": "received"}
