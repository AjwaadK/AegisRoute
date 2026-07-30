from datetime import UTC, datetime

import pytest

from app.analytics.contracts import CountByName, ProviderAggregate, RouteAggregate, RoutingAnalyticsData
from app.analytics.service import InvalidAnalyticsTimeRangeError, RoutingAnalyticsService


class StubRepository:
    def __init__(self, data: RoutingAnalyticsData) -> None:
        self.data = data
        self.calls: list[tuple[datetime | None, datetime | None]] = []

    async def get_routing_analytics(self, *, start_time=None, end_time=None):
        self.calls.append((start_time, end_time))
        return self.data


def empty_data() -> RoutingAnalyticsData:
    return RoutingAnalyticsData(0, 0, 0, None, (), (), (), (), (), 0, 0)


@pytest.mark.anyio
async def test_empty_summary_has_zero_rate_and_null_latency() -> None:
    summary = await RoutingAnalyticsService(StubRepository(empty_data())).get_routing_summary()
    assert summary.total_requests == 0
    assert summary.success_rate == 0.0
    assert summary.average_latency_ms is None
    assert [item.stage for item in summary.failures_by_stage] == ["before_routing", "after_routing"]


@pytest.mark.anyio
async def test_service_calculates_rates_and_preserves_deterministic_aggregates() -> None:
    data = RoutingAnalyticsData(
        3, 1, 2, 15.0,
        (CountByName("alpha", 2),),
        (CountByName("model-a", 2),),
        (RouteAggregate("public", "model-a", "alpha", "first", 2),),
        (ProviderAggregate("alpha", 2, 1, 1, 20.0),),
        (CountByName("ProviderError", 2),),
        1, 1,
    )
    summary = await RoutingAnalyticsService(StubRepository(data)).get_routing_summary()
    assert summary.success_rate == pytest.approx(1 / 3)
    assert summary.provider_metrics[0].success_rate == 0.5
    assert summary.failures_by_error_type[0].name == "ProviderError"
    assert [item.request_count for item in summary.failures_by_stage] == [1, 1]


@pytest.mark.anyio
async def test_time_window_is_forwarded_with_inclusive_exclusive_contract() -> None:
    repository = StubRepository(empty_data())
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 2, 1, tzinfo=UTC)
    await RoutingAnalyticsService(repository).get_routing_summary(start_time=start, end_time=end)
    assert repository.calls == [(start, end)]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime(2026, 1, 1), None),
        (None, datetime(2026, 1, 2)),
        (datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)),
        (datetime(2026, 1, 3, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)),
    ],
)
async def test_invalid_time_windows_are_rejected(start, end) -> None:
    with pytest.raises(InvalidAnalyticsTimeRangeError):
        await RoutingAnalyticsService(StubRepository(empty_data())).get_routing_summary(
            start_time=start, end_time=end
        )
