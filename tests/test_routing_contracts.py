from dataclasses import FrozenInstanceError

import pytest

from app.routing.contracts import RoutingDecision, RoutingRequest


def make_decision(**overrides: str) -> RoutingDecision:
    values = {
        "requested_model": "public-model",
        "selected_model": "provider-model-v1",
        "provider_name": "mock",
        "reason": "model is available from the selected provider",
    }
    values.update(overrides)
    return RoutingDecision(**values)


def test_valid_routing_request() -> None:
    request = RoutingRequest(requested_model="public-model")

    assert request.requested_model == "public-model"


@pytest.mark.parametrize("requested_model", ["", "   "])
def test_routing_request_rejects_empty_model(requested_model: str) -> None:
    with pytest.raises(ValueError, match="requested_model must not be empty"):
        RoutingRequest(requested_model=requested_model)


def test_valid_routing_decision() -> None:
    decision = make_decision()

    assert decision.requested_model == "public-model"
    assert decision.selected_model == "provider-model-v1"
    assert decision.provider_name == "mock"
    assert decision.reason == "model is available from the selected provider"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("requested_model", ""),
        ("selected_model", ""),
        ("provider_name", ""),
        ("reason", ""),
    ],
)
def test_routing_decision_rejects_empty_fields(field_name: str, value: str) -> None:
    with pytest.raises(ValueError, match=rf"{field_name} must not be empty"):
        make_decision(**{field_name: value})


def test_routing_decision_rejects_uppercase_provider() -> None:
    with pytest.raises(ValueError, match="provider_name must be lowercase"):
        make_decision(provider_name="Mock")


def test_routing_request_is_immutable() -> None:
    request = RoutingRequest(requested_model="public-model")

    with pytest.raises(FrozenInstanceError):
        request.requested_model = "another-model"  # type: ignore[misc]


def test_routing_decision_is_immutable() -> None:
    decision = make_decision()

    with pytest.raises(FrozenInstanceError):
        decision.selected_model = "another-model"  # type: ignore[misc]
