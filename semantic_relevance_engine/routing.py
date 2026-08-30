"""
Cost-aware routing decision: SKIP / LIGHT / FULL.

Called ONCE, before any pipeline stage runs, to decide how much work is
worth doing on this request. This is the piece that makes the "cost-aware"
part of the pitch literally true rather than aspirational -- without this,
every request runs the full pipeline unconditionally regardless of whether
it's worth it.

Calibration constants below are seeded from YOUR actual measured scenarios
in measure_token_savings.py, not guessed. Update them once you have more
benchmark runs (see design.md's benchmark step) -- these are a reasonable
MVP starting point, not a claim of optimality.
"""

from dataclasses import dataclass

# --- Calibration constants (from your real measured scenarios) ---

# Below this, optimization overhead isn't worth it regardless of content.
# This is an absolute floor, not cost-derived -- matches design.md's
# "500 tokens -> skip" example.
SKIP_TOKEN_FLOOR = 500

# From Scenario 1 (mostly irrelevant): 172 -> 66 via relevance+dedup alone
# = ~62% reduction. From Scenario 2 (everything relevant): 111 -> 88 =
# ~21% reduction. Real inputs will vary between these -- use a conservative
# mid-estimate for the ROUTING decision only (not a promise, just a guess
# to decide which tier to run).
LIGHT_REDUCTION_ESTIMATE = 0.35   # conservative: assume "everything relevant"-ish

# From Scenario 4: compression added ~15% additional reduction on top of
# relevance/dedup when there was low-relevance content to shrink.
FULL_ADDITIONAL_REDUCTION_ESTIMATE = 0.15

from semantic_relevance_engine.llm_provider import get_active_provider

provider = get_active_provider()
if provider == "rakha":
    # Reka Edge public pricing ($0.10 / 1M tokens)
    LLM_INPUT_COST_PER_TOKEN = 0.10 / 1_000_000
else:
    # Groq Llama-3.1-8b-instant pricing ($0.05 / 1M tokens)
    LLM_INPUT_COST_PER_TOKEN = 0.05 / 1_000_000

# Local/n-gram embedding tier costs effectively nothing. If you're on the
# OpenAI embedding tier instead, set this to a real per-chunk estimate.
EMBED_COST_PER_CHUNK = 0.0

# Compression cost: one Gemini call per non-pinned, non-duplicate chunk.
# Rough estimate -- refine using real chunk counts once you have more data.
ESTIMATED_CHUNKS_PER_1000_TOKENS = 8  # rough chunking density estimate
AVG_COMPRESSION_OUTPUT_RATIO = 0.5     # compressed output is ~half the input, on average

# Margin threshold: how much bigger does the estimated savings need to be
# than the optimizer's own cost before it's worth running FULL instead of
# just LIGHT? Expressed as a multiple (e.g. 2.0 = savings must be at least
# 2x the optimizer's own cost).
LIGHT_TO_FULL_MARGIN_MULTIPLIER = 1.5


@dataclass
class RoutingDecision:
    route: str  # "SKIP" | "LIGHT" | "FULL"
    original_tokens: int
    estimated_light_tokens: int
    estimated_full_tokens: int
    estimated_optimizer_cost: float
    estimated_savings: float
    reasoning: str


def decide_route(original_tokens: int, n_chunks: int | None = None,
                  token_budget: int | None = None) -> RoutingDecision:
    """
    The routing gate. Call this ONCE before running any pipeline stage.

    n_chunks: if you already know the chunk count (e.g. from a quick
    pre-chunk pass), pass it for a more accurate compression cost estimate.
    If not provided, estimates chunk count from token count.

    token_budget: if provided and original_tokens exceeds it, budget-fit
    takes priority over pure dollar-cost economics -- see the note below on
    why. This is the realistic case: you almost always have a hard budget
    from the caller, and "does it fit at all" matters more than "is
    compression cheaper than what it saves."
    """
    if n_chunks is None:
        n_chunks = max(1, round(original_tokens / 1000 * ESTIMATED_CHUNKS_PER_1000_TOKENS))

    # Hard floor: below this, never bother, regardless of budget.
    if original_tokens < SKIP_TOKEN_FLOOR:
        return RoutingDecision(
            route="SKIP",
            original_tokens=original_tokens,
            estimated_light_tokens=original_tokens,
            estimated_full_tokens=original_tokens,
            estimated_optimizer_cost=0.0,
            estimated_savings=0.0,
            reasoning=f"original_tokens ({original_tokens}) below SKIP_TOKEN_FLOOR "
                      f"({SKIP_TOKEN_FLOOR}) -- not worth optimizing regardless of content",
        )

    estimated_light_tokens = round(original_tokens * (1 - LIGHT_REDUCTION_ESTIMATE))
    estimated_full_tokens = round(
        original_tokens * (1 - LIGHT_REDUCTION_ESTIMATE - FULL_ADDITIONAL_REDUCTION_ESTIMATE)
    )

    # --- Budget-fit override: takes priority over cost-margin economics. ---
    # If the content doesn't even fit in the caller's budget, the question
    # isn't "is compression cheaper than its savings" -- it's "can we retain
    # more USEFUL information within the budget than dropping chunks alone
    # would give us." Compression's real value here is packing more relevant
    # content into a fixed budget, not dollar savings (see measured result:
    # 6 compressed chunks fit vs. 4 uncompressed at the same budget).
    if token_budget is not None and original_tokens > token_budget:
        if estimated_light_tokens <= token_budget:
            return RoutingDecision(
                route="LIGHT",
                original_tokens=original_tokens,
                estimated_light_tokens=estimated_light_tokens,
                estimated_full_tokens=estimated_full_tokens,
                estimated_optimizer_cost=n_chunks * EMBED_COST_PER_CHUNK,
                estimated_savings=0.0,
                reasoning=f"content ({original_tokens}t) exceeds token_budget ({token_budget}t), "
                          f"but relevance+dedup alone is estimated to bring it under budget "
                          f"(~{estimated_light_tokens}t) -- compression not needed to fit",
            )
        else:
            avg_chunk_tokens = original_tokens / n_chunks
            full_cost = n_chunks * EMBED_COST_PER_CHUNK + n_chunks * (
                avg_chunk_tokens * LLM_INPUT_COST_PER_TOKEN
                + avg_chunk_tokens * AVG_COMPRESSION_OUTPUT_RATIO * LLM_INPUT_COST_PER_TOKEN
            )
            return RoutingDecision(
                route="FULL",
                original_tokens=original_tokens,
                estimated_light_tokens=estimated_light_tokens,
                estimated_full_tokens=estimated_full_tokens,
                estimated_optimizer_cost=full_cost,
                estimated_savings=0.0,
                reasoning=f"content ({original_tokens}t) exceeds token_budget ({token_budget}t) "
                          f"even after estimated relevance+dedup (~{estimated_light_tokens}t) -- "
                          f"compression needed to retain more useful content within budget "
                          f"than dropping chunks alone would allow",
            )

    # Optimizer cost: LIGHT path is ~free (local embeddings, no LLM calls).
    # FULL path additionally costs one compression call per chunk.
    light_cost = n_chunks * EMBED_COST_PER_CHUNK
    # rough compression cost: assume most chunks aren't pinned and get sent
    # to the LLM; input = original chunk size, output = ~half that.
    avg_chunk_tokens = original_tokens / n_chunks
    full_cost = light_cost + n_chunks * (
        avg_chunk_tokens * LLM_INPUT_COST_PER_TOKEN
        + avg_chunk_tokens * AVG_COMPRESSION_OUTPUT_RATIO * LLM_INPUT_COST_PER_TOKEN
    )

    savings_from_light = (original_tokens - estimated_light_tokens) * LLM_INPUT_COST_PER_TOKEN
    savings_from_full = (original_tokens - estimated_full_tokens) * LLM_INPUT_COST_PER_TOKEN
    additional_savings_from_full = savings_from_full - savings_from_light

    if savings_from_light <= light_cost:
        # LIGHT path itself isn't worth it (rare, since light_cost is ~0,
        # but keeps the logic correct if you ever add a paid embedding tier)
        return RoutingDecision(
            route="SKIP",
            original_tokens=original_tokens,
            estimated_light_tokens=estimated_light_tokens,
            estimated_full_tokens=estimated_full_tokens,
            estimated_optimizer_cost=light_cost,
            estimated_savings=savings_from_light,
            reasoning="estimated LIGHT-path savings don't exceed even the LIGHT-path cost",
        )

    if additional_savings_from_full > full_cost * LIGHT_TO_FULL_MARGIN_MULTIPLIER:
        return RoutingDecision(
            route="FULL",
            original_tokens=original_tokens,
            estimated_light_tokens=estimated_light_tokens,
            estimated_full_tokens=estimated_full_tokens,
            estimated_optimizer_cost=full_cost,
            estimated_savings=savings_from_full,
            reasoning=f"additional savings from compression (${additional_savings_from_full:.6f}) "
                      f"exceed {LIGHT_TO_FULL_MARGIN_MULTIPLIER}x the full-path cost "
                      f"(${full_cost:.6f})",
        )

    return RoutingDecision(
        route="LIGHT",
        original_tokens=original_tokens,
        estimated_light_tokens=estimated_light_tokens,
        estimated_full_tokens=estimated_full_tokens,
        estimated_optimizer_cost=light_cost,
        estimated_savings=savings_from_light,
        reasoning="relevance+dedup alone is worthwhile, but compression's additional "
                  "savings don't clearly justify its own cost for this input size",
    )


if __name__ == "__main__":
    print("=== Without token_budget (pure cost-margin logic) ===")
    test_cases = [
        ("tiny context", 300, None, None),
        ("medium, low-relevance-heavy", 5000, 40, None),
        ("large, mostly relevant", 20000, 60, None),
        ("huge context", 100000, 200, None),
    ]
    for name, tokens, chunks, budget in test_cases:
        decision = decide_route(tokens, chunks, budget)
        print(f"\n{name} ({tokens} tokens, {chunks or 'auto'} chunks, budget={budget}):")
        print(f"  ROUTE: {decision.route}")
        print(f"  reasoning: {decision.reasoning}")

    print("\n\n=== With token_budget (budget-fit takes priority) ===")
    budget_cases = [
        ("fits comfortably in budget", 5000, 40, 8000),
        ("exceeds budget, light alone should fit", 5000, 40, 3800),
        ("exceeds budget, needs full compression to fit", 20000, 60, 5000),
        ("huge context, tight budget", 100000, 200, 3000),
    ]
    for name, tokens, chunks, budget in budget_cases:
        decision = decide_route(tokens, chunks, budget)
        print(f"\n{name} ({tokens} tokens, budget={budget}):")
        print(f"  ROUTE: {decision.route}")
        print(f"  reasoning: {decision.reasoning}")
