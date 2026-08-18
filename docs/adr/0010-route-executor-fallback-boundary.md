# ADR 0010: Route executor fallback boundary

## Context

AegisRoute already classifies typed provider failures and executes bounded
retries for one selected provider through `ProviderExecutor`. Routing returned a
single deterministic provider/model choice, and `GatewayService` invoked that
choice directly. The gateway needs parity-level fallback behavior without
coupling provider adapters to routing policy or turning the gateway lifecycle
into one request per provider.

## Decision

- Provider adapters continue to perform one provider attempt only.
- `ProviderExecutor` continues to own retries for one selected provider.
- A new `RouteExecutor` owns execution across ordered provider/model candidates.
- Routing output retains its backward-compatible primary fields and may include
  ordered `RouteCandidate` fallbacks. The deterministic policy uses configured
  provider order and still produces the same primary route.
- Eligible retries are exhausted within a candidate before fallback is
  considered.
- Timeout, rate-limit, unavailable, and internal provider errors allow fallback
  in V1. Authentication and invalid-request errors stop the route immediately.
- All candidates share the existing monotonic total request deadline. A
  fallback starts only when the existing minimum useful attempt budget remains.
- `PROVIDER_MAX_ROUTE_ATTEMPTS` bounds unique route executions and includes the
  primary candidate. Its default is three.
- Candidate identity is the bounded provider/model pair. Each identity executes
  at most once even if routing output contains duplicates.
- `GatewayService` continues to own one logical request lifecycle across all
  retries and fallbacks. A successful fallback completes that request normally.
- Fallback transitions use bounded metrics labels and structured fields; raw
  prompts and unrestricted provider messages are excluded.

## Consequences

Single-candidate routing behaves as before. Multi-candidate routing can recover
from selected transient provider failures while preserving typed final errors,
HTTP response shape, retry semantics, and one persistence record. Provider call
and failure metrics remain attempt-level, while request completion and failure
metrics remain logical-request-level.

The persisted routing fields continue to describe the initial deterministic
routing decision. Actual fallback transitions and the successful provider are
observable in structured execution logs and Prometheus metrics without a schema
or migration change.

## Alternatives Considered

- Put fallback in provider adapters. Rejected because adapters own one attempt
  and must not choose other providers.
- Move retries into `RouteExecutor`. Rejected because retry and fallback are
  distinct policies and retries must complete within one provider first.
- Put cross-provider loops in `GatewayService`. Rejected because that would
  combine execution policy with persistence and response assembly.
- Add exception booleans for retryability or fallbackability. Rejected because
  both remain policy decisions.
- Introduce an `ExecutionPlan`, circuit breakers, or adaptive/cost/health-aware
  routing. Deferred to keep V1 bounded; no intelligence control plane is
  implemented by this decision.

## Related Components

- `RouteCandidate`, `RoutingDecision`, and `DeterministicRoutingPolicy`
- `RouteExecutor` and `FallbackPolicy`
- `ProviderExecutor`, `RetryPolicy`, and provider adapters
- `ProviderRouteSettings` and `ProviderRetrySettings`
- `GatewayService`, application composition, persistence, structured logging,
  and Prometheus application metrics
- ADR 0003, provider failure classification
- ADR 0006, Prometheus application metrics
- ADR 0008, provider retry execution boundary
