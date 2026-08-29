# LLM Context Optimization Middleware

Middleware that sits between an app and an LLM. It cuts irrelevant/redundant
context, compresses what's useful, fits it into a token budget, and proves —
with measured numbers — that this saves tokens/cost/latency without wrecking
answer quality.

30-second pitch: *"LLM apps send huge, mostly-unnecessary contexts with every
request. We built middleware that analyzes token usage, filters context by
semantic relevance to the current query, scores importance, removes
redundancy, protects critical facts (constraints, numbers, negations),
compresses the rest, and fits it into a token budget — then measures the
before/after token savings, cost savings, latency, and answer quality."*

See `design.md` for the full technical spec. This file is the quickstart +
team map.

---

## Architecture (one paragraph)

Request → deterministic chunking + tagging (no paid calls) → cost-aware
routing decision (SKIP / LIGHT / FULL) → semantic relevance + dedup →
critical-info pinning + compression + token-budget knapsack → coherence
reassembly → LLM → evaluation (deterministic safety checks + LLM-judge
quality). Full detail: `design.md`.

---

## API

```
POST /analyze              → routing decision + cost estimate only
POST /optimize              → optimized context + trace, no LLM call
POST /optimize-and-answer   → /optimize then calls the LLM (demo endpoint)
```

Full request/response shapes are in `design.md` §11.

---

## Team map

| Person | Owns | Status |
|---|---|---|
| **Person 1** | Chunking, tagging, embeddings, relevance, dedup | **Complete (`semantic_relevance_engine/`)** |
| **Person 2** | Critical-info detection, pinning, compression, coherence assembly, token budget | See `HARDEST_PART.md` |
| **Person 3** | LLM integration, cost model, routing decision, evaluation (both tracks), benchmark set | Active |
| **Person 4** | Backend (3 endpoints), orchestration, fallback logic, dashboard | Active |

---

## Semantic Relevance Engine (Person 1 Module)

### Directory Structure
```
├── __init__.py           # Package exports (rank_chunks, Chunk, chunk_context, Embedder)
├── models.py             # Pydantic schema enforcing Chunk contract
├── chunker.py            # Multi-format context splitter & source tagger
├── embedder.py           # Pluggable 3-tier embeddings (sentence-transformers / API / NumPy fallback)
├── engine.py             # Scoring, pairwise deduplication, fact guard, descending sorting
├── cli.py                # Command line interface & report generator
├── setup.py              # Package installation configuration
├── requirements.txt      # Python dependencies
└── tests/
    ├── __init__.py
    └── test_engine.py    # Unit & integration test suite
```

### Quick Start
```powershell
# Install dependencies & package
pip install -r requirements.txt
pip install -e .

# Run CLI
python cli.py

# Run CLI JSON export
python cli.py --json

# Run unit tests
python -m unittest discover tests
```

### Python API Integration
```python
from semantic_relevance_engine import rank_chunks, Chunk

results: list[Chunk] = rank_chunks(
    query="How does vector indexing work?",
    context="[SYSTEM] instructions\n[USER] question\n[DOC] documentation..."
)
```

---

## Core engineering principle

Do not optimize for maximum token reduction. Optimize for maximum useful
information retained per token. 90% reduction that breaks the answer is a
failure; 70% reduction that preserves quality is the win condition.

## Files in this repo

- `README.md` — this file
- `design.md` — full technical design
- `AGENT_PROMPTS.md` — ready-to-paste AI-agent briefs per teammate, with
  locked interface contracts
- `HARDEST_PART.md` — Person 2's spec, checklist, and starter code
  (critical-info protection + compression + budget engine)
- `tests/adversarial_cases.md` — the adversarial test set (negations,
  numbers, constraints, paraphrases) used to validate the hardest module
- `chunker.py`, `embedder.py`, `engine.py`, `models.py`, `cli.py` — Person 1's Semantic Relevance Engine
