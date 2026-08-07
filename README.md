# AegisRoute

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?logo=prometheus&logoColor=white)](https://prometheus.io/)
[![Grafana](https://img.shields.io/badge/Grafana-F46800?logo=grafana&logoColor=white)](https://grafana.com/)
[![Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![CI](https://github.com/AjwaadK/AegisRoute/actions/workflows/quality.yml/badge.svg)](https://github.com/AjwaadK/AegisRoute/actions/workflows/quality.yml)
![Tests](https://img.shields.io/badge/tests-140%20passing-brightgreen)

AegisRoute is an early-stage AI gateway focused on deterministic model routing,
request lifecycle persistence, routing analytics, and Prometheus observability.
The current provider is a mock implementation intended for development and
testing.

## Current Stage

- ✅ Gateway
- ✅ Persistence
- ✅ Observability
- ✅ Provider Resilience
- 🚧 Redis Caching
- ⬜ Rate Limiting
- ⬜ Async Workers
- ⬜ Kubernetes

## Security status

This repository is a development skeleton, not a production-hardened gateway.
The HTTP API does not yet implement authentication, authorization, rate
limiting, quotas, or TLS termination. Do not expose it directly to the public
internet. The included Compose stack binds its development ports to localhost.

See [SECURITY.md](SECURITY.md) for vulnerability reporting guidance and
[docs/roadmap.md](docs/roadmap.md) for planned security capabilities.

## Local setup

Requirements:

- Python 3.12
- PostgreSQL 18 for integration tests
- Docker Compose for the full local observability stack

Create a virtual environment and install the project:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Copy the environment template and replace every `replace-me` value:

```powershell
Copy-Item .env.example .env
```

Start the local stack:

```powershell
docker compose up --build
```

The development services are available only from the local machine:

- API: <http://localhost:8000>
- Prometheus: <http://localhost:9090>
- Grafana: <http://localhost:3000>

## Tests

Run the unit suite:

```powershell
python -m pytest
```

PostgreSQL integration tests require an explicit `TEST_DATABASE_URL`. See
[docs/local-observability.md](docs/local-observability.md) for details.

## Documentation

- [Vision](docs/vision.md)
- [Principles](docs/principles.md)
- [Roadmap](docs/roadmap.md)
- [Local observability](docs/local-observability.md)
- [Architecture decisions](docs/adr)

## License

AegisRoute is licensed under the Apache License 2.0. See [LICENSE](LICENSE)
for details.
