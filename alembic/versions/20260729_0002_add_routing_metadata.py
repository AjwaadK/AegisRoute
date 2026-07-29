"""Add routing metadata to generation requests.

Revision ID: 20260729_0002
Revises: 20260715_0001
Create Date: 2026-07-29 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260729_0002"
down_revision: Union[str, None] = "20260715_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_generation_requests_model", table_name="generation_requests")
    op.alter_column(
        "generation_requests",
        "model",
        existing_type=sa.String(length=255),
        existing_nullable=False,
        new_column_name="requested_model",
    )
    op.create_index(
        "ix_generation_requests_requested_model",
        "generation_requests",
        ["requested_model"],
        unique=False,
    )
    op.add_column(
        "generation_requests",
        sa.Column("selected_model", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "generation_requests",
        sa.Column("routing_reason", sa.Text(), nullable=True),
    )
    op.alter_column(
        "generation_requests",
        "provider",
        existing_type=sa.String(length=100),
        existing_nullable=False,
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE generation_requests "
            "SET provider = 'unrouted' "
            "WHERE provider IS NULL"
        )
    )
    op.alter_column(
        "generation_requests",
        "provider",
        existing_type=sa.String(length=100),
        existing_nullable=True,
        nullable=False,
    )
    op.drop_column("generation_requests", "routing_reason")
    op.drop_column("generation_requests", "selected_model")
    op.drop_index(
        "ix_generation_requests_requested_model",
        table_name="generation_requests",
    )
    op.alter_column(
        "generation_requests",
        "requested_model",
        existing_type=sa.String(length=255),
        existing_nullable=False,
        new_column_name="model",
    )
    op.create_index(
        "ix_generation_requests_model",
        "generation_requests",
        ["model"],
        unique=False,
    )
