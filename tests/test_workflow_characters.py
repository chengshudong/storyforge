import json
from unittest.mock import MagicMock

import pytest

from workflows.character_generation import (
    CharacterGenerationState,
    _extract_node,
    _profile_node,
    _merge_node,
    _normalize_node,
)


class MockCharacterAgent:
    def __init__(self, fail_at: str | None = None):
        self.fail_at = fail_at
        self.extract_called = False
        self.profile_called = False
        self.merge_called = False
        self.normalize_called = False

    async def extract_characters(self, project_id, chapter_summaries,
                                 relationships, entities_persons, scene_characters):
        self.extract_called = True
        if self.fail_at == "extract":
            raise RuntimeError("extract failed")
        return [
            {"name": "Alice", "role": "protagonist", "importance": "primary",
             "narrative_function": "Hero", "is_protagonist": True, "aliases": []},
            {"name": "Bob", "role": "antagonist", "importance": "primary",
             "narrative_function": "Villain", "is_protagonist": False, "aliases": []},
        ]

    async def generate_profiles(self, project_id, characters, chapter_summaries,
                                relationships, scenes, world_setting):
        self.profile_called = True
        if self.fail_at == "profile":
            raise RuntimeError("profile failed")
        result = []
        for c in characters:
            c_copy = dict(c)
            c_copy.update({
                "appearance": {"age_estimate": "30s"},
                "voice_profile": {"pitch": "medium"},
                "personality": {"traits": ["brave"]},
                "emotion_range": {"dominant": "neutral"},
                "costume_style": {"era": "modern"},
                "backstory": "...",
            })
            result.append(c_copy)
        return result

    async def merge_duplicates(self, project_id, characters):
        self.merge_called = True
        if self.fail_at == "merge":
            raise RuntimeError("merge failed")
        return characters

    async def normalize_profiles(self, project_id, characters, world_setting):
        self.normalize_called = True
        if self.fail_at == "normalize":
            raise RuntimeError("normalize failed")
        return {"characters": characters, "issues": []}


@pytest.fixture
def base_state():
    return CharacterGenerationState(
        project_id="proj-test",
        chapter_summaries=[{"chapter_index": 1, "chapter_summary": "Test."}],
        relationships=[{"character_a": "Alice", "character_b": "Bob"}],
        entities_persons=["Alice", "Bob"],
        scene_characters=["Alice"],
        scenes=[],
        world_setting={"time_period": "modern"},
    )


@pytest.mark.asyncio
async def test_extract_node_success(base_state):
    agent = MockCharacterAgent()
    result = await _extract_node(base_state, agent)
    assert result["status"] == "extracted"
    assert len(result["extracted_characters"]) == 2
    assert agent.extract_called


@pytest.mark.asyncio
async def test_extract_node_failure(base_state):
    agent = MockCharacterAgent(fail_at="extract")
    result = await _extract_node(base_state, agent)
    assert result["status"] == "failed"
    assert "extract failed" in str(result["error"])


@pytest.mark.asyncio
async def test_profile_node_success(base_state):
    base_state.extracted_characters = [{"name": "Alice", "role": "protagonist"}]
    agent = MockCharacterAgent()
    result = await _profile_node(base_state, agent)
    assert result["status"] == "profiled"
    assert len(result["profiled_characters"]) == 1
    assert "appearance" in result["profiled_characters"][0]


@pytest.mark.asyncio
async def test_profile_node_failure(base_state):
    agent = MockCharacterAgent(fail_at="profile")
    result = await _profile_node(base_state, agent)
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_merge_node_success(base_state):
    base_state.profiled_characters = [{"name": "Alice"}, {"name": "Bob"}]
    agent = MockCharacterAgent()
    result = await _merge_node(base_state, agent)
    assert result["status"] == "merged"
    assert len(result["merged_characters"]) == 2


@pytest.mark.asyncio
async def test_normalize_node_success(base_state):
    base_state.merged_characters = [{"name": "Alice", "role": "protagonist"}]
    agent = MockCharacterAgent()
    result = await _normalize_node(base_state, agent)
    assert result["status"] == "normalized"
    assert len(result["normalized_characters"]) == 1


def test_character_generation_state_defaults():
    state = CharacterGenerationState(project_id="test")
    assert state.project_id == "test"
    assert state.status == "pending"
    assert state.chapter_summaries == []
    assert state.entities_persons == []
    assert state.scene_characters == []
    assert state.extracted_characters is None
    assert state.profiled_characters is None
    assert state.merged_characters is None
    assert state.normalized_characters is None
    assert state.issues == []


def test_character_generation_state_full():
    state = CharacterGenerationState(
        project_id="proj-1",
        chapter_summaries=[{"chapter_index": 1}],
        extracted_characters=[{"name": "Alice"}],
        profiled_characters=[{"name": "Alice", "appearance": {}}],
        merged_characters=[{"name": "Alice", "appearance": {}}],
        normalized_characters=[{"name": "Alice", "appearance": {}}],
        issues=[],
        saved_character_ids=["uuid-1"],
        status="done",
    )
    assert state.status == "done"
    assert len(state.saved_character_ids) == 1


def test_workflow_builds():
    from workflows.character_generation import build_character_workflow

    agent = MockCharacterAgent()

    class FakeRepo:
        async def create(self, entity):
            m = MagicMock()
            m.id = "fake-id"
            return m
        async def get(self, id):
            return None
        async def get_by_name(self, project_id, name):
            return None

    class FakeSession:
        async def flush(self):
            pass
        async def execute(self, stmt):
            pass

    workflow = build_character_workflow(agent, FakeRepo(), FakeSession())
    assert workflow is not None
