import pytest

from app.errors import ProviderNotFoundError
from app.providers.mock import MockProviderAdapter
from app.providers.provider_registry import ProviderRegistry


def test_successful_lookup() -> None:
    provider = MockProviderAdapter()
    registry = ProviderRegistry({"mock": provider})

    assert registry.get("mock") is provider


def test_missing_provider() -> None:
    registry = ProviderRegistry({"mock": MockProviderAdapter()})

    with pytest.raises(ProviderNotFoundError) as exc_info:
        registry.get("missing")

    assert exc_info.value.provider_name == "missing"


def test_names() -> None:
    registry = ProviderRegistry(
        {"first": MockProviderAdapter(), "second": MockProviderAdapter()}
    )

    assert registry.names() == ("first", "second")


def test_empty_registry() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ProviderRegistry({})


def test_uppercase_provider_names_rejected() -> None:
    with pytest.raises(ValueError, match="lowercase"):
        ProviderRegistry({"OpenAI": MockProviderAdapter()})


def test_registry_copies_input_mapping() -> None:
    providers = {"mock": MockProviderAdapter()}
    registry = ProviderRegistry(providers)

    providers["other"] = MockProviderAdapter()

    assert registry.names() == ("mock",)


def test_registry_attributes_are_immutable() -> None:
    registry = ProviderRegistry({"mock": MockProviderAdapter()})

    with pytest.raises(AttributeError):
        registry._providers = {}  # type: ignore[misc]
