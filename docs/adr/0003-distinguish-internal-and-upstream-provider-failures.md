# ADR 0003: Distinguish Internal and Upstream Provider Failures

## Status

Accepted

## Context

Gateway routing can fail before or during provider invocation. Treating an
unsupported client-selected model, an invalid internal provider reference, and
an upstream provider outage as the same error obscures ownership and makes
incidents harder to classify.

## Decision

- `ModelNotFoundError` maps to HTTP 422 because the client selected a model the
  routing policy does not support.
- `ProviderNotFoundError` maps to HTTP 500 because a routing decision referenced
  a provider absent from the registry. This is an internal routing, registry, or
  composition invariant violation that occurs before an upstream call.
- `ProviderError` maps to HTTP 502 because a registered upstream provider failed
  during invocation.
- Internal provider lookup failures are logged with routing context and the
  registered provider names, while the public HTTP 500 response remains generic.

This distinction primarily improves observability and incident classification.

## Consequences

Clients can distinguish unsupported input from transient upstream failure.
Operators can distinguish internal configuration defects from provider outages.
Internal routing details must remain confined to structured logs.

## Alternatives considered

- Map every failure to HTTP 500. Rejected because it loses client and upstream
  failure semantics.
- Map every provider-related failure to HTTP 502. Rejected because a missing
  registry entry means no upstream call occurred.
- Expose the missing provider in the HTTP response. Rejected because registry
  and routing configuration are internal implementation details.

## Related components

- `GatewayService`
- `RoutingPolicy`
- `ProviderRegistry`
- generation HTTP route error mapping
- structured application logging
