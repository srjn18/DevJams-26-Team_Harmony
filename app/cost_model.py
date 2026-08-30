"""Cost calculation models for LLM inference and optimizer overhead with configurable rates."""
import os
from typing import Dict, Optional

# Default Provider Pricing per 1,000 tokens (USD)
DEFAULT_MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4o": {
        "input": float(os.environ.get("PRICING_GPT4O_INPUT", "0.005")),       # $5.00 per 1M tokens
        "output": float(os.environ.get("PRICING_GPT4O_OUTPUT", "0.015")),    # $15.00 per 1M tokens
    },
    "gpt-4o-mini": {
        "input": float(os.environ.get("PRICING_GPT4O_MINI_INPUT", "0.00015")),
        "output": float(os.environ.get("PRICING_GPT4O_MINI_OUTPUT", "0.00060")),
    },
    "claude-3.5-sonnet": {
        "input": float(os.environ.get("PRICING_CLAUDE_SONNET_INPUT", "0.003")),
        "output": float(os.environ.get("PRICING_CLAUDE_SONNET_OUTPUT", "0.015")),
    },
    "generic": {
        "input": float(os.environ.get("PRICING_GENERIC_INPUT", "0.002")),
        "output": float(os.environ.get("PRICING_GENERIC_OUTPUT", "0.008")),
    }
}

# Optimizer overhead estimate per 1,000 input tokens (USD)
DEFAULT_OPTIMIZER_OVERHEAD_PER_1K: Dict[str, float] = {
    "SKIP": 0.00000,
    "LIGHT": float(os.environ.get("PRICING_OPTIMIZER_LIGHT", "0.00002")),   # local embeddings / fast cosine scoring
    "FULL": float(os.environ.get("PRICING_OPTIMIZER_FULL", "0.00010")),     # embeddings + small extractive/abstractive compression
}


def estimate_cost(
    tokens: int,
    model: str = "gpt-4o",
    is_output: bool = False,
    custom_pricing: Optional[Dict[str, Dict[str, float]]] = None
) -> float:
    """Calculate USD cost for a given token count using configurable pricing."""
    pricing_map = custom_pricing or DEFAULT_MODEL_PRICING
    pricing = pricing_map.get(model, pricing_map.get("generic", {"input": 0.002, "output": 0.008}))
    rate = pricing["output"] if is_output else pricing["input"]
    return round((tokens / 1000.0) * rate, 6)


def estimate_optimizer_cost(
    original_tokens: int,
    route: str = "FULL",
    custom_overhead: Optional[Dict[str, float]] = None
) -> float:
    """Estimate the compute / embedding cost incurred by the optimizer middleware."""
    overhead_map = custom_overhead or DEFAULT_OPTIMIZER_OVERHEAD_PER_1K
    rate = overhead_map.get(route.upper(), overhead_map.get("FULL", 0.00010))
    return round((original_tokens / 1000.0) * rate, 6)


def calculate_cost_comparison(
    original_tokens: int,
    optimized_tokens: int,
    output_tokens: int = 150,
    model: str = "gpt-4o",
    route: str = "FULL",
    custom_pricing: Optional[Dict[str, Dict[str, float]]] = None,
    custom_overhead: Optional[Dict[str, float]] = None
) -> Dict[str, float]:
    """
    Compare baseline unoptimized cost against (optimizer overhead + optimized LLM inference cost)
    with dynamic provider rates.
    """
    baseline_input_cost = estimate_cost(original_tokens, model=model, is_output=False, custom_pricing=custom_pricing)
    baseline_output_cost = estimate_cost(output_tokens, model=model, is_output=True, custom_pricing=custom_pricing)
    baseline_cost = round(baseline_input_cost + baseline_output_cost, 6)

    optimizer_cost = estimate_optimizer_cost(original_tokens, route=route, custom_overhead=custom_overhead)
    optimized_input_cost = estimate_cost(optimized_tokens, model=model, is_output=False, custom_pricing=custom_pricing)
    optimized_output_cost = estimate_cost(output_tokens, model=model, is_output=True, custom_pricing=custom_pricing)
    optimized_llm_cost = round(optimized_input_cost + optimized_output_cost, 6)

    total_optimized_cost = round(optimizer_cost + optimized_llm_cost, 6)
    
    if baseline_cost > 0:
        savings = baseline_cost - total_optimized_cost
        savings_percentage = round(max(0.0, (savings / baseline_cost) * 100.0), 2)
    else:
        savings_percentage = 0.0

    return {
        "baseline_cost": baseline_cost,
        "optimizer_cost": optimizer_cost,
        "optimized_llm_cost": optimized_llm_cost,
        "total_optimized_cost": total_optimized_cost,
        "savings_percentage": savings_percentage,
    }
