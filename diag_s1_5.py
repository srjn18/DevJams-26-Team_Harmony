"""
DIAGNOSTIC Steps 1-5 (Groq backend).
Outputs compact summaries only — no full dumps.
"""
import os, sys, copy, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError: pass

from semantic_relevance_engine import rank_chunks, optimize_chunks
from semantic_relevance_engine.grok_client import (
    grok_compress, get_token_usage, reset_token_usage
)
from semantic_relevance_engine.optimizer import (
    apply_pinning, compute_importance_score, compute_final_score,
    approx_token_count, COMPRESSION_PROMPT_TEMPLATE, enforce_budget
)
from semantic_relevance_engine.critical_flags import detect_critical_flags
from openai import OpenAI

api_key = os.getenv("GROQ_API_KEY")
model   = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")
_raw_client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

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

SEP = "="*72

def run_scenario(name, query, context, budget):
    print(f"\n{SEP}\n{name}\n{SEP}")
    ranked = rank_chunks(query, context, dedup_threshold=0.85)

    # ── STEP 1: compression execution ─────────────────────────────────────
    surviving = [c for c in copy.deepcopy(ranked) if c.is_duplicate_of is None]
    surviving = apply_pinning(surviving)
    for c in surviving:
        c.importance_score = compute_importance_score(c)
        if not c.pinned:
            c.final_score = compute_final_score(c)

    non_pinned = [c for c in surviving if not c.pinned]
    print(f"\n[S1] chunks={len(surviving)} pinned={len(surviving)-len(non_pinned)} eligible={len(non_pinned)}")
    print(f"     pinned IDs+reasons: { {c.id: (c.tag if c.tag in ('SYSTEM','PERSISTENT_CONSTRAINT') else c.critical_flags) for c in surviving if c.pinned} }")

    # Per-chunk compression calls with full instrumentation
    success, failed, reverted_flag, reverted_empty = 0, 0, 0, 0
    per_chunk_results = []   # (id, disposition, tokens_before, tokens_after, finish_reason, latency_ms, revert_detail)
    step3_pair = None         # first successful before/after for S1 only

    for c in non_pinned:
        prompt = COMPRESSION_PROMPT_TEMPLATE.format(query=query, chunk_text=c.text)
        t0 = time.perf_counter()
        try:
            time.sleep(1)   # 1s gap to stay under 12k TPM free-tier limit
            resp = _raw_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=750,
            )
            latency = (time.perf_counter()-t0)*1000
            out = resp.choices[0].message.content or ""
            finish = resp.choices[0].finish_reason

            tok_before = approx_token_count(c.text)
            tok_after  = approx_token_count(out)
            orig_flags = set(detect_critical_flags(c.text))
            new_flags  = set(detect_critical_flags(out))
            lost       = orig_flags - new_flags

            if not out.strip():
                reverted_empty += 1
                disp = "REVERTED-empty"
                revert_detail = "empty output"
            elif lost:
                reverted_flag += 1
                disp = "REVERTED-flag-loss"
                revert_detail = f"lost flags={lost}"
            else:
                success += 1
                disp = "COMPRESSED"
                revert_detail = ""
                if step3_pair is None and name == "S1-MostlyIrrelevant":
                    step3_pair = (c.id, c.text.strip(), out.strip(), tok_before, tok_after, finish)

            per_chunk_results.append((c.id, disp, tok_before, tok_after, finish, int(latency), revert_detail))

        except Exception as e:
            latency = (time.perf_counter()-t0)*1000
            failed += 1
            per_chunk_results.append((c.id, "EXCEPTION", 0, 0, "error", int(latency), str(e)[:80]))

    print(f"\n[S1] success={success} failed={failed} reverted_flag={reverted_flag} reverted_empty={reverted_empty}")

    # ── STEP 2 (S1 only): chunk-set parity ────────────────────────────────
    if name == "S1-MostlyIrrelevant":
        base_chunks  = copy.deepcopy(ranked)
        opt_chunks   = copy.deepcopy(ranked)
        reset_token_usage()
        base_out, base_trace = optimize_chunks(query=query, chunks=base_chunks,  token_budget=budget, llm_call_fn=None)
        reset_token_usage()
        opt_out, opt_trace   = optimize_chunks(query=query, chunks=opt_chunks,   token_budget=budget, llm_call_fn=grok_compress)

        base_ids = [c.id for c in base_out]
        opt_ids  = [c.id for c in opt_out]
        print(f"\n[S2] Baseline IDs  : {base_ids}")
        print(f"[S2] Optimized IDs : {opt_ids}")
        print(f"[S2] Sets differ   : {set(base_ids) != set(opt_ids)}")
        print(f"[S2] chunks_compressed={opt_trace['chunks_compressed']} fallback_triggered={opt_trace['fallback_triggered']}")
        print(f"[S2] stage_tokens: {opt_trace['stage_tokens']}")
    else:
        # still run optimize to get chunks_compressed from trace
        opt_chunks = copy.deepcopy(ranked)
        reset_token_usage()
        _, opt_trace = optimize_chunks(query=query, chunks=opt_chunks, token_budget=budget, llm_call_fn=grok_compress)
        print(f"     chunks_compressed={opt_trace['chunks_compressed']} fallback_triggered={opt_trace['fallback_triggered']}")

    # ── STEP 3 (S1): before/after text + truncation check ─────────────────
    if name == "S1-MostlyIrrelevant":
        print(f"\n[S3] Before/after pair (chunk {step3_pair[0] if step3_pair else 'none'}):")
        if step3_pair:
            cid, bef, aft, tb, ta, fin = step3_pair
            print(f"  BEFORE ({tb}t): {bef[:200]!r}")
            print(f"  AFTER  ({ta}t): {aft[:200]!r}")
            print(f"  finish_reason={fin}  {'TRUNCATION DETECTED' if fin=='length' else 'OK'}")
        else:
            print("  No successful compression call — cannot show pair.")

    # ── STEP 4: revert events ──────────────────────────────────────────────
    reverts = [(r[0], r[1], r[6]) for r in per_chunk_results if "REVERT" in r[1]]
    if reverts:
        print(f"\n[S4] Revert events ({len(reverts)}):")
        for cid, disp, detail in reverts:
            print(f"  {cid}: {disp} — {detail}")
    else:
        print(f"\n[S4] No revert events.")

    # ── per-chunk compression table ────────────────────────────────────────
    print(f"\n     {'ID':<8} {'disp':<20} {'tok_b':>5} {'tok_a':>5} {'finish':<12} {'ms':>6}  {'note'}")
    for row in per_chunk_results:
        cid, disp, tb, ta, fin, ms, note = row
        print(f"     {cid:<8} {disp:<20} {tb:>5} {ta:>5} {fin:<12} {ms:>6}  {note[:60]}")


# ── Run all scenarios ──────────────────────────────────────────────────────
for name, cfg in SCENARIOS.items():
    run_scenario(name, cfg["query"], cfg["context"], cfg["budget"])

print(f"\n{SEP}\nDone. Proceeding to Step 5 (guard implementation).\n{SEP}")
