# AegisRoute Roadmap

This roadmap is staged to keep the gateway understandable while growing toward production AI infrastructure. Each stage should produce usable value and teach specific engineering concepts.

## Stage 0: Gateway Foundation

- **Purpose:** Establish the minimal gateway architecture.
- **User/product value:** Developers can send a request to one gateway API and receive a normalized response.
- **Engineering concepts learned:** FastAPI routing, request validation, provider adapter boundaries, domain errors, structured logging, and tests.
- **Deliverable:** FastAPI gateway, request validation, provider adapter, mock provider, domain errors, structured logging, and tests.
- **Deferred:** Real providers, persistence, caching, auth, routing policies, queues, Docker, and dashboards.

## Stage 1: Persistence

- **Purpose:** Persist request and response metadata for usage analysis and debugging.
- **User/product value:** Operators can inspect historical usage and understand request behavior over time.
- **Engineering concepts learned:** PostgreSQL, SQLAlchemy, Alembic migrations, data modeling, and usage queries.
- **Deliverable:** PostgreSQL-backed request/response metadata logging with queryable usage records.
- **Deferred:** Full billing, tenant analytics, complex retention policies, and dashboards.

## Stage 2: Provider Routing

- **Purpose:** Support real providers and route requests between them.
- **User/product value:** Applications can use OpenAI, Gemini, Anthropic, or other providers behind one gateway contract.
- **Engineering concepts learned:** Provider adapters, timeouts, retries, fallbacks, error mapping, and routing policy design.
- **Deliverable:** OpenAI/Gemini/Anthropic adapters, basic routing policies, timeouts, retries, and fallbacks.
- **Deferred:** Cost optimization engines, advanced policy languages, and automatic provider selection.

## Stage 3: Cost and Caching

- **Purpose:** Track usage cost and avoid repeated work where safe.
- **User/product value:** Teams can understand spend and reduce latency/cost for repeated requests.
- **Engineering concepts learned:** Token tracking, cost estimation, Redis caching, cache keys, cache invalidation, and cache hit metrics.
- **Deliverable:** Token tracking, cost estimation, Redis caching, cache hit metrics, and usage analytics.
- **Deferred:** Billing systems, budget enforcement, semantic caching, and tenant-level financial controls.

## Stage 4: Async Workers

- **Purpose:** Support queued and long-running inference workflows.
- **User/product value:** Applications can submit work that does not need to complete during the HTTP request lifecycle.
- **Engineering concepts learned:** Celery or RQ, background jobs, job statuses, retries, idempotency, and dead job handling.
- **Deliverable:** Queued requests, job statuses, retry handling, and dead job handling.
- **Deferred:** Complex workflow orchestration, distributed scheduling, and agent task graphs.

## Stage 5: Benchmarking

- **Purpose:** Compare provider and model behavior with repeatable workloads.
- **User/product value:** Teams can choose provider/model strategies based on latency, throughput, error rate, and cost/request.
- **Engineering concepts learned:** Benchmark design, measurement, load generation, provider comparison, and result interpretation.
- **Deliverable:** Benchmarking for latency, throughput, error rate, cost/request, and provider comparison.
- **Deferred:** Quality evaluation, LLM-as-judge, and automated routing optimization.

## Stage 6: Observability

- **Purpose:** Make production behavior visible and debuggable.
- **User/product value:** Operators can detect incidents, investigate failures, and understand system health.
- **Engineering concepts learned:** Prometheus, Grafana, structured logs, metrics design, tracing concepts, and incident debugging.
- **Deliverable:** Prometheus metrics, Grafana dashboards, structured logs, and incident debugging workflows. OpenTelemetry can come later.
- **Deferred:** Full distributed tracing, advanced alerting, and hosted console experiences.

## Stage 7: Local Serving

- **Purpose:** Support local and self-hosted model runtimes.
- **User/product value:** Teams can route between cloud providers and local models for privacy, cost, latency, or control.
- **Engineering concepts learned:** Ollama, vLLM, local/cloud routing, tokens/sec measurement, streaming, and runtime health checks.
- **Deliverable:** Ollama and vLLM adapters, local/cloud routing, tokens/sec metrics, and streaming support.
- **Deferred:** GPU orchestration, autoscaling model clusters, and advanced capacity planning.

## Stage 8: Deployment

- **Purpose:** Make AegisRoute easier to run reliably in real environments.
- **User/product value:** Teams can deploy the gateway with repeatable operational patterns.
- **Engineering concepts learned:** Docker Compose, Kubernetes, health checks, readiness probes, CI/CD, and release workflows.
- **Deliverable:** Docker Compose, Kubernetes manifests, health checks, readiness probes, and GitHub Actions.
- **Deferred:** Hosted cloud platform, managed upgrades, and multi-region deployment automation.

## Stage 9: Platform Governance

- **Purpose:** Control access, usage, and spend.
- **User/product value:** Teams can safely expose AegisRoute across applications, teams, and environments.
- **Engineering concepts learned:** API keys, authentication, rate limits, quotas, budgets, tenant usage, and policy enforcement.
- **Deliverable:** API keys, auth, rate limits, quotas, budgets, and tenant usage reporting.
- **Deferred:** Full billing, enterprise SSO, audit logs, and complex organization management.

## Stage 10: Ecosystem

- **Purpose:** Expand from gateway to developer and operator ecosystem.
- **User/product value:** Teams get native clients, terminal workflows, examples, evaluations, and reference applications.
- **Engineering concepts learned:** SDK design, CLI UX, documentation, examples, benchmark harnesses, evaluation systems, and reference architecture.
- **Deliverable:** SDK, CLI, docs, examples, AegisRAG, AegisAgent, AegisBench, and AegisEval.
- **Deferred:** Aegis Cloud until self-hosted value and operational needs are proven.
