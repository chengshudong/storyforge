from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.image_agent import ImageAgent
from api.v1.schemas import AssetGenerationParams
from interfaces.image import ImageProvider, ImageResult, ImageStatus


class FakeProvider(ImageProvider):
    """In-memory fake for ImageAgent tests. No real ComfyUI needed."""

    def __init__(self) -> None:
        self.prompts: list[dict] = []
        self.uploads: list[tuple[str, bytes]] = []
        self._counter = 0
        self._poll_results: dict[str, ImageResult] = {}

    async def generate(self, workflow: dict) -> str:
        self._counter += 1
        pid = f"prompt-{self._counter}"
        self.prompts.append({"id": pid, "workflow": workflow})
        return pid

    async def poll(self, prompt_id: str) -> ImageResult:
        if prompt_id in self._poll_results:
            return self._poll_results[prompt_id]
        return ImageResult(
            prompt_id=prompt_id,
            status=ImageStatus.DONE,
            images=[b"fake_png_data"],
            filenames=["output_00001_.png"],
        )

    async def upload_image(self, filename: str, data: bytes) -> str:
        self.uploads.append((filename, data))
        return filename

    async def health(self) -> bool:
        return True

    def set_poll_result(self, prompt_id: str, result: ImageResult) -> None:
        self._poll_results[prompt_id] = result


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def agent(provider: FakeProvider) -> ImageAgent:
    return ImageAgent(image_provider=provider, asset_repo=None)


@pytest.fixture
def params() -> AssetGenerationParams:
    return AssetGenerationParams(width=512, height=768, steps=20, cfg=7.0, sampler="euler")


class TestGenerateCharRef:
    @pytest.mark.asyncio
    async def test_submits_workflow_with_correct_prompt(self, agent: ImageAgent, provider: FakeProvider, params: AssetGenerationParams):
        profile = {
            "appearance": {"age_estimate": "teen", "hair": "red, long"},
            "costume_style": {"era": "medieval", "color_palette": ["green"]},
        }
        pid = await agent.generate_char_ref("Arya", profile, 123, params)
        assert pid == "prompt-1"
        wf = provider.prompts[0]["workflow"]
        positive = wf["6"]["inputs"]["text"]
        assert "portrait photograph of Arya" in positive
        assert "teen" in positive
        assert "medieval" in positive

    @pytest.mark.asyncio
    async def test_default_params_used(self, agent: ImageAgent, provider: FakeProvider):
        pid = await agent.generate_char_ref("Bob", None, 1, AssetGenerationParams())
        assert pid == "prompt-1"


class TestGenerateCharScene:
    @pytest.mark.asyncio
    async def test_submits_instantid_workflow(self, agent: ImageAgent, provider: FakeProvider, params: AssetGenerationParams):
        profile = {
            "appearance": {"build": "slender"},
            "costume_style": {"style": "armor"},
        }
        storyboard = {
            "camera": "medium",
            "emotion": "angry",
            "location": "castle hall",
        }
        pid = await agent.generate_char_scene("Knight", profile, storyboard, "ref_knight.png", 99, params)
        assert pid == "prompt-1"
        wf = provider.prompts[0]["workflow"]
        assert "1" in wf  # LoadImage
        assert "2" in wf  # IPAdapterInstantID
        assert wf["1"]["inputs"]["image"] == "ref_knight.png"
        positive = wf["6"]["inputs"]["text"]
        assert "Knight" in positive
        assert "angry expression" in positive
        assert "castle hall" in positive

    @pytest.mark.asyncio
    async def test_action_included_in_prompt(self, agent: ImageAgent, provider: FakeProvider, params: AssetGenerationParams):
        await agent.generate_char_scene("Hero", {}, {}, "ref.png", 1, params, action="drawing a sword")
        wf = provider.prompts[0]["workflow"]
        assert "drawing a sword" in wf["6"]["inputs"]["text"]


class TestGenerateBackground:
    @pytest.mark.asyncio
    async def test_submits_basic_workflow(self, agent: ImageAgent, provider: FakeProvider, params: AssetGenerationParams):
        storyboard = {"location": "misty forest", "emotion": "eerie", "props": ["old lantern"]}
        pid = await agent.generate_background(storyboard, 42, params)
        assert pid == "prompt-1"
        positive = provider.prompts[0]["workflow"]["6"]["inputs"]["text"]
        assert "misty forest" in positive
        assert "eerie atmosphere" in positive

    @pytest.mark.asyncio
    async def test_empty_storyboard_defaults(self, agent: ImageAgent, provider: FakeProvider):
        pid = await agent.generate_background({}, 1, AssetGenerationParams())
        assert pid == "prompt-1"


class TestGenerateProp:
    @pytest.mark.asyncio
    async def test_submits_basic_workflow(self, agent: ImageAgent, provider: FakeProvider, params: AssetGenerationParams):
        pid = await agent.generate_prop("Crown", "Golden crown with rubies", "jewelry", 7, params)
        assert pid == "prompt-1"
        positive = provider.prompts[0]["workflow"]["6"]["inputs"]["text"]
        assert "Golden crown with rubies" in positive

    @pytest.mark.asyncio
    async def test_no_description(self, agent: ImageAgent, provider: FakeProvider, params: AssetGenerationParams):
        pid = await agent.generate_prop("Crown", "", "", 1, params)
        assert pid == "prompt-1"


class TestGenerateCover:
    @pytest.mark.asyncio
    async def test_submits_basic_workflow(self, agent: ImageAgent, provider: FakeProvider, params: AssetGenerationParams):
        pid = await agent.generate_cover("Epic Tale", "A story of heroes", "ancient Greece", "Achilles and Hector", "dramatic", 100, params)
        assert pid == "prompt-1"
        positive = provider.prompts[0]["workflow"]["6"]["inputs"]["text"]
        assert "Epic Tale" in positive
        assert "A story of heroes" in positive
        assert "ancient Greece" in positive

    @pytest.mark.asyncio
    async def test_minimal_fields(self, agent: ImageAgent, provider: FakeProvider, params: AssetGenerationParams):
        pid = await agent.generate_cover("Untitled", seed=1, params=params)
        assert pid == "prompt-1"


class TestPoll:
    @pytest.mark.asyncio
    async def test_returns_result(self, agent: ImageAgent, provider: FakeProvider):
        result = await agent.poll("prompt-1")
        assert result.status == ImageStatus.DONE
        assert result.images == [b"fake_png_data"]

    @pytest.mark.asyncio
    async def test_returns_failure(self, agent: ImageAgent, provider: FakeProvider):
        provider.set_poll_result("fail-1", ImageResult("fail-1", ImageStatus.FAILED, error="timeout"))
        result = await agent.poll("fail-1")
        assert result.status == ImageStatus.FAILED


class TestUploadFaceRef:
    @pytest.mark.asyncio
    async def test_delegates_to_provider(self, agent: ImageAgent, provider: FakeProvider):
        result = await agent.upload_face_ref("arthur_ref.png", b"image_bytes")
        assert result == "arthur_ref.png"
        assert provider.uploads == [("arthur_ref.png", b"image_bytes")]


class TestSaveAsset:
    @pytest.mark.asyncio
    @patch("agents.image_agent.upload_file", new_callable=AsyncMock)
    async def test_saves_to_minio_and_creates_record(self, mock_upload: AsyncMock, provider: FakeProvider):
        from repository.asset_repository import AssetRepository
        from domain.models import Asset, AssetType

        mock_repo = MagicMock(spec=AssetRepository)
        mock_repo.create = AsyncMock()
        saved_asset = Asset(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            asset_type=AssetType.CHARACTER_IMAGE,
            file_path="projects/x/assets/test.png",
            file_size=1024,
            status="completed",
        )
        mock_repo.create.return_value = saved_asset

        agent = ImageAgent(provider, mock_repo)
        pid = uuid.uuid4()
        result = await agent.save_asset(
            project_id=pid,
            asset_type=AssetType.CHARACTER_IMAGE,
            image_data=b"fake_image",
            filename="arthur_ref.png",
            prompt="a knight portrait",
            negative_prompt="low quality",
            seed=42,
            params_dict={"steps": 20},
        )

        mock_upload.assert_awaited_once()
        mock_repo.create.assert_awaited_once()
        assert result == saved_asset
