# AegisRoute Vision

## Current foundation

AegisRoute is currently in **Phase I: Reliable Gateway**. It provides a FastAPI
generation boundary, deterministic model and provider routing, a mock provider,
PostgreSQL lifecycle persistence and routing analytics, typed provider errors,
timeouts, bounded retries, and Prometheus/Grafana observability. It does not yet
connect to a real model provider, and it is not production hardened.

This foundation is useful in its own right, but core gateway parity is necessary
infrastructure rather than the intended long-term differentiation.

## North star

> AegisRoute is an adaptive inference control plane that learns how each
> application's AI workloads should execute, continuously optimizing quality,
> cost, latency, reliability, and infrastructure utilization across models,
> providers, and deployments.

Privacy constraints are part of that optimization: an execution target that
violates an application's data-handling requirements is not a valid target.

The internal principle is:

> The gateway is the foundation. The learning loop is the product.

Both statements describe the long-term direction. The adaptive learning loop
does **not** exist in the current implementation.

## Why application-specific intelligence

AI workloads differ by task, context, quality threshold, latency objective,
budget, privacy requirement, and available infrastructure. A globally sensible
model choice may be poor for a particular application's extraction, support,
agent, or retrieval workload. AegisRoute's research direction is to use
application-specific evidence where sufficient evidence exists, while retaining
safe deterministic policies and operator control.

## Long-term optimization loop

The intended loop is conceptual and staged:

```text
Production Requests
  → Route / Plan Execution
  → Generate
  → Collect Telemetry
  → Evaluate Quality / Outcomes
  → Update Workload Intelligence
  → Improve Routing Policy
  → Route Future Requests Better
  → repeat
```

The gateway provides execution evidence. Future evaluation systems may add
quality and outcome signals. Future workload intelligence may then inform a
versioned policy, subject to safety, privacy, confidence, and rollout controls.
Telemetry collection alone is not learning, and evaluation data alone must not
automatically change production behavior.

## Long-term conceptual architecture

The following planes are conceptual boundaries, not currently implemented
services.

### Data Plane

The latency-sensitive path responsible for request routing and execution,
caching, rate limiting, retries and fallbacks, provider invocation, and
telemetry emission. Today's gateway implements only a subset of this boundary.

### Control Plane

The configuration and operational boundary for providers and models,
credentials, tenants, budgets, policies, configuration, and deployments. These
capabilities are planned; they are not a current standalone control plane.

### Intelligence Plane

The future evidence and optimization boundary for workload profiles, evaluation
data, feature extraction, quality/latency/cost predictors, routing models,
experimentation, and policy optimization. No intelligence plane exists today.

Separating these concerns should allow the request path to remain predictable
while slower configuration, analysis, evaluation, and learning workflows evolve
independently.

## Explainability as a requirement

Future intelligent routing decisions should be inspectable rather than opaque.
The eventual decision record should be able to explain:

- the chosen execution target
- predicted quality
- expected latency
- expected cost
- relevant reliability and capacity context
- prediction confidence
- rejected alternatives and the constraints or tradeoffs behind their rejection

These are requirements for future design, not fields or behaviors available in
the current API.

## Product and engineering posture

AegisRoute is an actively developed, self-host-first AI infrastructure project.
It prioritizes correctness, reliability, observable failure semantics, and
stable machine-readable evidence before adaptive behavior. Established gateway
patterns should be adopted when they solve real problems; novelty is not a goal.
Future intelligence should be added only after data quality and operational need
justify its complexity.

See the [Roadmap](roadmap.md), [Principles](principles.md), and
[Ecosystem](ecosystem.md) for the staged plan and related project concepts.
