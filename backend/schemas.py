from pydantic import BaseModel, Field
from typing import List, Optional


class AnalyzeRequest(BaseModel):
    query: str
    context: str
    token_budget: int = Field(..., alias="token_budget")


class OptimizeRequest(BaseModel):
    query: str
    context: str
    token_budget: int = Field(..., alias="token_budget")
    simulate_tier2_failure: Optional[bool] = False


class ChunkDetail(BaseModel):
    id: int
    position: int
    tag: str
    is_critical: bool
    token_count: int
    relevance_score: float
    action_taken: str
    text: str


class StageTokens(BaseModel):
    original: int
    after_relevance: int
    after_dedup: int
    after_compression: int
    after_budget: int


class StageLatency(BaseModel):
    total: float
    chunking: float
    embedding_relevance: float
    dedup: float
    compression: float
    assembly: float


class TraceInfo(BaseModel):
    fallback_triggered: bool
    fallback_reason: Optional[str]
    stage_tokens: StageTokens
    stage_latency_ms: StageLatency
    chunks_total: int
    chunks_removed_irrelevant: int
    chunks_merged_duplicate: int
    chunks_compressed: int
    chunks_pinned_critical: int


class CostComparison(BaseModel):
    baseline_cost: float
    optimizer_cost: float
    optimized_llm_cost: float
    total_optimized_cost: float
    savings_percentage: float


class OptimizeResponse(BaseModel):
    route: str
    original_tokens: int
    optimized_tokens: int
    reduction_percentage: float
    trace: TraceInfo
    chunks_detail: List[ChunkDetail] = []


class OptimizeAndAnswerResponse(OptimizeResponse):
    answer: str
    quality_score: Optional[float]
    llm_latency_ms: Optional[float]
    cost_comparison: Optional[CostComparison]


class AnalyzeResponse(BaseModel):
    route: str
    original_tokens: int
    estimated_cost: float
