# Aegis Ecosystem

## Current focus

AegisRoute is the current engineering focus. It is building the reliable gateway
and telemetry foundation needed before other Aegis concepts can become useful.
The names below describe possible future products or workflows, not an
implemented suite and not equal-priority commitments.

## Strategic relationship with Aegis Evaluations

Aegis Evaluations is the most strategically relevant future ecosystem concept
for AegisRoute's learning direction. It could turn generated responses and
application outcomes into explicit quality signals for workload intelligence:

```text
AegisRoute
  ↓ executes requests
Telemetry / outcomes
  ↓
Aegis Evaluations
  ↓ quality signals
Workload intelligence
  ↓
Future routing policy improvement
```

No such integration, evaluation service, workload-intelligence system, or
automatic policy update exists today. A future design must define stable event
semantics, privacy and retention controls, delayed-outcome linkage, evaluation
provenance, and safeguards before evaluation signals influence routing.

## Ecosystem concepts

### AegisRoute — now

The AI inference gateway and routing platform. Its current Phase I foundation
includes deterministic routing, mock-provider execution, PostgreSQL lifecycle
history and analytics, provider timeout/retry behavior, and Prometheus/Grafana
observability. Real providers and adaptive routing are not yet implemented.

### Aegis Evaluations — future enabler

A possible evaluation system for task-specific quality metrics, regression
suites, human or application feedback, and carefully governed model-based
judging. Its primary strategic value would be supplying quality/outcome evidence
to AegisRoute; it should not be built as a disconnected feature catalog.

### SDK and CLI — future developer workflow

Native clients and command-line workflows may wrap stable AegisRoute contracts
once those contracts no longer churn rapidly. Possible workflows include model
discovery, generation, request inspection, and policy operations.

### Console and Cloud — future operations

A console could expose data and controls that AegisRoute already owns; it should
not invent unsupported visibility. Aegis Cloud remains a possible managed
hosting and operations direction after self-hosted requirements are understood.
Neither exists today.

### Retrieval, Memory, and agent applications — future integration surfaces

Aegis Retrieval, Memory, RAG, or agent concepts may eventually provide reference
workloads and demonstrate gateway integration. They are not current AegisRoute
capabilities and should not compete with the gateway and evaluation feedback
path for near-term engineering attention.

### Benchmarking — supporting evidence

Repeatable benchmarks may compare latency, throughput, reliability, and cost.
They complement—but do not replace—application-specific quality evaluation and
production outcome evidence.

## Investment rule

Add an ecosystem component only when it strengthens AegisRoute, supplies a
required feedback signal, improves a demonstrated developer workflow, or solves
a clear operational problem. Platform capability matters more than repository
count.
