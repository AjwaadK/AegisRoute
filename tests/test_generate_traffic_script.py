import asyncio
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.generate_traffic import (
    TrafficConfig,
    TrafficStats,
    calculate_latency_summary,
    parse_args,
    run_workers,
    send_request,
)


@pytest.mark.parametrize(
    "arguments",
    [
        ["--duration", "0"],
        ["--concurrency", "0"],
        ["--failure-rate", "1.1"],
        ["--failure-rate", "-0.1"],
    ],
)
def test_invalid_arguments_are_rejected(arguments: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(arguments)


def run_request(status_code: int, *, intended_failure: bool = False) -> TrafficStats:
    async def scenario() -> TrafficStats:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(status_code, json={"detail": "test"})
        )
        stats = TrafficStats()
        async with httpx.AsyncClient(
            base_url="http://test", transport=transport
        ) as client:
            await send_request(
                client,
                TrafficConfig(),
                stats,
                intended_failure=intended_failure,
            )
        return stats

    return asyncio.run(scenario())


def test_valid_response_is_counted_as_successful() -> None:
    stats = run_request(200)
    assert stats.total_requests == 1
    assert stats.successful_responses == 1


def test_intentional_422_is_counted_as_expected_failure() -> None:
    stats = run_request(422, intended_failure=True)
    assert stats.expected_failures == 1
    assert stats.unexpected_http_failures == 0


def test_unexpected_http_failure_is_counted_separately() -> None:
    stats = run_request(500)
    assert stats.unexpected_http_failures == 1
    assert stats.expected_failures == 0


def test_transport_exception_is_counted_separately() -> None:
    async def scenario() -> TrafficStats:
        def fail(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("unavailable", request=request)

        stats = TrafficStats()
        async with httpx.AsyncClient(
            base_url="http://test", transport=httpx.MockTransport(fail)
        ) as client:
            await send_request(client, TrafficConfig(), stats, intended_failure=False)
        return stats

    stats = asyncio.run(scenario())
    assert stats.transport_errors == 1
    assert stats.latencies == []


def test_latency_summary_handles_no_completed_requests() -> None:
    summary = calculate_latency_summary([])
    assert (summary.minimum, summary.average, summary.p95, summary.maximum) == (
        0.0,
        0.0,
        0.0,
        0.0,
    )


def test_latency_summary_calculates_nearest_rank_p95() -> None:
    summary = calculate_latency_summary([value / 100 for value in range(1, 101)])
    assert summary.minimum == 0.01
    assert summary.average == pytest.approx(0.505)
    assert summary.p95 == 0.95
    assert summary.maximum == 1.0


def test_concurrency_is_bounded_and_one_shared_client_is_used() -> None:
    async def scenario() -> tuple[int, set[int]]:
        active = 0
        maximum_active = 0
        client_ids: set[int] = set()

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return httpx.Response(200, json={})

        stats = TrafficStats()
        async with httpx.AsyncClient(
            base_url="http://test", transport=httpx.MockTransport(handler)
        ) as client:
            client_ids.add(id(client))
            await run_workers(
                client,
                TrafficConfig(duration=0.035, concurrency=3),
                stats,
            )
            client_ids.add(id(client))
        return maximum_active, client_ids

    maximum_active, client_ids = asyncio.run(scenario())
    assert maximum_active == 3
    assert len(client_ids) == 1
