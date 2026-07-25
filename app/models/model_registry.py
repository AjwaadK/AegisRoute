"""Immutable model definitions and registry."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from app.errors import ModelNotFoundError


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    """A model and the providers capable of serving it."""

    name: str
    providers: tuple[str, ...]

    def __init__(self, name: str, providers: Iterable[str]) -> None:
        provider_names = tuple(providers)
        if not name or not name.strip():
            raise ValueError("Model name cannot be empty")
        if not provider_names:
            raise ValueError("A model must have at least one provider")
        if any(not provider_name or not provider_name.strip() for provider_name in provider_names):
            raise ValueError("Provider names cannot be empty")
        if any(provider_name != provider_name.lower() for provider_name in provider_names):
            raise ValueError("Provider names must be lowercase")
        if len(provider_names) != len(set(provider_names)):
            raise ValueError("Duplicate provider names are not allowed")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "providers", provider_names)


@dataclass(frozen=True, slots=True)
class ModelRegistry:
    """Provide constant-time access to a fixed set of model definitions."""

    _models: Mapping[str, ModelDefinition] = field(init=False, repr=False)

    def __init__(self, models: Mapping[str, ModelDefinition]) -> None:
        copied_models = dict(models)
        if not copied_models:
            raise ValueError("Model registry cannot be empty")
        for model_name, definition in copied_models.items():
            if model_name != definition.name:
                raise ValueError(
                    f"Model registry key '{model_name}' does not match "
                    f"definition name '{definition.name}'"
                )
        object.__setattr__(self, "_models", MappingProxyType(copied_models))

    def get(self, model_name: str) -> ModelDefinition:
        """Return a registered model definition by name."""

        try:
            return self._models[model_name]
        except KeyError:
            raise ModelNotFoundError(model_name) from None

    def names(self) -> tuple[str, ...]:
        """Return registered model names in sorted order."""

        return tuple(sorted(self._models))
