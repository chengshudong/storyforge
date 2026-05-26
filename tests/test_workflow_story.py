import asyncio
import json

import pytest

from workflows.story_generation import (
    StoryGenerationState,
    _summarize_node,
    _extract_node,
    _plan_node,
)


class MockStoryAgent:
    def __init__(self, fail=False):
        self.fail = fail
        self.summarize_called = False
        self.extract_called = False

    async def summarize(self, project_id, chapter_chunks, summary_stub=None):
        self.summarize_called = True
        if self.fail:
            raise RuntimeError("summarize failed")
        return {
            "story_summary": "Mock summary.",
            "protagonist_arc": "Mock arc.",
            "central_conflict": "Mock conflict.",
            "turning_points": ["Turning 1"],
            "chapter_summaries": [{"chapter_summary": "Ch1"}, {"chapter_summary": "Ch2"}],
            "chapter_count": 2,
            "meta": {},
        }

    async def extract(self, story_summary, entities_stub=None, chapter_chunks=None, project_id=""):
        self.extract_called = True
        if self.fail:
            raise RuntimeError("extract failed")
        return {
            "timeline": [{"event": "E1", "chapter_ref": 1}],
            "conflicts": [],
            "relationships": [],
            "world_setting": {"time_period": "2020s"},
        }


class MockEpisodeAgent:
    async def plan(self, project_id, story_summary, timeline, chapter_count):
        return [
            {
                "episode_number": 1,
                "title": "Episode 1",
                "summary": "First episode.",
                "chapter_range": [1, 2],
                "cliffhanger": "Next time...",
                "key_scenes": ["Scene A", "Scene B"],
            }
        ]


@pytest.fixture
def base_state():
    return StoryGenerationState(
        project_id="proj-test",
        chapter_chunks=[{"text": "test", "index": 0}],
    )


@pytest.mark.asyncio
async def test_summarize_node_success(base_state):
    agent = MockStoryAgent()
    result = await _summarize_node(base_state, agent)
    assert result["status"] == "summarized"
    assert result["story_summary"] == "Mock summary."
    assert result["chapter_count"] == 2
    assert agent.summarize_called


@pytest.mark.asyncio
async def test_summarize_node_failure(base_state):
    agent = MockStoryAgent(fail=True)
    result = await _summarize_node(base_state, agent)
    assert result["status"] == "failed"
    assert result["error"] == "summarize failed"


@pytest.mark.asyncio
async def test_extract_node_success(base_state):
    base_state.story_summary = "Test summary."
    agent = MockStoryAgent()
    result = await _extract_node(base_state, agent)
    assert result["status"] == "extracted"
    assert result["timeline"][0]["event"] == "E1"
    assert agent.extract_called


@pytest.mark.asyncio
async def test_extract_node_failure(base_state):
    agent = MockStoryAgent(fail=True)
    result = await _extract_node(base_state, agent)
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_plan_node_success(base_state):
    base_state.story_summary = "Test summary."
    base_state.timeline = []
    base_state.chapter_count = 2
    agent = MockEpisodeAgent()
    result = await _plan_node(base_state, agent)
    assert result["status"] == "planned"
    assert len(result["episode_plan"]) == 1
    assert result["episode_plan"][0]["title"] == "Episode 1"


def test_story_generation_state_defaults():
    state = StoryGenerationState(project_id="test")
    assert state.project_id == "test"
    assert state.status == "pending"
    assert state.chapter_chunks == []
    assert state.story_summary is None
    assert state.episode_plan is None


def test_story_generation_state_fields():
    state = StoryGenerationState(
        project_id="proj-1",
        story_summary="A story.",
        timeline=[{"event": "X"}],
        conflicts=[{"type": "person_vs_person"}],
        relationships=[{"a": "Alice", "b": "Bob"}],
        world_setting={"time_period": "1800s"},
        episode_plan=[{"episode_number": 1}],
        status="done",
    )
    assert state.story_summary == "A story."
    assert len(state.timeline) == 1
    assert len(state.conflicts) == 1
    assert state.world_setting["time_period"] == "1800s"


def test_workflow_builds():
    from workflows.story_generation import build_story_workflow

    agent = MockStoryAgent()
    ep_agent = MockEpisodeAgent()

    class FakeRepo:
        async def create(self, entity):
            from unittest.mock import MagicMock
            m = MagicMock()
            m.id = "fake-id"
            return m

        async def get(self, id):
            from unittest.mock import MagicMock
            m = MagicMock()
            m.status = MagicMock()
            m.meta = {}
            return m

    class FakeSession:
        async def flush(self):
            pass

    workflow = build_story_workflow(
        agent, ep_agent, FakeRepo(), FakeRepo(), FakeSession(),
    )
    assert workflow is not None
