# HARDEST_PART.md — Critical Info Protection + Compression + Budget Engine

This is your module. It's the hardest one because it's the only place where
a bug doesn't just waste tokens — it silently changes what the LLM is told,
and that failure mode is invisible unless you specifically test for it.

## Why this is the hard one

- Relevance filtering (Person 1) can be wrong and the answer just misses some
  context — usually recoverable, usually visible in a spot-check.
- Your module can be wrong in a way that looks *fine* — the optimized context
  reads perfectly coherently, the LLM answers confidently, and the answer is
  simply **wrong or dangerous**, because a negation got dropped or a number
  got paraphrased into a different number. This is the failure mode that
  will embarrass you in front of judges if you don't build the deterministic
  checks first.

Build order: **detector → adversarial tests → pinning → compression →
budget.** Do not build compression before you trust the detector, or you'll
be compressing over a foundation you can't verify.

---

## Input/output contract

```
Input:
  query: str
  chunks: list[Chunk]     # from Person 1, includes relevance_score, is_duplicate_of
  token_budget: int
  route: "LIGHT" | "FULL"  # LIGHT = you don't run at all, dedup output goes straight to assembly

Output:
  optimized_chunks: list[Chunk]   # subset, with compressed text where applicable
  trace: {
    chunks_pinned_critical: int,
    chunks_compressed: int,
    chunks_removed_by_budget: int,
    stage_tokens: {"after_relevance": int, "after_dedup": int,
                   "after_compression": int, "after_budget": int}
  }
```

You receive chunks already deduplicated by Person 1 (drop anything where
`is_duplicate_of` is not null before you start). You do NOT re-run relevance
filtering — that already happened. Your job starts from "here are the
surviving, deduplicated chunks — now protect the critical ones, compress the
rest, and fit the budget."

---

## Step A: Critical-info detection (build first, test hardest)

Tag each chunk with `critical_flags` and set `pinned=true` if any flag fires,
OR if `tag` is already `SYSTEM`/`PERSISTENT_CONSTRAINT` from Person 1.

Rule categories (regex/heuristic — this is intentionally simple for MVP,
do not build an ML classifier for this in 48 hours):

| Flag | Pattern examples | Why it's dangerous to lose |
|---|---|---|
| negation | `don't`, `do not`, `never`, `must not`, `can't`, `won't`, `shouldn't` near a named entity | "Do NOT use MongoDB" losing the negation inverts the instruction |
| number | digit sequences with units, or `= <number>`, `is <number>`, `set to <number>` | "timeout = 30s" becoming "timeout" loses the constraint entirely |
| constraint | `must`, `required`, `shall`, `has to`, `needs to`, `only`, `always` | "API must remain stateless" is load-bearing for every future turn |
| error | HTTP status codes (3-digit near "error"/"status"/"returns"), `exception`, `traceback`, `failed with` | debugging context depends on the exact code/message |
| decision | `we chose`, `we decided`, `we will use`, `we're using`, `switched to`, `migrated to` | user's explicit choice, easy to accidentally "helpfully" correct away |

Write this as a list of `(flag_name, compiled_regex)` pairs, not one giant
regex — you'll be adding/tuning patterns against the adversarial suite and
a modular list is much easier to iterate on under time pressure.

**Known blind spots to accept for MVP, but write down so the team knows:**
- Paraphrased negations without a trigger word (e.g. "MongoDB is off the
  table") won't be caught by pattern matching. If time remains, add a cheap
  LLM classification pass ("does this sentence contain a negation,
  constraint, or specific number that changes meaning if altered? yes/no")
  as a second-tier check — but ship the regex version first, it's free and
  catches the majority of your own test cases.
- Over-triggering on dense technical/legal text is expected and acceptable —
  false positives (pinning too much) are much safer than false negatives
  here, so bias the rules toward pinning when uncertain.

---

## Step B: Write the adversarial tests BEFORE trusting the detector

Do not proceed to compression until `tests/adversarial_cases.md` (Person 3
is writing this in parallel — coordinate) passes for detection. At minimum,
confirm your regex catches:

- `"Do NOT use MongoDB for this project."` → negation flag, pinned
- `"We can't go with Mongo."` → paraphrase, may legitimately fail MVP regex —
  note as known gap, don't silently pass
- `"Timeout is set to 30 seconds."` → number flag, pinned
- `"The timeout, thirty seconds, was chosen after testing."` → number in
  prose, spelled out — likely a gap, note it
- `"The API must remain stateless even under load."` → constraint flag,
  pinned
- `"Endpoint returns HTTP 401 after the auth change."` → error flag, pinned
- `"We decided to migrate off Postgres next quarter."` → decision flag,
  pinned — and this must NOT get deduplicated with an earlier "we use
  Postgres" statement upstream (that's Person 1's dedup threshold, but
  verify it didn't happen before this chunk reaches you)

Log a pass/fail table. Ship the compressor only once this table is mostly
green and every red case is a documented known gap, not a surprise.

---

## Step C: Compression (only non-pinned, non-critical chunks get rewritten)

Pinned chunks: never rewritten by an LLM. Only allowed transformation is
removing surrounding filler *outside* the critical clause — the critical
clause itself passes through untouched. Simplest safe approach for MVP:
**don't compress pinned chunks at all.** Compression risk is not worth the
token savings on a small subset of chunks — spend your compression budget on
the non-critical majority instead.

Non-pinned, non-critical chunks: send to the LLM with an explicit
instruction to preserve facts/constraints/numbers/names even though you've
already screened out the ones you know are critical — treat this as a
second safety net, not the primary defense.

Prompt shape (do not just say "summarize this"):

```
Rewrite the following context to be as concise as possible while preserving
every fact, number, date, name, and technical detail. Do not remove any
information that could affect the answer to this question: "{query}"

Do not add information that isn't present. Do not soften or generalize
specific claims. If in doubt, keep it rather than cut it.

Context:
{chunk_text}
```

Call this per-chunk or batched (batching a few chunks per call reduces
round-trips — reasonable tradeoff for hackathon time budget, note the
tradeoff in your writeup).

**Verify after compression, not just before**: re-run your Step A detector
on the compressed text. If a critical flag that was present pre-compression
is missing post-compression, that's a bug — either revert that chunk to its
original uncompressed text, or flag it in the trace as a compression
failure. Do not silently ship a compressed chunk that lost a flag.

---

## Step D: Token budget (knapsack)

After compression, you likely still exceed budget. Rank surviving chunks by
`final_score` (pinned chunks get an effectively infinite score — they are
never cut by budget, they can only be truncated as an absolute last resort
if the budget is smaller than the pinned content itself, which should be
rare and worth logging loudly if it happens).

Greedy knapsack is fine for MVP — sort non-pinned chunks by score
descending, add until budget hit, drop the rest. Do not spend hackathon time
on optimal knapsack (DP) — greedy is within a rounding error of optimal for
this and vastly simpler to debug live during a demo.

```
kept = [c for c in chunks if c.pinned]
budget_remaining = token_budget - sum(c.token_count for c in kept)
for c in sorted(non_pinned, key=lambda x: -x.final_score):
    if c.token_count <= budget_remaining:
        kept.append(c)
        budget_remaining -= c.token_count
    # else: dropped, log why
```

If `budget_remaining < 0` after adding pinned chunks alone: log this loudly
in the trace (`"budget_exceeded_by_pinned_content": true`) rather than
silently truncating a constraint mid-sentence.

---

## Checklist (work through top to bottom, don't skip ahead)

- [ ] Regex/heuristic detector for negation/number/constraint/error/decision
- [ ] Detector unit-tested against the adversarial cases (coordinate with
      Person 3) — pass/fail table written down, gaps documented
- [ ] Pinning logic: SYSTEM/PERSISTENT_CONSTRAINT tags + any critical_flags
      → pinned=true
- [ ] Compression prompt written and tested on 3-4 real chunk examples by
      hand before wiring into the pipeline
- [ ] Pinned chunks are never sent to the compressor
- [ ] Post-compression re-verification: flags present before must be present
      after, or the chunk reverts to original text
- [ ] Greedy knapsack budget enforcement, pinned chunks exempt from cuts
- [ ] Loud logging if pinned content alone exceeds budget
- [ ] Fallback path exists: if the compression LLM call fails, return
      uncompressed-but-filtered chunks truncated to budget (coordinate with
      Person 4, who catches this at the orchestration layer — but your
      function should raise a clear typed exception, not crash silently, so
      that fallback can trigger)
- [ ] Trace object populated: chunks_pinned_critical, chunks_compressed,
      chunks_removed_by_budget, stage_tokens

---

## Starter code

See `stubs/hardest_part_starter.py` in this repo for a runnable skeleton
implementing Steps A–D above with the regex rules, pinning, greedy knapsack,
and trace object already wired — compression LLM call left as a stub for you
to plug in your chosen provider/model.
