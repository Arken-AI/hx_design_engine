"""Shared fixtures and helpers for the Step 12 unit tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel


def make_collector() -> tuple[list[BaseModel], Callable[[BaseModel], Awaitable[None]]]:
    """Return (collected_events_list, async_callback).

    Use in tests that call ``step12.run(..., emit_event=emit)`` instead of
    passing an SSEManager.  Collected events are the original Pydantic model
    instances, so you can use ``isinstance`` checks in assertions.
    """
    collected: list[BaseModel] = []

    async def _emit(event: BaseModel) -> None:
        collected.append(event)

    return collected, _emit
