"""
Command-line interface for Semantic Relevance Engine.
Provides human-readable formatted table reports or raw JSON exports.
"""

import sys
import json
import argparse
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from semantic_relevance_engine import rank_chunks


SAMPLE_CONTEXT = """[SYSTEM]
You are an expert AI assistant that optimizes large context windows for LLMs.

[USER]
How do we configure vector indexing and semantic similarity in our database?

[DOC]
Vector search indexing uses cosine similarity across dense embeddings to retrieve relevant documentation sections rapidly.

[DOC]
Vector search indexing uses cosine similarity across dense embeddings to retrieve relevant documentation sections.

[CONVERSATION]
We are currently using Postgres for storing user session state and relational records.

[CONVERSATION]
We are migrating off Postgres to DynamoDB next quarter for better distributed scalability.

[TOOL_OUTPUT]
{"status": "ok", "index_size_mb": 128.5, "latency_ms": 14}
"""

SAMPLE_QUERY = "How does vector indexing and cosine similarity work in database documentation?"


def main():
    parser = argparse.ArgumentParser(
        description="Semantic Relevance Engine CLI - Ranks context chunks against a query."
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        default=SAMPLE_QUERY,
        help="The query string to rank context against."
    )
    parser.add_argument(
        "--context", "-c",
        type=str,
        default=SAMPLE_CONTEXT,
        help="Raw context string containing messages, documents, and tool outputs."
    )
    parser.add_argument(
        "--context-file", "-f",
        type=str,
        default=None,
        help="Path to a text file containing the context."
    )
    parser.add_argument(
        "--relevance-threshold",
        type=float,
        default=0.55,
        help="Downstream relevance threshold reference (default: 0.55)."
    )
    parser.add_argument(
        "--dedup-threshold",
        type=float,
        default=0.85,
        help="Deduplication pairwise cosine threshold (default: 0.85)."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON array of chunk dictionaries."
    )

    args = parser.parse_args()

    context_str = args.context
    if args.context_file:
        with open(args.context_file, "r", encoding="utf-8") as fp:
            context_str = fp.read()

    results = rank_chunks(
        query=args.query,
        context=context_str,
        relevance_threshold=args.relevance_threshold,
        dedup_threshold=args.dedup_threshold,
    )

    if args.json:
        print(json.dumps([c.to_dict(include_embedding=False) for c in results], indent=2))
        return

    print("\n" + "=" * 90)
    print(f" SEMANTIC RELEVANCE ENGINE REPORT")
    print("=" * 90)
    print(f" Query: {args.query}")
    print(f" Chunks processed: {len(results)} | Relevance Threshold: {args.relevance_threshold} | Dedup Threshold: {args.dedup_threshold}")
    print("-" * 90)
    print(f"{'Rank':<5} {'ID':<8} {'Score':<8} {'Tag':<14} {'Pinned':<8} {'Dup Of':<10} {'Flags':<22} {'Preview'}")
    print("-" * 90)

    for i, c in enumerate(results, 1):
        dup_str = c.is_duplicate_of or "-"
        pinned_str = "YES" if c.pinned else "no"
        flags_str = ",".join(c.critical_flags) if c.critical_flags else "-"
        text_preview = (c.text[:40] + "...") if len(c.text) > 40 else c.text
        text_preview = text_preview.replace("\n", " ")

        print(f"{i:<5} {c.id:<8} {c.relevance_score:<8.4f} {c.tag:<14} {pinned_str:<8} {dup_str:<10} {flags_str:<22} {text_preview}")

    print("=" * 90 + "\n")


if __name__ == "__main__":
    main()
