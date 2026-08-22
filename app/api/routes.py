import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import StreamingResponse

from app.analytics.service import (
    InvalidAnalyticsTimeRangeError,
    RoutingAnalyticsService,
)
from app.errors import (
    InvalidModelError,
    ModelNotFoundError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderInvalidRequestError,
    ProviderNotFoundError,
)
from app.schemas.analytics import RoutingSummary
from app.schemas.generation import (
    GenerateRequest,
    GenerateResponse,
    ProviderStreamEvent,
    StreamCompleted,
    StreamTextDelta,
)
from app.services.gateway import GatewayService

router = APIRouter()


def get_gateway_service(request: Request) -> GatewayService:
    """Retrieve the process-scoped gateway assembled during application startup."""

    return cast(GatewayService, request.app.state.container.gateway_service)


def get_routing_analytics_service(request: Request) -> RoutingAnalyticsService:
    service = request.app.state.container.routing_analytics_service
    if service is None:
        raise RuntimeError("Routing analytics service is not configured")
    return cast(RoutingAnalyticsService, service)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    registry = request.app.state.container.metrics_registry
    return Response(
        content=generate_latest(registry),
        media_type=CONTENT_TYPE_LATEST,
    )


@router.get("/analytics/routing-summary", response_model=RoutingSummary)
async def routing_summary(
    analytics_service: Annotated[
        RoutingAnalyticsService, Depends(get_routing_analytics_service)
    ],
    start_time: Annotated[datetime | None, Query()] = None,
    end_time: Annotated[datetime | None, Query()] = None,
) -> RoutingSummary:
    try:
        return await analytics_service.get_routing_summary(
            start_time=start_time,
            end_time=end_time,
        )
    except InvalidAnalyticsTimeRangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "analytics_unavailable",
                "message": "Routing analytics are unavailable",
            },
        ) from exc


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    request: GenerateRequest,
    gateway_service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> GenerateResponse:
    request_id = str(uuid4())
    try:
        return await gateway_service.generate(request=request, request_id=request_id)
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error": "model_not_found",
                "requested_model": exc.model_name,
            },
        ) from exc
    except ProviderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_routing_error",
                "message": "An internal routing error occurred",
            },
        ) from exc
    except InvalidModelError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_model",
                "requested_model": exc.requested_model,
                "valid_models": exc.valid_models,
            },
        ) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "provider_error",
                "message": "Upstream provider failed",
            },
        ) from exc


@router.post("/generate/stream")
async def generate_stream(
    request: GenerateRequest,
    gateway_service: Annotated[GatewayService, Depends(get_gateway_service)],
) -> StreamingResponse:
    """Prime execution before headers, then expose AegisRoute-owned SSE events."""

    request_id = str(uuid4())
    stream = gateway_service.stream(request=request, request_id=request_id)
    try:
        first_event = await anext(stream)
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "model_not_found", "requested_model": exc.model_name},
        ) from exc
    except ProviderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_routing_error",
                "message": "An internal routing error occurred",
            },
        ) from exc
    except InvalidModelError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_model",
                "requested_model": exc.requested_model,
                "valid_models": exc.valid_models,
            },
        ) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "provider_error", "message": "Upstream provider failed"},
        ) from exc
    except StopAsyncIteration as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "provider_error", "message": "Upstream stream ended"},
        ) from exc

    async def body() -> AsyncIterator[str]:
        event = first_event
        try:
            while True:
                yield _encode_sse_event(event, request_id)
                if isinstance(event, StreamCompleted):
                    return
                try:
                    event = await anext(stream)
                except StopAsyncIteration:
                    return
                except ProviderError as exc:
                    yield _encode_sse_error(_public_stream_error(exc))
                    return
                except Exception:  # noqa: BLE001 -- post-commit wire error is bounded
                    yield _encode_sse_error("internal_error")
                    return
        finally:
            await stream.aclose()

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _encode_sse_event(event: ProviderStreamEvent, request_id: str) -> str:
    if isinstance(event, StreamTextDelta):
        name = "delta"
        data: dict[str, object] = {"text": event.text}
    else:
        name = "completed"
        data = {
            "request_id": request_id,
            "model": event.model,
            "input_tokens": (
                event.usage.input_tokens if event.usage is not None else None
            ),
            "output_tokens": (
                event.usage.output_tokens if event.usage is not None else None
            ),
        }
    return f"event: {name}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def _encode_sse_error(error_type: str) -> str:
    data = {"error_type": error_type, "stage": "post_commit"}
    return f"event: error\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def _public_stream_error(error: ProviderError) -> str:
    if isinstance(error, ProviderAuthenticationError):
        return "provider_authentication"
    if isinstance(error, ProviderInvalidRequestError):
        return "provider_invalid_request"
    name = type(error).__name__
    return {
        "ProviderTimeoutError": "provider_timeout",
        "ProviderRateLimitError": "provider_rate_limit",
        "ProviderUnavailableError": "provider_unavailable",
        "ProviderInternalError": "provider_internal",
    }.get(name, "provider_error")
