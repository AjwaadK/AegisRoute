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

### Follow-up: PostgreSQL Test Isolation

- Migration and SQLAlchemy repository tests now run in disposable PostgreSQL schemas.
- This prevents ORM-created schema state from drifting from Alembic revision state.
- Shared public database schemas are no longer modified by integration tests.
- Two consecutive configured runs passed with 105 tests.

## Routing Analytics Query Layer V1 — 2026-07-30

- Metrics: Added request totals, success/failure rates, nullable-latency
  averages, provider/model counts, route distribution, provider metrics, and
  failure groupings by error type and lifecycle stage.
- Query boundary: A separate read repository performs six bounded PostgreSQL
  aggregates and returns immutable analytics values to a service; HTTP receives
  only typed summaries.
- Semantics: Null dimensions are omitted, null latency is excluded, routed
  events distinguish before/after-routing failures, and time windows are
  inclusive at start and exclusive at end.
- Validation: Focused and full-suite pass/skip/warning counts are recorded in
  the implementation handoff.
- Next likely step: Observe production query plans and add an index only when
  measured workload demonstrates a need.

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

## Containerized Local Observability Stack V1 — 2026-08-01

- Feature and services: Added a Docker Compose development stack containing
  AegisRoute, PostgreSQL, a one-shot migration service, Prometheus, and Grafana.
- Networking: Compose DNS names connect the application to `postgres`, the
  Prometheus scrape job to `aegisroute:8000/metrics`, and Grafana to
  `prometheus:9090`; localhost ports remain available to the developer.
- Migration ownership: Alembic runs once after PostgreSQL becomes healthy, and
  the application starts only after migrations complete successfully.
- Provisioning: Prometheus uses a checked-in 15-second scrape configuration;
  Grafana loads a stable-UID Prometheus datasource and the checked-in dashboard
  automatically without persistent UI state.
- Dashboard: `AegisRoute Overview` shows request and success rates, failures by
  lifecycle stage, p95 generation latency, provider traffic and failures, and
  routing failures using only existing application metrics.
- Validation: The pre-change Python suite passed (114 passed, 14 PostgreSQL
  integration tests skipped). Static Compose, YAML, JSON, secret, DNS, metric,
  migration/model, and diff checks were performed; runtime stack validation was
  unavailable because Docker is not installed in the execution environment.
- Next likely step: Exercise the stack with representative traffic in a Docker
  environment, then define alert thresholds and Alertmanager separately.

## Traffic Generator V1 — 2026-08-03

- Feature and purpose: Added a standalone asynchronous HTTP CLI that generates
  representative local traffic so live AegisRoute observability panels can be
  exercised without changing application runtime behavior.
- Controls: Target base URL, duration, bounded worker concurrency, intentional
  unsupported-model failure rate, request timeout, and valid model are
  configurable.
- Summary statistics: Reports total requests, successful responses, expected
  injected failures, unexpected HTTP failures, transport errors, elapsed time,
  throughput, and minimum, average, p95, and maximum response latency.
- Validation: Focused mocked-transport tests cover argument validation, outcome
  classification, safe latency aggregation, bounded concurrency, and shared
  client reuse; complete-suite and repository hygiene results are recorded in
  the feature handoff.
- Next likely step: Use measured development traffic patterns to inform a
  separate, explicitly scoped load-testing or alert-threshold effort.

## Apache License 2.0 — 2026-08-04

- Added the canonical Apache License 2.0 text and a concise NOTICE file.
- Added README documentation linking to the repository license.
- No application behavior changed.
- Validation confirmed the license files, documentation link, intended change
  scope, repository hygiene, and passing test suite.
