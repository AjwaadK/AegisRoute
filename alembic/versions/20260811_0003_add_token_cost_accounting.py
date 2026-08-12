"""Add logical-request token and estimated cost accounting.

Revision ID: 20260811_0003
Revises: 20260729_0002
Create Date: 2026-08-11 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260811_0003"
down_revision: str | None = "20260729_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "generation_requests",
        "input_tokens",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )
    op.alter_column(
        "generation_requests",
        "output_tokens",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )
    op.add_column(
        "generation_requests",
        sa.Column("total_tokens", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "generation_requests",
        sa.Column(
            "estimated_cost_usd",
            sa.Numeric(precision=30, scale=12),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_generation_requests_total_tokens_gte_0",
        "generation_requests",
        "total_tokens IS NULL OR total_tokens >= 0",
    )
    op.create_check_constraint(
        "ck_generation_requests_estimated_cost_usd_gte_0",
        "generation_requests",
        "estimated_cost_usd IS NULL OR estimated_cost_usd >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_generation_requests_estimated_cost_usd_gte_0",
        "generation_requests",
        type_="check",
    )
    op.drop_constraint(
        "ck_generation_requests_total_tokens_gte_0",
        "generation_requests",
        type_="check",
    )
    op.drop_column("generation_requests", "estimated_cost_usd")
    op.drop_column("generation_requests", "total_tokens")
    op.alter_column(
        "generation_requests",
        "output_tokens",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
    op.alter_column(
        "generation_requests",
        "input_tokens",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
