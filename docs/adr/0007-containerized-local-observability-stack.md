# ADR 0007: Containerized Local Observability Stack

## Status

Accepted

## Context

AegisRoute already exposes bounded application metrics through `GET /metrics`,
but contributors need a reproducible way to run the application database,
collect those metrics, and inspect an operational dashboard. Manual local
service configuration is difficult to reproduce and obscures migration and
service-discovery ownership.

## Decision

- Docker Compose manages the local AegisRoute, PostgreSQL, Prometheus, and
  Grafana stack.
- Compose service names provide internal discovery: AegisRoute connects to
  `postgres`, Prometheus scrapes `aegisroute:8000`, and Grafana queries
  `prometheus:9090`.
- Prometheus configuration and Grafana provisioning are version-controlled.
- Grafana's Prometheus datasource and AegisRoute dashboard are provisioned from
  checked-in files and are not configured manually through the UI.
- PostgreSQL and Prometheus use named persistent local volumes.
- Grafana V1 has no persistent data volume; checked-in provisioning is the
  source of truth rather than mutable UI state.
- Alembic runs in a dedicated, one-shot `migrate` service after PostgreSQL is
  healthy. AegisRoute starts only after that service completes successfully.
- The stack is for local development and demonstrations. It is not a claim of
  production hardening.
- Grafana alerts, Alertmanager, TLS, reverse proxies, Kubernetes, and remote
  metrics storage are deferred.

## Consequences

Contributors can start the complete local stack with one Compose command and
receive the same datasource and dashboard configuration on every start.
Database migration ownership is explicit, and persistent PostgreSQL and
Prometheus data survive normal container recreation. Grafana UI edits do not
survive because V1 intentionally omits a Grafana volume; durable dashboard
changes must be reviewed in the checked-in JSON.

The stack still requires local placeholder credentials to be replaced, Docker
to be installed, and published ports to be available. Production concerns such
as secret managers, redundant services, TLS, retention policy, and access
control remain outside its scope.

## Alternatives considered

- Run each service manually. Rejected because startup order, networking, and
  provisioning would vary between developer machines.
- Run migrations during web application startup. Rejected because migration
  ownership should remain explicit and independently observable.
- Persist Grafana state. Deferred because checked-in provisioning covers V1
  and avoiding mutable UI state keeps local setup reproducible.
- Use host networking or `host.docker.internal`. Rejected because Compose DNS
  provides portable service discovery within the full-stack network.
- Add alerting or a production orchestrator now. Deferred until alert rules and
  production deployment requirements are defined.

## Related components

- `Dockerfile`
- `compose.yml`
- `infra/prometheus/prometheus.yml`
- `infra/grafana/provisioning/`
- `infra/grafana/dashboards/aegisroute-overview.json`
- `GET /health`
- `GET /metrics`
- Alembic migrations
- `docs/local-observability.md`
