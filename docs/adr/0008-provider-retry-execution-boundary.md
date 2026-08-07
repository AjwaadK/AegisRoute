# ADR 0008: Provider Retry Execution Boundary

## Status

Accepted

## Context

AegisRoute provider adapters normalize provider-specific failures and enforce a
single provider-call timeout. Bounded retries require orchestration across
multiple adapter calls, but placing retry loops in adapters would mix transport
translation with resilience policy. Placing the loop directly in
`GatewayService` would further expand a service that already owns routing,
logical request persistence, responses, and lifecycle observability.

Retries also create two distinct failure levels. A failed provider attempt must
remain operationally visible, while a logical generation request is successful
if a permitted later attempt succeeds.

## Decision

- Provider adapters continue to perform exactly one provider attempt and keep
  provider-specific networking exceptions inside the adapter boundary.
- `RetryPolicy` classifies selected typed provider failures and calculates
  retry decisions and delays. `ProviderTimeoutError`,
  `ProviderRateLimitError`, `ProviderUnavailableError`, and
  `ProviderInternalError` are candidates. Authentication and invalid-request
  failures are not retryable.
- `ProviderExecutor` invokes the selected adapter and owns attempt counting,
  deadline accounting, sleeps, retry logs, and attempt-level metrics.
  `GatewayService` delegates provider execution and retains ownership of the
  logical generation lifecycle.
- `max_attempts` includes the original call. A value of one disables retries.
- Retry numbers are zero-based: retry zero is the first retry after the
  original attempt. Its exponential cap is the base delay. Later caps double
  until the configured maximum, and full jitter selects a delay from zero
  through that cap.
- Retry deadline arithmetic uses a monotonic clock. A retry is scheduled only
  when its failure is retryable, another attempt remains, and the remaining
  gateway deadline can cover both the selected sleep and the configured
  minimum useful attempt budget. Each attempt is also bounded by the remaining
  deadline.
- Clock, sleep, and jitter dependencies are replaceable for deterministic
  tests. `asyncio.CancelledError` is never caught or retried.
- Provider call and provider failure metrics have attempt-level semantics.
  `aegisroute_provider_retries_total` increments only when a retry is actually
  scheduled, with bounded `provider` and `error_type` labels. Generation
  completion/failure metrics and persistence retain logical-request semantics.
- The existing generation latency histogram continues to observe each failed
  provider attempt through `record_provider_failure` and the eventual logical
  completion or terminal failure through the existing lifecycle path. This
  preserves the established metric contract while making transient attempt
  failures visible.
- Provider rate-limit errors do not currently carry stable retry-after
  metadata, so `Retry-After` parsing is deferred.

## Consequences

Transient failures can recover without being reported or persisted as logical
request failures. Operators can count provider attempts, failed attempts, and
scheduled retries separately. Retry behavior is bounded by both attempts and
time, and deterministic tests do not sleep in real time.

The executor is a new provider-execution boundary and adds one dependency to
the gateway composition graph. Metrics consumers must understand that provider
call/failure series describe attempts, whereas generation and persistence
series describe logical requests.

Fallback routing and circuit breakers remain deferred. The executor boundary
keeps those future policies above single-attempt adapters without requiring a
rewrite of `GatewayService`.

## Alternatives considered

- Put retry loops in each provider adapter. Rejected because adapters must
  normalize and execute one provider attempt consistently.
- Put retry orchestration directly in `GatewayService`. Rejected because it
  couples resilience details to routing, persistence, and response assembly.
- Mark exceptions with a `retryable` boolean. Rejected because retryability is
  deployment policy, not intrinsic exception metadata.
- Retry every `ProviderError` or every exception. Rejected because
  authentication, invalid requests, cancellation, and unknown programming
  failures should fail immediately.
- Add fallback routing or circuit breakers in the same change. Rejected to keep
  this policy bounded and independently testable.

## Related components

- `ProviderRetrySettings`
- `RetryPolicy`
- `ProviderExecutor`
- `ProviderAdapter`
- `GatewayService`
- `ApplicationMetrics` and `PrometheusApplicationMetrics`
- application composition and structured logging
- ADR 0003, provider error classification
- ADR 0006, Prometheus application metrics
