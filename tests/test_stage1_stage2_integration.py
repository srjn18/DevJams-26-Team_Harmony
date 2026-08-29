"""
Cross-stage integration tests for Tier 1 (Person 1) + Tier 2 (Person 2)
after schema unification onto a single Pydantic Chunk model.

These do NOT re-test what each module's own unit tests already cover
(regex detection accuracy, embedding cosine math, etc). They specifically
target integration risks that only show up when the two stages run
together: field survival across the schema migration, dedup-then-pin
ordering, importance_score actually being populated, tokenizer
consistency, and Pydantic mutation behavior.

Adjust imports to match your actual package structure.
"""

import pytest
from semantic_relevance_engine import Chunk, optimize_chunks, rank_chunks
from semantic_relevance_engine.optimizer import approx_token_count


# ---------------------------------------------------------------------------
# 1. Schema survival: confirm no fields were silently dropped in migration
# ---------------------------------------------------------------------------

def test_all_expected_fields_present_on_unified_model():
    """The Pydantic Chunk must still carry every field both tiers depend on.
    A missing field here would surface as an AttributeError deep in the
    pipeline rather than at schema definition time -- catch it here instead."""
    expected_fields = {
        "id", "text", "token_count", "source", "tag", "timestamp", "position",
        "pinned", "critical_flags", "is_duplicate_of", "relevance_score",
        "importance_score", "final_score", "compressed", "embedding",
    }
    actual_fields = set(Chunk.model_fields.keys())  # pydantic v2; use __fields__ for v1
    missing = expected_fields - actual_fields
    assert not missing, f"Fields dropped during schema migration: {missing}"


def test_pydantic_chunk_allows_in_place_mutation():
    """Tier 2 mutates chunks in place (c.pinned = True, c.final_score = ...).
    Confirm the unified model doesn't silently block or fail to validate
    this the way a frozen or strict model would."""
    c = Chunk(id="c1", text="test", token_count=5, source="conversation", tag="CONVERSATION",
              position=0)
    c.pinned = True
    c.final_score = 0.75
    c.text = "modified text"
    assert c.pinned is True
    assert c.final_score == 0.75
    assert c.text == "modified text"


# ---------------------------------------------------------------------------
# 2. Deduplication must actually remove chunks before Tier 2, not just tag them
# ---------------------------------------------------------------------------

def test_duplicate_chunks_excluded_from_final_output():
    """A chunk marked is_duplicate_of by Tier 1 must never appear in the
    final assembled context, even if it would otherwise score highly on
    relevance or get pinned."""
    chunks = [
        Chunk(id="keep", text="We use Postgres as our primary database.",
              token_count=8, source="conversation", tag="CONVERSATION", position=0,
              relevance_score=0.9),
        Chunk(id="dup", text="The application uses Postgres.",
              token_count=6, source="conversation", tag="CONVERSATION", position=1,
              relevance_score=0.85, is_duplicate_of="keep"),
    ]
    kept, trace = optimize_chunks(query="what database do we use?",
                                   chunks=chunks, token_budget=100)
    kept_ids = {c.id for c in kept}
    assert "dup" not in kept_ids, \
        "FAIL: duplicate chunk reached final output -- dedup filter not applied before Tier 2"
    assert "keep" in kept_ids


def test_fact_conflict_pair_never_marked_duplicate_and_both_survive():
    """Regression test for the specific case called out in the design doc.
    These must never be merged even though they're topically near-identical,
    and BOTH must independently reach Tier 2's pinning logic since the second
    is a decision statement."""
    chunks = [
        Chunk(id="c1", text="We use Postgres.", token_count=5,
              source="conversation", tag="CONVERSATION", position=0, relevance_score=0.7),
        Chunk(id="c2", text="We're migrating off Postgres next quarter.",
              token_count=8, source="conversation", tag="CONVERSATION", position=1,
              relevance_score=0.7),
    ]
    kept, trace = optimize_chunks(query="what's our database situation?",
                                   chunks=chunks, token_budget=100)
    kept_ids = {c.id for c in kept}
    assert "c1" in kept_ids and "c2" in kept_ids, \
        "FAIL: contradictory facts were merged or one was dropped"
    # c2 should be pinned as a 'decision' -- confirm it made it through
    c2 = next(c for c in kept if c.id == "c2")
    assert "decision" in c2.critical_flags


# ---------------------------------------------------------------------------
# 3. importance_score must actually be populated, not silently stay 0.0
# ---------------------------------------------------------------------------

def test_importance_score_is_actually_computed():
    """If nothing sets importance_score, final_score collapses to just
    0.7 * relevance_score and the blended-score design is dead code. This
    test fails loudly if that's the case."""
    chunks = [
        Chunk(id="c1", text="Some fairly ordinary conversational text.",
              token_count=10, source="conversation", tag="CONVERSATION", position=0,
              relevance_score=0.5),
    ]
    kept, trace = optimize_chunks(query="test query", chunks=chunks,
                                   token_budget=100)
    c = kept[0]
    assert c.importance_score != 0.0, \
        "FAIL: importance_score was never populated -- final_score is silently relevance-only"


def test_final_score_reflects_both_relevance_and_importance():
    """Construct two chunks with identical relevance_score but expect
    different importance (e.g. one contains a number, one doesn't) and
    confirm final_score actually differs between them."""
    chunks = [
        Chunk(id="plain", text="The user likes dark mode in their editor.",
              token_count=8, source="conversation", tag="CONVERSATION", position=0,
              relevance_score=0.5),
        Chunk(id="numeric", text="Response time averages 240ms per request.",
              token_count=8, source="conversation", tag="CONVERSATION", position=1,
              relevance_score=0.5),
    ]
    kept, trace = optimize_chunks(query="test query", chunks=chunks,
                                   token_budget=100)
    plain = next(c for c in kept if c.id == "plain")
    numeric = next(c for c in kept if c.id == "numeric")
    # numeric chunk should be pinned (has a number flag) so final_score may
    # not even apply the same way -- but if BOTH ended up non-pinned for some
    # reason, their final_scores should differ given different importance.
    if not numeric.pinned and not plain.pinned:
        assert plain.final_score != numeric.final_score, \
            "FAIL: identical final_score despite different importance signals"


# ---------------------------------------------------------------------------
# 4. Tokenizer consistency across Tier 1 chunking and Tier 2 recompression
# ---------------------------------------------------------------------------

def test_token_count_consistent_before_and_after_compression():
    """The token_count assigned by Tier 1's chunker and the token_count
    recomputed by Tier 2 after compression must use the same counting
    method, or budget math is comparing incompatible numbers."""
    text = "This is a moderately long piece of conversational text for testing."
    chunk = Chunk(id="c1", text=text, token_count=approx_token_count(text),
                  source="conversation", tag="CONVERSATION", position=0, relevance_score=0.3)

    def mock_llm(prompt):
        return "Shorter version of the text."

    kept, trace = optimize_chunks(query="q", chunks=[chunk], token_budget=100,
                                   llm_call_fn=mock_llm)
    c = kept[0]
    if c.compressed:
        expected = approx_token_count(c.text)
        assert c.token_count == expected, \
            f"FAIL: post-compression token_count ({c.token_count}) doesn't match " \
            f"shared tokenizer output ({expected}) -- inconsistent counting method"


# ---------------------------------------------------------------------------
# 5. End-to-end: raw context string -> Tier 1 -> Tier 2 -> assembled output
# ---------------------------------------------------------------------------

def test_full_pipeline_preserves_critical_info_end_to_end():
    """The real test: does a negation and a number survive the ENTIRE
    pipeline, not just Tier 2 in isolation? This exercises Tier 1's real
    chunking/embedding/relevance code, not hand-built Chunk objects."""
    raw_context = (
        "[SYSTEM] You are a helpful coding assistant.\n"
        "[USER] We changed our auth from sessions to JWT.\n"
        "[ASSISTANT] Got it, noting the change.\n"
        "[USER] Do NOT use MongoDB for this project.\n"
        "[USER] Timeout is set to 30 seconds for all requests.\n"
        "[USER] I like using dark mode in my editor.\n"
        "[TOOL_OUTPUT] Endpoint returns HTTP 401 after the auth change.\n"
    )
    query = "Why am I getting 401 errors?"

    ranked_chunks = rank_chunks(query=query, context=raw_context)
    kept, trace = optimize_chunks(query=query, chunks=ranked_chunks,
                                   token_budget=60)

    assembled_texts = " ".join(c.text for c in kept)
    assert "MongoDB" in assembled_texts and (
        "not" in assembled_texts.lower() or "NOT" in assembled_texts
    ), "FAIL: negation about MongoDB did not survive the full pipeline"
    assert "30" in assembled_texts, \
        "FAIL: the timeout number did not survive the full pipeline"
    assert "401" in assembled_texts, \
        "FAIL: the error code did not survive the full pipeline"


def test_full_pipeline_coherence_ordering_with_real_tier1_output():
    """Confirm fixed-slot coherence assembly still holds when chunk objects
    come from real Tier 1 output (with real position/tag values) rather
    than hand-constructed test chunks."""
    raw_context = (
        "[SYSTEM] You are a helpful assistant.\n"
        "[USER] The API must remain stateless.\n"
        "[USER] We talked about deployment strategies yesterday.\n"
        "[USER] Let's also discuss caching layers.\n"
    )
    query = "What are our architecture constraints?"

    ranked_chunks = rank_chunks(query=query, context=raw_context)
    kept, trace = optimize_chunks(query=query, chunks=ranked_chunks,
                                   token_budget=200)

    tags_in_order = [c.tag for c in kept]
    assert tags_in_order[0] == "SYSTEM", \
        f"FAIL: expected SYSTEM first, got order: {tags_in_order}"
    assert tags_in_order[-1] in ("PERSISTENT_CONSTRAINT", "CONVERSATION"), \
        "FAIL: unexpected tag ordering at the end of assembled context"
    # if a PERSISTENT_CONSTRAINT chunk exists, it must come after all
    # plain CONVERSATION chunks, regardless of original position
    if "PERSISTENT_CONSTRAINT" in tags_in_order:
        constraint_idx = tags_in_order.index("PERSISTENT_CONSTRAINT")
        conversation_idxs = [i for i, t in enumerate(tags_in_order) if t == "CONVERSATION"]
        if conversation_idxs:
            assert constraint_idx > max(conversation_idxs), \
                "FAIL: PERSISTENT_CONSTRAINT chunk not placed after conversation chunks"


# ---------------------------------------------------------------------------
# 6. trace_events field: confirm it aggregates correctly across the pipeline
# ---------------------------------------------------------------------------

def test_trace_events_populated_for_reverted_chunk():
    """If trace_events is meant to carry per-chunk events like
    empty_compression_result or flag_added, confirm it actually gets
    populated end-to-end and isn't left as an empty list by default."""
    chunk = Chunk(id="c1", text="Some non-critical filler text here.",
                  token_count=8, source="conversation", tag="CONVERSATION", position=0,
                  relevance_score=0.3)

    def mock_llm_empty(prompt):
        return ""

    kept, trace = optimize_chunks(query="q", chunks=[chunk], token_budget=100,
                                   llm_call_fn=mock_llm_empty)
    c = kept[0]
    assert c.text == "Some non-critical filler text here.", \
        "FAIL: empty compression result should have reverted to original text"
    assert len(c.trace_events) > 0, \
        "FAIL: trace_events is empty -- empty_compression_result event not logged on the chunk"
