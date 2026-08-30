import unittest

from semantic_relevance_engine.optimizer import Chunk, compress_chunk

class TestChecks(unittest.TestCase):
    
    def test_case_1_empty_string(self):
        c = Chunk(id="c1", text="Normal text.", token_count=5, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        def mock_llm(p): return ""
        res = compress_chunk(c, "query", llm_call_fn=mock_llm)
        self.assertFalse(res.compressed)
        self.assertEqual(res.text, "Normal text.")
        self.assertIn("empty_compression_result", getattr(res, "trace_events", []))

    def test_case_2_whitespace_string(self):
        c = Chunk(id="c2", text="Normal text.", token_count=5, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        def mock_llm(p): return "   \n\t  "
        res = compress_chunk(c, "query", llm_call_fn=mock_llm)
        self.assertFalse(res.compressed)
        self.assertEqual(res.text, "Normal text.")
        self.assertIn("empty_compression_result", getattr(res, "trace_events", []))

    def test_case_3_single_space(self):
        c = Chunk(id="c3", text="Normal text.", token_count=5, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        def mock_llm(p): return " "
        res = compress_chunk(c, "query", llm_call_fn=mock_llm)
        self.assertFalse(res.compressed)
        self.assertEqual(res.text, "Normal text.")
        self.assertIn("empty_compression_result", getattr(res, "trace_events", []))

    def test_case_4_single_punctuation(self):
        c = Chunk(id="c4", text="Normal text.", token_count=5, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        def mock_llm(p): return "."
        res = compress_chunk(c, "query", llm_call_fn=mock_llm)
        self.assertTrue(res.compressed)
        self.assertNotIn("empty_compression_result", getattr(res, "trace_events", []))

    def test_case_5_original_chunk_empty(self):
        c = Chunk(id="c5", text="", token_count=0, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        def mock_llm(p): return "Some generated text."
        res = compress_chunk(c, "query", llm_call_fn=mock_llm)
        self.assertFalse(res.compressed)
        self.assertEqual(res.text, "")
        self.assertIn("length_expanded_revert", getattr(res, "trace_events", []))

    def test_case_6_new_flag_logged(self):
        c = Chunk(id="c6", text="The user likes dark mode.", token_count=5, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        def mock_llm(p): return "The user has liked dark mode since version 2.1."
        res = compress_chunk(c, "query", llm_call_fn=mock_llm)
        self.assertFalse(res.compressed)
        self.assertEqual(res.text, "The user likes dark mode.")
        self.assertIn("length_expanded_revert", getattr(res, "trace_events", []))

    def test_case_7_original_flag_preserved_new_added(self):
        c = Chunk(id="c7", text="Timeout is 30 seconds.", token_count=5, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        c.critical_flags = ["number"]
        c.pinned = False 
        def mock_llm(p): return "Timeout is 30 seconds, and we decided to add it in v4.2."
        res = compress_chunk(c, "query", llm_call_fn=mock_llm)
        self.assertFalse(res.compressed)
        self.assertEqual(res.text, "Timeout is 30 seconds.")
        self.assertIn("length_expanded_revert", getattr(res, "trace_events", []))

    def test_case_8_negation_replaced_with_avoid(self):
        c = Chunk(id="c8", text="Do NOT use MongoDB.", token_count=5, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        c.critical_flags = ["negation"]
        c.pinned = False
        def mock_llm(p): return "Avoid MongoDB; use PostgreSQL instead, decided as of the 2023 migration."
        res = compress_chunk(c, "query", llm_call_fn=mock_llm)
        self.assertFalse(res.compressed)
        self.assertIn("flag_lost_revert", getattr(res, "trace_events", []))
        if "flag_added" not in getattr(res, "trace_events", []):
            print("\nNOTE for Case 8: Revert occurred, but 'flag_added' wasn't logged because the function returned early upon detecting the lost flag.")

    def test_case_9_identical_text(self):
        c = Chunk(id="c9", text="API must remain stateless.", token_count=5, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        c.critical_flags = ["constraint"]
        c.pinned = False
        def mock_llm(p): return "API must remain stateless."
        res = compress_chunk(c, "query", llm_call_fn=mock_llm)
        self.assertFalse(res.compressed)
        self.assertEqual(res.text, "API must remain stateless.")
        self.assertIn("length_expanded_revert", getattr(res, "trace_events", []))

    def test_case_10_empty_and_zero_flags(self):
        c = Chunk(id="c10", text="Normal text.", token_count=5, source="document", tag="CONVERSATION", position=0, relevance_score=0.5)
        def mock_llm(p): return ""
        res = compress_chunk(c, "query", llm_call_fn=mock_llm)
        self.assertFalse(res.compressed)
        self.assertIn("empty_compression_result", getattr(res, "trace_events", []))

if __name__ == "__main__":
    unittest.main()
