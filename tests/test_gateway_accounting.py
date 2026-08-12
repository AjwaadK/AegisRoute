import asyncio
from decimal import Decimal

from prometheus_client import CollectorRegistry

from app.accounting import AccountingError, CostEstimator, ModelPricing, PricingCatalog
from app.observability.prometheus import PrometheusApplicationMetrics
from app.providers.base import ProviderAdapter
from app.repositories.request_log import InMemoryRequestLogRepository
from app.routing.model_registry import ModelDefinition, ModelRegistry
from app.routing.policy import DeterministicRoutingPolicy
from app.routing.provider_registry import ProviderRegistry
from app.schemas.generation import GenerateRequest, ProviderResult, TokenUsage
from app.services.gateway import GatewayService


class UsageProvider(ProviderAdapter):
    provider_name = "usage-provider"

    def __init__(self, usage: TokenUsage | None) -> None:
        super().__init__()
        self.usage = usage

    async def generate(
        self, request: GenerateRequest, request_id: str
    ) -> ProviderResult:
        return ProviderResult(
            request_id=request_id,
            provider=self.provider_name,
            model=request.model,
            output="ok",
            usage=self.usage,
        )


class UnavailableEstimator(CostEstimator):
    def estimate_usd(self, provider, model, usage):
        raise AccountingError("catalog unavailable")


def make_gateway(
    usage: TokenUsage | None,
    estimator: CostEstimator,
) -> tuple[GatewayService, InMemoryRequestLogRepository, CollectorRegistry]:
    provider = UsageProvider(usage)
    providers = ProviderRegistry([provider])
    models = ModelRegistry([ModelDefinition("model-a", (provider.provider_name,))])
    repository = InMemoryRequestLogRepository()
    registry = CollectorRegistry()
    gateway = GatewayService(
        routing_policy=DeterministicRoutingPolicy(models, providers),
        provider_registry=providers,
        request_log_repository=repository,
        metrics=PrometheusApplicationMetrics(registry),
        cost_estimator=estimator,
    )
    return gateway, repository, registry


def request() -> GenerateRequest:
    return GenerateRequest(
        model="model-a",
        messages=[{"role": "user", "content": "private prompt"}],
    )


def test_gateway_persists_observed_usage_and_request_time_decimal_cost() -> None:
    estimator = CostEstimator(
        PricingCatalog(
            (
                ModelPricing(
                    "usage-provider",
                    "model-a",
                    Decimal("2.00"),
                    Decimal("8.00"),
                ),
            )
        )
    )
    gateway, repository, registry = make_gateway(
        TokenUsage(input_tokens=100, output_tokens=25, total_tokens=125), estimator
    )

    response = asyncio.run(gateway.generate(request(), "request-1"))

    assert response.output == "ok"
    assert response.input_tokens == 100
    assert response.output_tokens == 25
    assert list(repository.requests) == ["request-1"]
    persisted = repository.requests["request-1"]
    assert persisted["total_tokens"] == 125
    assert persisted["estimated_cost_usd"] == Decimal("0.000400000000")
    assert (
        registry.get_sample_value(
            "aegisroute_estimated_cost_usd_total",
            {"provider": "usage-provider", "model": "model-a"},
        )
        == 0.0004
    )


def test_gateway_unknown_pricing_succeeds_and_persists_null_cost() -> None:
    gateway, repository, registry = make_gateway(
        TokenUsage(input_tokens=3, output_tokens=4, total_tokens=None),
        CostEstimator(),
    )

    response = asyncio.run(gateway.generate(request(), "request-1"))

    assert response.output == "ok"
    assert repository.requests["request-1"]["input_tokens"] == 3
    assert repository.requests["request-1"]["estimated_cost_usd"] is None
    assert (
        registry.get_sample_value(
            "aegisroute_estimated_cost_usd_total",
            {"provider": "usage-provider", "model": "model-a"},
        )
        is None
    )


def test_gateway_absent_usage_succeeds_with_null_accounting() -> None:
    gateway, repository, registry = make_gateway(None, CostEstimator())

    response = asyncio.run(gateway.generate(request(), "request-1"))

    assert response.input_tokens is None
    assert response.output_tokens is None
    assert repository.requests["request-1"]["input_tokens"] is None
    assert repository.requests["request-1"]["estimated_cost_usd"] is None
    assert (
        registry.get_sample_value(
            "aegisroute_tokens_total",
            {"provider": "usage-provider", "model": "model-a", "token_type": "input"},
        )
        is None
    )


def test_expected_accounting_failure_does_not_change_generation_success() -> None:
    gateway, repository, _registry = make_gateway(
        TokenUsage(input_tokens=3, output_tokens=4),
        UnavailableEstimator(),
    )

    response = asyncio.run(gateway.generate(request(), "request-1"))

    assert response.output == "ok"
    assert repository.requests["request-1"]["status"] == "completed"
    assert repository.requests["request-1"]["estimated_cost_usd"] is None
