import pytest
from unittest.mock import patch, MagicMock
from semantic_relevance_engine.answer_quality import (
    run_llm_judge,
    evaluate_answer_quality,
    AnswerQualityResult
)

def test_run_llm_judge_parsing_standard():
    """Test standard parsing of LLM Judge responses."""
    raw_response = (
        "Answer A score: 8.5\n"
        "Answer B score: 9.0\n"
        "Reasoning: Answer B is more complete."
    )
    with patch("semantic_relevance_engine.answer_quality.grok_answer", return_value=raw_response):
        parsed = run_llm_judge("dummy query", "baseline", "optimized", "dummy context")
        assert parsed["score_baseline"] == 8.5
        assert parsed["score_optimized"] == 9.0
        assert parsed["reasoning"] == "Answer B is more complete."

def test_run_llm_judge_parsing_whitespace_case():
    """Test parsing with variable whitespace and casing."""
    raw_response = (
        "   answer a score   :   7  \n"
        "   ANSWER B SCORE: 6\n"
        "reasoning: None really."
    )
    with patch("semantic_relevance_engine.answer_quality.grok_answer", return_value=raw_response):
        parsed = run_llm_judge("dummy query", "baseline", "optimized", "dummy context")
        assert parsed["score_baseline"] == 7.0
        assert parsed["score_optimized"] == 6.0
        assert parsed["reasoning"] == "None really."

def test_run_llm_judge_parsing_fallback():
    """Test fallback when reasoning field or score is malformed."""
    raw_response = "No scores provided here. Completely malformed."
    with patch("semantic_relevance_engine.answer_quality.grok_answer", return_value=raw_response):
        parsed = run_llm_judge("dummy query", "baseline", "optimized", "dummy context")
        assert parsed["score_baseline"] is None
        assert parsed["score_optimized"] is None
        # Should fallback to returning raw response as reasoning
        assert parsed["reasoning"] == "No scores provided here. Completely malformed."

def test_evaluate_answer_quality_skip_calls():
    """Test that skip_llm_calls avoids generating answers and reports trivially preserved."""
    with patch("semantic_relevance_engine.answer_quality.grok_answer") as mock_grok:
        res = evaluate_answer_quality(
            query="test query",
            original_context="original context",
            optimized_context="original context",
            comparison_type="llm_judge",
            skip_llm_calls=True
        )
        mock_grok.assert_not_called()
        assert res.passed is None
        assert res.judge_score_baseline == 10.0
        assert res.judge_score_optimized == 10.0
        assert "trivially preserved" in res.notes.lower()

def test_evaluate_answer_quality_deterministic_pass():
    """Test deterministic evaluation when all checks pass."""
    mock_answers = ("Baseline answer text", "Optimized answer text containing DynamoDB and 401 code.")
    
    checks = [
        {
            "name": "Check DynamoDB",
            "check_fn": lambda ans: "dynamodb" in ans.lower(),
            "description": "Must mention DynamoDB"
        },
        {
            "name": "Check 401",
            "check_fn": lambda ans: "401" in ans,
            "description": "Must mention 401 status"
        }
    ]
    
    with patch("semantic_relevance_engine.answer_quality.generate_answers", return_value=mock_answers):
        res = evaluate_answer_quality(
            query="test query",
            original_context="context",
            optimized_context="context",
            comparison_type="deterministic",
            deterministic_checks=checks
        )
        assert res.passed is True
        assert len(res.deterministic_results) == 2
        assert res.deterministic_results[0]["passed"] is True
        assert res.deterministic_results[1]["passed"] is True

def test_evaluate_answer_quality_deterministic_fail():
    """Test deterministic evaluation when one check fails."""
    mock_answers = ("Baseline answer text", "Optimized answer text with 401 but missing the DB.")
    
    checks = [
        {
            "name": "Check DynamoDB",
            "check_fn": lambda ans: "dynamodb" in ans.lower(),
            "description": "Must mention DynamoDB"
        },
        {
            "name": "Check 401",
            "check_fn": lambda ans: "401" in ans,
            "description": "Must mention 401 status"
        }
    ]
    
    with patch("semantic_relevance_engine.answer_quality.generate_answers", return_value=mock_answers):
        res = evaluate_answer_quality(
            query="test query",
            original_context="context",
            optimized_context="context",
            comparison_type="deterministic",
            deterministic_checks=checks
        )
        assert res.passed is False
        assert len(res.deterministic_results) == 2
        assert res.deterministic_results[0]["passed"] is False
        assert res.deterministic_results[1]["passed"] is True
