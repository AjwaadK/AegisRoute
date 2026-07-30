"""Infrastructure-independent routing analytics contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CountByName:
    name: str
    request_count: int


@dataclass(frozen=True, slots=True)
class ProviderAggregate:
    provider_name: str
    request_count: int
    successful_requests: int
    failed_requests: int
    average_latency_ms: float | None


@dataclass(frozen=True, slots=True)
class RouteAggregate:
    requested_model: str
    selected_model: str
    provider_name: str
    routing_reason: str
    request_count: int


@dataclass(frozen=True, slots=True)
class RoutingAnalyticsData:
    total_requests: int
    successful_requests: int
    failed_requests: int
    average_latency_ms: float | None
    requests_by_provider: tuple[CountByName, ...]
    requests_by_selected_model: tuple[CountByName, ...]
    routing_distribution: tuple[RouteAggregate, ...]
    provider_metrics: tuple[ProviderAggregate, ...]
    failures_by_error_type: tuple[CountByName, ...]
    failures_before_routing: int
    failures_after_routing: int


class RoutingAnalyticsRepository(Protocol):
    async def get_routing_analytics(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> RoutingAnalyticsData:
        """Return read-only aggregate data for one consistent time window."""
