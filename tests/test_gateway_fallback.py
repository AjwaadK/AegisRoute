import asyncio

from prometheus_client import CollectorRegistry

from app.config import ProviderRetrySettings
from app.errors import ProviderTimeoutError
from app.observability.prometheus import PrometheusApplicationMetrics
from app.providers.base import ProviderAdapter
from app.providers.executor import ProviderExecutor, RetryPolicy
from app.repositories.request_log import InMemoryRequestLogRepository
from app.routing.model_registry import ModelDefinition, ModelRegistry
from app.routing.policy import DeterministicRoutingPolicy
from app.routing.provider_registry import ProviderRegistry
from app.schemas.generation import GenerateRequest, ProviderResult, TokenUsage
from app.services.gateway import GatewayService


class TimeoutProvider(ProviderAdapter):
    provider_name = "primary"

    async def generate(
        self, request: GenerateRequest, request_id: str
    ) -> ProviderResult:
        raise ProviderTimeoutError(self.provider_name)


class SuccessProvider(ProviderAdapter):
    provider_name = "fallback"

    async def generate(
        self, request: GenerateRequest, request_id: str
    ) -> ProviderResult:
        return ProviderResult(
            request_id=request_id,
            provider=self.provider_name,
            model=request.model,
            output="fallback success",
            usage=TokenUsage(input_tokens=2, output_tokens=3, total_tokens=5),
        )


def sample(
    registry: CollectorRegistry, name: str, labels: dict[str, str] | None = None
) -> float:
    value = registry.get_sample_value(name, labels or {})
    assert value is not None
    return value


def test_fallback_success_is_one_successful_logical_gateway_request() -> None:
    providers = ProviderRegistry([TimeoutProvider(), SuccessProvider()])
    models = ModelRegistry([ModelDefinition("model-v1", ("primary", "fallback"))])
    repository = InMemoryRequestLogRepository()
    registry = CollectorRegistry()
    metrics = PrometheusApplicationMetrics(registry)
    provider_executor = ProviderExecutor(
        RetryPolicy(
            ProviderRetrySettings(
                max_attempts=1,
                base_delay_seconds=0,
                max_delay_seconds=0,
                request_deadline_seconds=5,
                min_attempt_budget_seconds=0.1,
            )
        )
    )
    gateway = GatewayService(
        routing_policy=DeterministicRoutingPolicy(models, providers),
        provider_registry=providers,
        request_log_repository=repository,
        metrics=metrics,
        provider_executor=provider_executor,
    )

    response = asyncio.run(
        gateway.generate(
            GenerateRequest(
                model="model-v1",
                messages=[{"role": "user", "content": "private"}],
            ),
            "request-1",
        )
    )

    assert response.output == "fallback success"
    assert response.model == "model-v1"
    assert list(repository.requests) == ["request-1"]
    assert repository.requests["request-1"]["status"] == "completed"
    assert repository.requests["request-1"]["total_tokens"] == 5
    assert repository.requests["request-1"]["estimated_cost_usd"] is None
    assert [event["event_type"] for event in repository.events] == [
        "generation_started",
        "generation_routed",
        "generation_completed",
    ]
    assert sample(registry, "aegisroute_generation_completed_total") == 1
    assert (
        sample(
            registry,
            "aegisroute_tokens_total",
            {"provider": "fallback", "model": "model-v1", "token_type": "input"},
        )
        == 2
    )
    assert (
        registry.get_sample_value(
            "aegisroute_estimated_cost_usd_total",
            {"provider": "fallback", "model": "model-v1"},
        )
        is None
    )
    assert (
        registry.get_sample_value(
            "aegisroute_generation_failed_total",
            {"error_type": "ProviderTimeoutError", "failure_stage": "provider"},
        )
        is None
    )
    assert (
        sample(
            registry,
            "aegisroute_provider_failures_total",
            {
                "provider": "primary",
                "selected_model": "model-v1",
                "error_type": "ProviderTimeoutError",
            },
        )
        == 1
    )
    assert (
        sample(
            registry,
            "aegisroute_provider_fallbacks_total",
            {
                "from_provider": "primary",
                "to_provider": "fallback",
                "reason": "ProviderTimeoutError",
            },
        )
        == 1
    )
