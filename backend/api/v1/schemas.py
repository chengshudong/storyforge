import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from domain.models import JobStatus, ProjectStatus


class ProjectCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    source_file: Optional[str] = None
    source_format: Optional[str] = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    source_file: Optional[str]
    source_format: Optional[str]
    status: ProjectStatus
    meta: Optional[dict]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    items: list[ProjectResponse]
    total: int
    offset: int
    limit: int


class JobResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    job_type: str
    status: JobStatus
    progress: int
    result: Optional[dict]
    error: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    offset: int
    limit: int


class ParseUploadResponse(BaseModel):
    project_id: uuid.UUID
    title: str
    char_count: int
    chunk_count: int
    entities: dict
    collection: str

    model_config = {"from_attributes": True}


class StoryGenerateRequest(BaseModel):
    project_id: uuid.UUID
    regenerate: bool = False


class StoryGenerateResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    message: str


class EpisodeResponse(BaseModel):
    id: uuid.UUID
    episode_number: int
    title: str
    summary: str | None = None
    status: str
    chapter_range: list[int] | None = None
    cliffhanger: str | None = None
    key_scenes: list[str] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EpisodeListResponse(BaseModel):
    items: list[EpisodeResponse]
    total: int
    offset: int
    limit: int


class SceneStoryboardSchema(BaseModel):
    camera: str | None = None
    duration: int | None = None
    emotion: str | None = None
    location: str | None = None
    props: list[str] = []
    transition: str | None = None
    asset_refs: list[str] = []
    character_actions: dict[str, str] = {}
    characters_present: list[str] = []
    locked: bool = False


class SceneResponse(BaseModel):
    id: uuid.UUID
    episode_id: uuid.UUID
    scene_number: int
    title: str | None = None
    description: str | None = None
    dialogue: list | None = None
    storyboard: SceneStoryboardSchema | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SceneListResponse(BaseModel):
    items: list[SceneResponse]
    total: int
    offset: int
    limit: int


class SceneGenerateRequest(BaseModel):
    regenerate: bool = False


class SceneGenerateResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    message: str


class SceneEditRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    dialogue: list | None = None
    storyboard: SceneStoryboardSchema | None = None
    feedback: str | None = None


# ── Character schemas (TASK_006) ──────────────────────────────────────────


class CharacterProfileSchema(BaseModel):
    appearance: dict | None = None
    voice_profile: dict | None = None
    personality: dict | None = None
    emotion_range: dict | None = None
    costume_style: dict | None = None
    relationship_graph: dict | None = None
    backstory: str | None = None


class CharacterVersionSchema(BaseModel):
    id: uuid.UUID
    version_number: int
    profile_snapshot: dict
    diff: dict | None = None
    created_at: datetime
    created_by: str | None = None

    model_config = {"from_attributes": True}


class CharacterResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None = None
    role: str | None = None
    traits: list | None = None
    profile: CharacterProfileSchema | None = None
    version: int = 1
    locked: bool = False
    locked_at: datetime | None = None
    locked_by: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CharacterListResponse(BaseModel):
    items: list[CharacterResponse]
    total: int
    offset: int
    limit: int


class CharacterGenerateRequest(BaseModel):
    project_id: uuid.UUID
    regenerate: bool = False


class CharacterGenerateResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    message: str


class CharacterSelectRequest(BaseModel):
    character_ids: list[uuid.UUID]
    approved: bool = True


class CharacterEditRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    role: str | None = None
    traits: list | None = None
    profile: CharacterProfileSchema | None = None
    unlock: bool = False
    feedback: str | None = None


class CharacterVersionListResponse(BaseModel):
    items: list[CharacterVersionSchema]
    total: int


class CharacterRollbackRequest(BaseModel):
    version: int
