# AGENT_PROMPTS.md

Copy the relevant section whole into your AI coding agent (Claude Code, etc.)
as the first message. Each brief includes the locked interface contract so
your agent can build against a stub immediately instead of waiting on anyone
else's real implementation. Do not let your agent change these interfaces
without telling the other three people.

---

## PERSON 1 — Semantic Relevance Engine

```
You are building the Semantic Relevance Engine for a hackathon LLM context
optimization middleware. Read this brief fully before writing code.

GOAL
Given a query and a large context, split it into chunks, embed them, and
return the chunks ranked/filtered by relevance to the query, with
duplicates merged. You do NOT compress or call an LLM for rewriting — that's
a different module.

INPUT CONTRACT (you receive this)
{
  "query": "string",
  "context": "string (raw, could be conversation history + docs + tool output concatenated with source markers)"
}

CHUNK SCHEMA (you produce this — do not deviate, other modules depend on it)
{
  "id": "c_0001",
  "text": "string",
  "token_count": int,
  "source": "conversation | document | tool_output | system",
  "tag": "SYSTEM | PERSISTENT_CONSTRAINT | CONVERSATION | DOC | TOOL_OUTPUT",
  "timestamp": "ISO8601 or null",
  "position": int,              // original order, 0-indexed
  "pinned": bool,                // true if tag is SYSTEM or PERSISTENT_CONSTRAINT
  "critical_flags": ["negation"|"number"|"constraint"|"error"|"decision"|...],
  "relevance_score": float,      // cosine similarity to query, 0-1
  "is_duplicate_of": "c_000X or null",
  "embedding": [float, ...]       // ok to omit from final API response, keep internally
}

YOUR JOB, STEP BY STEP
1. Chunking: split context into chunks. Keep it simple — split conversation
   history by message, documents by paragraph/section, tool outputs as one
   chunk each. Do not over-engineer this.
2. Tagging: mark the system-prompt chunk as SYSTEM (always pinned=true).
   Everything else defaults to its source type for now — a separate module
   (Person 2) will additionally flag PERSISTENT_CONSTRAINT and
   critical_flags; leave those fields present but populate what you can.
3. Embeddings: embed the query once, embed every chunk once. Use a small
   fast off-the-shelf embedding model (e.g. an OpenAI/Anthropic-compatible
   embeddings endpoint or a local sentence-transformers model — pick
   whichever is fastest to wire up, this is not the novel part of the
   project).
4. Relevance scoring: cosine similarity between query embedding and each
   chunk embedding → relevance_score.
5. Deduplication: compute pairwise cosine similarity BETWEEN chunks (not
   vs query). Use a STRICTER threshold than relevance filtering — e.g.
   relevance threshold ~0.55, dedup threshold ~0.85. These must be two
   separate configurable constants, not the same number. When two chunks
   exceed the dedup threshold, keep the more information-dense one (longer,
   or higher relevance_score) and mark the other is_duplicate_of=<kept id>.
   DO NOT merge chunks that are topically similar but state different facts
   (e.g. "using Postgres" vs "migrating off Postgres" — these must NOT be
   deduplicated even though they're semantically close).
6. Output: return the full list of chunks with relevance_score and
   is_duplicate_of populated, sorted by relevance_score descending. Do not
   drop any chunks yourself — filtering by threshold happens downstream in
   the budget/routing stage, you just supply the scores.

DELIVERABLE
A single function/module:
  rank_chunks(query: str, context: str) -> list[Chunk]
Plus a CLI or test script that prints the ranked output for a sample input
so other people can sanity check it immediately.

FIRST THING TO DO (hour 0-1)
Before building the real thing, ship a STUB version that returns hardcoded
fake chunks in the exact schema above (3-5 fake chunks, fake scores) so
Persons 2, 3, and 4 can build against your interface immediately without
waiting for your real embeddings pipeline. Commit this stub first, then
replace it with the real implementation.

DO NOT build compression, critical-info detection, or LLM calls — those
belong to Person 2. Stay in your lane so integration doesn't conflict.
```

---

## PERSON 3 — LLM + Evaluation + Cost Engine

```
You are building the LLM integration, cost model, routing decision, and
evaluation engine for a hackathon LLM context optimization middleware.

GOAL
Decide whether optimization is worth running (routing), call the LLM for
both baseline and optimized paths, and measure whether optimization actually
helped: token reduction, cost reduction, latency, and answer quality.

ROUTING DECISION (build this early — it's cheap and testable in isolation)
Given original_token_count and a rough estimate of achievable reduction:
  est_optimizer_cost = embed_cost(n_chunks) + (compression_llm_cost if FULL path)
  est_savings = (original_tokens - est_optimized_tokens_guess) * llm_price_per_token
  route = "SKIP" if est_savings <= est_optimizer_cost
  route = "LIGHT" if 0 < margin < LIGHT_FULL_THRESHOLD   # relevance+dedup only, no compression LLM call
  route = "FULL" if margin >= LIGHT_FULL_THRESHOLD         # adds compression + budget
This is a real cost model, not a flat token threshold — make the constants
(LIGHT_FULL_THRESHOLD, llm_price_per_token, embed_cost) configurable.

LLM INTEGRATION
- Same LLM for baseline and optimized paths wherever possible (controlled
  comparison).
- temperature=0 (or lowest available) on every call — compression is
  stochastic and non-determinism will make the demo look flaky if you don't
  pin it.
- Wrap every call in try/except. If a call fails, that's Person 4's fallback
  logic to catch upstream — you just need to raise a clear, typed error, not
  crash silently.

EVALUATION — TWO SEPARATE TRACKS, DO NOT MIX THEM
1. Deterministic / safety track (for adversarial test cases only):
   String/regex-check that a specific number, negation, or constraint
   literally survived in the optimized_context. Do NOT use an LLM judge for
   this — it can paraphrase-and-miss a dropped negation without flagging it.
   Example: test case says "Do NOT use MongoDB" — after optimization, assert
   the optimized_context still contains a negation associated with MongoDB
   (don't just check the substring "MongoDB" is present — check the negation
   survived too).
2. LLM-as-judge / quality track (for open-ended natural-language cases):
   Have the judge score correctness/relevance/completeness/consistency on
   baseline answer vs optimized answer, temperature=0. Use the same model as
   the answering model where possible. In your writeup, explicitly disclose
   that same-model-as-judge risks self-preference bias — don't hide this.

METRICS TO COLLECT PER TEST CASE
{
  "original_tokens": int, "optimized_tokens": int, "reduction_pct": float,
  "original_cost": float, "optimizer_cost": float, "optimized_llm_cost": float,
  "net_savings": float,
  "quality_baseline": float, "quality_optimized": float,
  "latency_baseline_ms": int, "latency_optimized_ms": int,
  "latency_breakdown": {"embedding_ms": int, "compression_ms": int, "llm_ms": int}
}

BENCHMARK SET — BUILD THIS EARLY (hour 2-10), IN PARALLEL WITH PERSON 2
Write 20-30 test cases NOW, before Person 2's critical-info detector is done,
so it can be validated against real adversarial cases as soon as it exists.
Categories, per the project's adversarial testing plan:
  - mostly irrelevant context (expect large reduction)
  - everything relevant (expect limited removal)
  - repeated information (expect dedup to trigger)
  - negations ("do NOT use X") — must survive
  - numbers ("timeout = 30 seconds") — must survive unchanged
  - constraints ("API must remain stateless") — must survive
  - small context (expect route=SKIP)
Put these in tests/adversarial_cases.md in the shared repo.

DELIVERABLE
- routing_decision(token_count, estimated_reduction) -> "SKIP"|"LIGHT"|"FULL"
- run_baseline(query, context) -> {answer, tokens, cost, latency}
- run_optimized(query, optimized_context) -> {answer, tokens, cost, latency}
- evaluate(test_case, baseline_result, optimized_result) -> metrics dict above
- 20-30 written test cases before hour 10

Only report numbers you actually measured. Do not estimate or invent
benchmark results for the demo.
```

---

## PERSON 4 — Backend + Frontend + Integration

```
You are building the backend orchestration, API, and dashboard for a
hackathon LLM context optimization middleware.

GOAL
Wire Person 1's relevance module, Person 2's compression module, and Person
3's LLM/eval module into a working pipeline exposed over three endpoints,
with a dashboard showing before/after numbers and WHY tokens were removed.

API — THREE SEPARATE ENDPOINTS, DO NOT BUNDLE THEM
This split matters for the project's positioning as middleware, not a
wrapper that happens to also answer questions — keep them distinct even
though it's a bit more code.

POST /analyze
  in:  {"query": str, "context": str, "token_budget": int|null}
  out: {"original_tokens": int, "estimated_cost": float, "route": "SKIP|LIGHT|FULL"}
  (no LLM call, no optimization actually run — just the routing decision)

POST /optimize
  in:  {"query": str, "context": str, "token_budget": int}
  out: {
    "original_tokens": int, "optimized_tokens": int, "reduction_percentage": float,
    "route": str, "optimized_context": str,
    "trace": {
      "chunks_total": int, "chunks_removed_irrelevant": int,
      "chunks_merged_duplicate": int, "chunks_compressed": int,
      "chunks_pinned_critical": int,
      "stage_tokens": {"original": int, "after_relevance": int,
                        "after_dedup": int, "after_compression": int,
                        "after_budget": int}
    }
  }
  (runs the full pipeline, no LLM inference call)

POST /optimize-and-answer
  in: same as /optimize
  out: everything /optimize returns, plus {"answer": str}
  (calls /optimize internally, then calls the LLM — this is the demo
  convenience endpoint)

PIPELINE ORCHESTRATION ORDER (call in this order, do not reorder)
1. Tier 0 (Person 1's chunking/tagging, deterministic, no paid calls)
2. Routing decision (Person 3's cost model) → SKIP short-circuits here
3. Tier 1 (Person 1's embeddings/relevance/dedup) — skip this stage entirely
   if route == SKIP
4. Tier 2 (Person 2's critical-protection/compression/budget) — skip this
   stage if route == LIGHT (LIGHT path stops after dedup)
5. Coherence assembly: reorder surviving chunks by their `position` field
   (NOT by score), pinned chunks inserted at fixed slots — system block
   first, constraints immediately before the query text. This is a small
   but important step — do not just concatenate in score order, it produces
   incoherent prompts.
6. Return trace + optimized_context

FALLBACK / GRACEFUL DEGRADATION — BUILD THIS, DON'T SKIP IT
If Person 2's compression call fails or times out, catch it and fall back to
the Tier-1 output (relevance-filtered + deduped, uncompressed), truncated to
the token budget if necessary, rather than failing the whole request. Log
`"fallback_triggered": true` in the trace so the dashboard doesn't silently
show numbers from a degraded run without saying so.

PER-STAGE LATENCY LOGGING — WIRE THIS IN FROM THE START, NOT AT HOUR 26
Time each stage (chunking, embedding, compression, LLM call) separately and
include it in the response. Retrofitting this later is more painful than
building it in from the first integration.

DASHBOARD (keep it simple, function over polish for the first pass)
Show:
  - query + context input, token budget field, [Optimize] button
  - original tokens / optimized tokens / reduction %
  - cost comparison (original vs optimizer+optimized)
  - quality score (from Person 3's eval, once available)
  - latency (baseline vs optimized, broken down per stage)
  - optimization trace: chunk counts removed/merged/compressed/pinned, and
    the stage-by-stage token count waterfall (original → after relevance →
    after dedup → after compression → after budget)
Only display numbers the system actually measured — no placeholder/fake
numbers in the final demo build.

FIRST THING TO DO (hour 0-2)
Stand up the three endpoints against Person 1's STUB output (see Person 1's
brief) so the API contract is exercised end-to-end before any real module is
finished. This is how you catch interface mismatches on hour 2, not hour 12.
```

---

## Notes for whoever assigns these

- Person 2's brief is deliberately not included here — see `HARDEST_PART.md`,
  which is a fuller spec, checklist, and starter code rather than a short
  agent brief, because it's the highest-risk module.
- If someone's AI agent proposes changing the chunk schema or API contract
  mid-build, stop and get agreement from the other three before it merges —
  a silent schema drift here is the most likely cause of an hour-12
  integration failure.
