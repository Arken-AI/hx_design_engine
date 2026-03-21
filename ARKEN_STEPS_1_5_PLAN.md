# ARKEN AI — Steps 1–5 Implementation Plan

**Scope:** HX Engine microservice (Steps 1–5) + Backend integration + Frontend SSE wiring
**Team:** 3 developers working in parallel by layer
**Duration:** ~10 working days (Week 1 foundation + Week 2 steps)
**Source of truth:** `hx_design_engine/ARKEN_MASTER_PLAN.md` v8.0
**Eng Review:** 2026-03-21 — 7 issues resolved (see Eng Review Log at end of file)

---

## Table of Contents

1. [Developer Assignments](#1-developer-assignments)
2. [Dependency Graph](#2-dependency-graph)
3. [Day-by-Day Breakdown](#3-day-by-day-breakdown)
4. [Dev A — HX Engine Core](#4-dev-a--hx-engine-core)
5. [Dev B — Infrastructure & API](#5-dev-b--infrastructure--api)
6. [Dev C — Frontend + Backend Integration](#6-dev-c--frontend--backend-integration)
7. [File Specifications](#7-file-specifications)
8. [Data Files (Steps 1–5)](#8-data-files-steps-15)
9. [Test Requirements](#9-test-requirements)
10. [Integration Checkpoints](#10-integration-checkpoints)
11. [Docker & nginx Setup](#11-docker--nginx-setup)
12. [NOT in Scope](#12-not-in-scope)

---

## 1. Developer Assignments

```
DEV A — HX Engine Core (models, steps, correlations, data)
  Owner of: hx_engine/app/models/*, hx_engine/app/steps/*,
            hx_engine/app/correlations/*, hx_engine/app/adapters/*,
            hx_engine/app/data/*, hx_engine/app/core/ai_engineer.py,
            hx_engine/app/core/validation_rules.py,
            hx_engine/app/core/exceptions.py

DEV B — Infrastructure & API (FastAPI, Redis, Docker, nginx, SSE, pipeline)
  Owner of: hx_engine/app/main.py, hx_engine/app/config.py,
            hx_engine/app/dependencies.py, hx_engine/app/routers/*,
            hx_engine/app/core/session_store.py, hx_engine/app/core/sse_manager.py,
            hx_engine/app/core/pipeline_runner.py, hx_engine/app/core/prompts/*,
            docker-compose.yml, nginx.conf, Dockerfile, pyproject.toml

DEV C — Frontend + Backend Integration
  Owner of: frontend/src/hooks/useHXStream.js,
            frontend/src/types/hxEvents.ts (or .js mirror),
            frontend/src/components/hx/* (wire to live SSE),
            frontend/src/utils/sseClient.js (extend for HX events),
            backend/app/core/engine_client.py,
            backend/app/config.py (add hx_engine_url),
            backend/app/dependencies.py (add get_engine_registry)
```

---

## 2. Dependency Graph

```
DAY 1 ─────────────────────────────────────────────────────────────
  DEV A: Contracts (models) ←── BLOCKER for everything else
  DEV B: waits on Dev A's models (can scaffold pyproject.toml, Dockerfile)
  DEV C: can start backend engine_client.py stub + frontend useHXStream.js

DAY 2 ─────────────────────────────────────────────────────────────
  DEV A: BaseStep, validation_rules, ai_engineer stub, exceptions
  DEV B: config.py, session_store.py, sse_manager.py, main.py (needs models from Day 1)
  DEV C: backend config + dependencies + engines.yaml; frontend hxEvents types

DAY 3 ─────────────────────────────────────────────────────────────
  DEV A: tests for models (12 CG3A validator tests)
  DEV B: routers (design.py, stream.py), pipeline_runner.py skeleton
  DEV C: frontend StepCard SSE wiring, ProgressBar live updates

DAY 4 ─────────────────────────────────────────────────────────────
  DEV B: Docker + nginx + docker-compose.yml + .env.example
  DEV A: can start adapters (thermo_adapter, units_adapter)
  DEV C: frontend ChatContainer → HX design flow, MessageBubble reskin

DAY 5 ─── CHECKPOINT 1: all 3 services start, /health 200 ────────
  ALL: Integration test — docker-compose up, verify health checks
  DEV A: lmtd.py correlation
  DEV B: conftest.py + test fixtures
  DEV C: end-to-end: type message → backend → HX Engine → SSE → frontend

DAYS 6–10 (Week 2) ───────────────────────────────────────────────
  DEV A: step_01 → step_05 (one step per day, tests included)
  DEV B: wire steps into pipeline_runner, integration tests
  DEV C: frontend renders each step's SSE events as they come online

  Pre-requisite gate: Week 1 models finalized + 12 CG3A tests passing
```

---

## 3. Day-by-Day Breakdown

### WEEK 1 — Foundation

| Day | Dev A (Core) | Dev B (Infrastructure) | Dev C (Frontend + Backend) |
|-----|-------------|----------------------|---------------------------|
| 1 | `models/design_state.py`, `models/step_result.py`, `models/sse_events.py`, `steps/__init__.py` | `pyproject.toml`, `Dockerfile` scaffold, project structure | `backend/app/core/engine_client.py` stub, start `useHXStream.js` |
| 2 | `steps/base.py`, `core/validation_rules.py`, `core/ai_engineer.py` stub, `core/exceptions.py` | `config.py`, `session_store.py`, `sse_manager.py`, `main.py` + `/health` | `backend/app/config.py` (add `hx_engine_url`), `backend/engines.yaml`, `frontend/src/types/hxEvents.js` |
| 3 | Unit tests: 12 CG3A validators, StepProtocol compliance | `routers/design.py`, `routers/stream.py`, `core/pipeline_runner.py` skeleton | Wire `useHXStream.js` → `StepCard.jsx` (mock SSE events for dev), `ProgressBar.jsx` live |
| 4 | `adapters/thermo_adapter.py`, `adapters/units_adapter.py` | `docker-compose.yml`, `nginx.conf`, `.env.example`, `Dockerfile` final | `ChatContainer.jsx` → trigger HX design via backend, `MessageBubble.jsx` terminal reskin |
| 5 | `correlations/lmtd.py` + tests, `data/tema_tables.py`, `data/fouling_factors.py`, `data/u_assumptions.py` | `tests/conftest.py`, integration smoke test (health checks) | End-to-end smoke: message → backend → HX Engine → SSE → StepCard renders |

### WEEK 2 — Steps 1–5

| Day | Dev A (Core) | Dev B (Infrastructure) | Dev C (Frontend + Backend) |
|-----|-------------|----------------------|---------------------------|
| 6 | `step_01_requirements.py` + unit tests | Wire step_01 into pipeline_runner, verify SSE events | Frontend: Step 1 card rendering with ESCALATED state (fluid ambiguity) |
| 7 | `step_02_heat_duty.py` + unit tests | Wire step_02, verify conditional AI trigger | Frontend: Step 2 card, heat duty display with Q value |
| 8 | `step_03_fluid_props.py` + unit tests | Wire step_03, verify property anomaly trigger | Frontend: Step 3 card, fluid properties table display |
| 9 | `step_04_tema_geometry.py` + unit tests | Wire step_04, verify ESCALATED flow (two equally valid types) | Frontend: Step 4 card, geometry spec display, escalation inline input |
| 10 | `step_05_lmtd.py` + unit tests | `tests/integration/test_pipeline_steps_1_5.py` (Steps 1–5 with mock AI) | Full flow test: user types design request → Steps 1–5 stream to frontend |

---

## 4. Dev A — HX Engine Core

### 4.1 Repository Setup

```bash
mkdir -p /workspace/hx_engine
cd /workspace/hx_engine
git init
```

### 4.2 Directory Structure (Dev A's files)

```
hx_engine/
├── app/
│   ├── __init__.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── design_state.py      # Day 1
│   │   ├── step_result.py       # Day 1
│   │   └── sse_events.py        # Day 1
│   ├── steps/
│   │   ├── __init__.py           # Day 1 (StepProtocol)
│   │   ├── base.py               # Day 2
│   │   ├── step_01_requirements.py    # Day 6
│   │   ├── step_02_heat_duty.py       # Day 7
│   │   ├── step_03_fluid_props.py     # Day 8
│   │   ├── step_04_tema_geometry.py   # Day 9
│   │   └── step_05_lmtd.py           # Day 10
│   ├── core/
│   │   ├── __init__.py
│   │   ├── ai_engineer.py        # Day 2 (stub — always PROCEED)
│   │   ├── validation_rules.py   # Day 2 (framework, rules added per step)
│   │   └── exceptions.py         # Day 2
│   ├── correlations/
│   │   ├── __init__.py
│   │   └── lmtd.py               # Day 5
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── thermo_adapter.py     # Day 4
│   │   └── units_adapter.py      # Day 4
│   └── data/
│       ├── __init__.py
│       ├── tema_tables.py         # Day 5
│       ├── fouling_factors.py     # Day 5
│       └── u_assumptions.py       # Day 5
├── tests/
│   ├── unit/
│   │   ├── models/
│   │   │   └── test_design_state.py   # Day 3
│   │   ├── steps/
│   │   │   ├── test_step_protocol.py  # Day 3
│   │   │   ├── test_step_01.py        # Day 6
│   │   │   ├── test_step_02.py        # Day 7
│   │   │   ├── test_step_03.py        # Day 8
│   │   │   ├── test_step_04.py        # Day 9
│   │   │   └── test_step_05.py        # Day 10
│   │   ├── correlations/
│   │   │   └── test_lmtd.py           # Day 5
│   │   └── adapters/
│   │       └── test_thermo_adapter.py # Day 4
│   └── __init__.py
└── pyproject.toml                     # Dev B owns this
```

### 4.3 Day 1 — Contracts (BLOCKER)

**File: `app/models/design_state.py`**

```python
from __future__ import annotations
from typing import Optional, List
from uuid import uuid4
from pydantic import BaseModel, Field, field_validator

class FluidProperties(BaseModel):
    name: str
    density_kg_m3: float          # [50, 2000]
    viscosity_Pa_s: float         # [1e-6, 1.0]
    cp_J_kgK: float               # [500, 10000]
    k_W_mK: float                 # [0.01, 100]
    Pr: float                     # [0.5, 1000]
    phase: str = "liquid"         # "liquid" | "gas"
    mean_temp_C: Optional[float] = None

class GeometrySpec(BaseModel):
    shell_diameter_m: Optional[float] = None
    tube_od_m: Optional[float] = None
    tube_id_m: Optional[float] = None
    tube_length_m: Optional[float] = None
    baffle_spacing_m: Optional[float] = None    # [0.05, 2.0] m
    pitch_ratio: Optional[float] = None         # [1.2, 1.5]
    n_tubes: Optional[int] = None
    n_passes: Optional[int] = None
    pitch_layout: str = "triangular"            # "triangular" | "square"
    baffle_cut: Optional[float] = None          # [0.15, 0.45]

    # CG3A validators — every geometry field has physical bounds
    @field_validator("baffle_spacing_m")
    @classmethod
    def validate_baffle_spacing(cls, v):
        if v is not None and not (0.05 <= v <= 2.0):
            raise ValueError(f"baffle_spacing_m must be 0.05–2.0m, got {v}")
        return v

    @field_validator("pitch_ratio")
    @classmethod
    def validate_pitch_ratio(cls, v):
        if v is not None and not (1.2 <= v <= 1.5):
            raise ValueError(f"pitch_ratio must be 1.2–1.5, got {v}")
        return v

    @field_validator("shell_diameter_m")
    @classmethod
    def validate_shell_diameter(cls, v):
        if v is not None and not (0.05 <= v <= 3.0):
            raise ValueError(f"shell_diameter_m must be 0.05–3.0m, got {v}")
        return v

    @field_validator("tube_od_m")
    @classmethod
    def validate_tube_od(cls, v):
        if v is not None and not (0.005 <= v <= 0.10):
            raise ValueError(f"tube_od_m must be 0.005–0.10m, got {v}")
        return v

    @field_validator("tube_id_m")
    @classmethod
    def validate_tube_id(cls, v):
        if v is not None and not (0.003 <= v <= 0.095):
            raise ValueError(f"tube_id_m must be 0.003–0.095m, got {v}")
        return v

    @field_validator("tube_length_m")
    @classmethod
    def validate_tube_length(cls, v):
        if v is not None and not (0.5 <= v <= 10.0):
            raise ValueError(f"tube_length_m must be 0.5–10.0m, got {v}")
        return v

    @field_validator("baffle_cut")
    @classmethod
    def validate_baffle_cut(cls, v):
        if v is not None and not (0.15 <= v <= 0.45):
            raise ValueError(f"baffle_cut must be 0.15–0.45, got {v}")
        return v


class DesignState(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    org_id: Optional[str] = None
    raw_request: str
    mode: str = "design"  # "design" | "rating"

    # Fluid properties (populated by Step 3)
    shell_fluid: Optional[FluidProperties] = None
    tube_fluid: Optional[FluidProperties] = None

    # Geometry (populated by Step 4)
    geometry: GeometrySpec = Field(default_factory=GeometrySpec)

    # Thermal results
    Q_W: Optional[float] = None
    LMTD_C: Optional[float] = None
    F_factor: Optional[float] = None
    U_overall_W_m2K: Optional[float] = None
    h_tube_W_m2K: Optional[float] = None
    h_shell_W_m2K: Optional[float] = None
    area_required_m2: Optional[float] = None
    area_provided_m2: Optional[float] = None
    overdesign_pct: Optional[float] = None

    # Pressure drops
    dP_tube_Pa: Optional[float] = None
    dP_shell_Pa: Optional[float] = None

    # Final results
    vibration_safe: Optional[bool] = None
    cost_usd: Optional[float] = None
    confidence_score: Optional[float] = None
    confidence_breakdown: Optional[dict] = None
    tema_type: Optional[str] = None

    # Process temps (populated by Step 1)
    T_hot_in_C: Optional[float] = None
    T_hot_out_C: Optional[float] = None
    T_cold_in_C: Optional[float] = None
    T_cold_out_C: Optional[float] = None
    m_dot_hot_kg_s: Optional[float] = None
    m_dot_cold_kg_s: Optional[float] = None
    hot_fluid_name: Optional[str] = None
    cold_fluid_name: Optional[str] = None
    shell_passes: int = 1
    tube_passes: int = 2

    # Pipeline state
    warnings: List[str] = Field(default_factory=list)
    step_records: List[dict] = Field(default_factory=list)
    review_notes: List[str] = Field(default_factory=list)
    in_convergence_loop: bool = False
    convergence_iteration: int = 0
    waiting_for_user: bool = False
    current_step: int = 0
```

**File: `app/models/step_result.py`**

```python
from enum import Enum
from typing import Optional, Any, List
from datetime import datetime
from pydantic import BaseModel


class AIModeEnum(str, Enum):
    FULL = "full"
    CONDITIONAL = "conditional"
    NONE = "none"


class AIDecisionEnum(str, Enum):
    PROCEED = "proceed"
    CORRECT = "correct"
    WARN = "warn"
    ESCALATE = "escalate"


class AICorrection(BaseModel):
    affected_fields: List[str]
    values: dict[str, Any]
    reasoning: str


class AIReview(BaseModel):
    decision: AIDecisionEnum
    confidence: float               # 0.0 to 1.0
    reasoning: str
    correction: Optional[AICorrection] = None
    user_summary: str = ""
    observation: Optional[str] = None
    # Escalation-only fields
    attempts: Optional[list] = None
    recommendation: Optional[str] = None
    options: Optional[List[str]] = None
    ai_called: bool = True


class StepResult(BaseModel):
    """Output of a step's Layer 1 execute() call."""
    step_id: int
    step_name: str
    outputs: dict[str, Any]         # step-specific computed values
    validation_passed: bool = True
    validation_errors: List[str] = Field(default_factory=list)


class StepRecord(BaseModel):
    """Persisted audit log entry appended to DesignState.step_records."""
    step_id: int
    step_name: str
    result: dict                    # serialized StepResult
    review: Optional[dict] = None   # serialized AIReview
    timestamp: datetime
    duration_ms: int
    ai_called: bool
    ai_decision: Optional[str] = None
```

**File: `app/models/sse_events.py`**

```python
"""
All 8 SSE event types emitted by the HX Engine pipeline.
Frontend mirrors these in types/hxEvents.js
"""
from typing import Optional, Any, List
from pydantic import BaseModel


class StepStartedEvent(BaseModel):
    event_type: str = "step_started"
    step_id: int
    step_name: str
    total_steps: int = 16


class StepApprovedEvent(BaseModel):
    event_type: str = "step_approved"
    step_id: int
    step_name: str
    confidence: float
    reasoning: str
    user_summary: str
    duration_ms: int
    outputs: dict[str, Any] = {}


class StepCorrectedEvent(BaseModel):
    event_type: str = "step_corrected"
    step_id: int
    step_name: str
    confidence: float
    reasoning: str
    user_summary: str
    correction: dict               # what changed and why
    before: dict                   # old values
    after: dict                    # new values
    duration_ms: int
    outputs: dict[str, Any] = {}


class StepWarningEvent(BaseModel):
    event_type: str = "step_warning"
    step_id: int
    step_name: str
    confidence: float
    reasoning: str
    user_summary: str
    warning_message: str
    duration_ms: int
    outputs: dict[str, Any] = {}


class StepEscalatedEvent(BaseModel):
    event_type: str = "step_escalated"
    step_id: int
    step_name: str
    confidence: float
    observation: str
    recommendation: str
    options: List[str]
    attempts: Optional[list] = None


class StepErrorEvent(BaseModel):
    event_type: str = "step_error"
    step_id: int
    step_name: str
    message: str
    observation: Optional[str] = None
    recommendation: Optional[str] = None
    options: Optional[List[str]] = None


class IterationProgressEvent(BaseModel):
    event_type: str = "iteration_progress"
    iteration_number: int
    max_iterations: int = 20
    current_U: Optional[float] = None
    delta_U_pct: Optional[float] = None
    constraints_met: bool = False


class DesignCompleteEvent(BaseModel):
    event_type: str = "design_complete"
    session_id: str
    confidence_score: Optional[float] = None
    confidence_breakdown: Optional[dict] = None
    summary: str = ""
    design_state: dict = {}        # full serialized DesignState
```

**File: `app/steps/__init__.py`**

```python
from typing import Protocol, runtime_checkable
from app.models.design_state import DesignState
from app.models.step_result import StepResult


@runtime_checkable
class StepProtocol(Protocol):
    step_id: int
    step_name: str

    def execute(self, state: DesignState) -> StepResult: ...
```

### 4.4 Day 2 — Base Step Infrastructure

**File: `app/steps/base.py`**

```python
from abc import ABC, abstractmethod
from app.models.step_result import AIModeEnum, StepResult, AIReview
from app.models.design_state import DesignState


class BaseStep(ABC):
    step_id: int
    step_name: str
    ai_mode: AIModeEnum

    @abstractmethod
    def execute(self, state: DesignState) -> StepResult:
        """Layer 1: Pure calculation. No side effects."""
        ...

    def _should_call_ai(self, state: DesignState, result: StepResult) -> bool:
        """Determine if AI review is needed for this step."""
        if self.ai_mode == AIModeEnum.FULL:
            return True
        if self.ai_mode == AIModeEnum.NONE:
            return False
        if state.in_convergence_loop:
            return False  # Decision 3A
        return self._conditional_ai_trigger(state, result)

    def _conditional_ai_trigger(self, state: DesignState, result: StepResult) -> bool:
        """Override in subclass to define when conditional AI fires."""
        return False
```

**Full `run_with_review_loop()` implementation:** Copy from master plan §7.5 lines 978–1102. This is the shared correction loop all 16 steps use. Implement it exactly as specified — it handles PROCEED, CORRECT (max 3 attempts), WARN, ESCALATE, confidence gate (< 0.5 → force escalate), snapshot/restore on Layer 2 hard fail.

**File: `app/core/ai_engineer.py`** (STUB for Week 1–2)

```python
"""
AI Senior Engineer — STUB.
Always returns PROCEED with confidence 0.85.
Real implementation in Week 3 (Anthropic API call).
"""
from app.models.step_result import AIReview, AIDecisionEnum


class AIEngineer:
    async def review(self, step, result, design_state,
                     book_context="", past_designs="",
                     prior_attempts=None) -> AIReview:
        return AIReview(
            decision=AIDecisionEnum.PROCEED,
            confidence=0.85,
            reasoning="[STUB] AI review not yet implemented. Proceeding with calculation result.",
            user_summary=f"Step {step} completed. AI review pending.",
            ai_called=False,
        )
```

**File: `app/core/validation_rules.py`**

```python
"""
Layer 2: Hard engineering rules. AI CANNOT override these.
Rules added per-step as steps are built.
"""
from dataclasses import dataclass
from typing import Optional
from app.models.step_result import StepResult


@dataclass
class ValidationResult:
    passed: bool
    errors: list[str]
    auto_corrections: list[dict]  # Layer 2 auto-corrections before AI

    @property
    def fails(self) -> bool:
        return not self.passed


# Registry of rules per step_id
_rules: dict[int, list] = {}


def register_rule(step_id: int, rule_fn):
    """Register a validation rule for a step."""
    _rules.setdefault(step_id, []).append(rule_fn)


def check(step: int, result: StepResult) -> ValidationResult:
    """Run all registered rules for a step."""
    errors = []
    auto_corrections = []
    rules = _rules.get(step, [])
    for rule in rules:
        rule_result = rule(result)
        if rule_result and not rule_result.get("passed", True):
            errors.append(rule_result.get("message", "Validation failed"))
    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        auto_corrections=auto_corrections,
    )
```

**File: `app/core/exceptions.py`**

```python
class CalculationError(Exception):
    def __init__(self, step_id: int, message: str, cause: Exception = None):
        self.step_id = step_id
        self.message = message
        self.cause = cause
        super().__init__(f"Step {step_id}: {message}")


class StepHardFailure(Exception):
    def __init__(self, step_id: int, validation):
        self.step_id = step_id
        self.validation = validation
        super().__init__(f"Step {step_id} hard failure: {validation.errors}")
```

### 4.5 Day 4 — Adapters

**File: `app/adapters/thermo_adapter.py`**

```python
"""
Fluid property lookup with fallback chain: iapws (water) → CoolProp → thermo.
Always returns SI units.

Public interface:
    get_fluid_properties(fluid_name: str, temperature_C: float,
                         pressure_Pa: float = 101325.0) -> FluidProperties
"""
```

Priority chain:
1. **iapws** — for water/steam only (most accurate for water)
2. **CoolProp** — for common pure fluids (reliable, fast)
3. **thermo** — for mixtures and uncommon fluids (broadest coverage)

Must handle:
- Water at 25°C → properties within 1% of NIST values (test this)
- Unknown fluid → raise `CalculationError` with message suggesting similar fluid
- Fluid near critical point → log warning, proceed with best available
- Return `FluidProperties` model with all fields populated

**File: `app/adapters/units_adapter.py`**

```python
"""
Unit conversion utilities. All internal calculations use SI.
Convert user inputs from any common engineering unit system.
"""

def fahrenheit_to_celsius(f: float) -> float: ...
def psi_to_pascal(psi: float) -> float: ...
def lb_hr_to_kg_s(lb_hr: float) -> float: ...
def inch_to_meter(inch: float) -> float: ...
def btu_hr_ft2_F_to_W_m2K(btu: float) -> float: ...
def bar_to_pascal(bar: float) -> float: ...
def pascal_to_bar(pa: float) -> float: ...

def detect_and_convert_temperature(value: float, unit: str) -> float:
    """Detect unit string and convert to Celsius."""
    ...
```

### 4.6 Day 5 — Correlations & Data

**File: `app/correlations/lmtd.py`**

```python
"""
LMTD and F-factor calculations.

Public interface:
    compute_lmtd(T_hot_in, T_hot_out, T_cold_in, T_cold_out) -> float
    compute_f_factor(R, P, n_shell_passes) -> float
    compute_R(T_hot_in, T_hot_out, T_cold_in, T_cold_out) -> float
    compute_P(T_hot_in, T_hot_out, T_cold_in, T_cold_out) -> float

Corner cases to handle:
    - ΔT1 == ΔT2 → use arithmetic mean (avoid 0/0)
    - R == 1.0 → L'Hôpital's rule for F-factor formula
    - Temperature cross (T_cold_out > T_hot_out) → detect, return F with warning
    - F < 0 or complex → return F=0 with error flag
"""
import math

def compute_lmtd(T_hot_in: float, T_hot_out: float,
                 T_cold_in: float, T_cold_out: float) -> float:
    dT1 = T_hot_in - T_cold_out
    dT2 = T_hot_out - T_cold_in

    if abs(dT1 - dT2) < 1e-6:
        return (dT1 + dT2) / 2.0  # arithmetic mean when equal

    if dT1 <= 0 or dT2 <= 0:
        raise ValueError("Temperature cross detected: LMTD undefined")

    return (dT1 - dT2) / math.log(dT1 / dT2)
```

### 4.7 Days 6–10 — Steps 1–5

Each step follows the same template:

```python
class StepNN(BaseStep):
    step_id = N
    step_name = "Step Name"
    ai_mode = AIModeEnum.FULL | CONDITIONAL

    def execute(self, state: DesignState) -> StepResult:
        """Layer 1: Pure calculation."""
        outputs = {}
        # ... calculation logic ...
        return StepResult(
            step_id=self.step_id,
            step_name=self.step_name,
            outputs=outputs,
        )

    def _conditional_ai_trigger(self, state, result) -> bool:
        """When should AI be called? (CONDITIONAL steps only)"""
        return False
```

**Step 1: Gather Process Requirements** (`step_01_requirements.py`)
- ai_mode = FULL
- Layer 1: Parse `raw_request` string to extract: fluid names, temperatures (3 or 4), flow rates, pressures (optional), TEMA class preference (optional)
- Strategy: Use regex patterns + keyword matching for structured extraction. This is deterministic parsing, NOT LLM parsing.
- Populate: `T_hot_in_C`, `T_hot_out_C`, `T_cold_in_C`, `T_cold_out_C`, `m_dot_hot_kg_s`, `m_dot_cold_kg_s`, `hot_fluid_name`, `cold_fluid_name`
- Layer 2 rules: All blocking inputs present (both fluid names, 3+ temps, both flow rates)
- Escalates: fluid ambiguous ("oil" without qualifier), fewer than 3 temps, missing flow rate
- Unit detection: if user says "150°F" → convert to Celsius via `units_adapter`
- If 3 temps given: calculate 4th from energy balance in Step 2

**Step 2: Calculate Heat Duty** (`step_02_heat_duty.py`)
- ai_mode = CONDITIONAL (trigger if Q balance error > 2%)
- Layer 1: `Q = m_dot × Cp × ΔT` for both sides. If 3 temps, calculate 4th.
- Use `thermo_adapter` to get Cp at mean temperature
- Layer 2 rules: Q > 0, Q < 500 MW, energy balance closure |Q_hot - Q_cold|/Q_hot < 1%
- Populate: `Q_W`, missing temperature
- Corner cases: very small ΔT (< 5°C) → warn; Q = 0 → reject; identical temps → reject

**Step 3: Collect Fluid Properties** (`step_03_fluid_props.py`)
- ai_mode = CONDITIONAL (trigger if Pr outside [0.5, 1000])
- Layer 1: Call `thermo_adapter.get_fluid_properties()` for both fluids at bulk mean temp
- Mean temp = (T_in + T_out) / 2 for each side
- Layer 2 rules: all properties > 0, density 50–2000 kg/m³, viscosity > 0
- Populate: `shell_fluid`, `tube_fluid` (FluidProperties models)
- Corner cases: fluid not in library → error with suggestion; crude oil without API gravity → assume API 29

**Step 4: Select TEMA Type + Initial Geometry** (`step_04_tema_geometry.py`)
- ai_mode = FULL
- Layer 1: Decision tree for TEMA type + heuristic geometry selection
- TEMA selection logic:
  - ΔT > 50°C between streams → floating head (AES) for thermal expansion
  - Both fluids clean → fixed tubesheet (BEM, cheapest)
  - One fluid fouling → fouling fluid tube-side, square pitch for cleaning
  - High pressure on one side → high-pressure fluid tube-side
  - Default: BEM with triangular pitch, 19.05mm OD, 1.25 pitch ratio
- Initial geometry heuristics:
  - Tube OD: 19.05mm (3/4"), tube ID from BWG 14
  - Pitch ratio: 1.25 triangular (clean) or 1.25 square (fouling)
  - Tube length: 4.877m (16 ft, standard)
  - Tube passes: 2 (default)
  - Baffle cut: 25%
  - Baffle spacing: 0.2 × shell_diameter (initial estimate)
  - N_tubes, shell_diameter from `data/tema_tables.py` lookup
- Populate: `tema_type`, `geometry` (GeometrySpec)
- Escalates: two TEMA types equally valid → present trade-offs

**Step 5: Determine LMTD and F-Factor** (`step_05_lmtd.py`)
- ai_mode = CONDITIONAL (trigger if F < 0.85)
- Layer 1: Call `correlations/lmtd.py` functions
- Layer 2 rules: F >= 0.75 (HARD FAIL if below), LMTD > 0
- Can correct: if F < 0.80 → try incrementing shell passes from 1→2
- Populate: `LMTD_C`, `F_factor`
- Corner cases: R = 1.0, ΔT1 = ΔT2, temperature cross, very small LMTD (< 3°C → warn)

---

## 5. Dev B — Infrastructure & API

### 5.1 Directory Structure (Dev B's files)

```
hx_engine/
├── app/
│   ├── main.py                    # Day 2
│   ├── config.py                  # Day 2
│   ├── dependencies.py            # Day 2
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── design.py              # Day 3
│   │   └── stream.py              # Day 3
│   └── core/
│       ├── session_store.py       # Day 2
│       ├── sse_manager.py         # Day 2
│       ├── pipeline_runner.py     # Day 3 (skeleton), Days 6–10 (wire steps)
│       └── prompts/
│           └── engineer_review.txt # Day 2 (placeholder)
├── tests/
│   ├── conftest.py                # Day 5
│   └── integration/
│       └── test_pipeline_steps_1_5.py  # Day 10
├── pyproject.toml                 # Day 1
├── Dockerfile                     # Day 4
├── .env.example                   # Day 4
└── .gitignore                     # Day 1
```

Plus at workspace root (or in /workspace/docker/):
```
docker-compose.yml                 # Day 4 (unified, replaces existing)
nginx.conf                         # Day 4
```

### 5.2 Day 1 — Project Scaffold

**File: `pyproject.toml`**

```toml
[project]
name = "hx-engine"
version = "0.1.0"
description = "ARKEN AI Heat Exchanger Design Engine"
requires-python = ">=3.11"

dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.6.0",
    "pydantic-settings>=2.1.0",
    "redis[hiredis]>=5.0.0",
    "httpx>=0.27.0",
    "sse-starlette>=2.0.0",
    "CoolProp>=6.6.0",
    "iapws>=1.5.0",
    "thermo>=0.3.0",
    "fluids>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.0",
    "httpx>=0.27.0",
    "fakeredis[aioredis]>=2.21",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

Note: `anthropic` SDK is NOT a dependency until Week 3 (AI is stubbed). `motor` not needed until Week 5+ (MongoDB for calibration). `supermemory` not needed until Week 7.

### 5.3 Day 2 — Infrastructure Files

**File: `app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class HXEngineSettings(BaseSettings):
    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # API
    host: str = "0.0.0.0"
    port: int = 8100
    debug: bool = False

    # Pipeline
    pipeline_orphan_threshold_seconds: int = 120

    # AI (stub values for now)
    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"

    # Internal auth
    hx_engine_secret: str = "dev-secret-change-me"
    backend_url: str = "http://localhost:8001"
    internal_secret: str = "dev-internal-secret"

    # Logging
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="HX_",
        case_sensitive=False,
        extra="ignore",
    )

settings = HXEngineSettings()
```

**File: `app/core/session_store.py`**

```python
"""
Redis session store for DesignState.
- save/load by session_id
- heartbeat() for orphan detection
- is_orphaned() check
- 24h TTL
"""
import json
import redis.asyncio as redis
from app.models.design_state import DesignState

SESSION_TTL_SECONDS = 86400  # 24h
HEARTBEAT_KEY_PREFIX = "hx:heartbeat:"

class SessionStore:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def save(self, session_id: str, state: DesignState) -> None:
        await self.redis.setex(
            f"hx:session:{session_id}",
            SESSION_TTL_SECONDS,
            state.model_dump_json()
        )

    async def load(self, session_id: str) -> DesignState | None:
        data = await self.redis.get(f"hx:session:{session_id}")
        if data is None:
            return None
        return DesignState.model_validate_json(data)

    async def heartbeat(self, session_id: str) -> None:
        await self.redis.setex(
            f"{HEARTBEAT_KEY_PREFIX}{session_id}",
            120,  # orphan threshold
            "alive"
        )

    async def is_orphaned(self, session_id: str) -> bool:
        return not await self.redis.exists(f"{HEARTBEAT_KEY_PREFIX}{session_id}")

    async def delete(self, session_id: str) -> None:
        await self.redis.delete(f"hx:session:{session_id}")
        await self.redis.delete(f"{HEARTBEAT_KEY_PREFIX}{session_id}")
```

**File: `app/core/sse_manager.py`**

```python
"""
SSE event manager.
- One asyncio.Queue per session
- stream_events() yields SSE data
- emit() pushes events to the session's queue
- Refcount cleanup when last listener disconnects
"""
import asyncio
import json
from typing import AsyncGenerator

class SSEManager:
    def __init__(self):
        self._queues: dict[str, asyncio.Queue] = {}
        self._futures: dict[str, asyncio.Future] = {}  # for ESCALATED user responses

    def get_queue(self, session_id: str) -> asyncio.Queue:
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue()
        return self._queues[session_id]

    async def emit(self, session_id: str, event: dict) -> None:
        queue = self.get_queue(session_id)
        await queue.put(event)

    async def stream_events(self, session_id: str) -> AsyncGenerator[dict, None]:
        queue = self.get_queue(session_id)
        while True:
            event = await queue.get()
            if event.get("event_type") == "design_complete":
                yield event
                break
            if event.get("event_type") == "stream_end":
                break
            yield event

    def create_user_response_future(self, session_id: str) -> asyncio.Future:
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._futures[session_id] = future
        return future

    def resolve_user_response(self, session_id: str, response: dict) -> None:
        future = self._futures.pop(session_id, None)
        if future and not future.done():
            future.set_result(response)

    def cleanup(self, session_id: str) -> None:
        self._queues.pop(session_id, None)
        self._futures.pop(session_id, None)
```

**File: `app/main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: connect to Redis
    import redis.asyncio as redis_lib
    app.state.redis = redis_lib.from_url(settings.redis_url)
    await app.state.redis.ping()

    from app.core.session_store import SessionStore
    from app.core.sse_manager import SSEManager
    app.state.session_store = SessionStore(app.state.redis)
    app.state.sse_manager = SSEManager()

    yield

    # Shutdown
    await app.state.redis.aclose()

app = FastAPI(title="ARKEN HX Engine", version="0.1.0", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "hx-engine", "version": "0.1.0"}

# Import routers after app creation
from app.routers import design, stream
app.include_router(design.router, prefix="/api/v1/hx")
app.include_router(stream.router, prefix="/api/v1/hx")
```

### 5.4 Day 3 — API Endpoints

**File: `app/routers/design.py`**

```python
"""
POST /api/v1/hx/design     → trigger design, return {session_id, stream_url, token}
GET  /api/v1/hx/design/{id}/status  → poll fallback
POST /api/v1/hx/design/{id}/respond → user response to ESCALATED step
"""
from fastapi import APIRouter, Request, BackgroundTasks
from pydantic import BaseModel

router = APIRouter()

class DesignRequest(BaseModel):
    raw_request: str
    user_id: str
    org_id: str | None = None
    mode: str = "design"  # "design" | "rating"

class DesignResponse(BaseModel):
    session_id: str
    stream_url: str   # relative path: /api/v1/hx/design/{id}/stream
    token: str        # JWT for stream auth (stub for now)

@router.post("/design")
async def start_design(req: DesignRequest, request: Request,
                       background_tasks: BackgroundTasks) -> DesignResponse:
    from app.models.design_state import DesignState
    state = DesignState(
        user_id=req.user_id,
        org_id=req.org_id,
        raw_request=req.raw_request,
        mode=req.mode,
    )
    session_id = state.session_id

    # Save initial state
    await request.app.state.session_store.save(session_id, state)

    # Run pipeline in background
    background_tasks.add_task(
        _run_pipeline, request.app, session_id, state
    )

    return DesignResponse(
        session_id=session_id,
        stream_url=f"/api/v1/hx/design/{session_id}/stream",
        token="stub-token",  # Real JWT in Week 6
    )

async def _run_pipeline(app, session_id: str, state):
    from app.core.pipeline_runner import PipelineRunner
    runner = PipelineRunner(
        session_store=app.state.session_store,
        sse_manager=app.state.sse_manager,
    )
    await runner.run(session_id, state)


@router.get("/design/{session_id}/status")
async def get_status(session_id: str, request: Request):
    state = await request.app.state.session_store.load(session_id)
    if state is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Session not found")
    return {
        "session_id": session_id,
        "current_step": state.current_step,
        "waiting_for_user": state.waiting_for_user,
        "step_records": state.step_records,
        "warnings": state.warnings,
    }


class UserResponse(BaseModel):
    type: str          # "accept" | "override" | "skip"
    values: dict | None = None

@router.post("/design/{session_id}/respond")
async def respond_to_escalation(session_id: str, response: UserResponse,
                                request: Request):
    request.app.state.sse_manager.resolve_user_response(
        session_id, response.model_dump()
    )
    return {"status": "received"}
```

**File: `app/routers/stream.py`**

```python
"""
GET /api/v1/hx/design/{id}/stream → SSE event stream
"""
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
import json

router = APIRouter()

@router.get("/design/{session_id}/stream")
async def stream_design(session_id: str, request: Request):
    sse_manager = request.app.state.sse_manager

    async def event_generator():
        async for event in sse_manager.stream_events(session_id):
            yield {
                "event": event.get("event_type", "message"),
                "data": json.dumps(event),
            }

    return EventSourceResponse(event_generator())
```

**File: `app/core/pipeline_runner.py`** (skeleton — wired incrementally Days 6–10)

```python
"""
Orchestrates the 16-step pipeline.
Week 1: skeleton that runs 0 steps.
Week 2: wires Steps 1–5.
"""
import logging
from datetime import datetime, timezone
from app.models.design_state import DesignState
from app.core.session_store import SessionStore
from app.core.sse_manager import SSEManager
from app.core.ai_engineer import AIEngineer
from app.core.exceptions import CalculationError, StepHardFailure

logger = logging.getLogger(__name__)

class PipelineRunner:
    def __init__(self, session_store: SessionStore, sse_manager: SSEManager):
        self.session_store = session_store
        self.sse_manager = sse_manager
        self.ai_engineer = AIEngineer()

    async def run(self, session_id: str, state: DesignState) -> DesignState:
        steps = self._get_steps()

        for step in steps:
            start_time = datetime.now(timezone.utc)

            # Emit step_started
            await self.sse_manager.emit(session_id, {
                "event_type": "step_started",
                "step_id": step.step_id,
                "step_name": step.step_name,
                "total_steps": 16,
            })

            try:
                # Layer 1: Execute
                result = step.execute(state)

                # Layer 2: Validate
                from app.core.validation_rules import check
                validation = check(step.step_id, result)

                # Layer 3: AI review (stub for now)
                if step._should_call_ai(state, result):
                    review = await self.ai_engineer.review(
                        step=step.step_id,
                        result=result,
                        design_state=state,
                    )
                else:
                    review = None

                # Layer 4: Update state
                state = self._apply_result(state, step, result, review)

                # Record
                duration_ms = int(
                    (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                )
                record = {
                    "step_id": step.step_id,
                    "step_name": step.step_name,
                    "result": result.model_dump(),
                    "review": review.model_dump() if review else None,
                    "timestamp": start_time.isoformat(),
                    "duration_ms": duration_ms,
                    "ai_called": step._should_call_ai(state, result),
                    "ai_decision": review.decision.value if review else None,
                }
                state = state.model_copy(update={
                    "step_records": state.step_records + [record],
                    "current_step": step.step_id,
                })

                # Emit step_approved (simplified — will use correct event type later)
                await self.sse_manager.emit(session_id, {
                    "event_type": "step_approved",
                    "step_id": step.step_id,
                    "step_name": step.step_name,
                    "confidence": review.confidence if review else 0.85,
                    "reasoning": review.reasoning if review else "",
                    "user_summary": review.user_summary if review else "",
                    "duration_ms": duration_ms,
                    "outputs": result.outputs,
                })

                # Save to Redis
                await self.session_store.save(session_id, state)
                await self.session_store.heartbeat(session_id)

            except (CalculationError, StepHardFailure) as e:
                logger.error(f"Pipeline error at step {step.step_id}: {e}")
                await self.sse_manager.emit(session_id, {
                    "event_type": "step_error",
                    "step_id": step.step_id,
                    "step_name": step.step_name,
                    "message": str(e),
                })
                break

        # Emit design_complete
        await self.sse_manager.emit(session_id, {
            "event_type": "design_complete",
            "session_id": session_id,
            "confidence_score": state.confidence_score,
            "summary": f"Steps 1-{state.current_step} completed.",
            "design_state": state.model_dump(),
        })

        return state

    def _get_steps(self) -> list:
        """
        Explicit step registry [Eng Review 2A].
        Import errors crash loudly — never silently skip a step.
        Add steps here as they're built in Week 2.
        """
        from app.steps.step_01_requirements import Step01Requirements
        from app.steps.step_02_heat_duty import Step02HeatDuty
        from app.steps.step_03_fluid_props import Step03FluidProperties
        from app.steps.step_04_tema_geometry import Step04TEMAGeometry
        from app.steps.step_05_lmtd import Step05LMTD

        return [
            Step01Requirements(),
            Step02HeatDuty(),
            Step03FluidProperties(),
            Step04TEMAGeometry(),
            Step05LMTD(),
        ]

    def _apply_result(self, state, step, result, review):
        """Apply step outputs to DesignState."""
        update = {}
        for key, value in result.outputs.items():
            if hasattr(state, key):
                update[key] = value
        if update:
            state = state.model_copy(update=update)
        return state
```

### 5.5 Day 4 — Docker + nginx

See [Section 11](#11-docker--nginx-setup) for full docker-compose.yml and nginx.conf.

### 5.6 Day 5 — Test Fixtures

**File: `tests/conftest.py`**

```python
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from app.models.design_state import DesignState, FluidProperties, GeometrySpec

@pytest.fixture
def sample_design_state():
    """A realistic DesignState for testing Steps 1-5."""
    return DesignState(
        user_id="test-user",
        raw_request="Design a heat exchanger for cooling 50 kg/s of crude oil "
                    "from 150°C to 90°C using cooling water at 30°C",
        T_hot_in_C=150.0,
        T_hot_out_C=90.0,
        T_cold_in_C=30.0,
        m_dot_hot_kg_s=50.0,
        hot_fluid_name="crude_oil",
        cold_fluid_name="water",
    )

@pytest.fixture
def sample_water_properties():
    return FluidProperties(
        name="water",
        density_kg_m3=995.7,
        viscosity_Pa_s=0.000798,
        cp_J_kgK=4181.0,
        k_W_mK=0.615,
        Pr=5.42,
        phase="liquid",
        mean_temp_C=35.0,
    )

@pytest.fixture
def sample_geometry():
    return GeometrySpec(
        shell_diameter_m=0.5906,
        tube_od_m=0.01905,
        tube_id_m=0.01575,
        tube_length_m=4.877,
        baffle_spacing_m=0.127,
        pitch_ratio=1.333,
        n_tubes=324,
        n_passes=2,
        pitch_layout="triangular",
        baffle_cut=0.25,
    )

@pytest.fixture
def mock_session_store():
    store = AsyncMock()
    store.save = AsyncMock()
    store.load = AsyncMock()
    store.heartbeat = AsyncMock()
    return store

@pytest.fixture
def mock_sse_manager():
    from app.core.sse_manager import SSEManager
    return SSEManager()
```

---

## 6. Dev C — Frontend + Backend Integration

### 6.1 Backend Changes

**File: `backend/app/config.py`** — Add:
```python
# HX Engine
hx_engine_url: str = Field(
    default="http://localhost:8100",
    description="HX Engine microservice URL"
)
hx_engine_secret: str = Field(
    default="dev-secret-change-me",
    description="Shared secret for HX Engine internal auth"
)
```

**File: `backend/engines.yaml`** — CREATE:
```yaml
engines:
  hx_engine:
    name: "Heat Exchanger Design Engine"
    base_url: "${HX_ENGINE_URL:-http://hx-engine:8100}"
    enabled: true
    health_endpoint: "/health"
    tools_endpoint: "/api/v1/hx/tools"
    tools:
      - name: hx_design
        description: "Run full 16-step heat exchanger design"
        endpoint: "/api/v1/hx/design"
        method: POST
        streaming: true
      - name: hx_get_fluid_properties
        description: "Look up fluid properties at a temperature"
        endpoint: "/api/v1/hx/properties"
        method: POST
        streaming: false
      - name: hx_suggest_geometry
        description: "Suggest initial TEMA type and geometry"
        endpoint: "/api/v1/hx/geometry"
        method: POST
        streaming: false
```

**File: `backend/app/core/engine_client.py`** — CREATE (stub for Week 1, full impl Week 6):

```python
"""
HTTP client for HX Engine microservice.
Stub implementation — returns mock responses.
Full implementation in Week 6 when backend orchestration is wired.
"""
import httpx
import logging
from app.config import settings

logger = logging.getLogger(__name__)

class HXEngineClient:
    def __init__(self):
        self.base_url = settings.hx_engine_url
        self._client: httpx.AsyncClient | None = None

    async def connect(self):
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        # Verify connectivity
        try:
            resp = await self._client.get("/health")
            resp.raise_for_status()
            logger.info(f"HX Engine connected: {self.base_url}")
        except Exception as e:
            logger.warning(f"HX Engine not available: {e}")

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def start_design(self, raw_request: str, user_id: str,
                           org_id: str = None) -> dict:
        resp = await self._client.post("/api/v1/hx/design", json={
            "raw_request": raw_request,
            "user_id": user_id,
            "org_id": org_id,
        })
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        if self._client:
            await self._client.aclose()
```

**File: `backend/app/dependencies.py`** — Add engine registry:

```python
# Add alongside existing dependencies:

_engine_client: "HXEngineClient | None" = None

async def get_engine_client():
    global _engine_client
    if _engine_client is None:
        from app.core.engine_client import HXEngineClient
        _engine_client = HXEngineClient()
        await _engine_client.connect()
    return _engine_client

async def close_engine_client():
    global _engine_client
    if _engine_client:
        await _engine_client.close()
        _engine_client = None
```

### 6.2 Frontend Changes

**File: `frontend/src/types/hxEvents.js`** — CREATE:

```javascript
/**
 * HX Engine SSE event types.
 * Mirrors hx_engine/app/models/sse_events.py
 */

export const HX_EVENT_TYPES = {
  STEP_STARTED: "step_started",
  STEP_APPROVED: "step_approved",
  STEP_CORRECTED: "step_corrected",
  STEP_WARNING: "step_warning",
  STEP_ESCALATED: "step_escalated",
  STEP_ERROR: "step_error",
  ITERATION_PROGRESS: "iteration_progress",
  DESIGN_COMPLETE: "design_complete",
};

// Step states for StepCard rendering
export const STEP_STATES = {
  PENDING: "PENDING",
  RUNNING: "RUNNING",
  APPROVED: "APPROVED",
  CORRECTED: "CORRECTED",
  WARNING: "WARNING",
  ESCALATED: "ESCALATED",
  ERROR: "ERROR",
};

// Map SSE event_type → StepCard state
export function eventToStepState(eventType) {
  switch (eventType) {
    case HX_EVENT_TYPES.STEP_STARTED: return STEP_STATES.RUNNING;
    case HX_EVENT_TYPES.STEP_APPROVED: return STEP_STATES.APPROVED;
    case HX_EVENT_TYPES.STEP_CORRECTED: return STEP_STATES.CORRECTED;
    case HX_EVENT_TYPES.STEP_WARNING: return STEP_STATES.WARNING;
    case HX_EVENT_TYPES.STEP_ESCALATED: return STEP_STATES.ESCALATED;
    case HX_EVENT_TYPES.STEP_ERROR: return STEP_STATES.ERROR;
    default: return STEP_STATES.PENDING;
  }
}

// All 16 step names for rendering pending cards
export const STEP_NAMES = [
  "Process Requirements",
  "Heat Duty",
  "Fluid Properties",
  "TEMA Type & Geometry",
  "LMTD & F-Factor",
  "Initial U & Size",
  "Tube-Side h",
  "Shell-Side h (Bell-Delaware)",
  "Overall U & Resistances",
  "Pressure Drops",
  "Area & Overdesign",
  "Convergence Loop",
  "Vibration Check",
  "Mechanical Design",
  "Cost Estimate",
  "Final Validation",
];
```

**File: `frontend/src/hooks/useHXStream.js`** — CREATE:

```javascript
/**
 * Hook to manage HX Engine SSE stream.
 *
 * Usage:
 *   const { steps, isRunning, error, startDesign } = useHXStream();
 *
 * Flow:
 *   1. POST /api/chat → backend → returns stream_url
 *   2. Connect EventSource to stream_url (via nginx proxy)
 *   3. Receive step_started/approved/corrected/warning/escalated/error events
 *   4. Update steps array → StepCard components re-render
 *   5. design_complete → close stream
 */
import { useState, useRef, useCallback } from "react";
import { HX_EVENT_TYPES, eventToStepState, STEP_NAMES } from "../types/hxEvents";

export function useHXStream() {
  const [steps, setSteps] = useState(
    STEP_NAMES.map((name, i) => ({
      stepId: i + 1,
      stepName: name,
      state: "PENDING",
      data: null,
    }))
  );
  const [isRunning, setIsRunning] = useState(false);
  const [designResult, setDesignResult] = useState(null);
  const [error, setError] = useState(null);
  const eventSourceRef = useRef(null);

  const connectStream = useCallback((streamUrl) => {
    // Close any existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    setIsRunning(true);
    setError(null);

    const fullUrl = `${window.location.origin}${streamUrl}`;
    const es = new EventSource(fullUrl);
    eventSourceRef.current = es;

    // Listen for all HX event types
    Object.values(HX_EVENT_TYPES).forEach((eventType) => {
      es.addEventListener(eventType, (e) => {
        try {
          const data = JSON.parse(e.data);
          handleEvent(eventType, data);
        } catch (err) {
          console.error("Failed to parse SSE event:", err);
        }
      });
    });

    es.onerror = (err) => {
      console.error("SSE connection error:", err);
      // Fallback to polling after 3s
      setTimeout(() => pollStatus(streamUrl), 3000);
    };

    function handleEvent(eventType, data) {
      const stepId = data.step_id;

      if (eventType === HX_EVENT_TYPES.DESIGN_COMPLETE) {
        setDesignResult(data);
        setIsRunning(false);
        es.close();
        return;
      }

      if (!stepId) return;

      setSteps((prev) =>
        prev.map((step) =>
          step.stepId === stepId
            ? {
                ...step,
                state: eventToStepState(eventType),
                data: data,
              }
            : step
        )
      );
    }

    async function pollStatus(url) {
      // Extract session_id from stream URL
      const match = url.match(/design\/(.+)\/stream/);
      if (!match) return;
      const statusUrl = `/api/v1/hx/design/${match[1]}/status`;
      try {
        const resp = await fetch(statusUrl);
        const status = await resp.json();
        // Update steps from status.step_records
        // ... (poll fallback logic)
      } catch (e) {
        setError("Connection lost. Please refresh.");
      }
    }
  }, []);

  const reset = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
    setSteps(
      STEP_NAMES.map((name, i) => ({
        stepId: i + 1,
        stepName: name,
        state: "PENDING",
        data: null,
      }))
    );
    setIsRunning(false);
    setDesignResult(null);
    setError(null);
  }, []);

  const respondToEscalation = useCallback(async (sessionId, response) => {
    await fetch(`/api/v1/hx/design/${sessionId}/respond`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(response),
    });
  }, []);

  return {
    steps,
    isRunning,
    designResult,
    error,
    connectStream,
    reset,
    respondToEscalation,
  };
}
```

**Frontend component wiring (Day 3+):**

Update `HXPanel.jsx` to use `useHXStream`:

```jsx
// In HXPanel.jsx — wire to live SSE data
import { useHXStream } from "../../hooks/useHXStream";

export default function HXPanel({ streamUrl }) {
  const { steps, isRunning, designResult, error, connectStream } = useHXStream();

  useEffect(() => {
    if (streamUrl) {
      connectStream(streamUrl);
    }
  }, [streamUrl, connectStream]);

  return (
    <div className="hx-panel">
      {isRunning && <ProgressBar steps={steps} />}
      <div className="step-cards">
        {steps.map((step) => (
          <StepCard key={step.stepId} {...step} />
        ))}
      </div>
      {designResult && <DesignSummary result={designResult} />}
      {error && <div className="error-banner">{error}</div>}
    </div>
  );
}
```

Update `ChatContainer.jsx` to trigger HX design and pass `streamUrl` to `HXPanel`:

```jsx
// When backend returns a stream_url in its response,
// pass it up to Layout.jsx which passes it to HXPanel:

// In the chat submit handler:
const response = await fetch("/api/chat", {
  method: "POST",
  body: JSON.stringify({ message, conversation_id }),
});
const data = await response.json();

// If backend triggered HX design, it returns stream_url
if (data.stream_url) {
  onStreamUrl(data.stream_url);  // prop callback to Layout
}
```

---

## 7. File Specifications

### Complete File List — All Three Services

```
CREATED FILES (new):
────────────────────
hx_engine/                              # NEW REPO
├── app/__init__.py
├── app/models/__init__.py
├── app/models/design_state.py          # Dev A, Day 1
├── app/models/step_result.py           # Dev A, Day 1
├── app/models/sse_events.py            # Dev A, Day 1
├── app/steps/__init__.py               # Dev A, Day 1
├── app/steps/base.py                   # Dev A, Day 2
├── app/steps/step_01_requirements.py   # Dev A, Day 6
├── app/steps/step_02_heat_duty.py      # Dev A, Day 7
├── app/steps/step_03_fluid_props.py    # Dev A, Day 8
├── app/steps/step_04_tema_geometry.py  # Dev A, Day 9
├── app/steps/step_05_lmtd.py          # Dev A, Day 10
├── app/core/__init__.py
├── app/core/ai_engineer.py             # Dev A, Day 2 (stub)
├── app/core/validation_rules.py        # Dev A, Day 2
├── app/core/exceptions.py              # Dev A, Day 2
├── app/core/session_store.py           # Dev B, Day 2
├── app/core/sse_manager.py             # Dev B, Day 2
├── app/core/pipeline_runner.py         # Dev B, Day 3
├── app/core/prompts/engineer_review.txt # Dev B, Day 2
├── app/routers/__init__.py
├── app/routers/design.py               # Dev B, Day 3
├── app/routers/stream.py               # Dev B, Day 3
├── app/adapters/__init__.py
├── app/adapters/thermo_adapter.py      # Dev A, Day 4
├── app/adapters/units_adapter.py       # Dev A, Day 4
├── app/correlations/__init__.py
├── app/correlations/lmtd.py            # Dev A, Day 5
├── app/data/__init__.py
├── app/data/tema_tables.py             # Dev A, Day 5
├── app/data/fouling_factors.py         # Dev A, Day 5
├── app/data/u_assumptions.py           # Dev A, Day 5
├── app/config.py                       # Dev B, Day 2
├── app/dependencies.py                 # Dev B, Day 2
├── app/main.py                         # Dev B, Day 2
├── tests/__init__.py
├── tests/conftest.py                   # Dev B, Day 5
├── tests/unit/models/test_design_state.py    # Dev A, Day 3
├── tests/unit/steps/test_step_protocol.py    # Dev A, Day 3
├── tests/unit/steps/test_step_01.py          # Dev A, Day 6
├── tests/unit/steps/test_step_02.py          # Dev A, Day 7
├── tests/unit/steps/test_step_03.py          # Dev A, Day 8
├── tests/unit/steps/test_step_04.py          # Dev A, Day 9
├── tests/unit/steps/test_step_05.py          # Dev A, Day 10
├── tests/unit/correlations/test_lmtd.py      # Dev A, Day 5
├── tests/unit/adapters/test_thermo_adapter.py # Dev A, Day 4
├── tests/integration/test_pipeline_steps_1_5.py  # Dev B, Day 10
├── pyproject.toml                      # Dev B, Day 1
├── Dockerfile                          # Dev B, Day 4
├── .env.example                        # Dev B, Day 4
└── .gitignore                          # Dev B, Day 1

backend/                                # EXISTING REPO
├── app/config.py                       # Dev C, Day 2 (MODIFY: add hx_engine_url)
├── app/dependencies.py                 # Dev C, Day 2 (MODIFY: add get_engine_client)
├── app/core/engine_client.py           # Dev C, Day 1 (CREATE)
├── engines.yaml                        # Dev C, Day 2 (CREATE)
└── .env                                # Dev C (add HX_ENGINE_URL)

frontend/                               # EXISTING REPO
├── src/types/hxEvents.js               # Dev C, Day 2 (CREATE)
├── src/hooks/useHXStream.js            # Dev C, Day 1-3 (CREATE)
├── src/components/hx/HXPanel.jsx       # Dev C, Day 3 (MODIFY: wire to SSE)
├── src/components/hx/StepCard.jsx      # Dev C, Day 3 (MODIFY: wire to live data)
├── src/components/hx/ProgressBar.jsx   # Dev C, Day 3 (MODIFY: wire to live data)
├── src/components/chat/ChatContainer.jsx # Dev C, Day 4 (MODIFY: trigger HX design)
└── src/components/chat/MessageBubble.jsx # Dev C, Day 4 (MODIFY: terminal reskin)

workspace root:
├── docker-compose.yml                  # Dev B, Day 4 (CREATE or replace existing)
└── nginx.conf                          # Dev B, Day 4 (CREATE)
```

---

## 8. Data Files (Steps 1–5)

### 8.1 `data/tema_tables.py`

```python
"""
TEMA tube count tables.
Maps (shell_id_inch, tube_od_inch, pitch_layout, n_passes) → n_tubes.
40+ shell IDs from 8" to 60".

Source: TEMA Standards, 10th Edition, Table D-7
"""

# Standard shell inner diameters (inches → meters)
STANDARD_SHELL_IDS = {
    8: 0.2032, 10: 0.2540, 12: 0.3048, 13.25: 0.3366,
    15.25: 0.3874, 17.25: 0.4382, 19.25: 0.4890,
    21.25: 0.5398, 23.25: 0.5906, 25: 0.6350,
    27: 0.6858, 29: 0.7366, 31: 0.7874,
    33: 0.8382, 35: 0.8890, 37: 0.9398,
    39: 0.9906, 42: 1.0668, 45: 1.1430,
    48: 1.2192, 54: 1.3716, 60: 1.5240,
}

# Tube count table: (shell_id_inch, n_passes) → n_tubes
# For 3/4" (19.05mm) OD tubes, triangular pitch, 1.25 ratio
TUBE_COUNTS_19MM_TRI = {
    (8, 1): 32, (8, 2): 26, (8, 4): 20,
    (10, 1): 56, (10, 2): 52, (10, 4): 40,
    (12, 1): 92, (12, 2): 82, (12, 4): 68,
    (13.25, 1): 110, (13.25, 2): 106, (13.25, 4): 90,
    (15.25, 1): 152, (15.25, 2): 142, (15.25, 4): 124,
    (17.25, 1): 204, (17.25, 2): 188, (17.25, 4): 164,
    (19.25, 1): 260, (19.25, 2): 244, (19.25, 4): 220,
    (21.25, 1): 316, (21.25, 2): 302, (21.25, 4): 272,
    (23.25, 1): 384, (23.25, 2): 360, (23.25, 4): 324,
    (25, 1): 436, (25, 2): 416, (25, 4): 380,
    (27, 1): 510, (27, 2): 486, (27, 4): 446,
    (29, 1): 596, (29, 2): 562, (29, 4): 524,
    (31, 1): 684, (31, 2): 650, (31, 4): 604,
    (33, 1): 784, (33, 2): 744, (33, 4): 696,
    (35, 1): 880, (35, 2): 838, (35, 4): 788,
    (37, 1): 988, (37, 2): 942, (37, 4): 886,
    (39, 1): 1100, (39, 2): 1050, (39, 4): 990,
}

def lookup_tube_count(shell_diameter_m: float, n_passes: int,
                      tube_od_m: float = 0.01905,
                      pitch_layout: str = "triangular") -> tuple[int, float]:
    """
    Returns (n_tubes, actual_shell_diameter_m).
    Selects the smallest standard shell that fits the required tube count.
    """
    ...

def shell_diameter_for_tubes(n_tubes_required: int, n_passes: int,
                             tube_od_m: float = 0.01905) -> float:
    """Find smallest standard shell that accommodates n_tubes."""
    ...
```

### 8.2 `data/fouling_factors.py`

```python
"""
Fouling resistance values by fluid type (m²K/W).
Source: TEMA Standards + Serth Table 3.14
"""

FOULING_FACTORS = {
    # Clean fluids
    "water": 0.000176,              # clean cooling water
    "cooling_water": 0.000176,
    "boiler_feedwater": 0.000088,
    "steam": 0.000088,

    # Hydrocarbons
    "crude_oil": 0.000352,
    "light_oil": 0.000176,
    "heavy_oil": 0.000528,
    "gasoline": 0.000176,
    "kerosene": 0.000176,
    "diesel": 0.000264,
    "naphtha": 0.000176,

    # Gases
    "air": 0.000176,
    "nitrogen": 0.000088,
    "hydrogen": 0.000088,

    # Process fluids
    "methanol": 0.000176,
    "ethanol": 0.000176,
    "ethylene_glycol": 0.000176,
    "brine": 0.000264,

    # Default
    "unknown": 0.000352,
}

def get_fouling_factor(fluid_name: str) -> float:
    """Look up fouling factor. Returns default if not found."""
    return FOULING_FACTORS.get(fluid_name.lower().replace(" ", "_"),
                               FOULING_FACTORS["unknown"])
```

### 8.3 `data/u_assumptions.py`

```python
"""
Typical overall U ranges by fluid pair (W/m²K).
Used in Step 6 for initial area estimate.
Source: Serth Table 3.5, Kern Table 8
"""

# (hot_fluid_type, cold_fluid_type) → (U_low, U_high, U_typical)
TYPICAL_U_RANGES = {
    ("water", "water"): (800, 1500, 1000),
    ("crude_oil", "water"): (300, 500, 380),
    ("light_oil", "water"): (350, 700, 500),
    ("heavy_oil", "water"): (50, 300, 150),
    ("gas", "water"): (15, 250, 100),
    ("steam", "water"): (1000, 3500, 2000),
    ("organic", "water"): (250, 750, 500),
    ("organic", "organic"): (100, 400, 250),
    ("gas", "gas"): (10, 50, 25),
    ("water", "brine"): (600, 1200, 800),
}

def get_typical_U(hot_fluid: str, cold_fluid: str) -> tuple[float, float, float]:
    """Returns (U_low, U_high, U_typical) for a fluid pair."""
    ...
```

---

## 9. Test Requirements

### 9.1 Week 1 Tests (must pass before Week 2)

**`tests/unit/models/test_design_state.py`** — 12 CG3A validator tests:

| # | Test | Assertion |
|---|------|-----------|
| 1 | `test_baffle_spacing_valid` | 0.127m accepted |
| 2 | `test_baffle_spacing_below_min` | 0.02m raises ValueError |
| 3 | `test_baffle_spacing_above_max` | 3.0m raises ValueError |
| 4 | `test_baffle_spacing_none` | None accepted (optional) |
| 5 | `test_pitch_ratio_valid` | 1.333 accepted |
| 6 | `test_pitch_ratio_below_min` | 1.1 raises ValueError |
| 7 | `test_pitch_ratio_above_max` | 1.6 raises ValueError |
| 8 | `test_shell_diameter_valid` | 0.59m accepted |
| 9 | `test_shell_diameter_below_min` | 0.01m raises ValueError |
| 10 | `test_tube_od_valid` | 0.019m accepted |
| 11 | `test_tube_od_below_min` | 0.001m raises ValueError |
| 12 | `test_default_factory_isolation` | `DesignState().step_records is not DesignState().step_records` |

**`tests/unit/steps/test_step_protocol.py`:**
- BaseStep subclass with all required attributes → isinstance(step, StepProtocol) is True
- Class missing execute() → not a StepProtocol

### 9.2 Week 2 Tests

**`tests/unit/correlations/test_lmtd.py`** — 6 cases:
1. Normal counter-current: known values → LMTD within 0.1%
2. ΔT1 == ΔT2: returns arithmetic mean
3. Temperature cross: raises ValueError
4. R = 1.0: F-factor handles special case (no NaN)
5. F < 0.75: detected correctly
6. Very small LMTD (< 3°C): computation succeeds

**`tests/unit/adapters/test_thermo_adapter.py`:**
- Water at 25°C: density within 1% of 997.05 kg/m³, Cp within 1% of 4181 J/kgK
- Unknown fluid: raises CalculationError

**`tests/unit/steps/test_step_02.py`:**
- Normal case: Q matches manual calc
- Energy balance: |Q_hot - Q_cold|/Q_hot < 1%
- Q = 0 (identical temps): raises error
- Very small ΔT: warns

**`tests/unit/steps/test_step_05.py`:**
- F > 0.85: AI not triggered
- F = 0.78: AI triggered (CONDITIONAL)
- F < 0.75: HARD FAIL (validation error)
- R = 1.0: computation succeeds

**`tests/integration/test_pipeline_steps_1_5.py`:**
- Input: crude oil cooling request (50 kg/s, 150→90°C, water at 30°C)
- Steps 1–5 run with mock AI (always PROCEED)
- Assert: DesignState has Q_W, LMTD_C, F_factor, shell_fluid, tube_fluid, geometry, tema_type populated
- Assert: 5 step_records in state
- Assert: 5 SSE events emitted (one step_approved per step) + 5 step_started + 1 design_complete

---

## 10. Integration Checkpoints

### Checkpoint 1 — End of Week 1 (Day 5)

```
PASS CRITERIA:
  [  ] docker-compose up starts all services (hx-engine, backend, frontend, redis, mongodb, nginx)
  [  ] GET http://localhost/api/v1/hx/health → 200 {"status": "ok"} (via nginx)
  [  ] GET http://localhost:8100/health → 200 (direct)
  [  ] GET http://localhost:8001/health → 200 (backend)
  [  ] 12 CG3A validator tests pass
  [  ] StepProtocol compliance test passes
  [  ] POST /api/v1/hx/design → returns session_id + stream_url
  [  ] GET /api/v1/hx/design/{id}/stream → SSE connection opens (returns design_complete immediately since no steps)
```

### Checkpoint 2 — End of Week 2 (Day 10)

```
PASS CRITERIA:
  [  ] Steps 1–5 run with mock AI for crude oil/water case
  [  ] DesignState has all Step 1–5 fields populated
  [  ] LMTD test: known values match within 0.1%
  [  ] Thermo adapter: water at 25°C matches NIST within 1%
  [  ] SSE events stream to frontend: 5 step_started + 5 step_approved + design_complete
  [  ] Frontend StepCards update from PENDING → RUNNING → APPROVED in real time
  [  ] ProgressBar shows "Step N/16" correctly
  [  ] User types "Design a heat exchanger..." → full Steps 1–5 execute → results visible in HXPanel
  [  ] All unit tests pass (pytest tests/unit/ -v)
  [  ] Integration test passes (pytest tests/integration/ -v)
```

---

## 11. Docker & nginx Setup

### 11.1 `docker-compose.yml` (at /workspace root or /workspace/docker/)

```yaml
version: "3.8"

services:
  # ── MongoDB ──
  mongodb:
    image: mongo:7.0
    container_name: arken-mongodb
    ports:
      - "127.0.0.1:27017:27017"
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGODB_ROOT_USERNAME:-arken}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGODB_ROOT_PASSWORD:-arken_dev}
    volumes:
      - mongo_data:/data/db
    networks:
      - arken-network
    healthcheck:
      test: echo 'db.runCommand("ping").ok' | mongosh localhost:27017/test --quiet
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  # ── Redis (AOF persistence) ──
  redis:
    image: redis:7-alpine
    container_name: arken-redis
    ports:
      - "127.0.0.1:6379:6379"
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD:-arken_dev}
    volumes:
      - redis_data:/data
    networks:
      - arken-network
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD:-arken_dev}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 5s

  # ── HX Engine (port 8100) ──
  hx-engine:
    build:
      context: ./hx_engine
      dockerfile: Dockerfile
    container_name: arken-hx-engine
    ports:
      - "127.0.0.1:8100:8100"
    env_file: .env
    environment:
      HX_REDIS_URL: redis://:${REDIS_PASSWORD:-arken_dev}@redis:6379/0
      HX_PORT: 8100
      HX_BACKEND_URL: http://backend:8001
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - arken-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8100/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  # ── Backend (port 8001) ──
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: arken-backend
    ports:
      - "127.0.0.1:8001:8001"
    env_file:
      - ./backend/.env
    environment:
      HX_ENGINE_URL: http://hx-engine:8100
    depends_on:
      mongodb:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - arken-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  # ── nginx reverse proxy (port 80) ──
  nginx:
    image: nginx:alpine
    container_name: arken-nginx
    ports:
      - "80:80"
    extra_hosts:
      - "host.docker.internal:host-gateway"  # Linux compat [Eng Review 3A]
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - hx-engine
      - backend
    networks:
      - arken-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 5s

volumes:
  mongo_data:
    name: arken_mongo_data
  redis_data:
    name: arken_redis_data

networks:
  arken-network:
    name: arken_network
    driver: bridge
```

### 11.2 `nginx.conf`

```nginx
events {
    worker_connections 1024;
}

http {
    upstream hx_engine {
        server hx-engine:8100;
    }

    upstream backend {
        server backend:8001;
    }

    server {
        listen 80;

        # HX Engine routes — MUST come before /api catch-all
        location /api/v1/hx/ {
            proxy_pass http://hx_engine;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;

            # SSE support
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 300s;
            proxy_set_header Connection '';
            chunked_transfer_encoding off;
        }

        # Backend API routes
        location /api/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        # Health check (returns nginx status)
        location /health {
            return 200 '{"status":"ok","service":"nginx"}';
            add_header Content-Type application/json;
        }

        # Frontend static files (dev: proxy to Vite dev server)
        location / {
            proxy_pass http://host.docker.internal:5173;
            proxy_set_header Host $host;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
}
```

### 11.3 HX Engine `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System deps for CoolProp
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
```

### 11.4 `.env.example`

```bash
# HX Engine
HX_REDIS_URL=redis://:arken_dev@localhost:6379/0
HX_PORT=8100
HX_ANTHROPIC_API_KEY=sk-ant-...  # not needed until Week 3
HX_HX_ENGINE_SECRET=change-me-in-production
HX_BACKEND_URL=http://localhost:8001
HX_INTERNAL_SECRET=change-me-in-production

# Redis
REDIS_PASSWORD=arken_dev

# MongoDB
MONGODB_ROOT_USERNAME=arken
MONGODB_ROOT_PASSWORD=arken_dev
```

---

## 12. NOT in Scope

These items were considered and explicitly deferred:

| Item | Rationale |
|------|-----------|
| Steps 6–16 | Out of scope — this plan covers Steps 1–5 only |
| Bell-Delaware correlations | Needed for Step 8 (Week 3) |
| Real AI engineer (Anthropic API) | Stubbed — real implementation in Week 3 |
| Supermemory integration | Week 7 |
| Autoresearch / Loop 3 | Post-beta |
| Auth (JWT, login, users) | Week 6 |
| HTRI Comparison workflow | Week 5 |
| Extraction from calculation_engine/ | Explicitly excluded per user request |
| /btw context injection | Deferred post-beta |
| PDF export | Post-beta |
| Rating mode implementation | Steps 1–5 focus on design mode; rating shares steps but skips Step 4 geometry selection |
| Supermemory calls in steps | Stubbed as empty strings; real wiring Week 7 |
| Stream token JWT security | Stub token for now; real JWT in Week 6 |
| Frontend responsive/mobile | Desktop-first. Mobile: auto-tab-switch + badge only (see Appendix C, 5A) |
| CI/CD pipeline | Post-Week-1 |

---

## Appendix: Quick Reference

### How to Run Locally (without Docker)

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: HX Engine
cd /workspace/hx_engine
pip install -e ".[dev]"
uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload

# Terminal 3: Backend
cd /workspace/backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Terminal 4: Frontend
cd /workspace/frontend
npm run dev

# Terminal 5: Run tests
cd /workspace/hx_engine
pytest tests/ -v
```

### Key URLs

| URL | Service |
|-----|---------|
| `http://localhost:5173` | Frontend (Vite dev) |
| `http://localhost:8001/health` | Backend |
| `http://localhost:8100/health` | HX Engine |
| `http://localhost/api/v1/hx/health` | HX Engine via nginx |
| `http://localhost/api/v1/hx/design` | Design endpoint via nginx |

### Git Workflow

Each developer works on their own branch:
```
main
├── feat/hx-core-models       (Dev A)
├── feat/hx-infrastructure     (Dev B)
└── feat/hx-frontend-backend   (Dev C)
```

Merge order: Dev A first (contracts), then Dev B (infra), then Dev C (integration).

---

*Plan generated 2026-03-21. Source: ARKEN_MASTER_PLAN.md v8.0*

---

## Appendix C: Design Review Amendments (2026-03-21)

### Resolved Design Decisions

| # | Issue | Resolution |
|---|-------|-----------|
| 1A | HXPanel "dead zone" between chat submit and first SSE event | Immediate skeleton: show 16 PENDING StepCards + ProgressBar "Step 0/16 — Initializing..." with shimmer instantly when design is triggered, before SSE connects |
| 2A | ESCALATED state — user doesn't know pipeline is paused | Amber attention bar in ProgressBar: "⚠ Waiting for input — Step N". ESCALATED StepCard auto-scrolls into view and pulses border once |
| 3A | Pipeline error state — ProgressBar stays blue, no recovery action | Red ProgressBar: "✗ Pipeline stopped — Step N". Remaining steps grey out. "Start new design" button appears below the error card |
| 4A | MessageBubble "terminal reskin" undefined | Terminal-style: 2px radius (no rounded pills), full-width both roles. User messages: left amber border. Assistant: left blue border. Inter for text, JetBrains Mono for values |
| 5A | Mobile tab — user doesn't know pipeline started | Auto-switch to HX Pipeline tab on mobile when design triggers. Badge (●N) on HX tab when events arrive while on Chat tab. Auto-switch on ESCALATED |
| 6A | Chat panel silent after triggering design | System message (not a bubble): "▶ Design pipeline started — follow progress →". Monospace, muted, thin border. Chat stays open for conversation during pipeline |

### Design Spec: HXPanel State Machine

```
                        ┌─────────────────┐
                        │      IDLE       │
                        │ WelcomeScreen   │
                        │ + "Run Demo"    │
                        └────────┬────────┘
                                 │ user triggers design
                                 ▼
                        ┌─────────────────┐
                        │   INITIALIZING  │
                        │ 16 PENDING cards│
                        │ "Step 0/16"     │
                        │ shimmer bar     │
                        └────────┬────────┘
                                 │ first step_started SSE
                                 ▼
                        ┌─────────────────┐
                        │    RUNNING      │◄──────────────┐
                        │ Steps flip:     │               │
                        │ PENDING→RUNNING │               │
                        │ →APPROVED       │               │
                        └───┬──────┬──────┘               │
                            │      │                      │
                  step_error│      │step_escalated        │ user responds
                            ▼      ▼                      │
                   ┌────────────┐  ┌──────────────┐       │
                   │   ERROR    │  │  ESCALATED   │───────┘
                   │ Red bar    │  │ Amber bar    │
                   │ Grey steps │  │ Pulse card   │
                   │ [New design│  │ Inline input │
                   │  button]   │  │ Auto-scroll  │
                   └────────────┘  └──────────────┘

                                 │ design_complete
                                 ▼
                        ┌─────────────────┐
                        │   COMPLETE      │
                        │ DesignSummary   │
                        │ All steps shown │
                        │ [New design btn]│
                        └─────────────────┘
```

### Design Spec: ProgressBar States

```
STATE          │ BAR COLOR │ TEXT                           │ ANIMATION
───────────────┼───────────┼────────────────────────────────┼──────────────
INITIALIZING   │ blue      │ "Step 0/16 — Initializing..."  │ shimmer
RUNNING        │ blue      │ "Step N/16 — {step_name}"      │ stripe
ESCALATED      │ amber     │ "⚠ Waiting for input — Step N" │ none (paused)
RESUMING       │ blue      │ "Resuming — Step N"            │ stripe
ERROR          │ red       │ "✗ Pipeline stopped — Step N"  │ none
COMPLETE       │ green     │ "✓ 16/16 — Design complete"    │ none
```

### Design Spec: MessageBubble Terminal Reskin

```
BEFORE (current):                AFTER (terminal reskin):
╭─────────────────────────╮     ┌─────────────────────────┐
│ User message text in a  │     │ █ User message text     │
│ rounded pill, right-    │     │ █ full-width, 2px       │
│ aligned, 16px radius    │     │ █ radius, amber left    │
╰─────────────────────────╯     │ █ border accent         │
                                └─────────────────────────┘
No background for assistant:    ┌─────────────────────────┐
I'll design that heat           │ ┃ I'll design that heat │
exchanger for you.              │ ┃ exchanger for you.    │
                                │ ┃ Starting pipeline...  │
                                └─────────────────────────┘
                                  (blue left border, 2px radius)

System message (new type):
┌─────────────────────────┐
│ ▶ Design pipeline       │  (monospace, --color-text-muted,
│   started — follow →    │   thin border, no left accent,
└─────────────────────────┘   not a bubble)
```

### Design Spec: Accessibility Additions

```
COMPONENT       │ ARIA ATTRIBUTE                        │ WHY
────────────────┼───────────────────────────────────────┼───────────────────
ProgressBar     │ role="progressbar"                    │ Screen reader
                │ aria-valuenow={currentStep}           │ announces progress
                │ aria-valuemin={0}                     │
                │ aria-valuemax={totalSteps}            │
                │ aria-label="Design pipeline progress" │
────────────────┼───────────────────────────────────────┼───────────────────
ESCALATED input │ aria-label="Respond to Step N"        │ Input context
                │ auto-focus on ESCALATED state         │ for keyboard users
────────────────┼───────────────────────────────────────┼───────────────────
Error "New      │ auto-focus after error                │ Next action
design" button  │                                       │ is immediately
                │                                       │ reachable
────────────────┼───────────────────────────────────────┼───────────────────
Mobile tab badge│ aria-label="HX Pipeline, N new events"│ Badge count
                │                                       │ for screen readers
```

### Design Spec: Mobile Tab Behavior

```
EVENT                    │ MOBILE ACTION
─────────────────────────┼──────────────────────────────────
Design triggered         │ Auto-switch to HX Pipeline tab
step_started/approved    │ Badge ●N on HX tab (if on Chat)
step_escalated           │ Auto-switch to HX Pipeline tab
step_error               │ Auto-switch to HX Pipeline tab
design_complete          │ Badge "✓" on HX tab (if on Chat)
User taps HX tab         │ Clear badge count
```

---

## Appendix B: Eng Review Amendments (2026-03-21)

### Resolved Issues

| # | Issue | Resolution |
|---|-------|-----------|
| 1A | `run_with_review_loop()` missing from plan | Full implementation added below |
| 2A | Pipeline runner silently skips steps on ImportError | Replaced with explicit step registry (crashes on bad imports) |
| 3A | `host.docker.internal` fails on Linux | Added `extra_hosts: host-gateway` to nginx service |
| 4A | `data/standard_sizes.py` missing | Added below (BWG table, standard tube lengths) |
| 5A | Step 1 parser too fragile for NL input | Step 1 accepts structured JSON AND natural language fallback |
| 6A | `useHXStream.js` duplicates SSEClient logic | Hook wraps existing `sseClient.js` instead of reimplementing |
| 7A | 8 test gaps identified | All 8 test cases added to test requirements |

### Amendment 1A: Full `run_with_review_loop()` Implementation

Add to `app/steps/base.py` (Dev A, Day 2):

```python
async def run_with_review_loop(
    self,
    result: StepResult,
    state: DesignState,
    ai_engineer,
    book_ctx: str = "",
    past_ctx: str = "",
) -> AIReview:
    """
    Shared correction loop — all 16 steps call this.
    Written once in BaseStep, not copy-pasted per step.

    Flow:
      review → correct → re-run Layer 1 → re-review  (attempt 1)
            → correct → re-run Layer 1 → re-review  (attempt 2)
            → correct → re-run Layer 1 → re-review  (attempt 3)
            → escalate (with all 3 attempts in payload)

    Confidence gate: after every review, if confidence < 0.5 → force escalate.
    Snapshot/restore: take DesignState snapshot before each correction;
    restore on Layer 2 hard fail so state is never left partially mutated.
    """
    from app.core.validation_rules import check as validation_check
    from app.core.exceptions import StepHardFailure

    MAX_CORRECTIONS = 3
    correction_attempts = []

    for attempt in range(MAX_CORRECTIONS + 1):
        review = await ai_engineer.review(
            step=self.step_id, result=result, design_state=state,
            book_context=book_ctx, past_designs=past_ctx,
            prior_attempts=correction_attempts,
        )

        # Confidence gate [Decision ENG-1B]
        if review.confidence < 0.5:
            review.decision = "escalate"
            review.observation = (
                f"Confidence {review.confidence:.2f} below threshold (0.50) — escalating."
            )

        if review.decision == "correct" and attempt < MAX_CORRECTIONS:
            # Snapshot before correction
            snapshot = {}
            for field in review.correction.affected_fields:
                snapshot[field] = getattr(state, field, None)

            # Apply correction
            for field, value in review.correction.values.items():
                if hasattr(state, field):
                    state = state.model_copy(update={field: value})

            # Re-run Layer 1
            result = self.execute(state)

            # Check Layer 2
            validation = validation_check(step=self.step_id, result=result)
            if validation.fails:
                # Rollback on hard fail
                state = state.model_copy(update=snapshot)

            correction_attempts.append({
                "attempt": attempt + 1,
                "correction": review.correction.model_dump() if review.correction else None,
                "reasoning": review.reasoning,
                "confidence": review.confidence,
                "layer2_passed": not validation.fails,
            })

            if validation.fails:
                continue  # re-review with restored state

        elif review.decision == "correct" and attempt == MAX_CORRECTIONS:
            # 3 corrections exhausted → convert to escalate
            review.decision = "escalate"
            review.attempts = correction_attempts
            review.observation = "Three correction attempts did not resolve the issue."
            review.recommendation = review.reasoning
            # Falls through to escalate handling below

        elif review.decision == "warn":
            # Record warning, proceed
            state = state.model_copy(update={
                "warnings": state.warnings + [review.user_summary]
            })
            break

        if review.decision == "escalate":
            review.attempts = correction_attempts
            # Emit escalation event — pipeline_runner handles wait_for_user
            break

        if review.decision == "proceed":
            # Append AI's forward-looking observation to review_notes
            if review.observation and len(review.observation) <= 200:
                note = f"[Step {self.step_id}] {review.observation}"
                state = state.model_copy(update={
                    "review_notes": state.review_notes + [note]
                })
            break

    return review
```

### Amendment 4A: `data/standard_sizes.py`

Add to Dev A's Day 5 tasks:

```python
# hx_engine/app/data/standard_sizes.py
"""
Standard tube sizes (BWG gauge), pipe sizes, and tube lengths.
Source: TEMA Standards, ASME B36.10/B36.19

Used by Step 4 to select tube OD/ID from BWG gauge.
"""

# BWG (Birmingham Wire Gauge) → wall thickness in meters
# For common tube ODs used in S&T heat exchangers
BWG_WALL_THICKNESS_M = {
    # BWG: wall_thickness_m
    7:  0.004826,   # 0.190"
    8:  0.004191,   # 0.165"
    9:  0.003404,   # 0.134"
    10: 0.003404,   # 0.134"
    11: 0.003048,   # 0.120"
    12: 0.002769,   # 0.109"
    13: 0.002413,   # 0.095"
    14: 0.002108,   # 0.083"
    15: 0.001829,   # 0.072"
    16: 0.001651,   # 0.065"
    17: 0.001473,   # 0.058"
    18: 0.001245,   # 0.049"
    20: 0.000889,   # 0.035"
}

# Standard tube ODs (meters) with default BWG
STANDARD_TUBE_ODS = {
    0.01587: {"name": "5/8 inch", "default_bwg": 14, "inch": 0.625},
    0.01905: {"name": "3/4 inch", "default_bwg": 14, "inch": 0.750},
    0.02540: {"name": "1 inch",   "default_bwg": 12, "inch": 1.000},
    0.03175: {"name": "1-1/4 inch", "default_bwg": 12, "inch": 1.250},
    0.03810: {"name": "1-1/2 inch", "default_bwg": 12, "inch": 1.500},
}

# Standard tube lengths (meters)
STANDARD_TUBE_LENGTHS_M = [
    2.438,   # 8 ft
    3.048,   # 10 ft
    3.658,   # 12 ft
    4.877,   # 16 ft (most common)
    6.096,   # 20 ft
]

def tube_id_from_od_bwg(tube_od_m: float, bwg: int) -> float:
    """Calculate tube ID from OD and BWG gauge."""
    wall = BWG_WALL_THICKNESS_M.get(bwg)
    if wall is None:
        raise ValueError(f"Unknown BWG gauge: {bwg}. Valid: {list(BWG_WALL_THICKNESS_M.keys())}")
    tube_id = tube_od_m - 2 * wall
    if tube_id <= 0:
        raise ValueError(f"BWG {bwg} wall ({wall*1000:.1f}mm) too thick for OD {tube_od_m*1000:.1f}mm")
    return tube_id

def get_default_tube_spec(tube_od_m: float = 0.01905) -> dict:
    """Return default tube spec for a given OD."""
    spec = STANDARD_TUBE_ODS.get(tube_od_m)
    if spec is None:
        # Find nearest standard OD
        nearest = min(STANDARD_TUBE_ODS.keys(), key=lambda x: abs(x - tube_od_m))
        spec = STANDARD_TUBE_ODS[nearest]
        tube_od_m = nearest
    bwg = spec["default_bwg"]
    return {
        "tube_od_m": tube_od_m,
        "tube_id_m": tube_id_from_od_bwg(tube_od_m, bwg),
        "bwg": bwg,
        "wall_thickness_m": BWG_WALL_THICKNESS_M[bwg],
        "name": spec["name"],
    }
```

### Amendment 5A: Step 1 Dual Input (Structured + NL)

Update Step 1 spec — `step_01_requirements.py` accepts both formats:

```python
class DesignInput(BaseModel):
    """Structured input — guaranteed parsing. Used by backend orchestration."""
    hot_fluid: str
    cold_fluid: str
    T_hot_in_C: float
    T_hot_out_C: Optional[float] = None
    T_cold_in_C: float
    T_cold_out_C: Optional[float] = None
    m_dot_hot_kg_s: float
    m_dot_cold_kg_s: Optional[float] = None
    pressure_hot_Pa: float = 101325.0
    pressure_cold_Pa: float = 101325.0
    tema_class: Optional[str] = None   # "R", "C", "B"

class Step01Requirements(BaseStep):
    step_id = 1
    step_name = "Process Requirements"
    ai_mode = AIModeEnum.FULL

    def execute(self, state: DesignState) -> StepResult:
        # Try parsing as JSON (structured input)
        try:
            import json
            data = json.loads(state.raw_request)
            inputs = DesignInput(**data)
            return self._from_structured(state, inputs)
        except (json.JSONDecodeError, ValidationError):
            pass

        # Fallback: regex-based NL parsing
        return self._from_natural_language(state)

    def _from_structured(self, state, inputs: DesignInput) -> StepResult:
        """Guaranteed parsing from structured JSON."""
        ...

    def _from_natural_language(self, state) -> StepResult:
        """Best-effort regex parsing from natural language."""
        # Match patterns like: "50 kg/s", "150°C", "crude oil", "cooling water"
        ...
```

### Amendment 6A: `useHXStream.js` Wraps Existing SSEClient

Update the hook to use the existing `sseClient.js` class:

```javascript
// frontend/src/hooks/useHXStream.js
import { useState, useRef, useCallback } from "react";
import SSEClient from "../utils/sseClient";
import { HX_EVENT_TYPES, eventToStepState, STEP_NAMES } from "../types/hxEvents";

export function useHXStream() {
  // ... same state as before ...
  const sseClientRef = useRef(null);

  const connectStream = useCallback((streamUrl) => {
    // Reuse existing SSEClient for connection lifecycle
    const fullUrl = `${window.location.origin}${streamUrl}`;

    // Extend SSEClient's EVENT_TYPES to include HX events
    const hxEventHandler = (event) => {
      const { type, data } = event;
      // ... same event handling logic as before ...
    };

    sseClientRef.current = new SSEClient(fullUrl, hxEventHandler);
    // SSEClient handles: connection timeout, cleanup, error recovery
  }, []);

  // ... rest of hook unchanged ...
}
```

### Amendment 7A: 8 Additional Test Cases

Add to `tests/` (Dev A + Dev B):

```
# T1: Pipeline error propagation (Dev B, Day 5)
tests/unit/core/test_pipeline_error.py
  - Step raises CalculationError → step_error SSE emitted → pipeline stops
  - DesignState preserved up to the failing step (not corrupted)

# T2: Validation rules registration (Dev A, Day 6-10, per step)
tests/unit/core/test_validation_rules.py
  - Step 2: Q <= 0 → validation fails
  - Step 5: F < 0.75 → validation fails (hard rule)
  - Step with no rules registered → validation passes

# T3: ESCALATED user response (Dev B, Day 9)
tests/unit/routers/test_design_respond.py
  - POST /design/{id}/respond with valid response → future resolved
  - POST /design/{id}/respond with no pending future → no-op (not crash)

# T4: units_adapter conversions (Dev A, Day 4)
tests/unit/adapters/test_units_adapter.py
  - fahrenheit_to_celsius(212) == 100.0
  - psi_to_pascal(14.696) ≈ 101325
  - lb_hr_to_kg_s(7936.6) ≈ 1.0

# T5: thermo_adapter unknown fluid (Dev A, Day 4)
# Add to existing test_thermo_adapter.py:
  - get_fluid_properties("unobtanium", 25.0) → raises CalculationError

# T6: Step 4 ESCALATED path (Dev A, Day 9)
tests/unit/steps/test_step_04.py  (add case):
  - Input where ΔT > 50°C AND both fluids clean → two valid TEMA types
  - StepResult indicates ambiguity → AI (when real) should escalate

# T7: SSE stream invalid session (Dev B, Day 5)
tests/unit/routers/test_stream.py
  - GET /design/nonexistent-id/stream → empty stream or error event

# T8: Redis round-trip (Dev B, Day 5)
tests/unit/core/test_session_store.py
  - save(DesignState) → load(session_id) → identical DesignState
  - load(nonexistent) → returns None
  - Use fakeredis for test isolation
```

### Critical Gaps — Inline Fixes

Add these to `pipeline_runner.py` (Dev B):

```python
# Fix 1: Redis save failure handling
try:
    await self.session_store.save(session_id, state)
except Exception as e:
    logger.warning(f"Redis save failed at step {step.step_id}: {e}")
    await self.sse_manager.emit(session_id, {
        "event_type": "step_warning",
        "step_id": step.step_id,
        "step_name": step.step_name,
        "warning_message": "Session state save failed — results may not persist.",
        "confidence": 0.0,
        "reasoning": str(e),
        "user_summary": "Warning: session save failed.",
        "duration_ms": 0,
    })

# Fix 2: Add to session_store.load()
async def load(self, session_id: str) -> DesignState | None:
    data = await self.redis.get(f"hx:session:{session_id}")
    if data is None:
        return None
    try:
        return DesignState.model_validate_json(data)
    except Exception as e:
        logger.error(f"Corrupted session {session_id}: {e}")
        return None
```

### TODO for ARKEN_MASTER_PLAN.md

Add to the master plan's Open Questions / Deferred Items section:

> **ESCALATED step timeout:** Add `asyncio.wait_for(future, timeout=300)` to the `wait_for_user()` call in `pipeline_runner.py`. Without a timeout, if a user closes their browser tab during an ESCALATED step, the asyncio task hangs forever. Auto-skip with WARNING after 5 minutes. Consider aligning with the orphan detection threshold (currently 120s). Depends on: ESCALATED flow working (Step 4). Priority: build inline with Week 2 Day 9.

### Diagrams to Add as Code Comments

**In `pipeline_runner.py` header:**
```python
"""
Pipeline Runner — orchestrates the 16-step HX design pipeline.

Data flow through Steps 1-5:
  User Request → DesignState(raw_request)
    → Step 1: parse → populate temps, flows, fluid names
    → Step 2: Q = ṁ·Cp·ΔT → populate Q_W
    → Step 3: thermo_adapter → populate shell_fluid, tube_fluid
    → Step 4: decision tree → populate tema_type, geometry
    → Step 5: LMTD correlations → populate LMTD_C, F_factor
    → [Steps 6-16 in later weeks]
    → design_complete SSE event
"""
```

**In `base.py` header:**
```python
"""
BaseStep — 4-layer execution template for all 16 pipeline steps.

Execution flow at every step:
  Layer 1: execute(state) → StepResult
      ↓
  Layer 2: validation_rules.check(step, result) → PASS/FAIL
      ↓ (FAIL → retry with fix, max 3)
  Layer 3: ai_engineer.review(step, result, state) → Decision
      ↓
      ├── PROCEED → commit, next step
      ├── CORRECT → apply fix, re-run L1, re-review (max 3)
      ├── WARN → record, proceed
      └── ESCALATE → pause, wait for user, resume
      ↓
  Layer 4: state.update(step, result, review) → emit SSE
"""
```
