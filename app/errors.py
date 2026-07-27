
class ProviderError(Exception):
    """Raised when a provider fails to generate a response."""


class InvalidModelError(ValueError):
    """Raised when a requested model is not supported by the gateway."""

    def __init__(self, requested_model: str, valid_models: list[str]) -> None:
        self.requested_model = requested_model
        self.valid_models = valid_models
        super().__init__(f"Unsupported model '{requested_model}'")


class ModelNotFoundError(Exception):
    """Raised when a requested model is not registered for routing."""


class ProviderNotFoundError(Exception):
    """Raised when a configured routing provider is not registered."""


__all__ = (
    "InvalidModelError",
    "ModelNotFoundError",
    "ProviderError",
    "ProviderNotFoundError",
)
