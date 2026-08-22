"""Prometheus-backed application metrics with an explicit registry."""

from decimal import Decimal

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
        self._provider_retries = Counter(
            "aegisroute_provider_retries_total",
            "Provider retries that were scheduled.",
            ("provider", "error_type"),
            registry=registry,
        )
        self._provider_fallbacks = Counter(
            "aegisroute_provider_fallbacks_total",
            "Provider fallback transitions that were scheduled.",
            ("from_provider", "to_provider", "reason"),
            registry=registry,
        )
        self._streams_started = Counter(
            "aegisroute_streams_started_total",
            "Logical streaming generation requests started.",
            registry=registry,
        )
        self._streams_completed = Counter(
            "aegisroute_streams_completed_total",
            "Successfully completed streaming generation requests.",
            ("provider", "model"),
            registry=registry,
        )
        self._streams_failed = Counter(
            "aegisroute_streams_failed_total",
            "Failed streaming generation requests by commit stage.",
            ("provider", "model", "stage"),
            registry=registry,
        )
        self._stream_ttft = Histogram(
            "aegisroute_stream_time_to_first_token_seconds",
            "Provider-attempt latency to the first user-visible text delta.",
            ("provider", "model"),
            buckets=LATENCY_BUCKETS,
            registry=registry,
        )
        self._routing_failures = Counter(
            "aegisroute_routing_failures_total",
            "Routing failures before provider invocation.",
            ("error_type",),
            registry=registry,
        )
        self._tokens = Counter(
            "aegisroute_tokens_total",
            "Provider-observed input and output tokens.",
            ("provider", "model", "token_type"),
            registry=registry,
        )
        self._estimated_cost = Counter(
            "aegisroute_estimated_cost_usd_total",
            "Request-time estimated cost in USD for observed usage.",
            ("provider", "model"),
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

    def record_provider_retry(self, provider: str, error_type: str) -> None:
        self._provider_retries.labels(
            provider=provider,
            error_type=error_type,
        ).inc()

    def record_provider_fallback(
        self, from_provider: str, to_provider: str, reason: str
    ) -> None:
        self._provider_fallbacks.labels(
            from_provider=from_provider,
            to_provider=to_provider,
            reason=reason,
        ).inc()

    def record_stream_started(self) -> None:
        self._streams_started.inc()

    def record_stream_completed(self, provider: str, model: str) -> None:
        self._streams_completed.labels(provider=provider, model=model).inc()

    def record_stream_failed(self, provider: str, model: str, stage: str) -> None:
        self._streams_failed.labels(provider=provider, model=model, stage=stage).inc()

    def record_stream_time_to_first_token(
        self, provider: str, model: str, latency_seconds: float
    ) -> None:
        self._stream_ttft.labels(provider=provider, model=model).observe(
            latency_seconds
        )

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

    def record_tokens(
        self,
        provider: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        for token_type, value in (
            ("input", input_tokens),
            ("output", output_tokens),
        ):
            if value is not None:
                self._tokens.labels(
                    provider=provider,
                    model=model,
                    token_type=token_type,
                ).inc(value)

    def record_estimated_cost(
        self, provider: str, model: str, estimated_cost_usd: Decimal
    ) -> None:
        self._estimated_cost.labels(provider=provider, model=model).inc(
            float(estimated_cost_usd)
        )
