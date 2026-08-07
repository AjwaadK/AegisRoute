# AegisRoute Roadmap

AegisRoute is evolving from a reliable gateway toward an adaptive inference
control plane. The phases below are directional, not rigid release boundaries.
Prerequisites may be pulled forward when real dependency needs justify it, and
features may be reclassified as the market and evidence evolve. A checked item
means the repository currently implements it; an unchecked item is planned or a
research direction.

## Classification framework

Major investments are assessed with five labels:

- **Parity:** Expected gateway capability; necessary, but not differentiating.
- **Enabler:** Creates reliable boundaries, data, or operations needed later.
- **Differentiator:** Advances application-specific routing or execution value.
- **Moat candidate:** Could compound through proprietary workload evidence and
  learning, if real usage and quality validate it.
- **Distraction:** Adds breadth without advancing current reliability or the
  learning loop; defer unless evidence changes.

The label describes strategic intent, not implementation status.

## Phase I: Reliable Gateway — current

**Goal:** Establish a correct, observable execution boundary before adding
adaptive intelligence.

**Parity**

- [x] FastAPI unified generation endpoint and request validation
- [x] Provider adapter contract and mock provider
- [x] Provider and model registries with deterministic routing
- [x] Typed provider failures and configurable timeouts
- [x] Bounded retries above single-attempt provider adapters
- [ ] Real provider adapters
- [ ] Streaming responses
- [ ] Fallback routing and circuit breaking
- [ ] Token accounting and cost estimation
- [ ] Redis response caching and cache metrics
- [ ] API-key authentication, authorization, quotas, and rate limiting
- [ ] Readiness/dependency health checks beyond the current liveness endpoint
- [ ] Asynchronous workers for long-running requests
- [ ] Local inference adapters
- [ ] Kubernetes and production deployment hardening

**Enablers**

- [x] PostgreSQL request/event lifecycle persistence
- [x] Persisted routing decisions and a routing analytics query layer
- [x] Alembic migrations
- [x] Prometheus application metrics and `/metrics`
- [x] Provisioned Grafana dashboard and Docker Compose development stack
- [x] Development traffic generator and automated test suite
- [ ] Stable token, cost, attempt, cache, and SLO telemetry semantics

Provider adapters perform one attempt; retry and future fallback orchestration
belong above them. Phase I remains incomplete until real execution and the
security/operational fundamentals required by actual deployments are proven.

## Phase II: Policy Router

**Goal:** Make deterministic routing expressive, versioned, testable, and
operator controlled.

**Parity / Enablers**

- [ ] Versioned deterministic policy framework and decision records
- [ ] Cost-aware, latency-aware, and reliability-aware routing
- [ ] SLO-aware constraints and budget enforcement
- [ ] Privacy and data-residency constraints
- [ ] Weighted routing and traffic splitting
- [ ] A/B tests with explicit assignment and outcome semantics
- [ ] Policy rollout, rollback, and audit controls

This phase does not require machine learning. It creates safe policy semantics
and experimentation boundaries on which later intelligence can depend.

## Phase III: Workload Intelligence

**Goal:** Build trustworthy, application-specific evidence without allowing it
to autonomously control production routing.

**Differentiators / Enablers**

- [ ] Workload classification and feature extraction
- [ ] Workload clustering where labels are unavailable
- [ ] Empirical model/provider profiles by workload
- [ ] Evaluation and application-outcome ingestion
- [ ] Explicit feedback and delayed-outcome linkage
- [ ] Per-workload quality, latency, cost, and reliability statistics
- [ ] Data quality, retention, privacy, and drift monitoring

Evaluation data—potentially including signals from Aegis Evaluations—must use
stable semantics and preserve the distinction between logical requests and
provider attempts.

## Phase IV: Learned Routing

**Goal:** Recommend and safely validate workload-specific learned policies.

**Differentiators / Moat candidates**

- [ ] Quality, latency, and cost prediction with calibrated confidence
- [ ] Workload-specific learned routing policies
- [ ] Contextual bandits where the decision structure and safety constraints
  make them appropriate
- [ ] Safe exploration/exploitation limits
- [ ] Offline policy evaluation and counterfactual analysis
- [ ] Shadow routing and comparison without user-visible impact
- [ ] Progressive rollout, rollback, guardrails, and operator approval
- [ ] Explainable decisions and rejected-alternative context

A learned policy must outperform an appropriate deterministic baseline under
measured objectives before it controls production traffic.

## Phase V: Adaptive Inference Control Plane

**Goal:** Close a governed feedback loop across application outcomes and
heterogeneous execution infrastructure.

**Differentiators / Moat candidates**

- [ ] Continuous, monitored multi-objective policy optimization
- [ ] Joint local/cloud execution optimization
- [ ] Infrastructure-aware routing and execution planning
- [ ] GPU, queue, capacity, and deployment-health awareness
- [ ] Dynamic model and deployment discovery
- [ ] Automated multi-step execution planning
- [ ] Continuous experimentation with explainability and safety controls

This phase is a long-term research and product direction, not a claim about the
current system.

## Deliberate deferrals

Standalone ecosystem products, broad UI suites, billing platforms, general
agent orchestration, and speculative infrastructure are **Distractions** while
they do not serve a demonstrated AegisRoute dependency. SDKs, evaluation tools,
and management surfaces can become Enablers when gateway contracts and real
workflows justify them. See [Ecosystem](ecosystem.md).
