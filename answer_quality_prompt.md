Build the answer-quality comparison module -- the last major missing piece
of this project. Everything so far proves token reduction and critical-info
survival at the CHUNK level. Nothing yet proves the final LLM ANSWER is
still good after optimization. This closes that gap.

## 1. Create `answer_quality.py` in `semantic_relevance_engine/`

For a given (query, original_context, optimized_context) triple, this
module should:

1. Call Grok with the ORIGINAL context + query -> baseline_answer
2. Call Grok with the OPTIMIZED context + query -> optimized_answer
3. Run a comparison (see §2 and §3 below)
4. Return a structured result, not just print statements, so it can be
   aggregated across many test cases later

```python
@dataclass
class AnswerQualityResult:
    query: str
    baseline_answer: str
    optimized_answer: str
    comparison_type: str  # "deterministic" | "llm_judge"
    passed: bool | None    # for deterministic checks
    judge_score_baseline: float | None   # for llm_judge checks
    judge_score_optimized: float | None
    judge_reasoning: str | None
    notes: str
```

Use `grok_compress`-style client calls (reuse `grok_client.py`'s
`_get_client()` pattern, or add a plain `grok_answer(prompt: str) -> str`
function to `grok_client.py` if a dedicated non-compression call is
cleaner -- either is fine, just don't duplicate the client setup code).

## 2. Deterministic checks for adversarial test cases

For test cases built from your adversarial scenarios (the ones with a
known negation, number, constraint, or decision baked in), do NOT use an
LLM judge -- check directly whether the optimized_answer's BEHAVIOR still
respects the critical fact. Examples:

- If context says "Do NOT use MongoDB", check that optimized_answer does
  NOT recommend or mention using MongoDB as a solution (simple keyword/
  pattern check on the answer text, not the context).
- If context says "Timeout is set to 30 seconds", and the query asks about
  timeout behavior, check that optimized_answer states "30" somewhere if
  it discusses the timeout value at all (don't require it to always
  mention the number if the question doesn't call for it -- just check it
  doesn't state a WRONG number if it does mention one).
- If context contains "HTTP 401" and the query is about the error, check
  optimized_answer references "401" and not a different, hallucinated
  status code.

Write at least 5 of these using your existing adversarial cases from
`adversarial_cases.md` and `test_hard_cases.py`. Report each as PASS/FAIL
with the actual answer text quoted, not just a boolean.

## 3. LLM-judge comparison for open-ended test cases

For test cases without a single deterministic fact to check (e.g. "why is
my BFS slower than DFS", general explanatory questions), use a third Grok
call as a judge:

```
You are evaluating two answers to the same question, generated from two
different versions of the source context (one full, one compressed/
optimized). Score each answer 1-10 on correctness, completeness, and
relevance to the question. Do not favor either answer based on length or
style alone -- focus on whether the factual content is accurate and
complete relative to what the source context actually supports.

Question: {query}

Answer A: {baseline_answer}
Answer B: {optimized_answer}

Respond in this exact format:
Answer A score: <number>
Answer B score: <number>
Reasoning: <one or two sentences>
```

Parse the judge's response into `judge_score_baseline` and
`judge_score_optimized`. In your written report, explicitly disclose that
the same model family is being used to answer AND judge, which risks
self-preference bias -- do not hide this, state it plainly next to any
aggregate quality numbers you report.

## 4. Build the test case set

Reuse your existing scenarios rather than inventing new ones:
- The 4 (or 5) scenarios already in `measure_token_savings.py`
- At minimum, extract 2-3 deterministic adversarial checks per scenario
  where applicable (Scenario 3 in particular, since it's built specifically
  around critical facts)
- For Scenario 2 (everything relevant, general question), use the
  LLM-judge path since there's no single fact to check deterministically

## 5. Wire this into `measure_token_savings.py`

After the existing token/cost reporting for each scenario, add a call to
the new answer-quality comparison and print its result alongside the
existing token stats, so a single script run produces the FULL demo
picture: tokens saved, cost saved, AND answer quality preserved (or not).

## 6. Report format

Run this across all scenarios and report, per scenario:
- Deterministic check results (if applicable): PASS/FAIL with quoted answer
  text
- LLM-judge scores (if applicable): baseline score vs. optimized score,
  plus the judge's one-line reasoning
- Any case where the optimized answer meaningfully regressed (lower score,
  or a deterministic check failed) -- flag these clearly and do not average
  them away in an aggregate number without also showing the individual
  failure

Do not claim overall success from a single averaged score if any
individual deterministic check failed -- a failed critical-fact check is a
correctness bug, not a quality trade-off, and should be reported and fixed
before considering this done, not folded into an average.
