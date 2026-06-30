from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_generate_success() -> None:
    payload = {
        "model": "mock-model-v1",
        "messages": [{"role": "user", "content": "Hello router"}],
        "max_tokens": 64,
        "temperature": 0.5,
    }
    response = client.post("/generate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert "provider" not in body
    assert body["model"] == payload["model"]
    assert body["output"].startswith("mock_response:")
    assert isinstance(body["request_id"], str)
    assert isinstance(body["latency_ms"], int)
    assert body["input_tokens"] >= 1
    assert body["output_tokens"] >= 1


def test_generate_invalid_model() -> None:
    payload = {
        "model": "unknown-model",
        "messages": [{"role": "user", "content": "Hello router"}],
        "max_tokens": 64,
        "temperature": 0.5,
    }
    response = client.post("/generate", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "error": "invalid_model",
        "requested_model": "unknown-model",
        "valid_models": ["mock-model-v1"],
    }


def test_generate_invalid_schema_messages_required() -> None:
    payload = {
        "model": "mock-model-v1",
        "messages": [],
        "max_tokens": 64,
        "temperature": 0.5,
    }
    response = client.post("/generate", json=payload)
    assert response.status_code == 422


def test_generate_invalid_schema_content_not_empty() -> None:
    payload = {
        "model": "mock-model-v1",
        "messages": [{"role": "user", "content": "   "}],
        "max_tokens": 64,
        "temperature": 0.5,
    }
    response = client.post("/generate", json=payload)
    assert response.status_code == 422


def test_generate_invalid_schema_max_tokens_bounds() -> None:
    payload = {
        "model": "mock-model-v1",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 0,
        "temperature": 0.5,
    }
    response = client.post("/generate", json=payload)
    assert response.status_code == 422


def test_generate_invalid_schema_temperature_bounds() -> None:
    payload = {
        "model": "mock-model-v1",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 10,
        "temperature": 2.1,
    }
    response = client.post("/generate", json=payload)
    assert response.status_code == 422


def test_generate_whitespace_model_returns_422() -> None:
    payload = {
        "model": "   ",
        "messages": [{"role": "user", "content": "Hello router"}],
        "max_tokens": 64,
        "temperature": 0.5,
    }
    response = client.post("/generate", json=payload)
    assert response.status_code == 422


def test_generate_provider_error_returns_502(monkeypatch) -> None:
    from app.errors import ProviderError

    async def raise_provider_error(request, request_id):
        raise ProviderError("mock failure")

    monkeypatch.setattr(
        "app.api.routes.gateway_service.generate",
        raise_provider_error,
    )
    payload = {
        "model": "mock-model-v1",
        "messages": [{"role": "user", "content": "Hello router"}],
        "max_tokens": 64,
        "temperature": 0.5,
    }
    response = client.post("/generate", json=payload)

    assert response.status_code == 502
    assert response.json()["detail"] == {"error": "provider_error"}


def test_gateway_logs_generation_failed_on_provider_error(caplog, monkeypatch) -> None:
    from app.errors import ProviderError
    from app.providers.base import ProviderAdapter
    from app.schemas.generation import GenerateRequest, ProviderResult
    from app.services.gateway import GatewayService

    class FailingProviderAdapter(ProviderAdapter):
        provider_name = "failing_mock"

        async def generate(self, request: GenerateRequest, request_id: str) -> ProviderResult:
            raise ProviderError("mock failure")

    monkeypatch.setattr(
        "app.services.gateway.MockProviderAdapter",
        FailingProviderAdapter,
    )
    request = GenerateRequest(
        model="mock-model-v1",
        messages=[{"role": "user", "content": "Hello router"}],
        max_tokens=64,
        temperature=0.5,
    )

    with caplog.at_level("INFO", logger="ai_compute_router"):
        try:
            import asyncio

            asyncio.run(GatewayService().generate(request, "test-request-id"))
        except ProviderError:
            pass

    assert "generation_failed" in caplog.text
    assert "failing_mock" in caplog.text
    assert "test-request-id" in caplog.text
