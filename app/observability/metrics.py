"""Application-owned contract for live operational metrics."""

from decimal import Decimal
from typing import Protocol


class ApplicationMetrics(Protocol):
    """Record bounded generation lifecycle metrics without exposing a backend."""

    def record_request_started(self) -> None: ...

    def record_routing_failure(self, error_type: str) -> None: ...

    def record_provider_call(self, provider: str, selected_model: str) -> None: ...

    def record_provider_failure(
        self,
        provider: str,
        selected_model: str,
        error_type: str,
        latency_seconds: float,
    ) -> None: ...

    def record_provider_retry(self, provider: str, error_type: str) -> None: ...

    def record_provider_fallback(
        self, from_provider: str, to_provider: str, reason: str
    ) -> None: ...

    def record_stream_started(self) -> None: ...

    def record_stream_completed(self, provider: str, model: str) -> None: ...

    def record_stream_failed(self, provider: str, model: str, stage: str) -> None: ...

    def record_stream_time_to_first_token(
        self, provider: str, model: str, latency_seconds: float
    ) -> None: ...

    def record_request_completed(
        self,
        provider: str,
        selected_model: str,
        latency_seconds: float,
    ) -> None: ...

    def record_request_failed(self, error_type: str, failure_stage: str) -> None: ...

    def record_tokens(
        self,
        provider: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None: ...

    def record_estimated_cost(
        self, provider: str, model: str, estimated_cost_usd: Decimal
    ) -> None: ...


class NoopApplicationMetrics:
    """Deliberately disabled metrics implementation."""

    def record_request_started(self) -> None:
        pass

    def record_routing_failure(self, error_type: str) -> None:
        pass

    def record_provider_call(self, provider: str, selected_model: str) -> None:
        pass

    def record_provider_failure(
        self,
        provider: str,
        selected_model: str,
        error_type: str,
        latency_seconds: float,
    ) -> None:
        pass

    def record_provider_retry(self, provider: str, error_type: str) -> None:
        pass

    def record_provider_fallback(
        self, from_provider: str, to_provider: str, reason: str
    ) -> None:
        pass

    def record_stream_started(self) -> None:
        pass

    def record_stream_completed(self, provider: str, model: str) -> None:
        pass

    def record_stream_failed(self, provider: str, model: str, stage: str) -> None:
        pass

    def record_stream_time_to_first_token(
        self, provider: str, model: str, latency_seconds: float
    ) -> None:
        pass

    def record_request_completed(
        self,
        provider: str,
        selected_model: str,
        latency_seconds: float,
    ) -> None:
        pass

    def record_request_failed(self, error_type: str, failure_stage: str) -> None:
        pass

    def record_tokens(
        self,
        provider: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        pass

    def record_estimated_cost(
        self, provider: str, model: str, estimated_cost_usd: Decimal
    ) -> None:
        pass
