"""Pydantic schemas and data contracts for the Context Optimization Middleware."""
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class ChunkInfo(BaseModel):
    """Metadata and inspection details for a single context chunk."""
    id: str
    position: int = Field(description="Original sequence position in document")
    text: str
    original_text: Optional[str] = None
    tag: str = Field(default="generic", description="system | constraint | code | fact | dialogue | generic")
    is_critical: bool = False
    relevance_score: float = 1.0
    token_count: int = 0
    action_taken: str = Field(default="kept", description="kept | filtered_irrelevant | merged_duplicate | compressed | pinned")


class AnalyzeRequest(BaseModel):
    """Input payload for POST /analyze."""
    query: str
    context: str
    token_budget: Optional[int] = None


class AnalyzeResponse(BaseModel):
    """Output payload for POST /analyze."""
    original_tokens: int
    estimated_cost: float
    route: Literal["SKIP", "LIGHT", "FULL"]


class OptimizeRequest(BaseModel):
    """Input payload for POST /optimize and POST /optimize-and-answer."""
    query: str
    context: str
    token_budget: int
    model: Optional[str] = "gpt-4o"
    # Optional debug flag to simulate Tier 2 failure for testing fallback
    simulate_tier2_failure: Optional[bool] = False


class StageTokens(BaseModel):
    """Token count waterfall across pipeline stages."""
    original: int
    after_relevance: int
    after_dedup: int
    after_compression: int
    after_budget: int


class StageLatencyMs(BaseModel):
    """Per-stage latency breakdown in milliseconds."""
    chunking: float
    embedding_relevance: float
    dedup: float
    compression: float
    assembly: float
    total: float


class OptimizationTrace(BaseModel):
    """Detailed audit trace of the optimization execution."""
    chunks_total: int
    chunks_removed_irrelevant: int
    chunks_merged_duplicate: int
    chunks_compressed: int
    chunks_pinned_critical: int
    stage_tokens: StageTokens
    stage_latency_ms: StageLatencyMs
    fallback_triggered: bool = False
    fallback_reason: Optional[str] = None


class OptimizeResponse(BaseModel):
    """Output payload for POST /optimize."""
    original_tokens: int
    optimized_tokens: int
    reduction_percentage: float
    route: Literal["SKIP", "LIGHT", "FULL"]
    optimized_context: str
    trace: OptimizationTrace
    chunks_detail: Optional[List[ChunkInfo]] = None


class CostComparison(BaseModel):
    """Cost comparison between baseline raw prompt and optimized pipeline."""
    baseline_cost: float
    optimizer_cost: float
    optimized_llm_cost: float
    total_optimized_cost: float
    savings_percentage: float


class OptimizeAndAnswerResponse(OptimizeResponse):
    """Output payload for POST /optimize-and-answer."""
    answer: str
    quality_score: Optional[float] = None
    llm_latency_ms: float = 0.0
    cost_comparison: CostComparison
