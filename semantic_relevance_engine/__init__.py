"""
Semantic Relevance Engine Package for LLM Context Optimization Middleware.
"""

from .models import Chunk, SourceType, TagType
from .engine import rank_chunks
from .chunker import chunk_context
from .embedder import Embedder
from .optimizer import optimize_chunks
from .critical_flags import detect_critical_flags

__all__ = [
    "rank_chunks",
    "optimize_chunks",
    "detect_critical_flags",
    "Chunk",
    "SourceType",
    "TagType",
    "chunk_context",
    "Embedder",
]
