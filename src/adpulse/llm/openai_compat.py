"""OpenAI-compatible providers (Groq, OpenRouter) with validated JSON output.

Structured output strategy, most to least strict:
1. ``response_format=json_schema`` (Groq's gpt-oss / kimi models, most OpenRouter models)
2. ``response_format=json_object`` + the JSON schema in the prompt, for models without (1).
The reply is validated against the Pydantic schema. One repair round sends the validation
error back to the model before giving up.
"""
from __future__ import annotations

import json
import re

from openai import APIConnectionError, APIStatusError, BadRequestError, OpenAI, RateLimitError
from pydantic import ValidationError

from .base import LLMError, T, Usage


class OpenAICompatLLM:
    def __init__(self, *, provider: str, api_key: str, base_url: str, model: str,
                 headers: dict | None = None):
        if not api_key:
            raise LLMError(f"{provider.upper()}_API_KEY is not set")
        self.provider = provider
        self.client = OpenAI(api_key=api_key, base_url=base_url, max_retries=4, timeout=180,
                             default_headers=headers or {})
        self.model = model
        self.name = f"{provider}:{model}"
        self.usage = Usage()
        self._schema_mode = True  # flips to json_object mode if the model rejects json_schema

    def structured(self, *, system: str, user: str, schema: type[T], step: str, max_tokens: int = 8000) -> T:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last_err = ""
        for _ in range(2):
            text = self._complete(messages, schema, step, max_tokens)
            try:
                return schema.model_validate_json(_extract_json(text))
            except (ValidationError, ValueError) as e:
                last_err = str(e)[:1500]
                messages += [{"role": "assistant", "content": text},
                             {"role": "user", "content": f"That JSON did not match the schema: {last_err}\n"
                                                         "Reply again with ONLY a corrected JSON object."}]
        raise LLMError(f"Could not parse model output during '{step}': {last_err}")

    def _complete(self, messages: list[dict], schema: type[T], step: str, max_tokens: int) -> str:
        json_schema = schema.model_json_schema()
        for _ in range(2):
            if self._schema_mode:
                fmt = {"type": "json_schema", "json_schema": {"name": schema.__name__, "schema": json_schema,
                                                              "strict": False}}
                msgs = messages
            else:
                fmt = {"type": "json_object"}
                msgs = [{"role": "system", "content": messages[0]["content"] +
                         "\n\nRespond with ONLY a JSON object matching this JSON schema:\n" + json.dumps(json_schema)},
                        *messages[1:]]
            try:
                resp = self.client.chat.completions.create(model=self.model, max_tokens=max_tokens,
                                                           messages=msgs, response_format=fmt)
                break
            except BadRequestError as e:
                if self._schema_mode and _schema_unsupported(e):
                    self._schema_mode = False
                    continue
                raise LLMError(f"{self.provider} rejected the request: {e.message}") from e
            except RateLimitError as e:
                raise LLMError(f"{self.provider} rate limit reached, try again in a minute ({e.message})") from e
            except APIStatusError as e:
                raise LLMError(f"{self.provider} error {e.status_code}: {e.message}") from e
            except APIConnectionError as e:
                raise LLMError(f"Cannot reach {self.provider}: {e}") from e
        if resp.usage:
            self.usage.add(step, resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0)
        choice = resp.choices[0]
        if choice.finish_reason == "length":
            raise LLMError(f"Response truncated during '{step}'.")
        return choice.message.content or ""


def _schema_unsupported(e: BadRequestError) -> bool:
    msg = str(e.message).lower()
    return "json_schema" in msg or "response_format" in msg or "response format" in msg


def _extract_json(text: str) -> str:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in response")
    json.loads(text[start:end + 1])
    return text[start:end + 1]
