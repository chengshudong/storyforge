import json
from unittest.mock import MagicMock

import pytest

from workflows.scene_generation import (
    SceneGenerationState,
    _split_node,
    _storyboard_node,
    _validate_node,
)


class MockSceneAgent:
    def __init__(self, fail_at: str | None = None):
        self.fail_at = fail_at
        self.split_called = False
        self.storyboard_called = False
        self.validate_called = False

    async def _split_episode(self, project_id, episode, characters, timeline):
        self.split_called = True
        if self.fail_at == "split":
            raise RuntimeError("split failed")
        return [
            {"scene_number": 1, "scene_title": "Scene 1", "scene_beat": "Beat 1", "characters_present": ["John"], "estimated_duration": 30},
            {"scene_number": 2, "scene_title": "Scene 2", "scene_beat": "Beat 2", "characters_present": ["John"], "estimated_duration": 40},
        ]

    async def storyboard(self, project_id, episode, characters, timeline=None, world_setting=None, previous_scenes=None):
        self.storyboard_called = True
        if self.fail_at == "storyboard":
            raise RuntimeError("storyboard failed")
        return [
            {"scene_number": 1, "scene_title": "S1", "description": "...", "camera": "wide", "emotion": "tense", "location": "Room", "dialogue": [], "props": [], "transition": "cut", "character_actions": {}, "asset_refs": [], "characters_present": ["John"], "estimated_duration": 30},
        ]

    async def _validate_continuity(self, project_id, scenes):
        self.validate_called = True
        if self.fail_at == "validate":
            raise RuntimeError("validate failed")
        return {"valid": True, "issues": []}


@pytest.fixture
def base_state():
    return SceneGenerationState(
        project_id="proj-test",
        episode_id="ep-test",
        episode={"title": "Test", "summary": "Test summary.", "key_scenes": ["a", "b"]},
        characters=[{"name": "John", "role": "protagonist"}],
    )


@pytest.mark.asyncio
async def test_split_node_success(base_state):
    agent = MockSceneAgent()
    result = await _split_node(base_state, agent)
    assert result["status"] == "split"
    assert len(result["scene_beats"]) == 2
    assert agent.split_called


@pytest.mark.asyncio
async def test_split_node_failure(base_state):
    agent = MockSceneAgent(fail_at="split")
    result = await _split_node(base_state, agent)
    assert result["status"] == "failed"
    assert "split failed" in str(result["error"])


@pytest.mark.asyncio
async def test_storyboard_node_success(base_state):
    base_state.scene_beats = [{"scene_number": 1, "scene_beat": "Beat 1"}]
    agent = MockSceneAgent()
    result = await _storyboard_node(base_state, agent)
    assert result["status"] == "storyboarded"
    assert len(result["scenes"]) == 1
    assert agent.storyboard_called


@pytest.mark.asyncio
async def test_storyboard_node_failure(base_state):
    agent = MockSceneAgent(fail_at="storyboard")
    result = await _storyboard_node(base_state, agent)
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_validate_node_success(base_state):
    base_state.scenes = [{"scene_number": 1, "scene_title": "S1"}]
    agent = MockSceneAgent()
    result = await _validate_node(base_state, agent)
    assert result["status"] == "validated"
    assert result["validation_passed"] is True


@pytest.mark.asyncio
async def test_validate_node_handles_failure_gracefully(base_state):
    """Validate node failure should not block — it returns passed=True."""
    base_state.scenes = [{"scene_number": 1}]
    agent = MockSceneAgent(fail_at="validate")
    result = await _validate_node(base_state, agent)
    assert result["status"] == "validated"
    assert result["validation_passed"] is True  # non-blocking


def test_scene_generation_state_defaults():
    state = SceneGenerationState(project_id="test", episode_id="ep-1")
    assert state.project_id == "test"
    assert state.episode_id == "ep-1"
    assert state.status == "pending"
    assert state.characters == []
    assert state.scenes is None
    assert state.scene_beats is None
    assert state.validation_passed is True  # default is True (validation is non-blocking)


def test_scene_generation_state_full():
    state = SceneGenerationState(
        project_id="proj-1",
        episode_id="ep-1",
        scene_beats=[{"scene_number": 1}],
        scenes=[{"scene_number": 1, "scene_title": "Test"}],
        validation={"valid": True},
        validation_passed=True,
        saved_scene_ids=["uuid-1", "uuid-2"],
        status="done",
    )
    assert state.scene_beats is not None
    assert len(state.saved_scene_ids) == 2
    assert state.status == "done"


def test_workflow_builds():
    from workflows.scene_generation import build_scene_workflow

    agent = MockSceneAgent()

    class FakeRepo:
        async def create(self, entity):
            m = MagicMock()
            m.id = "fake-id"
            return m
        async def get(self, id):
            m = MagicMock()
            m.status = MagicMock()
            return m

    class FakeSession:
        async def flush(self):
            pass

    workflow = build_scene_workflow(agent, FakeRepo(), FakeRepo(), FakeSession())
    assert workflow is not None
