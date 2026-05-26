from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import create_app
from infra.database import get_db

_now = datetime.now(timezone.utc)


@pytest.fixture
def mock_video():
    video = MagicMock()
    video.id = uuid.uuid4()
    video.project_id = uuid.uuid4()
    video.scene_id = uuid.uuid4()
    video.file_path = "projects/test/videos/test.mp4"
    video.duration = 5.0
    video.resolution = "768x1152"
    video.prompt = "test prompt"
    video.negative_prompt = ""
    video.seed = 42
    video.fps = 24
    video.generation_params = {"width": 768, "height": 1152}
    video.provider = "wan21"
    video.preview_path = "projects/test/videos/test_preview.mp4"
    video.thumbnail_path = "projects/test/videos/test_thumb.jpg"
    video.batch_id = uuid.uuid4()
    video.selected = False
    video.version = 1
    video.audio_path = "projects/test/videos/test_audio.mp4"
    video.audio_duration = 3000.0
    video.file_size = 100000
    video.status = MagicMock(value="completed")
    video.created_at = _now
    video.updated_at = _now
    video.locked = False
    return video


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def client(mock_db):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: mock_db
    with TestClient(app) as c:
        yield c


# ── POST /generate ──────────────────────────────────────────────────────

class TestGenerateVideo:
    def test_generate_returns_202(self, client):
        with patch("api.v1.videos.ProjectRepository") as mock_repo:
            mock_repo.return_value.get = AsyncMock(return_value=MagicMock())
            with patch("api.v1.videos.create_job", new_callable=AsyncMock) as mock_job:
                mock_job.return_value = MagicMock(id=uuid.uuid4())
                with patch("infra.celery_app.app", MagicMock()):
                    response = client.post("/api/v1/videos/generate", json={
                        "project_id": str(uuid.uuid4()),
                    })
                    assert response.status_code == 202
                    data = response.json()
                    assert data["status"] == "pending"
                    assert "job_id" in data
                    assert "batch_id" in data

    def test_generate_project_not_found(self, client):
        with patch("api.v1.videos.ProjectRepository") as mock_repo:
            mock_repo.return_value.get = AsyncMock(return_value=None)
            response = client.post("/api/v1/videos/generate", json={
                "project_id": str(uuid.uuid4()),
            })
            assert response.status_code == 404


# ── GET / ───────────────────────────────────────────────────────────────

class TestListVideos:
    def test_list_by_project(self, client, mock_video):
        with patch("api.v1.videos.VideoRepository") as mock_repo:
            mock_repo.return_value.list_by_project = AsyncMock(return_value=[mock_video])
            response = client.get(f"/api/v1/videos?project_id={uuid.uuid4()}")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert len(data["items"]) == 1

    def test_list_by_scene(self, client, mock_video):
        with patch("api.v1.videos.VideoRepository") as mock_repo:
            mock_repo.return_value.list_by_scene = AsyncMock(return_value=[mock_video])
            response = client.get(f"/api/v1/videos?project_id={uuid.uuid4()}&scene_id={uuid.uuid4()}")
            assert response.status_code == 200

    def test_list_filter_selected(self, client, mock_video):
        mock_video.selected = True
        with patch("api.v1.videos.VideoRepository") as mock_repo:
            mock_repo.return_value.list_by_project = AsyncMock(return_value=[mock_video])
            response = client.get(f"/api/v1/videos?project_id={uuid.uuid4()}&selected=true")
            assert response.status_code == 200
            assert response.json()["items"][0]["selected"] is True


# ── GET /{id} ───────────────────────────────────────────────────────────

class TestGetVideo:
    def test_get_video_200(self, client, mock_video):
        with patch("api.v1.videos.VideoRepository") as mock_repo:
            mock_repo.return_value.get = AsyncMock(return_value=mock_video)
            response = client.get(f"/api/v1/videos/{mock_video.id}")
            assert response.status_code == 200
            data = response.json()
            assert data["provider"] == "wan21"
            assert data["fps"] == 24

    def test_get_video_404(self, client):
        with patch("api.v1.videos.VideoRepository") as mock_repo:
            mock_repo.return_value.get = AsyncMock(return_value=None)
            response = client.get(f"/api/v1/videos/{uuid.uuid4()}")
            assert response.status_code == 404


# ── GET /{id}/stream ────────────────────────────────────────────────────

class TestStreamVideo:
    def test_stream_200(self, client, mock_video):
        with patch("api.v1.videos.VideoRepository") as mock_repo:
            mock_repo.return_value.get = AsyncMock(return_value=mock_video)
            with patch("infra.minio.download_file", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = b"fake_mp4_data"
                response = client.get(f"/api/v1/videos/{mock_video.id}/stream")
                assert response.status_code == 200
                assert response.headers["content-type"] == "video/mp4"

    def test_stream_404_file_not_found(self, client, mock_video):
        with patch("api.v1.videos.VideoRepository") as mock_repo:
            mock_repo.return_value.get = AsyncMock(return_value=mock_video)
            with patch("infra.minio.download_file", side_effect=Exception("not found")):
                response = client.get(f"/api/v1/videos/{mock_video.id}/stream")
                assert response.status_code == 404


# ── GET /{id}/thumbnail ─────────────────────────────────────────────────

class TestThumbnail:
    def test_thumbnail_200(self, client, mock_video):
        with patch("api.v1.videos.VideoRepository") as mock_repo:
            mock_repo.return_value.get = AsyncMock(return_value=mock_video)
            with patch("infra.minio.download_file", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = b"\xff\xd8fake_jpg"
                response = client.get(f"/api/v1/videos/{mock_video.id}/thumbnail")
                assert response.status_code == 200
                assert response.headers["content-type"] == "image/jpeg"

    def test_thumbnail_404(self, client, mock_video):
        mock_video.thumbnail_path = None
        with patch("api.v1.videos.VideoRepository") as mock_repo:
            mock_repo.return_value.get = AsyncMock(return_value=mock_video)
            response = client.get(f"/api/v1/videos/{mock_video.id}/thumbnail")
            assert response.status_code == 404


# ── GET /{id}/preview ───────────────────────────────────────────────────

class TestPreview:
    def test_preview_200(self, client, mock_video):
        with patch("api.v1.videos.VideoRepository") as mock_repo:
            mock_repo.return_value.get = AsyncMock(return_value=mock_video)
            with patch("infra.minio.download_file", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = b"fake_preview_data"
                response = client.get(f"/api/v1/videos/{mock_video.id}/preview")
                assert response.status_code == 200
                assert response.headers["content-type"] == "video/mp4"

    def test_preview_404(self, client, mock_video):
        mock_video.preview_path = None
        with patch("api.v1.videos.VideoRepository") as mock_repo:
            mock_repo.return_value.get = AsyncMock(return_value=mock_video)
            response = client.get(f"/api/v1/videos/{mock_video.id}/preview")
            assert response.status_code == 404


# ── POST /select ────────────────────────────────────────────────────────

class TestSelectVideo:
    def test_select_200(self, client, mock_video):
        with patch("api.v1.videos.VideoRepository") as mock_repo:
            mock_repo.return_value.get = AsyncMock(return_value=mock_video)
            response = client.post("/api/v1/videos/select", json={
                "video_ids": [str(mock_video.id)],
                "selected": True,
            })
            assert response.status_code == 200
            assert response.json()["items"][0]["selected"] is True

    def test_select_404(self, client):
        with patch("api.v1.videos.VideoRepository") as mock_repo:
            mock_repo.return_value.get = AsyncMock(return_value=None)
            response = client.post("/api/v1/videos/select", json={
                "video_ids": [str(uuid.uuid4())],
            })
            assert response.status_code == 404


# ── DELETE /{id} ────────────────────────────────────────────────────────

class TestDeleteVideo:
    def test_delete_204(self, client, mock_video):
        with patch("api.v1.videos.VideoRepository") as mock_repo:
            repo_instance = mock_repo.return_value
            repo_instance.get = AsyncMock(return_value=mock_video)
            repo_instance.delete = AsyncMock()
            response = client.delete(f"/api/v1/videos/{mock_video.id}")
            assert response.status_code == 204

    def test_delete_404(self, client):
        with patch("api.v1.videos.VideoRepository") as mock_repo:
            mock_repo.return_value.get = AsyncMock(return_value=None)
            response = client.delete(f"/api/v1/videos/{uuid.uuid4()}")
            assert response.status_code == 404
