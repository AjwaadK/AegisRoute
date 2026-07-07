# Aegis Ecosystem

## Overview

Aegis is a family of infrastructure products for building, deploying, operating, and scaling AI applications. AegisRoute is the foundation and current flagship product. Other products should only be built when they strengthen the gateway, improve developer workflow, or solve a clear operational problem.

```text
AI Application
  ↓
AegisSDK / AegisCLI
  ↓
AegisRoute
  ↓
Providers and runtimes
  ├─ OpenAI
  ├─ Anthropic
  ├─ Gemini
  ├─ Ollama
  └─ vLLM

AegisConsole / AegisBench / AegisEval
  ↕
AegisRoute logs, metrics, usage, costs, and evaluations

Aegis Cloud eventually hosts managed AegisRoute and platform services.
```

## AegisRoute

- **Purpose:** Provide the AI infrastructure gateway between applications and model providers.
- **Target user:** Product engineers, platform engineers, AI engineers, and operators.
- **Relationship to AegisRoute:** This is the core product.
- **When to build:** Now. It is the foundation for the rest of the ecosystem.

AegisRoute currently starts as a minimal gateway skeleton. It will eventually provide unified inference, provider abstraction, routing, retries, fallbacks, logging, token and cost tracking, caching, workers, benchmarking hooks, observability, local serving, authentication, rate limiting, SDK support, and deployment support.

## AegisSDK

- **Purpose:** Provide official clients for Python, TypeScript, and eventually Go.
- **Target user:** Application developers integrating AegisRoute into products.
- **Relationship to AegisRoute:** Wraps the AegisRoute API with native language clients.
- **When to build:** After the gateway API stabilizes enough that client contracts will not churn constantly.

Developers should be able to call native clients instead of manually writing HTTP requests.

## AegisCLI

- **Purpose:** Provide command-line workflow and operational control.
- **Target user:** Developers and operators working from a terminal.
- **Relationship to AegisRoute:** Calls AegisRoute and related platform APIs.
- **When to build:** After basic API, logs, models, and benchmark endpoints exist.

Possible commands:

- `aegis login`
- `aegis models`
- `aegis generate`
- `aegis logs`
- `aegis benchmark`
- `aegis deploy`

## AegisBench

- **Purpose:** Compare models, providers, routing policies, latency, throughput, cost/request, and cache effectiveness.
- **Target user:** AI engineers, platform teams, and technical founders choosing provider strategies.
- **Relationship to AegisRoute:** Uses gateway traffic patterns, provider adapters, and metrics as benchmark inputs.
- **When to build:** After multiple provider adapters, metrics, and repeatable request workloads exist.

AegisBench should help teams make evidence-based provider and model decisions.

## AegisEval

- **Purpose:** Measure answer quality through LLM-as-judge, RAGAS-style evaluation, regression tests, and custom metrics.
- **Target user:** AI product teams and ML engineers responsible for output quality.
- **Relationship to AegisRoute:** Evaluates responses generated through AegisRoute and can compare providers or routing policies.
- **When to build:** After request logging and benchmark workflows exist.

AegisEval should measure quality, not just latency and cost.

## AegisConsole

- **Purpose:** Provide a web dashboard for requests, latency, provider usage, token costs, cache hit rate, logs, metrics, API keys, and usage.
- **Target user:** Operators, engineering managers, founders, and platform teams.
- **Relationship to AegisRoute:** Visualizes gateway data and controls operational settings.
- **When to build:** After persistence, usage tracking, and core metrics exist.

The console should not invent visibility. It should expose data the gateway already captures.

## AegisRAG

- **Purpose:** Provide a reference production RAG application built on AegisRoute.
- **Target user:** Engineers learning how to build retrieval applications on Aegis infrastructure.
- **Relationship to AegisRoute:** Demonstrates embeddings, vector databases, retrieval, caching, and observability through the gateway.
- **When to build:** After AegisRoute supports enough observability and provider behavior to make the reference app realistic.

AegisRAG should prove AegisRoute supports real AI applications.

## AegisAgent

- **Purpose:** Provide a reference agent system built on AegisRoute, likely using LangGraph.
- **Target user:** Engineers building agentic applications with tool calling, memory, retries, and observability.
- **Relationship to AegisRoute:** Exercises gateway behavior under agent workloads.
- **When to build:** After streaming, retries, observability, and tool-call-friendly request handling are better understood.

AegisAgent should prove AegisRoute supports agentic workloads.

## Aegis Cloud

- **Purpose:** Provide a future hosted SaaS platform with managed AegisRoute, dashboards, team management, billing, API keys, managed deployments, observability, benchmarking, and evaluations.
- **Target user:** Teams that want Aegis capabilities without operating the infrastructure themselves.
- **Relationship to AegisRoute:** Hosts and manages AegisRoute and related platform services.
- **When to build:** Later, after self-hosted AegisRoute proves value and operational requirements are clear.

Aegis Cloud is a future hosted platform, not another repo right now.
