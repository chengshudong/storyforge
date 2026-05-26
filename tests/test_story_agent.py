import asyncio
import json

import pytest

from agents.story_agent import StoryAgent
from services.model_router.router import ModelRouter


class MockLLMAdapter:
    """Mock adapter that returns controlled responses."""
    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or []
        self.calls: list[dict] = []

    async def generate(self, prompt, model, **kwargs):
        self.calls.append({"prompt": prompt, "model": model})
        text = self.responses.pop(0) if self.responses else "{}"
        from interfaces.llm import ModelResponse
        return ModelResponse(
            text=text, model=model, provider="mock",
            tokens_input=10, tokens_output=20, duration_ms=100,
        )

    async def stream(self, prompt, model, **kwargs):
        yield ""
    async def embedding(self, texts, model):
        return []
    async def health(self):
        return {"status": "healthy"}


class MockCacheService:
    def __init__(self):
        self.store: dict = {}

    def build_key(self, entity, project_id, content_hash):
        return f"cache:model:{entity}:{project_id}:{content_hash}"

    @staticmethod
    def hash_content(content):
        import hashlib
        return hashlib.md5(content.encode()).hexdigest()[:16]

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ttl):
        self.store[key] = value

    async def invalidate_project(self, project_id):
        return 0


class MockContextStore:
    async def embed(self, chunks, model="all-MiniLM-L6-v2"):
        return [[0.1] * 384 for _ in chunks]

    async def search(self, query, top_k=10):
        return []

    async def delete(self, document_id):
        return True


def make_router(responses: list[str] | None = None):
    adapter = MockLLMAdapter(responses)
    registry = {
        "tasks": {"summary": {"provider": "mock", "model": "mock-model"}},
        "fallback": ["mock", "local"],
        "degrade": {"summary": {"provider": "mock", "model": "local-model"}},
    }
    return ModelRouter({"mock": adapter, "local": adapter}, registry), adapter


def make_agent(responses: list[str] | None = None):
    router, adapter = make_router(responses)
    cache = MockCacheService()
    context = MockContextStore()
    agent = StoryAgent(router, cache, context)
    return agent, adapter


CHAPTER_CHAPTERS = [
    {"text": "Chapter 1\nThe door creaked open. John stepped inside, his heart pounding.", "index": 0},
    {"text": "The room was dark and smelled of old books. Someone had been here recently.", "index": 1},
    {"text": "Chapter 2\nMorning light flooded the kitchen. Mary poured coffee.", "index": 2},
    {"text": "She stared at the letter in her hands. Everything had changed.", "index": 3},
]


def test_detect_chapters_finds_boundaries():
    agent, _ = make_agent()
    chapters = agent._detect_chapters(CHAPTER_CHAPTERS)
    assert len(chapters) == 2
    assert chapters[0]["chapter_index"] == 1
    assert chapters[1]["chapter_index"] == 2


def test_detect_chapters_no_boundaries_returns_single():
    agent, _ = make_agent()
    chunks = [{"text": "Some text without chapter markers.", "index": 0},
              {"text": "More text, also no markers.", "index": 1}]
    chapters = agent._detect_chapters(chunks)
    assert len(chapters) == 1
    assert chapters[0]["chapter_index"] == 1


def test_detect_chapters_empty():
    agent, _ = make_agent()
    chapters = agent._detect_chapters([])
    assert chapters == []


def test_parse_json_response_direct_json():
    result = StoryAgent._parse_json_response('{"key": "value"}', {"default": True})
    assert result == {"key": "value"}


def test_parse_json_response_code_fence():
    result = StoryAgent._parse_json_response(
        '```json\n{"key": "value"}\n```\n', {"default": True}
    )
    assert result == {"key": "value"}


def test_parse_json_response_embedded_object():
    result = StoryAgent._parse_json_response(
        'Some text before {"key": "value"} and text after', {"default": True}
    )
    assert result == {"key": "value"}


def test_parse_json_response_invalid_defaults():
    result = StoryAgent._parse_json_response("not json at all", {"fallback": 42})
    assert result == {"fallback": 42}


def test_summarize_single_chapter():
    chapter_summary = json.dumps({
        "chapter_summary": "John enters a dark room full of books.",
        "key_events": ["door creaks", "room is dark"],
        "characters_appearing": ["John"],
        "location": "Old room",
    })
    merge_result = json.dumps({
        "merged_summary": "John finds himself in a mysterious place.",
    })
    story_result = json.dumps({
        "narrative_summary": "A man named John enters a mysterious room...",
        "protagonist_arc": "John goes from curious to terrified.",
        "central_conflict": "John vs. the unknown.",
        "turning_points": ["The creaking door", "The old letter"],
    })

    agent, adapter = make_agent([chapter_summary, merge_result, story_result])

    result = asyncio.run(agent.summarize(
        project_id="proj-1",
        chapter_chunks=CHAPTER_CHAPTERS,
    ))

    assert "story_summary" in result
    assert "chapter_summaries" in result
    assert result["chapter_count"] == 2
    assert len(result["chapter_summaries"]) == 2


def test_extract_returns_structured_data():
    extract_result = json.dumps({
        "timeline": [{"event": "John enters room", "chapter_ref": 1, "characters_involved": ["John"]}],
        "conflicts": [{"type": "person_vs_self", "description": "Inner fear", "parties": ["John"], "stakes": "Sanity"}],
        "relationships": [{"character_a": "John", "character_b": "Mary", "relation_type": "spouses", "evolution": "strained", "significance": "core"}],
        "world_setting": {"time_period": "1940s", "primary_locations": ["Old house"], "social_rules": "Post-war", "atmosphere": "Tense", "notable_systems": None},
    })

    agent, adapter = make_agent([extract_result])

    result = asyncio.run(agent.extract(
        story_summary="A man enters a mysterious house...",
        project_id="proj-1",
    ))

    assert len(result["timeline"]) == 1
    assert len(result["conflicts"]) == 1
    assert len(result["relationships"]) == 1
    assert result["world_setting"]["time_period"] == "1940s"


def test_summarize_cache_hit():
    """Second call with same content should use cache."""
    chapter_summary = json.dumps({
        "chapter_summary": "Cached summary.",
        "key_events": [],
    })
    merge_result = json.dumps({"merged_summary": "Merged."})
    story_result = json.dumps({"narrative_summary": "Cached story."})

    agent, adapter = make_agent([
        chapter_summary, merge_result, story_result,
        chapter_summary, merge_result, story_result,
    ])

    # First call — populates cache
    result1 = asyncio.run(agent.summarize(
        project_id="proj-1",
        chapter_chunks=CHAPTER_CHAPTERS,
    ))

    # Second call — should hit cache for chapter summaries
    result2 = asyncio.run(agent.summarize(
        project_id="proj-1",
        chapter_chunks=CHAPTER_CHAPTERS,
    ))

    assert result1["story_summary"] == result2["story_summary"]


def test_empty_chunks_handled():
    agent, adapter = make_agent([
        json.dumps({"chapter_summary": "", "key_events": []}),
        json.dumps({"merged_summary": ""}),
        json.dumps({"narrative_summary": "Empty story."}),
    ])

    result = asyncio.run(agent.summarize(
        project_id="proj-1",
        chapter_chunks=[],
    ))

    assert result["chapter_count"] == 0
