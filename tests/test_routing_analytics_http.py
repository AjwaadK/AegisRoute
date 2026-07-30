from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.analytics.contracts import RoutingAnalyticsData
from app.analytics.service import RoutingAnalyticsService
from app.composition import ApplicationContainer
from app.main import create_app
from app.services.gateway import GatewayService


class Repository:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.window = None

    async def get_routing_analytics(self, *, start_time=None, end_time=None):
        self.window = (start_time, end_time)
        if self.error:
            raise self.error
        return RoutingAnalyticsData(0, 0, 0, None, (), (), (), (), (), 0, 0)


def client_for(repository: Repository) -> TestClient:
    def container() -> ApplicationContainer:
        return ApplicationContainer(
            engine=create_engine("sqlite://"),
            gateway_service=GatewayService(),
            routing_analytics_service=RoutingAnalyticsService(repository),
        )
    return TestClient(create_app(container))


def test_endpoint_returns_typed_empty_summary_and_forwards_filters() -> None:
    repository = Repository()
    with client_for(repository) as client:
        response = client.get(
            "/analytics/routing-summary",
            params={
                "start_time": "2026-01-01T00:00:00Z",
                "end_time": "2026-02-01T00:00:00Z",
            },
        )
    assert response.status_code == 200
    assert response.json()["total_requests"] == 0
    assert response.json()["average_latency_ms"] is None
    assert repository.window is not None
    assert all(isinstance(value, datetime) for value in repository.window)


def test_invalid_range_returns_422() -> None:
    with client_for(Repository()) as client:
        response = client.get(
            "/analytics/routing-summary",
            params={
                "start_time": "2026-02-01T00:00:00Z",
                "end_time": "2026-01-01T00:00:00Z",
            },
        )
    assert response.status_code == 422


def test_invalid_or_naive_timestamp_returns_422() -> None:
    with client_for(Repository()) as client:
        malformed = client.get("/analytics/routing-summary", params={"start_time": "not-a-date"})
        naive = client.get("/analytics/routing-summary", params={"start_time": "2026-01-01T00:00:00"})
    assert malformed.status_code == 422
    assert naive.status_code == 422


def test_infrastructure_failure_is_generic() -> None:
    with client_for(Repository(RuntimeError("SELECT secret FROM generation_requests"))) as client:
        response = client.get("/analytics/routing-summary")
    assert response.status_code == 500
    assert response.json()["detail"]["error"] == "analytics_unavailable"
    assert "SELECT" not in response.text
    assert "generation_requests" not in response.text
