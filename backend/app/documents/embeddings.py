"""Optional OpenAI embeddings; no vector or network access without explicit consent."""

import time
from typing import Protocol

import httpx
import numpy as np

from app.agent.security import redact
from app.core.config import settings
from app.core.errors import AppError


class Embedder(Protocol):
    def embed(self, texts: list[str], timeout: float = 12) -> tuple[list[list[float]], dict]: ...


class OpenAIEmbedder:
    def embed(self, texts, timeout=12):
        config = settings()
        if not config.openai_api_key:
            raise AppError(
                "EMBEDDINGS_NOT_CONFIGURED",
                "Embedding provider not configured; keyword retrieval remains available.",
                503,
            )
        if not texts or len(texts) > 64 or any(not t.strip() or len(t) > 4000 for t in texts):
            raise AppError(
                "EMBEDDING_INPUT", "Embedding batches require at most 64 nonempty bounded passages."
            )
        started = time.monotonic()
        for attempt in range(2):
            try:
                with httpx.Client(
                    timeout=max(
                        0.1, min(timeout - (time.monotonic() - started), config.llm_timeout_seconds)
                    ),
                    follow_redirects=False,
                ) as client:
                    response = client.post(
                        "https://api.openai.com/v1/embeddings",
                        headers={"Authorization": f"Bearer {config.openai_api_key}"},
                        json={
                            "model": config.embedding_model,
                            "input": [redact(t) for t in texts],
                            "dimensions": 256,
                            "encoding_format": "float",
                        },
                    )
                if response.status_code in (408, 429, 500, 502, 503, 504) and attempt == 0:
                    continue
                if response.status_code != 200:
                    raise AppError(
                        "EMBEDDING_PROVIDER_ERROR",
                        "Embedding provider could not index/search this evidence.",
                        502,
                    )
                payload = response.json()
                ordered = sorted(payload["data"], key=lambda row: row["index"])
                if [row["index"] for row in ordered] != list(range(len(texts))):
                    raise ValueError("Mismatched embedding indices")
                matrix = np.asarray([row["embedding"] for row in ordered], dtype=float)
                if (
                    matrix.shape != (len(texts), 256)
                    or not np.isfinite(matrix).all()
                    or (np.linalg.norm(matrix, axis=1) == 0).any()
                ):
                    raise ValueError("Invalid embedding vectors")
                return matrix.tolist(), {
                    "model": config.embedding_model,
                    "dimensions": 256,
                    "input_tokens": payload.get("usage", {}).get("prompt_tokens"),
                    "estimated_cost_usd": None,
                }
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == 0:
                    continue
                raise AppError(
                    "EMBEDDING_TIMEOUT",
                    "Embedding provider timed out after one bounded retry.",
                    504,
                ) from None
            except (ValueError, KeyError, TypeError):
                raise AppError(
                    "EMBEDDING_SCHEMA",
                    "Embedding response failed finite-dimension/index checks.",
                    502,
                ) from None
        raise AppError("EMBEDDING_PROVIDER_ERROR", "Embedding provider unavailable.", 502)


def configured_embedder():
    return OpenAIEmbedder()
