"""FastAPI application exposing the 3 decoupled middleware endpoints and dashboard."""
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    OptimizeRequest,
    OptimizeResponse,
    OptimizeAndAnswerResponse,
    CostComparison,
)
from app.tokenizer import count_tokens
from app.cost_model import (
    estimate_cost,
    calculate_cost_comparison,
)
from app.modules.person1_relevance import tier0_chunk_and_tag
from app.modules.person3_llm_eval import (
    person3_route_decision,
    person3_generate_answer,
    person3_evaluate_quality,
)
from app.orchestrator import run_pipeline

app = FastAPI(
    title="LLM Context Optimization Middleware",
    description="High-performance middleware for LLM context compression, routing, and coherence assembly",
    version="1.0.0",
)

# Enable CORS for local integration & web dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------
# Endpoint 1: POST /analyze (Cost Model & Routing Decision Only)
# ----------------------------------------------------------------------
@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_context(req: AnalyzeRequest):
    """
    Dry-run analysis endpoint:
    - Computes original token count
    - Estimates baseline LLM cost
    - Selects execution route (SKIP | LIGHT | FULL) without running heavy optimization or LLM inference.
    """
    original_tokens = count_tokens(req.context)
    chunks = tier0_chunk_and_tag(req.context)
    route = person3_route_decision(req.query, chunks, req.token_budget)
    estimated_cost = estimate_cost(original_tokens, model="gpt-4o")

    return AnalyzeResponse(
        original_tokens=original_tokens,
        estimated_cost=estimated_cost,
        route=route,
    )


# ----------------------------------------------------------------------
# Endpoint 2: POST /optimize (Full Pipeline, No LLM Inference)
# ----------------------------------------------------------------------
@app.post("/optimize", response_model=OptimizeResponse)
async def optimize_context(req: OptimizeRequest):
    """
    Primary optimization pipeline endpoint:
    - Runs Tier 0, Routing, Tier 1, Tier 2, and Coherence Assembly
    - Returns optimized context, token waterfall, and stage-by-stage latency trace.
    - Does NOT call the downstream LLM.
    """
    if req.token_budget <= 0:
        raise HTTPException(status_code=400, detail="token_budget must be a positive integer.")

    response = run_pipeline(
        query=req.query,
        context=req.context,
        token_budget=req.token_budget,
        simulate_tier2_failure=bool(req.simulate_tier2_failure),
    )
    return response


# ----------------------------------------------------------------------
# Endpoint 3: POST /optimize-and-answer (Demo Convenience Endpoint)
# ----------------------------------------------------------------------
@app.post("/optimize-and-answer", response_model=OptimizeAndAnswerResponse)
async def optimize_and_answer(req: OptimizeRequest):
    """
    Demo convenience endpoint:
    - Calls /optimize internally
    - Dispatches optimized prompt to downstream LLM
    - Performs quality evaluation and returns cost comparison.
    """
    if req.token_budget <= 0:
        raise HTTPException(status_code=400, detail="token_budget must be a positive integer.")

    # 1. Run optimization pipeline
    opt_resp = run_pipeline(
        query=req.query,
        context=req.context,
        token_budget=req.token_budget,
        simulate_tier2_failure=bool(req.simulate_tier2_failure),
    )

    # 2. Downstream LLM inference call
    answer_text, llm_latency_ms = person3_generate_answer(
        query=req.query,
        optimized_context=opt_resp.optimized_context,
        model=req.model or "gpt-4o",
    )

    # 3. Quality evaluation (wrapped in try/except, returns None on failure per Zero Placeholder Policy)
    quality_score = None
    try:
        quality_score = person3_evaluate_quality(
            query=req.query,
            optimized_context=opt_resp.optimized_context,
            answer=answer_text,
        )
    except Exception:
        quality_score = None

    # 4. Cost comparison
    cost_comp_data = calculate_cost_comparison(
        original_tokens=opt_resp.original_tokens,
        optimized_tokens=opt_resp.optimized_tokens,
        output_tokens=count_tokens(answer_text),
        model=req.model or "gpt-4o",
        route=opt_resp.route,
    )
    cost_comparison = CostComparison(**cost_comp_data)

    return OptimizeAndAnswerResponse(
        original_tokens=opt_resp.original_tokens,
        optimized_tokens=opt_resp.optimized_tokens,
        reduction_percentage=opt_resp.reduction_percentage,
        route=opt_resp.route,
        optimized_context=opt_resp.optimized_context,
        trace=opt_resp.trace,
        chunks_detail=opt_resp.chunks_detail,
        answer=answer_text,
        quality_score=quality_score,
        llm_latency_ms=llm_latency_ms,
        cost_comparison=cost_comparison,
    )


# ----------------------------------------------------------------------
# Health & Static Dashboard Mount
# ----------------------------------------------------------------------
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "llm-context-optimizer"}


# Static files mount for Dashboard
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def serve_dashboard():
        index_file = os.path.join(static_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"message": "Context Optimizer API is active. Dashboard UI file pending."}
