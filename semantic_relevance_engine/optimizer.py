from __future__ import annotations
import re
import logging
from typing import Optional

try:
    from .models import Chunk
except ImportError:
    from models import Chunk

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Step A: Critical-info detection
# ---------------------------------------------------------------------------

CRITICAL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("negation", re.compile(
        r"\b(do not|don't|never|must not|mustn't|can't|cannot|won't|shouldn't|"
        r"should not)\b", re.IGNORECASE)),
    ("number", re.compile(
        r"(\b\d+(\.\d+)?\s*(seconds?|s|ms|minutes?|hours?|days?|%|percent|"
        r"tokens?|requests?|MB|GB|KB)(?!\w))|(\b(is|=|set(?:[a-zA-Z\s]+)?to|equals)\s+\d+\b)",
        re.IGNORECASE)),
    ("constraint", re.compile(
        r"\b(must|required|shall|has to|needs to|only|always|mandatory)\b",
        re.IGNORECASE)),
    ("error", re.compile(
        r"(\b(HTTP\s*)?[1-5]\d{2}\b.{0,20}(error|status|returns?))|"
        r"(\b(error|status|returns?)\b.{0,20}\b(HTTP\s*)?[1-5]\d{2}\b)|"
        r"(\bexception\b|\btraceback\b|\bfailed with\b|\bstack trace\b)", re.IGNORECASE)),
    ("decision", re.compile(
        r"\b(we\s+(chose|decided|will use|are using)|we're\s+using|switched\s+to|migrat(ed|ing)\s+(to|off))\b",
        re.IGNORECASE)),
]


def detect_critical_flags(text: str) -> list[str]:
    """Return list of flag names that fire on this text."""
    flags = []
    for name, pattern in CRITICAL_PATTERNS:
        if pattern.search(text):
            flags.append(name)
    return flags


def approx_token_count(text: str) -> int:
    """Rough fallback token counter (~4 chars per token)."""
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Step A cont'd: apply detection + pinning to a chunk list
# ---------------------------------------------------------------------------

def apply_pinning(chunks: list[Chunk]) -> list[Chunk]:
    for c in chunks:
        c.critical_flags = detect_critical_flags(c.text)
        if c.tag in ("SYSTEM", "PERSISTENT_CONSTRAINT") or c.critical_flags:
            c.pinned = True
    return chunks


def compute_importance_score(c: Chunk) -> float:
    """
    Computes an importance score based on chunk metadata and critical flags.
    Allows balancing relevance and metadata importance.
    """
    # Base importance depending on source/tag
    if c.tag == "SYSTEM":
        base = 0.8
    elif c.tag == "PERSISTENT_CONSTRAINT":
        base = 0.7
    elif c.source == "conversation":
        base = 0.3
    elif c.source == "document":
        base = 0.2
    else:
        base = 0.1
    
    # Boost by critical flags
    flag_boost = 0.2 * len(c.critical_flags)
    return min(1.0, base + flag_boost)


def compute_final_score(c: Chunk, relevance_weight: float = 0.7,
                        importance_weight: float = 0.3) -> float:
    return relevance_weight * c.relevance_score + importance_weight * c.importance_score


# ---------------------------------------------------------------------------
# Step C: compression
# ---------------------------------------------------------------------------

COMPRESSION_PROMPT_TEMPLATE = """\
Rewrite the following context to be as concise as possible while preserving
every fact, number, date, name, and technical detail. Do not remove any
information that could affect the answer to this question: "{query}"

Do not add information that isn't present. Do not soften or generalize
specific claims. If in doubt, keep it rather than cut it.

Context:
{chunk_text}
"""


def compress_chunk(chunk: Chunk, query: str, llm_call_fn=None) -> Chunk:
    """
    Compresses non-pinned chunk text using llm_call_fn. Reverts to original if
    information is lost or empty output is received.
    """
    if chunk.pinned:
        return chunk

    if llm_call_fn is None:
        return chunk

    prompt = COMPRESSION_PROMPT_TEMPLATE.format(query=query, chunk_text=chunk.text)
    compressed_text = llm_call_fn(prompt)

    # CHECK 1 — Empty compression guard
    if compressed_text.strip() == "":
        logger.warning("empty_compression_result")
        chunk.trace_events.append("empty_compression_result")
        return chunk

    original_flags = set(detect_critical_flags(chunk.text))
    new_flags = set(detect_critical_flags(compressed_text))
    if original_flags - new_flags:
        logger.warning("flag_lost_revert")
        chunk.trace_events.append("flag_lost_revert")
        return chunk

    # CHECK 2 — New-flag logging (non-blocking)
    added_flags = new_flags - original_flags
    if added_flags:
        logger.info(f"flag_added: {added_flags}")
        chunk.trace_events.append("flag_added")

    chunk.text = compressed_text
    chunk.token_count = approx_token_count(compressed_text)
    chunk.compressed = True
    return chunk


# ---------------------------------------------------------------------------
# Step D: token budget knapsack (greedy)
# ---------------------------------------------------------------------------

def enforce_budget(chunks: list[Chunk], token_budget: int) -> tuple[list[Chunk], dict]:
    pinned = [c for c in chunks if c.pinned]
    non_pinned = sorted(
        [c for c in chunks if not c.pinned],
        key=lambda c: c.final_score,
        reverse=True,
    )

    pinned_tokens = sum(c.token_count for c in pinned)
    trace = {
        "chunks_pinned_critical": len(pinned),
        "chunks_removed_by_budget": 0,
        "budget_exceeded_by_pinned_content": pinned_tokens > token_budget,
    }

    kept = list(pinned)
    remaining = token_budget - pinned_tokens

    for c in non_pinned:
        if c.token_count <= remaining:
            kept.append(c)
            remaining -= c.token_count
        else:
            trace["chunks_removed_by_budget"] += 1

    return kept, trace


# ---------------------------------------------------------------------------
# Orchestration entry point
# ---------------------------------------------------------------------------

def optimize_chunks(query: str, chunks: list[Chunk], token_budget: int,
                    llm_call_fn=None) -> tuple[list[Chunk], dict]:
    """
    Full Tier-2 pipeline: pin -> score -> compress -> budget -> coherence sort.
    """
    chunks_total = len(chunks)
    after_relevance = sum(c.token_count for c in chunks)

    # 1. Deduplication Filter (drop duplicates)
    duplicates = [c for c in chunks if c.is_duplicate_of is not None]
    chunks_merged_duplicate = len(duplicates)
    
    surviving_chunks = [c for c in chunks if c.is_duplicate_of is None]
    after_dedup = sum(c.token_count for c in surviving_chunks)

    # 2. Pinning
    surviving_chunks = apply_pinning(surviving_chunks)

    # 3. Scoring
    for c in surviving_chunks:
        c.importance_score = compute_importance_score(c)
        if not c.pinned:
            c.final_score = compute_final_score(c)

    # 4. Compression
    compressed_count = 0
    for i, c in enumerate(surviving_chunks):
        before = c.text
        try:
            compressed_chunk = compress_chunk(c, query, llm_call_fn=llm_call_fn)
        except Exception:
            compressed_chunk = c
        
        surviving_chunks[i] = compressed_chunk
        if compressed_chunk.compressed and compressed_chunk.text != before:
            compressed_count += 1

    after_compression = sum(c.token_count for c in surviving_chunks)

    # 5. Token Budget
    kept, budget_trace = enforce_budget(surviving_chunks, token_budget)

    # 6. Coherence Assembly (Option b)
    system_chunks = sorted([c for c in kept if c.tag == "SYSTEM"], key=lambda c: c.position)
    constraint_chunks = sorted([c for c in kept if c.tag == "PERSISTENT_CONSTRAINT"], key=lambda c: c.position)
    middle_chunks = sorted([c for c in kept if c.tag not in ("SYSTEM", "PERSISTENT_CONSTRAINT")], key=lambda c: c.position)
    assembled_chunks = system_chunks + middle_chunks + constraint_chunks

    trace = {
        "chunks_total": chunks_total,
        "chunks_merged_duplicate": chunks_merged_duplicate,
        "chunks_compressed": compressed_count,
        "revert_policy": "loss-only",
        **budget_trace,
        "stage_tokens": {
            "after_relevance": after_relevance,
            "after_dedup": after_dedup,
            "after_compression": after_compression,
            "after_budget": sum(c.token_count for c in assembled_chunks),
        },
    }
    return assembled_chunks, trace
