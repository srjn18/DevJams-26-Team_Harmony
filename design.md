# DESIGN.md — LLM Context Optimization Middleware

## 1. What we're building

Middleware that sits between an application and an LLM. Given a query + a large
context, it removes what's not needed, deduplicates what's repeated, compresses
what's kept, fits it into a token budget, and only then calls the LLM — without
breaking the answer.

We are not training a model. We are not a summarizer. We are a **cost-aware
context optimization layer** with measurable before/after token, cost, latency,
and quality numbers.

---

## 2. Two-tier pipeline (why, not just what)

Naively running embeddings + LLM-compression on every request can cost more in
latency and money than it saves. So the pipeline has a routing decision before
any expensive work happens:

```
REQUEST (query, context, budget)
        │
        ▼
TIER 0 — Deterministic prep (no paid calls, <50ms)
  - tokenize, count
  - chunk
  - tag chunks: SYSTEM / PERSISTENT_CONSTRAINT / CONVERSATION / DOC / TOOL_OUTPUT
  - rule pass: flag negations, numbers, constraints, errors → CRITICAL
  - SYSTEM + PERSISTENT_CONSTRAINT + CRITICAL chunks are PINNED:
    never scored against the query, never dropped, only ever compressed
        │
        ▼
ROUTING DECISION (cost model, not a flat token threshold)
  SKIP  → send as-is
  LIGHT → embeddings + relevance + dedup only, no compression LLM call
  FULL  → LIGHT + compression + critical protection + budget knapsack
        │
        ▼
TIER 1 — Semantic (embeddings, relevance, dedup)      [Person 1]
        │
        ▼
TIER 2 — Critical protection, compression, budget     [Person 2 — hardest part]
        │
        ▼
COHERENCE ASSEMBLY
  - reassemble surviving chunks in original chronological order, not score order
  - pinned chunks inserted at fixed slots (system first, constraints near query)
        │
        ▼
OPTIMIZED CONTEXT → LLM → ANSWER
        │
        ▼
EVALUATION (deterministic safety checks + LLM-judge quality)  [Person 3]
```

Why pinning instead of just "high importance score": a scored-but-not-pinned
constraint can still lose to a knapsack budget cut. A system prompt or an
explicit "API must remain stateless" stated once, three turns ago, must never
be filtered by per-query relevance — it isn't about *this* query, it's about
*every* query in the session. Pinning is a structural guarantee, not a score.

---

## 3. Chunk schema (contract between all modules)

```json
{
  "id": "c_0012",
  "text": "The user changed authentication from sessions to JWT.",
  "token_count": 14,
  "source": "conversation | document | tool_output | system",
  "tag": "SYSTEM | PERSISTENT_CONSTRAINT | CONVERSATION | DOC | TOOL_OUTPUT",
  "timestamp": "2026-08-29T10:00:00Z",
  "position": 12,
  "pinned": false,
  "critical_flags": ["negation", "number", "constraint", "error", "none"],
  "relevance_score": null,
  "importance_score": null,
  "final_score": null,
  "embedding": null
}
```

`position` is the original order index — used for coherence reassembly at the
end, never for scoring.

---

## 4. Tagging rules (Tier 0, deterministic, no LLM)

- `SYSTEM`: the system prompt block. Always pinned.
- `PERSISTENT_CONSTRAINT`: any chunk matching a constraint/negation/requirement
  pattern that appears to apply globally (not tied to one prior question).
  Always pinned.
- `CONVERSATION` / `DOC` / `TOOL_OUTPUT`: everything else, scored normally.

Critical-flag rule set (regex/heuristic, MVP-level, must be validated against
the adversarial suite in `tests/adversarial_cases.md`):

- Negation: `\b(do not|don't|never|must not|can't|cannot)\b` near an
  entity/tool name
- Number: any numeral followed by a unit or preceded by `=`, `is`, `set to`
- Constraint/requirement: `\b(must|required|shall|has to|needs to)\b`
- Error: HTTP status codes, stack trace markers, `error|exception|failed`
- Explicit decision: `\b(we (chose|decided|will use|are using))\b`

Any chunk matching ≥1 rule gets `critical_flags` populated and is pinned for
Tier 2 (protected from removal, eligible only for lossless-preserving
compression).

---

## 5. Two similarity thresholds — do not conflate these

| | Relevance filtering | Deduplication |
|---|---|---|
| Question | "Do we need this for the current query?" | "Do we already have this fact?" |
| Threshold | looser (e.g. cosine ≥ 0.55) | stricter (e.g. cosine ≥ 0.85) |
| Failure mode if wrong | drops something needed | merges two facts that differ ("using Postgres" vs "migrating off Postgres") — silently changes meaning |

Both thresholds are config values, not hardcoded, and both must be logged per
decision for the optimization trace shown in the demo.

---

## 6. Scoring (non-pinned chunks only)

```
final_score = 0.7 × relevance_score + 0.3 × importance_score
```

Weights are configurable, explicitly not claimed optimal — an MVP starting
point stated as such in the README and demo narration.

---

## 7. Routing decision (replaces flat token threshold)

```
est_optimizer_cost = embed_cost(n_chunks) + (compression_llm_cost if FULL)
est_savings        = (original_tokens - est_optimized_tokens) × llm_price_per_token

route = SKIP  if est_savings <= est_optimizer_cost
route = LIGHT if 0 < margin < LIGHT_FULL_THRESHOLD
route = FULL  if margin >= LIGHT_FULL_THRESHOLD
```

`est_optimized_tokens` can be a rough heuristic for the routing decision only
(e.g. assume relevance filtering alone cuts X%) — it does not need to be exact,
it only needs to decide which tier to run.

---

## 8. Compression contract (Tier 2 — see AGENT_PROMPTS.md / hardest-part kit)

Input: query, selected+deduped chunks (with pin flags), token budget.
Output: optimized context text, per-chunk trace (kept/compressed/removed/why).

Hard rule: pinned chunks may be reworded for brevity but every negation,
number, named entity, and constraint they contain must survive verbatim or
semantically identical. This is checked deterministically in evaluation, not
by LLM judge (see §10).

---

## 9. Coherence assembly

Do not concatenate by score. Reassemble surviving chunks by original
`position`/`timestamp`, with pinned chunks inserted at fixed slots (system
block first, constraints immediately before the query). This prevents
"bag of disconnected high-value fragments" answers.

---

## 10. Evaluation — two tracks, not one

**Deterministic / safety track** (adversarial cases): string/regex-check that
the specific number, negation, or constraint literally survived in the
optimized context. Do not trust an LLM judge for this — it can paraphrase-and-
miss a dropped negation.

**LLM-as-judge / quality track** (open-ended cases): temperature=0, same model
for baseline/optimized/judge where possible, disclose self-preference bias
risk explicitly in the writeup.

Metrics collected per test case:
```
original_tokens, optimized_tokens, reduction_pct
original_cost, optimizer_cost, optimized_llm_cost, net_savings
quality_score (baseline vs optimized)
latency_baseline, latency_optimized (broken down per pipeline stage)
```

---

## 11. API contract

```
POST /analyze              → token count, cost estimate, routing decision only
POST /optimize              → optimized_context + full trace (no LLM call)
POST /optimize-and-answer   → /optimize then calls the LLM (demo convenience)
```

Splitting these matters for the pitch: this is middleware, not a wrapper that
happens to also answer questions. It also lets Person 3 benchmark optimizer
overhead independent of LLM latency.

### `/optimize` response shape

```json
{
  "original_tokens": 18432,
  "optimized_tokens": 3921,
  "reduction_percentage": 78.7,
  "route": "FULL",
  "optimized_context": "...",
  "trace": {
    "chunks_total": 63,
    "chunks_removed_irrelevant": 34,
    "chunks_merged_duplicate": 12,
    "chunks_compressed": 17,
    "chunks_pinned_critical": 6,
    "stage_tokens": {
      "original": 18432,
      "after_relevance": 12100,
      "after_dedup": 9200,
      "after_compression": 5100,
      "after_budget": 3921
    }
  }
}
```

---

## 12. Failure handling

If the compression LLM call fails or times out: fall back to
relevance-filtered + deduped (uncompressed) context, truncated to budget if
necessary, rather than failing the whole request. Log that fallback occurred
in the trace so the demo doesn't silently show wrong numbers.

---

## 13. Explicitly out of scope for the 48 hours

No model training, no tokenizer building, no vector DB unless genuinely
needed, no multi-provider support, no production infra. See README for MVP
scope (must/should/stretch).
