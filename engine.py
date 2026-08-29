"""
Semantic Relevance Engine for LLM Context Optimization Middleware.

Implements chunk relevance ranking, cosine similarity scoring, and fact-preserving
pairwise deduplication.
"""

import re
import numpy as np
from typing import List, Optional, Set
from .models import Chunk
from .chunker import chunk_context
from .embedder import Embedder

# Configurable default thresholds
DEFAULT_RELEVANCE_THRESHOLD = 0.55
DEFAULT_DEDUP_THRESHOLD = 0.85

# Polarity and fact-transition patterns for the dedup guard
CONTRAST_KEYWORDS = {
    "not", "never", "no", "neither", "nor", "cannot", "can't", "won't", "don't",
    "doesn't", "isn't", "aren't", "shouldn't", "without", "instead", "migrating",
    "migration", "migrated", "deprecated", "replacing", "replaced", "abandoned",
    "moving off", "transitioning from", "disabled", "removed"
}

CONTRAST_REGEX = re.compile(
    r'\b(?:' + '|'.join(re.escape(k) for k in CONTRAST_KEYWORDS) + r')\b',
    re.IGNORECASE
)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if not vec1 or not vec2:
        return 0.0
    v1 = np.array(vec1, dtype=np.float32)
    v2 = np.array(vec2, dtype=np.float32)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 < 1e-9 or norm2 < 1e-9:
        return 0.0
    sim = float(np.dot(v1, v2) / (norm1 * norm2))
    return max(0.0, min(1.0, sim))


def has_fact_conflict(text1: str, text2: str) -> bool:
    """
    Guard: Determine if two semantically close texts have conflicting facts or opposing polarity
    (e.g., 'using Postgres' vs 'migrating off Postgres' or 'feature enabled' vs 'feature disabled').
    Returns True if a fact conflict is detected (preventing deduplication).
    """
    t1 = text1.lower()
    t2 = text2.lower()

    matches1 = set(CONTRAST_REGEX.findall(t1))
    matches2 = set(CONTRAST_REGEX.findall(t2))

    # If one text contains contrast/negation/migration indicators and the other does not
    if bool(matches1) != bool(matches2):
        return True

    # If both contain contrast keywords but different specific polarities/terms
    diff = matches1.symmetric_difference(matches2)
    if diff:
        return True

    return False


def _choose_canonical_chunk(c1: Chunk, c2: Chunk) -> tuple[Chunk, Chunk]:
    """
    Choose the more information-dense chunk to keep as canonical.
    Winner criteria:
    1. Higher information density (longer text length)
    2. Higher relevance score
    3. Earlier original position
    Returns (canonical_winner, duplicate_loser).
    """
    len1, len2 = len(c1.text.strip()), len(c2.text.strip())
    if len1 > len2:
        return c1, c2
    elif len2 > len1:
        return c2, c1
    else:
        # Tie-break on relevance score
        if c1.relevance_score > c2.relevance_score:
            return c1, c2
        elif c2.relevance_score > c1.relevance_score:
            return c2, c1
        else:
            # Tie-break on earlier position
            return (c1, c2) if c1.position <= c2.position else (c2, c1)


def perform_deduplication(
    chunks: List[Chunk],
    dedup_threshold: float = DEFAULT_DEDUP_THRESHOLD
) -> None:
    """
    Perform pairwise chunk-to-chunk cosine similarity comparison.
    Marks duplicates by setting `is_duplicate_of` to the ID of the kept canonical chunk.
    Does NOT drop any chunks.
    """
    n = len(chunks)
    if n < 2:
        return

    # Pairwise comparison across chunks
    for i in range(n):
        c1 = chunks[i]
        # If c1 is already marked as a duplicate, skip initiating comparisons
        if c1.is_duplicate_of is not None:
            continue

        for j in range(i + 1, n):
            c2 = chunks[j]
            if c2.is_duplicate_of is not None:
                continue

            # Compute similarity between c1 and c2 embeddings
            sim = cosine_similarity(c1.embedding, c2.embedding)

            if sim >= dedup_threshold:
                # Guard against fact conflicts (e.g. 'using Postgres' vs 'migrating off Postgres')
                if has_fact_conflict(c1.text, c2.text):
                    continue

                canonical, duplicate = _choose_canonical_chunk(c1, c2)
                duplicate.is_duplicate_of = canonical.id


def rank_chunks(
    query: str,
    context: str,
    relevance_threshold: float = DEFAULT_RELEVANCE_THRESHOLD,
    dedup_threshold: float = DEFAULT_DEDUP_THRESHOLD,
) -> List[Chunk]:
    """
    Core function for the Semantic Relevance Engine.
    
    1. Splits context into structured chunks.
    2. Embeds query and all chunks.
    3. Computes relevance scores (cosine similarity to query).
    4. Performs pairwise deduplication with fact-conflict protection.
    5. Returns all chunks sorted by relevance_score descending (zero-drop policy).
    """
    if not context or not context.strip():
        return []

    # 1. Chunking and source tagging
    chunks = chunk_context(context)
    if not chunks:
        return []

    # 2. Embeddings
    query_embedding = Embedder.embed_query(query)
    chunk_texts = [c.text for c in chunks]
    chunk_embeddings = Embedder.embed_chunks(chunk_texts)

    # 3. Relevance Scoring
    for chunk, emb in zip(chunks, chunk_embeddings):
        chunk.embedding = emb
        chunk.relevance_score = round(cosine_similarity(query_embedding, emb), 4)

    # 4. Pairwise Deduplication (between chunks, using separate DEDUP_THRESHOLD)
    perform_deduplication(chunks, dedup_threshold=dedup_threshold)

    # 5. Output: sorted by relevance_score descending (zero-drop guarantee)
    ranked_chunks = sorted(chunks, key=lambda c: c.relevance_score, reverse=True)
    return ranked_chunks
