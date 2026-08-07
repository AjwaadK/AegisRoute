# AegisRoute

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?logo=prometheus&logoColor=white)](https://prometheus.io/)
[![Grafana](https://img.shields.io/badge/Grafana-F46800?logo=grafana&logoColor=white)](https://grafana.com/)
[![Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![CI](https://github.com/AjwaadK/AegisRoute/actions/workflows/quality.yml/badge.svg)](https://github.com/AjwaadK/AegisRoute/actions/workflows/quality.yml)

AegisRoute is an AI inference gateway and routing platform being built toward
an adaptive inference control plane.

Today, it provides the reliable gateway foundation: deterministic routing,
provider abstraction, request lifecycle persistence, routing analytics,
provider timeouts and bounded retries, Prometheus observability, and a
containerized local development stack. It is an actively developed AI
infrastructure project; its only provider adapter is currently a deterministic
mock for development and testing.

Long term, AegisRoute is intended to learn from application-specific workload
telemetry and evaluation outcomes to improve how requests execute across
models, providers, and deployments. That adaptive loop is a direction, not a
capability of the current system.

## Overview

Clients submit generation requests through one FastAPI endpoint. A replaceable
routing policy resolves a model and provider, the gateway executes the request,
and PostgreSQL and Prometheus capture bounded lifecycle evidence for analysis
and operations. The current Phase I implementation deliberately uses only a
mock provider while it establishes reliable boundaries; future phases explore
application-specific, evidence-driven routing without presenting that work as
implemented.

## Architecture

Current request path:

```text
Client
  ↓
FastAPI (`POST /generate`)
  ↓
GatewayService
  ↓
DeterministicRoutingPolicy
  ↓
ModelRegistry / ProviderRegistry
  ↓
ProviderExecutor (deadline + bounded retries)
  ↓
MockProviderAdapter
```

Current side systems:

```text
PostgreSQL ← request/event lifecycle and routing metadata
PostgreSQL → routing analytics query layer → `GET /analytics/routing-summary`
Prometheus ← application metrics ← `GET /metrics`
Grafana    ← provisioned local dashboard
```

The long-term conceptual architecture separates a latency-sensitive data plane,
a configuration-oriented control plane, and an evidence-driven intelligence
plane. These are future boundaries, not deployed services. See
[Vision](docs/vision.md) for details.

## Current Stage

AegisRoute is in **Phase I: Reliable Gateway**.

- ✅ FastAPI gateway and unified generation endpoint
- ✅ PostgreSQL request/event lifecycle persistence and Alembic migrations
- ✅ Provider and model registries
- ✅ Deterministic routing and persisted routing metadata
- ✅ Routing analytics query layer
- ✅ Prometheus metrics, `/metrics`, and a provisioned Grafana dashboard
- ✅ Typed provider failures
- ✅ Configurable provider timeout policy
- ✅ Bounded retries for eligible provider failures
- 🚧 Provider resilience (fallback routing and circuit breaking remain planned)
- ⬜ Real provider adapters and streaming
- ⬜ Token-based cost tracking
- ⬜ API-key authentication, authorization, quotas, and rate limiting
- ⬜ Redis caching and asynchronous workers
- ⬜ Local model serving
- ⬜ Kubernetes and production deployment hardening

## Why AegisRoute

AegisRoute is a systems and AI-infrastructure project built around explicit
contracts for routing, provider execution, failures, persistence, and
observability. Rather than presenting a finished gateway product, the project
is deliberately establishing the operational fundamentals needed to study a
harder question: how should execution adapt to the needs of each application?

**The gateway is the foundation. The learning loop is the long-term product.**
The gateway creates the trustworthy execution and telemetry boundary on which
future routing research can depend.

## Long-term direction

Planned and research-oriented work includes workload profiling,
application-specific routing intelligence, quality/latency/cost prediction,
multi-objective optimization, execution planning, evaluation feedback,
continuous experimentation, and explainable routing decisions. None of these
intelligence capabilities exists today. See the [Vision](docs/vision.md) and
[Roadmap](docs/roadmap.md) for the staged direction.

## Security status

This repository is not production hardened. The HTTP API does not currently
implement authentication, authorization, rate limiting, quotas, or built-in TLS
termination. Do not expose it directly to the public internet. The included
Compose stack binds its development ports to localhost.

See [Security](SECURITY.md) for vulnerability reporting guidance and the
[Roadmap](docs/roadmap.md) for planned security capabilities.

## Local setup

Requirements:

- Python 3.12
- PostgreSQL 18 for PostgreSQL-backed integration tests
- Docker Compose for the complete local stack

Create a virtual environment and install the project (PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Copy the environment template to `.env` and replace its placeholder values:

```powershell
Copy-Item .env.example .env
```

Start the local stack:

```powershell
docker compose up --build
```

The development services bind only to the local machine:

- API: <http://localhost:8000>
- Prometheus: <http://localhost:9090>
- Grafana: <http://localhost:3000>

See [Local observability](docs/local-observability.md) for verification, traffic
generation, and shutdown instructions.

## Tests

Run the full suite with:

```powershell
python -m pytest
```

PostgreSQL-backed integration tests require an explicit `TEST_DATABASE_URL` and
skip when it is absent. See [Local observability](docs/local-observability.md)
for an example.

## Documentation

- [Vision](docs/vision.md)
- [Principles](docs/principles.md)
- [Roadmap](docs/roadmap.md)
- [Ecosystem](docs/ecosystem.md)
- [Local observability](docs/local-observability.md)
- [Architecture decisions](docs/adr)
- [Build log](docs/BUILD_LOG.md)
- [Security](SECURITY.md)
- [License](LICENSE)

## License

AegisRoute is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for
details.
