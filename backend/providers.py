import os
import time
from typing import Tuple


class BaseProvider:
    def compress(self, query: str, context: str, token_budget: int) -> Tuple[str, int]:
        raise NotImplementedError()

    def answer(self, query: str, context: str) -> Tuple[str, float]:
        raise NotImplementedError()


class MockProvider(BaseProvider):
    """Deterministic mock provider: compression truncates context predictably and returns counts."""
    def compress(self, query: str, context: str, token_budget: int):
        # crude token estimate: 1 token ~= 4 chars
        original_tokens = max(1, len(context) // 4)
        # simple truncation strategy: keep first N characters proportional to budget
        keep_tokens = min(original_tokens, token_budget)
        keep_chars = keep_tokens * 4
        compressed = context[:keep_chars]
        # ensure deterministic marker
        compressed = f"[MOCK-COMPRESSED tokens={keep_tokens}]\n" + compressed
        return compressed, keep_tokens

    def answer(self, query: str, context: str):
        start = time.time()
        # deterministic canned answer
        answer_text = f"Mock answer for query: {query} — context_len={len(context)}"
        latency = (time.time() - start) * 1000.0
        return answer_text, latency


class RealProvider(BaseProvider):
    """Placeholder for a production provider; attempts a network call if configured."""
    def __init__(self, provider_name: str, api_key: str):
        self.provider_name = provider_name
        self.api_key = api_key

    def compress(self, query: str, context: str, token_budget: int):
        # For safety in the demo, fallback to a mock-like behavior.
        # Real implementation would call the provider's compression API.
        compressed = f"[REAL-{self.provider_name}-MOCK-COMPRESSED tokens={min(len(context)//4, token_budget)}]\n" + context[:token_budget*4]
        tokens = min(len(context)//4, token_budget)
        return compressed, tokens

    def answer(self, query: str, context: str):
        # Real implementation would call the provider; keep deterministic fallback.
        return f"[REAL-{self.provider_name}-MOCK-ANSWER] Query: {query}", 12.3


def get_provider():
    provider_name = os.environ.get("LLM_PROVIDER", "mock").lower()
    api_key = os.environ.get("LLM_API_KEY")

    if provider_name == "mock" or not api_key:
        return MockProvider()

    try:
        return RealProvider(provider_name, api_key)
    except Exception:
        return MockProvider()
