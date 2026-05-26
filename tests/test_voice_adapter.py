from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from interfaces.voice import SynthesisRequest, VoiceStatus
from providers.voice.cosyvoice_adapter import CosyVoiceAdapter


class TestCosyVoiceInit:
    def test_default_base_url(self):
        adapter = CosyVoiceAdapter()
        assert adapter._base_url == "http://localhost:5001"

    def test_custom_base_url_trailing_slash(self):
        adapter = CosyVoiceAdapter("http://example.com:8000/")
        assert adapter._base_url == "http://example.com:8000"


class TestCosyVoiceHealth:
    @pytest.mark.asyncio
    async def test_healthy(self):
        adapter = CosyVoiceAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_req.return_value = mock_response
            result = await adapter.health()
            assert result is True

    @pytest.mark.asyncio
    async def test_unhealthy_connection_refused(self):
        adapter = CosyVoiceAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("Connection refused")
            result = await adapter.health()
            assert result is False


class TestCosyVoiceSynthesize:
    @pytest.mark.asyncio
    async def test_successful_synthesis(self):
        adapter = CosyVoiceAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_response = MagicMock()
            mock_response.content = b"\x00" * 32000  # ~1s of 16-bit mono 16kHz
            mock_req.return_value = mock_response

            req = SynthesisRequest(text="Hello", speaker="spk_001", emotion="neutral")
            result = await adapter.synthesize(req)
            assert result.status == VoiceStatus.DONE
            assert result.audio == b"\x00" * 32000
            assert result.duration_ms == 1000.0  # 32000 bytes / 32000 bytes/sec * 1000

    @pytest.mark.asyncio
    async def test_synthesis_failure(self):
        adapter = CosyVoiceAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("TTS engine error")

            req = SynthesisRequest(text="Hello", speaker="spk_001")
            result = await adapter.synthesize(req)
            assert result.status == VoiceStatus.FAILED
            assert result.error is not None

    @pytest.mark.asyncio
    async def test_emotion_vector_passed(self):
        adapter = CosyVoiceAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_response = MagicMock()
            mock_response.content = b"\x00" * 16000
            mock_req.return_value = mock_response

            req = SynthesisRequest(
                text="Hello", speaker="spk_001", emotion="sad",
                emotion_vector={"pitch": 0.85, "rhythm": 0.9, "timbre": 0.4},
            )
            result = await adapter.synthesize(req)
            assert result.status == VoiceStatus.DONE


class TestCosyVoiceClone:
    @pytest.mark.asyncio
    async def test_successful_clone(self):
        adapter = CosyVoiceAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_response = MagicMock()
            mock_response.json.return_value = {"voice_id": "spk_new_001"}
            mock_req.return_value = mock_response

            speaker = await adapter.clone_voice("TestChar", b"fake_audio_data")
            assert speaker == "spk_new_001"

    @pytest.mark.asyncio
    async def test_clone_with_reference_text(self):
        adapter = CosyVoiceAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_response = MagicMock()
            mock_response.json.return_value = {"voice_id": "spk_new_002"}
            mock_req.return_value = mock_response

            speaker = await adapter.clone_voice("TestChar", b"audio", "reference text here")
            assert speaker == "spk_new_002"


class TestCosyVoiceListDelete:
    @pytest.mark.asyncio
    async def test_list_speakers(self):
        adapter = CosyVoiceAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_response = MagicMock()
            mock_response.json.return_value = ["spk_001", "spk_002"]
            mock_req.return_value = mock_response
            speakers = await adapter.list_speakers()
            assert len(speakers) == 2

    @pytest.mark.asyncio
    async def test_list_speakers_failure_returns_empty(self):
        adapter = CosyVoiceAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = Exception("down")
            speakers = await adapter.list_speakers()
            assert speakers == []
