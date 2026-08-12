"""Provider-neutral, deterministic token cost estimation."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext

from app.schemas.generation import TokenUsage

TOKENS_PER_MILLION = Decimal(1000000)
COST_QUANTUM_USD = Decimal("0.000000000001")


class AccountingError(RuntimeError):
    """Expected accounting failure that must not affect generation success."""


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Configured USD prices for one exact provider/model identity."""

    provider: str
    model: str
    input_cost_per_million_tokens: Decimal | None
    output_cost_per_million_tokens: Decimal | None

    def __post_init__(self) -> None:
        if not self.provider or not self.model:
            raise ValueError("provider and model must be non-empty")
        for name, value in (
            ("input_cost_per_million_tokens", self.input_cost_per_million_tokens),
            ("output_cost_per_million_tokens", self.output_cost_per_million_tokens),
        ):
            if value is not None and not isinstance(value, Decimal):
                raise TypeError(f"{name} must be a Decimal or None")
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")


class PricingCatalog:
    """Immutable exact-match catalog; unknown identities return no pricing."""

    def __init__(self, entries: tuple[ModelPricing, ...] = ()) -> None:
        prices: dict[tuple[str, str], ModelPricing] = {}
        for entry in entries:
            identity = (entry.provider, entry.model)
            if identity in prices:
                raise ValueError(f"duplicate pricing entry for {identity!r}")
            prices[identity] = entry
        self._prices = prices

    def get(self, provider: str, model: str) -> ModelPricing | None:
        return self._prices.get((provider, model))


class CostEstimator:
    """Estimate and quantize request cost without network access or guessing."""

    def __init__(self, catalog: PricingCatalog | None = None) -> None:
        self._catalog = catalog or PricingCatalog()

    def estimate_usd(
        self,
        provider: str,
        model: str,
        usage: TokenUsage | None,
    ) -> Decimal | None:
        if usage is None:
            return None
        pricing = self._catalog.get(provider, model)
        if pricing is None:
            return None
        if usage.input_tokens is None or usage.output_tokens is None:
            return None
        if (
            pricing.input_cost_per_million_tokens is None
            or pricing.output_cost_per_million_tokens is None
        ):
            return None

        with localcontext() as context:
            context.prec = 50
            input_cost = (
                Decimal(usage.input_tokens)
                * pricing.input_cost_per_million_tokens
                / TOKENS_PER_MILLION
            )
            output_cost = (
                Decimal(usage.output_tokens)
                * pricing.output_cost_per_million_tokens
                / TOKENS_PER_MILLION
            )
            return (input_cost + output_cost).quantize(
                COST_QUANTUM_USD,
                rounding=ROUND_HALF_UP,
            )


__all__ = (
    "COST_QUANTUM_USD",
    "AccountingError",
    "CostEstimator",
    "ModelPricing",
    "PricingCatalog",
)
