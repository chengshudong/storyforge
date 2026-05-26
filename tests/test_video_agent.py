from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from interfaces.video import VideoResult, VideoStatus, VideoSubmitRequest


class FakeVideoProvider:
    def __init__(self):
        self.submissions: list[VideoSubmitRequest] = []

    async def submit(self, request: VideoSubmitRequest) -> str:
        self.submissions.append(request)
        return f"task-{len(self.submissions)}"

    async def poll(self, prompt_id: str) -> VideoResult:
        return VideoResult(
            prompt_id=prompt_id,
            status=VideoStatus.DONE,
            video=b"\x00" * 10000,
            duration_s=5.0,
        )

    async def cancel(self, prompt_id: str) -> bool:
        return True

    async def health(self) -> bool:
        return True


@pytest.fixture
def video_provider():
    return FakeVideoProvider()


@pytest.fixture
def video_repo():
    repo = MagicMock()
    repo.get = AsyncMock(return_value=None)
    repo.create = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
    repo.get_selected = AsyncMock(return_value=None)
    repo.set_selected = AsyncMock()
    return repo


@pytest.fixture
def asset_repo():
    repo = MagicMock()
    repo.get = AsyncMock(return_value=None)
    repo.list_by_character = AsyncMock(return_value=[])
    repo.list_by_project = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def cache_service():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    cache.build_key.return_value = "cache:video:test"
    return cache


@pytest.fixture
def video_agent(video_provider, video_repo, asset_repo, cache_service):
    from agents.video_agent import VideoAgent
    return VideoAgent(video_provider, video_repo, asset_repo, cache_service, router=None)


class TestVideoAgentInit:
    def test_initializes_with_provider_and_deps(self, video_provider, video_repo, asset_repo, cache_service):
        from agents.video_agent import VideoAgent
        agent = VideoAgent(video_provider, video_repo, asset_repo, cache_service)
        assert agent._provider is video_provider
        assert agent._videos is video_repo


class TestSubmitSceneVideo:
    @pytest.mark.asyncio
    async def test_submit_returns_prompt_id(self, video_agent):
        pid = await video_agent.submit_scene_video(
            project_id=uuid.uuid4(),
            scene_id=uuid.uuid4(),
            character_name="Alice",
            character_profile={"appearance": "tall"},
            character_image_data=b"\x89PNG keyframe",
            storyboard={
                "camera": {"shot_type": "medium shot", "movement": "pan"},
                "emotion": "happy",
                "location": "meadow",
                "duration_estimate": 3.0,
            },
            seed=42,
        )
        assert pid == "task-1"

    @pytest.mark.asyncio
    async def test_empty_storyboard_safe(self, video_agent):
        pid = await video_agent.submit_scene_video(
            project_id=uuid.uuid4(),
            scene_id=uuid.uuid4(),
            character_name="Bob",
            character_profile={},
            character_image_data=b"img",
            storyboard={},
            seed=0,
        )
        assert pid == "task-1"


class TestGenerateSceneVideo:
    @pytest.mark.asyncio
    async def test_generate_returns_video_result(self, video_agent):
        result = await video_agent.generate_scene_video(
            project_id=uuid.uuid4(),
            scene_id=uuid.uuid4(),
            character_name="Alice",
            character_profile={},
            character_image_data=b"img",
            storyboard={},
            seed=0,
        )
        assert result.status == VideoStatus.DONE
        assert result.video is not None


class TestCompositeAudio:
    @pytest.mark.asyncio
    async def test_composite_calls_ffmpeg(self, video_agent):
        with patch("agents.video_agent.asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.return_value = mock_process

            with patch("builtins.open", MagicMock()):
                with patch("os.unlink"):
                    result = await video_agent.composite_audio(
                        video_data=b"fake_video",
                        audio_data=b"fake_audio",
                    )
                    assert mock_exec.called
                    assert result is not None

    @pytest.mark.asyncio
    async def test_composite_failure_raises(self, video_agent):
        with patch("agents.video_agent.asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_process = AsyncMock()
            mock_process.returncode = 1
            mock_process.communicate = AsyncMock(return_value=(b"", b"ffmpeg error"))
            mock_exec.return_value = mock_process

            with patch("builtins.open", MagicMock()):
                with patch("os.unlink"):
                    with pytest.raises(RuntimeError, match="ffmpeg failed"):
                        await video_agent.composite_audio(b"v", b"a")


class TestExtractThumbnail:
    @pytest.mark.asyncio
    async def test_extract_thumbnail(self, video_agent):
        with patch("agents.video_agent.asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.return_value = mock_process

            with patch("builtins.open", MagicMock()):
                with patch("os.unlink"):
                    result = await video_agent.extract_thumbnail(b"fake_video", at_seconds=1.0)
                    assert result is not None


class TestExtractPreview:
    @pytest.mark.asyncio
    async def test_extract_preview(self, video_agent):
        with patch("agents.video_agent.asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.return_value = mock_process

            with patch("builtins.open", MagicMock()):
                with patch("os.unlink"):
                    result = await video_agent.extract_preview(b"fake_video", duration_s=2.0)
                    assert result is not None


class TestSaveVideo:
    @pytest.mark.asyncio
    async def test_save_creates_video_record(self, video_agent, video_repo):
        saved = MagicMock()
        saved.id = uuid.uuid4()
        video_repo.create.return_value = saved

        with patch.object(video_agent, "_upload_media", new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = "projects/p1/videos/test.mp4"
            result = await video_agent.save_video(
                project_id=uuid.uuid4(),
                scene_id=uuid.uuid4(),
                video_data=b"\x00" * 10000,
                audio_data=b"\x00" * 3200,
                prompt="test prompt",
                negative_prompt="bad stuff",
                seed=42,
                fps=24,
                params_dict={"width": 768, "height": 1152},
                provider="wan21",
            )
            assert result is not None
            assert video_repo.create.called

    @pytest.mark.asyncio
    async def test_save_no_audio_handled(self, video_agent, video_repo):
        saved = MagicMock()
        saved.id = uuid.uuid4()
        video_repo.create.return_value = saved

        with patch.object(video_agent, "_upload_media", new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = "projects/p1/videos/test.mp4"
            result = await video_agent.save_video(
                project_id=uuid.uuid4(),
                scene_id=uuid.uuid4(),
                video_data=b"\x00" * 10000,
                audio_data=None,
                prompt="test",
                negative_prompt="",
                seed=0,
                fps=24,
                params_dict={},
                provider="cogvideox",
            )
            assert result is not None


class TestCacheKeys:
    def test_video_cache_key_deterministic(self, video_agent):
        k1 = video_agent.build_video_cache_key("p1", "s1", "Alice", 42, "hash123")
        k2 = video_agent.build_video_cache_key("p1", "s1", "Alice", 42, "hash123")
        assert k1 == k2

    def test_video_cache_key_different_params(self, video_agent):
        k1 = video_agent.build_video_cache_key("p1", "s1", "Alice", 42, "hashA")
        k2 = video_agent.build_video_cache_key("p1", "s1", "Alice", 43, "hashA")
        assert k1 != k2

    def test_prompt_cache_key(self, video_agent):
        k = video_agent.build_prompt_cache_key("p1", "s1", "storyboard_hash")
        assert "p1" in k
        assert "s1" in k


class TestResolveProvider:
    @pytest.mark.asyncio
    async def test_resolve_provider_name(self, video_agent):
        name = await video_agent._resolve_provider()
        assert name == "fakevideoprovider"
