"""Tests for prompt coherence assembly and position-based ordering."""
from app.orchestrator import assemble_coherent_context
from app.schemas import ChunkInfo

def test_coherence_assembly_order():
    """
    Surviving chunks must be reordered by their original position field,
    with System blocks at the top and Constraints at the bottom (pre-query),
    NOT sorted by relevance score.
    """
    chunks = [
        # Chunk with high relevance score but later position
        ChunkInfo(
            id="chk_2",
            position=2,
            text="Body paragraph 2: Detailed metric analysis.",
            tag="generic",
            relevance_score=0.98,
            token_count=10,
        ),
        # Constraint chunk with middle position
        ChunkInfo(
            id="chk_3",
            position=3,
            text="Constraint: DO NOT leak customer PII.",
            tag="constraint",
            is_critical=True,
            relevance_score=1.0,
            token_count=8,
        ),
        # Chunk with lower relevance score but earlier position
        ChunkInfo(
            id="chk_1",
            position=1,
            text="Body paragraph 1: Introduction and background.",
            tag="generic",
            relevance_score=0.45,
            token_count=10,
        ),
        # System chunk
        ChunkInfo(
            id="chk_0",
            position=0,
            text="System: You are an enterprise assistant.",
            tag="system",
            is_critical=True,
            relevance_score=1.0,
            token_count=8,
        ),
    ]

    assembled = assemble_coherent_context(chunks, query="Summarize metrics")

    lines = [line.strip() for line in assembled.split("\n\n") if line.strip()]

    # 1. First block MUST be system
    assert "System: You are an enterprise assistant." in lines[0]

    # 2. Body paragraph 1 (pos 1) MUST appear before Body paragraph 2 (pos 2), even though pos 2 had higher relevance!
    pos1_idx = -1
    pos2_idx = -1
    for idx, l in enumerate(lines):
        if "Body paragraph 1" in l:
            pos1_idx = idx
        if "Body paragraph 2" in l:
            pos2_idx = idx

    assert pos1_idx != -1 and pos2_idx != -1
    assert pos1_idx < pos2_idx, "Body chunks must be sorted by position, not by relevance score!"

    # 3. Constraint MUST appear at the end (immediately before query)
    assert "Constraint: DO NOT leak customer PII." in lines[-1]
