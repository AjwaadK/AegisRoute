# ADR 0009: OpenAI Provider Adapter

## Status

Accepted

## Context

The mock adapter was previously AegisRoute's only provider implementation. The
first real-provider integration must preserve provider independence and the
existing ownership boundaries: AegisRoute already owns provider timeouts,
bounded retries, routing, lifecycle persistence, and attempt metrics. Hidden
SDK retries would make upstream attempt counts and deadline accounting
inaccurate.

## Decision

- Use the official OpenAI Python SDK, `AsyncOpenAI`, and the Responses API.
- Create one reusable client per configured provider instance in composition;
  do not use a module-level client or create a client for every request.
- Configure the SDK with `max_retries=0`. Each adapter invocation makes exactly
  one Responses API request; retry and future fallback orchestration remain
  above the adapter.
- Set the SDK timeout to the configured AegisRoute provider timeout and retain
  AegisRoute's adapter and overall request deadlines as authoritative bounds.
  The SDK timeout supplies transport-level cancellation rather than a separate,
  longer retry budget.
- Translate known OpenAI SDK exceptions into the existing typed
  `ProviderError` hierarchy at the adapter boundary. Preserve safe stable codes
  and exception chaining, but not prompts, request bodies, headers, credentials,
  or unrestricted upstream messages.
- Keep model selection and aliases in `ModelRegistry`; the adapter forwards the
  selected model identifier without provider-specific routing logic.
- Make `OPENAI_API_KEY` optional. Without it, default composition remains
  mock-only. `OPENAI_MODEL` supplies an optional concrete model identifier;
  composition adds that exact identifier to `ModelRegistry` rather than
  defining an adapter-owned alias or universal default.
- Translate text messages to text-only Responses API input and map stable output
  text plus available input/output token counts to existing domain contracts.
- Use injected fake SDK-compatible clients in the normal test suite. Live API
  access is neither required nor performed.

## Consequences

OpenAI SDK types remain isolated from gateway domain contracts. Provider retry
metrics and request-deadline accounting continue to describe visible upstream
attempts accurately. Additional provider adapters can follow the same
single-attempt contract. OpenAI streaming, tools, structured output, multimodal
input, embeddings, sessions, pricing, and live production validation remain
deferred.

## Alternatives considered

- Raw HTTP calls. Rejected because the official asynchronous SDK supplies the
  supported Responses API transport and exception taxonomy.
- SDK-managed retries. Rejected because they hide attempts from AegisRoute.
- A global OpenAI client. Rejected because lifecycle and test isolation would be
  implicit.
- OpenAI conditionals in `GatewayService`. Rejected because routing and gateway
  orchestration are provider-independent.
- Chat Completions as the primary integration. Rejected in favor of the
  Responses API requested for this first adapter.
- A large generic provider framework. Rejected because AegisRoute already owns
  the required adapter and execution abstractions.

## Related components

- `OpenAIProviderAdapter`
- `OpenAISettings`
- `ProviderExecutor`
- `ProviderRegistry` and `ModelRegistry`
- `GatewayService`
- ADR 0008, provider retry execution boundary
