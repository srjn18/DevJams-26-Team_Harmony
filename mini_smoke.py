"""Minimal single-call test of grok_compress after reasoning_format fix."""
import sys
sys.path.insert(0, r'd:\DevJams_26')
from dotenv import load_dotenv
load_dotenv(r'd:\DevJams_26\.env')
import os, time
print("LLM_MODEL:", os.getenv("LLM_MODEL"))
from semantic_relevance_engine.grok_client import grok_compress, get_token_usage, reset_token_usage
reset_token_usage()
t0 = time.time()
result = grok_compress("Rewrite concisely: The weather today is sunny with a high of 75 degrees.")
t1 = time.time()
u = get_token_usage()
print(f"RESULT: {result!r}")
print(f"USAGE: {u}")
print(f"LATENCY: {t1-t0:.2f}s")
