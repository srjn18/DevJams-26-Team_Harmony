"""
Step 5: Three new realistic mid-size scenarios (2000-5000 tokens each).
Step 6: Latency measurement around each pipeline stage.

Run with:  python new_scenarios.py
"""
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os
import copy
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from semantic_relevance_engine import rank_chunks, optimize_chunks, Chunk
from semantic_relevance_engine.optimizer import approx_token_count
from semantic_relevance_engine.llm_provider import get_compress_fn, get_answer_fn, get_usage_fns
from semantic_relevance_engine.routing import decide_route
from semantic_relevance_engine.answer_quality import evaluate_answer_quality, run_llm_judge

print("=" * 80)
print(" NEW SCENARIO PIPELINE RUN (Steps 5 & 6)")
print("=" * 80)
print(f"LLM_MODEL: {os.getenv('LLM_MODEL')}")
print()

# ─────────────────────────────────────────────────────────────────
# SCENARIO A: Mostly-Irrelevant Content (~2500 tokens)
# A database-ops assistant flooded with unrelated company content.
# ─────────────────────────────────────────────────────────────────
scenario_a_query = "What are the connection pool settings and retry policies for the primary PostgreSQL database?"

scenario_a_context = (
    "[SYSTEM]\n"
    "You are a senior database operations assistant for Acme Corp.\n"
    "\n"
    "[DOC]\n"
    "Acme Corp Employee Handbook — Section 7: Office Culture\n"
    "Acme Corp has a vibrant and inclusive company culture. "
    "All employees are encouraged to participate in our monthly all-hands meetings held on the first Thursday of every month. "
    "The company provides free breakfast on Fridays, sponsored by the People Operations team. "
    "Employees may work remotely up to three days per week with manager approval. "
    "The dress code is business casual Monday through Thursday, and casual on Fridays. "
    "Team building activities are organized quarterly. Please RSVP to the events calendar two weeks in advance.\n"
    "\n"
    "[DOC]\n"
    "Acme Corp Benefits Summary — 2026 Open Enrollment\n"
    "Health insurance: Employees can choose between three tiers — Bronze, Silver, and Gold. "
    "The company covers 80% of the Gold plan premium for individuals. "
    "Dental and vision plans are available at group rates with payroll deductions. "
    "401(k) matching: Acme matches 4% of salary up to the IRS contribution limit of $23,000 for 2026. "
    "FSA and HSA accounts are available. The FSA limit is $3,200 per year. "
    "Life insurance coverage is 2x annual salary, provided at no cost to the employee.\n"
    "\n"
    "[DOC]\n"
    "Infrastructure as Code — Terraform Module Registry\n"
    "All infrastructure is provisioned through Terraform and stored in the acme-infra-terraform Git repository. "
    "Modules are versioned using semantic versioning. The current active modules include: "
    "vpc-module v2.4.1, rds-module v3.1.0, eks-cluster v1.9.2, s3-bucket v4.0.1. "
    "All module versions must be pinned in production environments to prevent unintended drift. "
    "Use 'terraform plan -out=tfplan' before applying any changes. "
    "Terraform state is stored in S3 at s3://acme-corp-terraform-state/ with DynamoDB locking.\n"
    "\n"
    "[DOC]\n"
    "PostgreSQL Primary Database Connection Configuration\n"
    "Host: postgres-primary.internal.acme.com\n"
    "Port: 5432\n"
    "Database: acme_production\n"
    "Connection Pool Settings (PgBouncer):\n"
    "  - pool_mode: transaction\n"
    "  - max_client_conn: 500\n"
    "  - default_pool_size: 50\n"
    "  - reserve_pool_size: 10\n"
    "  - reserve_pool_timeout: 5 seconds\n"
    "  - max_db_connections: 100\n"
    "  - server_idle_timeout: 600 seconds\n"
    "Retry Policy (application layer):\n"
    "  - Max retries: 3\n"
    "  - Backoff: exponential with jitter, base 500ms, max 8000ms\n"
    "  - Retry on: connection refused, server closed connection, lock timeout\n"
    "  - Do NOT retry on: authentication failure, constraint violation, syntax error\n"
    "\n"
    "[DOC]\n"
    "Acme Corp Marketing Team Quarterly OKRs — Q3 2026\n"
    "Objective 1: Increase brand awareness in the APAC market by 25% by end of Q3. "
    "Key Result 1.1: Run 5 targeted LinkedIn campaigns reaching 500,000 impressions. "
    "Key Result 1.2: Publish 12 thought leadership articles on the company blog. "
    "Key Result 1.3: Attend 3 industry conferences in Singapore, Tokyo, and Sydney.\n"
    "Objective 2: Launch the new enterprise product tier by September 15, 2026. "
    "Key Result 2.1: Complete all product copy and landing pages by August 31. "
    "Key Result 2.2: Coordinate a press release with PR agency by September 1.\n"
    "\n"
    "[DOC]\n"
    "Legal Department — Software License Compliance\n"
    "All open-source software dependencies must be reviewed by the legal team before use in production. "
    "Licenses permitted without review: MIT, Apache 2.0, BSD 2/3-clause. "
    "Licenses requiring legal review: LGPL, GPL, AGPL, CDDL, MPL. "
    "Licenses strictly prohibited: SSPL, Commons Clause. "
    "Please submit a Software Dependency Request via the ServiceNow portal for any GPL-family dependencies. "
    "Response time is typically 5 business days.\n"
    "\n"
    "[DOC]\n"
    "Catering and Events — 2026 Company Holiday Schedule\n"
    "January 1 — New Year's Day (observed January 2 if falls on Saturday). "
    "January 20 — Martin Luther King Jr. Day. "
    "May 26 — Memorial Day. "
    "July 4 — Independence Day. "
    "September 1 — Labor Day. "
    "November 27-28 — Thanksgiving break. "
    "December 25-26 — Winter holiday. "
    "The office will close at 2 PM on December 24 and December 31 for holiday observance.\n"
) * 2  # ~2400 tokens

# ─────────────────────────────────────────────────────────────────
# SCENARIO B: Highly-Relevant Single-Topic (~2800 tokens)
# A dense technical incident investigation — entirely on-topic.
# ─────────────────────────────────────────────────────────────────
scenario_b_query = "What caused the memory leak in the WebSocket notification service and how was it fixed?"

scenario_b_context = (
    "[SYSTEM]\n"
    "You are a senior backend engineer conducting a post-mortem analysis.\n"
    "\n"
    "[CONVERSATION]\n"
    "Timestamp: 2026-08-20T09:15:00Z\n"
    "priya: The notification-service pods are OOMKilled again. This is the third time this week. Memory usage climbs from 256MB to 512MB limit over ~90 minutes, then gets killed.\n"
    "daniel: That's a WebSocket leak. Let me look at the connection registry code.\n"
    "priya: The Kubernetes events show 'OOMKilled' on all three replicas at the same time, which means the load balancer was distributing connections and all pods hit the limit simultaneously after the same duration.\n"
    "daniel: I found it. In NotificationService.java line 847, we create a WebSocket session listener on every new connection but we never remove it from the static `SESSION_REGISTRY` map when the connection closes.\n"
    "priya: Oh no. The SESSION_REGISTRY is a ConcurrentHashMap and it's never cleaned up?\n"
    "daniel: Exactly. It's declared as a static final field, so it lives for the entire JVM lifetime. Each WebSocket session holds a reference to the user's subscription list and the message buffer — around 8KB per session. After 90 minutes we accumulate roughly 65,000 sessions (based on our 700 connections/minute rate) and that's 512MB.\n"
    "priya: Why doesn't the close event trigger cleanup?\n"
    "daniel: The issue is in the `@OnClose` handler. Look at line 912 — it calls `SESSION_REGISTRY.remove(session)` but the session object itself is a new wrapper instance, not the same reference that was PUT. We're using object identity comparison instead of the session ID.\n"
    "priya: Ah, classic Java reference equality trap. So the map fills but remove() never matches.\n"
    "daniel: Right. The fix is: (1) key the map by `session.getId()` (a String) instead of the session object reference. (2) In @OnClose, call `SESSION_REGISTRY.remove(session.getId())`. (3) Add a scheduled cleanup task every 5 minutes to remove entries whose sessions report `!session.isOpen()`.\n"
    "priya: And we should add a metric gauge on SESSION_REGISTRY.size() so we can alert before we hit OOM.\n"
    "daniel: Agreed. I'll add a Micrometer gauge and set a PagerDuty alert if size exceeds 20,000.\n"
    "\n"
    "[TOOL_OUTPUT]\n"
    "HeapDump Analysis — notification-service-pod-2 (2026-08-20T08:55:00Z)\n"
    "Tool: Eclipse Memory Analyzer (MAT)\n"
    "Total heap: 498 MB (512 MB limit)\n"
    "Retained heap of top offenders:\n"
    "  1. java.util.concurrent.ConcurrentHashMap @ 0x7f3a8c000 — 487 MB (97.8%)\n"
    "     Reference path: NotificationService.SESSION_REGISTRY (static)\n"
    "     Entry count: 62,943\n"
    "     Avg entry size: ~7.9 KB\n"
    "     Key type: jakarta.websocket.Session (object reference)\n"
    "     Value type: com.acme.notification.UserSubscription\n"
    "  2. byte[] buffers in UserSubscription.messageBuffer — 310 MB total\n"
    "     Retained per entry: ~4.9 KB average\n"
    "  3. SunTlsKeyMaterial (TLS session keys) — 24 MB\n"
    "Unreachable closed sessions in map: ~61,200 out of 62,943 (97.2%)\n"
    "\n"
    "[DOC]\n"
    "Fix Applied — Commit SHA: a3f9b2c (2026-08-20, author: daniel)\n"
    "Files changed: NotificationService.java (+18 lines, -3 lines)\n"
    "Change 1: Convert SESSION_REGISTRY key from Session object to String session ID.\n"
    "  Before: private static final Map<Session, UserSubscription> SESSION_REGISTRY = new ConcurrentHashMap<>();\n"
    "  After:  private static final Map<String, UserSubscription>  SESSION_REGISTRY = new ConcurrentHashMap<>();\n"
    "Change 2: Fix @OnOpen to use session ID as key.\n"
    "  Before: SESSION_REGISTRY.put(session, subscription);\n"
    "  After:  SESSION_REGISTRY.put(session.getId(), subscription);\n"
    "Change 3: Fix @OnClose to remove by session ID.\n"
    "  Before: SESSION_REGISTRY.remove(session);\n"
    "  After:  SESSION_REGISTRY.remove(session.getId());\n"
    "Change 4: Add scheduled cleanup every 5 minutes.\n"
    "  Added: @Scheduled(fixedRate = 300_000) void cleanClosedSessions() { SESSION_REGISTRY.entrySet().removeIf(e -> !sessionManager.isOpen(e.getKey())); }\n"
    "Change 5: Add Micrometer gauge for registry size.\n"
    "  Added: Metrics.gauge('websocket.session.registry.size', SESSION_REGISTRY, Map::size);\n"
    "\n"
    "[DOC]\n"
    "Post-Fix Verification — 2026-08-21 (24h monitoring)\n"
    "Memory usage after fix: Stable at 85-110 MB across all 3 replicas.\n"
    "SESSION_REGISTRY.size() gauge: Peaks at ~800 during business hours, drops to ~50 overnight.\n"
    "No OOMKilled events in 24h post-deployment.\n"
    "Alert threshold set at 20,000 sessions; PagerDuty integration verified.\n"
    "Load test at 2x normal traffic: Memory stayed below 200 MB with cleanup running.\n"
)
# Repeat for volume (already ~1800 tokens, multiply for realistic density)
scenario_b_context = scenario_b_context * 2  # ~3600 tokens


# ─────────────────────────────────────────────────────────────────
# SCENARIO C: Adversarial — Critical facts embedded in prose (~3200 tokens)
# Multi-paragraph text with 5 critical facts buried naturally.
# ─────────────────────────────────────────────────────────────────
scenario_c_query = "What are the hard constraints on the payment service — authentication, rate limits, database choice, timeout, and encryption?"

scenario_c_context = (
    "[SYSTEM]\n"
    "You are a principal engineer reviewing payment service architecture requirements.\n"
    "\n"
    "[DOC]\n"
    "Payment Service Architecture Overview — Version 3.2\n"
    "\n"
    "Background and Business Context\n"
    "The Acme payment service was first introduced in 2019 as a thin wrapper around the legacy Stripe integration. "
    "Over the past six years, the service has grown considerably in scope, now handling recurring subscriptions, "
    "refund processing, invoice generation, and dispute management. The team has grown from two to eleven engineers. "
    "In 2024, the decision was made to redesign the service from scratch using a microservice architecture. "
    "The new architecture was formally approved by the CTO in Q1 2026 after an extensive review process "
    "involving the security team, the platform engineering group, and external compliance auditors.\n"
    "\n"
    "Authentication Architecture\n"
    "One of the most debated decisions during the architecture review was the choice of authentication mechanism. "
    "Several approaches were considered, including mutual TLS, OAuth2 with client credentials, and API key-based auth "
    "using HMAC-SHA256 request signing. The security team spent three weeks evaluating each approach against "
    "the threat model for a PCI-DSS Level 1 compliant environment. After the evaluation, the team concluded that "
    "the payment service MUST authenticate all inbound API calls using OAuth2 client credentials with JWT tokens "
    "signed using RS256. Symmetric signing algorithms such as HS256 are explicitly prohibited because they require "
    "sharing the signing secret across all services, which violates the principle of least privilege in a "
    "multi-tenant microservice environment. The access token lifetime is 15 minutes. Refresh tokens are not issued "
    "for service-to-service calls; each caller must re-authenticate before the token expires.\n"
    "\n"
    "Traffic and Rate Limiting\n"
    "The payment service is expected to handle a peak of roughly 1,200 transactions per minute based on the "
    "Black Friday 2025 traffic model. To protect the service during unexpected traffic spikes, engineering has "
    "implemented tiered rate limiting. The hard rate limit is 500 requests per second per client ID. "
    "Requests that exceed this threshold will receive an HTTP 429 Too Many Requests response with a "
    "'Retry-After' header indicating the next available request window. The payment gateway downstream "
    "(Stripe) also enforces its own limits of 100 requests per second in the live environment. "
    "Our service must not exceed this upstream limit, and the internal rate limit is set conservatively "
    "at 80 requests per second toward Stripe to leave a safety margin for retries and burst behavior.\n"
    "\n"
    "Database Technology Selection\n"
    "The team evaluated PostgreSQL, MySQL, MongoDB, Cassandra, and DynamoDB for the payment records store. "
    "The compliance audit found that the payment service must use PostgreSQL with synchronous replication "
    "and write-ahead logging (WAL) enabled for all transactional payment data. "
    "Document databases like MongoDB are prohibited for payment records due to their lack of ACID transaction "
    "guarantees at the document level when used across collections, which is incompatible with the double-entry "
    "bookkeeping model required for financial audit trails. "
    "The PostgreSQL instance must be hosted in the same AWS region as the payment service (us-east-1) "
    "and must use Multi-AZ deployment with automated failover.\n"
    "\n"
    "Timeout and Latency Requirements\n"
    "Given that payment operations are in the critical path of the user checkout flow, strict latency SLOs "
    "have been defined. The p99 target for the entire payment processing flow is 3 seconds end-to-end. "
    "Individual service call timeouts are set conservatively to ensure the budget is respected: "
    "the outbound HTTP timeout for calls to the Stripe payment gateway is exactly 8 seconds. "
    "If the Stripe gateway does not respond within 8 seconds, the call must be abandoned and treated as "
    "a soft failure — the transaction must be placed in a 'pending verification' queue for background "
    "reconciliation. Under no circumstances should the application wait indefinitely. The team learned this "
    "lesson from a 2023 production incident where an unbounded timeout caused cascading connection pool "
    "exhaustion across the entire checkout platform.\n"
    "\n"
    "Encryption at Rest and in Transit\n"
    "All payment data, including card holder data, transaction amounts, and billing addresses, must be "
    "encrypted at rest using AES-256-GCM. The encryption keys are managed by AWS KMS using automatic "
    "annual key rotation. Key access is logged to AWS CloudTrail and reviewed monthly by the security team. "
    "Data in transit between all internal services and to external gateways must use TLS 1.3 exclusively. "
    "TLS 1.2 is still permitted for legacy payment gateway connections that have not yet migrated, but "
    "a hard deprecation date of December 31, 2026 has been set for all TLS 1.2 connections. "
    "The security team conducts quarterly TLS configuration audits using testssl.sh.\n"
    "\n"
    "[DOC]\n"
    "Sprint Planning Notes — Payment Service (Sprint 47, Aug 2026)\n"
    "This sprint focuses on the rate limiter implementation and the JWT validation middleware. "
    "Story points committed: 42. Team velocity last sprint: 38. We are slightly over capacity but the "
    "deadline is firm due to the compliance audit scheduled for September 15, 2026. "
    "Please update the Jira tickets by EOD Monday so the scrum master can generate the burndown chart.\n"
    "\n"
    "[CONVERSATION]\n"
    "aditya: Quick question — can we use HS256 for the internal service tokens to simplify the key management?\n"
    "sarah: No. The security review document is explicit. RS256 only for all payment service tokens. "
    "HS256 is explicitly prohibited. I know it's more operational overhead but we cannot change this.\n"
    "aditya: And the MongoDB question — the analytics team asked if they could mirror the payment records to Mongo for reporting.\n"
    "sarah: Mirroring to Mongo for read-only analytics is a separate discussion and not covered by the "
    "current constraints. The prohibition is specifically for the authoritative payment records store.\n"
) * 2  # ~3800 tokens


def run_new_scenario(label, query, context, token_budget, comparison_type="llm_judge", deterministic_checks=None):
    print("=" * 80)
    print(f" SCENARIO: {label}")
    print("=" * 80)
    print(f"Query: {query}")

    original_tokens = approx_token_count(context)
    print(f"Context length: {len(context)} chars (~{original_tokens} tokens)")
    print(f"Token budget: {token_budget}")

    decision = decide_route(original_tokens, token_budget=token_budget)
    print(f"ROUTING DECISION: {decision.route} — {decision.reasoning}")

    if decision.route == "SKIP":
        print("SKIP route — returning original context unchanged.")
        return

    print("-" * 80)

    # ── TIER 1: rank_chunks ──
    t0 = time.time()
    ranked_chunks = rank_chunks(query, context, dedup_threshold=0.85)
    t1 = time.time()
    tier1_time = t1 - t0

    chunks_for_baseline = copy.deepcopy(ranked_chunks)
    chunks_for_optimized = copy.deepcopy(ranked_chunks)

    # ── TIER 2: optimize_chunks (baseline, no compression) ──
    t2 = time.time()
    baseline_out, baseline_trace = optimize_chunks(
        query=query, chunks=chunks_for_baseline, token_budget=token_budget, llm_call_fn=None
    )
    t3 = time.time()

    # ── TIER 2: optimize_chunks (optimized, with LLM compression) ──
    get_usage, reset_usage = get_usage_fns()
    reset_usage()
    t4 = time.time()
    compress_fn = get_compress_fn()
    optimized_out, optimized_trace = optimize_chunks(
        query=query, chunks=chunks_for_optimized, token_budget=token_budget,
        llm_call_fn=compress_fn if decision.route == "FULL" else None
    )
    t5 = time.time()
    api_usage = get_usage()

    # ── ANSWER GENERATION ──
    original_context_str = context
    optimized_context_str = "".join(c.text for c in optimized_out)

    t6 = time.time()
    answer_fn = get_answer_fn()
    baseline_answer = answer_fn(
        f"Context:\n{original_context_str}\n\nQuestion: {query}\n\nAnswer:"
    )
    optimized_answer = answer_fn(
        f"Context:\n{optimized_context_str}\n\nQuestion: {query}\n\nAnswer:"
    )
    t7 = time.time()

    # ── LLM JUDGE ──
    t8 = time.time()
    judge = run_llm_judge(query, baseline_answer, optimized_answer, original_context_str)
    t9 = time.time()

    # ── PRINT LATENCY ──
    print(f"\n[LATENCY]")
    print(f"  Tier 1 (rank_chunks)       : {tier1_time:.2f}s")
    print(f"  Tier 2 baseline run        : {t3-t2:.2f}s")
    print(f"  Tier 2 optimized run (LLM) : {t5-t4:.2f}s")
    print(f"  Answer generation (2 calls): {t7-t6:.2f}s")
    print(f"  LLM Judge                  : {t9-t8:.2f}s")
    print(f"  TOTAL wall-clock           : {t9-t0:.2f}s")

    # ── PRINT TOKEN NUMBERS ──
    original_tokens_chunked = sum(c.token_count for c in ranked_chunks)
    after_dedup = optimized_trace["stage_tokens"]["after_dedup"]
    after_comp = optimized_trace["stage_tokens"]["after_compression"]
    final_tokens = sum(c.token_count for c in optimized_out)
    baseline_final = sum(c.token_count for c in baseline_out)

    print(f"\n[TOKEN COUNTS]")
    print(f"  Original (chunked)        : {original_tokens_chunked}")
    print(f"  After dedup (Tier 1)      : {after_dedup}")
    print(f"  After compression (Tier 2): {after_comp}")
    print(f"  Final (after budget)      : {final_tokens}")
    print(f"  Baseline final            : {baseline_final}")
    reduction = (1 - final_tokens / original_tokens_chunked) * 100 if original_tokens_chunked > 0 else 0
    print(f"  Token reduction           : {reduction:.1f}%")

    print(f"\n[TRACE]")
    print(f"  chunks_pinned_critical    : {optimized_trace['chunks_pinned_critical']}")
    print(f"  chunks_compressed         : {optimized_trace['chunks_compressed']}")
    print(f"  chunks_removed_by_budget  : {optimized_trace['chunks_removed_by_budget']}")
    print(f"  critical_before -> after  : {optimized_trace['critical_before']} -> {optimized_trace['critical_after']}")
    print(f"  fallback_triggered        : {optimized_trace['fallback_triggered']}")
    print(f"  API tokens (compress)     : prompt={api_usage['prompt_tokens']}, candidates={api_usage['candidates_tokens']}")

    if optimized_trace["fallback_triggered"]:
        print("  [WARNING] fallback_triggered=True — compression calls failed/timed out!")

    print(f"\n[ANSWER QUALITY — LLM Judge]")
    print(f"  Baseline score : {judge['score_baseline']}/10")
    print(f"  Optimized score: {judge['score_optimized']}/10")
    print(f"  Reasoning      : {judge['reasoning']}")

    print(f"\n[ANSWERS]")
    print(f"  Baseline  : {baseline_answer[:300]}{'...' if len(baseline_answer) > 300 else ''}")
    print(f"  Optimized : {optimized_answer[:300]}{'...' if len(optimized_answer) > 300 else ''}")
    print()


# ─────────────────────────────────────────────────────────────────
run_new_scenario(
    label="A — Mostly Irrelevant (2400 tokens, few critical facts buried)",
    query=scenario_a_query,
    context=scenario_a_context,
    token_budget=300,
)

run_new_scenario(
    label="B — Highly Relevant Single Topic (3600 tokens, all content on-point)",
    query=scenario_b_query,
    context=scenario_b_context,
    token_budget=500,
)

run_new_scenario(
    label="C — Adversarial: 5 Critical Facts Embedded in Dense Prose (3800 tokens)",
    query=scenario_c_query,
    context=scenario_c_context,
    token_budget=600,
)

print("=" * 80)
print(" NEW SCENARIO RUN COMPLETE")
print("=" * 80)
