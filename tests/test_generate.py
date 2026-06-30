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
