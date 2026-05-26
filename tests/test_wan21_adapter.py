from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from interfaces.video import VideoStatus, VideoSubmitRequest
from providers.video.wan21_adapter import Wan21Adapter


class TestWan21Init:
    def test_default_base_url(self):
        adapter = Wan21Adapter()
        assert adapter._base_url == "http://localhost:7860"

    def test_custom_base_url_trailing_slash(self):
        adapter = Wan21Adapter("http://example.com:8000/")
        assert adapter._base_url == "http://example.com:8000"


class TestWan21Health:
    @pytest.mark.asyncio
    async def test_healthy(self):
        adapter = Wan21Adapter()
        with patch.object(adapter, "_get_client", new_callable=AsyncMock) as mock_client:
            mock_http = AsyncMock()
            mock_http.status_code = 200
            mock_http.get = AsyncMock(return_value=mock_http)
            mock_client.return_value = mock_http

            result = await adapter.health()
            assert result is True

    @pytest.mark.asyncio
    async def test_unhealthy_connection_refused(self):
        adapter = Wan21Adapter()
        with patch.object(adapter, "_get_client", new_callable=AsyncMock) as mock_client:
            mock_client.side_effect = Exception("Connection refused")
            result = await adapter.health()
            assert result is False


class TestWan21Submit:
    @pytest.mark.asyncio
    async def test_submit_returns_task_id(self):
        adapter = Wan21Adapter()
        with patch.object(adapter, "_get_client", new_callable=AsyncMock) as mock_client_factory:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"task_id": "task_abc123"}
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_factory.return_value = mock_client

            req = VideoSubmitRequest(prompt="cinematic video of Alice")
            task_id = await adapter.submit(req)
            assert task_id == "task_abc123"

    @pytest.mark.asyncio
    async def test_submit_with_image(self):
        adapter = Wan21Adapter()
        with patch.object(adapter, "_get_client", new_callable=AsyncMock) as mock_client_factory:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.json.return_value = {"task_id": "task_image"}
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_factory.return_value = mock_client

            req = VideoSubmitRequest(
                prompt="test",
                image=b"\x89PNG fake",
                image_filename="alice_keyframe.png",
            )
            task_id = await adapter.submit(req)
            assert task_id == "task_image"


class TestWan21Poll:
    @pytest.mark.asyncio
    async def test_poll_completed(self):
        adapter = Wan21Adapter()
        with patch.object(adapter, "_get_client", new_callable=AsyncMock) as mock_client_factory:
            mock_client = AsyncMock()

            status_resp = MagicMock()
            status_resp.json.return_value = {"status": "completed", "duration": 5.0}
            download_resp = MagicMock()
            download_resp.content = b"\x00" * 5000

            mock_client.get = AsyncMock(side_effect=[status_resp, download_resp])
            mock_client_factory.return_value = mock_client

            result = await adapter.poll("task_abc")
            assert result.status == VideoStatus.DONE
            assert result.video == b"\x00" * 5000
            assert result.duration_s == 5.0

    @pytest.mark.asyncio
    async def test_poll_failed(self):
        adapter = Wan21Adapter()
        with patch.object(adapter, "_get_client", new_callable=AsyncMock) as mock_client_factory:
            mock_client = AsyncMock()
            status_resp = MagicMock()
            status_resp.json.return_value = {"status": "failed", "error": "GPU OOM"}
            mock_client.get = AsyncMock(return_value=status_resp)
            mock_client_factory.return_value = mock_client

            result = await adapter.poll("task_abc")
            assert result.status == VideoStatus.FAILED
            assert result.error == "GPU OOM"

    @pytest.mark.asyncio
    async def test_poll_timeout(self):
        adapter = Wan21Adapter()
        with patch.object(adapter, "_get_client", new_callable=AsyncMock) as mock_client_factory:
            mock_client = AsyncMock()
            pending_resp = MagicMock()
            pending_resp.json.return_value = {"status": "running"}
            mock_client.get = AsyncMock(return_value=pending_resp)
            mock_client_factory.return_value = mock_client

            # Override poll constants for fast test
            with patch("providers.video.wan21_adapter.WAN21_POLL_MAX", 2), \
                 patch("providers.video.wan21_adapter.WAN21_POLL_INTERVAL", 0.001):
                result = await adapter.poll("task_timeout")
                assert result.status == VideoStatus.FAILED
                assert "timeout" in result.error.lower()


class TestWan21Cancel:
    @pytest.mark.asyncio
    async def test_cancel_success(self):
        adapter = Wan21Adapter()
        with patch.object(adapter, "_get_client", new_callable=AsyncMock) as mock_client_factory:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_factory.return_value = mock_client

            result = await adapter.cancel("task_abc")
            assert result is True

    @pytest.mark.asyncio
    async def test_cancel_failure(self):
        adapter = Wan21Adapter()
        with patch.object(adapter, "_get_client", new_callable=AsyncMock) as mock_client_factory:
            mock_client_factory.side_effect = Exception("down")
            result = await adapter.cancel("task_abc")
            assert result is False
