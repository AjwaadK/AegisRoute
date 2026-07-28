"""In-memory model configuration registry used by routing policies."""

from collections.abc import Iterable
from dataclasses import dataclass

from app.routing.contracts import _validate_non_empty
from app.routing.errors import ModelNotFoundError


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    """A model name and its providers in routing preference order."""

    name: str
    providers: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_non_empty(self.name, "name")
        if not self.providers:
            raise ValueError("providers must not be empty")
        for provider_name in self.providers:
            _validate_non_empty(provider_name, "provider_name")


class ModelRegistry:
    """Resolve immutable model definitions by their public model name."""

    def __init__(self, definitions: Iterable[ModelDefinition]) -> None:
        self._definitions = {definition.name: definition for definition in definitions}

    def get(self, model_name: str) -> ModelDefinition:
        """Return a model definition or raise the routing-domain error."""

        try:
            return self._definitions[model_name]
        except KeyError:
            raise ModelNotFoundError(model_name) from None
