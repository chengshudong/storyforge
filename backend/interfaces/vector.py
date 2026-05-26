from abc import ABC, abstractmethod


class VectorStore(ABC):
    @abstractmethod
    async def upsert(self, collection: str, points: list[dict]) -> bool:
        """Insert/update vector points."""

    @abstractmethod
    async def query(self, collection: str, vector: list[float], top_k: int = 10) -> list[dict]:
        """K-nearest-neighbor query."""

    @abstractmethod
    async def delete(self, collection: str, point_ids: list[str]) -> bool:
        """Delete points by ID."""
