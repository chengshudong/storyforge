"""add storyboard column to scenes

Revision ID: 002
Revises: 001
Create Date: 2026-05-26

Add a JSONB storyboard column to scenes table for TASK_005 storyboard data
(camera, duration, emotion, location, props, transition, asset_refs, character_actions, locked).
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scenes",
        sa.Column(
            "storyboard",
            postgresql.JSONB,
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("scenes", "storyboard")
