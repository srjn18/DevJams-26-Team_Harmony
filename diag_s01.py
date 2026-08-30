"""
DIAG: Step 0 (key sanity) + Step 1 (compression execution check per scenario).
Outputs only counts, IDs, finish_reason — no full dumps.
"""
import os, sys, copy, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError: pass

# ── Step 0: key sanity ────────────────────────────────────────────────────
from google import genai
api_key = os.getenv("GEMINI_API_KEY", "")
model_name = os.getenv("LLM_MODEL", "gemini-3.6-flash")
print(f"Step 0: key prefix={api_key[:8]}... model={model_name}")

client = genai.Client(api_key=api_key)
t0 = time.perf_counter()
try:
    resp = client.models.generate_content(
        model=model_name,
        contents=["Compress: 'The replica resides in region us-east-1.'"],
        config={"max_output_tokens": 750},
    )
    ms = (time.perf_counter()-t0)*1000
    finish = resp.candidates[0].finish_reason if resp.candidates else "unknown"
    print(f"  test call: OK | latency={ms:.0f}ms | finish_reason={finish} | out_tokens={resp.usage_metadata.candidates_token_count}")
except Exception as e:
    print(f"  test call FAILED: {e}")
    sys.exit(1)

# ── Scenario definitions ──────────────────────────────────────────────────
from semantic_relevance_engine import rank_chunks, optimize_chunks
from semantic_relevance_engine.grok_client import grok_compress, reset_token_usage

SCENARIOS = {
    "S1-MostlyIrrelevant": {
        "query": "How do we handle HTTP 500 errors?",
        "context": (
            "[SYSTEM]\nYou are an operations coordinator. Keep instructions brief.\n"
            "[DOC]\nUnrelated grocery list: milk, eggs, honey, bread, cereal, apples.\n"
            "[DOC]\nWeather forecast: Tomorrow will be sunny with a high of 75F and light winds.\n"
            "[DOC]\nUnrelated backup instructions: verify the backup status daily at 3 AM.\n"
            "[DOC]\nOffice parking instructions: employees should park in zone B only.\n"
            "[DOC]\nMeeting schedule: Standup is at 9:30 AM, planning is at 10 AM, retro is at 4 PM.\n"
            "[DOC]\nDatabase configuration notes: The replica resides in region us-east-1.\n"
            "[TOOL_OUTPUT]\nError log: database connection lost Exception HTTP 500 status traceback.\n"
            "[DOC]\nLunch menu: Today's special is tomato basil soup with grilled cheese.\n"
            "[DOC]\nVacation policy: All employees receive 20 days of paid time off per year.\n"
        ),
        "budget": 80,
    },
    "S2-EverythingRelevant": {
        "query": "Explain how vector indexing and cosine similarity work together.",
        "context": (
            "[SYSTEM]\nYou are a technical retrieval assistant.\n"
            "[DOC]\nVector search indexing uses cosine similarity across dense embeddings to retrieve relevant documentation sections rapidly.\n"
            "[DOC]\nCosine similarity measures the angle between two embedding vectors to evaluate semantic relatedness.\n"
            "[DOC]\nDense embeddings represent text chunks as high-dimensional floats capturing semantic concepts.\n"
            "[DOC]\nDatabase documentation retrieval searches for matches between user queries and index vectors.\n"
        ),
        "budget": 100,
    },
    "S3-Adversarial": {
        "query": "What are the core database rules and timeout constraints?",
        "context": (
            "[SYSTEM]\nYou are a helpful operations coordinator. Always remember critical constraints.\n"
            "[DOC]\nDo NOT use MongoDB for this project.\n"
            "[DOC]\nTimeout is set to 30 seconds for all queries.\n"
            "[DOC]\nThe API must remain stateless even under load.\n"
            "[CONVERSATION]\nWe decided to migrate off Postgres to DynamoDB next quarter.\n"
            "[TOOL_OUTPUT]\nEndpoint returns HTTP 401 after the auth change.\n"
            "[DOC]\nWe should have sandwiches for lunch tomorrow.\n"
        ),
        "budget": 120,
    },
}

# ── Step 1: per-scenario compression execution check ─────────────────────
print("\nStep 1: compression execution per scenario")
print(f"{'Scenario':<24} {'eligible':>8} {'success':>8} {'failed':>8} {'reverted':>8} {'compressed':>10} {'fallback':>8}")
print("-"*80)

for name, cfg in SCENARIOS.items():
    ranked = rank_chunks(cfg["query"], cfg["context"], dedup_threshold=0.85)
    chunks_in = copy.deepcopy(ranked)
    reset_token_usage()
    _, trace = optimize_chunks(
        query=cfg["query"], chunks=chunks_in,
        token_budget=cfg["budget"], llm_call_fn=grok_compress
    )
    # Also collect per-chunk detail via direct calls
    from semantic_relevance_engine.optimizer import apply_pinning, compute_importance_score, compute_final_score, COMPRESSION_PROMPT_TEMPLATE, approx_token_count
    from semantic_relevance_engine.critical_flags import detect_critical_flags

    surviving = [c for c in ranked if c.is_duplicate_of is None]
    surviving = apply_pinning(copy.deepcopy(surviving))
    non_pinned = [c for c in surviving if not c.pinned]

    success, failed, reverted = 0, 0, 0
    for c in non_pinned:
        prompt = COMPRESSION_PROMPT_TEMPLATE.format(query=cfg["query"], chunk_text=c.text)
        try:
            out = grok_compress(prompt)
            orig_flags = set(detect_critical_flags(c.text))
            new_flags  = set(detect_critical_flags(out))
            if not out.strip():
                reverted += 1
            elif orig_flags - new_flags:
                reverted += 1
            else:
                success += 1
        except Exception:
            failed += 1

    print(f"{name:<24} {len(non_pinned):>8} {success:>8} {failed:>8} {reverted:>8} {trace['chunks_compressed']:>10} {str(trace['fallback_triggered']):>8}")

print("\nDone. Step 2+ awaiting instruction.")
