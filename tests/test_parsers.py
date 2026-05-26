import tempfile
import os
import asyncio

import pytest

from providers.novel.unstructured_adapter import UnstructuredAdapter


@pytest.fixture
def adapter():
    return UnstructuredAdapter()


def test_parse_txt(adapter):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write("hello world\nthis is a test novel chapter.\n")
        tmp_path = f.name
    try:
        doc = asyncio.run(adapter.parse(tmp_path, "txt"))
        assert doc.full_text == "hello world\nthis is a test novel chapter.\n"
        assert doc.metadata["format"] == "txt"
        assert doc.metadata["char_count"] > 0
        assert doc.metadata["size_bytes"] > 0
    finally:
        os.unlink(tmp_path)


def test_parse_unsupported_format(adapter):
    with pytest.raises(ValueError, match="Unsupported format"):
        asyncio.run(adapter.parse("test.pdf", "pdf"))


def test_split_empty_text(adapter):
    chunks = asyncio.run(adapter.split(""))
    assert len(chunks) == 0


def test_split_short_text(adapter):
    chunks = asyncio.run(adapter.split("short text", chunk_size=512, chunk_overlap=50))
    assert len(chunks) == 1
    assert chunks[0]["index"] == 0
    assert chunks[0]["text"] == "short text"
    assert "char_count" in chunks[0]


def test_extract_persons(adapter):
    text = "张三丰先生在武当山修炼，李四娘在江南小镇开设客栈。"
    entities = asyncio.run(adapter.extract(text))
    assert "persons" in entities
    assert "locations" in entities
    assert "key_terms" in entities
    assert isinstance(entities["persons"], list)
    assert isinstance(entities["locations"], list)


def test_extract_locations(adapter):
    text = "他们来到了北京市朝阳区的人民广场和西湖边的花园酒店。"
    entities = asyncio.run(adapter.extract(text))
    assert len(entities["locations"]) >= 1


def test_extract_empty_text(adapter):
    entities = asyncio.run(adapter.extract(""))
    assert entities["persons"] == []
    assert entities["locations"] == []
    assert entities["key_terms"] == []
