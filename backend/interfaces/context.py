from abc import ABC, abstractmethod


class ContextStore(ABC):
    @abstractmethod
    async def embed(self, chunks: list[dict], model: str = "all-MiniLM-L6-v2") -> list[list[float]]:
        """Embed text chunks into vectors."""

    @abstractmethod
    async def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Semantic search over stored chunks."""

    @abstractmethod
    async def delete(self, document_id: str) -> bool:
        """Delete all vectors for a document."""
