"""
LLM client wrapper — uses Groq (groq.com) via the OpenAI-compatible API.

Public API:
  grok_compress(prompt: str) -> str
  grok_answer(prompt: str) -> str
  get_token_usage() -> dict
  reset_token_usage()
"""
import os
import time
import contextvars
from openai import OpenAI, RateLimitError, APIConnectionError, APIStatusError, BadRequestError

# Context-var token counters (concurrent/thread-safe)
prompt_tokens_var     = contextvars.ContextVar("prompt_tokens",     default=0)
candidates_tokens_var = contextvars.ContextVar("candidates_tokens", default=0)

_client: OpenAI | None = None

# Models that produce hidden <think> tokens by default on Groq.
# Passing reasoning_format='hidden' suppresses thinking output so max_tokens
# applies only to the answer, not to the chain-of-thought.  Without this,
# a simple compress call can take 2+ minutes and burn quota invisibly.
_REASONING_MODEL_PREFIXES = ("qwen/", "openai/gpt-oss", "deepseek")

def _is_reasoning_model(model: str) -> bool:
    return any(model.startswith(p) for p in _REASONING_MODEL_PREFIXES)

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY") or os.getenv("XAI_API_KEY")
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is not set. Add it to your .env file."
            )
        _client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )
    return _client


def reset_token_usage() -> None:
    """Reset token tracking in the current execution context."""
    prompt_tokens_var.set(0)
    candidates_tokens_var.set(0)


def get_token_usage() -> dict:
    """Return token usage accumulated in the current execution context."""
    return {
        "prompt_tokens":     prompt_tokens_var.get(),
        "candidates_tokens": candidates_tokens_var.get(),
    }


def grok_compress(prompt: str) -> str:
    """
    Compress a prompt chunk using the configured LLM.
    """
    client = _get_client()
    model  = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")

    # Suppress chain-of-thought tokens for reasoning models so that
    # max_tokens applies only to the actual answer.
    # NOTE: reasoning_format must go in extra_body, NOT as a direct kwarg;
    # the OpenAI SDK rejects unknown direct kwargs with TypeError.
    extra_body = {"reasoning_format": "hidden"} if _is_reasoning_model(model) else None

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=750,   # cap per call to conserve quota
                extra_body=extra_body,
            )
            break
        except (RateLimitError, APIConnectionError) as e:
            if attempt == max_retries - 1:
                raise
            print(f"[grok_client] Network/RateLimit error: {e}. Retrying in 16s...")
            time.sleep(16)
        except BadRequestError:
            # 400 errors (e.g. unsupported parameter) — do not retry, propagate immediately.
            raise
        except APIStatusError as e:
            if e.status_code == 413:
                print("[grok_client] 413 Request Entity Too Large. Returning empty.")
                return ""
            raise

    usage = response.usage
    if usage:
        prompt_tokens_var.set(
            prompt_tokens_var.get() + (usage.prompt_tokens or 0)
        )
        candidates_tokens_var.set(
            candidates_tokens_var.get() + (usage.completion_tokens or 0)
        )

    content = response.choices[0].message.content or ""
    return content


def grok_answer(prompt: str) -> str:
    """
    Generate an answer using the configured LLM (for answering queries and judging).
    """
    client = _get_client()
    model  = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")

    # Suppress chain-of-thought tokens for reasoning models.
    # NOTE: reasoning_format must go in extra_body, NOT as a direct kwarg.
    extra_body = {"reasoning_format": "hidden"} if _is_reasoning_model(model) else None

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                extra_body=extra_body,
            )
            break
        except (RateLimitError, APIConnectionError) as e:
            if attempt == max_retries - 1:
                raise
            print(f"[grok_client] Network/RateLimit error: {e}. Retrying in 16s...")
            time.sleep(16)
        except BadRequestError:
            # 400 errors — do not retry, propagate immediately.
            raise
        except APIStatusError as e:
            if e.status_code == 413:
                print("[grok_client] 413 Request Entity Too Large in answer generation.")
                return "ERROR: 413 Request Entity Too Large"
            raise

    usage = response.usage
    if usage:
        prompt_tokens_var.set(
            prompt_tokens_var.get() + (usage.prompt_tokens or 0)
        )
        candidates_tokens_var.set(
            candidates_tokens_var.get() + (usage.completion_tokens or 0)
        )

    content = response.choices[0].message.content or ""
    return content


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    print("=== Grok Client Smoke Test ===")
    test_text = (
        "HTTP 401 Unauthorized client status error. "
        "We are currently using Postgres for our user records, but we decided to "
        "migrate off Postgres to DynamoDB next quarter. The timeout is strictly 30 seconds."
    )
    prompt = (
        f"Compress this context while keeping critical info "
        f"(HTTP 401, DynamoDB migration, Postgres, 30 seconds):\n{test_text}"
    )
    print(f"Input : {test_text}\n")
    try:
        reset_token_usage()
        output = grok_compress(prompt)
        usage  = get_token_usage()
        print(f"Output: {output}\n")
        print(f"Token usage: {usage}")
        print("Smoke test PASSED!")
    except Exception as e:
        print(f"Smoke test FAILED: {e}")
