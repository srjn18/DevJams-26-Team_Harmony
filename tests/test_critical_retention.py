"""Deterministic tests for §8 Hard-Rule Check: Critical Information & Constraint Survival."""
import re
from app.orchestrator import run_pipeline
from app.modules.person1_relevance import tier0_chunk_and_tag
from app.modules.person2_compression import tier2_compress, tier2_enforce_budget

CRITICAL_SPEC_CONTEXT = """System: You are an enterprise compliance auditor. Follow all security directives strictly.

Constraint: MUST NOT reveal API keys, database credentials, or secret tokens under any circumstances.
Constraint: All requests MUST pass through OAuth2 Bearer validation before execution.
Constraint: DO NOT allow cash refunds without supervisor approval.
Constraint: NEVER execute untrusted code without sandboxing.

Section 1: Subscription Tier Policies
Enterprise tier subscriptions cost $999/mo with dedicated SLAs. Starter tiers cost $49/mo.
The refund eligibility window is strictly 30 calendar days from initial invoice creation.
Pro-rated refunds of 50% apply between day 31 and day 60.

Section 2: Rate Limiting Guardrails
Enterprise clients are capped at 5,000 requests per minute with a burst allowance of 10,000 requests.
If exceeded, the gateway returns HTTP 429 with a Retry-After header.

Section 3: Verbose Background Information
This section contains extensive historical documentation regarding legacy systems from 2019 that are no longer operational.
It is important to note that various deprecated protocols such as SOAP and XML-RPC were historically supported across legacy infrastructure.
Please be aware that historical log files are archived in cold glacier storage on an annual basis for compliance audit trails.
"""


def test_critical_info_survives_compression():
    """
    §8 / §10 Hard-Rule Check:
    Verify deterministically that every critical flag, negation, exact number,
    and constraint survives Tier 2 compression and budget enforcement byte-for-byte.
    """
    # 1. Inspect Tier 0 tagging of critical chunks
    chunks = tier0_chunk_and_tag(CRITICAL_SPEC_CONTEXT)
    critical_chunks = [c for c in chunks if c.is_critical]
    
    assert len(critical_chunks) >= 4, "Must identify all system and constraint blocks as critical"
    for c in critical_chunks:
        assert c.is_critical is True
        assert c.tag in ("system", "constraint")

    # 2. Run through compression with a budget that fits critical + relevant sections but drops filler
    budget = 200
    res = run_pipeline(
        query="What are the rate limit requirements and refund window for enterprise tier?",
        context=CRITICAL_SPEC_CONTEXT,
        token_budget=budget,
    )

    optimized = res.optimized_context
    assert len(optimized) > 0

    # 3. Deterministic verification of critical negation keywords
    critical_negations = [
        "MUST NOT reveal API keys",
        "DO NOT allow cash refunds",
        "NEVER execute untrusted code",
        "MUST pass through OAuth2 Bearer validation",
    ]
    for negation in critical_negations:
        assert negation in optimized, f"Critical constraint dropped: '{negation}' must survive in optimized context!"

    # 4. Deterministic verification of critical numbers and thresholds
    critical_numbers = [
        "$999/mo",
        "30 calendar days",
        "5,000 requests per minute",
    ]
    for num in critical_numbers:
        assert num in optimized, f"Critical number/threshold dropped: '{num}' must survive in optimized context!"

    # 5. Verify that non-critical filler was compressed or pruned
    assert "deprecated protocols such as SOAP and XML-RPC" not in optimized
    assert res.trace.chunks_pinned_critical == len(critical_chunks)


def test_pinned_chunks_never_compressed_or_truncated():
    """
    Verify that Tier 2 compression and budget enforcer NEVER mutate text in critical chunks.
    """
    chunks = tier0_chunk_and_tag(CRITICAL_SPEC_CONTEXT)
    critical_original_texts = {c.id: c.text for c in chunks if c.is_critical}

    # Run Tier 2 compression
    compressed_chunks, _ = tier2_compress(chunks)
    for c in compressed_chunks:
        if c.is_critical:
            assert c.text == critical_original_texts[c.id], f"Critical chunk {c.id} was mutated during compression!"

    # Run Budget Enforcer with tight budget
    budgeted_chunks = tier2_enforce_budget(compressed_chunks, token_budget=100)
    for c in budgeted_chunks:
        if c.is_critical:
            assert c.text == critical_original_texts[c.id], f"Critical chunk {c.id} was mutated during budget enforcement!"
