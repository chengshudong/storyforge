import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from infra.database import Base
from domain.base import TimestampMixin, UUIDMixin


class ProjectStatus(str, enum.Enum):
    PENDING = "pending"
    PARSING = "parsing"
    SUMMARIZING = "summarizing"
    EPISODES = "episodes"
    SCENES = "scenes"
    CHARACTERS = "characters"
    ASSETS = "assets"
    VOICE = "voice"
    VIDEO = "video"
    EDITING = "editing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Project(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_format: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"), default=ProjectStatus.PENDING, nullable=False
    )
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    episodes: Mapped[list["Episode"]] = relationship("Episode", back_populates="project", cascade="all, delete-orphan")
    characters: Mapped[list["Character"]] = relationship("Character", back_populates="project", cascade="all, delete-orphan")
    assets: Mapped[list["Asset"]] = relationship("Asset", back_populates="project", cascade="all, delete-orphan")
    voices: Mapped[list["Voice"]] = relationship("Voice", back_populates="project", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="project", cascade="all, delete-orphan")


class Episode(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "episodes"

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"), default=ProjectStatus.PENDING, nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="episodes")
    scenes: Mapped[list["Scene"]] = relationship("Scene", back_populates="episode", cascade="all, delete-orphan")


class Scene(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "scenes"

    episode_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("episodes.id"), nullable=False)
    scene_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    dialogue: Mapped[list | None] = mapped_column(JSON, nullable=True)
    storyboard: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"), default=ProjectStatus.PENDING, nullable=False
    )

    episode: Mapped["Episode"] = relationship("Episode", back_populates="scenes")
    assets: Mapped[list["Asset"]] = relationship("Asset", back_populates="scene")
    videos: Mapped[list["Video"]] = relationship("Video", back_populates="scene", cascade="all, delete-orphan")


class Character(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "characters"

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    traits: Mapped[list | None] = mapped_column(JSON, nullable=True)
    profile: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"), default=ProjectStatus.PENDING, nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="characters")
    assets: Mapped[list["Asset"]] = relationship("Asset", back_populates="character")
    voices: Mapped[list["Voice"]] = relationship("Voice", back_populates="character", cascade="all, delete-orphan")
    versions: Mapped[list["CharacterVersion"]] = relationship("CharacterVersion", back_populates="character", cascade="all, delete-orphan")


class CharacterVersion(Base, UUIDMixin):
    __tablename__ = "character_versions"

    character_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("characters.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    diff: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    character: Mapped["Character"] = relationship("Character", back_populates="versions")


class Prop(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "props"

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    scene_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("scenes.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    prop_type: Mapped[str | None] = mapped_column(String(50), nullable=True)


class AssetType(str, enum.Enum):
    IMAGE = "image"
    CHARACTER_IMAGE = "character_image"
    STORYBOARD = "storyboard"
    COVER = "cover"
    OTHER = "other"


class Asset(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "assets"

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    character_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("characters.id"), nullable=True)
    scene_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("scenes.id"), nullable=True)
    asset_type: Mapped[AssetType] = mapped_column(Enum(AssetType, name="asset_type"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    variation_of: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("assets.id"), nullable=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    selected: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    asset_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"), default=ProjectStatus.PENDING, nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="assets")
    character: Mapped["Character | None"] = relationship("Character", back_populates="assets")
    scene: Mapped["Scene | None"] = relationship("Scene", back_populates="assets")


class GenerationBatch(Base, UUIDMixin):
    __tablename__ = "generation_batches"

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    total_assets: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    completed_assets: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Voice(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "voices"

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    character_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("characters.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"), default=ProjectStatus.PENDING, nullable=False
    )

    project: Mapped["Project"] = relationship("Project", back_populates="voices")
    character: Mapped["Character"] = relationship("Character", back_populates="voices")


class Video(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "videos"

    scene_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("scenes.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status"), default=ProjectStatus.PENDING, nullable=False
    )

    scene: Mapped["Scene"] = relationship("Scene", back_populates="videos")


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "jobs"

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id"), nullable=False)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status"), default=JobStatus.PENDING, nullable=False
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="jobs")
    logs: Mapped[list["Log"]] = relationship("Log", back_populates="job", cascade="all, delete-orphan")


class Log(Base, UUIDMixin):
    __tablename__ = "logs"

    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("jobs.id"), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="INFO")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    job: Mapped["Job"] = relationship("Job", back_populates="logs")
