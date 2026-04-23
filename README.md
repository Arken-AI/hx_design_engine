# HX Design Engine

ARKEN AI — a computational engineering platform for designing industrial shell-and-tube heat exchangers. Users describe their problem in natural language; the engine performs all engineering calculations, validates every result with AI engineering judgment, and returns a complete, fabrication-ready design with full reasoning transparency at every step.

> Deterministic calculation + bounded AI judgment + hard rule safety net + user escalation.

## What It Does

**Design Mode (Sizing):** User knows process conditions; system determines geometry.
**Rating Mode (Performance Check):** User knows conditions and geometry; system checks if it works.

**Inputs:** Fluid identities, flow rates (kg/s), inlet/outlet temperatures, pressures, material preferences, TEMA class, constraints.

**Outputs:** Complete geometry, thermal performance (U, Q, LMTD, overdesign %), pressure drops, vibration safety, mechanical design, cost estimate, confidence score (0.0–1.0), step-by-step reasoning.

## Phase Support

**Phase 1 scope: single-phase liquids only.**

| Phase | Supported | Notes |
|---|---|---|
| Liquid | Yes | Density 50–2000 kg/m³ — full pipeline |
| Vapour / Gas | No | Density < 50 kg/m³ rejected at Step 3 validation |
| Two-phase | No | Escalated at Step 1; deferred to Phase 2 |

## Architecture

The engine follows a **fat skill, thin harness** design:

- **Thin harness** — FastAPI routers (~500 LOC) accept HTTP requests, create a session, and delegate to the pipeline runner. Zero calculation logic.
- **Fat skill** — The pipeline (~20,000 LOC) runs a 16-step deterministic calculation engine, hard validation rules, and bounded Claude AI review per step.

Every step passes through four layers:

1. **Deterministic calculation** — pure Python engineering math (Bell-Delaware, Gnielinski, ASME, etc.)
2. **Hard rule validation** — engineering limits checked before AI review; AI cannot override
3. **Bounded AI review** — single Claude API call per step; can only proceed / correct / warn / escalate
4. **Design state** — Pydantic model accumulates outputs, corrections, warnings, and confidence across all steps

```
hx_engine/app/
├── routers/          # Thin harness — HTTP routes only
├── core/             # Pipeline runner, AI engineer, validation rules
├── steps/            # 16 step implementations (pure calculation functions)
├── correlations/     # Bell-Delaware, TEMA vibration, ASME thickness, etc.
├── data/             # TEMA tables, fouling factors, material properties
├── adapters/         # CoolProp / IAPWS wrapper, unit conversions
└── models/           # DesignState, StepResult, AIReview
```

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI + Uvicorn |
| Data validation | Pydantic v2 |
| AI review | Anthropic Claude (via `anthropic` SDK) |
| Session state | Redis |
| Fouling cache | MongoDB (optional) |
| Streaming | Server-Sent Events (sse-starlette) |
| Thermo properties | CoolProp, IAPWS, thermo (optional) |
| Python | ≥ 3.11 |

## Installation

### Prerequisites

- Python 3.11+
- Redis
- MongoDB (optional — fouling factor cache)
- Anthropic API key

### Setup

```bash
# Create and activate virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install with thermo libraries (recommended)
pip install ".[thermo]"

# Or core only
pip install .

# Dev / testing extras
pip install ".[dev]"
```

### Environment Variables

```bash
cp .env.example .env
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `HX_ANTHROPIC_API_KEY` | Yes | — | Anthropic API key for Claude |
| `HX_REDIS_URL` | Yes | `redis://localhost:6379/0` | Redis connection URL |
| `HX_MONGODB_URI` | No | — | MongoDB connection string |
| `HX_MONGODB_DB_NAME` | No | `arken_process_db` | MongoDB database name |
| `HX_HOST` | No | `0.0.0.0` | Bind address |
| `HX_PORT` | No | `8100` | Port |
| `HX_DEBUG` | No | `false` | Debug mode |
| `HX_LOG_LEVEL` | No | `INFO` | Logging level |

### Start Redis

```bash
# macOS
brew services start redis

# Linux
sudo systemctl start redis

# Docker
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

### Start MongoDB (optional)

```bash
docker run -d --name mongo \
  -p 27017:27017 \
  -e MONGO_INITDB_ROOT_USERNAME=admin \
  -e MONGO_INITDB_ROOT_PASSWORD=admin \
  mongo:7
```

## Running

```bash
uvicorn hx_engine.app.main:app --host 0.0.0.0 --port 8100 --reload
```

### Docker

```bash
docker build -t hx-design-engine .
docker run -d --name hx-engine \
  -p 8100:8100 \
  --env-file .env \
  hx-design-engine
```

## API

Base URL: `http://localhost:8100`

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/docs` | GET | Swagger UI |
| `/api/v1/hx/validate` | POST | Validate requirements before design |
| `/api/v1/hx/design` | POST | Start a design session |
| `/api/v1/hx/design/{session_id}/status` | GET | Poll session status |
| `/api/v1/hx/design/{session_id}/respond` | POST | Respond to an AI escalation |
| `/api/v1/hx/stream/{session_id}` | GET | SSE stream of step-by-step results |

## Tests

```bash
pytest
```

## Design Constraints

- Calculation accuracy target: match HTRI/textbook benchmarks (Serth Example 5.1 ±5% on U, ±10% on dP)
- AI is bounded — deterministic calculation and hard rule validation always run before AI review
- AI cannot override hard engineering limits
- Phase 1 scope: single-phase liquids only (ρ = 50–2000 kg/m³)
