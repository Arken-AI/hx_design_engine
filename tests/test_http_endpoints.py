"""HTTP-level integration tests for HX Design Engine API endpoints.

Tests the actual FastAPI routes via TestClient (httpx), covering:
  - POST /api/v1/hx/design (start design)
  - GET  /api/v1/hx/design/{session_id}/status
  - POST /api/v1/hx/design/{session_id}/respond
  - GET  /health
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from hx_engine.app.core.session_store import SessionStore
from hx_engine.app.core.sse_manager import SSEManager
from hx_engine.app.main import app
from hx_engine.app import dependencies


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
async def _setup_deps():
    """Wire in-memory session store (no Redis needed) for tests."""
    store = SessionStore(redis_client=None)
    sse = SSEManager()

    dependencies._session_store = store
    dependencies._sse_manager = sse
    dependencies._ai_engineer = dependencies.AIEngineer(stub_mode=True)
    yield
    dependencies._session_store = None
    dependencies._ai_engineer = None


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "hx-engine"
        assert "version" in body


# ---------------------------------------------------------------------------
# POST /api/v1/hx/design
# ---------------------------------------------------------------------------

class TestStartDesign:
    @pytest.mark.asyncio
    async def test_start_design_minimal_payload(self, client: AsyncClient):
        """Minimal valid payload returns session_id and stream_url."""
        resp = await client.post(
            "/api/v1/hx/design",
            json={
                "raw_request": "Design HX for water-to-water 80C to 40C",
                "user_id": "test-user",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "session_id" in body
        assert body["stream_url"].startswith("/api/v1/hx/design/")
        assert body["stream_url"].endswith("/stream")
        assert "token" in body

    @pytest.mark.asyncio
    async def test_start_design_full_payload(self, client: AsyncClient):
        """Full payload with explicit overrides."""
        resp = await client.post(
            "/api/v1/hx/design",
            json={
                "raw_request": "Design crude oil cooler",
                "user_id": "test-user",
                "mode": "design",
                "hot_fluid_name": "crude oil",
                "cold_fluid_name": "water",
                "T_hot_in_C": 120.0,
                "T_hot_out_C": 60.0,
                "T_cold_in_C": 25.0,
                "T_cold_out_C": 50.0,
                "m_dot_hot_kg_s": 5.0,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "session_id" in body

    @pytest.mark.asyncio
    async def test_start_design_missing_raw_request(self, client: AsyncClient):
        """Omitting required field returns 422."""
        resp = await client.post(
            "/api/v1/hx/design",
            json={"user_id": "test-user"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_start_design_empty_raw_request(self, client: AsyncClient):
        """Empty raw_request violates min_length=1."""
        resp = await client.post(
            "/api/v1/hx/design",
            json={"raw_request": "", "user_id": "test-user"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_start_design_missing_user_id(self, client: AsyncClient):
        """Omitting user_id returns 422."""
        resp = await client.post(
            "/api/v1/hx/design",
            json={"raw_request": "Design an HX"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/hx/design/{session_id}/status
# ---------------------------------------------------------------------------

class TestDesignStatus:
    @pytest.mark.asyncio
    async def test_status_of_existing_session(self, client: AsyncClient):
        """After starting a design, its status should be loadable."""
        create_resp = await client.post(
            "/api/v1/hx/design",
            json={
                "raw_request": "Design HX for steam condensation",
                "user_id": "test-user",
            },
        )
        session_id = create_resp.json()["session_id"]

        # Give the background task a moment to start
        await asyncio.sleep(0.3)

        resp = await client.get(f"/api/v1/hx/design/{session_id}/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == session_id
        assert "current_step" in body
        assert "waiting_for_user" in body

    @pytest.mark.asyncio
    async def test_status_unknown_session_returns_404(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/hx/design/nonexistent-session-id/status"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/hx/design/{session_id}/respond
# ---------------------------------------------------------------------------

class TestRespondToEscalation:
    @pytest.mark.asyncio
    async def test_respond_unknown_session_returns_404(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/hx/design/nonexistent-id/respond",
            json={"type": "accept"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_respond_accept(self, client: AsyncClient):
        """Create session, then post accept — should return 200 if session exists."""
        create_resp = await client.post(
            "/api/v1/hx/design",
            json={
                "raw_request": "Design HX",
                "user_id": "test-user",
            },
        )
        session_id = create_resp.json()["session_id"]

        # Give session time to be persisted
        await asyncio.sleep(0.3)

        resp = await client.post(
            f"/api/v1/hx/design/{session_id}/respond",
            json={"type": "accept"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "received"

    @pytest.mark.asyncio
    async def test_respond_override_with_values(self, client: AsyncClient):
        """Override with custom values."""
        create_resp = await client.post(
            "/api/v1/hx/design",
            json={
                "raw_request": "Design HX",
                "user_id": "test-user",
            },
        )
        session_id = create_resp.json()["session_id"]
        await asyncio.sleep(0.3)

        resp = await client.post(
            f"/api/v1/hx/design/{session_id}/respond",
            json={
                "type": "override",
                "values": {"T_hot_in_C": 130.0},
            },
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Session store in-memory fallback
# ---------------------------------------------------------------------------

class TestSessionStoreInMemory:
    @pytest.mark.asyncio
    async def test_save_and_load_without_redis(self):
        """SessionStore works with redis_client=None (in-memory)."""
        from hx_engine.app.models.design_state import DesignState

        store = SessionStore(redis_client=None)
        state = DesignState(raw_request="test", user_id="u1")
        sid = state.session_id

        await store.save(sid, state)
        loaded = await store.load(sid)
        assert loaded is not None
        assert loaded.session_id == sid
        assert loaded.raw_request == "test"

    @pytest.mark.asyncio
    async def test_heartbeat_and_orphan_without_redis(self):
        """Heartbeat + orphan detection works in-memory."""
        store = SessionStore(redis_client=None)
        sid = "test-session-123"

        # Before heartbeat, should not be orphaned (no record = assume alive)
        assert not await store.is_orphaned(sid)

        await store.heartbeat(sid)
        assert not await store.is_orphaned(sid)

    @pytest.mark.asyncio
    async def test_delete_without_redis(self):
        """Delete cleans in-memory stores."""
        from hx_engine.app.models.design_state import DesignState

        store = SessionStore(redis_client=None)
        state = DesignState(raw_request="test", user_id="u1")
        sid = state.session_id

        await store.save(sid, state)
        await store.heartbeat(sid)
        await store.delete(sid)

        assert await store.load(sid) is None
