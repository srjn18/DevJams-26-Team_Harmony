"""
Semantic Relevance Engine Package for LLM Context Optimization Middleware.
"""

from .models import Chunk, SourceType, TagType
from .engine import rank_chunks
from .chunker import chunk_context
from .embedder import Embedder
from .optimizer import optimize_chunks
from .critical_flags import detect_critical_flags
from .grok_client import grok_compress, grok_answer, get_token_usage, reset_token_usage

__all__ = [
    "rank_chunks",
    "optimize_chunks",
    "detect_critical_flags",
    "grok_compress",
    "grok_answer",
    "get_token_usage",
    "reset_token_usage",
    "Chunk",
    "SourceType",
    "TagType",
    "chunk_context",
    "Embedder",
]
