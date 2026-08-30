# IMPLEMENTATION.md — Wiring in Gemini 3.6 Flash + Measuring Real Token Savings

This is the plan for the last remaining piece: connecting real LLM
compression to the already-built and tested Tier 1 + Tier 2 pipeline, and
getting actual, measured token/cost numbers instead of mock-based estimates.

Everything up to this point (chunking, relevance, dedup, pinning,
compression logic, budget, coherence assembly) is done and tested with mock
LLM functions. This step only adds the real model behind `llm_call_fn` and
a measurement script — it does not change any pipeline logic.

---

## 1. Model facts (confirmed, not assumed)

- Model ID: `gemini-3.6-flash`, released July 21, 2026, still stable/
  supported by Google as of now (superseded by 3.7 Flash on Aug 13, 2026,
  but not deprecated).
- Pricing: $1.50 / 1M input tokens, $3.75-$7.50 / 1M output tokens depending
  on provider (use $1.50 in / $7.50 out for official Google pricing).
- Context window: 1,048,576 input tokens, 65,536 output tokens.
- **Important**: `temperature`, `top_p`, `top_k` are deprecated for Gemini
  3.x per Google's own migration guidance — do not rely on them for
  deterministic output. This conflicts with the earlier project-wide
  decision to force `temperature=0` on every compression call. Resolve
  this explicitly (see §5) rather than silently ignoring it.

---

## 2. Setup

```bash
pip install google-genai
export GEMINI_API_KEY="your-key-here"    # or GOOGLE_API_KEY
```

Get a key from Google AI Studio if you don't have one yet. Confirm the key
works with a single manual call before wiring it into the pipeline (see
§3, smoke test).

---

## 3. Build the LLM client wrapper

File: `gemini_client.py` (already provided — see `gemini_client.py` in this
project's outputs).

Requirements for this file:
- Exposes exactly one function matching the contract every other module
  already expects: `gemini_compress(prompt: str) -> str`.
- Does NOT swallow exceptions — raises on failure, so the pipeline's
  existing fallback logic (uncompressed-but-filtered content) is what
  catches it, not this function itself.
- Does NOT pass `temperature`/`top_p`/`top_k` (see §5 for the determinism
  discussion).
- Lazily initializes the `genai.Client` once (module-level singleton),
  not on every call.

**Verification step (do this before wiring into the full pipeline):**
```bash
python gemini_client.py
```
This runs the built-in smoke test — a single hardcoded compression prompt.
Confirm:
- It returns actual text, not an error.
- The output is meaningfully shorter than the input.
- The output still contains the facts from the input (spot-check by eye:
  does "HTTP 401" survive? does "JWT" survive?).

Do not proceed to full pipeline integration until this single-call smoke
test passes cleanly.

---

## 4. Wire it into the pipeline

No changes needed to `optimizer.py`, `chunker.py`, or `engine.py`. Wherever
`optimize_chunks` is currently called with `llm_call_fn=None` or a mock
function, swap in the real one:

```python
from gemini_client import gemini_compress

optimized_chunks, trace = optimize_chunks(
    query=query,
    chunks=ranked_chunks,
    token_budget=token_budget,
    llm_call_fn=gemini_compress,   # <-- only change needed
)
```

This applies to:
- The `/optimize` and `/optimize-and-answer` API endpoints (Person 4's
  orchestration layer)
- Any CLI `--optimize`/`--full-pipeline` flag, if built
- The measurement script in §6

---

## 5. Resolve the determinism conflict explicitly

Pick one of these two options and document which one in your final writeup
— don't leave this ambiguous:

**Option A (recommended): Accept non-determinism, note it explicitly.**
Gemini 3.6 Flash's default behavior is what Google tuned it for; don't
fight the deprecated parameters. In your demo/writeup, state plainly that
compression output may vary slightly between runs, and that your
determinism guarantees apply to the DETECTION and PINNING logic (which are
pure regex, always deterministic) — not to the compression wording itself.
This is the honest framing: the safety net (critical info never lost) is
deterministic; the exact phrasing of compressed prose is not, and doesn't
need to be.

**Option B: Test if `temperature` is silently still accepted.**
Some SDKs continue to accept deprecated parameters for backward
compatibility even after doc guidance changes. Test this directly:
```python
response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents=prompt,
    config={"temperature": 0}  # or whatever config shape the SDK expects
)
```
If this doesn't raise an error, decide whether relying on undocumented
backward-compatible behavior is worth the risk for a hackathon demo (fine,
short-term) versus something to flag as fragile (also fine, just be aware).

Do not spend more than 10-15 minutes on this decision — Option A is safe
and sufficient; only pursue Option B if you have spare time.

---

## 6. Build and run the token savings measurement

File: `measure_token_savings.py` (already provided — see this project's
outputs).

This script runs the full real pipeline twice on the same input:
1. **Baseline**: `llm_call_fn=None` — relevance filtering, dedup, pinning,
   and budget enforcement all run for real, but compression is a no-op.
   This isolates how much reduction comes from filtering/dedup alone.
2. **With real Gemini compression**: same input, `llm_call_fn=gemini_compress`.
   This shows the additional reduction compression contributes on top of
   filtering/dedup.

Reporting includes, per run:
- `original_tokens` → `after Tier 1` → `final optimized tokens`
- Reduction percentage
- Trace fields: `chunks_pinned_critical`, `chunks_compressed`,
  `chunks_removed_by_budget`, `critical_before`/`critical_after`
- Approximate cost comparison (sending original context vs. optimized
  context vs. the cost of the compression calls themselves), using Gemini
  3.6 Flash's real published pricing

**Run it:**
```bash
python measure_token_savings.py
```

Adjust the import paths at the top of the script to match your actual
module layout under `semantic_relevance_engine/` before running.

**What "done" looks like for this step:** you have two real numbers you can
put in your demo — reduction from filtering/dedup alone, and additional
reduction from real LLM compression — plus confirmation that
`critical_before == critical_after` (nothing critical was lost) on your
test input.

---

## 7. Get exact per-call token costs (do this before finalizing demo numbers)

The cost estimate in `measure_token_savings.py` currently uses your own
`approx_token_count()` function, not Gemini's actual tokenizer — these will
differ slightly. For accurate final numbers:

1. Modify `gemini_compress` in `gemini_client.py` to capture and return (or
   log) `response.usage_metadata.prompt_token_count` and
   `.candidates_token_count` from each real API call.
2. Sum these across all compression calls in a run and compare against the
   approximated cost in `measure_token_savings.py`.
3. Use the real numbers in your final demo slide/dashboard, not the
   approximation — the approximation is fine for development iteration,
   not for the number you say out loud to judges.

---

## 8. Test with realistic mixed input before trusting the numbers

Don't just run the measurement script on a single toy example and call it
done. Run it against:
- At least one of your team's real adversarial test cases from
  `adversarial_cases.md` (converted into a full raw-context string, not
  isolated chunk objects)
- One deliberately "mostly irrelevant" context (per the original adversarial
  testing plan) to confirm large reduction happens as expected
- One deliberately "everything relevant" context to confirm reduction stays
  limited and compression does more of the work than removal

Record the actual reduction percentage and cost savings for each scenario
— these become your demo's "before/after" evidence across different
realistic conditions, not just one cherry-picked example.

---

## 9. Final checklist before calling this done

- [ ] `gemini_client.py` smoke test passes with real API output
- [ ] Determinism decision made and documented (§5, Option A recommended)
- [ ] Full pipeline runs end-to-end with real `gemini_compress` wired in,
      no crashes
- [ ] `measure_token_savings.py` run on at least 3 different context
      scenarios (toy example, mostly-irrelevant, everything-relevant)
- [ ] `critical_before == critical_after` confirmed on every run (nothing
      critical lost)
- [ ] Real per-call token usage captured from `usage_metadata`, not just
      approximated
- [ ] Fallback path re-tested with the REAL client this time: force a
      failure (invalid API key, network cutoff) and confirm the pipeline
      still falls back to uncompressed-but-filtered content rather than
      crashing
- [ ] Final reduction % and cost savings numbers written down for the demo,
      sourced from real runs, not estimates
