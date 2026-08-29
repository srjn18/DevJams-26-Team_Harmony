# Semantic Relevance Engine

Semantic relevance ranking, scoring, and deduplication middleware for LLM context optimization.

## Directory Structure

```
semantic_relevance_engine/
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

## Quick Start

### 1. Installation
```powershell
pip install -r requirements.txt
pip install -e .
```

### 2. Run CLI
```powershell
# Default demo run
semantic-relevance-engine

# Custom query and context
semantic-relevance-engine --query "How does vector indexing work?" --context "[SYSTEM] System prompt\n[USER] How does indexing work?\n[DOC] Vector search indexing docs"

# Export as JSON
semantic-relevance-engine --json
```

### 3. Python API
```python
from semantic_relevance_engine import rank_chunks

results = rank_chunks(
    query="How does vector indexing work?",
    context="[SYSTEM] instructions\n[USER] question\n[DOC] documentation..."
)

for chunk in results:
    print(f"ID: {chunk.id} | Score: {chunk.relevance_score:.4f} | Tag: {chunk.tag}")
```

### 4. Run Tests
```powershell
python -m unittest discover tests
```
