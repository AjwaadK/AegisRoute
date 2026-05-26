from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter

from app.core.logging import log_event
from app.providers.mock import MockProviderAdapter
from app.schemas.generation import GenerateRequest, GenerateResponse

router = APIRouter()
provider_adapter = MockProviderAdapter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    request_id = str(uuid4())
    log_event(
        "generation_started",
        request_id=request_id,
        provider=provider_adapter.provider_name,
        model=request.model,
        status="started",
    )
    start = perf_counter()
    response = await provider_adapter.generate(request=request, request_id=request_id)
    latency_ms = int((perf_counter() - start) * 1000)
    normalized_response = response.model_copy(update={"latency_ms": latency_ms})
    log_event(
        "generation_completed",
        request_id=request_id,
        provider=normalized_response.provider,
        model=normalized_response.model,
        status="completed",
        latency_ms=latency_ms,
    )
    return normalized_response
