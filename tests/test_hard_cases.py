import unittest
import sys
import os

from semantic_relevance_engine.critical_flags import detect_critical_flags
from semantic_relevance_engine.optimizer import (
    Chunk, apply_pinning, compute_final_score,
    compress_chunk, enforce_budget, optimize_chunks, approx_token_count
)

class TestHardCases(unittest.TestCase):

    def test_cat1_false_negatives(self):
        cases = [
            ("Do NOT use MongoDB for this project.", "negation"),
            ("We must never deploy on Fridays.", "negation"),
            ("This should not be cached under any circumstances.", "negation"),
            ("Timeout=30s for all requests.", "number"),
            ("Rate limit is 100 requests per minute.", "number"),
            ("Set retries to 3.", "number"),
            ("The service must remain stateless at all times.", "constraint"),
            ("Only admins are permitted to access this endpoint.", "constraint"),
            ("The endpoint returns a 401 error on invalid tokens.", "error"),
            ("We saw HTTP 500 status codes spike after deploy.", "error"),
            ("Client threw an exception during checkout.", "error"),
            ("We decided to migrate off Redis last sprint.", "decision"),
            ("The team switched to PostgreSQL in March.", "decision")
        ]
        for text, expected_flag in cases:
            flags = detect_critical_flags(text)
            self.assertIn(expected_flag, flags, f"Expected {expected_flag} in '{text}', got {flags}")

    def test_cat2_false_positives(self):
        """Canonical-set false-positive discipline: these inputs must produce
        ZERO flags. If any new regex addition causes a hit here, it doesn't
        belong in the canonical set."""
        cases = [
            "See step 4 for details on deployment.",
            "Refer to chapter 3 of the handbook.",
            "There are 12 items in the backlog.",
            "The meeting is in room 5.",
            "Ideally the API would be stateless, but it's not a hard requirement.",
            "Check out issue #404 on GitHub for context.",
            "Our office is at 500 Main Street.",
            "Port 8080 is used for local dev.",
            "He said the food was okay, nothing special.",
            # Additional canonical-set false-positive guards:
            # bare numbers that aren't measurements or assignments
            "The README has 7 sections.",
            "Version 2 of the API was released.",
            # casual negation-adjacent phrasing
            "I noticed the config file was updated.",
            "The team discussed options briefly.",
            # Negation-widening false-positive guards: these contain negation
            # words (neither, doesn't, without, aren't, nor) in benign,
            # non-critical contexts. They must NOT trigger negation flags.
            "Neither option matters much for this demo.",
            "The bug report doesn't mention any specifics.",
            "This works fine without any special configuration.",
            "The two approaches aren't that different in practice.",
            "Nor did anyone raise concerns about it.",
        ]
        for text in cases:
            flags = detect_critical_flags(text)
            self.assertEqual(flags, [], f"Expected NO flags in '{text}', got {flags}")

    def test_cat3_known_gaps(self):
        cases = [
            ("We can't go with Mongo.", "negation"),
            ("MongoDB is off the table.", "negation"),
            ("The timeout, thirty seconds, was chosen after testing.", "number"),
            ("It's non-negotiable that we support offline mode.", "constraint")
        ]
        results = []
        for text, flag in cases:
            flags = detect_critical_flags(text)
            status = "gap closed" if flag in flags else "still a gap"
            results.append((text, status, flags))
        # Print for reporting
        print("\n--- Cat 3 Results ---")
        for r in results:
            print(f"'{r[0]}' -> {r[1]} (flags: {r[2]})")

    def test_cat4_compression_correctness(self):
        # 1. Pinned chunk is NEVER sent to llm_call_fn
        c1 = Chunk(id="c1", text="Do NOT use MongoDB for this project.", token_count=10, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        apply_pinning([c1])
        self.assertTrue(c1.pinned, "apply_pinning should set pinned to True for negation chunks")
        called = []
        def mock_llm_1(prompt):
            called.append(True)
            return "Compressed"
        res1 = compress_chunk(c1, "query", llm_call_fn=mock_llm_1)
        self.assertEqual(len(called), 0, "LLM was called for a pinned negation chunk")
        self.assertEqual(res1.text, "Do NOT use MongoDB for this project.")

        # 2. Pinned chunk with number is NEVER sent
        c2 = Chunk(id="c2", text="Timeout is set to 30 seconds.", token_count=10, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        apply_pinning([c2])
        self.assertTrue(c2.pinned, "apply_pinning should set pinned to True for number chunks")
        res2 = compress_chunk(c2, "query", llm_call_fn=mock_llm_1)
        self.assertEqual(len(called), 0, "LLM was called for a pinned number chunk")

        # 3. LLM adds a new critical flag (loss-only revert policy)
        c3 = Chunk(id="c3", text="The user likes dark mode in their editor.", token_count=10, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        apply_pinning([c3])
        def mock_llm_3(prompt):
            return "The user likes dark mode in their editor, which requires 30 seconds to load."
        res3 = compress_chunk(c3, "query", llm_call_fn=mock_llm_3)
        self.assertFalse(res3.compressed)
        self.assertIn("length_expanded_revert", getattr(res3, "trace_events", []))

        # 4. Correctly compresses non-critical chunk
        c4 = Chunk(id="c4", text="This is a very long and verbose sentence with lots of extra words.", token_count=20, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        apply_pinning([c4])
        def mock_llm_4(prompt):
            return "Short sentence."
        res4 = compress_chunk(c4, "query", llm_call_fn=mock_llm_4)
        self.assertTrue(res4.compressed)
        self.assertTrue(res4.token_count < 20)

        # 5. LLM raises exception
        c5 = Chunk(id="c5", text="Unpinned chunk.", token_count=5, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        apply_pinning([c5])
        def mock_llm_5(prompt):
            raise TimeoutError("LLM timed out")
        
        try:
            optimize_chunks("query", [c5], token_budget=100, llm_call_fn=mock_llm_5)
            c5_caught = True
        except Exception as e:
            c5_caught = False
            print(f"\nCat 4.5 Result: Exception leaked: {e}")

        # 6. LLM returns empty string
        c6 = Chunk(id="c6", text="Unpinned chunk to empty.", token_count=5, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        apply_pinning([c6])
        def mock_llm_6(prompt):
            return ""
        res6 = compress_chunk(c6, "query", llm_call_fn=mock_llm_6)
        self.assertFalse(res6.compressed)
        self.assertEqual(res6.text, "Unpinned chunk to empty.")
        self.assertIn("empty_compression_result", getattr(res6, "trace_events", []))

    def test_cat5_dedup_interaction(self):
        # We just confirm if they slip through, they are independently detected.
        c1 = Chunk(id="c1", text="We use Postgres.", token_count=3, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        c2 = Chunk(id="c2", text="We're migrating off Postgres next quarter.", token_count=5, source="document", tag="CONVERSATION", position=1, relevance_score=0.5)
        apply_pinning([c1, c2])
        self.assertNotIn("decision", c1.critical_flags)
        self.assertIn("decision", c2.critical_flags)

        c3 = Chunk(id="c3", text="The API must remain stateless.", token_count=5, source="document", tag="CONVERSATION", position=2, relevance_score=0.5)
        c4 = Chunk(id="c4", text="The API used to be stateless but now uses sessions.", token_count=8, source="document", tag="CONVERSATION", position=3, relevance_score=0.5)
        apply_pinning([c3, c4])
        self.assertIn("constraint", c3.critical_flags)
        print(f"\nCat 5.2 Result for c4: flags = {c4.critical_flags}")

        c5 = Chunk(id="c5", text="Timeout is 30 seconds.", token_count=4, source="document", tag="CONVERSATION", position=4, relevance_score=0.5)
        c6 = Chunk(id="c6", text="Timeout was 30 seconds before the update.", token_count=6, source="document", tag="CONVERSATION", position=5, relevance_score=0.5)
        apply_pinning([c5, c6])
        self.assertIn("number", c5.critical_flags)
        self.assertIn("number", c6.critical_flags)

    def test_cat6_budget_edge_cases(self):
        # 1. Pinned exceeds budget
        c1 = Chunk(id="c1", text="SYSTEM", token_count=20, source="system", tag="SYSTEM", position=0, relevance_score=0.5, pinned=True)
        c2 = Chunk(id="c2", text="Constraint", token_count=20, source="document", tag="PERSISTENT_CONSTRAINT", position=1, relevance_score=0.5, pinned=True)
        kept, trace = enforce_budget([c1, c2], 10)
        self.assertTrue(trace["budget_exceeded_by_pinned_content"])
        self.assertEqual(len(kept), 2)

        # 2. Budget exactly 0, only non-pinned
        c3 = Chunk(id="c3", text="Unpinned", token_count=5, source="document", tag="CONVERSATION", position=2, relevance_score=0.5, importance_score=0.5)
        c3.final_score = compute_final_score(c3)
        kept, trace = enforce_budget([c3], 0)
        self.assertEqual(len(kept), 0)
        self.assertEqual(trace["chunks_removed_by_budget"], 1)

        # 3. Stable tie-breaking
        c4 = Chunk(id="c4", text="A", token_count=5, source="document", tag="CONVERSATION", position=1, relevance_score=0.5, importance_score=0.5, final_score=0.5)
        c5 = Chunk(id="c5", text="B", token_count=5, source="document", tag="CONVERSATION", position=2, relevance_score=0.5, importance_score=0.5, final_score=0.5)
        c6 = Chunk(id="c6", text="C", token_count=5, source="document", tag="CONVERSATION", position=3, relevance_score=0.5, importance_score=0.5, final_score=0.5)
        kept1, _ = enforce_budget([c4, c5, c6], 10) # can fit 2
        kept2, _ = enforce_budget([c4, c5, c6], 10)
        self.assertEqual([c.id for c in kept1], [c.id for c in kept2])
        print(f"\nCat 6.3 Tiebreaker Result: { [c.id for c in kept1] }")

    def test_cat7_coherence_assembly(self):
        chunks = [
            Chunk(id="sys", text="SYS", token_count=1, source="system", tag="SYSTEM", position=0, relevance_score=0.5),
            Chunk(id="conv", text="CONV", token_count=1, source="document", tag="CONVERSATION", position=5, relevance_score=0.5),
            Chunk(id="const", text="CONST", token_count=1, source="document", tag="PERSISTENT_CONSTRAINT", position=1, relevance_score=0.5)
        ]
        kept, trace = optimize_chunks("q", chunks, 100)
        order = [c.id for c in kept]
        self.assertEqual(order, ["sys", "conv", "const"])

    def test_cat8_full_pipeline(self):
        chunks = [
            Chunk(id="sys", text="SYSTEM PROMPT", token_count=10, source="system", tag="SYSTEM", position=0, relevance_score=1.0),
            Chunk(id="neg", text="Do NOT use MongoDB.", token_count=10, source="document", tag="CONVERSATION", position=1, relevance_score=0.5),
            Chunk(id="filler", text="This is low relevance filler.", token_count=10, source="document", tag="CONVERSATION", position=2, relevance_score=0.1),
            Chunk(id="verbose", text="This is a very long and verbose chunk that should be compressed by the LLM.", token_count=20, source="document", tag="CONVERSATION", position=3, relevance_score=0.9)
        ]
        def mock_llm(p): 
            if "verbose" in p: return "Compressed verbose chunk." # 4 tokens
            if "filler" in p: return "This is low relevance filler."
            return p

        kept, trace = optimize_chunks("q", chunks, 30, llm_call_fn=mock_llm)
        
        kept_ids = [c.id for c in kept]
        self.assertIn("sys", kept_ids)
        self.assertIn("neg", kept_ids)
        self.assertIn("verbose", kept_ids)
        self.assertNotIn("filler", kept_ids)

        self.assertEqual(trace["chunks_compressed"], 1)
        self.assertEqual(trace["chunks_removed_by_budget"], 1)
        self.assertEqual(trace["chunks_pinned_critical"], 2)
        # Verify critical-info-count trace metrics (#7)
        self.assertIn("critical_before", trace)
        self.assertIn("critical_after", trace)
        self.assertGreater(trace["critical_before"], 0,
            "critical_before should be > 0 — chunks with flags exist")
        self.assertEqual(trace["critical_before"], trace["critical_after"],
            "critical flags should be preserved through compression")

if __name__ == "__main__":
    unittest.main()
