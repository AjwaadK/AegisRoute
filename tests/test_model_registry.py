from dataclasses import FrozenInstanceError

import pytest

from app.errors import ModelNotFoundError
from app.models.model_registry import ModelDefinition, ModelRegistry


def test_successful_lookup() -> None:
    definition = ModelDefinition("model-a", ("mock",))
    registry = ModelRegistry({"model-a": definition})

    assert registry.get("model-a") is definition


def test_missing_model() -> None:
    registry = ModelRegistry({"model-a": ModelDefinition("model-a", ("mock",))})

    with pytest.raises(ModelNotFoundError) as exc_info:
        registry.get("missing")

    assert exc_info.value.model_name == "missing"


def test_names_are_sorted() -> None:
    registry = ModelRegistry(
        {
            "z-model": ModelDefinition("z-model", ("mock",)),
            "a-model": ModelDefinition("a-model", ("mock",)),
        }
    )

    assert registry.names() == ("a-model", "z-model")


def test_empty_registry_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ModelRegistry({})


def test_empty_model_name_rejected() -> None:
    with pytest.raises(ValueError, match="name cannot be empty"):
        ModelDefinition("", ("mock",))


def test_empty_provider_tuple_rejected() -> None:
    with pytest.raises(ValueError, match="at least one provider"):
        ModelDefinition("model-a", ())


def test_duplicate_providers_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        ModelDefinition("model-a", ("mock", "mock"))


def test_uppercase_provider_names_rejected() -> None:
    with pytest.raises(ValueError, match="lowercase"):
        ModelDefinition("model-a", ("OpenAI",))


def test_empty_provider_name_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        ModelDefinition("model-a", ("",))


def test_key_name_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="does not match"):
        ModelRegistry({"wrong": ModelDefinition("model-a", ("mock",))})


def test_registry_defensively_copies_input_mapping() -> None:
    models = {"model-a": ModelDefinition("model-a", ("mock",))}
    registry = ModelRegistry(models)

    models["model-b"] = ModelDefinition("model-b", ("mock",))

    assert registry.names() == ("model-a",)


def test_model_definition_is_immutable() -> None:
    definition = ModelDefinition("model-a", ("mock",))

    with pytest.raises(FrozenInstanceError):
        definition.name = "changed"  # type: ignore[misc]


def test_registry_attributes_are_immutable() -> None:
    registry = ModelRegistry({"model-a": ModelDefinition("model-a", ("mock",))})

    with pytest.raises(FrozenInstanceError):
        registry._models = {}  # type: ignore[misc]

    with pytest.raises(TypeError):
        registry._models["model-b"] = ModelDefinition(  # type: ignore[index]
            "model-b",
            ("mock",),
        )
