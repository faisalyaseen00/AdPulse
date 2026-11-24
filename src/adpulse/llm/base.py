"""Provider-neutral LLM interface: every call returns a validated Pydantic object."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Raised when the model refuses, truncates, or returns unparseable output."""


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    log: list[dict] = field(default_factory=list)

    def add(self, step: str, inp: int, out: int, cache_read: int = 0) -> None:
        self.calls += 1
        self.input_tokens += inp
        self.output_tokens += out
        self.cache_read_tokens += cache_read
        self.log.append({"step": step, "input": inp, "output": out, "cache_read": cache_read})


class LLM(Protocol):
    name: str
    usage: Usage

    def structured(self, *, system: str, user: str, schema: type[T], step: str,
                   max_tokens: int = 8000) -> T: ...
