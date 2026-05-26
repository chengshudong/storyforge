import asyncio
import json

import pytest

from agents.scene_agent import SceneAgent
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
        "tasks": {"scene": {"provider": "mock", "model": "mock-model"}},
        "fallback": ["mock", "local"],
        "degrade": {"scene": {"provider": "mock", "model": "local-model"}},
    }
    router = ModelRouter({"mock": adapter, "local": adapter}, registry)
    cache = MockCacheService()
    agent = SceneAgent(router, cache)
    return agent, adapter


SPLIT_JSON = json.dumps({
    "scenes": [
        {"scene_number": 1, "scene_title": "The Door Opens", "scene_beat": "John enters.", "characters_present": ["John"], "estimated_duration": 30},
        {"scene_number": 2, "scene_title": "The Letter", "scene_beat": "John reads.", "characters_present": ["John"], "estimated_duration": 40},
    ]
})

STORYBOARD_JSON_1 = json.dumps({
    "scene_title": "The Door Opens",
    "description": "John steps into the dark study, peering around.",
    "camera": "tracking shot",
    "emotion": "suspenseful",
    "location": "Old manor study",
    "dialogue": [],
    "props": ["letter"],
    "transition": "cut",
    "character_actions": {"John": "steps through doorway"},
    "asset_refs": ["BG_OLD_STUDY", "CHAR_JOHN_ENTERING"],
})

STORYBOARD_JSON_2 = json.dumps({
    "scene_title": "The Letter",
    "description": "John reads the mysterious letter by lamplight.",
    "camera": "close-up",
    "emotion": "tense",
    "location": "Desk area",
    "dialogue": [{"character": "John", "line": "Who wrote this?"}],
    "props": ["letter", "desk lamp"],
    "transition": "fade",
    "character_actions": {"John": "reads letter, furrows brow"},
    "asset_refs": ["PROP_LETTER", "CHAR_JOHN_READING"],
})

VALIDATE_JSON = json.dumps({"valid": True, "issues": []})


def test_split_episode():
    agent, adapter = make_agent([SPLIT_JSON])

    beats = asyncio.run(agent._split_episode(
        project_id="proj-1",
        episode={"id": "ep-1", "title": "The Arrival", "summary": "John enters the house.", "key_scenes": ["Door opens", "Finding letter"]},
        characters=[{"name": "John", "role": "protagonist", "traits": ["curious"]}],
        timeline=[],
    ))

    assert len(beats) == 2
    assert beats[0]["scene_number"] == 1
    assert beats[0]["scene_title"] == "The Door Opens"
    assert beats[1]["estimated_duration"] == 40


def test_split_cache_hit():
    agent, adapter = make_agent([SPLIT_JSON, SPLIT_JSON])

    args = {
        "project_id": "proj-1",
        "episode": {"id": "ep-1", "title": "T", "summary": "S.", "key_scenes": ["a"]},
        "characters": [],
        "timeline": [],
    }
    beats1 = asyncio.run(agent._split_episode(**args))
    beats2 = asyncio.run(agent._split_episode(**args))
    assert beats1 == beats2
    assert len(adapter.calls) == 1


def test_storyboard_scene():
    agent, adapter = make_agent([STORYBOARD_JSON_1])

    result = asyncio.run(agent._storyboard_scene(
        project_id="proj-1",
        scene_beat={"scene_number": 1, "scene_beat": "John enters.", "characters_present": ["John"], "scene_title": "", "estimated_duration": 30},
        episode_summary="John enters the house.",
        world_setting={"time_period": "1940s", "atmosphere": "dark"},
        previous_scene="",
        next_scene="John reads letter.",
    ))

    assert result["camera"] == "tracking shot"
    assert result["emotion"] == "suspenseful"
    assert result["location"] == "Old manor study"
    assert result["transition"] == "cut"
    assert "BG_OLD_STUDY" in result["asset_refs"]
    assert result["scene_number"] == 1


def test_storyboard_scene_cache_hit():
    agent, adapter = make_agent([STORYBOARD_JSON_1, STORYBOARD_JSON_1])

    beat = {"scene_number": 1, "scene_beat": "X.", "characters_present": [], "scene_title": "", "estimated_duration": 30}
    args = {
        "project_id": "proj-1", "scene_beat": beat,
        "episode_summary": "S.", "world_setting": {},
        "previous_scene": "", "next_scene": "",
    }
    r1 = asyncio.run(agent._storyboard_scene(**args))
    r2 = asyncio.run(agent._storyboard_scene(**args))
    assert r1 == r2
    assert len(adapter.calls) == 1


def test_full_storyboard_pipeline():
    """Test the full storyboard() pipeline: split → storyboard → validate."""
    agent, adapter = make_agent([SPLIT_JSON, STORYBOARD_JSON_1, STORYBOARD_JSON_2, VALIDATE_JSON])

    scenes = asyncio.run(agent.storyboard(
        project_id="proj-1",
        episode={"id": "ep-1", "title": "The Arrival", "summary": "John enters.", "key_scenes": ["Door", "Letter"]},
        characters=[{"name": "John", "role": "protagonist", "traits": []}],
        timeline=[],
        world_setting={"time_period": "1940s"},
    ))

    assert len(scenes) == 2
    assert scenes[0]["camera"] == "tracking shot"
    assert scenes[1]["camera"] == "close-up"
    assert len(scenes[1]["dialogue"]) == 1
    assert scenes[1]["dialogue"][0]["character"] == "John"


def test_regenerate_scene():
    edit_json = json.dumps({
        "scene_title": "Revised Title",
        "description": "Revised description.",
        "camera": "wide shot",
        "emotion": "suspenseful",
        "location": "Revised location",
        "dialogue": [{"character": "John", "line": "New line."}],
        "props": [],
        "transition": "cut",
        "character_actions": {"John": "revised action"},
        "asset_refs": [],
    })

    agent, adapter = make_agent([edit_json])

    result = asyncio.run(agent.regenerate_scene(
        project_id="proj-1",
        scene={"scene_number": 1, "scene_title": "Old", "description": "Old.", "camera": "close-up", "emotion": "neutral", "location": "Old", "dialogue": [], "props": [], "transition": "cut", "character_actions": {}, "asset_refs": [], "characters_present": ["John"], "estimated_duration": 30},
        adjacent=[{"scene_number": 2, "scene_title": "Next"}],
        feedback="Make it wider and more tense.",
    ))

    assert result["camera"] == "wide shot"
    assert result["scene_title"] == "Revised Title"
    assert result["scene_number"] == 1


def test_validate_continuity_passes():
    agent, adapter = make_agent([json.dumps({"valid": True, "issues": []})])

    result = asyncio.run(agent._validate_continuity(
        project_id="proj-1",
        scenes=[
            {"scene_number": 1, "scene_title": "A", "location": "", "emotion": "", "characters_present": [], "props": [], "transition": "cut"},
            {"scene_number": 2, "scene_title": "B", "location": "", "emotion": "", "characters_present": [], "props": [], "transition": "cut"},
        ],
    ))

    assert result["valid"] is True
    assert result["issues"] == []


def test_validate_continuity_finds_issues():
    agent, adapter = make_agent([json.dumps({
        "valid": False,
        "issues": [{"scene_pair": [1, 2], "problem": "Location jump", "suggestion": "Add travel scene"}]
    })])

    result = asyncio.run(agent._validate_continuity(
        project_id="proj-1",
        scenes=[
            {"scene_number": 1, "scene_title": "A", "location": "", "emotion": "", "characters_present": [], "props": [], "transition": ""},
            {"scene_number": 2, "scene_title": "B", "location": "", "emotion": "", "characters_present": [], "props": [], "transition": ""},
        ],
    ))

    assert result["valid"] is False
    assert len(result["issues"]) == 1


def test_empty_episode_returns_empty():
    agent, adapter = make_agent([json.dumps({"scenes": []})])

    scenes = asyncio.run(agent.storyboard(
        project_id="proj-1",
        episode={"id": "ep-1", "title": "", "summary": "", "key_scenes": []},
        characters=[],
    ))

    assert scenes == []


def test_parse_json_fallback():
    result = SceneAgent._parse_json('```json\n{"key": "value"}\n```', {"default": True})
    assert result == {"key": "value"}
    result2 = SceneAgent._parse_json("not json", {"fallback": 1})
    assert result2 == {"fallback": 1}
