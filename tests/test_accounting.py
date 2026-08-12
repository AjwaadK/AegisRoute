from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.accounting import COST_QUANTUM_USD, CostEstimator, ModelPricing, PricingCatalog
from app.schemas.generation import ProviderResult, TokenUsage


def pricing(
    *,
    provider: str = "provider-a",
    model: str = "model-a",
    input_rate: Decimal | None = Decimal("2.50"),
    output_rate: Decimal | None = Decimal("10.00"),
) -> ModelPricing:
    return ModelPricing(provider, model, input_rate, output_rate)


def test_token_usage_supports_values_and_absent_fields() -> None:
    assert TokenUsage(input_tokens=1, output_tokens=2, total_tokens=3) == TokenUsage(
        input_tokens=1,
        output_tokens=2,
        total_tokens=3,
    )
    assert TokenUsage() == TokenUsage(
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
    )


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens", "total_tokens"])
def test_token_usage_rejects_negative_counts(field: str) -> None:
    with pytest.raises(ValidationError):
        TokenUsage(**{field: -1})


def test_provider_result_contains_only_provider_neutral_usage() -> None:
    result = ProviderResult(
        request_id="request-1",
        provider="provider-a",
        model="model-a",
        output="ok",
        usage=TokenUsage(input_tokens=1, output_tokens=2),
    )

    assert type(result.usage) is TokenUsage
    assert result.input_tokens == 1
    assert result.output_tokens == 2
    assert result.total_tokens is None


def test_pricing_catalog_uses_deterministic_exact_identity_lookup() -> None:
    entry = pricing()
    catalog = PricingCatalog((entry,))

    assert catalog.get("provider-a", "model-a") is entry
    assert catalog.get("provider-a", "model-b") is None
    assert catalog.get("provider-b", "model-a") is None
    assert catalog.get("provider-a", "model-a") is entry


def test_cost_estimator_calculates_decimal_cost() -> None:
    estimator = CostEstimator(PricingCatalog((pricing(),)))

    result = estimator.estimate_usd(
        "provider-a",
        "model-a",
        TokenUsage(input_tokens=1_000_000, output_tokens=500_000),
    )

    assert result == Decimal("7.500000000000")
    assert isinstance(result, Decimal)


def test_cost_estimator_handles_large_and_very_small_usage() -> None:
    estimator = CostEstimator(
        PricingCatalog(
            (
                pricing(
                    input_rate=Decimal("0.000001"),
                    output_rate=Decimal("0.000001"),
                ),
            )
        )
    )

    assert (
        estimator.estimate_usd(
            "provider-a", "model-a", TokenUsage(input_tokens=1, output_tokens=0)
        )
        == COST_QUANTUM_USD
    )
    assert estimator.estimate_usd(
        "provider-a",
        "model-a",
        TokenUsage(input_tokens=9_000_000_000, output_tokens=9_000_000_000),
    ) == Decimal("0.018000000000")


def test_cost_estimator_returns_zero_for_observed_zero_usage() -> None:
    estimator = CostEstimator(PricingCatalog((pricing(),)))

    assert estimator.estimate_usd(
        "provider-a", "model-a", TokenUsage(input_tokens=0, output_tokens=0)
    ) == Decimal("0E-12")


@pytest.mark.parametrize(
    ("catalog", "usage"),
    [
        (PricingCatalog(), TokenUsage(input_tokens=1, output_tokens=1)),
        (PricingCatalog((pricing(),)), None),
        (PricingCatalog((pricing(),)), TokenUsage(input_tokens=1)),
        (
            PricingCatalog((pricing(input_rate=None),)),
            TokenUsage(input_tokens=1, output_tokens=1),
        ),
        (
            PricingCatalog((pricing(output_rate=None),)),
            TokenUsage(input_tokens=1, output_tokens=1),
        ),
    ],
)
def test_cost_estimator_returns_unknown_when_inputs_are_incomplete(
    catalog: PricingCatalog, usage: TokenUsage | None
) -> None:
    assert CostEstimator(catalog).estimate_usd("provider-a", "model-a", usage) is None


def test_cost_estimator_does_not_guess_similar_models() -> None:
    estimator = CostEstimator(PricingCatalog((pricing(model="model-a-v2"),)))

    assert (
        estimator.estimate_usd(
            "provider-a",
            "model-a",
            TokenUsage(input_tokens=100, output_tokens=100),
        )
        is None
    )


def test_pricing_rejects_binary_float_rates() -> None:
    with pytest.raises(TypeError):
        pricing(input_rate=0.1)  # type: ignore[arg-type]
