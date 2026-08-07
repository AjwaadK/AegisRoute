import asyncio
from typing import Any

import pytest

from app.errors import ModelNotFoundError, ProviderError, ProviderTimeoutError
from app.observability.metrics import NoopApplicationMetrics
from app.providers.base import ProviderAdapter
from app.providers.mock import MockProviderAdapter
from app.routing.model_registry import ModelDefinition, ModelRegistry
from app.routing.policy import DeterministicRoutingPolicy
from app.routing.provider_registry import ProviderRegistry
from app.schemas.generation import GenerateRequest, ProviderResult
from app.services.gateway import GatewayService


class RecordingMetrics(NoopApplicationMetrics):
    def __init__(self, *, fail: bool = False) -> None:
        self.events: list[tuple[Any, ...]] = []
        self.fail = fail

    def _record(self, *event: Any) -> None:
        self.events.append(event)
        if self.fail:
            raise RuntimeError("metrics unavailable")

    def record_request_started(self) -> None:
        self._record("request_started")

    def record_routing_failure(self, error_type: str) -> None:
        self._record("routing_failure", error_type)

    def record_provider_call(self, provider: str, selected_model: str) -> None:
        self._record("provider_call", provider, selected_model)

    def record_provider_failure(
        self,
        provider: str,
        selected_model: str,
        error_type: str,
        latency_seconds: float,
    ) -> None:
        self._record(
            "provider_failure",
            provider,
            selected_model,
            error_type,
            latency_seconds,
        )

    def record_request_completed(
        self,
        provider: str,
        selected_model: str,
        latency_seconds: float,
    ) -> None:
        self._record("request_completed", provider, selected_model, latency_seconds)

    def record_request_failed(self, error_type: str, failure_stage: str) -> None:
        self._record("request_failed", error_type, failure_stage)


class SuccessfulProvider(ProviderAdapter):
    provider_name = "stable"

    def __init__(self) -> None:
        self.called = False

    async def generate(
        self, request: GenerateRequest, request_id: str
    ) -> ProviderResult:
        self.called = True
        return ProviderResult(
            request_id=request_id,
            provider=self.provider_name,
            model=request.model,
            output="ok",
            input_tokens=1,
            output_tokens=1,
        )


class FailingProvider(ProviderAdapter):
    provider_name = "unstable"

    async def generate(
        self, request: GenerateRequest, request_id: str
    ) -> ProviderResult:
        raise ProviderError(self.provider_name, message="free-form upstream message")


def make_request(model: str = "model-v1") -> GenerateRequest:
    return GenerateRequest(
        model=model,
        messages=[{"role": "user", "content": "private prompt"}],
    )


def make_service(
    provider: ProviderAdapter, metrics: RecordingMetrics
) -> GatewayService:
    registry = ProviderRegistry([provider])
    models = ModelRegistry([ModelDefinition("model-v1", (provider.provider_name,))])
    return GatewayService(
        routing_policy=DeterministicRoutingPolicy(models, registry),
        provider_registry=registry,
        metrics=metrics,
    )


def test_success_records_started_call_completion_and_latency_once() -> None:
    metrics = RecordingMetrics()

    response = asyncio.run(
        make_service(SuccessfulProvider(), metrics).generate(
            make_request(),
            "request-secret",
        )
    )

    assert response.output == "ok"
    assert [event[0] for event in metrics.events] == [
        "request_started",
        "provider_call",
        "request_completed",
    ]
    assert metrics.events[1] == ("provider_call", "stable", "model-v1")
    assert metrics.events[2][1:3] == ("stable", "model-v1")
    assert metrics.events[2][3] >= 0
    assert "request-secret" not in repr(metrics.events)
    assert "private prompt" not in repr(metrics.events)


def test_routing_failure_records_one_failed_request_without_provider_latency() -> None:
    metrics = RecordingMetrics()

    with pytest.raises(ModelNotFoundError):
        asyncio.run(
            make_service(SuccessfulProvider(), metrics).generate(
                make_request("unknown"),
                "request-1",
            )
        )

    assert metrics.events == [
        ("request_started",),
        ("routing_failure", "ModelNotFoundError"),
        ("request_failed", "ModelNotFoundError", "routing"),
    ]


def test_provider_failure_records_attempt_latency_and_one_failed_request() -> None:
    metrics = RecordingMetrics()

    with pytest.raises(ProviderError):
        asyncio.run(
            make_service(FailingProvider(), metrics).generate(
                make_request(),
                "request-1",
            )
        )

    assert [event[0] for event in metrics.events] == [
        "request_started",
        "provider_call",
        "provider_failure",
        "request_failed",
    ]
    assert metrics.events[2][1:4] == ("unstable", "model-v1", "ProviderError")
    assert metrics.events[2][4] >= 0
    assert metrics.events.count(("request_failed", "ProviderError", "provider")) == 1
    assert "free-form upstream message" not in repr(metrics.events)


def test_provider_timeout_uses_existing_failure_metrics_path() -> None:
    metrics = RecordingMetrics()
    provider = MockProviderAdapter(failure=TimeoutError("SDK timeout"))

    with pytest.raises(ProviderTimeoutError):
        asyncio.run(
            make_service(provider, metrics).generate(make_request(), "request-1")
        )

    assert [event[0] for event in metrics.events] == [
        "request_started",
        "provider_call",
        "provider_failure",
        "request_failed",
    ]
    assert metrics.events[2][1:4] == (
        "mock",
        "model-v1",
        "ProviderTimeoutError",
    )
    assert metrics.events[3] == (
        "request_failed",
        "ProviderTimeoutError",
        "provider",
    )


def test_metrics_failures_do_not_prevent_provider_or_successful_response() -> None:
    metrics = RecordingMetrics(fail=True)
    provider = SuccessfulProvider()

    response = asyncio.run(
        make_service(provider, metrics).generate(make_request(), "request-1")
    )

    assert provider.called
    assert response.output == "ok"
    assert [event[0] for event in metrics.events] == [
        "request_started",
        "provider_call",
        "request_completed",
    ]


def test_metrics_failures_do_not_replace_provider_error() -> None:
    metrics = RecordingMetrics(fail=True)

    with pytest.raises(ProviderError, match="free-form upstream message"):
        asyncio.run(
            make_service(FailingProvider(), metrics).generate(
                make_request(),
                "request-1",
            )
        )

    assert [event[0] for event in metrics.events] == [
        "request_started",
        "provider_call",
        "provider_failure",
        "request_failed",
    ]
