"""Integration tests for the three decoupled API endpoints."""
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

SAMPLE_CONTEXT = """System: You are an enterprise support bot. Provide concise answers.

Policy Article 1: Return windows are 30 days for standard plans and 60 days for premium plans.
Policy Article 1: Return windows are 30 days for standard plans and 60 days for premium plans.

Constraint: DO NOT offer cash refunds without supervisor approval under any circumstances.

Payment options include Visa, MasterCard, PayPal, and Wire Transfer.
"""

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_analyze_endpoint():
    """POST /analyze should return original tokens, estimated cost, and route."""
    payload = {
        "query": "What is the return window for premium plans?",
        "context": SAMPLE_CONTEXT,
        "token_budget": 100
    }
    response = client.post("/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "original_tokens" in data
    assert "estimated_cost" in data
    assert "route" in data
    assert data["original_tokens"] > 0
    assert data["route"] in ["SKIP", "LIGHT", "FULL"]


def test_optimize_endpoint():
    """POST /optimize should run full pipeline without calling LLM."""
    payload = {
        "query": "What is the return window for premium plans?",
        "context": SAMPLE_CONTEXT,
        "token_budget": 80
    }
    response = client.post("/optimize", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Core response fields
    assert "original_tokens" in data
    assert "optimized_tokens" in data
    assert "reduction_percentage" in data
    assert "route" in data
    assert "optimized_context" in data
    assert "trace" in data

    # Verify no LLM answer field in /optimize
    assert "answer" not in data

    # Verify trace structure
    trace = data["trace"]
    assert "chunks_total" in trace
    assert "chunks_removed_irrelevant" in trace
    assert "chunks_merged_duplicate" in trace
    assert "chunks_compressed" in trace
    assert "chunks_pinned_critical" in trace
    assert "stage_tokens" in trace
    assert "stage_latency_ms" in trace
    assert "fallback_triggered" in trace

    # Verify stage tokens waterfall
    st = trace["stage_tokens"]
    assert st["original"] >= st["after_budget"]

    # Verify latency breakdown
    lat = trace["stage_latency_ms"]
    assert lat["chunking"] >= 0.0
    assert lat["total"] >= 0.0


def test_optimize_and_answer_endpoint():
    """POST /optimize-and-answer should run optimization + LLM call + quality eval + cost comparison."""
    payload = {
        "query": "What is the return window for premium plans?",
        "context": SAMPLE_CONTEXT,
        "token_budget": 80
    }
    response = client.post("/optimize-and-answer", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "optimized_context" in data
    assert "answer" in data
    assert len(data["answer"]) > 0
    assert "quality_score" in data
    assert "llm_latency_ms" in data
    assert "cost_comparison" in data

    cost = data["cost_comparison"]
    assert "baseline_cost" in cost
    assert "optimizer_cost" in cost
    assert "optimized_llm_cost" in cost
    assert "total_optimized_cost" in cost
    assert "savings_percentage" in cost


def test_validation_errors():
    """Invalid token budget should return 400."""
    payload = {
        "query": "Hello",
        "context": "World",
        "token_budget": 0
    }
    response = client.post("/optimize", json=payload)
    assert response.status_code == 400
