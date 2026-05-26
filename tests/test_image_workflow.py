from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.v1.schemas import AssetGenerationParams
from interfaces.image import ImageProvider, ImageResult, ImageStatus
from workflows.image_generation import (
    PHASE_BG,
    PHASE_CHAR_REF,
    PHASE_CHAR_SCENE,
    PHASE_COVER,
    PHASE_PROP,
    PHASE_UPLOAD,
    ImageGenerationState,
    build_image_workflow,
)


class FakeProvider(ImageProvider):
    def __init__(self) -> None:
        self.prompts: list[dict] = []
        self.uploads: list[tuple[str, bytes]] = []
        self._counter = 0
        self._fail_after: int | None = None

    async def generate(self, workflow: dict) -> str:
        if self._fail_after is not None:
            self._fail_after -= 1
            if self._fail_after < 0:
                raise RuntimeError("simulated provider failure")
        self._counter += 1
        pid = f"prompt-{self._counter}"
        self.prompts.append({"id": pid, "workflow": workflow})
        return pid

    async def poll(self, prompt_id: str) -> ImageResult:
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


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def mock_asset_repo() -> MagicMock:
    from domain.models import Asset
    repo = MagicMock()
    saved = Asset(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        asset_type="character_image",
        file_path="test.png",
        file_size=100,
        status="completed",
    )
    repo.create = AsyncMock(return_value=saved)
    return repo


@pytest.fixture
def agent(provider: FakeProvider, mock_asset_repo: MagicMock) -> MagicMock:
    from agents.image_agent import ImageAgent
    return ImageAgent(provider, mock_asset_repo)


@pytest.fixture
def char_data() -> list[dict]:
    return [
        {
            "id": str(uuid.uuid4()),
            "name": "Hero",
            "profile": {
                "appearance": {"age_estimate": "young", "build": "athletic"},
                "costume_style": {"era": "fantasy", "style": "armor"},
            },
            "role": "protagonist",
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Villain",
            "profile": {
                "appearance": {"age_estimate": "middle-aged", "build": "tall"},
                "costume_style": {"era": "fantasy", "style": "dark robes"},
            },
            "role": "antagonist",
        },
    ]


@pytest.fixture
def scene_data() -> list[dict]:
    return [
        {
            "id": str(uuid.uuid4()),
            "title": "The Confrontation",
            "storyboard": {
                "camera": "wide shot",
                "emotion": "tense",
                "location": "castle throne room",
                "characters_present": ["Hero", "Villain"],
                "character_actions": {"Hero": "drawing sword", "Villain": "laughing"},
                "props": ["crown", "throne"],
            },
        },
    ]


@pytest.fixture
def prop_data() -> list[dict]:
    return [
        {"name": "Magic Crown", "description": "Golden crown with glowing gem", "prop_type": "jewelry"},
        {"name": "Ancient Throne", "description": "Stone throne with runes", "prop_type": "furniture"},
    ]


class TestImageGenerationState:
    def test_defaults(self):
        s = ImageGenerationState(project_id="test-1")
        assert s.project_id == "test-1"
        assert s.variant_count == 4
        assert s.status == "pending"
        assert s.phases == [PHASE_CHAR_REF, PHASE_CHAR_SCENE, PHASE_BG, PHASE_PROP]

    def test_custom_phases(self):
        s = ImageGenerationState(project_id="00000000-0000-0000-0000-000000000002", phases=[PHASE_COVER])
        assert s.phases == [PHASE_COVER]


class TestBuildWorkflow:
    def test_graph_compiles(self, agent, mock_asset_repo):
        graph = build_image_workflow(agent, mock_asset_repo)
        assert graph is not None

    @pytest.mark.asyncio
    @patch("agents.image_agent.upload_file", new_callable=AsyncMock)
    async def test_char_ref_only(self, mock_upload, agent, mock_asset_repo, char_data):
        workflow = build_image_workflow(agent, mock_asset_repo)
        state = ImageGenerationState(
            project_id="00000000-0000-0000-0000-000000000001",
            characters=char_data,
            phases=[PHASE_CHAR_REF],
            variant_count=1,
            params=AssetGenerationParams(width=512, height=768, steps=20),
        )
        config = {"configurable": {"thread_id": "test_char_ref_only"}}
        final = None
        async for event in workflow.astream(state, config):
            for node_output in event.values():
                if isinstance(node_output, dict):
                    final = node_output
        assert final is not None
        assert final.get("status") == "done"
        assert final.get("total_generated", 0) > 0

    @pytest.mark.asyncio
    @patch("agents.image_agent.upload_file", new_callable=AsyncMock)
    async def test_all_phases(self, mock_upload, agent, mock_asset_repo, char_data, scene_data, prop_data):
        workflow = build_image_workflow(agent, mock_asset_repo)
        state = ImageGenerationState(
            project_id="00000000-0000-0000-0000-000000000001",
            characters=char_data,
            scenes=scene_data,
            props=prop_data,
            phases=[PHASE_CHAR_REF, PHASE_UPLOAD, PHASE_CHAR_SCENE, PHASE_BG, PHASE_PROP],
            variant_count=1,
            params=AssetGenerationParams(width=512, height=768, steps=20),
        )
        config = {"configurable": {"thread_id": "test_all_phases"}}
        final = None
        async for event in workflow.astream(state, config):
            for node_output in event.values():
                if isinstance(node_output, dict):
                    final = node_output
        assert final is not None
        assert final.get("status") == "done"

    @pytest.mark.asyncio
    @patch("agents.image_agent.upload_file", new_callable=AsyncMock)
    async def test_phase_skip(self, mock_upload, agent, mock_asset_repo, char_data):
        """Phases not in the list should be skipped."""
        workflow = build_image_workflow(agent, mock_asset_repo)
        state = ImageGenerationState(
            project_id="00000000-0000-0000-0000-000000000001",
            characters=char_data,
            phases=[PHASE_COVER],  # Only cover, all others skipped
            variant_count=1,
            project_meta={"title": "Test Project"},
        )
        config = {"configurable": {"thread_id": "test_skip"}}
        final = None
        async for event in workflow.astream(state, config):
            for node_output in event.values():
                if isinstance(node_output, dict):
                    final = node_output
        assert final is not None
        assert final.get("status") == "done"
