"""Master Pipeline Orchestrator for LLM Context Optimization Middleware."""
import time
import logging
from typing import List, Optional, Tuple

from app.schemas import (
    ChunkInfo,
    OptimizationTrace,
    OptimizeResponse,
    StageLatencyMs,
    StageTokens,
)
from app.tokenizer import count_tokens, truncate_to_tokens
from app.modules.person1_relevance import (
    tier0_chunk_and_tag,
    tier1_filter_relevance,
    tier1_deduplicate,
)
from app.modules.person2_compression import (
    tier2_compress,
    tier2_enforce_budget,
)
from app.modules.person3_llm_eval import (
    person3_route_decision,
)

logger = logging.getLogger("orchestrator")


def assemble_coherent_context(surviving_chunks: List[ChunkInfo], query: str = "") -> str:
    """
    Stage 5: Coherence Assembly.
    - Reorder surviving chunks strictly by their original `position` field (NOT by relevance score).
    - Fixed slot placement:
        1. System block first (system instructions / persona / top header).
        2. Body / fact / dialogue / code chunks in original sequence order.
        3. Constraints / security rules immediately before the query text.
    """
    if not surviving_chunks:
        return ""

    # Sort chunks primarily by original position
    sorted_by_pos = sorted(surviving_chunks, key=lambda c: c.position)

    system_chunks = [c for c in sorted_by_pos if c.tag == "system"]
    constraint_chunks = [c for c in sorted_by_pos if c.tag == "constraint"]
    body_chunks = [c for c in sorted_by_pos if c.tag not in ("system", "constraint")]

    sections = []

    # 1. System block first
    if system_chunks:
        for c in system_chunks:
            sections.append(c.text.strip())

    # 2. Body / Context in original sequence
    if body_chunks:
        for c in body_chunks:
            sections.append(c.text.strip())

    # 3. Constraints immediately before the query
    if constraint_chunks:
        for c in constraint_chunks:
            sections.append(c.text.strip())

    return "\n\n".join(sections).strip()


def run_pipeline(
    query: str,
    context: str,
    token_budget: int,
    simulate_tier2_failure: bool = False
) -> OptimizeResponse:
    """
    Run the 6-stage optimization pipeline in strict sequential order.
    """
    start_total = time.perf_counter()
    original_tokens = count_tokens(context)

    # Latency trackers
    lat_chunking = 0.0
    lat_relevance = 0.0
    lat_dedup = 0.0
    lat_compression = 0.0
    lat_assembly = 0.0

    # Counters
    chunks_removed_irrelevant = 0
    chunks_merged_duplicate = 0
    chunks_compressed = 0
    chunks_pinned_critical = 0

    fallback_triggered = False
    fallback_reason: Optional[str] = None

    # ------------------------------------------------------------------
    # Stage 1: Tier 0 (Person 1's chunking/tagging, deterministic, no paid calls)
    # ------------------------------------------------------------------
    t0_start = time.perf_counter()
    chunks = tier0_chunk_and_tag(context)
    lat_chunking = round((time.perf_counter() - t0_start) * 1000.0, 3)

    chunks_total = len(chunks)
    chunks_pinned_critical = sum(1 for c in chunks if c.is_critical)
    tokens_original = sum(c.token_count for c in chunks) if chunks else original_tokens

    # ------------------------------------------------------------------
    # Stage 2: Routing decision (Person 3's cost model)
    # ------------------------------------------------------------------
    route = person3_route_decision(query, chunks, token_budget)

    # Waterfall token markers
    tokens_after_relevance = tokens_original
    tokens_after_dedup = tokens_original
    tokens_after_compression = tokens_original
    tokens_after_budget = tokens_original

    all_tracked_chunks = [c.model_copy() for c in chunks]

    # Handle SKIP route short-circuit
    if route == "SKIP":
        # Stage 3 and Stage 4 skipped entirely
        surviving_chunks = chunks
        if token_budget > 0 and tokens_original > token_budget:
            surviving_chunks = tier2_enforce_budget(chunks, token_budget)
        
        t_asm_start = time.perf_counter()
        optimized_context = assemble_coherent_context(surviving_chunks, query)
        lat_assembly = round((time.perf_counter() - t_asm_start) * 1000.0, 3)

        optimized_tokens = count_tokens(optimized_context)
        tokens_after_relevance = tokens_original
        tokens_after_dedup = tokens_original
        tokens_after_compression = tokens_original
        tokens_after_budget = optimized_tokens

        lat_total = round((time.perf_counter() - start_total) * 1000.0, 3)
        reduction_percentage = round(max(0.0, ((original_tokens - optimized_tokens) / max(1, original_tokens)) * 100.0), 2)

        return OptimizeResponse(
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            reduction_percentage=reduction_percentage,
            route=route,
            optimized_context=optimized_context,
            trace=OptimizationTrace(
                chunks_total=chunks_total,
                chunks_removed_irrelevant=0,
                chunks_merged_duplicate=0,
                chunks_compressed=0,
                chunks_pinned_critical=chunks_pinned_critical,
                stage_tokens=StageTokens(
                    original=tokens_original,
                    after_relevance=tokens_after_relevance,
                    after_dedup=tokens_after_dedup,
                    after_compression=tokens_after_compression,
                    after_budget=tokens_after_budget,
                ),
                stage_latency_ms=StageLatencyMs(
                    chunking=lat_chunking,
                    embedding_relevance=0.0,
                    dedup=0.0,
                    compression=0.0,
                    assembly=lat_assembly,
                    total=lat_total,
                ),
                fallback_triggered=False,
                fallback_reason=None,
            ),
            chunks_detail=all_tracked_chunks,
        )

    # ------------------------------------------------------------------
    # Stage 3: Tier 1 (Person 1's embeddings/relevance/dedup)
    # ------------------------------------------------------------------
    t1_rel_start = time.perf_counter()
    rel_chunks, removed_count = tier1_filter_relevance(query, chunks)
    lat_relevance = round((time.perf_counter() - t1_rel_start) * 1000.0, 3)
    chunks_removed_irrelevant = removed_count
    tokens_after_relevance = sum(c.token_count for c in rel_chunks)

    t1_dedup_start = time.perf_counter()
    dedup_chunks, merged_count = tier1_deduplicate(rel_chunks)
    lat_dedup = round((time.perf_counter() - t1_dedup_start) * 1000.0, 3)
    chunks_merged_duplicate = merged_count
    tokens_after_dedup = sum(c.token_count for c in dedup_chunks)

    tier1_output_snapshot = [c.model_copy() for c in dedup_chunks]

    # If route is LIGHT, skip Stage 4 (compression)
    if route == "LIGHT":
        surviving_chunks = dedup_chunks
        if token_budget > 0:
            surviving_chunks = tier2_enforce_budget(dedup_chunks, token_budget)
        
        tokens_after_compression = tokens_after_dedup
        tokens_after_budget = sum(c.token_count for c in surviving_chunks)

        t_asm_start = time.perf_counter()
        optimized_context = assemble_coherent_context(surviving_chunks, query)
        lat_assembly = round((time.perf_counter() - t_asm_start) * 1000.0, 3)

        optimized_tokens = count_tokens(optimized_context)
        lat_total = round((time.perf_counter() - start_total) * 1000.0, 3)
        reduction_percentage = round(max(0.0, ((original_tokens - optimized_tokens) / max(1, original_tokens)) * 100.0), 2)

        return OptimizeResponse(
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            reduction_percentage=reduction_percentage,
            route=route,
            optimized_context=optimized_context,
            trace=OptimizationTrace(
                chunks_total=chunks_total,
                chunks_removed_irrelevant=chunks_removed_irrelevant,
                chunks_merged_duplicate=chunks_merged_duplicate,
                chunks_compressed=0,
                chunks_pinned_critical=chunks_pinned_critical,
                stage_tokens=StageTokens(
                    original=tokens_original,
                    after_relevance=tokens_after_relevance,
                    after_dedup=tokens_after_dedup,
                    after_compression=tokens_after_compression,
                    after_budget=tokens_after_budget,
                ),
                stage_latency_ms=StageLatencyMs(
                    chunking=lat_chunking,
                    embedding_relevance=lat_relevance,
                    dedup=lat_dedup,
                    compression=0.0,
                    assembly=lat_assembly,
                    total=lat_total,
                ),
                fallback_triggered=False,
                fallback_reason=None,
            ),
            chunks_detail=all_tracked_chunks,
        )

    # ------------------------------------------------------------------
    # Stage 4: Tier 2 (Person 2's critical-protection/compression/budget)
    # with Graceful Degradation / Fallback on any failure
    # ------------------------------------------------------------------
    t2_comp_start = time.perf_counter()
    try:
        compressed_chunks, comp_count = tier2_compress(
            dedup_chunks,
            simulate_failure=simulate_tier2_failure
        )
        lat_compression = round((time.perf_counter() - t2_comp_start) * 1000.0, 3)
        chunks_compressed = comp_count
        tokens_after_compression = sum(c.token_count for c in compressed_chunks)

        # Budget enforcer
        budgeted_chunks = tier2_enforce_budget(compressed_chunks, token_budget)
        tokens_after_budget = sum(c.token_count for c in budgeted_chunks)
        surviving_chunks = budgeted_chunks

    except Exception as e:
        # Graceful fallback: catch any Tier-2 failure, log reason, fall back to Tier 1 deduped output
        logger.warning(f"Tier-2 compression failed: {e}. Falling back to Tier-1 uncompressed output.")
        lat_compression = round((time.perf_counter() - t2_comp_start) * 1000.0, 3)
        fallback_triggered = True
        fallback_reason = f"Tier 2 compression failed ({type(e).__name__}: {str(e)})"
        
        # Fall back to Tier 1 snapshot and enforce budget by truncation
        fallback_chunks = [c.model_copy() for c in tier1_output_snapshot]
        surviving_chunks = tier2_enforce_budget(fallback_chunks, token_budget)
        tokens_after_compression = tokens_after_dedup
        tokens_after_budget = sum(c.token_count for c in surviving_chunks)

    # ------------------------------------------------------------------
    # Stage 5: Coherence Assembly
    # ------------------------------------------------------------------
    t_asm_start = time.perf_counter()
    optimized_context = assemble_coherent_context(surviving_chunks, query)
    lat_assembly = round((time.perf_counter() - t_asm_start) * 1000.0, 3)

    optimized_tokens = count_tokens(optimized_context)
    lat_total = round((time.perf_counter() - start_total) * 1000.0, 3)
    reduction_percentage = round(max(0.0, ((original_tokens - optimized_tokens) / max(1, original_tokens)) * 100.0), 2)

    # Update actions on all_tracked_chunks for inspector UI
    surviving_ids = {c.id: c for c in surviving_chunks}
    for orig_chk in all_tracked_chunks:
        if orig_chk.id in surviving_ids:
            orig_chk.action_taken = surviving_ids[orig_chk.id].action_taken
            orig_chk.text = surviving_ids[orig_chk.id].text
            orig_chk.token_count = surviving_ids[orig_chk.id].token_count

    return OptimizeResponse(
        original_tokens=original_tokens,
        optimized_tokens=optimized_tokens,
        reduction_percentage=reduction_percentage,
        route=route,
        optimized_context=optimized_context,
        trace=OptimizationTrace(
            chunks_total=chunks_total,
            chunks_removed_irrelevant=chunks_removed_irrelevant,
            chunks_merged_duplicate=chunks_merged_duplicate,
            chunks_compressed=chunks_compressed,
            chunks_pinned_critical=chunks_pinned_critical,
            stage_tokens=StageTokens(
                original=tokens_original,
                after_relevance=tokens_after_relevance,
                after_dedup=tokens_after_dedup,
                after_compression=tokens_after_compression,
                after_budget=tokens_after_budget,
            ),
            stage_latency_ms=StageLatencyMs(
                chunking=lat_chunking,
                embedding_relevance=lat_relevance,
                dedup=lat_dedup,
                compression=lat_compression,
                assembly=lat_assembly,
                total=lat_total,
            ),
            fallback_triggered=fallback_triggered,
            fallback_reason=fallback_reason,
        ),
        chunks_detail=all_tracked_chunks,
    )
