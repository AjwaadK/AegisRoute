"""PostgreSQL integration tests for the SQLAlchemy request log repository."""

import asyncio
import os
from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.db.base import Base
from app.db.models import GenerationEvent, GenerationRequest
from app.composition import build_application_container
from app.main import create_app
from app.providers.base import ProviderAdapter
from app.repositories.errors import RequestLogNotFoundError
from app.repositories.request_log import SQLAlchemyRequestLogRepository
from app.schemas.generation import GenerateRequest, ProviderResult


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for PostgreSQL integration tests",
)


@pytest.fixture(scope="module")
def session_factory() -> Generator[sessionmaker[Session], None, None]:
    assert TEST_DATABASE_URL is not None
    schema_name = f"aegisroute_repository_{uuid4().hex}"
    admin_engine = create_engine(TEST_DATABASE_URL)
    database_url = make_url(TEST_DATABASE_URL)
    query = dict(database_url.query)
    query["options"] = f"-csearch_path={schema_name}"
    isolated_url = database_url.set(query=query)

    with admin_engine.begin() as connection:
        connection.execute(CreateSchema(schema_name))

    engine = create_engine(isolated_url)
    Base.metadata.create_all(engine)
    original_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = isolated_url.render_as_string(
        hide_password=False
    )
    try:
        yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    finally:
        if original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_database_url
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(DropSchema(schema_name, cascade=True))
        admin_engine.dispose()


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
        requested_model="mock-model-v1",
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
    assert generation_request.requested_model == "mock-model-v1"
    assert generation_request.selected_model is None
    assert generation_request.provider is None
    assert generation_request.routing_reason is None
    assert [(event.event_type, event.status) for event in events] == [("generation_started", "started")]


def test_complete_request_updates_row_and_appends_event(
    repository: SQLAlchemyRequestLogRepository, session_factory: sessionmaker[Session]
) -> None:
    asyncio.run(create_started_request(repository))
    asyncio.run(
        repository.mark_routed(
            request_id="request-123",
            selected_model="selected-model-v2",
            provider_name="mock",
            routing_reason="selected for test",
        )
    )
    asyncio.run(
        repository.mark_completed(
            request_id="request-123",
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
    assert generation_request.requested_model == "mock-model-v1"
    assert generation_request.selected_model == "selected-model-v2"
    assert generation_request.provider == "mock"
    assert generation_request.routing_reason == "selected for test"
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
        repository.mark_routed(
            request_id="request-123",
            selected_model="selected-model-v2",
            provider_name="mock",
            routing_reason="selected for test",
        )
    )
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
    assert generation_request.selected_model == "selected-model-v2"
    assert generation_request.provider == "mock"
    assert generation_request.routing_reason == "selected for test"
    assert generation_request.error_type == "ProviderError"
    assert generation_request.latency_ms == 12
    assert (event.event_type, event.message) == ("generation_failed", "sanitized provider failure")


@pytest.mark.parametrize(
    "operation",
    ["mark_routed", "mark_completed", "mark_failed", "add_event"],
)
def test_unknown_request_id_raises_not_found_error(
    repository: SQLAlchemyRequestLogRepository, operation: str
) -> None:
    async def invoke() -> None:
        if operation == "mark_routed":
            await repository.mark_routed(
                request_id="missing",
                selected_model="model",
                provider_name="mock",
                routing_reason="test",
            )
        elif operation == "mark_completed":
            await repository.mark_completed(
                request_id="missing",
                latency_ms=1,
                input_tokens=1,
                output_tokens=1,
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
                request_id="request-123",
                latency_ms=1,
                input_tokens=1,
                output_tokens=1,
            )
        )

    with session_factory() as session:
        generation_request = session.scalar(select(GenerationRequest))
        events = session.scalars(select(GenerationEvent)).all()

    assert generation_request is not None
    assert generation_request.status == "started"
    assert len(events) == 1


def test_mark_routed_updates_only_matching_request(
    repository: SQLAlchemyRequestLogRepository,
    session_factory: sessionmaker[Session],
) -> None:
    asyncio.run(create_started_request(repository, "request-1"))
    asyncio.run(create_started_request(repository, "request-2"))

    asyncio.run(
        repository.mark_routed(
            request_id="request-1",
            selected_model="selected-model",
            provider_name="mock",
            routing_reason="first available",
        )
    )

    with session_factory() as session:
        requests = {
            item.request_id: item
            for item in session.scalars(select(GenerationRequest)).all()
        }

    assert requests["request-1"].selected_model == "selected-model"
    assert requests["request-1"].provider == "mock"
    assert requests["request-1"].routing_reason == "first available"
    assert requests["request-2"].selected_model is None
    assert requests["request-2"].provider is None
    assert requests["request-2"].routing_reason is None


def test_mark_routed_event_failure_rolls_back_routing_fields(
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
            repository.mark_routed(
                request_id="request-123",
                selected_model="selected-model",
                provider_name="mock",
                routing_reason="test",
            )
        )

    with session_factory() as session:
        generation_request = session.scalar(select(GenerationRequest))

    assert generation_request is not None
    assert generation_request.selected_model is None
    assert generation_request.provider is None
    assert generation_request.routing_reason is None


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
    assert generation_request.requested_model == "mock-model-v1"
    assert generation_request.selected_model == "mock-model-v1"
    assert generation_request.provider == "deterministic"
    assert generation_request.routing_reason == "selected first configured provider"
    assert "generation_started" in event_types
    assert "generation_routed" in event_types
    assert "generation_completed" in event_types
