"""extend videos with prompts, generation params, provider tracking, selection

Revision ID: 006
Revises: 005
Create Date: 2026-05-26

Extend videos with 14 new columns for video generation pipeline.
Flat columns for frequently-accessed fields (fps, seed, provider),
JSONB for bulk params (generation_params).
Adds project_id FK for direct listing without JOIN chain.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    # New columns (all nullable initially for backward compat)
    op.add_column("videos", sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=True))
    op.add_column("videos", sa.Column("prompt", sa.Text(), nullable=True))
    op.add_column("videos", sa.Column("negative_prompt", sa.Text(), nullable=True))
    op.add_column("videos", sa.Column("seed", sa.Integer(), nullable=True))
    op.add_column("videos", sa.Column("fps", sa.Integer(), nullable=True, server_default="24"))
    op.add_column("videos", sa.Column("generation_params", postgresql.JSONB, nullable=True))
    op.add_column("videos", sa.Column("provider", sa.String(50), nullable=True))
    op.add_column("videos", sa.Column("preview_path", sa.String(500), nullable=True))
    op.add_column("videos", sa.Column("thumbnail_path", sa.String(500), nullable=True))
    op.add_column("videos", sa.Column("batch_id", sa.Uuid(), nullable=True))
    op.add_column("videos", sa.Column("selected", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("videos", sa.Column("version", sa.Integer(), nullable=True, server_default="1"))
    op.add_column("videos", sa.Column("audio_path", sa.String(500), nullable=True))
    op.add_column("videos", sa.Column("audio_duration", sa.Float(), nullable=True))
    op.add_column("videos", sa.Column("file_size", sa.Integer(), nullable=True))

    # Backfill project_id from scene -> episode FK chain
    op.execute("""
        UPDATE videos SET project_id = e.project_id
        FROM scenes s
        JOIN episodes e ON s.episode_id = e.id
        WHERE videos.scene_id = s.id AND videos.project_id IS NULL
    """)

    # Make project_id non-nullable after backfill
    op.alter_column("videos", "project_id", nullable=False)

    # Indexes
    op.create_index("ix_videos_project_id", "videos", ["project_id"])
    op.create_index("ix_videos_scene_selected", "videos", ["scene_id", "selected"])
    op.create_index("ix_videos_batch_id", "videos", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_videos_batch_id", table_name="videos")
    op.drop_index("ix_videos_scene_selected", table_name="videos")
    op.drop_index("ix_videos_project_id", table_name="videos")

    op.drop_column("videos", "file_size")
    op.drop_column("videos", "audio_duration")
    op.drop_column("videos", "audio_path")
    op.drop_column("videos", "version")
    op.drop_column("videos", "selected")
    op.drop_column("videos", "batch_id")
    op.drop_column("videos", "thumbnail_path")
    op.drop_column("videos", "preview_path")
    op.drop_column("videos", "provider")
    op.drop_column("videos", "generation_params")
    op.drop_column("videos", "fps")
    op.drop_column("videos", "seed")
    op.drop_column("videos", "negative_prompt")
    op.drop_column("videos", "prompt")
    op.drop_column("videos", "project_id")
