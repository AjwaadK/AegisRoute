import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.composition import ApplicationContainer
from app.errors import ProviderTimeoutError
from app.main import create_app
from app.providers.mock import MockProviderAdapter
from app.routing.model_registry import ModelDefinition, ModelRegistry
from app.routing.policy import DeterministicRoutingPolicy
from app.routing.provider_registry import ProviderRegistry
from app.services.gateway import GatewayService


def client(provider: MockProviderAdapter) -> TestClient:
    registry = ProviderRegistry([provider])
    models = ModelRegistry([ModelDefinition("model-v1", ("mock",))])
    policy = DeterministicRoutingPolicy(models, registry)
    container = ApplicationContainer(
        engine=create_engine("sqlite://"),
        gateway_service=GatewayService(
            routing_policy=policy, provider_registry=registry
        ),
        model_registry=models,
        provider_registry=registry,
        routing_policy=policy,
    )
    return TestClient(create_app(lambda: container))


def payload() -> dict[str, object]:
    return {
        "model": "model-v1",
        "messages": [{"role": "user", "content": "hello"}],
    }


def parse_sse(body: str) -> list[tuple[str, dict[str, object]]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        events.append((lines[0].removeprefix("event: "), json.loads(lines[1][6:])))
    return events


def test_http_stream_emits_ordered_owned_sse_and_completion() -> None:
    with client(MockProviderAdapter(stream_chunks=("hel", "lo"))) as test_client:
        response = test_client.post("/generate/stream", json=payload())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert [name for name, _data in events] == ["delta", "delta", "completed"]
    assert [events[0][1]["text"], events[1][1]["text"]] == ["hel", "lo"]
    assert "provider" not in events[-1][1]
    assert "StreamTextDelta" not in response.text


def test_precommit_failure_uses_normal_http_error_mapping() -> None:
    provider = MockProviderAdapter(
        stream_failure=ProviderTimeoutError("mock"),
        stream_failure_after_chunks=0,
    )
    with client(provider) as test_client:
        response = test_client.post("/generate/stream", json=payload())

    assert response.status_code == 502
    assert response.json()["detail"]["error"] == "provider_error"


def test_post_commit_failure_uses_bounded_error_event() -> None:
    provider = MockProviderAdapter(
        stream_chunks=("visible",),
        stream_failure=ProviderTimeoutError("mock", message="private upstream details"),
        stream_failure_after_chunks=1,
    )
    with client(provider) as test_client:
        response = test_client.post("/generate/stream", json=payload())

    assert response.status_code == 200
    events = parse_sse(response.text)
    assert [name for name, _data in events] == ["delta", "error"]
    assert events[-1][1] == {
        "error_type": "provider_timeout",
        "stage": "post_commit",
    }
    assert "private upstream details" not in response.text


def test_nonstreaming_generate_remains_available() -> None:
    with client(MockProviderAdapter()) as test_client:
        response = test_client.post("/generate", json=payload())

    assert response.status_code == 200
    assert response.json()["output"] == "mock_response:hello"
