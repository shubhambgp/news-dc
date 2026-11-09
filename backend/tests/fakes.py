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
