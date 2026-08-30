import unittest
from semantic_relevance_engine import rank_chunks, optimize_chunks

class TestIntegrationPipeline(unittest.TestCase):

    def test_full_pipeline_integration(self):
        # 1. Define query and verbose context with duplicates, system instructions, negations, numbers, and low-relevance filler.
        query = "Why is our service throwing HTTP 500 errors?"
        context = """[SYSTEM]
You are a database and scaling assistant. Follow constraints.

[DOC]
Timeout is set to 30 seconds for all queries.

[CONVERSATION]
We are currently using Postgres for our customer database.

[CONVERSATION]
We decided to migrate off Postgres to DynamoDB next quarter.

[DOC]
Unrelated backup instructions: verify the backup status daily at 3 AM.

[TOOL_OUTPUT]
Error: database connection timeout exception HTTP 500 status traceback.

[DOC]
Unrelated backup instructions: verify the backup status daily at 3 AM.
"""
        
        # 2. Run Tier 1: semantic relevance ranking and deduplication
        # rank_chunks will split context, calculate relevance score against query using embedder,
        # perform pairwise deduplication, and return chunks sorted by relevance descending.
        ranked_chunks = rank_chunks(query, context, dedup_threshold=0.85)
        
        # Verify Tier 1 output has zero-drop guarantee
        self.assertEqual(len(ranked_chunks), 7) # 7 raw blocks
        
        # Ensure duplicates are marked but not dropped by Tier 1
        duplicates = [c for c in ranked_chunks if c.is_duplicate_of is not None]
        self.assertEqual(len(duplicates), 1) # The second backup doc is duplicate of the first
        
        # 3. Run Tier 2: optimize context and enforce budget
        # We set a tight budget of 50 tokens.
        # This will force the low-relevance backup instruction (which has relevance to backups, not HTTP 500 errors) to be dropped.
        # Meanwhile:
        # - SYSTEM block (pinned)
        # - negation/decision (Postgres migration) and constraints/numbers (30 seconds) should be pinned or kept.
        # - error/HTTP 500 status block (high relevance) should survive.
        
        # Define mock LLM that compresses text
        def mock_llm(prompt):
            if "Timeout is set to 30 seconds" in prompt:
                # Keep critical flags
                return "Timeout is 30s."
            if "relational" in prompt or "Postgres" in prompt:
                return "Postgres customer database."
            if "DynamoDB" in prompt:
                return "Migrating to DynamoDB."
            if "backup" in prompt:
                return "Verify backup daily."
            if "HTTP 500" in prompt:
                return "HTTP 500 error exception."
            return "Compressed."
            
        optimized_chunks, trace = optimize_chunks(
            query=query,
            chunks=ranked_chunks,
            token_budget=65,
            llm_call_fn=mock_llm
        )
        
        # 4. Verify Tier 2 properties:
        # - Deduplicated chunk was dropped
        kept_ids = [c.id for c in optimized_chunks]
        dup_loser_id = duplicates[0].id
        self.assertNotIn(dup_loser_id, kept_ids, "Deduplicated chunks should be dropped")
        
        # - Check coherence assembly ordering (SYSTEM first, CONVERSATION/middle, PERSISTENT_CONSTRAINT last)
        self.assertEqual(optimized_chunks[0].tag, "SYSTEM")
        
        # - Verify critical information survived
        # "Timeout is set to 30 seconds" matches number & constraint -> pinned
        timeout_chunk = [c for c in optimized_chunks if "Timeout" in c.text]
        self.assertTrue(len(timeout_chunk) > 0)
        self.assertTrue(timeout_chunk[0].pinned)
        
        # - Verify decision/migration chunk survived and was pinned
        migration_chunk = [c for c in optimized_chunks if "DynamoDB" in c.text or "migrate" in c.text.lower()]
        self.assertTrue(len(migration_chunk) > 0)
        self.assertTrue(migration_chunk[0].pinned, "Decision/migration chunk should be pinned")

        # - Verify low relevance backup chunk was dropped by the budget
        backup_chunk = [c for c in optimized_chunks if "backup" in c.text.lower()]
        self.assertEqual(len(backup_chunk), 0, "Unrelated backup chunks should have been dropped by budget")

        # - Trace verification
        self.assertEqual(trace["chunks_total"], 7)
        self.assertEqual(trace["chunks_merged_duplicate"], 1)
        self.assertGreater(trace["chunks_compressed"], 0)
        self.assertGreater(trace["chunks_removed_by_budget"], 0)
        self.assertTrue(trace["stage_tokens"]["after_budget"] <= 65)
        
        print("\nTrace output for verification:")
        print(trace)

if __name__ == "__main__":
    unittest.main()
