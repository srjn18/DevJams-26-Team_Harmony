import os
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import copy
from pathlib import Path

# Add workspace root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from semantic_relevance_engine import rank_chunks, optimize_chunks, Chunk
from semantic_relevance_engine.optimizer import approx_token_count
from semantic_relevance_engine.llm_provider import get_compress_fn, get_usage_fns
from semantic_relevance_engine.routing import decide_route
from semantic_relevance_engine.answer_quality import evaluate_answer_quality

# Llama-3.1-8b-instant on Groq pricing vs Reka Edge pricing depending on active provider
from semantic_relevance_engine.llm_provider import get_active_provider

provider = get_active_provider()
if provider == "rakha":
    # Reka Edge pricing
    INPUT_PRICE_PER_TOKEN = 0.10 / 1_000_000
    OUTPUT_PRICE_PER_TOKEN = 0.10 / 1_000_000
else:
    # Groq Llama pricing
    INPUT_PRICE_PER_TOKEN = 0.05 / 1_000_000
    OUTPUT_PRICE_PER_TOKEN = 0.08 / 1_000_000

# Embedding cost (negligible but tracked)
EMBED_PRICE_PER_TOKEN = 0.02 / 1_000_000

COMPRESSION_MODEL = os.getenv("LLM_MODEL", "groq/compound-mini")

def print_separator(char="=", length=90):
    print(char * length)

def calculate_costs(original_tokens, final_tokens, embed_tokens, api_usage):
    """
    Calculate costs for comparative analysis.
    - Unoptimized: Sending original context directly to answering LLM.
    - Optimized: Cost of pipeline embeddings + compression API calls + sending optimized context to answering LLM.
    """
    # Answering LLM input cost (if we sent unoptimized vs optimized context)
    unoptimized_answering_cost = original_tokens * INPUT_PRICE_PER_TOKEN
    optimized_answering_cost = final_tokens * INPUT_PRICE_PER_TOKEN

    # Embedding cost (incurred by our relevance engine)
    pipeline_embedding_cost = embed_tokens * EMBED_PRICE_PER_TOKEN

    # Compression cost (incurred by gemini_compress API calls)
    pipeline_compression_cost = (
        (api_usage["prompt_tokens"] * INPUT_PRICE_PER_TOKEN) +
        (api_usage["candidates_tokens"] * OUTPUT_PRICE_PER_TOKEN)
    )

    total_optimized_cost = optimized_answering_cost + pipeline_embedding_cost + pipeline_compression_cost
    net_savings = unoptimized_answering_cost - total_optimized_cost

    return {
        "unoptimized_cost": unoptimized_answering_cost,
        "optimized_answering_cost": optimized_answering_cost,
        "pipeline_embedding_cost": pipeline_embedding_cost,
        "pipeline_compression_cost": pipeline_compression_cost,
        "total_optimized_cost": total_optimized_cost,
        "net_savings": net_savings
    }

def run_scenario(name, query, context, token_budget):
    print_separator()
    print(f" SCENARIO: {name}")
    print_separator("-")
    print(f"Query: {query}")
    
    original_tokens = approx_token_count(context)
    print(f"Original Text Length: {len(context)} characters (~{original_tokens} approx. tokens)")
    print(f"Target Budget: {token_budget} tokens")
    decision = decide_route(original_tokens, token_budget=token_budget)
    print(f"ROUTING DECISION: {decision.route} -- {decision.reasoning}")
    print_separator("-")

    # Configure deterministic checks
    comparison_type = "llm_judge"
    deterministic_checks = None
    if name == "Adversarial Context":
        comparison_type = "deterministic"
        deterministic_checks = [
            {
                "name": "Check MongoDB exclusion",
                "check_fn": lambda ans: "mongodb" not in ans.lower(),
                "description": "Must not recommend MongoDB"
            },
            {
                "name": "Check Timeout mention",
                "check_fn": lambda ans: "30" in ans,
                "description": "Must mention 30 seconds constraint"
            },
            {
                "name": "Check DynamoDB migration",
                "check_fn": lambda ans: "dynamodb" in ans.lower(),
                "description": "Must mention DynamoDB"
            },
            {
                "name": "Check HTTP 401 code",
                "check_fn": lambda ans: "401" in ans,
                "description": "Must mention 401 Unauthorized"
            }
        ]
    elif name == "Benign False-Positive Phrases":
        comparison_type = "deterministic"
        deterministic_checks = [
            {
                "name": "Check Postgres selection",
                "check_fn": lambda ans: "postgres" in ans.lower(),
                "description": "Must select Postgres database"
            },
            {
                "name": "Check MongoDB allowed",
                "check_fn": lambda ans: "mongodb is forbidden" not in ans.lower() and "mongodb is prohibited" not in ans.lower(),
                "description": "Must not state MongoDB is forbidden"
            }
        ]

    if decision.route == "SKIP":
        print(f"Skipping pipeline completely for '{name}'. Returning original context.")
        print("-" * 90)
        print()
        
        # Evaluate quality trivially (skip LLM calls)
        quality_res = evaluate_answer_quality(
            query=query,
            original_context=context,
            optimized_context=context,
            comparison_type=comparison_type,
            deterministic_checks=deterministic_checks,
            skip_llm_calls=True
        )
        
        # Calculate Costs for SKIP (both unoptimized and total_optimized cost are identical)
        embed_tokens_skip = approx_token_count(query) + original_tokens
        costs = calculate_costs(original_tokens, original_tokens, embed_tokens_skip, {"prompt_tokens": 0, "candidates_tokens": 0})
        
        # For tests that expect output, return a dummy chunk with the full context
        dummy_chunk = Chunk(id="dummy", text=context, token_count=original_tokens, source="document", tag="DOC", position=0, relevance_score=1.0)
        dummy_chunk.critical_flags = []
        dummy_chunk.pinned = False
        return {
            "original_tokens": original_tokens,
            "final_tokens": original_tokens,
            "reduction_pct": 0.0,
            "route": "SKIP",
            "trace": {"route": "SKIP", "reasoning": decision.reasoning},
            "output_chunks": [dummy_chunk],
            "quality_result": quality_res,
            "baseline_costs": costs,
            "optimized_costs": costs
        }

    # 1. Rank chunks (Tier 1)
    ranked_chunks = rank_chunks(query, context, dedup_threshold=0.85)
    
    # Recalculate based on chunks for accurate tier tracking
    original_tokens_chunks = sum(c.token_count for c in ranked_chunks)

    # Calculate embedding tokens (query tokens + all chunk tokens)
    query_tokens = approx_token_count(query)
    embed_tokens = query_tokens + original_tokens_chunks

    # Deep copy ranked chunks for both runs to avoid mutation conflicts
    chunks_baseline = copy.deepcopy(ranked_chunks)
    chunks_optimized = copy.deepcopy(ranked_chunks)

    # 2. Run Baseline (llm_call_fn=None)
    get_usage, reset_usage = get_usage_fns()
    reset_usage()
    baseline_output, baseline_trace = optimize_chunks(
        query=query,
        chunks=chunks_baseline,
        token_budget=token_budget,
        llm_call_fn=None
    )
    baseline_final_tokens = sum(c.token_count for c in baseline_output)

    # 3. Run Optimized
    compress_fn = get_compress_fn()
    llm_fn = compress_fn if decision.route == "FULL" else None
    reset_usage()
    optimized_output, optimized_trace = optimize_chunks(
        query=query,
        chunks=chunks_optimized,
        token_budget=token_budget,
        llm_call_fn=llm_fn
    )
    optimized_final_tokens = sum(c.token_count for c in optimized_output)
    api_usage = get_usage()

    # ── STEP 5 GUARD: surface silent fallbacks / truncation before reporting ──
    if optimized_trace["fallback_triggered"]:
        print(f"[ERROR] fallback_triggered=True in optimized run — compression calls"
              f" failed/timed out. Optimized numbers are BASELINE-EQUIVALENT, not real.")
        print(f"  Do NOT use these numbers for the demo. Fix quota/connectivity first.")
        raise RuntimeError("Aborting scenario: optimized run fell back to uncompressed output.")

    # Truncation check: if after_compression > after_dedup, the model expanded chunks
    # (no length guard in compress_chunk, or guard was bypassed).
    after_comp  = optimized_trace["stage_tokens"]["after_compression"]
    after_dedup = optimized_trace["stage_tokens"]["after_dedup"]
    if after_comp > after_dedup:
        print(f"[WARNING] after_compression ({after_comp}) > after_dedup ({after_dedup}) "
              f"— model expanded some chunks. Check for finish_reason='length' (truncation) "
              f"or a missing length guard in compress_chunk.")

    # Verify no critical flags lost
    if baseline_trace["critical_before"] != baseline_trace["critical_after"]:
        print(f"[WARNING] Baseline lost critical flags: {baseline_trace['critical_before']} -> {baseline_trace['critical_after']}")
    if optimized_trace["critical_before"] != optimized_trace["critical_after"]:
        print(f"[WARNING] Optimized lost critical flags: {optimized_trace['critical_before']} -> {optimized_trace['critical_after']}")

    assert optimized_trace["critical_before"] == optimized_trace["critical_after"], \
        f"Critical flag mismatch: before={optimized_trace['critical_before']}, after={optimized_trace['critical_after']}"

    # Calculate Costs
    baseline_costs = calculate_costs(original_tokens_chunks, baseline_final_tokens, embed_tokens, {"prompt_tokens": 0, "candidates_tokens": 0})
    optimized_costs = calculate_costs(original_tokens_chunks, optimized_final_tokens, embed_tokens, api_usage)

    # Report results
    col = COMPRESSION_MODEL if decision.route == "FULL" else "LIGHT (No LLM)"
    print(f"{'Metric':<35} | {'Baseline (No Comp)':<22} | {f'Optimized ({col})':<22}")
    print("-" * 90)
    print(f"{'Original Tokens':<35} | {original_tokens_chunks:<22} | {original_tokens_chunks:<22}")
    print(f"{'Tokens after Tier 1 (Dedup)':<35} | {optimized_trace['stage_tokens']['after_dedup']:<22} | {optimized_trace['stage_tokens']['after_dedup']:<22}")
    print(f"{'Tokens after Compression':<35} | {'(none)':<22} | {optimized_trace['stage_tokens']['after_compression']:<22}")
    print(f"{'Final Tokens (after Budget)':<35} | {baseline_final_tokens:<22} | {optimized_final_tokens:<22}")

    # Note: both are capped at token_budget — compare after_compression for real compression effect
    compress_red = (1 - optimized_trace['stage_tokens']['after_compression'] / original_tokens_chunks) * 100
    baseline_red = (1 - baseline_final_tokens / original_tokens_chunks) * 100
    optimized_red = (1 - optimized_final_tokens / original_tokens_chunks) * 100
    print(f"{'Reduction % (after compression)':<35} | {'n/a':<22} | {compress_red:.2f}%")
    print(f"{'Reduction % (after budget)':<35} | {baseline_red:.2f}%{'' : <16} | {optimized_red:.2f}%")
    print("-" * 90)
    print(f"{'Pinned Chunks':<35} | {baseline_trace['chunks_pinned_critical']:<22} | {optimized_trace['chunks_pinned_critical']:<22}")
    print(f"{'Compressed Chunks':<35} | {baseline_trace['chunks_compressed']:<22} | {optimized_trace['chunks_compressed']:<22}")
    print(f"{'Budget-Dropped Chunks':<35} | {baseline_trace['chunks_removed_by_budget']:<22} | {optimized_trace['chunks_removed_by_budget']:<22}")
    print(f"{'Critical Flags (Before -> After)':<35} | {baseline_trace['critical_before']} -> {baseline_trace['critical_after']:<16} | {optimized_trace['critical_before']} -> {optimized_trace['critical_after']:<16}")
    print(f"{'Fallback Triggered':<35} | {str(baseline_trace['fallback_triggered']):<22} | {str(optimized_trace['fallback_triggered']):<22}")
    print("-" * 90)
    print(f"{'Answering Call Cost':<35} | ${baseline_costs['optimized_answering_cost']:.6f}{'' : <14} | ${optimized_costs['optimized_answering_cost']:.6f}")
    print(f"{'Pipeline Compression Cost':<35} | ${baseline_costs['pipeline_compression_cost']:.6f}{'' : <14} | ${optimized_costs['pipeline_compression_cost']:.6f}")
    print(f"{'Total Cost (Answering + Pipeline)':<35} | ${baseline_costs['total_optimized_cost']:.6f}{'' : <14} | ${optimized_costs['total_optimized_cost']:.6f}")
    print(f"{'Unoptimized Base Cost':<35} | ${baseline_costs['unoptimized_cost']:.6f}{'' : <14} | ${optimized_costs['unoptimized_cost']:.6f}")
    print(f"{'Net Savings vs Unoptimized':<35} | ${baseline_costs['net_savings']:.6f}{'' : <14} | ${optimized_costs['net_savings']:.6f}")
    print("-" * 90)
    print(f"API Tokens Used for Compression: Prompt={api_usage['prompt_tokens']}, Candidates={api_usage['candidates_tokens']}")
    print_separator()
    print()

    # 4. Evaluate Answer Quality
    optimized_context = "".join([c.text for c in optimized_output])
    quality_res = evaluate_answer_quality(
        query=query,
        original_context=context,
        optimized_context=optimized_context,
        comparison_type=comparison_type,
        deterministic_checks=deterministic_checks,
        skip_llm_calls=False
    )

    # Print quality evaluation results
    print_separator("-")
    if comparison_type == "deterministic":
        print("ANSWER QUALITY EVALUATION (Deterministic Checks):")
        for res in quality_res.deterministic_results:
            status = "PASS" if res["passed"] else "FAIL"
            print(f"  - {res['name']}: {status} ({res['description']})")
        print(f"  Overall: {'PASS' if quality_res.passed else 'FAIL'}")
    else:
        print("ANSWER QUALITY EVALUATION (LLM Judge):")
        print(f"  Answer A (Baseline) Score  : {quality_res.judge_score_baseline}/10")
        print(f"  Answer B (Optimized) Score : {quality_res.judge_score_optimized}/10")
        print(f"  Reasoning                  : {quality_res.judge_reasoning}")
        print(f"  * Note: Both answers and judge evaluations were processed using the {COMPRESSION_MODEL} model family.")
        print(f"    This may introduce self-preference bias.")
    print_separator("-")
    print()

    # Return a consistent dictionary object for the caller
    optimized_trace["route"] = decision.route
    optimized_trace["reasoning"] = decision.reasoning
    return {
        "original_tokens": original_tokens_chunks,
        "final_tokens": optimized_final_tokens,
        "reduction_pct": optimized_red,
        "route": decision.route,
        "trace": optimized_trace,
        "output_chunks": optimized_output,
        "quality_result": quality_res,
        "baseline_costs": baseline_costs,
        "optimized_costs": optimized_costs
    }

def run_fallback_test():
    print_separator()
    print(" RUNNING FALLBACK INTEGRITY TEST")
    print_separator("-")
    
    query = "What is the timeout duration?"
    context = (
        "[SYSTEM]\nYou are a helpful database assistant.\n"
        "[DOC]\nTimeout is set to 30 seconds for all queries.\n"
        "[CONVERSATION]\nWe are currently using Postgres for our database.\n"
    )
    
    ranked_chunks = rank_chunks(query, context, dedup_threshold=0.85)

    # Injected compression function that intentionally raises an exception
    def failing_compression_fn(prompt):
        raise RuntimeError("Simulated connection timeout / API key failure.")

    try:
        output_chunks, trace = optimize_chunks(
            query=query,
            chunks=ranked_chunks,
            token_budget=100,
            llm_call_fn=failing_compression_fn
        )

        print("Pipeline Execution: SUCCESS (Did not crash!)")
        print(f"Fallback Triggered in Trace: {trace['fallback_triggered']}")
        print(f"Chunks in Output: {len(output_chunks)}")
        print("Output Chunk Texts:")
        for c in output_chunks:
            print(f"  - [{c.tag}] (Pinned={c.pinned}): {c.text.strip()}")
        
        # Verify fallback properties
        assert trace["fallback_triggered"] is True, "Fallback flag should be True"
        print("Fallback Integrity Test PASSED!")
    except Exception as e:
        print(f"Fallback Integrity Test FAILED with error: {e}")
    print_separator()
    print()

if __name__ == "__main__":
    print_separator()
    print(" STARTING TOKEN SAVINGS & PIPELINE PERFORMANCE EVALUATION")
    print_separator()
    print()

    results = []

    # --- Scenario 1: Mostly Irrelevant Context ---
    s1_query = "How do we handle HTTP 500 errors?"
    s1_context = (
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
    # Relevance filtering should drop almost everything except SYSTEM and the HTTP 500 block.
    # Tight token budget to enforce dropping.
    res1 = run_scenario("Mostly Irrelevant Context", s1_query, s1_context, token_budget=80)
    results.append(("Mostly Irrelevant Context", res1))

    # --- Scenario 2: Everything Relevant ---
    s2_query = "Explain how vector indexing and cosine similarity work together."
    s2_context = (
        "[SYSTEM]\nYou are a technical retrieval assistant.\n"
        "[DOC]\nVector search indexing uses cosine similarity across dense embeddings to retrieve relevant documentation sections rapidly.\n"
        "[DOC]\nCosine similarity measures the angle between two embedding vectors to evaluate semantic relatedness.\n"
        "[DOC]\nDense embeddings represent text chunks as high-dimensional floats capturing semantic concepts.\n"
        "[DOC]\nDatabase documentation retrieval searches for matches between user queries and index vectors.\n"
    )
    # Everything is relevant, so relevance filter won't drop them. Compression must shrink them.
    res2 = run_scenario("Everything Relevant", s2_query, s2_context, token_budget=100)
    results.append(("Everything Relevant", res2))

    # --- Scenario 3: Adversarial Context ---
    s3_query = "What are the core database rules and timeout constraints?"
    s3_context = (
        "[SYSTEM]\nYou are a helpful operations coordinator. Always remember critical constraints.\n"
        "[DOC]\nDo NOT use MongoDB for this project.\n"
        "[DOC]\nTimeout is set to 30 seconds for all queries.\n"
        "[DOC]\nThe API must remain stateless even under load.\n"
        "[CONVERSATION]\nWe decided to migrate off Postgres to DynamoDB next quarter.\n"
        "[TOOL_OUTPUT]\nEndpoint returns HTTP 401 after the auth change.\n"
        "[DOC]\nWe should have sandwiches for lunch tomorrow.\n"
    )
    # All except the lunch block are critical and should trigger flags -> pinned.
    # The lunch block is irrelevant and should be dropped or compressed.
    # Pinned blocks should not be compressed or lost.
    res3 = run_scenario("Adversarial Context", s3_query, s3_context, token_budget=120)
    results.append(("Adversarial Context", res3))

    # --- Scenario 4: Benign False-Positive Phrases ---
    s4_query = "What database should we use?"
    s4_context = (
        "[SYSTEM]\nYou are an database architecture assistant.\n"
        "[DOC]\nNeither option matters much for our simple test setup.\n"
        "[DOC]\nWe can deploy the application without any special configuration.\n"
        "[CONVERSATION]\nThe database choice is Postgres.\n"
        "[DOC]\nWe should test it today.\n"
    )
    # "Neither" and "without" should NOT trigger critical flags, so critical_before should be 0.
    res4 = run_scenario("Benign False-Positive Phrases", s4_query, s4_context, token_budget=100)
    results.append(("Benign False-Positive Phrases", res4))
    
    optimized_output = res4["output_chunks"]
    trace = res4["trace"]
    
    # Assert that no critical flags were detected (excluding SYSTEM tag pinning, which is based on tag, not critical flags)
    # Let's inspect the chunks containing the false-positive phrases
    if trace and trace.get("route") != "SKIP":
        print("Inspecting benign false-positive chunks critical flags:")
        for c in optimized_output:
            if "Neither option" in c.text or "without any" in c.text:
                print(f"  Chunk: '{c.text.strip()}' -> Critical Flags: {c.critical_flags} | Pinned: {c.pinned}")
                assert len(c.critical_flags) == 0, f"Spurious critical flags detected on benign text: {c.critical_flags}"
                assert c.pinned is False, "Benign text was spuriously pinned!"
        print("Benign False-Positive Verification PASSED!\n")

    # --- Scenario 5: Large Context (Force FULL Routing) ---
    s5_query = "Summarize the database constraints and the weather."
    # We create a large context by combining the previous ones multiple times 
    # to exceed the SKIP_TOKEN_FLOOR of 500 tokens.
    s5_context = (s1_context + s2_context + s3_context) * 3
    res5 = run_scenario("Large Context (Force FULL)", s5_query, s5_context, token_budget=200)
    results.append(("Large Context (Force FULL)", res5))

    # --- Scenario 6: Database SSL Configuration Documentation ---
    s6_query = "How do I configure client SSL options and certificate validation for PostgreSQL?"
    s6_context = (
        "[SYSTEM]\nYou are a cloud infrastructure assistant. Help configure secure database connections.\n"
        "[DOC]\n"
        "PostgreSQL supports secure connections using SSL/TLS to encrypt client/server communications. "
        "The security behavior is configured using the 'sslmode' parameter in the connection string or environment variables. "
        "There are six primary SSL modes:\n"
        "1. disable: SSL is not used. Communications are unencrypted and vulnerable to eavesdropping.\n"
        "2. allow: Client attempts a non-SSL connection first. If that fails, it tries SSL.\n"
        "3. prefer: Client attempts SSL first. If it fails, it falls back to non-SSL (default behavior).\n"
        "4. require: Client requires SSL. It will fail if the server does not support SSL. No certificate verification is performed.\n"
        "5. verify-ca: Client requires SSL and verifies that the server's certificate is signed by a trusted Certificate Authority (CA).\n"
        "6. verify-full: Client requires SSL, verifies the CA signature, and additionally validates that the server host name matches the name in the certificate. This protects against man-in-the-middle attacks.\n"
        "\n"
        "[DOC]\n"
        "To perform server certificate validation (verify-ca or verify-full), the client must have access to the trusted root CA certificate. "
        "This is typically configured via connection parameters or environment variables:\n"
        "- Connection parameters: 'sslrootcert=path/to/server-ca.pem' specifies the path to the root CA file.\n"
        "- Environment variables: PGSSLROOTCERT environment variable can be set to the path of the certificate file.\n"
        "If verify-full is selected, the server's common name (CN) or subject alternative name (SAN) in its certificate must match the host name provided by the client in the connection string. "
        "If it does not match, connection establishment will fail with a hostname verification error.\n"
        "\n"
        "[DOC]\n"
        "Client certificate authentication can also be configured. When the server is set up to require client certificates, the client must present its own certificate and private key:\n"
        "- sslcert: Path to the client's SSL certificate file (e.g. 'sslcert=certs/client-cert.pem').\n"
        "- sslkey: Path to the client's private key file (e.g. 'sslkey=certs/client-key.key').\n"
        "The permissions on the private key file must be strictly restricted (e.g. chmod 0600 on UNIX systems), or the client library will refuse to use it for security reasons, resulting in connection failure.\n"
        "\n"
        "[DOC]\n"
        "Here are connection string examples in common languages:\n"
        "Python (psycopg2):\n"
        "conn = psycopg2.connect(\"dbname=mydb user=postgres password=secret host=db.example.com port=5432 sslmode=verify-full sslrootcert=/etc/ssl/certs/db-ca.crt\")\n"
        "\n"
        "Node.js (pg):\n"
        "const client = new Client({\n"
        "  host: 'db.example.com',\n"
        "  database: 'mydb',\n"
        "  ssl: {\n"
        "    rejectUnauthorized: true,\n"
        "    ca: fs.readFileSync('/etc/ssl/certs/db-ca.crt').toString(),\n"
        "  }\n"
        "})\n"
        "\n"
        "Go (lib/pq):\n"
        "db, err := sql.Open(\"postgres\", \"postgres://postgres:secret@db.example.com:5432/mydb?sslmode=verify-full&sslrootcert=/etc/ssl/certs/db-ca.crt\")\n"
        "\n"
        "[DOC]\n"
        "Performance considerations: Establishing SSL connections introduces network and CPU overhead because of the cryptographic handshakes (RSA/Diffie-Hellman key exchanges). "
        "To mitigate latency spikes, especially in serverless or highly dynamic environments, it is strongly recommended to use a connection pooler like pgBouncer. "
        "When pgBouncer is positioned between the client and server, it maintains a pool of pre-established, encrypted connections to the database server. "
        "The clients connect to pgBouncer, which can be configured with lighter SSL overhead or local socket connections, dramatically reducing the connection startup latency from ~150ms to <5ms.\n"
        "\n"
        "[DOC]\n"
        "Common SSL connection errors and resolution steps:\n"
        "1. 'SSL error: certificate verify failed' - This indicates the server's certificate is not signed by any CA in the client's sslrootcert file. Resolve this by verifying that the CA certificate in sslrootcert matches the CA that signed the database server's certificate.\n"
        "2. 'private key file has group or world access; permissions should be u=rw (0600) or less' - This occurs when the client private key file permissions are too loose. Run 'chmod 600 client.key' to secure it.\n"
        "3. 'hostname name matching failed' - The hostname in the connection string does not match the CN/SAN in the database server's SSL certificate. Confirm the correct host domain or adjust the sslmode to verify-ca if hostname checks are not required.\n"
    ) * 4 # Multiplying naturally structured text blocks to reach ~2200 tokens
    res6 = run_scenario("Database SSL Configuration", s6_query, s6_context, token_budget=600)
    results.append(("Database SSL Configuration", res6))

    # --- Scenario 7: Production Database Incident Logs ---
    s7_query = "What was the root cause of the connection pool exhaustion on 2026-08-25?"
    s7_context = (
        "[SYSTEM]\nYou are a senior SRE. Diagnose the production incident from the logs and chat transcript.\n"
        "[CONVERSATION]\n"
        "Timestamp: 2026-08-25T14:10:00Z\n"
        "alice: Hey Team, we are seeing a spike in HTTP 500 errors on the API gateway. The error rate is up to 15%.\n"
        "bob: Looking at the metrics, the application servers are reporting connection pool exhaustion. All 50 max connections in the pool are active and waiting.\n"
        "alice: Are we seeing high database CPU? The DB dashboard shows CPU usage is low at ~12%, but active connections are capped at the max_connections limit of 100.\n"
        "charlie: That's weird. If CPU is low, it might not be a heavy CPU calculation query. Maybe we have locks or queries waiting on locks?\n"
        "bob: Let's run the pg_stat_activity query to see what queries are running right now.\n"
        "alice: I ran it. Here is the output: we have 80 active connections executing: 'SELECT * FROM users WHERE email = $1 FOR UPDATE'. They are all waiting on a transaction that started 5 minutes ago.\n"
        "charlie: Oh! 'FOR UPDATE' acquires an exclusive row lock on the user record. Who started that long-running transaction?\n"
        "bob: Checking the logs... Ah, the billing-service initiated a transaction at 14:05:00Z to process a payment, but it timed out calling the external payment gateway. It didn't release the database connection or commit/rollback the transaction!\n"
        "alice: Excellent catch. The billing-service had no timeout on the external API call, so it hung indefinitely, holding the database row lock. Other API requests tried to update the same users, queued up, exhausted the pool, and crashed the front-end.\n"
        "charlie: I will restart the billing-service container to kill the hung connections. alice, please add an API timeout to the payment gateway client.\n"
        "\n"
        "[TOOL_OUTPUT]\n"
        "Database pg_stat_activity Log (2026-08-25T14:08:00Z):\n"
        "datname | pid  | state  | query_start         | wait_event_type | wait_event | query\n"
        "--------+------+--------+---------------------+-----------------+------------+-------\n"
        "app_db  | 1205 | active | 2026-08-25T14:05:00 | Client          | ClientRead | BEGIN; SELECT balance FROM accounts WHERE user_id = 9987 FOR UPDATE; -- HUNG CALL\n"
        "app_db  | 1210 | active | 2026-08-25T14:06:12 | Lock            | transaction| SELECT balance FROM accounts WHERE user_id = 9987 FOR UPDATE;\n"
        "app_db  | 1215 | active | 2026-08-25T14:06:45 | Lock            | transaction| SELECT balance FROM accounts WHERE user_id = 9987 FOR UPDATE;\n"
        "app_db  | 1220 | active | 2026-08-25T14:07:01 | Lock            | transaction| SELECT balance FROM accounts WHERE user_id = 9987 FOR UPDATE;\n"
        "app_db  | 1230 | active | 2026-08-25T14:07:30 | Lock            | transaction| SELECT balance FROM accounts WHERE user_id = 9987 FOR UPDATE;\n"
        "app_db  | 1245 | active | 2026-08-25T14:07:55 | Pooler          | MaxPool    | SELECT * FROM users WHERE email = 'test@example.com';\n"
        "\n"
        "[DOC]\n"
        "Application Server Log traces:\n"
        "2026-08-25T14:06:15Z ERROR app-web-01 ConnectionPoolExhaustedException: Timeout waiting for connection from pool after 10000ms.\n"
        "  at org.apache.tomcat.jdbc.pool.ConnectionPool.borrowConnection(ConnectionPool.java:672)\n"
        "  at org.apache.tomcat.jdbc.pool.ConnectionPool.getConnection(ConnectionPool.java:188)\n"
        "  at com.example.service.UserService.getUserByEmail(UserService.java:45)\n"
        "2026-08-25T14:06:22Z ERROR app-web-02 ConnectionPoolExhaustedException: Timeout waiting for connection from pool after 10000ms.\n"
        "2026-08-25T14:06:40Z ERROR app-web-01 ConnectionPoolExhaustedException: Timeout waiting for connection from pool after 10000ms.\n"
        "\n"
        "[DOC]\n"
        "Incident Post-Mortem Report Summary:\n"
        "Severity: P0 - Critical Outage\n"
        "Date: 2026-08-25\n"
        "Duration: 25 minutes (14:05 to 14:30 UTC)\n"
        "Impacted System: Customer Payment & User Profiling services.\n"
        "Root Cause: The billing microservice initiated a database transaction with 'SELECT FOR UPDATE' on the accounts table (user_id 9987). "
        "It then issued an outbound HTTP call to the payment gateway (Stripe API) without setting a request timeout. "
        "The Stripe API gateway experienced degradation and became unresponsive. "
        "The billing microservice hung while waiting for the HTTP response, keeping the database transaction open and holding the row lock on user 9987. "
        "Subsequent customer requests attempting to update account information queued up behind the lock, quickly occupying all available database connection pool slots in the application gateway and leading to connection pool exhaustion across all web nodes.\n"
        "Resolution: Restarted billing service containers to forcefully close open sessions and terminate the database transaction locks. Added a strict 5000ms timeout on all outbound gateway API clients.\n"
    ) * 4 # Repeat blocks to reach ~3400 tokens
    res7 = run_scenario("Production Incident Logs", s7_query, s7_context, token_budget=800)
    results.append(("Production Incident Logs", res7))

    # --- Scenario 8: Microservice Architecture & Caching Design Requirement ---
    s8_query = "What are the session state security rules and Redis caching patterns?"
    s8_context = (
        "[SYSTEM]\nYou are a principal software architect. Summarize the caching architecture and security rules.\n"
        "[DOC]\n"
        "Session State Management Specifications:\n"
        "All user session payloads are stored in a centralized, secure Redis cache to ensure statelessness on the application tier. "
        "The session cache must be isolated from the product catalog cache to prevent memory exhaustion resource leaks. "
        "The following security rules must be strictly implemented for session storage:\n"
        "1. Session tokens must be cryptographically secure random identifiers (UUIDv4) and must not contain any encoded user details.\n"
        "2. Session payloads stored in Redis must be encrypted at rest using AES-256-GCM. The encryption key must be rotated every 90 days.\n"
        "3. Redis connections must utilize TLS 1.3 to encrypt session data in transit. Plaintext Redis ports (6379) are strictly disabled.\n"
        "4. Session TTL (Time-To-Live) is set to exactly 1800 seconds (30 minutes). Every user action resets the TTL to prevent premature expiration.\n"
        "5. The application must enforce a secure HttpOnly, Secure, and SameSite=Strict flag on all session cookies issued to clients.\n"
        "\n"
        "[DOC]\n"
        "Redis Caching Patterns and Strategies:\n"
        "Our application implements the Cache-Aside (Lazy Loading) pattern for retrieving static data collections:\n"
        "- When a request for data arrives, the application first checks the Redis cluster for a cache hit.\n"
        "- If a cache miss occurs, the data is fetched from the primary PostgreSQL database, written back to the Redis cache, and returned to the client.\n"
        "Eviction Policy: The Redis cluster is configured with the 'allkeys-lru' (Least Recently Used) eviction policy. "
        "This ensures that when memory allocation reaches the 85% threshold, Redis automatically evicts the oldest inactive sessions and objects to accommodate new allocations, preventing OOM crashes.\n"
        "TTL Strategies:\n"
        "- User Profile metadata: TTL of 86400 seconds (24 hours).\n"
        "- Session State: TTL of 1800 seconds (30 minutes).\n"
        "- Temporary Token storage: TTL of 300 seconds (5 minutes).\n"
        "\n"
        "[DOC]\n"
        "Architectural overview of unrelated services (for design completeness):\n"
        "Docker Registry: All base images are retrieved from our private registry at registry.example.com. "
        "DevOps pipelines are configured to scan all images for vulnerabilities using Trivy before deploying to production.\n"
        "Kubernetes deployment guidelines: Deployments are structured into namespaces (dev, staging, prod). "
        "Each pod is configured with strict resources requests and limits: CPU (requests: 100m, limits: 500m), Memory (requests: 256Mi, limits: 512Mi). "
        "Horizontal Pod Autoscalers (HPA) scale the deployments when average CPU utilization exceeds the 70% threshold.\n"
        "\n"
        "[DOC]\n"
        "CI/CD Pipeline Configuration details:\n"
        "The pipeline is triggered on every pull request merge to the main branch. "
        "It executes three stages: unit tests, code linting (using ESLint and Black), and docker build. "
        "Environment variables are injected at runtime via Kubernetes Secrets:\n"
        "- NODE_ENV=production\n"
        "- API_VERSION=v2\n"
        "- SECURITY_AUDIT_ENABLED=true\n"
        "Developers must ensure that no plaintext credentials or sensitive keys are committed directly to the git repository. "
        "A git pre-commit hook runs Talisman to check for accidental credentials leakage before committing.\n"
    ) * 4 # Repeat blocks to reach ~3800 tokens
    res8 = run_scenario("Microservice Architecture & Caching", s8_query, s8_context, token_budget=900)
    results.append(("Microservice Architecture & Caching", res8))

    # ── AGGREGATE SUMMARY (Excluding SKIP Scenarios) ──
    print_separator()
    print(" PIPELINE EVALUATION SUMMARY (Excluding SKIP Scenarios)")
    print_separator()
    
    skipped_scenarios = [name for name, r in results if r["route"] == "SKIP"]
    active_results = [r for name, r in results if r["route"] != "SKIP"]
    
    if active_results:
        avg_tokens_saved = sum(r["reduction_pct"] for r in active_results) / len(active_results)
        
        # Calculate answering cost savings
        total_unoptimized_cost = sum(r["baseline_costs"]["unoptimized_cost"] for r in active_results)
        total_optimized_cost = sum(r["optimized_costs"]["total_optimized_cost"] for r in active_results)
        cost_savings_pct = (1 - total_optimized_cost / total_unoptimized_cost) * 100 if total_unoptimized_cost > 0 else 0.0
        
        print(f"Scenarios Optimized (FULL/LIGHT): {len(active_results)}")
        print(f"Average Token Reduction         : {avg_tokens_saved:.2f}%")
        print(f"Net Pipeline Cost Savings       : {cost_savings_pct:.2f}%")
        
        judge_scores_base = []
        judge_scores_opt = []
        det_passes = 0
        det_totals = 0
        
        for r in active_results:
            qr = r["quality_result"]
            if qr.comparison_type == "llm_judge":
                if qr.judge_score_baseline is not None:
                    judge_scores_base.append(qr.judge_score_baseline)
                if qr.judge_score_optimized is not None:
                    judge_scores_opt.append(qr.judge_score_optimized)
            elif qr.comparison_type == "deterministic":
                if qr.passed is not None:
                    if qr.passed:
                        det_passes += 1
                    det_totals += 1
                    
        if judge_scores_base:
            avg_base = sum(judge_scores_base) / len(judge_scores_base)
            avg_opt = sum(judge_scores_opt) / len(judge_scores_opt)
            print(f"Average LLM Judge Score (Base)  : {avg_base:.2f}/10")
            print(f"Average LLM Judge Score (Optim) : {avg_opt:.2f}/10")
            
        if det_totals > 0:
            pass_rate = (det_passes / det_totals) * 100
            print(f"Deterministic Check Pass Rate   : {pass_rate:.2f}% ({det_passes}/{det_totals} scenarios)")
    else:
        print("No scenarios were optimized (all fell back or skipped).")
        
    print_separator("-")
    print("Trivially Preserved (SKIP Scenarios):")
    if skipped_scenarios:
        for name in skipped_scenarios:
            print(f"  - {name} (original context untouched)")
    else:
        print("  None")
    print_separator()
    print(f"* Self-Preference Bias Warning: Both answers and judge evaluations were processed using the {COMPRESSION_MODEL} model family.")
    print("  This may introduce self-preference bias.")
    print_separator()
    print()

    # --- Running Fallback Test ---
    run_fallback_test()
