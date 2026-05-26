from __future__ import annotations

import uuid

from interfaces.parser import NovelParser
from interfaces.context import ContextStore
from interfaces.vector import VectorStore


class NovelAgent:
    """Orchestrates the novel processing pipeline by wiring adapters together."""

    def __init__(
        self,
        parser: NovelParser,
        context_store: ContextStore,
        vector_store: VectorStore,
    ) -> None:
        self._parser = parser
        self._context_store = context_store
        self._vector_store = vector_store

    async def process(self, file_path: str, file_format: str, project_id: str) -> dict:
        """Run the full parse -> split -> extract -> embed -> store pipeline."""
        doc = await self._parser.parse(file_path, file_format)
        chunks = await self._parser.split(doc.full_text)
        entities = await self._parser.extract(doc.full_text)

        embeddings = await self._context_store.embed(chunks)

        collection = f"novel_{project_id}"
        chunk_ids = [str(uuid.uuid4()) for _ in chunks]
        points = [
            {
                "id": cid,
                "vector": emb,
                "payload": {
                    "text": chunk["text"],
                    "chunk_index": chunk["index"],
                    "document_id": project_id,
                },
            }
            for cid, emb, chunk in zip(chunk_ids, embeddings, chunks)
        ]
        await self._vector_store.upsert(collection, points)

        return {
            "title": doc.title,
            "char_count": doc.metadata.get("char_count", 0),
            "chunk_count": len(chunks),
            "chunk_ids": chunk_ids,
            "entities": entities,
            "collection": collection,
        }
