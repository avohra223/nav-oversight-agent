"""Single wrapper around the Anthropic SDK.

Provides:
  - shared client (lazily constructed)
  - retry logic for 429 / 5xx
  - token accounting (returned alongside response)
  - clear error if ANTHROPIC_API_KEY isn't set

All agent-side API calls go through `call_messages`. Nothing else in the
agent module should import `anthropic` directly.
"""
from __future__ import annotations

import os
import time
from typing import Any

import anthropic
from anthropic import Anthropic, APIStatusError, APIConnectionError, APITimeoutError

from .schemas import TokenUsage


_DEFAULT_MAX_RETRIES = 5
_INITIAL_BACKOFF_SECONDS = 1.5

_client: Anthropic | None = None


def get_client() -> Anthropic:
    """Return the shared Anthropic client. Lazily constructed."""
    global _client
    if _client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Export it in your shell before "
                "running the agent."
            )
        _client = Anthropic()
    return _client


def call_messages(
    *,
    model: str,
    system: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    max_tokens: int = 8192,
    temperature: float | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
) -> tuple[Any, TokenUsage]:
    """Call messages.create with retry on transient failures.

    Returns the raw response object plus a TokenUsage extracted from it.
    Raises after max_retries exhausted on 429/5xx; raises immediately on 4xx.
    """
    client = get_client()
    backoff = _INITIAL_BACKOFF_SECONDS
    last_err: Exception | None = None

    for attempt in range(max_retries):
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "tools": tools,
                "messages": messages,
            }
            if temperature is not None:
                kwargs["temperature"] = temperature
            response = client.messages.create(**kwargs)

            usage = TokenUsage(
                input_tokens=getattr(response.usage, "input_tokens", 0) or 0,
                output_tokens=getattr(response.usage, "output_tokens", 0) or 0,
                cache_creation_input_tokens=getattr(
                    response.usage, "cache_creation_input_tokens", 0
                ) or 0,
                cache_read_input_tokens=getattr(
                    response.usage, "cache_read_input_tokens", 0
                ) or 0,
            )
            return response, usage

        except APIStatusError as e:
            last_err = e
            transient = e.status_code in (408, 425, 429, 500, 502, 503, 504)
            if not transient:
                raise
            time.sleep(backoff)
            backoff *= 2
        except (APIConnectionError, APITimeoutError) as e:
            last_err = e
            time.sleep(backoff)
            backoff *= 2

    raise RuntimeError(
        f"call_messages exhausted {max_retries} retries; last error: {last_err}"
    )
