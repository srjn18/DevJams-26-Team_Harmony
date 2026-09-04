"""Person 1 Module: Tier 0 (Chunking & Tagging) and Tier 1 (Relevance & Deduplication)."""
import re
import math
from typing import List, Tuple
from collections import Counter
from app.schemas import ChunkInfo
from app.tokenizer import count_tokens

# Patterns for semantic tagging and critical protection
SYSTEM_PATTERNS = [
    r"^(system:|you are|role:|instructions?:|act as)",
    r"^#+ (system|role|persona|instructions)",
]
CONSTRAINT_PATTERNS = [
    r"\b(must not|do not|cannot|never|prohibited|mandatory|shall not|do not use|no mongodb|do not modify)\b",
    r"^(constraint|rule|guardrail|requirement|system|pinned):?",
    r"^#+ (constraints|rules|guardrails|requirements)",
]
CODE_PATTERNS = [
    r"```[\s\S]*?```",
    r"\b(def |class |import |from \w+ import|function |const |let |var |return |<script|SELECT .* FROM)\b",
]
DIALOGUE_PATTERNS = [
    r"^(user|assistant|human|ai|agent|customer|support|client):\s*",
]


def _is_critical_chunk(text: str, tag: str) -> bool:
    """Determine if chunk contains critical instructions, system prompts, or constraints."""
    if tag in ("system", "constraint"):
        return True
    text_lower = text.lower().strip()
    for pat in SYSTEM_PATTERNS:
        if re.search(pat, text_lower, re.IGNORECASE | re.MULTILINE):
            return True
    for pat in CONSTRAINT_PATTERNS:
        if re.search(pat, text_lower, re.IGNORECASE | re.MULTILINE):
            return True
    return False


def _detect_tag(text: str) -> str:
    """Detect semantic tag for a chunk."""
    text_lower = text.lower().strip()
    for pat in SYSTEM_PATTERNS:
        if re.search(pat, text_lower, re.IGNORECASE | re.MULTILINE):
            return "system"
    for pat in CONSTRAINT_PATTERNS:
        if re.search(pat, text_lower, re.IGNORECASE | re.MULTILINE):
            return "constraint"
    for pat in CODE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return "code"
    for pat in DIALOGUE_PATTERNS:
        if re.search(pat, text_lower, re.IGNORECASE | re.MULTILINE):
            return "dialogue"
    if text.strip().startswith(("#", "-", "*", "1.", "2.", "•")):
        return "fact"
    return "generic"


# ----------------------------------------------------------------------
# Tier 0: Deterministic Chunking & Tagging (Zero Paid Calls)
# ----------------------------------------------------------------------
def tier0_chunk_and_tag(context: str) -> List[ChunkInfo]:
    """
    Split context into semantically bounded chunks and tag each chunk.
    Maintains original 0-indexed position and marks critical instructions.
    """
    if not context or not context.strip():
        return []

    # Preserve code blocks and split by double newlines or section headers [...] / #
    raw_blocks = re.split(r"\n\s*\n+|(?<=\n)(?=\[[A-Z0-9_\-\s]+\]|#+\s+)", context.strip())
    chunks: List[ChunkInfo] = []
    
    pos = 0
    for block in raw_blocks:
        block_text = block.strip()
        if not block_text:
            continue
        
        # If block has multiple lines and contains a mixture of critical and non-critical lines, split lines
        lines = [ln.strip() for ln in block_text.splitlines() if ln.strip()]
        if len(lines) > 1 and any(_is_critical_chunk(ln, _detect_tag(ln)) for ln in lines):
            for ln in lines:
                tag = _detect_tag(ln)
                is_crit = _is_critical_chunk(ln, tag)
                tokens = count_tokens(ln)
                chunks.append(ChunkInfo(
                    id=f"chk_{pos}",
                    position=pos,
                    text=ln,
                    original_text=ln,
                    tag=tag,
                    is_critical=is_crit,
                    relevance_score=1.0,
                    token_count=tokens,
                    action_taken="pinned" if is_crit else "kept"
                ))
                pos += 1
            continue

        # If block is exceptionally large (> 350 words) and not code, split by sentences
        if len(block_text.split()) > 350 and not block_text.startswith("```"):
            sub_blocks = re.split(r"(?<=[.!?])\s+", block_text)
            current_sub = []
            current_len = 0
            for sb in sub_blocks:
                current_sub.append(sb)
                current_len += len(sb.split())
                if current_len >= 150:
                    sub_text = " ".join(current_sub).strip()
                    tag = _detect_tag(sub_text)
                    is_crit = _is_critical_chunk(sub_text, tag)
                    tokens = count_tokens(sub_text)
                    chunks.append(ChunkInfo(
                        id=f"chk_{pos}",
                        position=pos,
                        text=sub_text,
                        original_text=sub_text,
                        tag=tag,
                        is_critical=is_crit,
                        relevance_score=1.0,
                        token_count=tokens,
                        action_taken="pinned" if is_crit else "kept"
                    ))
                    pos += 1
                    current_sub = []
                    current_len = 0
            if current_sub:
                sub_text = " ".join(current_sub).strip()
                tag = _detect_tag(sub_text)
                is_crit = _is_critical_chunk(sub_text, tag)
                tokens = count_tokens(sub_text)
                chunks.append(ChunkInfo(
                    id=f"chk_{pos}",
                    position=pos,
                    text=sub_text,
                    original_text=sub_text,
                    tag=tag,
                    is_critical=is_crit,
                    relevance_score=1.0,
                    token_count=tokens,
                    action_taken="pinned" if is_crit else "kept"
                ))
                pos += 1
        else:
            tag = _detect_tag(block_text)
            is_crit = _is_critical_chunk(block_text, tag)
            tokens = count_tokens(block_text)
            chunks.append(ChunkInfo(
                id=f"chk_{pos}",
                position=pos,
                text=block_text,
                original_text=block_text,
                tag=tag,
                is_critical=is_crit,
                relevance_score=1.0,
                token_count=tokens,
                action_taken="pinned" if is_crit else "kept"
            ))
            pos += 1

    return chunks


def _stem(word: str) -> str:
    """Lightweight deterministic word normalizer/stemmer."""
    w = word.lower().strip()
    for suffix in ("ing", "tion", "tions", "ment", "ments", "ies", "es", "s", "ed", "al", "able"):
        if w.endswith(suffix) and len(w) > len(suffix) + 2:
            return w[:-len(suffix)]
    return w


def _compute_similarity(text_a: str, text_b: str) -> float:
    """Compute semantic term and subword similarity between two texts."""
    raw_a = re.findall(r"\w+", text_a.lower())
    raw_b = re.findall(r"\w+", text_b.lower())
    if not raw_a or not raw_b:
        return 0.0

    stems_a = [_stem(w) for w in raw_a]
    stems_b = [_stem(w) for w in raw_b]

    vec_a = Counter(stems_a)
    vec_b = Counter(stems_b)
    common = set(vec_a.keys()) & set(vec_b.keys())
    if not common:
        return 0.0

    dot = sum(vec_a[w] * vec_b[w] for w in common)
    mag_a = math.sqrt(sum(v ** 2 for v in vec_a.values()))
    mag_b = math.sqrt(sum(v ** 2 for v in vec_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _compute_relevance(query: str, chunk_text: str) -> float:
    """
    Compute hybrid relevance score incorporating stem cosine similarity
    and query keyword coverage so that extraction queries never drop matching context chunks.
    """
    if not query or not query.strip():
        return 1.0

    raw_sim = _compute_similarity(query, chunk_text)

    stopwords = {
        "what", "where", "when", "which", "who", "whom", "whose", "why", "how",
        "this", "that", "these", "those", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "can", "could", "should",
        "would", "will", "shall", "may", "might", "must", "and", "or", "but", "if",
        "then", "else", "for", "with", "about", "against", "between", "into", "through",
        "during", "before", "after", "above", "below", "to", "from", "up", "down", "in",
        "out", "on", "off", "over", "under", "again", "further", "once", "here", "there",
        "the", "a", "an"
    }
    q_words = [w.lower().strip(",.?!;:()[]{}") for w in query.split()]
    key_words = [w for w in q_words if len(w) >= 3 and w not in stopwords]

    if not key_words:
        return raw_sim

    c_text_lower = chunk_text.lower()
    matches = sum(1 for kw in key_words if _stem(kw) in c_text_lower or kw in c_text_lower)
    keyword_coverage = matches / len(key_words)

    hybrid_score = max(raw_sim, keyword_coverage * 0.85)
    return round(hybrid_score, 4)


def tier1_filter_relevance(
    query: str,
    chunks: List[ChunkInfo],
    relevance_threshold: float = 0.10
) -> Tuple[List[ChunkInfo], int]:
    """
    Score relevance against query. Keep critical chunks and high-scoring chunks.
    Returns (surviving_chunks, chunks_removed_irrelevant_count).
    """
    surviving: List[ChunkInfo] = []
    removed_count = 0

    query_clean = query.strip()
    
    for chunk in chunks:
        # Pinned / Critical chunks are never dropped by relevance
        if chunk.is_critical:
            chunk.relevance_score = 1.0
            chunk.action_taken = "pinned"
            surviving.append(chunk)
            continue

        score = _compute_relevance(query_clean, chunk.text)
        chunk.relevance_score = score
        
        # Keep chunk if it has keyword coverage/relevance or if query is empty
        if score >= relevance_threshold or not query_clean:
            chunk.action_taken = "kept"
            surviving.append(chunk)
        else:
            chunk.action_taken = "filtered_irrelevant"
            removed_count += 1

    # Safety: If all non-critical chunks were removed, keep at least top-1 most relevant chunk
    if not any(not c.is_critical for c in surviving) and any(not c.is_critical for c in chunks):
        non_crit = [c for c in chunks if not c.is_critical]
        best_chunk = max(non_crit, key=lambda c: c.relevance_score)
        best_chunk.action_taken = "kept"
        surviving.append(best_chunk)
        removed_count = max(0, removed_count - 1)

    return surviving, removed_count


def tier1_deduplicate(
    chunks: List[ChunkInfo],
    dedup_threshold: float = 0.85
) -> Tuple[List[ChunkInfo], int]:
    """
    Identify and eliminate near-duplicate or redundant chunks.
    Returns (deduped_chunks, chunks_merged_duplicate_count).
    """
    deduped: List[ChunkInfo] = []
    merged_count = 0

    for chunk in chunks:
        is_dup = False
        for existing in deduped:
            sim = _compute_similarity(chunk.text, existing.text)
            if sim >= dedup_threshold:
                is_dup = True
                chunk.action_taken = "merged_duplicate"
                merged_count += 1
                # If current chunk is critical, ensure surviving existing chunk remains critical & detailed
                if chunk.is_critical:
                    existing.is_critical = True
                    if existing.action_taken != "pinned":
                        existing.action_taken = "pinned"
                if chunk.token_count > existing.token_count:
                    existing.text = chunk.text
                    existing.token_count = chunk.token_count
                break

        if not is_dup:
            deduped.append(chunk)

    return deduped, merged_count
