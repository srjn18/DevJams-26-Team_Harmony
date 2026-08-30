"""
Single source of truth for which LLM provider is active.

This exists specifically to prevent the class of bug already hit once in
this project: an env var (JUDGE_MODEL) set in .env but never actually read
anywhere, silently having zero effect. Instead of `answer_quality.py`,
`measure_token_savings.py`, and `new_scenarios.py` each independently
reading os.environ["LLM_PROVIDER"] and branching (three places to get it
wrong, or for one to forget), they all import from HERE. There is exactly
ONE place that reads the env var.
"""

import os

from semantic_relevance_engine.grok_client import (
    grok_compress, grok_answer, get_token_usage as grok_usage,
    reset_token_usage as grok_reset,
)
from semantic_relevance_engine.rakha_client import (
    rakha_compress, rakha_answer, get_token_usage as rakha_usage,
    reset_token_usage as rakha_reset,
)

_VALID_PROVIDERS = {"groq", "rakha"}


def get_active_provider() -> str:
    """The ONE place LLM_PROVIDER is read. Everything else calls this."""
    provider = os.environ.get("LLM_PROVIDER", "groq").lower()
    if provider not in _VALID_PROVIDERS:
        raise ValueError(
            f"LLM_PROVIDER={provider!r} is not valid. "
            f"Must be one of {_VALID_PROVIDERS}. Check your .env."
        )
    return provider


def get_compress_fn():
    """Returns the compression function for whichever provider is active."""
    provider = get_active_provider()
    return rakha_compress if provider == "rakha" else grok_compress


def get_answer_fn():
    """Returns the answer-generation function for whichever provider is active."""
    provider = get_active_provider()
    return rakha_answer if provider == "rakha" else grok_answer


def get_usage_fns():
    """Returns (get_usage, reset_usage) for whichever provider is active."""
    provider = get_active_provider()
    if provider == "rakha":
        return rakha_usage, rakha_reset
    return grok_usage, grok_reset


# The judge is DELIBERATELY not routed through get_active_provider() --
# it always uses Groq, regardless of LLM_PROVIDER, to preserve the
# independent-judge bias mitigation. Import grok_answer directly wherever
# the judge is implemented; do not add a "rakha judge" path without a
# specific reason to abandon that mitigation.


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    provider = get_active_provider()
    print(f"Active LLM_PROVIDER: {provider}")
    compress_fn = get_compress_fn()
    answer_fn = get_answer_fn()
    print(f"compress_fn resolves to: {compress_fn.__module__}.{compress_fn.__name__}")
    print(f"answer_fn resolves to:   {answer_fn.__module__}.{answer_fn.__name__}")
    print("\nRunning a real call to confirm the resolved function actually works...")
    result = compress_fn("Rewrite concisely: The weather today is sunny with a high of 75 degrees.")
    print(f"Result: {result}")
