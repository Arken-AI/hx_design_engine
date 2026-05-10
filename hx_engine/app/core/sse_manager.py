"""SSE event manager — one async queue per design session.

Provides:
    emit()          — push an event dict to a session's queue
    stream_events() — async generator that yields events until design_complete
    create_user_response_future() / resolve_user_response() — for ESCALATED steps
    cleanup()       — remove queues when a session ends
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)


class SSEManager:
    """Manages per-session SSE event queues and ESCALATED response futures."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}
        self._futures: dict[str, asyncio.Future[dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    def get_queue(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()
        return self._queues[session_id]

    async def emit(self, session_id: str, event: dict[str, Any]) -> None:
        """Push an event to the session's queue."""
        queue = self.get_queue(session_id)
        await queue.put(event)

    async def stream_events(
        self, session_id: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield events until ``design_complete`` or ``stream_end``."""
        queue = self.get_queue(session_id)
        while True:
            event = await queue.get()
            event_type = event.get("event_type", "")
            if event_type == "design_complete":
                yield event
                break
            if event_type == "stream_end":
                break
            yield event

    # ------------------------------------------------------------------
    # ESCALATED user response handling
    # ------------------------------------------------------------------

    def create_user_response_future(
        self, session_id: str
    ) -> asyncio.Future[dict[str, Any]]:
        """Create a future the pipeline awaits when a step is ESCALATED."""
        loop = asyncio.get_event_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._futures[session_id] = future
        return future

    def resolve_user_response(
        self, session_id: str, response: dict[str, Any]
    ) -> None:
        """Resolve the pending future so the pipeline resumes."""
        future = self._futures.pop(session_id, None)
        if future and not future.done():
            future.set_result(response)

    def has_pending_user_response_future(self, session_id: str) -> bool:
        """Return True iff a user-response future exists and is unresolved.

        This is the authoritative in-process signal that the pipeline is
        currently awaiting user input.  ``DesignState.waiting_for_user`` is a
        persisted mirror of the same fact but can briefly lag the future
        (the future is created inside ``_wait_for_user`` *after* the
        ``state.waiting_for_user = True`` save returns, and is consumed
        *before* the subsequent ``state.waiting_for_user = False`` save).
        Callers that need to know whether ``/respond`` is currently
        meaningful should consult this method as well as the persisted
        flag — see the 410-on-click regression in
        ``test_respond_accepts_when_future_pending_even_if_state_flag_false``.
        """
        future = self._futures.get(session_id)
        return future is not None and not future.done()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self, session_id: str) -> None:
        """Remove queues and futures for a completed/abandoned session."""
        self._queues.pop(session_id, None)
        future = self._futures.pop(session_id, None)
        if future and not future.done():
            future.cancel()
