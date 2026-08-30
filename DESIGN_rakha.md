# DESIGN.md — Swapping in Rakha.ai (OpenAI-Compatible)

This is a provider swap, not an architecture change. Every part of this
project already routes through one contract:

```
llm_call_fn(prompt: str) -> str
```

`gemini_client.py` implements this against Gemini. `grok_client.py`
implements it against Groq. This doc adds `rakha_client.py` implementing
the exact same contract against Rakha.ai. Nothing in `optimizer.py`,
`chunker.py`, `engine.py`, or `answer_quality.py` needs to change — only
the import at the call site changes.

**Before writing any code, fill in the four unknowns below from Rakha.ai's
actual docs/dashboard.** Everything after that is copy-paste-adjust from
`grok_client.py`, since both are OpenAI-compatible.

---

## 1. Unknowns to confirm first (do not guess these)

| Item | Where to find it | Placeholder used below |
|---|---|---|
| Base URL | Rakha.ai docs / API reference page | `RAKHA_BASE_URL` |
| API key env var name | Whatever they told you to set | `RAKHA_API_KEY` |
| Model name(s) available | Their dashboard or docs | `RAKHA_MODEL` |
| Any non-standard params (e.g. a `reasoning_format`-style quirk like Groq's Qwen models needed) | Their docs, or trial-and-error via the smoke test in §4 | TBD |

Do not proceed past §2 until these four are confirmed — guessing a base
URL or model name wastes a debugging cycle for something that's a two-line
lookup.

---

## 2. Setup

```bash
export RAKHA_API_KEY="the-key-they-gave-you"
```

Since it's OpenAI-compatible, no new SDK is needed — reuse the `openai`
package already installed for `grok_client.py`:

```bash
pip install openai   # already installed if grok_client.py works
```

---

## 3. Build `rakha_client.py`

Location: `semantic_relevance_engine/rakha_client.py` — same package as
every other client, per the project's established convention (don't
reintroduce a root-level file).

Structure it identically to `grok_client.py` (same lazy-client pattern,
same token-usage tracking, same error-raising discipline), with only the
base URL, API key env var, and default model swapped:

```python
"""
Rakha.ai client for the compression/answer stage. Drop-in replacement for
gemini_client.py / grok_client.py -- same contract, same call sites.
"""

import os
from openai import OpenAI

_client = None

DEFAULT_MODEL = os.environ.get("RAKHA_MODEL", "REPLACE_WITH_REAL_MODEL_NAME")
RAKHA_BASE_URL = "REPLACE_WITH_REAL_BASE_URL"  # e.g. "https://api.rakha.ai/v1"


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("RAKHA_API_KEY")
        if not api_key:
            raise RuntimeError("No API key found. Set RAKHA_API_KEY.")
        _client = OpenAI(api_key=api_key, base_url=RAKHA_BASE_URL)
    return _client


def rakha_compress(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Matches the llm_call_fn(prompt: str) -> str contract."""
    client = _get_client()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.choices[0].message.content
    if not text:
        raise ValueError("Rakha.ai returned no text content")

    if hasattr(response, "usage") and response.usage:
        _record_usage(response.usage.prompt_tokens, response.usage.completion_tokens)

    return text


def rakha_answer(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Same call, separate name for clarity at answer-generation call sites
    (mirrors grok_answer's role)."""
    return rakha_compress(prompt, model=model)


# --- Real token usage tracking (mirrors grok_client.py) ---
_usage_totals = {"prompt_tokens": 0, "completion_tokens": 0}


def _record_usage(prompt_tokens: int, completion_tokens: int):
    _usage_totals["prompt_tokens"] += prompt_tokens
    _usage_totals["completion_tokens"] += completion_tokens


def get_token_usage() -> dict:
    return dict(_usage_totals)


def reset_token_usage():
    _usage_totals["prompt_tokens"] = 0
    _usage_totals["completion_tokens"] = 0


if __name__ == "__main__":
    test_prompt = "Rewrite concisely: The weather today is sunny with a high of 75 degrees."
    print(f"Calling Rakha.ai ({DEFAULT_MODEL})...")
    result = rakha_compress(test_prompt)
    print(f"Result: {result}")
    print(f"Token usage: {get_token_usage()}")
    print("Smoke test PASSED!" if result and len(result) < len(test_prompt) * 2 else "CHECK OUTPUT")
```

---

## 4. Live smoke test before touching the pipeline

Same discipline as every previous provider swap in this project — do not
wire this into `optimize_chunks` or `answer_quality.py` until this passes:

```bash
python semantic_relevance_engine/rakha_client.py
```

Confirm:
- Real network call (not instant — check latency is realistic, seconds not
  milliseconds)
- Non-empty, sensible output
- `get_token_usage()` returns non-zero real numbers, not estimates

If it fails, check for provider-specific quirks BEFORE assuming the code
is wrong — the Groq integration needed `extra_body={"reasoning_format":
"hidden"}` for thinking models, discovered only by testing. Rakha.ai may
have its own equivalent quirk (different param name, different response
shape for reasoning models, different rate-limit behavior). Test with a
single call first, read the raw error if one occurs, and check Rakha's docs
for anything named "reasoning," "thinking," or "verbosity" before assuming
a bug on your end.

---

## 5. Decide the model allocation strategy

Given the credits situation, decide explicitly (don't let this happen by
accident):

**Option A — Fully switch**: Rakha.ai handles compression, answer
generation, AND judging. Simplest, but reintroduces the same-model-judging-
itself bias problem already fixed for Groq (`JUDGE_MODEL` dead-env-var bug)
— don't repeat that mistake here.

**Option B — Mixed**: Rakha.ai (sponsor credits) handles compression and
answer generation (the bulk of your token volume, where sponsor credits
help most), while Groq's `openai/gpt-oss-120b` stays as the independent
judge, preserving the bias mitigation already built.

Recommend Option B — it uses the sponsor credits where they matter most
(the volume calls) while keeping the one piece of quality-safety work
(independent judging) you already fixed. This also means you don't have to
re-verify judge behavior against a brand-new, less-tested provider under
time pressure.

---

## 6. Wire into call sites

Wherever `gemini_compress`/`grok_compress` is currently passed as
`llm_call_fn`, swap the import:

```python
from semantic_relevance_engine.rakha_client import rakha_compress as llm_call_fn
```

Applies to:
- `optimize_chunks(..., llm_call_fn=...)` calls in `measure_token_savings.py`
- `answer_quality.py`'s `generate_answers()` — for baseline/optimized
  answer generation (per Option B, NOT for `run_llm_judge`, which should
  keep using the independent Groq judge model)

---

## 7. Re-run everything that touched the network before

Provider swaps have broken things twice already in this project (Gemini's
prompt-commentary expansion bug, Groq's reasoning-token burn). Do not
assume Rakha.ai is clean:

1. Re-run the expansion-bug check (Scenarios where compression runs on
   low-relevance filler) — confirm Rakha's model doesn't add commentary
   instead of compressing, same failure mode as the Gemini bug.
2. Re-run `measure_token_savings.py` on your existing realistic scenarios
   (6, 7, 8, A, B, C) and compare quality scores against the Groq baseline
   numbers already recorded — this tells you whether Rakha.ai's model
   quality is comparable, better, or worse for this specific task.
3. Update `routing.py`'s `LLM_INPUT_COST_PER_TOKEN` constant if Rakha's
   pricing differs from Groq's — check whether sponsor credits change this
   calculation at all (if compression is free via credits, your routing
   economics change substantially — SKIP/LIGHT/FULL thresholds may need
   rethinking if the optimizer's own cost is effectively zero).
4. Re-run the full pytest suite to confirm no import breakage.

---

## 8. Update `.env`

```dotenv
RAKHA_API_KEY=...
RAKHA_MODEL=...
GROQ_API_KEY=...            # keep -- still used for independent judge
JUDGE_MODEL=openai/gpt-oss-120b   # keep the fix already applied
```

---

## 9. Mention the sponsor integration in your pitch

Since Rakha.ai is a hackathon sponsor providing credits, this is worth a
one-line callout in your demo/pitch deck — sponsors generally want to see
their product used, and "we integrated Rakha.ai for our compression layer"
is a small, easy addition to your presentation that costs nothing and may
matter for judging criteria at sponsor-backed hackathons.

---

## Checklist

- [ ] Confirmed base URL, API key env var, model name, and any param
      quirks directly from Rakha.ai's docs (not guessed)
- [ ] `rakha_client.py` built in `semantic_relevance_engine/`
- [ ] Live smoke test passes with real network evidence
- [ ] Model allocation decided (recommend Option B: Rakha for volume,
      Groq for independent judge)
- [ ] Expansion-bug and reasoning-token-burn checks re-run against Rakha's
      model specifically
- [ ] Existing realistic scenarios (6, 7, 8, A, B, C) re-run and compared
      against recorded Groq baseline scores
- [ ] `routing.py` cost constants updated if pricing/credit structure
      changes the economics
- [ ] Full pytest suite re-run, no regressions
- [ ] `.env` updated and confirmed to actually be read (learn from the
      `JUDGE_MODEL` dead-env-var bug — grep for hardcoded strings before
      declaring this done)
