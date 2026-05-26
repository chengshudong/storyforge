import asyncio

import pytest

from agents.novel_agent import NovelAgent


class MockParser:
    async def parse(self, file_path, file_format):
        return type("ParsedDocument", (), {
            "title": "Test Novel",
            "full_text": "chapter one text content",
            "metadata": {"char_count": 25, "format": file_format},
        })

    async def split(self, text, chunk_size=512, chunk_overlap=50):
        return [{"index": 0, "text": text}]

    async def extract(self, text):
        return {"persons": ["hero"], "locations": ["mountain"], "key_terms": []}


class MockContextStore:
    async def embed(self, chunks, model="all-MiniLM-L6-v2"):
        return [[0.1] * 384 for _ in chunks]

    async def search(self, query, top_k=10):
        return [{"id": "1", "score": 0.9}]

    async def delete(self, document_id):
        return True


class MockVectorStore:
    def __init__(self):
        self.upserted = []

    async def upsert(self, collection, points):
        self.upserted.append({"collection": collection, "count": len(points)})
        return True

    async def query(self, collection, vector, top_k=10):
        return [{"id": "1", "score": 0.9}]

    async def delete(self, collection, point_ids):
        return True


@pytest.fixture
def agent():
    return NovelAgent(MockParser(), MockContextStore(), MockVectorStore())


def test_process_returns_expected_keys(agent):
    result = asyncio.run(agent.process("test.txt", "txt", "proj-001"))
    assert result["title"] == "Test Novel"
    assert result["char_count"] == 25
    assert result["chunk_count"] == 1
    assert result["collection"] == "novel_proj-001"
    assert "entities" in result
    assert "chunk_ids" in result
    assert len(result["chunk_ids"]) == 1


def test_process_stores_vectors(agent):
    result = asyncio.run(agent.process("test.txt", "txt", "proj-002"))
    assert len(agent._vector_store.upserted) == 1
    assert agent._vector_store.upserted[0]["collection"] == "novel_proj-002"
    assert agent._vector_store.upserted[0]["count"] == 1


def test_process_entities_passed_through(agent):
    result = asyncio.run(agent.process("test.txt", "txt", "proj-003"))
    assert result["entities"]["persons"] == ["hero"]
    assert result["entities"]["locations"] == ["mountain"]
