"""
Rakha.ai client wrapper — uses Rakha.ai via the OpenAI-compatible API.

Public API:
  rakha_compress(prompt: str) -> str
  rakha_answer(prompt: str) -> str
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

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("RAKHA_API_KEY")
        if not api_key:
            raise ValueError(
                "RAKHA_API_KEY is not set. Add it to your .env file."
            )
        base_url = os.getenv("RAKHA_BASE_URL", "https://api.reka.ai/v1")
        _client = OpenAI(
            api_key=api_key,
            base_url=base_url,
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


def rakha_compress(prompt: str) -> str:
    """
    Compress a prompt chunk using Rakha.ai.
    """
    client = _get_client()
    model  = os.getenv("RAKHA_MODEL", "reka-edge-2603")
    
    try:
        temp = float(os.getenv("LLM_TEMPERATURE", "0"))
    except ValueError:
        temp = 0.0

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=750,   # cap per call to conserve quota
                temperature=temp,
            )
            break
        except (RateLimitError, APIConnectionError) as e:
            if attempt == max_retries - 1:
                raise
            print(f"[rakha_client] Network/RateLimit error: {e}. Retrying in 16s...")
            time.sleep(16)
        except BadRequestError:
            raise
        except APIStatusError as e:
            if e.status_code == 413:
                print("[rakha_client] 413 Request Entity Too Large. Returning empty.")
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


def rakha_answer(prompt: str) -> str:
    """
    Generate an answer using Rakha.ai.
    """
    client = _get_client()
    model  = os.getenv("RAKHA_MODEL", "reka-edge-2603")

    try:
        temp = float(os.getenv("LLM_TEMPERATURE", "0"))
    except ValueError:
        temp = 0.0

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=temp,
            )
            break
        except (RateLimitError, APIConnectionError) as e:
            if attempt == max_retries - 1:
                raise
            print(f"[rakha_client] Network/RateLimit error: {e}. Retrying in 16s...")
            time.sleep(16)
        except BadRequestError:
            raise
        except APIStatusError as e:
            if e.status_code == 413:
                print("[rakha_client] 413 Request Entity Too Large in answer generation.")
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
