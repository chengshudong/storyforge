"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── Enum types (native PostgreSQL enums) ──
project_status_enum = sa.Enum(
    "PENDING", "PARSING", "SUMMARIZING", "EPISODES", "SCENES",
    "CHARACTERS", "ASSETS", "VOICE", "VIDEO", "EDITING",
    "COMPLETED", "FAILED", "CANCELLED",
    name="project_status",
    create_type=True,
)

job_status_enum = sa.Enum(
    "PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED",
    name="job_status",
    create_type=True,
)

asset_type_enum = sa.Enum(
    "IMAGE", "CHARACTER_IMAGE", "STORYBOARD", "OTHER",
    name="asset_type",
    create_type=True,
)


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_file", sa.String(500), nullable=True),
        sa.Column("source_format", sa.String(10), nullable=True),
        sa.Column("status", project_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("meta", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "episodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("status", project_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "characters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("role", sa.String(50), nullable=True),
        sa.Column("traits", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("status", project_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "scenes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("episode_id", sa.Uuid(), sa.ForeignKey("episodes.id"), nullable=False),
        sa.Column("scene_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("dialogue", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("status", project_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "props",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("scene_id", sa.Uuid(), sa.ForeignKey("scenes.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prop_type", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("character_id", sa.Uuid(), sa.ForeignKey("characters.id"), nullable=True),
        sa.Column("scene_id", sa.Uuid(), sa.ForeignKey("scenes.id"), nullable=True),
        sa.Column("asset_type", asset_type_enum, nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("status", project_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "voices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("character_id", sa.Uuid(), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("status", project_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "videos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scene_id", sa.Uuid(), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.Column("status", project_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("status", job_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("level", sa.String(20), nullable=False, server_default="INFO"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("logs")
    op.drop_table("jobs")
    op.drop_table("videos")
    op.drop_table("voices")
    op.drop_table("assets")
    op.drop_table("props")
    op.drop_table("scenes")
    op.drop_table("characters")
    op.drop_table("episodes")
    op.drop_table("projects")
    # Drop enum types after tables are removed
    asset_type_enum.drop(op.get_bind())
    job_status_enum.drop(op.get_bind())
    project_status_enum.drop(op.get_bind())
