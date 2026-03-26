"""Design router — start a design, check status, respond to escalations.

POST /api/v1/hx/design              → trigger design, return {session_id, stream_url, token}
GET  /api/v1/hx/design/{id}/status   → poll fallback
POST /api/v1/hx/design/{id}/respond  → user response to ESCALATED step
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from hx_engine.app.core.pipeline_runner import PipelineRunner
from hx_engine.app.core.session_store import SessionStore
from hx_engine.app.core.sse_manager import SSEManager
from hx_engine.app.dependencies import (
    get_pipeline_runner,
    get_session_store,
    get_sse_manager,
)
from hx_engine.app.models.design_state import DesignState

logger = logging.getLogger(__name__)
router = APIRouter(tags=["design"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class DesignRequest(BaseModel):
    """Payload for POST /api/v1/hx/design — kick off a new design session."""

    raw_request: str = Field(
        ...,
        description="Natural-language design request from the user / LLM",
        min_length=1,
    )
    user_id: str
    org_id: str | None = None
    mode: str = "design"  # "design" | "rating"

    # Optional explicit overrides (usually parsed by Step 01)
    T_hot_in_C: float | None = None
    T_hot_out_C: float | None = None
    T_cold_in_C: float | None = None
    T_cold_out_C: float | None = None
    m_dot_hot_kg_s: float | None = None
    m_dot_cold_kg_s: float | None = None
    hot_fluid_name: str | None = None
    cold_fluid_name: str | None = None
    P_hot_Pa: float | None = None
    P_cold_Pa: float | None = None
    tema_preference: str | None = None


class DesignResponse(BaseModel):
    """Response from POST /api/v1/hx/design."""

    session_id: str
    stream_url: str   # relative path: /api/v1/hx/design/{id}/stream
    token: str        # JWT for stream auth (stub for now)


class DesignStatusResponse(BaseModel):
    session_id: str
    current_step: int
    waiting_for_user: bool
    step_records: list[dict[str, Any]]
    warnings: list[str]


class UserResponse(BaseModel):
    """Payload for POST /design/{session_id}/respond — user answers an ESCALATE."""

    type: str  # "accept" | "override" | "skip"
    values: dict | None = None


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
    """Create a new HX design session and start the pipeline in the background."""
    # Build initial state from request
    state = DesignState(
        raw_request=req.raw_request,
        user_id=req.user_id,
        org_id=req.org_id,
        mode=req.mode,
        T_hot_in_C=req.T_hot_in_C,
        T_hot_out_C=req.T_hot_out_C,
        T_cold_in_C=req.T_cold_in_C,
        T_cold_out_C=req.T_cold_out_C,
        m_dot_hot_kg_s=req.m_dot_hot_kg_s,
        m_dot_cold_kg_s=req.m_dot_cold_kg_s,
        hot_fluid_name=req.hot_fluid_name,
        cold_fluid_name=req.cold_fluid_name,
        P_hot_Pa=req.P_hot_Pa,
        P_cold_Pa=req.P_cold_Pa,
        tema_preference=req.tema_preference,
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
        waiting_for_user=state.waiting_for_user,
        step_records=state.step_records,
        warnings=state.warnings,
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

    sse_manager.resolve_user_response(session_id, response.model_dump())
    return {"status": "received"}
