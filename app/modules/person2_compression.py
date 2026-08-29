"""Person 2 Module: Tier 2 (Critical Protection, Compression & Budget Enforcer)."""
import re
from typing import List, Tuple
from app.schemas import ChunkInfo
from app.tokenizer import count_tokens, truncate_to_tokens

# Filler and boilerplate phrases to condense in extractive compression
BOILERPLATE_PATTERNS = [
    (r"\b(it is important to note that|please be aware that|as previously mentioned|as stated above|in order to|due to the fact that)\b", ""),
    (r"\b(for the purpose of|in the event that|at this point in time|with reference to)\b", ""),
    (r"\s{2,}", " "),
]


def _compress_chunk_text(text: str, target_ratio: float = 0.65) -> str:
    """
    Compress a single non-critical chunk extractively by trimming filler
    and retaining high-information sentences.
    """
    cleaned = text
    for pattern, replacement in BOILERPLATE_PATTERNS:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    if len(sentences) <= 1:
        # For single sentence / short line, keep core
        words = cleaned.split()
        if len(words) > 15:
            keep_words = int(len(words) * target_ratio)
            return " ".join(words[:keep_words])
        return cleaned

    # Keep key sentences (first, last, and informative ones)
    target_count = max(1, int(math_ceil(len(sentences) * target_ratio)))
    selected_sentences = sentences[:target_count]
    return " ".join(selected_sentences).strip()


def math_ceil(x: float) -> int:
    import math
    return math.ceil(x)


def tier2_compress(
    chunks: List[ChunkInfo],
    simulate_failure: bool = False
) -> Tuple[List[ChunkInfo], int]:
    """
    Tier 2 Compression:
    - Preserves pinned/critical chunks without modification.
    - Compresses non-critical chunks.
    - Returns (compressed_chunks, chunks_compressed_count).
    """
    if simulate_failure:
        raise RuntimeError("Person 2 Compression Module encountered an unhandled timeout / execution error.")

    compressed: List[ChunkInfo] = []
    compressed_count = 0

    for chunk in chunks:
        # Pinned / Critical chunks are NEVER compressed
        if chunk.is_critical:
            compressed.append(chunk)
            continue

        orig_text = chunk.text
        new_text = _compress_chunk_text(orig_text, target_ratio=0.60)
        new_tokens = count_tokens(new_text)

        if new_tokens < chunk.token_count:
            chunk.text = new_text
            chunk.token_count = new_tokens
            chunk.action_taken = "compressed"
            compressed_count += 1

        compressed.append(chunk)

    return compressed, compressed_count


def tier2_enforce_budget(
    chunks: List[ChunkInfo],
    token_budget: int
) -> List[ChunkInfo]:
    """
    Fit surviving chunks into token_budget:
    - Pinned chunks are prioritized and kept.
    - Remaining budget is allocated to non-pinned chunks in original order / relevance.
    - Any excess is trimmed.
    """
    if token_budget <= 0:
        return chunks

    total_tokens = sum(c.token_count for c in chunks)
    if total_tokens <= token_budget:
        return chunks

    # Separate pinned vs non-pinned
    pinned = [c for c in chunks if c.is_critical]
    non_pinned = [c for c in chunks if not c.is_critical]

    pinned_tokens = sum(c.token_count for c in pinned)
    remaining_budget = max(0, token_budget - pinned_tokens)

    # Sort non-pinned by relevance score descending to pick best chunks
    non_pinned_by_relevance = sorted(non_pinned, key=lambda c: c.relevance_score, reverse=True)

    kept_non_pinned: List[ChunkInfo] = []
    used_budget = 0

    for chunk in non_pinned_by_relevance:
        if used_budget + chunk.token_count <= remaining_budget:
            kept_non_pinned.append(chunk)
            used_budget += chunk.token_count
        elif used_budget < remaining_budget:
            # Partial allocation
            avail = remaining_budget - used_budget
            if avail > 15: # worth including partial
                truncated = truncate_to_tokens(chunk.text, avail)
                chunk.text = truncated
                chunk.token_count = count_tokens(truncated)
                kept_non_pinned.append(chunk)
                used_budget += chunk.token_count
            break

    # Merge surviving chunks
    surviving = pinned + kept_non_pinned
    return surviving
