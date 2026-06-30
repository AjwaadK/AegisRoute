from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from app.errors import InvalidModelError, ProviderError
from app.schemas.generation import GenerateRequest, GenerateResponse
from app.services.gateway import GatewayService

router = APIRouter()
gateway_service = GatewayService()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    request_id = str(uuid4())
    try:
        return await gateway_service.generate(request=request, request_id=request_id)
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
            detail={"error": "provider_error"},
                    "message": "Upstream provider failed"},
        ) from exc
