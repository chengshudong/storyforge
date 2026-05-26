import asyncio

import pytest

from providers.context.llamaindex_adapter import LlamaIndexAdapter


class MockVectorStore:
    def __init__(self):
        self.points = []
        self.queries = []
        self.deletes = []

    async def upsert(self, collection, points):
        self.points.extend(points)
        return True

    async def query(self, collection, vector, top_k=10):
        self.queries.append({"collection": collection, "top_k": top_k})
        return [{"id": "mock-1", "score": 0.95, "text": "mock result"}]

    async def delete(self, collection, point_ids):
        self.deletes.append({"collection": collection, "point_ids": point_ids})
        return True


@pytest.fixture
def adapter():
    return LlamaIndexAdapter(MockVectorStore())


def test_embed_returns_correct_dimensions(adapter):
    chunks = [
        {"index": 0, "text": "chapter one: the beginning"},
        {"index": 1, "text": "chapter two: the journey"},
    ]
    embeddings = asyncio.run(adapter.embed(chunks))
    assert len(embeddings) == 2
    assert len(embeddings[0]) == 384


def test_embed_single_chunk(adapter):
    chunks = [{"index": 0, "text": "a single line of text"}]
    embeddings = asyncio.run(adapter.embed(chunks))
    assert len(embeddings) == 1
    assert len(embeddings[0]) == 384


def test_search_delegates_to_vector_store(adapter):
    results = asyncio.run(adapter.search("test query", top_k=5))
    assert len(results) == 1
    assert results[0]["id"] == "mock-1"
    assert results[0]["score"] == 0.95
    assert len(adapter._vector_store.queries) == 1
    assert adapter._vector_store.queries[0]["top_k"] == 5


def test_delete_delegates_to_vector_store(adapter):
    ok = asyncio.run(adapter.delete("doc-123"))
    assert ok is True
    assert len(adapter._vector_store.deletes) == 1
    assert adapter._vector_store.deletes[0]["point_ids"] == ["doc-123"]
