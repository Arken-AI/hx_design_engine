"""SSE streaming endpoint for real-time design progress."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request
from sse_starlette.sse import EventSourceResponse

from hx_engine.app.core.sse_manager import SSEManager
from hx_engine.app.dependencies import get_sse_manager

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stream"])


@router.get("/design/{session_id}/stream")
async def design_stream(
    session_id: str,
    request: Request,
    sse_manager: SSEManager = Depends(get_sse_manager),
) -> EventSourceResponse:
    """Server-Sent Events stream for a design session.

    Events follow the schema defined in ``hx_engine.app.models.sse_events``.
    The stream ends when a ``design_complete`` or ``stream_end`` event is emitted.
    """

    async def event_generator():
        async for event in sse_manager.stream_events(session_id):
            # Check if client disconnected
            if await request.is_disconnected():
                logger.info(
                    "Client disconnected from SSE stream: %s", session_id
                )
                break

            event_type = event.get("event_type", "message")
            yield {
                "event": event_type,
                "data": json.dumps(event, default=str),
            }

    return EventSourceResponse(
        event_generator(),
        media_type="text/event-stream",
    )
