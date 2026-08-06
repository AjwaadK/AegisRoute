class ProviderError(Exception):
    """Base exception for failures reported by a provider integration."""

    def __init__(
        self,
        provider_name: str,
        *,
        provider_code: str | None = None,
        message: str | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.provider_code = provider_code
        self.message = message
        display_message = (
            message
            if message is not None
            else f"Provider '{provider_name}' request failed"
        )
        super().__init__(display_message)


class ProviderTimeoutError(ProviderError):
    """Raised when a provider request exceeds its allowed duration."""


class ProviderRateLimitError(ProviderError):
    """Raised when a provider rejects a request due to rate limiting."""


class ProviderAuthenticationError(ProviderError):
    """Raised when a provider rejects authentication or authorization."""


class ProviderUnavailableError(ProviderError):
    """Raised when a provider is temporarily unavailable."""


class ProviderInvalidRequestError(ProviderError):
    """Raised when a provider rejects the request as invalid."""


class ProviderInternalError(ProviderError):
    """Raised when a provider reports an otherwise unclassified failure."""


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

    def __init__(
        self, requested_model: str, valid_models: list[str] | tuple[str, ...]
    ) -> None:
        self.requested_model = requested_model
        self.valid_models = valid_models
        super().__init__(f"Unsupported model '{requested_model}'")


__all__ = (
    "InvalidModelError",
    "ModelNotFoundError",
    "ProviderAuthenticationError",
    "ProviderError",
    "ProviderInternalError",
    "ProviderInvalidRequestError",
    "ProviderNotFoundError",
    "ProviderRateLimitError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
)
