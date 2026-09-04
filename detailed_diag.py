"""
Detailed diagnostic script to run the real pipeline (optimize_chunks) under the new prompt and length guard.
Prints before/after chunk details, trace reverts, and kept chunk IDs.
"""
import os, sys, copy, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError: pass

from semantic_relevance_engine import rank_chunks, optimize_chunks
from semantic_relevance_engine.optimizer import approx_token_count
from semantic_relevance_engine.grok_client import grok_compress, get_token_usage, reset_token_usage

# Inputs for Scenario 1
S1_query = "How do we handle HTTP 500 errors?"
S1_context = (
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
)
S1_budget = 80

S2_query = "Explain how vector indexing and cosine similarity work together."
S2_context = (
    "[SYSTEM]\nYou are a technical retrieval assistant.\n"
    "[DOC]\nVector search indexing uses cosine similarity across dense embeddings to retrieve relevant documentation sections rapidly.\n"
    "[DOC]\nCosine similarity measures the angle between two embedding vectors to evaluate semantic relatedness.\n"
    "[DOC]\nDense embeddings represent text chunks as high-dimensional floats capturing semantic concepts.\n"
    "[DOC]\nDatabase documentation retrieval searches for matches between user queries and index vectors.\n"
)
S2_budget = 100

def run_scenario_diag(name, query, context, budget):
    print(f"\n=== {name} ===")
    ranked = rank_chunks(query, context, dedup_threshold=0.85)
    
    # Store original text for comparison
    orig_map = {c.id: c.text for c in ranked}
    
    time.sleep(1)
    reset_token_usage()
    optimized_output, trace = optimize_chunks(
        query=query,
        chunks=copy.deepcopy(ranked),
        token_budget=budget,
        llm_call_fn=grok_compress
    )
    
    print("Trace Object:")
    print(f"  chunks_total: {trace['chunks_total']}")
    print(f"  chunks_compressed: {trace['chunks_compressed']}")
    print(f"  chunks_reverted_flag_loss: {trace['chunks_reverted_flag_loss']}")
    print(f"  empty_compression_result: {trace['empty_compression_result']}")
    print(f"  chunks_expanded_reverted: {trace['chunks_expanded_reverted']}")
    print(f"  fallback_triggered: {trace['fallback_triggered']}")
    print(f"  stage_tokens: {trace['stage_tokens']}")
    
    print("\nBefore/After for all eligible chunks:")
    # Eligible chunks are those surviving dedup that are not pinned
    from semantic_relevance_engine.optimizer import apply_pinning
    surviving = [c for c in ranked if c.is_duplicate_of is None]
    apply_pinning(surviving)
    non_pinned = [c for c in surviving if not c.pinned]
    
    opt_map = {c.id: c for c in optimized_output}
    
    for c in non_pinned:
        orig_text = orig_map[c.id]
        orig_tok = approx_token_count(orig_text)
        
        # Check if it was kept in optimized_output or discarded by budget
        opt_c = opt_map.get(c.id)
        if opt_c:
            after_text = opt_c.text
            after_tok = opt_c.token_count
            compressed_flag = opt_c.compressed
            reverted = "length_expanded_revert" in opt_c.trace_events or "flag_lost_revert" in opt_c.trace_events
        else:
            # Look up how it ended up after compression step but before budget
            # We can run compress_chunk directly
            from semantic_relevance_engine.optimizer import compress_chunk
            res_c = compress_chunk(copy.deepcopy(c), query, llm_call_fn=grok_compress)
            after_text = res_c.text
            after_tok = res_c.token_count
            compressed_flag = res_c.compressed
            reverted = "length_expanded_revert" in res_c.trace_events or "flag_lost_revert" in res_c.trace_events
            
        print(f"Chunk ID: {c.id}")
        print(f"  Before ({orig_tok}t): {orig_text.strip()!r}")
        print(f"  After  ({after_tok}t): {after_text.strip()!r}")
        print(f"  Compressed Flag: {compressed_flag} | Reverted Event: {reverted}")

if __name__ == "__main__":
    run_scenario_diag("Scenario 1", S1_query, S1_context, S1_budget)
    run_scenario_diag("Scenario 2", S2_query, S2_context, S2_budget)
