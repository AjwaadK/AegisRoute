"""Explicit HTTP and service output models for routing analytics."""

from typing import Literal

from pydantic import BaseModel


class NamedRequestCount(BaseModel):
    name: str
    request_count: int


class ProviderMetric(BaseModel):
    provider_name: str
    request_count: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    average_latency_ms: float | None


class RoutingDistributionMetric(BaseModel):
    requested_model: str
    selected_model: str
    provider_name: str
    routing_reason: str
    request_count: int


class FailureStageMetric(BaseModel):
    stage: Literal["before_routing", "after_routing"]
    request_count: int


class RoutingSummary(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    average_latency_ms: float | None
    requests_by_provider: list[NamedRequestCount]
    requests_by_selected_model: list[NamedRequestCount]
    routing_distribution: list[RoutingDistributionMetric]
    provider_metrics: list[ProviderMetric]
    failures_by_error_type: list[NamedRequestCount]
    failures_by_stage: list[FailureStageMetric]
