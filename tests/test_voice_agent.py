from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from interfaces.voice import VoiceResult, VoiceStatus


class MockVoiceProvider:
    """Mock VoiceProvider for agent tests."""
    async def clone_voice(self, name, audio, text=None):
        return f"spk_{name}"

    async def synthesize(self, request):
        return VoiceResult(
            speaker=request.speaker or "",
            status=VoiceStatus.DONE,
            audio=b"\x00" * 16000,
            duration_ms=500.0,
        )

    async def synthesize_batch(self, requests):
        return [await self.synthesize(r) for r in requests]

    async def preview(self, speaker, text):
        return VoiceResult(
            speaker=speaker,
            status=VoiceStatus.DONE,
            audio=b"\x00" * 8000,
            duration_ms=250.0,
        )

    async def health(self):
        return True

    async def list_speakers(self):
        return ["spk_1", "spk_2"]

    async def delete_speaker(self, speaker):
        return True


@pytest.fixture
def voice_provider():
    return MockVoiceProvider()


@pytest.fixture
def voice_repo():
    repo = MagicMock()
    repo.get = AsyncMock(return_value=None)
    repo.create = AsyncMock(return_value=MagicMock(id=uuid.uuid4(), speaker="spk_test"))
    repo.get_selected = AsyncMock(return_value=None)
    repo.get_by_version = AsyncMock(return_value=None)
    repo.set_selected = AsyncMock()
    return repo


@pytest.fixture
def voice_library():
    lib = MagicMock()
    lib.get_speaker = AsyncMock(return_value=None)
    lib.get_synthesis = AsyncMock(return_value=None)
    lib.set_speaker = AsyncMock()
    lib.set_synthesis = AsyncMock()
    lib.invalidate_speaker = AsyncMock()
    lib.invalidate_character_audio = AsyncMock()
    return lib


@pytest.fixture
def cache_service():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    cache.build_key.return_value = "cache:test:key"
    return cache


@pytest.fixture
def voice_agent(voice_provider, voice_repo, voice_library, cache_service):
    from agents.voice_agent import VoiceAgent
    return VoiceAgent(voice_provider, voice_repo, voice_library, cache_service, router=None)


class TestVoiceAgentInit:
    def test_initializes_with_provider_and_deps(self, voice_provider, voice_repo, voice_library, cache_service):
        from agents.voice_agent import VoiceAgent
        agent = VoiceAgent(voice_provider, voice_repo, voice_library, cache_service)
        assert agent._provider is voice_provider
        assert agent._voices is voice_repo


class TestCloneCharacterVoice:
    @pytest.mark.asyncio
    async def test_clones_and_returns_voice_id(self, voice_agent, voice_repo):
        saved_voice = MagicMock()
        saved_voice.id = uuid.uuid4()
        saved_voice.speaker = "spk_TestChar"
        voice_repo.create.return_value = saved_voice
        voice_repo.get.return_value = saved_voice
        voice_repo.get_selected.return_value = None

        with patch.object(voice_agent, "_upload_audio", new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = "projects/p1/voices/test.wav"
            vid = await voice_agent.clone_character_voice(
                project_id="00000000-0000-0000-0000-000000000001",
                character_id="00000000-0000-0000-0000-000000000002",
                voice_profile={"pitch": "medium", "tone_quality": "clear"},
                character_name="TestChar",
                character_version=1,
            )
            assert vid is not None

    @pytest.mark.asyncio
    async def test_clone_saves_reference_audio_to_minio(self, voice_agent, voice_repo):
        saved_voice = MagicMock()
        saved_voice.id = uuid.uuid4()
        saved_voice.speaker = "spk_RefTest"
        voice_repo.create.return_value = saved_voice
        voice_repo.get.return_value = saved_voice

        with patch.object(voice_agent, "_upload_audio", new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = "projects/p1/voices/ref.wav"
            await voice_agent.clone_character_voice(
                project_id="00000000-0000-0000-0000-000000000001",
                character_id="00000000-0000-0000-0000-000000000002",
                voice_profile={},
                character_name="RefTest",
                character_version=1,
            )
            assert mock_upload.call_count >= 2  # reference + preview


class TestGetOrCloneVoice:
    @pytest.mark.asyncio
    async def test_returns_existing_selected_voice(self, voice_agent, voice_repo):
        existing = MagicMock()
        existing.id = uuid.uuid4()
        existing.speaker = "spk_existing"
        existing.version = 1
        voice_repo.get_selected.return_value = existing

        vid, speaker = await voice_agent.get_or_clone_voice(
            project_id="00000000-0000-0000-0000-000000000001",
            character_id="00000000-0000-0000-0000-000000000002",
            voice_profile={},
            character_name="Test",
            character_version=1,
        )
        assert vid is not None
        assert speaker == "spk_existing"

    @pytest.mark.asyncio
    async def test_clones_when_no_existing_voice(self, voice_agent, voice_repo):
        voice_repo.get_selected.return_value = None
        saved = MagicMock()
        saved.id = uuid.uuid4()
        saved.speaker = "spk_new"
        saved.version = 1
        voice_repo.create.return_value = saved
        voice_repo.get.return_value = saved

        with patch.object(voice_agent, "_upload_audio", new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = "projects/p1/voices/test.wav"
            vid, speaker = await voice_agent.get_or_clone_voice(
                project_id="00000000-0000-0000-0000-000000000001",
                character_id="00000000-0000-0000-0000-000000000002",
                voice_profile={},
                character_name="NewChar",
                character_version=1,
            )
            assert speaker == "spk_new"


class TestSynthesizeDialogue:
    @pytest.mark.asyncio
    async def test_synthesizes_with_emotion(self, voice_agent):
        result = await voice_agent.synthesize_dialogue(
            speaker="spk_001",
            text="Hello, world!",
            emotion="happy",
        )
        assert result.status == VoiceStatus.DONE
        assert result.audio is not None

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty(self, voice_agent):
        result = await voice_agent.synthesize_dialogue(
            speaker="spk_001",
            text="",
            emotion="neutral",
        )
        assert result.status == VoiceStatus.DONE
        assert result.audio == b""


class TestPreviewVoice:
    @pytest.mark.asyncio
    async def test_preview_returns_audio_bytes(self, voice_agent):
        audio = await voice_agent.preview_voice("spk_001", "Hello")
        assert isinstance(audio, bytes)
        assert len(audio) > 0


class TestSaveVoiceAsset:
    @pytest.mark.asyncio
    async def test_saves_to_minio_and_creates_record(self, voice_agent, voice_repo):
        saved = MagicMock()
        saved.id = uuid.uuid4()
        voice_repo.create.return_value = saved

        with patch.object(voice_agent, "_upload_audio", new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = "projects/p1/voices/synth.wav"
            result = await voice_agent.save_voice_asset(
                project_id="00000000-0000-0000-0000-000000000001",
                character_id="00000000-0000-0000-0000-000000000002",
                audio_data=b"\x00" * 16000,
                filename="test.wav",
                provider="cosyvoice",
                speaker="spk_001",
                emotion="neutral",
                speed=1.0,
                pitch=0,
                version=1,
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_save_with_scene_context(self, voice_agent, voice_repo):
        saved = MagicMock()
        saved.id = uuid.uuid4()
        voice_repo.create.return_value = saved

        with patch.object(voice_agent, "_upload_audio", new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = "projects/p1/voices/synth.wav"
            result = await voice_agent.save_voice_asset(
                project_id="00000000-0000-0000-0000-000000000001",
                character_id="00000000-0000-0000-0000-000000000002",
                audio_data=b"\x00" * 8000,
                filename="scene_test.wav",
                provider="cosyvoice",
                speaker="spk_001",
                emotion="angry",
                speed=1.1,
                pitch=2,
                version=1,
                scene_id="00000000-0000-0000-0000-000000000003",
                dialogue_index=2,
            )
            assert result is not None


class TestEmotionLLMFallback:
    @pytest.mark.asyncio
    async def test_resolve_emotion_no_router_returns_neutral(self, voice_agent):
        tag, vector = await voice_agent._resolve_emotion_llm("Test", "calm", "complex mood")
        assert tag == "neutral"
        assert vector["pitch"] == 1.0


class TestWavHeader:
    def test_wav_header_valid(self, voice_agent):
        header = voice_agent._wav_header(16000)
        assert header[:4] == b"RIFF"
        assert header[8:12] == b"WAVE"
        assert len(header) == 44
