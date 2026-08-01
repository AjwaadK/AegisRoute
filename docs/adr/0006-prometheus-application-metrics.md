# ADR 0006: Prometheus Application Metrics

## Status

Accepted

## Context

AegisRoute has structured lifecycle logging and PostgreSQL request history, but
neither provides process-live counters and latency distributions suitable for
operational scraping. Historical PostgreSQL analytics and live operational
telemetry answer different questions and must keep separate semantics.

Metrics can also create availability and privacy risks. Process-global
collectors can fail during repeated application construction, instrumentation
exceptions can mask generation results, and unbounded labels can leak request
data or exhaust the monitoring system.

## Decision

- `GatewayService` emits lifecycle metrics through an injected application-owned
  contract and does not depend on Prometheus globals.
- The Prometheus implementation owns its collectors and uses an explicit
  `CollectorRegistry`. The composition root creates one registry and one metrics
  implementation per application process and injects the implementation into
  `GatewayService`.
- Metric recording is fail-open. The gateway's narrow metrics boundary logs and
  swallows instrumentation exceptions without replacing routing errors,
  provider errors, or successful generation responses.
- Labels are limited to provider names from `ProviderRegistry`, selected model
  names from routing decisions, stable exception class names, and the bounded
  failure stages `routing`, `provider`, and `internal`.
- Request IDs, prompts, error messages, timestamps, database IDs, arbitrary
  query strings, and free-form routing reasons are forbidden as metric labels.
- The latency histogram records every request that reached provider invocation,
  including successful calls and `ProviderError` failures. It does not observe
  failures before provider invocation. Its duration is measured end-to-end from
  entry into `GatewayService`, independently of the existing provider-call
  latency used by persistence and the public response. Its explicit buckets are
  0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, and 120 seconds.
- V1 exposes the application registry through read-only `GET /metrics` in the
  Prometheus exposition format. It does not add a Prometheus server, Grafana
  dashboards, or alerting.
- Default Python and process collectors are omitted from the isolated application
  registry.

## Consequences

Operators can scrape live request volume, completion and failure counts,
routing and provider failures, provider attempts, and latency distributions
without changing persistence or historical analytics. Tests and repeated app
construction use isolated registries, avoiding duplicate-timeseries errors.

Instrumentation is intentionally best-effort, so a metrics outage does not
reduce generation availability. The bounded dimensions limit operational
cardinality, while model and provider configuration growth still needs normal
monitoring. V1 provides raw telemetry only; dashboards and alerting remain a
separate deployment concern.

## Alternatives considered

- Use Prometheus's process-global default registry. Rejected because repeated
  app construction can produce duplicate-registration failures and tests would
  share state.
- Derive live operations exclusively from PostgreSQL analytics. Rejected because
  database history is not a substitute for scrape-time counters and histograms
  and would couple telemetry availability to persistence.
- Call `prometheus_client` collectors directly from `GatewayService`. Rejected
  because it couples application orchestration to one telemetry backend and
  makes disabled or isolated test metrics harder.
- Add request IDs, prompts, error messages, or routing reasons as labels.
  Rejected because these values are sensitive or unbounded.
- Observe only successful latency. Rejected because failed upstream attempts
  consume time and are operationally important.

## Related components

- `ApplicationMetrics`
- `NoopApplicationMetrics`
- `PrometheusApplicationMetrics`
- `GatewayService`
- `ApplicationContainer` and the composition root
- `GET /metrics`
- structured application logging
- PostgreSQL request logging and historical analytics
