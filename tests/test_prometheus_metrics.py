import inspect

from prometheus_client import CollectorRegistry

from app.observability.prometheus import PrometheusApplicationMetrics


def sample(registry: CollectorRegistry, name: str, labels: dict[str, str] | None = None) -> float:
    value = registry.get_sample_value(name, labels or {})
    assert value is not None
    return value


def test_prometheus_metrics_record_generation_lifecycle() -> None:
    registry = CollectorRegistry()
    metrics = PrometheusApplicationMetrics(registry)

    metrics.record_request_started()
    metrics.record_request_completed("mock", "mock-model-v1", 0.5)
    metrics.record_request_failed("ModelNotFoundError", "routing")
    metrics.record_routing_failure("ModelNotFoundError")
    metrics.record_provider_call("mock", "mock-model-v1")
    metrics.record_provider_failure(
        "mock",
        "mock-model-v1",
        "ProviderError",
        1.25,
    )

    assert sample(registry, "aegisroute_generation_requests_total") == 1
    assert sample(registry, "aegisroute_generation_completed_total") == 1
    assert sample(
        registry,
        "aegisroute_generation_failed_total",
        {"error_type": "ModelNotFoundError", "failure_stage": "routing"},
    ) == 1
    assert sample(
        registry,
        "aegisroute_routing_failures_total",
        {"error_type": "ModelNotFoundError"},
    ) == 1
    assert sample(
        registry,
        "aegisroute_provider_calls_total",
        {"provider": "mock", "selected_model": "mock-model-v1"},
    ) == 1
    assert sample(
        registry,
        "aegisroute_provider_failures_total",
        {
            "provider": "mock",
            "selected_model": "mock-model-v1",
            "error_type": "ProviderError",
        },
    ) == 1
    assert sample(
        registry,
        "aegisroute_generation_latency_seconds_count",
        {"provider": "mock", "selected_model": "mock-model-v1"},
    ) == 2
    assert sample(
        registry,
        "aegisroute_generation_latency_seconds_sum",
        {"provider": "mock", "selected_model": "mock-model-v1"},
    ) == 1.75


def test_isolated_registries_allow_repeated_metrics_construction() -> None:
    first = PrometheusApplicationMetrics(CollectorRegistry())
    second = PrometheusApplicationMetrics(CollectorRegistry())

    first.record_request_started()
    second.record_request_started()

    assert first.registry is not second.registry
    assert sample(first.registry, "aegisroute_generation_requests_total") == 1
    assert sample(second.registry, "aegisroute_generation_requests_total") == 1


def test_metrics_api_accepts_only_bounded_operational_dimensions() -> None:
    methods = (
        "record_request_started",
        "record_routing_failure",
        "record_provider_call",
        "record_provider_failure",
        "record_request_completed",
        "record_request_failed",
    )
    parameters = {
        parameter
        for method in methods
        for parameter in inspect.signature(
            getattr(PrometheusApplicationMetrics, method)
        ).parameters
    }

    assert "request_id" not in parameters
    assert "prompt" not in parameters
    assert "error_message" not in parameters
    assert "routing_reason" not in parameters
