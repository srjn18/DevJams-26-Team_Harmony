"""
DIAGNOSTIC STEP 1: Confirm compression actually executes per scenario.
Reports chunks_compressed from trace, and for each surviving chunk:
  - whether it's pinned (and why: tag vs. critical_flags)
  - whether llm_call_fn was invoked
  - final disposition: skipped-pinned / skipped-no-fn / called-compressed / called-reverted / exception
"""
import os
import sys
import copy
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from semantic_relevance_engine import rank_chunks, Chunk
from semantic_relevance_engine.optimizer import (
    approx_token_count, apply_pinning, compute_importance_score,
    compute_final_score, COMPRESSION_PROMPT_TEMPLATE
)
from semantic_relevance_engine.critical_flags import detect_critical_flags
from semantic_relevance_engine.grok_client import grok_compress

# ── Scenarios ──────────────────────────────────────────────────────────────

SCENARIOS = {
    "Scenario 1 — Mostly Irrelevant": {
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
        "token_budget": 80,
    },
    "Scenario 2 — Everything Relevant": {
        "query": "Explain how vector indexing and cosine similarity work together.",
        "context": (
            "[SYSTEM]\nYou are a technical retrieval assistant.\n"
            "[DOC]\nVector search indexing uses cosine similarity across dense embeddings to retrieve relevant documentation sections rapidly.\n"
            "[DOC]\nCosine similarity measures the angle between two embedding vectors to evaluate semantic relatedness.\n"
            "[DOC]\nDense embeddings represent text chunks as high-dimensional floats capturing semantic concepts.\n"
            "[DOC]\nDatabase documentation retrieval searches for matches between user queries and index vectors.\n"
        ),
        "token_budget": 100,
    },
    "Scenario 3 — Adversarial Context": {
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
        "token_budget": 120,
    },
}

SEP = "=" * 80
SEP2 = "-" * 80


def diagnose_step1(name, query, context, token_budget):
    print(f"\n{SEP}")
    print(f"  {name}")
    print(SEP)

    ranked = rank_chunks(query, context, dedup_threshold=0.85)
    surviving = [c for c in ranked if c.is_duplicate_of is None]
    surviving = apply_pinning(surviving)

    for c in surviving:
        c.importance_score = compute_importance_score(c)
        if not c.pinned:
            c.final_score = compute_final_score(c)

    print(f"\nChunk-level disposition (post-pinning, pre-compression):\n{SEP2}")
    print(f"  {'ID':<8} {'Tag':<20} {'Pinned':<8} {'PinnedWhy':<30} {'Flags'}")
    print(SEP2)

    for c in surviving:
        if c.pinned:
            if c.tag in ("SYSTEM", "PERSISTENT_CONSTRAINT"):
                why = f"tag={c.tag}"
                if c.critical_flags:
                    why += f" + flags={c.critical_flags}"
            else:
                why = f"flags={c.critical_flags}"
        else:
            why = "—"
        print(f"  {c.id:<8} {c.tag:<20} {str(c.pinned):<8} {why:<30} {c.critical_flags}")

    non_pinned = [c for c in surviving if not c.pinned]
    print(f"\nTotal surviving after dedup: {len(surviving)}")
    print(f"  Pinned: {len(surviving) - len(non_pinned)}")
    print(f"  Non-pinned (eligible for compression): {len(non_pinned)}")

    if not non_pinned:
        print("\n[FINDING] 0 non-pinned chunks → llm_call_fn was NEVER invoked. "
              "chunks_compressed will be 0. All chunks were pinned.")
        return

    print(f"\nCompression call log (non-pinned chunks only):\n{SEP2}")
    compressed_count = 0
    revert_count = 0
    call_count = 0

    for c in non_pinned:
        text_before = c.text
        tokens_before = approx_token_count(text_before)
        prompt = COMPRESSION_PROMPT_TEMPLATE.format(query=query, chunk_text=c.text)

        t0 = time.perf_counter()
        try:
            compressed_text = grok_compress(prompt)
            latency_ms = (time.perf_counter() - t0) * 1000
            call_count += 1
        except Exception as ex:
            latency_ms = (time.perf_counter() - t0) * 1000
            print(f"  {c.id}: EXCEPTION in llm_call_fn ({latency_ms:.0f}ms): {ex}")
            continue

        tokens_after = approx_token_count(compressed_text)
        original_flags = set(detect_critical_flags(text_before))
        new_flags = set(detect_critical_flags(compressed_text))
        lost_flags = original_flags - new_flags

        if compressed_text.strip() == "":
            disposition = "REVERTED (empty output)"
            revert_count += 1
        elif lost_flags:
            disposition = f"REVERTED (flag-loss: {lost_flags})"
            revert_count += 1
        else:
            disposition = "COMPRESSED"
            compressed_count += 1

        print(f"  {c.id} | latency={latency_ms:.0f}ms | "
              f"tokens {tokens_before}->{tokens_after} "
              f"({'shrunk' if tokens_after < tokens_before else 'same/grew'}) | "
              f"{disposition}")

        if "REVERTED" in disposition:
            # Show why
            print(f"    original  ({tokens_before}t): {text_before[:120].strip()!r}")
            print(f"    compressed({tokens_after}t): {compressed_text[:120].strip()!r}")
            if lost_flags:
                print(f"    lost flags: {lost_flags} | orig_flags={original_flags} | new_flags={new_flags}")

    print(f"\n{SEP2}")
    print(f"STEP 1 SUMMARY for '{name}':")
    print(f"  llm_call_fn invoked:  {call_count} times")
    print(f"  chunks_compressed:    {compressed_count}")
    print(f"  chunks_reverted:      {revert_count}")
    if call_count == 0 and len(non_pinned) == 0:
        print("  [ROOT CAUSE] No non-pinned chunks — compression never ran.")
    elif compressed_count == 0 and call_count > 0:
        print("  [ROOT CAUSE] Compression ran but ALL results were reverted (flag-loss or empty). "
              "chunks_compressed=0 because revert means chunk.compressed stays False.")
    print(SEP)


if __name__ == "__main__":
    print("DIAGNOSTIC: STEP 1 — Confirm compression actually executes per scenario")
    for name, cfg in SCENARIOS.items():
        diagnose_step1(name, cfg["query"], cfg["context"], cfg["token_budget"])
    print("\nStep 1 complete. Awaiting review before proceeding to Step 2.")
