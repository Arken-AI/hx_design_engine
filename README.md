# ARKEN AI — HX Design Engine

FastAPI microservice implementing the 16-step shell-and-tube heat exchanger design pipeline. Combines deterministic engineering calculations (Bell-Delaware, Gnielinski, TEMA standards) with bounded AI review (Claude Sonnet 4.6) to produce fully audited designs with real-time SSE streaming.

**Port:** `8100`  
**Current status:** Steps 1–9 live; Steps 10–16 in development (required to complete MVP)

---

## Overview

The HX Engine is the engineering core of ARKEN. It:

1. Receives validated process conditions from the Backend via `POST /api/v1/hx/design`
2. Runs a sequential 16-step pipeline — each step follows the same 4-layer pattern:
   - **Layer 1** — Deterministic calculation (pure Python, no AI)
   - **Layer 2** — Hard-rule validation (TEMA/ASME limits; AI cannot override)
   - **Layer 3** — AI Senior Engineer review (single Claude call: PROCEED / CORRECT / WARN / ESCALATE)
   - **Layer 4** — DesignState accumulation
3. Streams 8 SSE event types live to the browser as each step executes
4. Persists session state in Redis (24-hour TTL) with an in-memory fallback

---

## Pipeline Steps

| Step | Name | Status |
|---|---|---|
| 1 | Parse & Validate Requirements | ✅ Live |
| 2 | Calculate Heat Duty | ✅ Live |
| 3 | Fluid Properties (5-backend priority chain) | ✅ Live |
| 4 | TEMA Type & Geometry Selection | ✅ Live |
| 5 | LMTD & F-Factor | ✅ Live |
| 6 | Initial U Estimate (table lookup) | ✅ Live |
| 7 | Tube-Side Heat Transfer (Gnielinski) | ✅ Live |
| 8 | Shell-Side Heat Transfer (Bell-Delaware) | ✅ Live |
| 9 | Overall Heat Transfer Coefficient + Kern cross-check | ✅ Live |
| 10 | Pressure Drops (tube-side + shell-side) | ⬜ Planned |
| 11 | Area + Overdesign % | ⬜ Planned |
| 12 | Convergence Loop (Steps 7–11, ΔU < 1%) | ⬜ Planned |
| 13 | Vibration Safety (5 mechanisms) | ⬜ Planned |
| 14 | Mechanical Design (ASME VIII) | ⬜ Planned |
| 15 | Cost Estimate (Turton + CEPCI 2026) | ⬜ Planned |
| 16 | Final Validation + Confidence Score | ⬜ Planned |

---

## Prerequisites

- Python 3.11+
- Redis 7 (session state)
- MongoDB 7 (optional — fouling factor cache)
- Anthropic API key (Claude Sonnet 4.6)

---

## Quick Start

```bash
cd hx_design_engine
python3.11 -m venv venv
source venv/bin/activate
pip install ".[thermo,dev]"   # includes CoolProp, IAPWS, thermo
cp .env.example .env
# Edit .env — set HX_ANTHROPIC_API_KEY and HX_REDIS_URL
uvicorn hx_engine.app.main:app --host 0.0.0.0 --port 8100 --reload
```

API available at **http://localhost:8100**  
Swagger UI: **http://localhost:8100/docs**  
Health check: `GET /health`

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `HX_ANTHROPIC_API_KEY` | Yes | Claude Sonnet 4.6 API key |
| `HX_REDIS_URL` | Yes | Redis URL (default: `redis://localhost:6379/0`) |
| `HX_MONGODB_URI` | No | MongoDB connection string |
| `HX_MONGODB_DB_NAME` | No | Database name (default: `arken_process_db`) |
| `HX_INTERNAL_SECRET` | Yes | Shared secret for Backend → HX Engine auth |
| `HX_AI_MODEL` | No | Claude model name (default: `claude-sonnet-4-6`) |
| `HX_HOST` | No | Bind address (default: `0.0.0.0`) |
| `HX_PORT` | No | Port (default: `8100`) |
| `HX_DEBUG` | No | Debug mode (default: `false`) |
| `HX_LOG_LEVEL` | No | Log level (default: `INFO`) |

---

## Project Structure

```
hx_engine/app/
├── main.py                   # FastAPI app, lifespan, middleware
├── config.py                 # Pydantic settings
├── api/
│   └── hx_routes.py          # POST /requirements, POST /design,
│                             #   GET /design/{id}/stream, GET /design/{id}/status,
│                             #   POST /design/{id}/respond
├── core/
│   ├── pipeline_runner.py    # Outer loop: step execution, SSE emission, ESCALATE handling
│   ├── ai_engineer.py        # Claude API client — single call per step, 3 retries
│   └── session_store.py      # Redis-backed DesignState persistence (+ in-memory fallback)
├── steps/
│   ├── base.py               # BaseStep: run_with_review_loop() — 4-layer pattern
│   ├── step_01_*.py … step_09_*.py   # One file per implemented step
│   └── registry.py           # Step registry: maps step_id → class
├── models/
│   ├── design_state.py       # DesignState Pydantic model (~457 fields)
│   └── events.py             # SSE event models (8 types)
├── correlations/
│   ├── bell_delaware.py      # Shell-side h (Taborek 1983)
│   └── gnielinski.py         # Tube-side h (turbulent + laminar)
├── adapters/
│   ├── thermo_adapter.py     # Fluid property dispatcher (5-backend chain)
│   └── petroleum_correlations.py  # API gravity-based mixture correlations
├── data/
│   ├── u_assumptions.py      # Initial U lookup (Perry's / Serth)
│   ├── fouling_factors.py    # TEMA fouling factors
│   ├── tema_tables.py        # TEMA tube count tables
│   └── bwg_gauge.py          # BWG tube gauge data
└── prompts/
    └── ai_prompts.py         # Base prompt + 16 step-specific prompts
```

---

## Key Engineering Decisions

**Bell-Delaware is always primary.** Kern is a cross-check only. Deviation ≤15% → PROCEED; 15–30% → WARN; >30% → ESCALATE. The lower U is never auto-selected.

**Fluid property priority chain:**  
`iapws` → `CoolProp` → `Petroleum correlations` → `Specialty fits` → `thermo`  
Petroleum correlations (API gravity-based) precede `thermo` because `thermo`'s `Chemical` class returns silently wrong values for multi-component mixtures like crude oil.

**AI review is a single bounded call per step.** 4 decisions only: PROCEED, CORRECT, WARN, ESCALATE. Temperature 0.1, max tokens 2048. Confidence < 0.70 → forced ESCALATE. On total AI failure (3 retries exhausted), the design continues with hard-rule validation only.

**Hard validation rules (Layer 2) cannot be overridden by AI:**  
F-factor ≥ 0.75 · Shell ΔP < 1.4 bar · Tube ΔP < 0.7 bar · Tube velocity > 0.5 m/s · J_l > 0.40 · Connors ratio < 0.5

---

## SSE Events

| Event | When |
|---|---|
| `step_started` | Step begins |
| `step_approved` | AI: PROCEED |
| `step_corrected` | AI: CORRECT (after successful fix) |
| `step_warning` | AI: WARN |
| `step_escalated` | AI: ESCALATE — pipeline pauses for user input |
| `step_error` | Layer 2 failure, exception, or max escalations |
| `iteration_progress` | Step 12 convergence loop iterations |
| `design_complete` | All steps finished |

---

## Running Tests

```bash
cd hx_design_engine
pytest tests/ -v
pytest tests/ -v --cov=hx_engine   # with coverage
```

Validated against Serth Example 5.1: ±5% on overall U, ±10% on pressure drops and J-factors.

---

## Docker

The HX Engine runs as the `hx-engine` service in `docker/docker-compose.yml`. See `docker/README.md` for the full stack setup.

```bash
cd docker
docker compose up -d
```
