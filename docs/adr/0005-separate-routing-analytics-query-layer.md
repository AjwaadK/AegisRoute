# ADR 0005: Separate Routing Analytics Query Layer

## Status

Accepted

## Context

Operational summaries require aggregation across persisted generation outcomes
without exposing SQLAlchemy sessions, ORM entities, or raw rows to HTTP code.
The generation write lifecycle and routing policy must remain unchanged.

## Decision

Routing analytics use a separate read-oriented repository and service.
`SQLAlchemyRoutingAnalyticsRepository` owns six bounded SQLAlchemy 2-style
aggregation queries executed in PostgreSQL. The repository returns immutable
analytics result objects; no session or ORM entity escapes it.

Metric semantics, rate calculation, validation, deterministic output
orchestration, and typed response contracts remain in the analytics service and
schemas. The HTTP layer receives a typed summary. Time windows use an inclusive
`start_time` and exclusive `end_time`, consistently applied to every metric.

V1 provides one summary endpoint without dashboards, caching, background
aggregation, or external observability dependencies.

## Consequences

Aggregation happens in PostgreSQL instead of loading request records into
application memory. Six queries are a deliberate bounded tradeoff: one overall
aggregate and five cohesive grouped aggregates keep grouping and null behavior
auditable while avoiding N+1 access. Read traffic scales with aggregate
cardinality rather than raw request count.

The existing `created_at` index supports time filtering. No speculative
migration or index is introduced; production query plans can justify a future
composite index if needed.

## Alternatives considered

- Add analytics methods to the write repository. Rejected because it mixes
  lifecycle mutation with operational reads.
- Load requests and calculate metrics in Python. Rejected because memory and
  transfer costs grow with request volume.
- Use one highly complex query. Rejected because unrelated groupings would be
  harder to validate and maintain.
- Add materialized summaries or caching. Deferred until observed scale requires
  background aggregation.

## Related components

- `RoutingAnalyticsRepository`
- `SQLAlchemyRoutingAnalyticsRepository`
- `RoutingAnalyticsService`
- analytics Pydantic schemas
- `ApplicationContainer`
- `GET /analytics/routing-summary`
