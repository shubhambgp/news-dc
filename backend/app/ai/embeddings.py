"""Local CPU embeddings with fastembed (no API key). The model must match `items.embedding`'s
dimension; changing it needs a re-embedding migration, not a config change (§11.10).

The model (~70 MB) is downloaded from Hugging Face on first use. Set FASTEMBED_CACHE_PATH to a
persistent directory so it is not downloaded again after every container restart.
"""

import threading
from typing import Any, Protocol

from app.models import EMBEDDING_DIM

MODEL_NAME = "BAAI/bge-small-en-v1.5"


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class FastEmbedder:
    """Lazy-loaded, thread-safe wrapper. Vectors are L2-normalized, so dot = cosine."""

    def __init__(self) -> None:
        self._model: Any = None
        self._lock = threading.Lock()

    def embed(self, text: str) -> list[float]:
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding  # slow import; only when needed

                self._model = TextEmbedding(MODEL_NAME)
            vec = next(iter(self._model.embed([text])))
        if len(vec) != EMBEDDING_DIM:
            raise ValueError(f"{MODEL_NAME} returned {len(vec)} dims, expected {EMBEDDING_DIM}")
        return [float(x) for x in vec]
