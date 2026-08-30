import os
import json as py_json
from typing import Optional
from fastapi import FastAPI, HTTPException, Query

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


def resolve_optimize_request(
    body_req: Optional[OptimizeRequest] = None,
    query: Optional[str] = None,
    context: Optional[str] = None,
    token_budget: Optional[int] = None,
    model: Optional[str] = None,
    simulate_tier2_failure: Optional[bool] = None,
    json_str: Optional[str] = None,
) -> OptimizeRequest:
    """Helper to construct OptimizeRequest from either POST JSON body or GET query params/JSON string."""
    if body_req is not None and (body_req.context or body_req.query):
        return body_req

    if json_str:
        try:
            data = py_json.loads(json_str)
            return OptimizeRequest(
                query=data.get("query", query or ""),
                context=data.get("context", context or ""),
                token_budget=int(data.get("token_budget", token_budget or 100)),
                model=data.get("model", model or "gpt-4o"),
                simulate_tier2_failure=bool(data.get("simulate_tier2_failure", simulate_tier2_failure or False)),
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON in 'json' query parameter: {e}")

    q = query or ""
    c = context or ""
    b = token_budget if (token_budget is not None and token_budget > 0) else 100
    m = model or "gpt-4o"
    f = bool(simulate_tier2_failure)

    if not c and not q and body_req is not None:
        return body_req

    if not c and not q:
        raise HTTPException(status_code=400, detail="Missing required input parameters: provide 'query' and 'context' in request body, query parameters, or ?json= parameter.")

    return OptimizeRequest(
        query=q,
        context=c,
        token_budget=b,
        model=m,
        simulate_tier2_failure=f,
    )


# ----------------------------------------------------------------------
# Endpoint 1: POST/GET /analyze
# ----------------------------------------------------------------------
@app.get("/analyze", response_model=AnalyzeResponse)
@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_context(
    req: Optional[AnalyzeRequest] = None,
    query: Optional[str] = Query(None),
    context: Optional[str] = Query(None),
    token_budget: Optional[int] = Query(None),
    json_param: Optional[str] = Query(None, alias="json"),
):
    """
    Dry-run analysis endpoint:
    - Computes original token count
    - Estimates baseline LLM cost
    - Selects execution route (SKIP | LIGHT | FULL) without running heavy optimization or LLM inference.
    """
    if req is None:
        opt_req = resolve_optimize_request(
            query=query, context=context, token_budget=token_budget, json_str=json_param
        )
        ctx = opt_req.context
        qry = opt_req.query
        tb = opt_req.token_budget
    else:
        ctx = req.context
        qry = req.query
        tb = req.token_budget

    original_tokens = count_tokens(ctx)
    chunks = tier0_chunk_and_tag(ctx)
    route = person3_route_decision(qry, chunks, tb)
    estimated_cost = estimate_cost(original_tokens, model="gpt-4o")

    return AnalyzeResponse(
        original_tokens=original_tokens,
        estimated_cost=estimated_cost,
        route=route,
    )


# ----------------------------------------------------------------------
# Endpoint 2: POST/GET /optimize
# ----------------------------------------------------------------------
@app.get("/optimize", response_model=OptimizeResponse)
@app.post("/optimize", response_model=OptimizeResponse)
async def optimize_context(
    req: Optional[OptimizeRequest] = None,
    query: Optional[str] = Query(None),
    context: Optional[str] = Query(None),
    token_budget: Optional[int] = Query(None),
    model: Optional[str] = Query(None),
    simulate_tier2_failure: Optional[bool] = Query(False),
    json_param: Optional[str] = Query(None, alias="json"),
):
    """
    Primary optimization pipeline endpoint:
    - Runs Tier 0, Routing, Tier 1, Tier 2, and Coherence Assembly
    - Returns optimized context, token waterfall, and stage-by-stage latency trace.
    """
    opt_req = resolve_optimize_request(
        body_req=req,
        query=query,
        context=context,
        token_budget=token_budget,
        model=model,
        simulate_tier2_failure=simulate_tier2_failure,
        json_str=json_param,
    )

    if opt_req.token_budget <= 0:
        raise HTTPException(status_code=400, detail="token_budget must be a positive integer.")

    response = run_pipeline(
        query=opt_req.query,
        context=opt_req.context,
        token_budget=opt_req.token_budget,
        simulate_tier2_failure=bool(opt_req.simulate_tier2_failure),
    )
    return response


# ----------------------------------------------------------------------
# Endpoint 3: POST/GET /optimize-and-answer (and /answer alias)
# ----------------------------------------------------------------------
@app.get("/answer", response_model=OptimizeAndAnswerResponse)
@app.post("/answer", response_model=OptimizeAndAnswerResponse)
@app.get("/optimize-and-answer", response_model=OptimizeAndAnswerResponse)
@app.post("/optimize-and-answer", response_model=OptimizeAndAnswerResponse)
async def optimize_and_answer(
    req: Optional[OptimizeRequest] = None,
    query: Optional[str] = Query(None),
    context: Optional[str] = Query(None),
    token_budget: Optional[int] = Query(None),
    model: Optional[str] = Query(None),
    simulate_tier2_failure: Optional[bool] = Query(False),
    json_param: Optional[str] = Query(None, alias="json"),
):
    """
    Convenience endpoint (GET or POST):
    - Accepts JSON body or query parameters / ?json= input
    - Calls optimization pipeline internally
    - Dispatches prompt to downstream LLM and returns the exact answer.
    """
    opt_req = resolve_optimize_request(
        body_req=req,
        query=query,
        context=context,
        token_budget=token_budget,
        model=model,
        simulate_tier2_failure=simulate_tier2_failure,
        json_str=json_param,
    )

    if opt_req.token_budget <= 0:
        raise HTTPException(status_code=400, detail="token_budget must be a positive integer.")

    # 1. Run optimization pipeline
    opt_resp = run_pipeline(
        query=opt_req.query,
        context=opt_req.context,
        token_budget=opt_req.token_budget,
        simulate_tier2_failure=bool(opt_req.simulate_tier2_failure),
    )

    # 2. Downstream LLM inference call using compressed optimized context payload
    answer_text, llm_latency_ms = person3_generate_answer(
        query=opt_req.query,
        optimized_context=opt_resp.optimized_context,
        model=opt_req.model or "gpt-4o",
    )

    # 3. Quality evaluation
    quality_score = None
    try:
        quality_score = person3_evaluate_quality(
            query=opt_req.query,
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
        model=opt_req.model or "gpt-4o",
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
