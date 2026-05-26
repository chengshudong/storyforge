from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from interfaces.video import VideoStatus, VideoSubmitRequest
from providers.video.cogvideox_adapter import CogVideoXAdapter


class TestCogVideoXInit:
    def test_default_base_url(self):
        adapter = CogVideoXAdapter()
        assert adapter._base_url == "http://localhost:7861"

    def test_custom_base_url(self):
        adapter = CogVideoXAdapter("http://gpu:8000/")
        assert adapter._base_url == "http://gpu:8000"


class TestCogVideoXHealth:
    @pytest.mark.asyncio
    async def test_healthy(self):
        adapter = CogVideoXAdapter()
        with patch.object(adapter, "_get_client", new_callable=AsyncMock) as mock_client:
            mock_http = AsyncMock()
            mock_http.status_code = 200
            mock_http.get = AsyncMock(return_value=mock_http)
            mock_client.return_value = mock_http
            result = await adapter.health()
            assert result is True


class TestCogVideoXSubmit:
    @pytest.mark.asyncio
    async def test_submit_with_image_base64(self):
        adapter = CogVideoXAdapter()
        with patch.object(adapter, "_get_client", new_callable=AsyncMock) as mock_client_factory:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"task_id": "cog_task_001"}
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_factory.return_value = mock_client

            import base64
            img_data = b"\x89PNG test"
            req = VideoSubmitRequest(
                prompt="cinematic video of Alice",
                image=img_data,
                image_filename="keyframe.png",
            )
            task_id = await adapter.submit(req)
            assert task_id == "cog_task_001"
            # Verify base64 was sent in payload
            call_args = mock_client.post.call_args
            assert "image_base64" in call_args.kwargs["json"]
            assert call_args.kwargs["json"]["image_base64"] == base64.b64encode(img_data).decode("ascii")


class TestCogVideoXPoll:
    @pytest.mark.asyncio
    async def test_poll_completed(self):
        adapter = CogVideoXAdapter()
        with patch.object(adapter, "_get_client", new_callable=AsyncMock) as mock_client_factory:
            mock_client = AsyncMock()
            status_resp = MagicMock()
            status_resp.json.return_value = {"status": "completed", "duration": 3.0}
            download_resp = MagicMock()
            download_resp.content = b"fake_mp4_data"
            mock_client.get = AsyncMock(side_effect=[status_resp, download_resp])
            mock_client_factory.return_value = mock_client

            result = await adapter.poll("cog_task_001")
            assert result.status == VideoStatus.DONE
            assert result.video == b"fake_mp4_data"

    @pytest.mark.asyncio
    async def test_poll_failure(self):
        adapter = CogVideoXAdapter()
        with patch.object(adapter, "_get_client", new_callable=AsyncMock) as mock_client_factory:
            mock_client = AsyncMock()
            status_resp = MagicMock()
            status_resp.json.return_value = {"status": "failed", "error": "out of memory"}
            mock_client.get = AsyncMock(return_value=status_resp)
            mock_client_factory.return_value = mock_client

            result = await adapter.poll("cog_task_001")
            assert result.status == VideoStatus.FAILED
