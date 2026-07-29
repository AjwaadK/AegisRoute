# ADR 0004: Persist Routing Decision Metadata

## Status

Accepted

## Context

A completed or failed generation request must retain enough evidence to explain
what the client requested and what routing selected. Persisting only a mutable
model and provider loses that distinction, especially when a provider call
fails after routing.

## Decision

Record the client-requested model when the request lifecycle starts. Immediately
after routing succeeds, persist the selected model, provider, and routing reason
before resolving or invoking the provider. Routing fields remain nullable so a
failure before a decision can still be recorded.

Repository lifecycle operations own the corresponding started, routed,
completed, and failed timeline events. Completion and failure updates preserve
the previously stored routing metadata. Persistence failures remain fail-open
because generation availability is the gateway's primary responsibility.

## Consequences

Operators can distinguish pre-routing failures from failures after a concrete
route was chosen. Provider failures retain the complete routing decision.
Requests may have null routing fields when routing never succeeded, and
persistence outages can still leave incomplete evidence by design.

## Alternatives considered

- Persist routing data only on completion. Rejected because provider failures
  would lose the decision that preceded invocation.
- Require routing fields on every row. Rejected because no decision exists for
  model-resolution failures.
- Fail generation when routing persistence fails. Rejected because it would
  make observability storage a generation availability dependency.
- Add a separate routing record outside the existing lifecycle model. Rejected
  because the request row and generation events already represent current state
  and transitions.

## Related components

- `GatewayService`
- `RequestLogRepository`
- `GenerationRequest`
- `GenerationEvent`
- Alembic routing-metadata migration
- structured lifecycle logging
