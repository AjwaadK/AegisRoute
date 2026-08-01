"""Prometheus-backed application metrics with an explicit registry."""

from prometheus_client import CollectorRegistry, Counter, Histogram

LATENCY_BUCKETS = (0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120)


class PrometheusApplicationMetrics:
    """Process-scoped collectors for the generation lifecycle."""

    def __init__(self, registry: CollectorRegistry) -> None:
        self.registry = registry
        self._requests = Counter(
            "aegisroute_generation_requests_total",
            "Generation requests entering GatewayService.",
            registry=registry,
        )
        self._completed = Counter(
            "aegisroute_generation_completed_total",
            "Successfully completed generation requests.",
            registry=registry,
        )
        self._failed = Counter(
            "aegisroute_generation_failed_total",
            "Failed generation requests.",
            ("error_type", "failure_stage"),
            registry=registry,
        )
        self._latency = Histogram(
            "aegisroute_generation_latency_seconds",
            "End-to-end latency for generation requests that reached a provider.",
            ("provider", "selected_model"),
            buckets=LATENCY_BUCKETS,
            registry=registry,
        )
        self._provider_calls = Counter(
            "aegisroute_provider_calls_total",
            "Provider invocation attempts.",
            ("provider", "selected_model"),
            registry=registry,
        )
        self._provider_failures = Counter(
            "aegisroute_provider_failures_total",
            "Upstream provider invocation failures.",
            ("provider", "selected_model", "error_type"),
            registry=registry,
        )
        self._routing_failures = Counter(
            "aegisroute_routing_failures_total",
            "Routing failures before provider invocation.",
            ("error_type",),
            registry=registry,
        )

    def record_request_started(self) -> None:
        self._requests.inc()

    def record_routing_failure(self, error_type: str) -> None:
        self._routing_failures.labels(error_type=error_type).inc()

    def record_provider_call(self, provider: str, selected_model: str) -> None:
        self._provider_calls.labels(
            provider=provider,
            selected_model=selected_model,
        ).inc()

    def record_provider_failure(
        self,
        provider: str,
        selected_model: str,
        error_type: str,
        latency_seconds: float,
    ) -> None:
        labels = {"provider": provider, "selected_model": selected_model}
        self._provider_failures.labels(error_type=error_type, **labels).inc()
        self._latency.labels(**labels).observe(latency_seconds)

    def record_request_completed(
        self,
        provider: str,
        selected_model: str,
        latency_seconds: float,
    ) -> None:
        self._completed.inc()
        self._latency.labels(
            provider=provider,
            selected_model=selected_model,
        ).observe(latency_seconds)

    def record_request_failed(self, error_type: str, failure_stage: str) -> None:
        self._failed.labels(
            error_type=error_type,
            failure_stage=failure_stage,
        ).inc()
