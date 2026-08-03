# Local Observability Stack

The Docker Compose stack is a reproducible local development and demonstration
environment for AegisRoute, PostgreSQL, Prometheus, and Grafana. It is not a
production-hardened deployment.

## Start the stack

Copy the placeholder environment file and replace both placeholder passwords.
Keep `POSTGRES_PASSWORD` and the password embedded in `DATABASE_URL` in sync.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

To run in the background instead:

```powershell
docker compose up --build -d
```

Inspect services and follow logs:

```powershell
docker compose ps
docker compose logs -f aegisroute
docker compose logs -f prometheus
docker compose logs -f grafana
```

Open the local services:

- AegisRoute: <http://localhost:8000>
- Prometheus: <http://localhost:9090>
- Grafana: <http://localhost:3000>

Grafana uses the credentials configured in `.env`. Its Prometheus datasource
and `AegisRoute Overview` dashboard are loaded automatically from the checked-in
provisioning files.

## Verify the stack

1. Confirm <http://localhost:8000/health> returns `{"status":"ok"}`.
2. Confirm <http://localhost:8000/metrics> returns Prometheus exposition text.
3. Open <http://localhost:9090/targets> and confirm the `aegisroute` target is
   `UP`.
4. In Grafana, confirm the Prometheus datasource health check succeeds and the
   `AegisRoute Overview` dashboard appears in the AegisRoute folder.
5. Send representative `POST /generate` requests, then confirm request,
   latency, provider, and applicable failure panels receive data.

## Generate sample traffic

With the Compose stack running, use the development traffic generator from the
repository root. A success-only run using the default mock model is:

```powershell
python scripts/generate_traffic.py --duration 60 --concurrency 5
```

To mix successful requests with intentional unsupported-model responses:

```powershell
python scripts/generate_traffic.py --duration 60 --concurrency 5 --failure-rate 0.2
```

Watch the Grafana `AegisRoute Overview` dashboard for request and success rates,
p95 latency, provider traffic, routing failures, and failures by lifecycle
stage. Allow for the next Prometheus scrape interval before expecting panels to
change.

This script is a development traffic generator for exercising local
observability. It is not a formal load-testing or benchmarking tool.

## Stop or reset

Stop containers while retaining PostgreSQL and Prometheus data:

```powershell
docker compose down
```

Stop containers and delete all local stack data:

```powershell
docker compose down -v
```
