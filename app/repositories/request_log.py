from typing import Any, Protocol


class RequestLogRepository(Protocol):
    async def create_started_request(
        self,
        *,
        request_id: str,
        provider: str,
        model: str,
        prompt_hash: str,
        message_count: int,
        input_chars: int,
    ) -> None:
        """Create generation_requests current-state row in started state."""

    async def mark_completed(
        self,
        *,
        request_id: str,
        model: str,
        provider: str,
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Update generation_requests current-state row after provider success."""

    async def mark_failed(
        self,
        *,
        request_id: str,
        error_type: str,
    ) -> None:
        """Update generation_requests current-state row after provider failure."""

    async def add_event(
        self,
        *,
        request_id: str,
        event_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Append a generation_events timeline row."""


class InMemoryRequestLogRepository:
    def __init__(self) -> None:
        self.requests: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []

    async def create_started_request(
        self,
        *,
        request_id: str,
        provider: str,
        model: str,
        prompt_hash: str,
        message_count: int,
        input_chars: int,
    ) -> None:
        self.requests[request_id] = {
            "request_id": request_id,
            "provider": provider,
            "model": model,
            "prompt_hash": prompt_hash,
            "message_count": message_count,
            "input_chars": input_chars,
            "status": "started",
        }

    async def mark_completed(
        self,
        *,
        request_id: str,
        model: str,
        provider: str,
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        self.requests[request_id] = {
            **self.requests.get(request_id, {"request_id": request_id}),
            "model": model,
            "provider": provider,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "status": "completed",
        }

    async def mark_failed(
        self,
        *,
        request_id: str,
        error_type: str,
    ) -> None:
        self.requests[request_id] = {
            **self.requests.get(request_id, {"request_id": request_id}),
            "error_type": error_type,
            "status": "failed",
        }

    async def add_event(
        self,
        *,
        request_id: str,
        event_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            {
                "request_id": request_id,
                "event_type": event_type,
                "metadata": metadata or {},
            }
        )
