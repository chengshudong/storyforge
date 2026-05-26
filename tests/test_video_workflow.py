from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from workflows.video_generation import (
    VideoGenerationState,
    PHASE_INIT,
    PHASE_SUBMIT,
    PHASE_POLL,
    PHASE_COMPOSITE,
    PHASE_SAVE,
    _init_node,
    _submit_node,
    _poll_node,
    _composite_node,
    _save_node,
    build_video_workflow,
)


class MockVideoAgent:
    def __init__(self, fail_at: str | None = None):
        self.fail_at = fail_at
        self.submitted: list[dict] = []
        self.saved: list[dict] = []

    async def submit_scene_video(self, project_id, scene_id, character_name,
                                  character_profile, character_image_data,
                                  storyboard, seed):
        if self.fail_at == "submit":
            raise RuntimeError("submit failed")
        prompt_id = f"task-{len(self.submitted) + 1}"
        self.submitted.append({"prompt_id": prompt_id, "character_name": character_name})
        return prompt_id

    async def poll_scene_video(self, prompt_id):
        if self.fail_at == "poll":
            raise RuntimeError("poll failed")

        from interfaces.video import VideoResult, VideoStatus
        return VideoResult(
            prompt_id=prompt_id,
            status=VideoStatus.DONE,
            video=b"\x00" * 10000,
            duration_s=5.0,
        )

    async def extract_thumbnail(self, video_data, at_seconds=1.5):
        return b"\x89PNGthumb"

    async def extract_preview(self, video_data, duration_s=3.0):
        return b"\x00" * 5000

    async def save_video(self, project_id, scene_id, video_data, audio_data,
                          prompt, negative_prompt, seed, fps, params_dict,
                          provider, batch_id=None):
        saved = MagicMock()
        saved.id = uuid.uuid4()
        self.saved.append({"id": saved.id, "scene_id": scene_id})
        return saved

    async def _resolve_provider(self):
        return "mockprovider"


@pytest.fixture
def base_state():
    return VideoGenerationState(
        project_id=str(uuid.uuid4()),
        scenes=[
            {
                "id": str(uuid.uuid4()),
                "storyboard": {
                    "camera": {"shot_type": "medium shot", "movement": "pan"},
                    "emotion": "happy",
                    "location": "meadow",
                    "duration_estimate": 3.0,
                    "characters_present": ["Alice"],
                    "actions": [{"character": "Alice", "action": "waves"}],
                },
            },
        ],
        character_assets={
            "Alice": {
                "profile": {"appearance": "tall", "gender": "female"},
                "image_data": b"\x89PNGkeyframe",
            },
        },
        voice_assets={
        },
    )


@pytest.fixture
def scene_id(base_state):
    return base_state.scenes[0]["id"]


# ── State Defaults ──────────────────────────────────────────────────────

class TestVideoGenerationState:
    def test_defaults(self):
        state = VideoGenerationState(project_id="proj-1")
        assert state.project_id == "proj-1"
        assert state.scenes == []
        assert state.status == "pending"
        assert state.progress == 0
        assert state.submissions == []
        assert state.generated_videos == []
        assert state.saved_video_ids == []
        assert state.errors == []

    def test_default_phases(self):
        state = VideoGenerationState(project_id="p1")
        assert PHASE_INIT in state.phases
        assert PHASE_SUBMIT in state.phases
        assert PHASE_POLL in state.phases

    def test_batch_id_auto_generated(self):
        state = VideoGenerationState(project_id="p1")
        assert state.batch_id != ""
        assert state.batch_id is not None

    def test_full_state(self):
        state = VideoGenerationState(
            project_id="proj-1",
            scenes=[{"id": "s1", "storyboard": {}}],
            character_assets={"A": {"profile": {}, "image_data": b"x"}},
            voice_assets={"s1": [{"character_name": "A", "audio_data": b"a"}]},
            variant_count=2,
            regenerate=True,
            submissions=[{"prompt_id": "t1"}],
            generated_videos=[{"scene_id": "s1"}],
            saved_video_ids=["v1"],
            errors=[{"error": "test"}],
            status="done",
            progress=100,
        )
        assert state.variant_count == 2
        assert state.regenerate is True
        assert len(state.submissions) == 1
        assert len(state.generated_videos) == 1
        assert len(state.saved_video_ids) == 1
        assert len(state.errors) == 1
        assert state.status == "done"
        assert state.progress == 100


# ── Init Node ───────────────────────────────────────────────────────────

class TestInitNode:
    @pytest.mark.asyncio
    async def test_init_success(self, base_state):
        agent = MockVideoAgent()
        result = await _init_node(base_state, agent)
        assert result["status"] == "init_done"
        assert len(result["scenes"]) == 1

    @pytest.mark.asyncio
    async def test_init_no_scenes(self):
        agent = MockVideoAgent()
        state = VideoGenerationState(project_id="p1", scenes=[])
        result = await _init_node(state, agent)
        assert result["status"] == "no_scenes"

    @pytest.mark.asyncio
    async def test_init_scenes_no_storyboards(self):
        agent = MockVideoAgent()
        state = VideoGenerationState(
            project_id="p1",
            scenes=[{"id": "s1"}, {"id": "s2"}],
        )
        result = await _init_node(state, agent)
        assert result["status"] == "no_scenes"

    @pytest.mark.asyncio
    async def test_init_filters_no_storyboard_scenes(self, base_state):
        base_state.scenes.append({"id": "no_sb"})
        agent = MockVideoAgent()
        result = await _init_node(base_state, agent)
        assert result["status"] == "init_done"
        assert len(result["scenes"]) == 1  # only the one with storyboard

    @pytest.mark.asyncio
    async def test_init_skips_when_not_in_phases(self, base_state):
        base_state.phases = [PHASE_SUBMIT, PHASE_POLL, PHASE_COMPOSITE, PHASE_SAVE]
        agent = MockVideoAgent()
        result = await _init_node(base_state, agent)
        assert result["status"] == "init_skipped"


# ── Submit Node ─────────────────────────────────────────────────────────

class TestSubmitNode:
    @pytest.mark.asyncio
    async def test_submit_success(self, base_state):
        agent = MockVideoAgent()
        result = await _submit_node(base_state, agent)
        assert result["status"] == "submit_done"
        assert len(result["submissions"]) == 1
        assert result["submissions"][0]["character_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_submit_no_characters_with_images(self, base_state):
        base_state.character_assets = {}
        agent = MockVideoAgent()
        result = await _submit_node(base_state, agent)
        assert result["status"] == "failed"
        assert "no videos could be submitted" in result["error"]

    @pytest.mark.asyncio
    async def test_submit_character_not_in_assets(self, base_state):
        base_state.scenes[0]["storyboard"]["characters_present"] = ["UnknownChar"]
        agent = MockVideoAgent()
        result = await _submit_node(base_state, agent)
        assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_submit_skips_when_not_in_phases(self, base_state):
        base_state.phases = [PHASE_INIT, PHASE_POLL, PHASE_COMPOSITE, PHASE_SAVE]
        agent = MockVideoAgent()
        result = await _submit_node(base_state, agent)
        assert result["status"] == "submit_skipped"


# ── Poll Node ───────────────────────────────────────────────────────────

class TestPollNode:
    @pytest.mark.asyncio
    async def test_poll_success(self, base_state):
        base_state.submissions = [{"prompt_id": "task-1", "scene_id": base_state.scenes[0]["id"], "character_name": "Alice"}]
        agent = MockVideoAgent()
        result = await _poll_node(base_state, agent)
        assert result["status"] == "poll_done"
        assert len(result["generated_videos"]) == 1

    @pytest.mark.asyncio
    async def test_poll_retry_on_all_fail(self, base_state):
        base_state.submissions = [{"prompt_id": "task-1", "scene_id": "s1", "character_name": "Alice"}]
        agent = MockVideoAgent(fail_at="poll")
        result = await _poll_node(base_state, agent)
        assert result["status"] == "retry"
        assert result["retry_count"] == 1

    @pytest.mark.asyncio
    async def test_poll_fail_after_max_retries(self, base_state):
        base_state.submissions = [{"prompt_id": "task-1", "scene_id": "s1", "character_name": "Alice"}]
        base_state.retry_count = 1  # already at max
        agent = MockVideoAgent(fail_at="poll")
        result = await _poll_node(base_state, agent)
        assert result["status"] == "failed"
        assert "all video polls failed" in result["error"]

    @pytest.mark.asyncio
    async def test_poll_skips_when_not_in_phases(self, base_state):
        base_state.phases = [PHASE_INIT, PHASE_SUBMIT, PHASE_COMPOSITE, PHASE_SAVE]
        base_state.submissions = [{"prompt_id": "task-1"}]
        agent = MockVideoAgent()
        result = await _poll_node(base_state, agent)
        assert result["status"] == "poll_skipped"


# ── Composite Node ──────────────────────────────────────────────────────

class TestCompositeNode:
    @pytest.mark.asyncio
    async def test_composite_success(self, base_state):
        base_state.generated_videos = [
            {"prompt_id": "t1", "scene_id": "s1", "character_name": "Alice",
             "video_data": b"\x00", "audio_data": b"\x00", "duration_s": 5.0},
        ]
        agent = MockVideoAgent()
        result = await _composite_node(base_state, agent)
        assert result["status"] == "composite_done"
        assert "thumbnail_data" in result["generated_videos"][0]
        assert "preview_data" in result["generated_videos"][0]

    @pytest.mark.asyncio
    async def test_composite_skips_when_not_in_phases(self, base_state):
        base_state.phases = [PHASE_INIT, PHASE_SUBMIT, PHASE_POLL, PHASE_SAVE]
        base_state.generated_videos = [{"video_data": b"x"}]
        agent = MockVideoAgent()
        result = await _composite_node(base_state, agent)
        assert result["status"] == "composite_skipped"


# ── Save Node ───────────────────────────────────────────────────────────

class TestSaveNode:
    @pytest.mark.asyncio
    async def test_save_success(self, base_state):
        base_state.generated_videos = [
            {"scene_id": base_state.scenes[0]["id"], "character_name": "Alice",
             "video_data": b"\x00", "audio_data": None},
        ]
        agent = MockVideoAgent()
        result = await _save_node(base_state, agent)
        assert result["status"] == "done"
        assert len(result["saved_video_ids"]) == 1

    @pytest.mark.asyncio
    async def test_save_skips_empty_videos(self, base_state):
        base_state.generated_videos = [
            {"scene_id": "s1", "character_name": "Alice", "video_data": None, "audio_data": None},
        ]
        agent = MockVideoAgent()
        result = await _save_node(base_state, agent)
        assert result["status"] == "done"
        assert len(result["saved_video_ids"]) == 0


# ── Graph Construction ──────────────────────────────────────────────────

class TestBuildWorkflow:
    def test_workflow_compiles(self):
        agent = MockVideoAgent()
        workflow = build_video_workflow(agent)
        assert workflow is not None

    def test_workflow_has_checkpointer(self):
        agent = MockVideoAgent()
        workflow = build_video_workflow(agent)
        assert workflow.checkpointer is not None
