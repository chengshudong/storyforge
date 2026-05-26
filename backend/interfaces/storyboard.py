from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class SceneGenerationState:
    project_id: str
    episode_id: str
    episode: dict | None = None
    episode_number: int = 0
    characters: list[dict] = field(default_factory=list)
    timeline: list[dict] | None = None
    world_setting: dict | None = None
    relationships: list[dict] | None = None
    previous_episode_scenes: list[dict] = field(default_factory=list)
    scene_beats: list[dict] | None = None
    scenes: list[dict] | None = None
    validation: dict | None = None
    validation_passed: bool = True
    saved_scene_ids: list[str] = field(default_factory=list)
    status: str = "pending"
    error: str | None = None


class StoryboardEngine(ABC):
    """Interface for storyboard generation providers.

    Per OSS_REGISTRY: Provider → Adapter → Interface → Agent → Workflow → API.
    LangGraph serves as the workflow provider for TASK_005.
    """

    @abstractmethod
    async def run(self, state: SceneGenerationState) -> dict:
        """Execute storyboard generation. Returns final state dict."""

    @abstractmethod
    async def resume(self, checkpoint_id: str) -> dict:
        """Resume from a checkpoint."""

    @abstractmethod
    async def checkpoint(self) -> str:
        """Return current checkpoint ID."""
