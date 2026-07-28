"""Immutable model definitions and registry used by routing policies."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from app.errors import ModelNotFoundError


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    """A model name and its providers in routing preference order."""

    name: str
    providers: tuple[str, ...]

    def __init__(self, name: str, providers: Iterable[str]) -> None:
        provider_names = tuple(providers)
        if not name or not name.strip():
            raise ValueError("Model name cannot be empty")
        if not provider_names:
            raise ValueError("A model must have at least one provider")
        if any(not name or not name.strip() for name in provider_names):
            raise ValueError("Provider names cannot be empty")
        if any(name != name.lower() for name in provider_names):
            raise ValueError("Provider names must be lowercase")
        if len(provider_names) != len(set(provider_names)):
            raise ValueError("Duplicate provider names are not allowed")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "providers", provider_names)


@dataclass(frozen=True, slots=True)
class ModelRegistry:
    """Provide constant-time access to a fixed set of model definitions."""

    _models: Mapping[str, ModelDefinition] = field(init=False, repr=False)

    def __init__(
        self,
        definitions: Mapping[str, ModelDefinition] | Iterable[ModelDefinition],
    ) -> None:
        if isinstance(definitions, Mapping):
            copied = dict(definitions)
        else:
            copied = {definition.name: definition for definition in definitions}
        if not copied:
            raise ValueError("Model registry cannot be empty")
        for model_name, definition in copied.items():
            if model_name != definition.name:
                raise ValueError(
                    f"Model registry key '{model_name}' does not match "
                    f"definition name '{definition.name}'"
                )
        object.__setattr__(self, "_models", MappingProxyType(copied))

    def get(self, model_name: str) -> ModelDefinition:
        try:
            return self._models[model_name]
        except KeyError:
            raise ModelNotFoundError(model_name) from None

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._models))
