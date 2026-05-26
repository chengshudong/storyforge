from __future__ import annotations

from qdrant_client import AsyncQdrantClient, models

from infra.config import settings
from interfaces.vector import VectorStore


class QdrantAdapter(VectorStore):
    """Wraps Qdrant to implement the VectorStore interface."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self._host = host or settings.qdrant_host
        self._port = port or settings.qdrant_port
        self._client: AsyncQdrantClient | None = None

    async def _get_client(self) -> AsyncQdrantClient:
        if self._client is None:
            self._client = AsyncQdrantClient(
                host=self._host, port=self._port,
                trust_env=False, check_compatibility=False, timeout=30,
            )
        return self._client

    async def _ensure_collection(self, collection: str, vector_size: int = 384) -> None:
        client = await self._get_client()
        if not await client.collection_exists(collection):
            await client.create_collection(
                collection_name=collection,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )

    async def upsert(self, collection: str, points: list[dict]) -> bool:
        client = await self._get_client()
        await self._ensure_collection(collection)
        qdrant_points = [
            models.PointStruct(
                id=p["id"],
                vector=p["vector"],
                payload=p.get("payload", {}),
            )
            for p in points
        ]
        await client.upsert(collection_name=collection, points=qdrant_points)
        return True

    async def query(self, collection: str, vector: list[float], top_k: int = 10) -> list[dict]:
        client = await self._get_client()
        results = await client.query_points(
            collection_name=collection,
            query=vector,
            limit=top_k,
        )
        return [
            {
                "id": hit.id,
                "score": hit.score,
                **hit.payload,
            }
            for hit in results.points
        ]

    async def delete(self, collection: str, point_ids: list[str]) -> bool:
        client = await self._get_client()
        await client.delete(
            collection_name=collection,
            points_selector=models.PointIdsList(points=point_ids),
        )
        return True
