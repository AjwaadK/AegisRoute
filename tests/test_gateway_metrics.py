import asyncio
import json
import logging
from typing import Any

import pytest

from app.config import ProviderRetrySettings
from app.core.logging import LOGGER_NAME
from app.errors import ModelNotFoundError, ProviderError, ProviderTimeoutError
from app.observability.metrics import NoopApplicationMetrics
from app.providers.base import ProviderAdapter
from app.providers.executor import ProviderExecutor, RetryPolicy
from app.providers.mock import MockProviderAdapter
from app.repositories.request_log import InMemoryRequestLogRepository
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

    def record_provider_retry(self, provider: str, error_type: str) -> None:
        self._record("provider_retry", provider, error_type)

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


class TimeoutThenSuccessProvider(SuccessfulProvider):
    provider_name = "flaky"

    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    async def generate(
        self, request: GenerateRequest, request_id: str
    ) -> ProviderResult:
        self.attempts += 1
        if self.attempts == 1:
            raise ProviderTimeoutError(
                self.provider_name,
                provider_code="timeout",
                message="temporary timeout",
            )
        return await super().generate(request, request_id)


def make_request(model: str = "model-v1") -> GenerateRequest:
    return GenerateRequest(
        model=model,
        messages=[{"role": "user", "content": "private prompt"}],
    )


def make_service(
    provider: ProviderAdapter,
    metrics: RecordingMetrics,
    *,
    provider_executor: ProviderExecutor | None = None,
    request_log_repository=None,
) -> GatewayService:
    registry = ProviderRegistry([provider])
    models = ModelRegistry([ModelDefinition("model-v1", (provider.provider_name,))])
    return GatewayService(
        routing_policy=DeterministicRoutingPolicy(models, registry),
        provider_registry=registry,
        metrics=metrics,
        provider_executor=provider_executor,
        request_log_repository=request_log_repository,
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
        "provider_retry",
        "provider_call",
        "provider_failure",
        "request_failed",
    ]
    assert metrics.events[2][1:4] == (
        "mock",
        "model-v1",
        "ProviderTimeoutError",
    )
    assert metrics.events[3] == ("provider_retry", "mock", "ProviderTimeoutError")
    assert metrics.events[6] == (
        "request_failed",
        "ProviderTimeoutError",
        "provider",
    )


def test_retry_success_preserves_attempt_metrics_and_one_logical_lifecycle(
    caplog,
) -> None:
    metrics = RecordingMetrics()
    provider = TimeoutThenSuccessProvider()
    repository = InMemoryRequestLogRepository()
    policy = RetryPolicy(
        ProviderRetrySettings(
            max_attempts=2,
            base_delay_seconds=0,
            max_delay_seconds=0,
            request_deadline_seconds=10,
            min_attempt_budget_seconds=0.1,
        ),
        jitter=lambda lower, upper: 0,
    )

    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        response = asyncio.run(
            make_service(
                provider,
                metrics,
                provider_executor=ProviderExecutor(policy),
                request_log_repository=repository,
            ).generate(make_request(), "request-1")
        )

    assert response.output == "ok"
    assert provider.attempts == 2
    assert [event[0] for event in metrics.events] == [
        "request_started",
        "provider_call",
        "provider_failure",
        "provider_retry",
        "provider_call",
        "request_completed",
    ]
    assert not any(event[0] == "request_failed" for event in metrics.events)
    assert list(repository.requests) == ["request-1"]
    assert repository.requests["request-1"]["status"] == "completed"
    assert [event["event_type"] for event in repository.events] == [
        "generation_started",
        "generation_routed",
        "generation_completed",
    ]
    retry_log = next(
        json.loads(record.message)
        for record in caplog.records
        if json.loads(record.message).get("event") == "provider_retry_scheduled"
    )
    assert retry_log["request_id"] == "request-1"
    assert retry_log["provider"] == "flaky"
    assert retry_log["attempt"] == 1
    assert retry_log["error_type"] == "ProviderTimeoutError"
    assert retry_log["delay_seconds"] == 0
    assert retry_log["remaining_deadline_seconds"] > 0
    assert "private prompt" not in json.dumps(retry_log)


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
