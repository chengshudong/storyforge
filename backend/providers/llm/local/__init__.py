from __future__ import annotations

import time

from interfaces.llm import LLMProvider, ModelResponse


class LocalAdapter(LLMProvider):
    """Local model adapter. Returns stub responses when no cloud provider is available."""

    def __init__(self) -> None:
        self._healthy = True

    async def generate(self, prompt: str, model: str, **kwargs) -> ModelResponse:
        return ModelResponse(
            text="",
            model=model,
            provider="local",
            metadata={"degraded": True},
        )

    async def stream(self, prompt: str, model: str, **kwargs):
        yield ""
        return

    async def embedding(self, texts: list[str], model: str) -> list[list[float]]:
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer(model or "all-MiniLM-L6-v2", local_files_only=True)
        result = embedder.encode(texts, normalize_embeddings=True)
        return result.tolist()

    async def health(self) -> dict:
        start = time.time()
        try:
            from sentence_transformers import SentenceTransformer
            SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
            latency_ms = int((time.time() - start) * 1000)
            return {"status": "healthy", "latency_ms": latency_ms}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)[:200]}
