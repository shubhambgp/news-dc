"""Test doubles for the LLM and the embedder (no network, no cost)."""

import hashlib
import json
import math
import threading
from collections.abc import Callable
from typing import Any

from app.ai.llm import LLMResponse
from app.models import EMBEDDING_DIM


def answer(**overrides: Any) -> dict[str, Any]:
    """A valid classifier answer: relevant, good quality."""
    base: dict[str, Any] = {
        "is_relevant": True,
        "is_spam": False,
        "relevance_score": 90,
        "quality_score": 70,
        "primary_category": "cooling",
        "categories": ["cooling", "sustainability"],
        "content_type": "news",
        "summary": "An operator deployed liquid cooling.",
        "key_insights": [{"type": "technical", "text": "Liquid cooling was deployed."}],
        "entities": {"companies": ["Acme"], "technologies": ["liquid cooling"], "locations": []},
        "tags": ["Liquid Cooling", "pue"],
        "reject_reason": "",
    }
    return base | overrides


Reply = dict[str, Any] | str | LLMResponse | Exception


class FakeLLM:
    """`replies(user_message, call_number)` returns a dict (sent as JSON), raw text, a full
    LLMResponse, or an exception to raise."""

    model = "fake-model"

    def __init__(self, replies: Callable[[str, int], Reply] | None = None) -> None:
        self.replies = replies or (lambda user, n: answer())
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def complete_json(
        self, *, system: str, user: str, schema: dict[str, Any], max_tokens: int
    ) -> LLMResponse:
        with self._lock:
            self.calls.append(user)
            n = len(self.calls)
        out = self.replies(user, n)
        if isinstance(out, Exception):
            raise out
        if isinstance(out, LLMResponse):
            return out
        text = out if isinstance(out, str) else json.dumps(out)
        return LLMResponse(text, self.model, "end_turn", 1000, 200, 0, 0, 5)


class FakeEmbedder:
    """Same text -> same unit vector; different texts -> nearly orthogonal vectors."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def embed(self, text: str) -> list[float]:
        if self.fail:
            raise RuntimeError("embedding model unavailable")
        seed = hashlib.sha256(text.encode()).digest()
        raw = [math.sin(seed[i % 32] * (i + 1)) for i in range(EMBEDDING_DIM)]
        norm = math.sqrt(sum(x * x for x in raw))
        return [x / norm for x in raw]


class FakeChat:
    """Streams `chunks`, then an LLMResponse with `stop_reason`. `error` is raised after
    `error_after` chunks. `closed_early` is True when the consumer closed the stream mid-way."""

    model = "fake-chat"

    def __init__(
        self,
        chunks: tuple[str, ...] = ("Operators are adopting liquid cooling [1].",),
        stop_reason: str = "end_turn",
        error: Exception | None = None,
        error_after: int = 0,
    ) -> None:
        self.chunks, self.stop_reason = chunks, stop_reason
        self.error, self.error_after = error, error_after
        self.calls: list[dict[str, Any]] = []
        self.closed_early = False

    def stream_text(self, *, system: str, messages: list[Any], max_tokens: int):
        self.calls.append({"system": system, "messages": messages, "max_tokens": max_tokens})
        try:
            for i, chunk in enumerate(self.chunks):
                if self.error and i == self.error_after:
                    raise self.error
                yield chunk
            if self.error:
                raise self.error
            text = "".join(self.chunks)
            yield LLMResponse(text, self.model, self.stop_reason, 900, 120, 0, 0, 5)
        except GeneratorExit:
            self.closed_early = True
            raise
