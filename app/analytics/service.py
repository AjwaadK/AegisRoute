"""Metric definitions and orchestration for routing analytics."""

from __future__ import annotations

from datetime import datetime

from app.analytics.contracts import RoutingAnalyticsRepository
from app.schemas.analytics import (
    FailureStageMetric,
    NamedRequestCount,
    ProviderMetric,
    RoutingDistributionMetric,
    RoutingSummary,
)


class InvalidAnalyticsTimeRangeError(ValueError):
    """Raised when an analytics time window is invalid."""


class RoutingAnalyticsService:
    def __init__(self, repository: RoutingAnalyticsRepository) -> None:
        self._repository = repository

    async def get_routing_summary(
        self,
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> RoutingSummary:
        self._validate_time_window(start_time, end_time)
        data = await self._repository.get_routing_analytics(
            start_time=start_time,
            end_time=end_time,
        )
        return RoutingSummary(
            total_requests=data.total_requests,
            successful_requests=data.successful_requests,
            failed_requests=data.failed_requests,
            success_rate=self._rate(data.successful_requests, data.total_requests),
            average_latency_ms=data.average_latency_ms,
            requests_by_provider=[
                NamedRequestCount(name=item.name, request_count=item.request_count)
                for item in data.requests_by_provider
            ],
            requests_by_selected_model=[
                NamedRequestCount(name=item.name, request_count=item.request_count)
                for item in data.requests_by_selected_model
            ],
            routing_distribution=[
                RoutingDistributionMetric(
                    requested_model=item.requested_model,
                    selected_model=item.selected_model,
                    provider_name=item.provider_name,
                    routing_reason=item.routing_reason,
                    request_count=item.request_count,
                )
                for item in data.routing_distribution
            ],
            provider_metrics=[
                ProviderMetric(
                    provider_name=item.provider_name,
                    request_count=item.request_count,
                    successful_requests=item.successful_requests,
                    failed_requests=item.failed_requests,
                    success_rate=self._rate(item.successful_requests, item.request_count),
                    average_latency_ms=item.average_latency_ms,
                )
                for item in data.provider_metrics
            ],
            failures_by_error_type=[
                NamedRequestCount(name=item.name, request_count=item.request_count)
                for item in data.failures_by_error_type
            ],
            failures_by_stage=[
                FailureStageMetric(stage="before_routing", request_count=data.failures_before_routing),
                FailureStageMetric(stage="after_routing", request_count=data.failures_after_routing),
            ],
        )

    @staticmethod
    def _rate(successes: int, total: int) -> float:
        return successes / total if total else 0.0

    @staticmethod
    def _validate_time_window(
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> None:
        for name, value in (("start_time", start_time), ("end_time", end_time)):
            if value is not None and value.utcoffset() is None:
                raise InvalidAnalyticsTimeRangeError(f"{name} must be timezone-aware")
        if start_time is not None and end_time is not None and start_time >= end_time:
            raise InvalidAnalyticsTimeRangeError("start_time must be earlier than end_time")
