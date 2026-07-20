"""Exceptions raised by request log repositories."""


class RequestLogNotFoundError(Exception):
    """Raised when a request log operation targets an unknown request ID."""
