"""Design router — start a design, check status, respond to escalations."""

from __future__ import annotations

import asyncio
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
router = APIRouter(prefix="/design", tags=["design"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class DesignRequest(BaseModel):
    """Payload for POST /design — kick off a new design session."""

    raw_request: str = Field(
        ...,
        description="Natural-language design request from the user / LLM",
        min_length=1,
    )
    user_id: str | None = None

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


class DesignStartResponse(BaseModel):
    session_id: str
    status: str = "started"
    stream_url: str


class DesignStatusResponse(BaseModel):
    session_id: str
    current_step: int
    completed_steps: list[int]
    warnings: list[str]
    Q_W: float | None = None
    LMTD_K: float | None = None
    A_m2: float | None = None
    tema_type: str | None = None


class UserResponse(BaseModel):
    """Payload for POST /design/{session_id}/respond — user answers an ESCALATE."""

    response: dict[str, Any] = Field(
        default_factory=dict,
        description="Key-value overrides to apply to DesignState",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=DesignStartResponse, status_code=201)
async def start_design(
    body: DesignRequest,
    background_tasks: BackgroundTasks,
    session_store: SessionStore = Depends(get_session_store),
    sse_manager: SSEManager = Depends(get_sse_manager),
    pipeline_runner: PipelineRunner = Depends(get_pipeline_runner),
) -> DesignStartResponse:
    """Create a new HX design session and start the pipeline in the background."""
    # Build initial state from request
    state = DesignState(
        raw_request=body.raw_request,
        user_id=body.user_id,
        T_hot_in_C=body.T_hot_in_C,
        T_hot_out_C=body.T_hot_out_C,
        T_cold_in_C=body.T_cold_in_C,
        T_cold_out_C=body.T_cold_out_C,
        m_dot_hot_kg_s=body.m_dot_hot_kg_s,
        m_dot_cold_kg_s=body.m_dot_cold_kg_s,
        hot_fluid_name=body.hot_fluid_name,
        cold_fluid_name=body.cold_fluid_name,
        P_hot_Pa=body.P_hot_Pa,
        P_cold_Pa=body.P_cold_Pa,
        tema_preference=body.tema_preference,
    )
    session_id = state.session_id

    # Pre-create SSE queue so the client can connect before the first event
    sse_manager.get_queue(session_id)

    # Persist initial state
    await session_store.save(session_id, state)
    await session_store.heartbeat(session_id)

    # Launch pipeline in background
    background_tasks.add_task(pipeline_runner.run, state)

    return DesignStartResponse(
        session_id=session_id,
        status="started",
        stream_url=f"/design/{session_id}/stream",
    )


@router.get("/{session_id}/status", response_model=DesignStatusResponse)
async def get_design_status(
    session_id: str,
    session_store: SessionStore = Depends(get_session_store),
) -> DesignStatusResponse:
    """Return the current progress of a design session."""
    state = await session_store.load(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return DesignStatusResponse(
        session_id=state.session_id,
        current_step=state.current_step,
        completed_steps=state.completed_steps,
        warnings=state.warnings,
        Q_W=state.Q_W,
        LMTD_K=state.LMTD_K,
        A_m2=state.A_m2,
        tema_type=state.tema_type,
    )


@router.post("/{session_id}/respond", status_code=200)
async def respond_to_escalation(
    session_id: str,
    body: UserResponse,
    session_store: SessionStore = Depends(get_session_store),
    sse_manager: SSEManager = Depends(get_sse_manager),
) -> dict[str, str]:
    """Provide user input for an ESCALATED step, resuming the pipeline."""
    state = await session_store.load(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")

    sse_manager.resolve_user_response(session_id, body.response)
    return {"status": "accepted", "session_id": session_id}
