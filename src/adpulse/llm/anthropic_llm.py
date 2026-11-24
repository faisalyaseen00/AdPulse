"""Claude via the official Anthropic SDK (structured outputs + prompt caching)."""
from __future__ import annotations

import anthropic

from ..config import Settings
from .base import LLMError, T, Usage


class ClaudeLLM:
    def __init__(self, settings: Settings):
        if not settings.anthropic_api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set")
        # base_url is explicit so an unrelated ANTHROPIC_BASE_URL in the shell is not picked up.
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key,
                                          base_url=settings.anthropic_base_url, max_retries=3, timeout=180)
        self.model = settings.anthropic_model
        self.effort = settings.anthropic_effort
        self.fallbacks = settings.anthropic_fallbacks
        self.name = f"anthropic:{self.model}"
        self.usage = Usage()

    def structured(self, *, system: str, user: str, schema: type[T], step: str, max_tokens: int = 8000) -> T:
        extra: dict = {}
        if self.fallbacks:
            # Server-side refusal fallback: if the primary model declines, the API re-runs on a fallback.
            extra = {"extra_headers": {"anthropic-beta": "server-side-fallback-2026-07-01"},
                     "extra_body": {"fallbacks": "default"}}
        try:
            resp = self.client.messages.parse(
                model=self.model,
                max_tokens=max_tokens,
                # The system prompt (schema + metric definitions) is large and identical across calls: cache it.
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                output_config={"effort": self.effort},
                output_format=schema,
                **extra,
            )
        except anthropic.RateLimitError as e:
            raise LLMError(f"Claude rate limit: {e}") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(f"Cannot reach Claude API: {e}") from e

        u = resp.usage
        self.usage.add(step, u.input_tokens, u.output_tokens, getattr(u, "cache_read_input_tokens", 0) or 0)
        if resp.stop_reason == "refusal":
            raise LLMError("The model declined this request.")
        if resp.stop_reason == "max_tokens":
            raise LLMError(f"Response truncated at max_tokens={max_tokens} during '{step}'.")
        if resp.parsed_output is None:
            raise LLMError(f"No structured output returned during '{step}'.")
        return resp.parsed_output
