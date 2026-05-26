from __future__ import annotations

from typing import TYPE_CHECKING

from interfaces.context import ContextStore
from interfaces.vector import VectorStore

if TYPE_CHECKING:
    pass


class LlamaIndexAdapter(ContextStore):
    """Wraps LlamaIndex + SentenceTransformers to implement ContextStore."""

    def __init__(self, vector_store: VectorStore) -> None:
        self._vector_store = vector_store
        self._embedding_model: str | None = None
        self._embedder = None

    async def _get_embedder(self, model: str):
        if self._embedding_model != model or self._embedder is None:
            from sentence_transformers import SentenceTransformer

            try:
                self._embedder = SentenceTransformer(model, local_files_only=True)
            except Exception:
                self._embedder = SentenceTransformer(model)
            self._embedding_model = model
        return self._embedder

    async def embed(self, chunks: list[dict], model: str = "all-MiniLM-L6-v2") -> list[list[float]]:
        embedder = await self._get_embedder(model)
        texts = [chunk["text"] for chunk in chunks]
        embeddings = embedder.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    async def search(self, query: str, top_k: int = 10) -> list[dict]:
        embedder = await self._get_embedder("all-MiniLM-L6-v2")
        query_embedding = embedder.encode([query], normalize_embeddings=True)[0].tolist()
        results = await self._vector_store.query(
            collection="novels",
            vector=query_embedding,
            top_k=top_k,
        )
        return results

    async def delete(self, document_id: str) -> bool:
        return await self._vector_store.delete(collection="novels", point_ids=[document_id])
