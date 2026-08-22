import asyncio
from decimal import Decimal

import pytest

from app.accounting import CostEstimator, ModelPricing, PricingCatalog
from app.errors import ProviderTimeoutError
from app.observability.metrics import NoopApplicationMetrics
from app.providers.mock import MockProviderAdapter
from app.repositories.request_log import InMemoryRequestLogRepository
from app.routing.model_registry import ModelDefinition, ModelRegistry
from app.routing.policy import DeterministicRoutingPolicy
from app.routing.provider_registry import ProviderRegistry
from app.schemas.generation import GenerateRequest, StreamCompleted, TokenUsage
from app.services.gateway import GatewayService


class RecordingMetrics(NoopApplicationMetrics):
    def __init__(self) -> None:
        self.started = 0
        self.completed = 0
        self.failed: list[str] = []
        self.logical_completed = 0
        self.logical_failed = 0
        self.tokens: list[tuple[int | None, int | None]] = []
        self.costs: list[Decimal] = []

    def record_stream_started(self) -> None:
        self.started += 1

    def record_stream_completed(self, provider: str, model: str) -> None:
        self.completed += 1

    def record_stream_failed(self, provider: str, model: str, stage: str) -> None:
        self.failed.append(stage)

    def record_request_completed(
        self, provider: str, selected_model: str, latency_seconds: float
    ) -> None:
        self.logical_completed += 1

    def record_request_failed(self, error_type: str, failure_stage: str) -> None:
        self.logical_failed += 1

    def record_tokens(
        self,
        provider: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        self.tokens.append((input_tokens, output_tokens))

    def record_estimated_cost(
        self, provider: str, model: str, estimated_cost_usd: Decimal
    ) -> None:
        self.costs.append(estimated_cost_usd)


def request() -> GenerateRequest:
    return GenerateRequest(
        model="model-v1",
        messages=[{"role": "user", "content": "do not persist this text"}],
    )


def service(
    provider: MockProviderAdapter,
    repository: InMemoryRequestLogRepository,
    metrics: RecordingMetrics,
    *,
    priced: bool = False,
) -> GatewayService:
    registry = ProviderRegistry([provider])
    models = ModelRegistry([ModelDefinition("model-v1", (provider.provider_name,))])
    catalog = PricingCatalog(
        (
            ModelPricing(
                provider.provider_name,
                "model-v1",
                Decimal(1),
                Decimal(2),
            ),
        )
        if priced
        else ()
    )
    return GatewayService(
        routing_policy=DeterministicRoutingPolicy(models, registry),
        provider_registry=registry,
        request_log_repository=repository,
        metrics=metrics,
        cost_estimator=CostEstimator(catalog),
    )


async def collect(gateway: GatewayService):
    return [event async for event in gateway.stream(request(), "request-1")]


def test_successful_stream_completes_one_lifecycle_with_observed_accounting() -> None:
    usage = TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15)
    provider = MockProviderAdapter(
        stream_chunks=("hello", " world"), stream_usage=usage
    )
    repository = InMemoryRequestLogRepository()
    metrics = RecordingMetrics()

    events = asyncio.run(collect(service(provider, repository, metrics, priced=True)))

    assert isinstance(events[-1], StreamCompleted)
    assert repository.requests["request-1"]["status"] == "completed"
    assert repository.requests["request-1"]["input_tokens"] == 10
    assert repository.requests["request-1"]["output_tokens"] == 5
    assert repository.requests["request-1"]["estimated_cost_usd"] == Decimal(
        "0.000020000000"
    )
    assert len(repository.requests) == 1
    assert all("hello" not in repr(event) for event in repository.events)
    assert metrics.started == 1
    assert metrics.completed == 1
    assert metrics.logical_completed == 1
    assert metrics.logical_failed == 0
    assert metrics.tokens == [(10, 5)]


def test_missing_final_usage_does_not_fabricate_tokens_or_cost() -> None:
    repository = InMemoryRequestLogRepository()
    metrics = RecordingMetrics()

    asyncio.run(
        collect(
            service(MockProviderAdapter(stream_chunks=("text",)), repository, metrics)
        )
    )

    row = repository.requests["request-1"]
    assert row["input_tokens"] is None
    assert row["output_tokens"] is None
    assert row["estimated_cost_usd"] is None
    assert metrics.tokens == [(None, None)]
    assert metrics.costs == []


def test_post_commit_failure_is_failed_not_completed_and_persists_no_text() -> None:
    repository = InMemoryRequestLogRepository()
    metrics = RecordingMetrics()
    error = ProviderTimeoutError("mock")
    provider = MockProviderAdapter(
        stream_chunks=("partial secret output",),
        stream_failure=error,
        stream_failure_after_chunks=1,
    )
    seen = []

    async def consume() -> None:
        async for event in service(provider, repository, metrics).stream(
            request(), "request-1"
        ):
            seen.append(event)

    with pytest.raises(ProviderTimeoutError):
        asyncio.run(consume())

    row = repository.requests["request-1"]
    assert row["status"] == "failed"
    assert row["error_type"] == "stream_failed_after_commit"
    assert metrics.failed == ["post_commit"]
    assert metrics.logical_completed == 0
    assert metrics.logical_failed == 1
    assert "partial secret output" not in repr(repository.requests)
    assert "partial secret output" not in repr(repository.events)


def test_precommit_terminal_failure_records_failed_lifecycle() -> None:
    repository = InMemoryRequestLogRepository()
    metrics = RecordingMetrics()
    provider = MockProviderAdapter(
        stream_failure=ProviderTimeoutError("mock"),
        stream_failure_after_chunks=0,
    )

    with pytest.raises(ProviderTimeoutError):
        asyncio.run(collect(service(provider, repository, metrics)))

    assert repository.requests["request-1"]["status"] == "failed"
    assert repository.requests["request-1"]["error_type"] == (
        "stream_failed_before_commit"
    )
    assert metrics.failed == ["pre_commit"]
    assert metrics.logical_completed == 0


def test_consumer_close_after_commit_records_cancellation_not_success() -> None:
    repository = InMemoryRequestLogRepository()
    metrics = RecordingMetrics()
    gateway = service(
        MockProviderAdapter(stream_chunks=("first", "second")),
        repository,
        metrics,
    )

    async def consume_one_then_close() -> None:
        stream = gateway.stream(request(), "request-1")
        await anext(stream)
        await stream.aclose()

    asyncio.run(consume_one_then_close())

    row = repository.requests["request-1"]
    assert row["status"] == "failed"
    assert row["error_type"] == "stream_cancelled"
    assert metrics.failed == ["post_commit"]
    assert metrics.logical_completed == 0
