import uuid
from dataclasses import dataclass, field
from typing import Optional

from domain.models import (
    Project,
    Episode,
    Scene,
    Character,
    Asset,
    Voice,
    Video,
    Job,
    ProjectStatus,
)


@dataclass
class ProjectState:
    project: Optional[Project] = None
    episodes: list[Episode] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    characters: list[Character] = field(default_factory=list)
    assets: list[Asset] = field(default_factory=list)
    voices: list[Voice] = field(default_factory=list)
    videos: list[Video] = field(default_factory=list)
    jobs: list[Job] = field(default_factory=list)

    @property
    def project_id(self) -> uuid.UUID | None:
        return self.project.id if self.project else None

    @property
    def status(self) -> ProjectStatus | None:
        return self.project.status if self.project else None

    def to_dict(self) -> dict:
        return {
            "project_id": str(self.project_id) if self.project_id else None,
            "status": self.status.value if self.status else None,
            "episode_count": len(self.episodes),
            "scene_count": len(self.scenes),
            "character_count": len(self.characters),
            "asset_count": len(self.assets),
            "voice_count": len(self.voices),
            "video_count": len(self.videos),
            "job_count": len(self.jobs),
        }
