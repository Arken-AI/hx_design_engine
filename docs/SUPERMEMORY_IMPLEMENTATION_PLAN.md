# Supermemory / RAG Implementation Plan

**Status:** Planning  
**Depends on:** Supermemory account + API key (confirmed available)  
**SDK:** `supermemory` PyPI package v3.32.0  
**Scope:** Full pipeline — document ingestion, query-side integration, testing  
**Primary Use Case (this plan):** Tube material thermal conductivity (k_w) from ASME Section II Part D  
**Future Use Cases (not this plan):** Book context for AI prompts, past design retrieval, user profiles

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Architecture Overview](#2-architecture-overview)
3. [Phase 1: SDK Setup & Client Adapter](#3-phase-1-sdk-setup--client-adapter)
4. [Phase 2: Document Ingestion Pipeline](#4-phase-2-document-ingestion-pipeline)
5. [Phase 3: Query-Side Integration](#5-phase-3-query-side-integration)
6. [Phase 4: Material Property Adapter](#6-phase-4-material-property-adapter)
7. [Phase 5: Placeholder Adapter (Interim)](#7-phase-5-placeholder-adapter-interim)
8. [Phase 6: Testing & Validation](#8-phase-6-testing--validation)
9. [Data Model Changes](#9-data-model-changes)
10. [Dependency & Config Changes](#10-dependency--config-changes)
11. [File Inventory](#11-file-inventory)
12. [Open Questions](#12-open-questions)

---

## 1. Problem Statement

Step 9 (Overall U + Resistance Breakdown) computes the wall resistance term:

$$R_{wall} = \frac{d_o \ln(d_o / d_i)}{2 k_w}$$

This requires `k_w` — the tube wall thermal conductivity in W/m·K.

**Why not hardcode?**

- Engineering alloys (SA-179 carbon steel, 304SS, 316SS, titanium Gr.2, Inconel) are NOT pure elements
- Their k values differ significantly from pure metals (e.g., pure iron ~80 W/mK vs carbon steel SA-179 ~50 W/mK)
- k varies with temperature (stainless 304: ~14 W/mK at 20°C → ~21 W/mK at 400°C)
- The authoritative source is **ASME BPVC Section II, Part D, Table TCD**

**Why Supermemory/RAG?**

- No Python library covers alloy thermal conductivity (chemicals/CoolProp/thermo handle fluids, not engineering alloys)
- ASME data is copyrighted — cannot be committed to source code
- RAG retrieval preserves the citation chain (ASME edition, table number, year)
- Same infrastructure serves all future book-context and past-design queries planned in ARKEN_MASTER_PLAN.md §8

**Impact of getting k_w wrong:**

| Material          | k_w (W/mK) | Wall R as % of 1/U  |
| ----------------- | ---------- | ------------------- |
| Carbon steel      | ~50        | 1–5% (low impact)   |
| Stainless 304/316 | ~16        | 5–15% (significant) |
| Titanium Gr.2     | ~22        | 4–10% (moderate)    |
| Copper            | ~385       | <0.5% (negligible)  |
| Inconel 600       | ~15        | 5–15% (significant) |

For stainless and exotic alloys, a ±30% error in k_w changes U by 2–5%. This matters.

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│  One-Time Ingestion (scripts/ingest_asme.py)         │
│                                                       │
│  ASME PDF ──→ supermemory.documents.upload_file()    │
│               container_tags=["engineering_books",    │
│                               "material_properties"] │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │   Supermemory Cloud │
            │   (Vector Store)    │
            └─────────┬───────────┘
                      │
          ┌───────────┴───────────────┐
          │                           │
          ▼                           ▼
┌──────────────────┐     ┌──────────────────────────┐
│  MemoryClient    │     │  MaterialPropertyAdapter │
│  (generic)       │     │  (Step 9 specific)       │
│                  │     │                          │
│  search_docs()   │◄────│  get_k_wall()            │
│  search_mems()   │     │  resolve_material()      │
│  add()           │     │                          │
│  upload_file()   │     │  Fallback: stub defaults │
│  profile()       │     │  when Supermemory is down │
└──────────────────┘     └──────────────────────────┘
          │
          │  Used by pipeline_runner.py
          ▼
┌────────────────────────────────────────────┐
│  Pipeline Runner                           │
│  ├── Step 4: AI review → tube_material     │
│  ├── Step 8: book context for J-factors    │
│  ├── Step 9: k_w + book context for U      │
│  ├── Step 13: book context for vibration   │
│  └── Step 16: past designs + save          │
└────────────────────────────────────────────┘
```

---

## 3. Phase 1: SDK Setup & Client Adapter

### 3.1 Install SDK

```bash
pip install supermemory>=3.30
```

Add to `requirements.txt` and `pyproject.toml` dependencies.

### 3.2 Config Changes

**File:** `hx_engine/app/config.py`

Add to `HXEngineSettings`:

```python
supermemory_api_key: str = ""
supermemory_timeout_s: float = 5.0
supermemory_enabled: bool = True  # Feature flag — disable to skip all SM calls
```

### 3.3 Memory Client

**File:** `hx_engine/app/adapters/memory_client.py`

```python
class MemoryClient:
    """
    Thin wrapper around the Supermemory SDK.
    Provides typed methods for the HX engine's specific use cases.
    All methods have timeout + fallback behavior.
    """

    def __init__(self, api_key: str, timeout_s: float = 5.0, enabled: bool = True):
        self._enabled = enabled
        self._timeout_s = timeout_s
        if enabled and api_key:
            self._client = AsyncSupermemory(api_key=api_key, timeout=timeout_s)
        else:
            self._client = None

    async def search_documents(
        self,
        query: str,
        container_tags: list[str] | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """Search ingested documents (books, ASME tables). Returns chunks."""

    async def search_memories(
        self,
        query: str,
        container_tags: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search stored memories (past designs). Returns memories."""

    async def add_memory(
        self,
        content: str,
        container_tags: list[str],
        metadata: dict | None = None,
        custom_id: str | None = None,
    ) -> str:
        """Store a memory (design result, user preference). Returns ID."""

    async def get_profile(
        self,
        container_tag: str,
        query: str,
    ) -> str:
        """Get user profile summary."""

    async def upload_document(
        self,
        file_path: str,
        container_tags: list[str],
        metadata: dict | None = None,
    ) -> str:
        """Upload a document (PDF) for indexing. Returns document ID."""
```

### 3.4 Safety Wrapper Pattern

Every call goes through `_safe_call()`:

```python
async def _safe_call(self, coro, default=None, operation: str = ""):
    """
    5-second timeout. On failure → log warning, return default.
    Design completes with reduced context; never blocks on SM outage.
    """
    if not self._enabled or self._client is None:
        return default
    try:
        return await asyncio.wait_for(coro, timeout=self._timeout_s)
    except asyncio.TimeoutError:
        logger.warning("Supermemory timeout on %s", operation)
        return default
    except Exception as e:
        logger.warning("Supermemory error on %s: %s", operation, e)
        return default
```

### 3.5 Dependency Injection

**File:** `hx_engine/app/dependencies.py`

```python
_memory_client: MemoryClient | None = None

async def startup() -> None:
    global _memory_client
    _memory_client = MemoryClient(
        api_key=settings.supermemory_api_key,
        timeout_s=settings.supermemory_timeout_s,
        enabled=settings.supermemory_enabled,
    )
    # ... existing startup code ...

def get_memory_client() -> MemoryClient:
    assert _memory_client is not None
    return _memory_client
```

---

## 4. Phase 2: Document Ingestion Pipeline

### 4.1 ASME Data Ingestion

**File:** `scripts/ingest_asme.py`

One-time script to upload ASME Section II Part D PDF into Supermemory.

```python
"""
One-time ingestion of ASME BPVC Section II Part D material property tables.

Usage:
    python scripts/ingest_asme.py --file /path/to/ASME_Section_II_Part_D.pdf

The PDF is uploaded to Supermemory with container tags:
    - "engineering_books" (shared with all book queries)
    - "material_properties" (specific to material lookups)

Metadata includes ASME edition year for citation tracking.
"""
```

**Steps:**

1. Validate PDF exists and is readable
2. Call `memory_client.upload_document()` with tags `["engineering_books", "material_properties"]`
3. Call `documents.list_processing()` to poll until processing complete
4. Run validation query: search for "SA-179 thermal conductivity" → verify returns a result
5. Log document ID for reference

**Container Tags Strategy:**

| Tag                   | Purpose                         | Used By                |
| --------------------- | ------------------------------- | ---------------------- |
| `engineering_books`   | All technical reference PDFs    | Steps 4, 8, 9, 13, 16  |
| `material_properties` | ASME material data specifically | Step 9 material lookup |
| `hx_designs`          | Past design results             | Steps 6, 9, 16         |
| `user_{user_id}`      | Per-user preferences            | Step 1                 |

### 4.2 Supplementary Document Ingestion

Same script supports ingesting other reference PDFs:

```bash
# ASME material data (required for Step 9)
python scripts/ingest_asme.py --file ASME_Section_II_Part_D.pdf

# Future: other books (not needed for Step 9 but same pipeline)
python scripts/ingest_docs.py --file Serth_HX_Design.pdf --tags engineering_books
python scripts/ingest_docs.py --file Perry_Handbook.pdf --tags engineering_books
```

### 4.3 Ingestion Verification

After ingestion, run a test query to verify retrieval quality:

```python
# Test queries that MUST return meaningful results:
test_queries = [
    ("SA-179 carbon steel thermal conductivity 100°C", "material_properties"),
    ("304 stainless steel thermal conductivity", "material_properties"),
    ("titanium grade 2 thermal conductivity", "material_properties"),
]
```

Each query must return at least 1 result with a chunk containing a recognizable k value. This is a manual verification step after ingestion — not an automated test.

---

## 5. Phase 3: Query-Side Integration

### 5.1 How Steps Query Supermemory

The **pipeline runner** (not the step itself) manages Supermemory queries. Steps are pure calculation — they don't know about Supermemory.

```
pipeline_runner.py:
  1. Build query from design_state fields
  2. Call memory_client.search_documents()
  3. Format results as context string
  4. Pass context to ai_engineer.review() via step's run_with_review_loop()
```

### 5.2 Query Templates

For material properties (Step 9 specific):

```python
def _build_material_query(state: DesignState) -> str:
    """Build Supermemory query for tube material conductivity."""
    material = state.tube_material or "carbon steel"
    t_mean = _get_tube_side_mean_temp(state)
    return (
        f"thermal conductivity {material} tube material "
        f"at {t_mean:.0f}°C ASME Section II Part D Table TCD"
    )
```

For general book context (future, not this plan):

```python
def _build_book_query(state: DesignState, step_id: int) -> str:
    """Build Supermemory query for engineering book references."""
    # Step-specific query builders based on design state
    ...
```

### 5.3 Response Parsing

Supermemory returns document chunks. The material adapter parses k_w from the chunk text:

```
Supermemory returns:
  "SA-179 Carbon Steel, seamless cold-drawn tube.
   Thermal conductivity (W/m·K): 50°C: 51.9, 100°C: 51.1,
   150°C: 50.0, 200°C: 48.5 ..."

MaterialPropertyAdapter extracts:
  k_wall = 50.0 (at T_mean ≈ 150°C, interpolated)
  source = "ASME Section II Part D, Table TCD"
  confidence = 0.95
```

Parsing strategy:

- The AI engineer already reviews Step 9 — it can extract k_w from the ASME chunk text
- Alternatively: regex patterns for common ASME table formats (numerical extraction)
- Both approaches are valid; the AI extraction is more robust for varied PDF formats

**Recommended:** Use the AI review to validate/extract k_w from the ASME chunk. Step 9's execute() receives k_w as a pre-resolved number from the material adapter. If the adapter's regex extraction fails, the AI can correct it during review.

---

## 6. Phase 4: Material Property Adapter

### 6.1 Interface

**File:** `hx_engine/app/adapters/material_adapter.py`

```python
@dataclass
class MaterialProperties:
    k_wall_W_mK: float
    material_name: str
    source: str              # "ASME Section II Part D" | "stub_default"
    confidence: float        # 0.0–1.0
    temperature_C: float     # temperature at which k was evaluated
    needs_ai_review: bool    # True if from stub or low-confidence extraction

class MaterialPropertyAdapter:
    """
    Resolution chain for tube material thermal conductivity.

    Priority 1: Supermemory (ASME Section II Part D via RAG)
    Priority 2: Stub defaults (fallback when Supermemory unavailable)
    """

    def __init__(self, memory_client: MemoryClient | None = None):
        self._memory = memory_client

    async def get_k_wall(
        self,
        material_name: str,
        temperature_C: float,
    ) -> MaterialProperties:
        """
        Resolve tube wall thermal conductivity.

        1. Query Supermemory for ASME data
        2. Parse k value from returned chunk (regex extraction)
        3. Interpolate to target temperature if multi-temp data found
        4. Fallback to stub defaults if SM unavailable or parse fails
        """

    def resolve_material_from_fluid(
        self,
        hot_fluid: str,
        cold_fluid: str,
        max_temp_C: float,
        max_pressure_bar: float,
    ) -> str:
        """
        Heuristic material selection based on fluid pair and conditions.
        Returns a material name string (e.g., "carbon_steel_SA179").

        Rules:
        - Default: carbon steel SA-179 (most common HX tube)
        - If either fluid is seawater/brackish → titanium Gr.2 or 316SS
        - If max_temp > 400°C → stainless or alloy steel
        - If corrosive acids → Inconel or Hastelloy
        - If either fluid contains "ammonia" → carbon steel (compatible)
        """
```

### 6.2 Supermemory Query Flow

```python
async def _query_supermemory(self, material: str, temp_C: float) -> MaterialProperties | None:
    if not self._memory:
        return None

    query = (
        f"thermal conductivity {material} at {temp_C:.0f}°C "
        f"ASME Section II Part D Table TCD W/m·K"
    )
    results = await self._memory.search_documents(
        query=query,
        container_tags=["material_properties"],
        limit=3,
    )
    if not results:
        return None

    # Attempt to extract k value from the best chunk
    for chunk in results:
        k_value = self._extract_k_from_chunk(chunk["text"], temp_C)
        if k_value is not None:
            return MaterialProperties(
                k_wall_W_mK=k_value,
                material_name=material,
                source="ASME Section II Part D, Table TCD",
                confidence=0.95,
                temperature_C=temp_C,
                needs_ai_review=False,
            )

    return None  # Parse failed → fall through to stub
```

### 6.3 Extraction Logic

```python
def _extract_k_from_chunk(self, text: str, target_temp_C: float) -> float | None:
    """
    Extract thermal conductivity value from ASME table chunk text.

    Handles formats like:
      "50°C: 51.9, 100°C: 51.1, 150°C: 50.0"
      "Temperature (°C)    k (W/m·K)\n100    51.1\n200    48.5"

    If multiple temperatures found, interpolates linearly to target_temp_C.
    """
```

### 6.4 Stub Fallback

When Supermemory is unavailable or extraction fails:

```python
_STUB_DEFAULTS: dict[str, dict] = {
    "carbon_steel":     {"k_20C": 51.9, "k_100C": 51.1, "k_200C": 48.5, "k_300C": 44.0},
    "stainless_304":    {"k_20C": 14.9, "k_100C": 16.2, "k_200C": 17.8, "k_300C": 19.8},
    "stainless_316":    {"k_20C": 13.4, "k_100C": 14.7, "k_200C": 16.3, "k_300C": 18.1},
    "titanium_gr2":     {"k_20C": 16.4, "k_100C": 17.4, "k_200C": 18.6, "k_300C": 19.7},
    "copper":           {"k_20C": 391,  "k_100C": 388,  "k_200C": 383,  "k_300C": 377},
    "admiralty_brass":   {"k_20C": 111,  "k_100C": 116,  "k_200C": 121,  "k_300C": 126},
    "inconel_600":      {"k_20C": 14.8, "k_100C": 15.8, "k_200C": 17.3, "k_300C": 19.0},
}
```

**Important:** These stubs exist ONLY as a fallback when Supermemory is unavailable. They are marked with `source="stub_default"` and `needs_ai_review=True` so the AI review flags them. The actual source of truth is the ASME data in Supermemory.

---

## 7. Phase 5: Placeholder Adapter (Interim)

Since Supermemory is not wired into the pipeline yet, Step 9 initially uses the stub adapter.

### 7.1 Interim Strategy

```python
# In Step 9 execute():
# 1. Check if state has tube_material and k_wall_W_mK already set
#    (future: Step 4 or earlier step may set this via Supermemory)
# 2. If not set → use MaterialPropertyAdapter
# 3. Adapter tries Supermemory first, falls back to stubs

adapter = MaterialPropertyAdapter(memory_client=None)  # Stub mode initially
material_props = await adapter.get_k_wall(
    material_name=state.tube_material or "carbon_steel",
    temperature_C=t_mean_wall,
)
```

### 7.2 Swap Path

When Supermemory is fully wired (future phase):

```python
# In pipeline_runner.py:
adapter = MaterialPropertyAdapter(memory_client=self.memory_client)
# Same interface, now queries Supermemory first
```

No changes needed to Step 9's execute() — the adapter interface is the same.

---

## 8. Phase 6: Testing & Validation

### 8.1 Unit Tests

**File:** `tests/unit/adapters/test_material_adapter.py`

| Test                                  | Description                                            |
| ------------------------------------- | ------------------------------------------------------ |
| `test_stub_carbon_steel`              | Stub returns k≈50 for carbon steel at 100°C            |
| `test_stub_stainless_304`             | Stub returns k≈16 for 304SS at 100°C                   |
| `test_stub_temperature_interpolation` | k at 150°C interpolates between 100°C and 200°C values |
| `test_stub_unknown_material`          | Falls back to carbon steel with warning                |
| `test_resolve_material_seawater`      | Seawater → titanium or 316SS                           |
| `test_resolve_material_default`       | Normal fluids → carbon steel                           |
| `test_supermemory_timeout_fallback`   | SM timeout → stub defaults + `needs_ai_review=True`    |
| `test_supermemory_returns_valid`      | Mock SM → extracts k from chunk text                   |
| `test_chunk_parsing_multi_temp`       | Parses "50°C: 51.9, 100°C: 51.1" format                |
| `test_chunk_parsing_table_format`     | Parses tabular format                                  |
| `test_chunk_parsing_no_match`         | Unparseable chunk → returns None → stub                |

### 8.2 Integration Test (Post-Ingestion)

**File:** `scripts/test_supermemory_retrieval.py`

Manual test (not pytest) that runs after document ingestion:

```python
# Requires SUPERMEMORY_API_KEY in environment
# Run: python scripts/test_supermemory_retrieval.py

EXPECTED_RESULTS = {
    "carbon_steel_SA179_100C": (48.0, 54.0),   # expected k range
    "stainless_304_100C":      (14.0, 18.0),
    "titanium_gr2_100C":       (15.0, 20.0),
}
```

### 8.3 Memory Client Unit Tests

**File:** `tests/unit/adapters/test_memory_client.py`

| Test                             | Description                                   |
| -------------------------------- | --------------------------------------------- |
| `test_disabled_returns_default`  | `enabled=False` → returns default immediately |
| `test_timeout_returns_default`   | Mock timeout → returns default, logs warning  |
| `test_api_error_returns_default` | Mock 500 → returns default, logs warning      |
| `test_search_documents_forwards` | Mock SDK → forwards query + tags correctly    |
| `test_search_memories_forwards`  | Mock SDK → forwards query + tags correctly    |

---

## 9. Data Model Changes

### 9.1 DesignState New Fields

```python
# Added to DesignState (design_state.py):
tube_material: Optional[str] = None          # e.g., "carbon_steel", "stainless_304"
k_wall_W_mK: Optional[float] = None         # tube wall thermal conductivity
k_wall_source: Optional[str] = None          # "ASME Section II Part D" | "stub_default"
k_wall_confidence: Optional[float] = None    # 0.0–1.0
```

### 9.2 MaterialProperties Dataclass

```python
# In adapters/material_adapter.py:
@dataclass
class MaterialProperties:
    k_wall_W_mK: float
    material_name: str
    source: str
    confidence: float
    temperature_C: float
    needs_ai_review: bool
```

---

## 10. Dependency & Config Changes

### 10.1 requirements.txt

Add:

```
supermemory>=3.30
```

### 10.2 pyproject.toml

Add to `[project.optional-dependencies]`:

```toml
memory = ["supermemory>=3.30"]
```

Add to `[project]` dependencies:

```toml
"supermemory>=3.30",
```

### 10.3 .env.example

Add:

```
SUPERMEMORY_API_KEY=your_supermemory_api_key_here
SUPERMEMORY_ENABLED=true
SUPERMEMORY_TIMEOUT_S=5.0
```

### 10.4 config.py

```python
supermemory_api_key: str = ""
supermemory_timeout_s: float = 5.0
supermemory_enabled: bool = True
```

---

## 11. File Inventory

### New Files

| File                                           | Purpose                                       |
| ---------------------------------------------- | --------------------------------------------- |
| `hx_engine/app/adapters/memory_client.py`      | Supermemory SDK wrapper with safety + timeout |
| `hx_engine/app/adapters/material_adapter.py`   | Material k_w resolution chain (SM → stub)     |
| `scripts/ingest_asme.py`                       | One-time ASME PDF ingestion script            |
| `scripts/test_supermemory_retrieval.py`        | Manual post-ingestion validation              |
| `tests/unit/adapters/test_material_adapter.py` | Material adapter unit tests                   |
| `tests/unit/adapters/test_memory_client.py`    | Memory client unit tests                      |

### Modified Files

| File                                   | Change                                                                   |
| -------------------------------------- | ------------------------------------------------------------------------ |
| `requirements.txt`                     | Add `supermemory>=3.30`                                                  |
| `pyproject.toml`                       | Add `supermemory>=3.30` to dependencies                                  |
| `hx_engine/app/config.py`              | Add `supermemory_*` settings                                             |
| `hx_engine/app/dependencies.py`        | Add `MemoryClient` singleton + getter                                    |
| `hx_engine/app/models/design_state.py` | Add `tube_material`, `k_wall_W_mK`, `k_wall_source`, `k_wall_confidence` |
| `.env.example`                         | Add `SUPERMEMORY_API_KEY`, `SUPERMEMORY_ENABLED`                         |

---

## 12. Open Questions

| #   | Question                                                                               | Impact                        | Default If Unresolved                                            |
| --- | -------------------------------------------------------------------------------------- | ----------------------------- | ---------------------------------------------------------------- |
| 1   | What ASME edition year is the PDF? (2019, 2021, 2023?)                                 | Metadata tagging for citation | Tag with edition year in metadata                                |
| 2   | Should the ingestion script chunk the PDF manually or let Supermemory handle chunking? | Retrieval quality for tables  | Let Supermemory auto-chunk, validate with test queries           |
| 3   | Should material selection happen in Step 4 (future) or always in Step 9?               | Architecture cleanliness      | Step 9 resolves via adapter (per decision)                       |
| 4   | What's the Supermemory plan/tier? (affects rate limits, storage)                       | Ingestion strategy            | Assume standard tier, one PDF at a time                          |
| 5   | Should k_w extracted by adapter be re-validated by the AI review, or trusted directly? | Accuracy vs latency           | AI validates in FULL review (no extra cost since Step 9 is FULL) |

---

## Build Sequence

```
1. Install supermemory SDK + config changes
2. Build MemoryClient adapter (with safety wrapper)
3. Build MaterialPropertyAdapter (with stubs)
4. Add DesignState fields
5. Wire into dependencies.py
6. Unit tests for both adapters
7. Build ingestion script
8. Ingest ASME PDF (manual step)
9. Run retrieval validation script
10. Swap Step 9 to use live Supermemory (remove None memory_client)
```

Steps 1–6 are needed for Step 9 implementation.  
Steps 7–10 are needed for live Supermemory integration (can be done after Step 9 ships with stubs).
