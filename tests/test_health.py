import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.composition import ApplicationContainer
from app.main import create_app
from app.services.gateway import GatewayService


@pytest.fixture
def client() -> TestClient:
    container = ApplicationContainer(engine=create_engine("sqlite://"), gateway_service=GatewayService())
    with TestClient(create_app(lambda: container)) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
