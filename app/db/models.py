"""SQLAlchemy models for generation request persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class GenerationRequest(Base):
    """Mutable current and final state for one generation request."""

    __tablename__ = "generation_requests"
    __table_args__ = (
        CheckConstraint("message_count >= 1", name="ck_generation_requests_message_count_gte_1"),
        CheckConstraint("input_chars >= 0", name="ck_generation_requests_input_chars_gte_0"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="ck_generation_requests_latency_ms_gte_0"),
        CheckConstraint("input_tokens IS NULL OR input_tokens >= 0", name="ck_generation_requests_input_tokens_gte_0"),
        CheckConstraint("output_tokens IS NULL OR output_tokens >= 0", name="ck_generation_requests_output_tokens_gte_0"),
        Index("ix_generation_requests_created_at", "created_at"),
        Index("ix_generation_requests_status", "status"),
        Index("ix_generation_requests_provider", "provider"),
        Index("ix_generation_requests_model", "model"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False)
    input_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    events: Mapped[list[GenerationEvent]] = relationship(
        back_populates="generation_request",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class GenerationEvent(Base):
    """Append-only timeline event for a generation request."""

    __tablename__ = "generation_events"
    __table_args__ = (
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="ck_generation_events_latency_ms_gte_0"),
        Index("ix_generation_events_created_at", "created_at"),
        Index("ix_generation_events_event_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    generation_request_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("generation_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    generation_request: Mapped[GenerationRequest] = relationship(back_populates="events")
