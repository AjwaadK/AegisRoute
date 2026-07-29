from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import GenerationEvent, GenerationRequest
from app.repositories.errors import RequestLogNotFoundError


class RequestLogRepository(Protocol):
    async def create_started_request(
        self,
        *,
        request_id: str,
        requested_model: str,
        prompt_hash: str,
        message_count: int,
        input_chars: int,
    ) -> None:
        """Create generation_requests current-state row in started state."""

    async def mark_routed(
        self,
        *,
        request_id: str,
        selected_model: str,
        provider_name: str,
        routing_reason: str,
    ) -> None:
        """Persist the routing decision before provider invocation."""

    async def mark_completed(
        self,
        *,
        request_id: str,
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Update generation_requests current-state row after provider success."""

    async def mark_failed(
        self,
        *,
        request_id: str,
        error_type: str,
        latency_ms: int,
        message: str | None = None,
    ) -> None:
        """Update generation_requests current-state row after provider failure."""

    async def add_event(
        self,
        *,
        request_id: str,
        event_type: str,
        status: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        error_type: str | None = None,
        message: str | None = None,
        latency_ms: int | None = None,
    ) -> None:
        """Append a generation_events timeline row."""


class NoopRequestLogRepository:
    async def create_started_request(
        self,
        *,
        request_id: str,
        requested_model: str,
        prompt_hash: str,
        message_count: int,
        input_chars: int,
    ) -> None:
        return None

    async def mark_routed(
        self,
        *,
        request_id: str,
        selected_model: str,
        provider_name: str,
        routing_reason: str,
    ) -> None:
        return None

    async def mark_completed(
        self,
        *,
        request_id: str,
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        return None

    async def mark_failed(
        self,
        *,
        request_id: str,
        error_type: str,
        latency_ms: int,
        message: str | None = None,
    ) -> None:
        return None

    async def add_event(
        self,
        *,
        request_id: str,
        event_type: str,
        status: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        error_type: str | None = None,
        message: str | None = None,
        latency_ms: int | None = None,
    ) -> None:
        return None


class InMemoryRequestLogRepository:
    def __init__(self) -> None:
        self.requests: dict[str, dict[str, object]] = {}
        self.events: list[dict[str, object]] = []

    async def create_started_request(
        self,
        *,
        request_id: str,
        requested_model: str,
        prompt_hash: str,
        message_count: int,
        input_chars: int,
    ) -> None:
        self.requests[request_id] = {
            "request_id": request_id,
            "requested_model": requested_model,
            "selected_model": None,
            "provider": None,
            "routing_reason": None,
            "prompt_hash": prompt_hash,
            "message_count": message_count,
            "input_chars": input_chars,
            "status": "started",
        }
        self._add_event(
            request_id=request_id,
            event_type="generation_started",
            status="started",
            model=requested_model,
        )

    async def mark_routed(
        self,
        *,
        request_id: str,
        selected_model: str,
        provider_name: str,
        routing_reason: str,
    ) -> None:
        request = self.requests[request_id]
        request.update(
            selected_model=selected_model,
            provider=provider_name,
            routing_reason=routing_reason,
        )
        self._add_event(
            request_id=request_id,
            event_type="generation_routed",
            status="started",
            provider=provider_name,
            model=selected_model,
        )

    async def mark_completed(
        self,
        *,
        request_id: str,
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        request = self.requests[request_id]
        request.update(
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            status="completed",
            error_type=None,
        )
        self._add_event(
            request_id=request_id,
            event_type="generation_completed",
            status="completed",
            provider=request["provider"],
            model=request["selected_model"],
            latency_ms=latency_ms,
        )

    async def mark_failed(
        self,
        *,
        request_id: str,
        error_type: str,
        latency_ms: int,
        message: str | None = None,
    ) -> None:
        request = self.requests[request_id]
        request.update(
            error_type=error_type,
            latency_ms=latency_ms,
            status="failed",
        )
        self._add_event(
            request_id=request_id,
            event_type="generation_failed",
            status="failed",
            provider=request["provider"],
            model=request["selected_model"],
            error_type=error_type,
            message=message,
            latency_ms=latency_ms,
        )

    async def add_event(
        self,
        *,
        request_id: str,
        event_type: str,
        status: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        error_type: str | None = None,
        message: str | None = None,
        latency_ms: int | None = None,
    ) -> None:
        self._add_event(
            request_id=request_id,
            event_type=event_type,
            status=status,
            provider=provider,
            model=model,
            error_type=error_type,
            message=message,
            latency_ms=latency_ms,
        )

    def _add_event(
        self,
        *,
        request_id: str,
        event_type: str,
        status: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        error_type: str | None = None,
        message: str | None = None,
        latency_ms: int | None = None,
    ) -> None:
        self.events.append(
            {
                "request_id": request_id,
                "event_type": event_type,
                "status": status,
                "provider": provider,
                "model": model,
                "error_type": error_type,
                "message": message,
                "latency_ms": latency_ms,
            }
        )


class SQLAlchemyRequestLogRepository:
    """Persist generation request state and timeline events with SQLAlchemy."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    async def create_started_request(
        self,
        *,
        request_id: str,
        requested_model: str,
        prompt_hash: str,
        message_count: int,
        input_chars: int,
    ) -> None:
        """Create a started request and its initial timeline event atomically."""

        with self._session_factory() as session:
            try:
                generation_request = GenerationRequest(
                    request_id=request_id,
                    requested_model=requested_model,
                    prompt_hash=prompt_hash,
                    message_count=message_count,
                    input_chars=input_chars,
                    status="started",
                )
                session.add(generation_request)
                session.flush()
                self._add_event(
                    session,
                    generation_request_id=generation_request.id,
                    event_type="generation_started",
                    status="started",
                    model=requested_model,
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

    async def mark_routed(
        self,
        *,
        request_id: str,
        selected_model: str,
        provider_name: str,
        routing_reason: str,
    ) -> None:
        """Persist routing state and its lifecycle event atomically."""

        with self._session_factory() as session:
            try:
                generation_request = self._get_request(session, request_id)
                generation_request.selected_model = selected_model
                generation_request.provider = provider_name
                generation_request.routing_reason = routing_reason
                generation_request.updated_at = datetime.now(UTC)
                self._add_event(
                    session,
                    generation_request_id=generation_request.id,
                    event_type="generation_routed",
                    status="started",
                    provider=provider_name,
                    model=selected_model,
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

    async def complete_request(
        self,
        *,
        request_id: str,
        model: str,
        provider: str,
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Compatibility alias; routing metadata is preserved, not overwritten."""

        await self.mark_completed(
            request_id=request_id,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def mark_completed(
        self,
        *,
        request_id: str,
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record successful completion and its lifecycle event atomically."""

        with self._session_factory() as session:
            try:
                generation_request = self._get_request(session, request_id)
                generation_request.status = "completed"
                generation_request.latency_ms = latency_ms
                generation_request.input_tokens = input_tokens
                generation_request.output_tokens = output_tokens
                generation_request.error_type = None
                generation_request.updated_at = datetime.now(UTC)
                self._add_event(
                    session,
                    generation_request_id=generation_request.id,
                    event_type="generation_completed",
                    status="completed",
                    provider=generation_request.provider,
                    model=generation_request.selected_model,
                    latency_ms=latency_ms,
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

    async def mark_failed(
        self,
        *,
        request_id: str,
        error_type: str,
        latency_ms: int,
        message: str | None = None,
    ) -> None:
        """Record a failed request and its lifecycle event atomically."""

        with self._session_factory() as session:
            try:
                generation_request = self._get_request(session, request_id)
                generation_request.status = "failed"
                generation_request.latency_ms = latency_ms
                generation_request.error_type = error_type
                generation_request.updated_at = datetime.now(UTC)
                self._add_event(
                    session,
                    generation_request_id=generation_request.id,
                    event_type="generation_failed",
                    status="failed",
                    provider=generation_request.provider,
                    model=generation_request.selected_model,
                    error_type=error_type,
                    message=message,
                    latency_ms=latency_ms,
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

    async def add_event(
        self,
        *,
        request_id: str,
        event_type: str,
        status: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        error_type: str | None = None,
        message: str | None = None,
        latency_ms: int | None = None,
    ) -> None:
        """Append a timeline event without changing the current request state."""

        with self._session_factory() as session:
            try:
                generation_request = self._get_request(session, request_id)
                self._add_event(
                    session,
                    generation_request_id=generation_request.id,
                    event_type=event_type,
                    status=status,
                    provider=provider,
                    model=model,
                    error_type=error_type,
                    message=message,
                    latency_ms=latency_ms,
                )
                session.commit()
            except Exception:
                session.rollback()
                raise

    async def fail_request(
        self,
        *,
        request_id: str,
        error_type: str,
        latency_ms: int,
        message: str | None = None,
    ) -> None:
        """Compatibility alias for recording a failed request."""

        await self.mark_failed(
            request_id=request_id,
            error_type=error_type,
            latency_ms=latency_ms,
            message=message,
        )

    @staticmethod
    def _get_request(session: Session, request_id: str) -> GenerationRequest:
        generation_request = session.scalar(
            select(GenerationRequest).where(GenerationRequest.request_id == request_id)
        )
        if generation_request is None:
            raise RequestLogNotFoundError(f"Request log not found for request_id={request_id!r}")
        return generation_request

    @staticmethod
    def _add_event(
        session: Session,
        *,
        generation_request_id: int,
        event_type: str,
        status: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        error_type: str | None = None,
        message: str | None = None,
        latency_ms: int | None = None,
    ) -> None:
        session.add(
            GenerationEvent(
                generation_request_id=generation_request_id,
                event_type=event_type,
                status=status,
                provider=provider,
                model=model,
                error_type=error_type,
                message=message,
                latency_ms=latency_ms,
            )
        )
