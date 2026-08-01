# Build Log

## Gateway Routing Integration V1 — 2026-07-28

- Summary: Integrated `GatewayService` with the existing routing policy and
  provider registry, added routing observability and distinct HTTP error
  mappings, and preserved request logging and repository fail-open behavior.
- Important decisions: Unsupported models map to 422, missing selected
  providers map to a generic 500, and invoked-provider failures map to 502.
- Why: The distinction separates client input, internal invariant, and upstream
  availability incidents without exposing routing internals.
- Validation: Focused and complete automated test results recorded in the
  feature commit handoff.
- Next planned architectural step: Add additional routing policies while
  retaining the same gateway orchestration contract.

## Routing Observability and Persistence V1 — 2026-07-29

- Schema and repository changes: Renamed persisted `model` to
  `requested_model`, added nullable `selected_model` and `routing_reason`, made
  the selected-provider field nullable, and added an atomic `mark_routed`
  lifecycle operation and routed event.
- Lifecycle decision: Persist request start before routing and persist the full
  routing decision before provider resolution and invocation; completion and
  failure preserve that evidence.
- Observability rationale: Distinguishes failures before routing from failures
  after a provider and model were selected while keeping persistence fail-open.
- Validation: Focused repository, gateway, migration, HTTP, and full-suite
  results are recorded in the feature handoff.
- Next likely step: Query and aggregate persisted routing outcomes for
  operational diagnostics.

## Prometheus Metrics V1 — 2026-07-31

- Metrics added: Live generation request, completion, failure, provider-call,
  provider-failure, routing-failure, and provider-attempt latency metrics are
  exposed through `GET /metrics` using a process-scoped isolated registry.
- Label/cardinality policy: Labels are limited to configured provider names,
  routed model names, stable exception class names, and bounded failure stages;
  request IDs, prompts, error messages, and free-form routing reasons are
  forbidden.
- Latency semantics: The histogram records all requests that reached provider
  invocation, including successful calls and `ProviderError` failures, and
  excludes pre-routing failures. It measures end-to-end Gateway time without
  changing the existing provider-call latency in persistence or responses.
- Failure policy: Metrics are injected through an application contract and all
  recording remains fail-open so telemetry cannot replace generation responses
  or routing/provider errors.
- Validation: Focused metrics, gateway, HTTP, and composition tests plus the
  complete configured suite validate isolated registries, exact labels,
  single-count failures, and unchanged generation behavior.
- Next step: Prometheus server and Grafana Dashboard V1.
