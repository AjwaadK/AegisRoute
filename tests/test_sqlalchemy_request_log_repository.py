"""PostgreSQL integration tests for the SQLAlchemy request log repository."""

import asyncio
import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import GenerationEvent, GenerationRequest
from app.composition import build_application_container
from app.main import create_app
from app.providers.base import ProviderAdapter
from app.repositories.errors import RequestLogNotFoundError
from app.repositories.request_log import SQLAlchemyRequestLogRepository
from app.schemas.generation import GenerateRequest, ProviderResult


DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL is required for PostgreSQL integration tests")


@pytest.fixture(scope="module")
def session_factory() -> Generator[sessionmaker[Session], None, None]:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def clear_tables(session_factory: sessionmaker[Session]) -> Generator[None, None, None]:
    with session_factory() as session:
        session.execute(delete(GenerationEvent))
        session.execute(delete(GenerationRequest))
        session.commit()
    yield


@pytest.fixture
def repository(session_factory: sessionmaker[Session]) -> SQLAlchemyRequestLogRepository:
    return SQLAlchemyRequestLogRepository(session_factory)


async def create_started_request(repository: SQLAlchemyRequestLogRepository, request_id: str = "request-123") -> None:
    await repository.create_started_request(
        request_id=request_id,
        provider="mock",
        model="mock-model-v1",
        prompt_hash="a" * 64,
        message_count=1,
        input_chars=5,
    )


def test_started_request_creates_request_and_started_event(
    repository: SQLAlchemyRequestLogRepository, session_factory: sessionmaker[Session]
) -> None:
    asyncio.run(create_started_request(repository))

    with session_factory() as session:
        generation_request = session.scalar(select(GenerationRequest))
        events = session.scalars(select(GenerationEvent)).all()

    assert generation_request is not None
    assert generation_request.status == "started"
    assert [(event.event_type, event.status) for event in events] == [("generation_started", "started")]


def test_complete_request_updates_row_and_appends_event(
    repository: SQLAlchemyRequestLogRepository, session_factory: sessionmaker[Session]
) -> None:
    asyncio.run(create_started_request(repository))
    asyncio.run(
        repository.mark_completed(
            request_id="request-123",
            provider="mock",
            model="mock-model-v1",
            latency_ms=12,
            input_tokens=3,
            output_tokens=4,
        )
    )

    with session_factory() as session:
        generation_request = session.scalar(select(GenerationRequest))
        events = session.scalars(select(GenerationEvent).order_by(GenerationEvent.id)).all()

    assert generation_request is not None
    assert generation_request.status == "completed"
    assert generation_request.latency_ms == 12
    assert (generation_request.input_tokens, generation_request.output_tokens) == (3, 4)
    assert generation_request.error_type is None
    assert events[-1].event_type == "generation_completed"
    assert events[-1].status == "completed"


def test_fail_request_updates_row_and_appends_event(
    repository: SQLAlchemyRequestLogRepository, session_factory: sessionmaker[Session]
) -> None:
    asyncio.run(create_started_request(repository))
    asyncio.run(
        repository.mark_failed(
            request_id="request-123",
            error_type="ProviderError",
            latency_ms=12,
            message="sanitized provider failure",
        )
    )

    with session_factory() as session:
        generation_request = session.scalar(select(GenerationRequest))
        event = session.scalars(select(GenerationEvent).order_by(GenerationEvent.id)).all()[-1]

    assert generation_request is not None
    assert generation_request.status == "failed"
    assert generation_request.error_type == "ProviderError"
    assert generation_request.latency_ms == 12
    assert (event.event_type, event.message) == ("generation_failed", "sanitized provider failure")


@pytest.mark.parametrize("operation", ["mark_completed", "mark_failed", "add_event"])
def test_unknown_request_id_raises_not_found_error(
    repository: SQLAlchemyRequestLogRepository, operation: str
) -> None:
    async def invoke() -> None:
        if operation == "mark_completed":
            await repository.mark_completed(
                request_id="missing", provider="mock", model="mock-model-v1", latency_ms=1, input_tokens=1, output_tokens=1
            )
        elif operation == "mark_failed":
            await repository.mark_failed(request_id="missing", error_type="ProviderError", latency_ms=1)
        else:
            await repository.add_event(request_id="missing", event_type="attempted")

    with pytest.raises(RequestLogNotFoundError):
        asyncio.run(invoke())


def test_duplicate_request_id_rolls_back_event_insert(
    repository: SQLAlchemyRequestLogRepository, session_factory: sessionmaker[Session]
) -> None:
    asyncio.run(create_started_request(repository))

    with pytest.raises(IntegrityError):
        asyncio.run(create_started_request(repository))

    with session_factory() as session:
        assert len(session.scalars(select(GenerationRequest)).all()) == 1
        assert len(session.scalars(select(GenerationEvent)).all()) == 1


def test_event_insertion_failure_rolls_back_status_change(
    repository: SQLAlchemyRequestLogRepository,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(create_started_request(repository))

    def fail_event(*args: object, **kwargs: object) -> None:
        raise RuntimeError("event insert failed")

    monkeypatch.setattr(repository, "_add_event", fail_event)
    with pytest.raises(RuntimeError, match="event insert failed"):
        asyncio.run(
            repository.mark_completed(
                request_id="request-123", provider="mock", model="mock-model-v1", latency_ms=1, input_tokens=1, output_tokens=1
            )
        )

    with session_factory() as session:
        generation_request = session.scalar(select(GenerationRequest))
        events = session.scalars(select(GenerationEvent)).all()

    assert generation_request is not None
    assert generation_request.status == "started"
    assert len(events) == 1


def test_add_event_does_not_change_current_status(
    repository: SQLAlchemyRequestLogRepository, session_factory: sessionmaker[Session]
) -> None:
    asyncio.run(create_started_request(repository))
    asyncio.run(repository.add_event(request_id="request-123", event_type="provider_attempted", status="started"))

    with session_factory() as session:
        generation_request = session.scalar(select(GenerationRequest))
        event = session.scalars(select(GenerationEvent).order_by(GenerationEvent.id)).all()[-1]

    assert generation_request is not None
    assert generation_request.status == "started"
    assert event.event_type == "provider_attempted"


class DeterministicProvider(ProviderAdapter):
    provider_name = "deterministic"

    async def generate(self, request: GenerateRequest, request_id: str) -> ProviderResult:
        return ProviderResult(
            request_id=request_id,
            provider=self.provider_name,
            model=request.model,
            output="deterministic response",
            input_tokens=2,
            output_tokens=3,
        )


def test_application_composition_persists_completed_request(
    session_factory: sessionmaker[Session],
) -> None:
    provider = DeterministicProvider()
    application = create_app(lambda: build_application_container(provider))

    with TestClient(application) as client:
        response = client.post(
            "/generate",
            json={"model": "mock-model-v1", "messages": [{"role": "user", "content": "Hello"}]},
        )

    with session_factory() as session:
        generation_request = session.scalar(select(GenerationRequest))
        event_types = session.scalars(
            select(GenerationEvent.event_type).order_by(GenerationEvent.id)
        ).all()

    assert response.status_code == 200
    assert response.json()["output"] == "deterministic response"
    assert generation_request is not None
    assert generation_request.status == "completed"
    assert "generation_started" in event_types
    assert "generation_completed" in event_types
