import os
import math
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    OptimizeRequest,
    OptimizeResponse,
    OptimizeAndAnswerResponse,
    ChunkDetail,
    StageTokens,
    StageLatency,
    TraceInfo,
    CostComparison,
)
from .providers import get_provider

app = FastAPI(title="Context Optimization Demo Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

provider = get_provider()

ROUTE_TOKEN_THRESHOLD = int(os.environ.get("ROUTE_TOKEN_THRESHOLD", "800"))


def estimate_tokens(text: str) -> int:
    # simple heuristic: 1 token ~= 4 chars
    return max(0, len(text) // 4)


def estimate_cost(tokens: int) -> float:
    # nominal cost per token for baseline demo
    return float(tokens) * 0.00001


def make_trace(original_tokens: int, optimized_tokens: int, fallback=False, reason=None):
    stage_tokens = StageTokens(
        original=original_tokens,
        after_relevance=max(0, int(original_tokens * 0.9)),
        after_dedup=max(0, int(original_tokens * 0.85)),
        after_compression=optimized_tokens,
        after_budget=optimized_tokens,
    )

    lat = StageLatency(
        total=123.4,
        chunking=12.3,
        embedding_relevance=23.4,
        dedup=10.0,
        compression=30.0,
        assembly=47.7,
    )

    trace = TraceInfo(
        fallback_triggered=fallback,
        fallback_reason=reason,
        stage_tokens=stage_tokens,
        stage_latency_ms=lat,
        chunks_total=10,
        chunks_removed_irrelevant=2,
        chunks_merged_duplicate=1,
        chunks_compressed=3,
        chunks_pinned_critical=1,
    )
    return trace


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    original_tokens = estimate_tokens(req.context)
    route = "FULL" if original_tokens > ROUTE_TOKEN_THRESHOLD else "LIGHT"
    est_cost = estimate_cost(original_tokens)
    return {"route": route, "original_tokens": original_tokens, "estimated_cost": est_cost}


@app.post("/optimize", response_model=OptimizeResponse)
async def optimize(req: OptimizeRequest):
    original_tokens = estimate_tokens(req.context)
    # attempt compression via provider
    try:
        compressed, compressed_tokens = provider.compress(req.query, req.context, req.token_budget)
    except Exception as e:
        # provider failed, fallback to mock behavior
        compressed = req.context[: req.token_budget * 4]
        compressed_tokens = estimate_tokens(compressed)

    # simulate tier2 failure
    fallback = False
    reason = None
    if getattr(req, "simulate_tier2_failure", False):
        fallback = True
        reason = "Simulated Tier-2 compression failure"

    reduction_pct = round(100.0 * (original_tokens - compressed_tokens) / max(1, original_tokens), 2)

    trace = make_trace(original_tokens, compressed_tokens, fallback, reason)

    # simplistic chunk detail
    chunks = [
        ChunkDetail(
            id=i + 1,
            position=i + 1,
            tag="generic",
            is_critical=(i == 0),
            token_count=max(1, compressed_tokens // max(1, 5)),
            relevance_score=0.5,
            action_taken="compressed",
            text=(compressed[:120] + "...") if len(compressed) > 120 else compressed,
        )
        for i in range(min(5, max(1, compressed_tokens // 10)))
    ]

    return {
        "route": ("FULL" if original_tokens > ROUTE_TOKEN_THRESHOLD else "LIGHT"),
        "original_tokens": original_tokens,
        "optimized_tokens": compressed_tokens,
        "reduction_percentage": reduction_pct,
        "trace": trace,
        "chunks_detail": chunks,
    }


@app.post("/optimize-and-answer", response_model=OptimizeAndAnswerResponse)
async def optimize_and_answer(req: OptimizeRequest):
    # Reuse optimize path for compression
    opt_resp = await optimize(req)

    # opt_resp is a dict-like; extract compressed token count and simulate compressed context
    optimized_tokens = opt_resp["optimized_tokens"]
    compressed_context = f"[OPTIMIZED_CONTEXT tokens={optimized_tokens}]"

    # call provider.answer
    try:
        answer_text, llm_latency = provider.answer(req.query, compressed_context)
    except Exception:
        answer_text, llm_latency = "[fallback answer]", 0.0

    # cost comparison
    baseline = estimate_cost(opt_resp["original_tokens"]) 
    optimizer_cost = estimate_cost(opt_resp["optimized_tokens"]) * 0.2
    optimized_llm_cost = estimate_cost(opt_resp["optimized_tokens"]) * 0.5
    total_optimized = optimizer_cost + optimized_llm_cost
    savings = round(100.0 * (baseline - total_optimized) / max(1e-6, baseline), 2) if baseline > 0 else 0.0

    cost_comp = CostComparison(
        baseline_cost=baseline,
        optimizer_cost=optimizer_cost,
        optimized_llm_cost=optimized_llm_cost,
        total_optimized_cost=total_optimized,
        savings_percentage=savings,
    )

    # build final response dict merging optimize results
    resp = dict(opt_resp)
    resp.update({
        "answer": answer_text,
        "quality_score": 0.9,
        "llm_latency_ms": llm_latency,
        "cost_comparison": cost_comp,
    })

    return resp
