"""
Smoke test: Section 2 of the end-to-end verification.
Tests actual live API calls for grok_compress, grok_answer, and run_llm_judge.
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

print(f"LLM_MODEL: {os.getenv('LLM_MODEL')}")
print(f"JUDGE_MODEL (env var): {os.getenv('JUDGE_MODEL')} [NOTE: this var is NOT read by any Python code — judge uses grok_answer which reads LLM_MODEL]")
print("=" * 70)

from semantic_relevance_engine.grok_client import (
    grok_compress, grok_answer, get_token_usage, reset_token_usage
)
from semantic_relevance_engine.answer_quality import run_llm_judge

# ---- TEST 1: grok_compress ----
print("\n[TEST 1] grok_compress — real API call")
reset_token_usage()
t0 = time.time()
result = grok_compress("Rewrite concisely: The weather today is sunny with a high of 75 degrees.")
t1 = time.time()
usage = get_token_usage()
print(f"  Input   : 'Rewrite concisely: The weather today is sunny with a high of 75 degrees.'")
print(f"  Result  : {result!r}")
print(f"  Usage   : prompt={usage['prompt_tokens']}, candidates={usage['candidates_tokens']}")
print(f"  Latency : {t1-t0:.2f}s")
assert result and len(result) > 0, "grok_compress returned empty string!"
assert t1 - t0 > 0.1, f"Suspiciously fast ({t1-t0:.3f}s) — possible mock?"
print("  STATUS  : PASS")

# ---- TEST 2: grok_answer ----
print("\n[TEST 2] grok_answer — real API call")
reset_token_usage()
t0 = time.time()
result2 = grok_answer("What is 2+2? Answer in one sentence.")
t1 = time.time()
usage2 = get_token_usage()
print(f"  Input   : 'What is 2+2? Answer in one sentence.'")
print(f"  Result  : {result2!r}")
print(f"  Usage   : prompt={usage2['prompt_tokens']}, candidates={usage2['candidates_tokens']}")
print(f"  Latency : {t1-t0:.2f}s")
assert result2 and len(result2) > 0, "grok_answer returned empty string!"
assert t1 - t0 > 0.1, f"Suspiciously fast ({t1-t0:.3f}s) — possible mock?"
print("  STATUS  : PASS")

# ---- TEST 3: run_llm_judge ----
print("\n[TEST 3] run_llm_judge — real API call (judge call)")
reset_token_usage()
t0 = time.time()
judge_result = run_llm_judge(
    query="What color is the sky?",
    baseline_answer="The sky is blue.",
    optimized_answer="Blue.",
    original_context="The sky appears blue due to Rayleigh scattering of sunlight."
)
t1 = time.time()
usage3 = get_token_usage()
print(f"  Query           : 'What color is the sky?'")
print(f"  Baseline answer : 'The sky is blue.'")
print(f"  Optimized answer: 'Blue.'")
print(f"  Judge result    : {judge_result}")
print(f"  Usage           : prompt={usage3['prompt_tokens']}, candidates={usage3['candidates_tokens']}")
print(f"  Latency         : {t1-t0:.2f}s")
assert judge_result["score_baseline"] is not None, f"score_baseline is None! Raw: {judge_result}"
assert judge_result["score_optimized"] is not None, f"score_optimized is None! Raw: {judge_result}"
assert t1 - t0 > 0.1, f"Suspiciously fast ({t1-t0:.3f}s) — possible mock?"
print("  STATUS  : PASS")

print("\n" + "=" * 70)
print("ALL SMOKE TESTS PASSED — real API, real latency, real token counts")
