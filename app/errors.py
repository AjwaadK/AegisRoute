class ProviderError(Exception):
    """Raised when a provider fails to generate a response."""


class ProviderNotFoundError(LookupError):
    """Raised when a requested provider is not registered."""

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name
        super().__init__(f"Provider '{provider_name}' is not registered")


class ModelNotFoundError(LookupError):
    """Raised when a requested model is not registered."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        super().__init__(f"Model '{model_name}' is not registered")


class InvalidModelError(ValueError):
    """Raised when a requested model is not supported by the gateway."""

    def __init__(self, requested_model: str, valid_models: list[str] | tuple[str, ...]) -> None:
        self.requested_model = requested_model
        self.valid_models = valid_models
        super().__init__(f"Unsupported model '{requested_model}'")


__all__ = (
    "InvalidModelError",
    "ModelNotFoundError",
    "ProviderError",
    "ProviderNotFoundError",
)
