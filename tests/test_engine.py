"""
Unit and integration test suite for Semantic Relevance Engine.
"""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from semantic_relevance_engine import rank_chunks, Chunk, chunk_context
from semantic_relevance_engine.engine import has_fact_conflict, cosine_similarity


class TestSemanticRelevanceEngine(unittest.TestCase):

    def test_schema_conformity(self):
        """Verify that every chunk strictly adheres to the Pydantic schema and contract."""
        query = "Explain caching layers."
        context = "[SYSTEM] System instructions.\n[USER] How does caching work?\n[DOC] Redis caching documentation."
        chunks = rank_chunks(query, context)

        self.assertGreater(len(chunks), 0)
        for c in chunks:
            self.assertIsInstance(c, Chunk)
            self.assertTrue(c.id.startswith("c_"))
            self.assertIsInstance(c.text, str)
            self.assertIsInstance(c.token_count, int)
            self.assertIn(c.source, ["conversation", "document", "tool_output", "system"])
            self.assertIn(c.tag, ["SYSTEM", "PERSISTENT_CONSTRAINT", "CONVERSATION", "DOC", "TOOL_OUTPUT"])
            self.assertIsInstance(c.position, int)
            self.assertIsInstance(c.pinned, bool)
            self.assertIsInstance(c.critical_flags, list)
            self.assertIsInstance(c.relevance_score, float)
            self.assertTrue(0.0 <= c.relevance_score <= 1.0)
            self.assertTrue(c.is_duplicate_of is None or isinstance(c.is_duplicate_of, str))

    def test_system_pinning(self):
        """Verify that SYSTEM chunks are always pinned=True and non-system chunks are pinned=False."""
        context = "[SYSTEM] Strict system instructions.\n[USER] Hello!\n[DOC] API Reference."
        chunks = rank_chunks("test query", context)

        system_chunks = [c for c in chunks if c.tag == "SYSTEM"]
        non_system_chunks = [c for c in chunks if c.tag != "SYSTEM" and c.tag != "PERSISTENT_CONSTRAINT"]

        self.assertEqual(len(system_chunks), 1)
        self.assertTrue(system_chunks[0].pinned)
        self.assertEqual(system_chunks[0].source, "system")

        for c in non_system_chunks:
            self.assertFalse(c.pinned)

    def test_sorting_descending(self):
        """Verify that output chunks are sorted strictly in descending order of relevance_score."""
        query = "vector database indexing"
        context = """[DOC]
Vector database indexing organizes embeddings into trees or graphs for fast nearest-neighbor search.

[DOC]
A recipe for chocolate chip cookies using baking soda and flour.

[DOC]
Cosine similarity measures the angle between two vectors in vector space.
"""
        chunks = rank_chunks(query, context)
        scores = [c.relevance_score for c in chunks]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_zero_drop_guarantee(self):
        """Verify that NO chunks are dropped — total input parsed chunks == total output chunks."""
        context = """[SYSTEM] System prompt
[USER] User question
[DOC] Document 1
[DOC] Document 2 (duplicate of 1)
[TOOL_OUTPUT] {"status": 200}
"""
        parsed_chunks = chunk_context(context)
        ranked_chunks = rank_chunks("irrelevant query that might match nothing", context)

        self.assertEqual(len(parsed_chunks), len(ranked_chunks))
        # Ensure all original IDs are present in the output
        parsed_ids = {c.id for c in parsed_chunks}
        ranked_ids = {c.id for c in ranked_chunks}
        self.assertEqual(parsed_ids, ranked_ids)

    def test_deduplication_and_density_winner(self):
        """Verify that near-identical chunks are deduplicated and the more informative one is kept as canonical."""
        context = """[DOC]
Vector search indexing uses cosine similarity across dense embeddings to retrieve relevant documentation sections rapidly.

[DOC]
Vector search indexing uses cosine similarity across dense embeddings to retrieve relevant documentation sections.
"""
        chunks = rank_chunks("vector search", context, dedup_threshold=0.80)
        self.assertEqual(len(chunks), 2)

        dup_chunks = [c for c in chunks if c.is_duplicate_of is not None]
        canonical_chunks = [c for c in chunks if c.is_duplicate_of is None]

        self.assertEqual(len(dup_chunks), 1)
        self.assertEqual(len(canonical_chunks), 1)
        # Duplicate should point to the canonical ID
        self.assertEqual(dup_chunks[0].is_duplicate_of, canonical_chunks[0].id)
        # The longer chunk should be the canonical winner
        self.assertGreater(len(canonical_chunks[0].text), len(dup_chunks[0].text))

    def test_fact_contrast_guard_postgres(self):
        """
        Verify that contrasting statements (e.g. 'using Postgres' vs 'migrating off Postgres')
        are NEVER marked as duplicates even with high lexical and semantic overlap.
        """
        context = """[CONVERSATION]
We are currently using Postgres for storing our relational data and customer profiles.

[CONVERSATION]
We are migrating off Postgres to DynamoDB next quarter for better scale and performance.
"""
        # First verify the fact conflict helper directly
        t1 = "We are currently using Postgres for storing our relational data and customer profiles."
        t2 = "We are migrating off Postgres to DynamoDB next quarter for better scale and performance."
        self.assertTrue(has_fact_conflict(t1, t2))

        # Test end-to-end rank_chunks
        chunks = rank_chunks("Postgres database setup", context, dedup_threshold=0.50)
        self.assertEqual(len(chunks), 2)
        # Neither chunk should be marked as a duplicate of the other
        for c in chunks:
            self.assertIsNone(c.is_duplicate_of, f"Chunk {c.id} was falsely marked as duplicate of {c.is_duplicate_of}")

    def test_multi_format_parsing(self):
        """Test parsing of various formats: colon prefix, markdown headers, and plain paragraphs."""
        # Colon prefix
        colon_context = "User: Hello there\nAssistant: Hi, how can I help you today?"
        chunks = chunk_context(colon_context)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].source, "conversation")
        self.assertEqual(chunks[1].source, "conversation")

        # Markdown headers
        md_context = "## Architecture\nThis is the architecture section.\n\n## Deployment\nThis is the deployment section."
        chunks_md = chunk_context(md_context)
        self.assertEqual(len(chunks_md), 2)
        self.assertIn("Architecture", chunks_md[0].text)
        self.assertIn("Deployment", chunks_md[1].text)

    def test_provisional_critical_flags(self):
        """Test canonical critical-flag detection at chunking time (numbers, errors, constraints, negations)."""
        context = """[DOC]
The timeout limit is strictly 500ms and must not exceed $50 per transaction.
[TOOL_OUTPUT]
Error: database connection timeout exception traceback.
"""
        chunks = chunk_context(context)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(any(f in chunks[0].critical_flags for f in ["number", "constraint", "negation"]))
        self.assertIn("error", chunks[1].critical_flags)


if __name__ == "__main__":
    unittest.main()
