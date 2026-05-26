import asyncio
import json

import pytest

from agents.episode_agent import EpisodeAgent
from services.model_router.router import ModelRouter


class MockLLMAdapter:
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


def make_agent(responses: list[str] | None = None):
    adapter = MockLLMAdapter(responses)
    registry = {
        "tasks": {"episode": {"provider": "mock", "model": "mock-model"}},
        "fallback": ["mock", "local"],
        "degrade": {"episode": {"provider": "mock", "model": "local-model"}},
    }
    router = ModelRouter({"mock": adapter, "local": adapter}, registry)
    cache = MockCacheService()
    agent = EpisodeAgent(router, cache)
    return agent, adapter


def test_plan_coverage_all_chapters():
    plan_json = json.dumps({
        "episodes": [
            {
                "episode_number": 1,
                "title": "The Arrival",
                "summary": "John enters the mysterious house.",
                "chapter_range": [1, 2],
                "cliffhanger": "Who left the letter?",
                "key_scenes": ["Door opens", "Finding the letter"],
            },
            {
                "episode_number": 2,
                "title": "The Reveal",
                "summary": "Mary discovers the truth.",
                "chapter_range": [3, 4],
                "cliffhanger": None,
                "key_scenes": ["Morning coffee", "Reading the letter"],
            },
        ]
    })
    agent, adapter = make_agent([plan_json])

    episodes = asyncio.run(agent.plan(
        project_id="proj-1",
        story_summary="A mystery story about a couple...",
        timeline=[
            {"event": "John enters room", "chapter_ref": 1},
            {"event": "Mary reads letter", "chapter_ref": 4},
        ],
        chapter_count=4,
    ))

    assert len(episodes) == 2
    assert episodes[0]["episode_number"] == 1
    assert episodes[0]["title"] == "The Arrival"
    assert episodes[0]["chapter_range"] == [1, 2]
    assert episodes[0]["cliffhanger"] == "Who left the letter?"
    assert len(episodes[0]["key_scenes"]) == 2
    assert episodes[1]["cliffhanger"] is None


def test_plan_short_novel_few_episodes():
    plan_json = json.dumps({
        "episodes": [
            {
                "episode_number": 1,
                "title": "Short Story",
                "summary": "A brief tale.",
                "chapter_range": [1, 1],
                "cliffhanger": None,
                "key_scenes": ["Beginning", "Middle", "End"],
            },
        ]
    })
    agent, adapter = make_agent([plan_json])

    episodes = asyncio.run(agent.plan(
        project_id="proj-1",
        story_summary="A very short story.",
        timeline=[],
        chapter_count=1,
    ))

    assert len(episodes) == 1


def test_plan_cache_hit():
    plan_json = json.dumps({
        "episodes": [{"episode_number": 1, "title": "Cached", "summary": "...",
                       "chapter_range": [1, 3], "cliffhanger": None, "key_scenes": []}]
    })
    agent, adapter = make_agent([plan_json, plan_json])

    # First call — should populate cache
    episodes1 = asyncio.run(agent.plan(
        project_id="proj-1", story_summary="Test", timeline=[], chapter_count=3,
    ))

    # Second call — should hit cache
    episodes2 = asyncio.run(agent.plan(
        project_id="proj-1", story_summary="Test", timeline=[], chapter_count=3,
    ))

    assert episodes1 == episodes2
    # Only 1 LLM call, not 2
    assert len(adapter.calls) == 1


def test_regenerate_episode():
    regenerate_json = json.dumps({
        "title": "Improved Title",
        "summary": "Better summary with more detail.",
        "cliffhanger": "What lies beyond?",
        "key_scenes": ["New scene 1", "New scene 2", "New scene 3"],
    })
    agent, adapter = make_agent([regenerate_json])

    result = asyncio.run(agent.regenerate_episode(
        project_id="proj-1",
        episode={
            "episode_number": 2,
            "title": "Old Title",
            "summary": "Old summary.",
            "key_scenes": ["Old scene"],
            "cliffhanger": "Old cliffhanger",
            "chapter_range": [3, 5],
        },
        adjacent_episodes=[
            {"episode_number": 1, "title": "First", "summary": "..."},
        ],
        feedback="Make it more exciting with higher stakes.",
    ))

    assert result["title"] == "Improved Title"
    assert result["summary"] == "Better summary with more detail."
    assert result["episode_number"] == 2
    assert result["chapter_range"] == [3, 5]


def test_plan_fallback_on_invalid_json():
    """When LLM returns garbage, should return a single catch-all episode."""
    agent, adapter = make_agent(["not json at all, just some text"])

    episodes = asyncio.run(agent.plan(
        project_id="proj-1",
        story_summary="Test story.",
        timeline=[],
        chapter_count=3,
    ))

    assert len(episodes) == 1
    assert episodes[0]["episode_number"] == 1
    assert episodes[0]["chapter_range"] == [1, 3]
