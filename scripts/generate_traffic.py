#!/usr/bin/env python3
"""Generate representative development traffic through AegisRoute's HTTP API."""

from __future__ import annotations

import argparse
import asyncio
import math
import random
import time
from dataclasses import dataclass, field
from typing import Sequence

import httpx

INVALID_MODEL = "unsupported-load-test-model"
DIAGNOSTIC_BODY_LIMIT = 200


@dataclass(frozen=True, slots=True)
class TrafficConfig:
    base_url: str = "http://localhost:8000"
    duration: float = 60
    concurrency: int = 5
    failure_rate: float = 0.0
    timeout: float = 10
    model: str = "mock-model-v1"


@dataclass(slots=True)
class TrafficStats:
    total_requests: int = 0
    successful_responses: int = 0
    expected_failures: int = 0
    unexpected_http_failures: int = 0
    transport_errors: int = 0
    latencies: list[float] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class LatencySummary:
    minimum: float
    average: float
    p95: float
    maximum: float


def calculate_latency_summary(latencies: Sequence[float]) -> LatencySummary:
    """Return latency aggregates in seconds, using nearest-rank p95."""
    if not latencies:
        return LatencySummary(0.0, 0.0, 0.0, 0.0)

    ordered = sorted(latencies)
    p95_index = math.ceil(0.95 * len(ordered)) - 1
    return LatencySummary(
        minimum=ordered[0],
        average=sum(ordered) / len(ordered),
        p95=ordered[p95_index],
        maximum=ordered[-1],
    )


def parse_args(argv: Sequence[str] | None = None) -> TrafficConfig:
    parser = argparse.ArgumentParser(
        description="Generate representative traffic against a running AegisRoute instance."
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--failure-rate", type=float, default=0.0)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--model", default="mock-model-v1")
    arguments = parser.parse_args(argv)

    if arguments.duration <= 0:
        parser.error("--duration must be greater than zero")
    if arguments.concurrency <= 0:
        parser.error("--concurrency must be greater than zero")
    if arguments.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    if not 0.0 <= arguments.failure_rate <= 1.0:
        parser.error("--failure-rate must be between 0.0 and 1.0")
    if not arguments.model.strip():
        parser.error("--model must not be empty")

    return TrafficConfig(**vars(arguments))


async def send_request(
    client: httpx.AsyncClient,
    config: TrafficConfig,
    stats: TrafficStats,
    *,
    intended_failure: bool,
) -> None:
    model = INVALID_MODEL if intended_failure else config.model
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Generate a brief sample response."}],
        "max_tokens": 64,
        "temperature": 0.5,
    }
    stats.total_requests += 1
    started = time.perf_counter()
    try:
        response = await client.post("/generate", json=payload)
    except httpx.TransportError:
        stats.transport_errors += 1
        return

    stats.latencies.append(time.perf_counter() - started)
    if 200 <= response.status_code < 300:
        stats.successful_responses += 1
    elif intended_failure and response.status_code == 422:
        stats.expected_failures += 1
    else:
        stats.unexpected_http_failures += 1
        body = response.text[:DIAGNOSTIC_BODY_LIMIT]
        if len(response.text) > DIAGNOSTIC_BODY_LIMIT:
            body += "..."
        print(
            "Unexpected response: "
            f"status={response.status_code} intended_failure={intended_failure} body={body!r}"
        )


async def run_workers(
    client: httpx.AsyncClient,
    config: TrafficConfig,
    stats: TrafficStats,
) -> float:
    """Run exactly ``concurrency`` workers and return elapsed wall-clock seconds."""
    started = time.monotonic()
    deadline = started + config.duration

    async def worker() -> None:
        while time.monotonic() < deadline:
            await send_request(
                client,
                config,
                stats,
                # This controls synthetic traffic distribution, not a security decision.
                intended_failure=random.random() < config.failure_rate,  # nosec B311
            )

    await asyncio.gather(*(worker() for _ in range(config.concurrency)))
    return time.monotonic() - started


def print_start(config: TrafficConfig) -> None:
    target = f"{config.base_url.rstrip('/')}/generate"
    print(
        f"Generating traffic: target={target} duration={config.duration:g}s "
        f"concurrency={config.concurrency} model={config.model} "
        f"failure_rate={config.failure_rate:.1%}"
    )


def print_summary(stats: TrafficStats, elapsed: float) -> None:
    latency = calculate_latency_summary(stats.latencies)
    requests_per_second = stats.total_requests / elapsed if elapsed > 0 else 0.0
    print("\nTraffic summary")
    print(f"  Total requests:             {stats.total_requests}")
    print(f"  Successful HTTP responses: {stats.successful_responses}")
    print(f"  Expected injected failures:{stats.expected_failures:>6}")
    print(f"  Unexpected HTTP failures:  {stats.unexpected_http_failures}")
    print(f"  Transport errors:          {stats.transport_errors}")
    print(f"  Elapsed time:              {elapsed:.2f}s")
    print(f"  Requests per second:       {requests_per_second:.2f}")
    print(
        f"  Latency min / avg / p95 / max: "
        f"{latency.minimum * 1000:.2f} / {latency.average * 1000:.2f} / "
        f"{latency.p95 * 1000:.2f} / {latency.maximum * 1000:.2f} ms"
    )


async def async_main(config: TrafficConfig) -> None:
    print_start(config)
    stats = TrafficStats()
    async with httpx.AsyncClient(
        base_url=config.base_url.rstrip("/"), timeout=config.timeout
    ) as client:
        elapsed = await run_workers(client, config, stats)
    print_summary(stats, elapsed)


def main(argv: Sequence[str] | None = None) -> int:
    config = parse_args(argv)
    try:
        asyncio.run(async_main(config))
    except KeyboardInterrupt:
        print("\nTraffic generation stopped by user.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
