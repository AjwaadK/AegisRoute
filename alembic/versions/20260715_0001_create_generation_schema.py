"""Create generation request and event tables.

Revision ID: 20260715_0001
Revises:
Create Date: 2026-07-15 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260715_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generation_requests",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("input_chars", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("input_chars >= 0", name="ck_generation_requests_input_chars_gte_0"),
        sa.CheckConstraint("input_tokens IS NULL OR input_tokens >= 0", name="ck_generation_requests_input_tokens_gte_0"),
        sa.CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="ck_generation_requests_latency_ms_gte_0"),
        sa.CheckConstraint("message_count >= 1", name="ck_generation_requests_message_count_gte_1"),
        sa.CheckConstraint("output_tokens IS NULL OR output_tokens >= 0", name="ck_generation_requests_output_tokens_gte_0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index("ix_generation_requests_created_at", "generation_requests", ["created_at"], unique=False)
    op.create_index("ix_generation_requests_model", "generation_requests", ["model"], unique=False)
    op.create_index("ix_generation_requests_provider", "generation_requests", ["provider"], unique=False)
    op.create_index("ix_generation_requests_request_id", "generation_requests", ["request_id"], unique=False)
    op.create_index("ix_generation_requests_status", "generation_requests", ["status"], unique=False)

    op.create_table(
        "generation_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("generation_request_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("error_type", sa.String(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="ck_generation_events_latency_ms_gte_0"),
        sa.ForeignKeyConstraint(["generation_request_id"], ["generation_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generation_events_created_at", "generation_events", ["created_at"], unique=False)
    op.create_index("ix_generation_events_event_type", "generation_events", ["event_type"], unique=False)
    op.create_index("ix_generation_events_generation_request_id", "generation_events", ["generation_request_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_generation_events_generation_request_id", table_name="generation_events")
    op.drop_index("ix_generation_events_event_type", table_name="generation_events")
    op.drop_index("ix_generation_events_created_at", table_name="generation_events")
    op.drop_table("generation_events")

    op.drop_index("ix_generation_requests_status", table_name="generation_requests")
    op.drop_index("ix_generation_requests_request_id", table_name="generation_requests")
    op.drop_index("ix_generation_requests_provider", table_name="generation_requests")
    op.drop_index("ix_generation_requests_model", table_name="generation_requests")
    op.drop_index("ix_generation_requests_created_at", table_name="generation_requests")
    op.drop_table("generation_requests")
