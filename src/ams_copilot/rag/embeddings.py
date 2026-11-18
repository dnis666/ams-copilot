import hashlib
import re
from typing import Protocol

import httpx
import numpy as np

from ams_copilot.config import Settings
from ams_copilot.guardrails import mask_pii
from ams_copilot.llm.heuristics import normalize

STOPWORDS = {
    "a",
    "o",
    "os",
    "as",
    "de",
    "da",
    "do",
    "das",
    "dos",
    "e",
    "em",
    "no",
    "na",
    "nos",
    "nas",
    "um",
    "uma",
    "para",
    "por",
    "com",
    "que",
    "se",
    "ao",
    "aos",
    "ou",
    "nao",
    "esta",
    "estao",
    "foi",
    "ser",
    "sao",
    "ja",
    "mais",
    "muito",
    "quando",
    "ele",
    "ela",
    "isso",
    "este",
    "esse",
    "the",
    "of",
    "to",
    "and",
    "is",
    "in",
}


class Embedder(Protocol):
    dimensions: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


class HashingEmbedder:
    def __init__(self, dimensions: int = 512) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dimensions), dtype=np.float32)
        for row, text in enumerate(texts):
            tokens = [token for token in re.findall(r"[a-z0-9_/\-]+", normalize(text)) if token not in STOPWORDS]
            features = [(token, 1.0) for token in tokens]
            features += [(f"{left} {right}", 0.5) for left, right in zip(tokens, tokens[1:], strict=False)]
            for feature, weight in features:
                digest = int(hashlib.blake2b(feature.encode(), digest_size=8).hexdigest(), 16)
                sign = 1.0 if digest >> 63 else -1.0
                matrix[row, digest % self.dimensions] += sign * weight
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms


class OpenAICompatibleEmbedder:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._http = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=60, transport=transport)

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimensions), dtype=np.float32)
        response = self._http.post(
            "/embeddings",
            json={"model": self.model, "input": [mask_pii(text)[0] for text in texts], "dimensions": self.dimensions},
        )
        response.raise_for_status()
        rows = sorted(response.json()["data"], key=lambda item: item["index"])
        matrix = np.array([row["embedding"] for row in rows], dtype=np.float32)
        if [row["index"] for row in rows] != list(range(len(texts))):
            raise ValueError("índices de embeddings inválidos")
        if matrix.shape != (len(texts), self.dimensions) or not np.isfinite(matrix).all():
            raise ValueError("dimensões ou valores de embeddings inválidos")
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if (norms == 0).any():
            raise ValueError("embedding vazio")
        return matrix / norms

    def close(self) -> None:
        self._http.close()


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedding_provider == "hashing":
        return HashingEmbedder(settings.embedding_dimensions)
    if settings.embedding_provider in {"openai", "openai_compatible", "ollama"}:
        return OpenAICompatibleEmbedder(
            settings.embedding_base_url,
            settings.embedding_api_key,
            settings.embedding_model,
            settings.embedding_dimensions,
        )
    raise ValueError(f"provedor de embeddings desconhecido: {settings.embedding_provider}")
