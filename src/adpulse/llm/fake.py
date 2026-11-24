"""Scripted LLM for tests and offline demos: a function decides each structured reply."""
from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from .base import T, Usage

Responder = Callable[[str, str, type[BaseModel]], BaseModel]


class ScriptedLLM:
    def __init__(self, responder: Responder, name: str = "scripted"):
        self.responder = responder
        self.name = name
        self.usage = Usage()
        self.calls: list[tuple[str, str]] = []

    def structured(self, *, system: str, user: str, schema: type[T], step: str, max_tokens: int = 8000) -> T:
        self.calls.append((step, user))
        self.usage.add(step, 0, 0)
        out = self.responder(step, user, schema)
        assert isinstance(out, schema), f"responder returned {type(out).__name__}, expected {schema.__name__}"
        return out
