# ADR 0011: Token and cost accounting

## Status

Accepted

## Context

AegisRoute already receives token counts from providers and persists input and
output counts on the logical generation request. The existing result contract
cannot represent absent or partial provider usage cleanly, and pricing does not
belong in provider adapters. Estimated cost must preserve request-time history
without making provider telemetry or configured pricing an availability
dependency.

Provider billing may include work from failed or timed-out attempts for which
AegisRoute receives no usage metadata. Local accounting therefore cannot be
treated as invoice truth.

## Decision

- Provider adapters emit immutable, provider-neutral `TokenUsage` facts with
  nullable input, output, and total token counts. They do not emit SDK usage
  objects or contain pricing logic.
- `PricingCatalog` performs deterministic exact provider/model lookup. V1 ships
  with an empty default catalog; configured test or deployment entries use USD
  `Decimal` rates per million tokens and no runtime network access.
- `CostEstimator` returns unknown unless exact pricing plus observed input and
  output counts are available. It never guesses a related model or derives a
  missing total. Known estimates are rounded half-up only at the final step to
  12 decimal places in USD.
- `GatewayService` estimates cost after the final successful observed response.
  Missing usage, missing pricing, or an expected accounting availability error
  does not alter generation success.
- Logical generation requests persist nullable `BIGINT` input, output, and
  total counts plus `NUMERIC(30,12)` `estimated_cost_usd`. Twelve fractional
  digits retain useful precision for very small requests; 18 integer digits
  accommodate large aggregates without implying invoice-grade accounting.
- Historical estimated cost is stored at execution time and is not recomputed
  from a later catalog.
- Prometheus records observed input/output token counters and known estimated
  cost only. Metrics use bounded provider/model/token-type labels and float
  representation; PostgreSQL remains the precise accounting source.
- V1 persists only the final observed logical-request usage and estimate.
  Attempt-level accounting is deferred because retries and fallbacks currently
  expose attempts through logs and metrics, not persisted attempt records.

## Consequences

Successful requests can retain factual usage even when their cost is unknown.
Existing rows remain valid with null accounting fields, and no historical
values are fabricated. Public response field names remain unchanged, while
input or output counts may be null when a provider reports no usage.

The recorded value is observed/estimated cost. A provider can bill work for a
failed or timed-out attempt without returning usage, so the provider billing
system remains authoritative.

## Alternatives Considered

- Put static prices in provider adapters. Rejected because adapters translate
  provider facts and must remain independent of cost policy.
- Infer pricing from similar model names or derive costs from total tokens.
  Rejected because input and output rates may differ and guessing would create
  false accounting facts.
- Fetch or synchronize live pricing. Deferred; V1 is deterministic, static,
  and network-free.
- Persist accounting on every generation event. Deferred because current
  events describe logical lifecycle transitions rather than provider attempts.
- Add cost-aware routing, billing, budgets, quotas, or currency conversion.
  Deferred outside this accounting slice.

## Related Components

- `TokenUsage` and `ProviderResult`
- `OpenAIProviderAdapter` and `MockProviderAdapter`
- `PricingCatalog`, `ModelPricing`, and `CostEstimator`
- `GatewayService` and `RequestLogRepository`
- `GenerationRequest` and Alembic revision `20260811_0003`
- `ApplicationMetrics` and `PrometheusApplicationMetrics`
- ADR 0006, Prometheus application metrics
- ADR 0008, provider retry execution boundary
- ADR 0010, route executor fallback boundary
