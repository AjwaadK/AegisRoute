# ADR 0012: Streaming commit semantics

## Status

Accepted

## Context

Non-streaming provider responses are atomic from the caller's perspective:
AegisRoute can retry an eligible failure or select a fallback before returning
any generated output. Text streaming exposes partial output while provider
execution is still active. Restarting or switching providers after visible text
would append a different generation to output the caller has already consumed.

The existing architecture assigns one provider attempt to an adapter,
same-provider retries to `ProviderExecutor`, cross-provider fallback to
`RouteExecutor`, and the logical request lifecycle to `GatewayService`.
Streaming must preserve those boundaries, the shared monotonic request deadline,
and provider-neutral accounting and persistence contracts.

## Decision

- Providers expose streaming as the optional `StreamingProvider` protocol,
  separately from `ProviderResult`. Existing non-streaming adapters remain
  compatible without being forced to implement streaming.
- The provider-neutral stream contract contains only `StreamTextDelta` and
  `StreamCompleted`. Completion carries provider/model identity and optional
  observed `TokenUsage`; OpenAI SDK event types remain inside its adapter.
- `OpenAIProviderAdapter` creates one Responses API stream per adapter
  invocation using the injected process-scoped client. SDK retries remain
  disabled in composition. The adapter translates text deltas, completion
  usage, known failures, and closes the upstream stream where supported.
- `ProviderExecutor.stream()` owns same-provider retries. `RouteExecutor.stream()`
  owns fallback across ordered candidates. Both reuse the existing retry and
  fallback classifiers and share the existing monotonic request deadline.
- The first user-visible `StreamTextDelta` yielded toward the caller is the
  commit point. Non-text SDK events and connection establishment do not commit.
  Retry and fallback are allowed only before this point. After commit, the route
  is locked and any provider failure or deadline expiry terminates the stream.
- `POST /generate/stream` exposes AegisRoute-owned Server-Sent Events named
  `delta`, `completed`, and bounded post-commit `error`. It primes execution
  before returning the streaming response, so terminal pre-commit failures can
  still use normal HTTP error mappings. Once SSE output begins, the HTTP status
  cannot change; a bounded error event terminates the stream.
- Client cancellation propagates through gateway and executor generators to the
  active provider stream. Cancellation never triggers retry or fallback.
- `GatewayService` retains one logical request. Successful completion records
  observed usage and any configured cost estimate. Missing usage or pricing
  remains unknown. Streamed chunks and raw generated text are not persisted.
- A post-commit failure uses the existing failed request status with the stable
  `stream_failed_after_commit` error type. V1 does not add a `partial` status or
  change the persistence schema.
- Streaming lifecycle counters and time-to-first-token are bounded Prometheus
  metrics. TTFT measures the successful committed provider attempt from
  immediately before that attempt begins until its first visible text delta.

## Consequences

Streaming remains deterministic and cannot stitch unrelated generations.
Clients may receive partial output followed by a bounded error event. No
transparent mid-stream recovery exists in V1. Future resumability or replay
would require a different transport and persisted state model. Usage and cost
can remain unknown when a failed stream never reports final usage.

## Alternatives considered

- Retry from scratch after partial output. Rejected because it duplicates or
  changes already-visible output.
- Switch providers mid-stream. Rejected because provider continuations are not
  semantically interchangeable and would stitch outputs.
- Buffer the entire generation before returning. Rejected because it removes
  streaming latency benefits and restores atomic non-streaming behavior.
- Proxy raw OpenAI SSE. Rejected because it leaks provider-specific contracts
  and prevents future adapters from sharing a stable public API.
- Use WebSockets. Rejected because V1 is a one-directional event stream and SSE
  provides a smaller HTTP contract.
- Persist every chunk. Rejected because chunks and raw generated text are not
  required lifecycle facts and would expand storage and privacy exposure.

## Related components

- `StreamingProvider`, `StreamTextDelta`, and `StreamCompleted`
- `OpenAIProviderAdapter` and `MockProviderAdapter`
- `ProviderExecutor.stream()` and `RouteExecutor.stream()`
- `GatewayService.stream()` and `POST /generate/stream`
- `ApplicationMetrics`, request persistence, and cost accounting
- ADR 0008, provider retry execution boundary
- ADR 0010, route executor fallback boundary
- ADR 0011, token and cost accounting
