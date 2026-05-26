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


# ── Asset / Image schemas (TASK_007) ─────────────────────────────────────


class AssetGenerationParams(BaseModel):
    checkpoint: str | None = None
    steps: int = 25
    cfg: float = 7.5
    sampler: str = "dpmpp_2m"
    width: int = 768
    height: int = 1152


class AssetResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    character_id: uuid.UUID | None = None
    scene_id: uuid.UUID | None = None
    asset_type: str
    file_path: str
    file_size: int | None = None
    prompt: str | None = None
    negative_prompt: str | None = None
    seed: int | None = None
    generation_params: dict | None = None
    variation_of: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    selected: bool = False
    favorite: bool = False
    locked: bool = False
    locked_at: datetime | None = None
    asset_ref: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    total: int
    offset: int
    limit: int


class AssetGenerateRequest(BaseModel):
    project_id: uuid.UUID
    regenerate: bool = False
    variant_count: int = 4
    phases: list[str] = ["char_ref", "char_scene", "bg", "prop"]


class AssetGenerateResponse(BaseModel):
    job_id: uuid.UUID
    batch_id: uuid.UUID | None = None
    status: str
    message: str


class AssetSelectRequest(BaseModel):
    asset_ids: list[uuid.UUID]
    selected: bool = True


class AssetFavoriteRequest(BaseModel):
    asset_ids: list[uuid.UUID]
    favorite: bool = True


class AssetEditRequest(BaseModel):
    locked: bool | None = None
    feedback: str | None = None
    regenerate: bool = False


# ── Voice schemas (TASK_008) ────────────────────────────────────────────────


class VoiceGenerateRequest(BaseModel):
    project_id: uuid.UUID
    regenerate: bool = False
    phases: list[str] = ["clone", "synthesize", "preview"]


class VoiceGenerateResponse(BaseModel):
    job_id: uuid.UUID
    batch_id: uuid.UUID
    status: str
    message: str


class VoiceResponse(BaseModel):
    voice_id: uuid.UUID
    character_id: uuid.UUID
    provider: str = ""
    speaker: str = ""
    speed: float = 1.0
    pitch: int = 0
    emotion: str = "neutral"
    version: int = 1
    selected: bool = False
    file_path: str
    file_size: int | None = None
    duration_ms: float | None = None
    preview_path: str | None = None
    reference_audio_path: str | None = None
    scene_id: uuid.UUID | None = None
    dialogue_index: int | None = None
    voice_params: dict | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VoiceListResponse(BaseModel):
    items: list[VoiceResponse]
    total: int
    offset: int
    limit: int


# ── Video schemas (TASK_009) ────────────────────────────────────────────────


class VideoGenerationParams(BaseModel):
    guidance_scale: float = 7.5
    width: int = 768
    height: int = 1152
    steps: int = 25
    motion_bucket_id: int = 127


class VideoGenerateRequest(BaseModel):
    project_id: uuid.UUID
    regenerate: bool = False
    variant_count: int = 1
    phases: list[str] = ["init", "submit", "poll", "composite", "save"]


class VideoGenerateResponse(BaseModel):
    job_id: uuid.UUID
    batch_id: uuid.UUID
    status: str
    message: str


class VideoResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    scene_id: uuid.UUID
    file_path: str
    duration: float | None = None
    resolution: str | None = None
    prompt: str | None = None
    negative_prompt: str | None = None
    seed: int | None = None
    fps: int = 24
    generation_params: dict | None = None
    provider: str | None = None
    preview_path: str | None = None
    thumbnail_path: str | None = None
    batch_id: uuid.UUID | None = None
    selected: bool = False
    version: int = 1
    audio_path: str | None = None
    audio_duration: float | None = None
    file_size: int | None = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VideoListResponse(BaseModel):
    items: list[VideoResponse]
    total: int
    offset: int
    limit: int


class VideoSelectRequest(BaseModel):
    video_ids: list[uuid.UUID]
    selected: bool = True
