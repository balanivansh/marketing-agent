# AI Marketing Operating System

A modular AI Marketing Operating System supporting multi-tenant brand isolation, dynamic path resolution, SQLite tenant storage, dual LLM routing (Local Ollama + Cloud Gemini), deterministic research ingestion, and Logfire observability.

## System Architecture

- **Stage 0: Scaffolding, Observability, and Tenant Storage**
  - Tenant isolation under `brands/{tenant_id}/` (`brand.json`, `brand.db`, `templates/`)
  - SQLite persistence (`research_items`, `drafts`, `draft_diffs`, `style_observations`)
  - Logfire telemetry with graceful fallback to standard logging
- **Stage 1: Dual LLM Router & Memory Management**
  - Task-based inference routing:
    - `TRIAGE_SCORING` -> `LLMEngine.LOCAL` (Ollama: `llama3.1:8b-instruct-q4_K_M` with mandatory `keep_alive: "1m"`)
    - `IDEATION`, `DRAFTING`, `CRITIC`, `OBSERVATION` -> `LLMEngine.CLOUD` (Gemini Flash via `google-genai`)
  - Automatic error recovery and bidirectional graceful engine fallback
  - Telemetry spans wrapping inference latency, token counts, and engine metadata
- **Stage 2: Research Ingestion & Relevance Scoring**
  - Deterministic RSS feed ingestion via `feedparser` with deduplication using SQLite `UNIQUE(url)`
  - Local relevance scoring with Ollama evaluating against tenant content pillars
  - Tenant-aware execution (`--tenant`) with structured spans (`ingest_sources`, `triage_batch`)

## Directory Structure
```
├── .env.example
├── .env
├── README.md
├── pyproject.toml
├── uv.lock
├── brands/
│   └── v_personal/
│       ├── brand.db
│       ├── brand.json
│       └── templates/
├── core/
│   ├── __init__.py
│   ├── config.py
│   ├── db.py
│   ├── logger.py
│   ├── router.py
│   └── schemas.py
├── pipeline/
│   ├── __init__.py
│   ├── ingest.py
│   └── triage.py
├── scripts/
│   ├── verify_stage_0.py
│   └── verify_stage_2.py
├── tests/
│   ├── __init__.py
│   ├── test_router.py
│   ├── test_stage_0.py
│   └── test_stage_2.py
└── ui/
    └── __init__.py
```

## Running Verification

Verify Stage 0 (Scaffolding & Tenant DB):
```bash
uv run python scripts/verify_stage_0.py
```

Verify Stage 2 (Research Ingestion & Local Triage):
```bash
uv run python scripts/verify_stage_2.py --limit 3
```

Run Full Test Suite:
```bash
uv run python -m unittest discover tests
```
