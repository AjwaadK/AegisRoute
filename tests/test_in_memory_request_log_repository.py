import asyncio

from app.repositories.request_log import InMemoryRequestLogRepository


def create_started(
    repository: InMemoryRequestLogRepository,
    request_id: str = "request-1",
) -> None:
    asyncio.run(
        repository.create_started_request(
            request_id=request_id,
            requested_model="public-model",
            prompt_hash="a" * 64,
            message_count=1,
            input_chars=5,
        )
    )


def test_started_request_has_nullable_routing_fields() -> None:
    repository = InMemoryRequestLogRepository()
    create_started(repository)

    request = repository.requests["request-1"]
    assert request["requested_model"] == "public-model"
    assert request["selected_model"] is None
    assert request["provider"] is None
    assert request["routing_reason"] is None


def test_mark_routed_persists_decision_and_event() -> None:
    repository = InMemoryRequestLogRepository()
    create_started(repository)

    asyncio.run(
        repository.mark_routed(
            request_id="request-1",
            selected_model="provider-model",
            provider_name="mock",
            routing_reason="first configured provider",
        )
    )

    request = repository.requests["request-1"]
    assert request["selected_model"] == "provider-model"
    assert request["provider"] == "mock"
    assert request["routing_reason"] == "first configured provider"
    assert repository.events[-1]["event_type"] == "generation_routed"


def test_completion_and_failure_preserve_routing_metadata() -> None:
    repository = InMemoryRequestLogRepository()
    create_started(repository, "completed")
    create_started(repository, "failed")
    for request_id in ("completed", "failed"):
        asyncio.run(
            repository.mark_routed(
                request_id=request_id,
                selected_model="provider-model",
                provider_name="mock",
                routing_reason="first configured provider",
            )
        )

    asyncio.run(
        repository.mark_completed(
            request_id="completed",
            latency_ms=2,
            input_tokens=1,
            output_tokens=1,
        )
    )
    asyncio.run(
        repository.mark_failed(
            request_id="failed",
            error_type="ProviderError",
            latency_ms=3,
        )
    )

    for request_id in ("completed", "failed"):
        request = repository.requests[request_id]
        assert request["requested_model"] == "public-model"
        assert request["selected_model"] == "provider-model"
        assert request["provider"] == "mock"
        assert request["routing_reason"] == "first configured provider"
