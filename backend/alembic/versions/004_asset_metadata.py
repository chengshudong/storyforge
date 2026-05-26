"""add generation metadata to assets, add generation_batches table

Revision ID: 004
Revises: 003
Create Date: 2026-05-26

Extend assets with prompt/seed/params/variation/selection/lock columns.
Add generation_batches table for tracking batch generation progress.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("prompt", sa.Text(), nullable=True))
    op.add_column("assets", sa.Column("negative_prompt", sa.Text(), nullable=True))
    op.add_column("assets", sa.Column("seed", sa.Integer(), nullable=True))
    op.add_column("assets", sa.Column("generation_params", postgresql.JSONB, nullable=True))
    op.add_column("assets", sa.Column("variation_of", sa.Uuid(), sa.ForeignKey("assets.id"), nullable=True))
    op.add_column("assets", sa.Column("batch_id", sa.Uuid(), nullable=True))
    op.add_column("assets", sa.Column("selected", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("assets", sa.Column("favorite", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("assets", sa.Column("locked", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("assets", sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assets", sa.Column("asset_ref", sa.String(100), nullable=True))

    op.create_table(
        "generation_batches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("total_assets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_assets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Add cover to asset_type enum
    op.execute("ALTER TYPE asset_type ADD VALUE IF NOT EXISTS 'cover'")


def downgrade() -> None:
    op.drop_table("generation_batches")
    op.drop_column("assets", "asset_ref")
    op.drop_column("assets", "locked_at")
    op.drop_column("assets", "locked")
    op.drop_column("assets", "favorite")
    op.drop_column("assets", "selected")
    op.drop_column("assets", "batch_id")
    op.drop_column("assets", "variation_of")
    op.drop_column("assets", "generation_params")
    op.drop_column("assets", "seed")
    op.drop_column("assets", "negative_prompt")
    op.drop_column("assets", "prompt")
