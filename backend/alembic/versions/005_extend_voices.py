"""extend voices with provider, speaker, synthesis params, version binding, selection

Revision ID: 005
Revises: 004
Create Date: 2026-05-26

Extend voices with 12 new columns for voice cloning/synthesis pipeline.
Flat columns for frequently-accessed fields (speed, pitch, emotion),
JSONB for bulk metadata (voice_params).
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("voices", sa.Column("scene_id", sa.Uuid(), sa.ForeignKey("scenes.id"), nullable=True))
    op.add_column("voices", sa.Column("dialogue_index", sa.Integer(), nullable=True))
    op.add_column("voices", sa.Column("provider", sa.String(50), nullable=True))
    op.add_column("voices", sa.Column("speaker", sa.String(255), nullable=True))
    op.add_column("voices", sa.Column("speed", sa.Float(), nullable=True))
    op.add_column("voices", sa.Column("pitch", sa.Integer(), nullable=True))
    op.add_column("voices", sa.Column("emotion", sa.String(50), nullable=True))
    op.add_column("voices", sa.Column("version", sa.Integer(), nullable=True))
    op.add_column("voices", sa.Column("selected", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("voices", sa.Column("voice_params", postgresql.JSONB, nullable=True))
    op.add_column("voices", sa.Column("duration_ms", sa.Float(), nullable=True))
    op.add_column("voices", sa.Column("preview_path", sa.String(500), nullable=True))
    op.add_column("voices", sa.Column("reference_audio_path", sa.String(500), nullable=True))

    op.create_index("ix_voices_character_selected", "voices", ["character_id", "selected"])
    op.create_index("ix_voices_character_version", "voices", ["character_id", "version"])
    op.create_index("ix_voices_scene_dialogue", "voices", ["scene_id", "dialogue_index"])


def downgrade() -> None:
    op.drop_index("ix_voices_scene_dialogue")
    op.drop_index("ix_voices_character_version")
    op.drop_index("ix_voices_character_selected")

    op.drop_column("voices", "reference_audio_path")
    op.drop_column("voices", "preview_path")
    op.drop_column("voices", "duration_ms")
    op.drop_column("voices", "voice_params")
    op.drop_column("voices", "selected")
    op.drop_column("voices", "version")
    op.drop_column("voices", "emotion")
    op.drop_column("voices", "pitch")
    op.drop_column("voices", "speed")
    op.drop_column("voices", "speaker")
    op.drop_column("voices", "provider")
    op.drop_column("voices", "dialogue_index")
    op.drop_column("voices", "scene_id")
