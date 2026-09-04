import pytest
from fastapi.testclient import TestClient
from backend.main import app


client = TestClient(app)


def test_analyze_returns_expected_fields():
    payload = {"query": "q", "context": "x" * 400, "token_budget": 100}
    r = client.post("/analyze", json=payload)
    assert r.status_code == 200
    j = r.json()
    assert "route" in j
    assert isinstance(j.get("original_tokens"), int)
    assert "estimated_cost" in j


def test_optimize_returns_expected_fields():
    payload = {"query": "q", "context": "x" * 400, "token_budget": 100, "simulate_tier2_failure": False}
    r = client.post("/optimize", json=payload)
    assert r.status_code == 200
    j = r.json()
    for k in ("route", "original_tokens", "optimized_tokens", "reduction_percentage", "trace", "chunks_detail"):
        assert k in j
    assert isinstance(j["trace"]["stage_tokens"]["original"], int)


def test_optimize_and_answer_contains_answer_and_costs():
    payload = {"query": "q", "context": "x" * 400, "token_budget": 100, "simulate_tier2_failure": False}
    r = client.post("/optimize-and-answer", json=payload)
    assert r.status_code == 200
    j = r.json()
    assert "answer" in j
    assert "quality_score" in j
    assert "llm_latency_ms" in j
    assert "cost_comparison" in j
