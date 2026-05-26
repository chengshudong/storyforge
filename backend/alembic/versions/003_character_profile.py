"""add character profile, versioning, and locking

Revision ID: 003
Revises: 002
Create Date: 2026-05-26

Extend characters table with profile JSONB, version counter, and lock fields.
Add character_versions table for append-only version history.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("characters", sa.Column("profile", postgresql.JSONB, nullable=True))
    op.add_column("characters", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("characters", sa.Column("locked", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("characters", sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("characters", sa.Column("locked_by", sa.String(255), nullable=True))

    op.create_table(
        "character_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("character_id", sa.Uuid(), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("profile_snapshot", postgresql.JSONB, nullable=False),
        sa.Column("diff", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.UniqueConstraint("character_id", "version_number", name="uq_character_versions"),
    )


def downgrade() -> None:
    op.drop_table("character_versions")
    op.drop_column("characters", "locked_by")
    op.drop_column("characters", "locked_at")
    op.drop_column("characters", "locked")
    op.drop_column("characters", "version")
    op.drop_column("characters", "profile")
