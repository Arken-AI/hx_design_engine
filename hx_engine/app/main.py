"""HX Design Engine — FastAPI application entry point.

Run with:
    uvicorn hx_engine.app.main:app --host 0.0.0.0 --port 8100 --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hx_engine.app import dependencies
from hx_engine.app.config import settings
from hx_engine.app.routers import design, requirements, stream

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown hooks
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage shared resources: Redis connection, AI engineer, etc."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info(
        "Starting HX Design Engine on %s:%d (debug=%s)",
        settings.host,
        settings.port,
        settings.debug,
    )
    await dependencies.startup()
    yield
    await dependencies.shutdown()
    logger.info("HX Design Engine shutdown complete")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="HX Design Engine",
    description="TEMA-compliant shell-and-tube heat exchanger design pipeline",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow all in development; restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers — plan requires /api/v1/hx prefix
app.include_router(requirements.router, prefix="/api/v1/hx")
app.include_router(design.router, prefix="/api/v1/hx")
app.include_router(stream.router, prefix="/api/v1/hx")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "hx-engine", "version": "0.1.0"}
