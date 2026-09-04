import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from semantic_relevance_engine.grok_client import grok_answer
from semantic_relevance_engine.llm_provider import get_answer_fn

@dataclass
class AnswerQualityResult:
    query: str
    baseline_answer: str
    optimized_answer: str
    comparison_type: str                  # "deterministic" | "llm_judge"
    passed: Optional[bool]                # True/False for deterministic checks (None for LLM judge)
    judge_score_baseline: Optional[float]  # Score (1-10)
    judge_score_optimized: Optional[float] # Score (1-10)
    judge_reasoning: Optional[str]
    notes: str
    deterministic_results: Optional[List[Dict]] = None # Detailed PASS/FAIL list for checks

def generate_answers(query: str, original_context: str, optimized_context: str) -> Tuple[str, str]:
    """
    Generate answers for the query using both the original and optimized context.
    """
    prompt_template = (
        "Context:\n{context}\n\n"
        "Question: {query}\n\n"
        "Answer:"
    )
    
    baseline_prompt = prompt_template.format(context=original_context, query=query)
    optimized_prompt = prompt_template.format(context=optimized_context, query=query)
    
    answer_fn = get_answer_fn()
    baseline_answer = answer_fn(baseline_prompt).strip()
    optimized_answer = answer_fn(optimized_prompt).strip()
    
    return baseline_answer, optimized_answer

def run_llm_judge(query: str, baseline_answer: str, optimized_answer: str, original_context: str) -> Dict:
    """
    Evaluate baseline vs optimized answer using a Grok LLM Judge.
    """
    judge_prompt = (
        "You are evaluating two answers to the same question, generated from two "
        "different versions of the source context (one full, one compressed/optimized). "
        "Score each answer 1-10 on correctness, completeness, and relevance to the question. "
        "Do not favor either answer based on length or style alone -- focus on whether the "
        "factual content is accurate and complete relative to what the source context actually supports.\n\n"
        f"Source Context:\n{original_context}\n\n"
        f"Question: {query}\n\n"
        f"Answer A: {baseline_answer}\n\n"
        f"Answer B: {optimized_answer}\n\n"
        "Respond in this exact format:\n"
        "Answer A score: <number>\n"
        "Answer B score: <number>\n"
        "Reasoning: <one or two sentences>"
    )
    
    judge_response = grok_answer(judge_prompt).strip()
    
    # Robust parsing
    score_a = None
    score_b = None
    reasoning = None
    
    match_a = re.search(r"Answer\s+A\s+score\s*:\s*([\d\.]+)", judge_response, re.IGNORECASE)
    match_b = re.search(r"Answer\s+B\s+score\s*:\s*([\d\.]+)", judge_response, re.IGNORECASE)
    match_reasoning = re.search(r"Reasoning\s*:\s*(.*)", judge_response, re.IGNORECASE | re.DOTALL)
    
    if match_a:
        try:
            score_a = float(match_a.group(1))
        except ValueError:
            pass
    if match_b:
        try:
            score_b = float(match_b.group(1))
        except ValueError:
            pass
    if match_reasoning:
        reasoning = match_reasoning.group(1).strip()
    else:
        reasoning = judge_response
        
    return {
        "score_baseline": score_a,
        "score_optimized": score_b,
        "reasoning": reasoning
    }

def evaluate_answer_quality(
    query: str,
    original_context: str,
    optimized_context: str,
    comparison_type: str,
    deterministic_checks: Optional[List[Dict]] = None,
    skip_llm_calls: bool = False
) -> AnswerQualityResult:
    """
    Evaluates the quality of the optimized answer against the baseline answer.
    Supports deterministic checks and/or LLM judge checks.
    """
    if skip_llm_calls:
        return AnswerQualityResult(
            query=query,
            baseline_answer="[SKIPPED - Identical Context]",
            optimized_answer="[SKIPPED - Identical Context]",
            comparison_type=comparison_type,
            passed=True if comparison_type == "deterministic" else None,
            judge_score_baseline=10.0 if comparison_type == "llm_judge" else None,
            judge_score_optimized=10.0 if comparison_type == "llm_judge" else None,
            judge_reasoning="Route was SKIP: original context untouched.",
            notes="Trivially preserved by definition."
        )

    # 1. Generate both answers
    baseline_ans, optimized_ans = generate_answers(query, original_context, optimized_context)
    
    if comparison_type == "deterministic":
        passed_all = True
        detailed_results = []
        if deterministic_checks:
            for check in deterministic_checks:
                name = check["name"]
                check_fn = check["check_fn"]
                desc = check.get("description", "")
                
                # We check the optimized answer behavior
                passed = check_fn(optimized_ans)
                if not passed:
                    passed_all = False
                
                detailed_results.append({
                    "name": name,
                    "description": desc,
                    "passed": passed
                })
        else:
            passed_all = True  # trivially passes if no checks configured
            
        return AnswerQualityResult(
            query=query,
            baseline_answer=baseline_ans,
            optimized_answer=optimized_ans,
            comparison_type="deterministic",
            passed=passed_all,
            judge_score_baseline=None,
            judge_score_optimized=None,
            judge_reasoning=None,
            notes=f"Deterministic checks run: {len(detailed_results)}",
            deterministic_results=detailed_results
        )
        
    else:  # llm_judge
        judge_res = run_llm_judge(query, baseline_ans, optimized_ans, original_context)
        return AnswerQualityResult(
            query=query,
            baseline_answer=baseline_ans,
            optimized_answer=optimized_ans,
            comparison_type="llm_judge",
            passed=None,
            judge_score_baseline=judge_res["score_baseline"],
            judge_score_optimized=judge_res["score_optimized"],
            judge_reasoning=judge_res["reasoning"],
            notes="Evaluated via LLM Judge (Grok)."
        )
