"""Token counting and manipulation utilities."""
from typing import Optional

_tiktoken_encoder = None

def _get_encoder():
    global _tiktoken_encoder
    if _tiktoken_encoder is None:
        try:
            import tiktoken
            _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _tiktoken_encoder = False
    return _tiktoken_encoder if _tiktoken_encoder is not False else None


def count_tokens(text: str) -> int:
    """Accurately count tokens in text using tiktoken or deterministic fallback."""
    if not text:
        return 0
    enc = _get_encoder()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    # Deterministic fallback tokenizer approximating BPE
    # Standard approximation: ~4 characters per token in English or ~0.75 words per token
    words = text.split()
    if not words:
        return 0
    # Approximate 1.3 tokens per whitespace-separated word, min 1 token per 4 chars
    char_estimate = max(1, len(text) // 4)
    word_estimate = int(len(words) * 1.3)
    return max(char_estimate, word_estimate)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to at most max_tokens without breaking coherence if possible."""
    if max_tokens <= 0:
        return ""
    if not text:
        return ""
    if count_tokens(text) <= max_tokens:
        return text

    enc = _get_encoder()
    if enc is not None:
        try:
            tokens = enc.encode(text)
            if len(tokens) <= max_tokens:
                return text
            truncated_tokens = tokens[:max_tokens]
            return enc.decode(truncated_tokens)
        except Exception:
            pass

    # Fallback word-based truncation
    words = text.split()
    target_words = int(max_tokens / 1.3)
    if target_words <= 0:
        target_words = max(1, max_tokens)
    return " ".join(words[:target_words])
