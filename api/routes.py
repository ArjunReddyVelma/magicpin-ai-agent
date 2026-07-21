from fastapi import APIRouter

from api.schemas import ContextRequest
from services.context_manager import ContextManager

router = APIRouter()

context_manager = ContextManager()


@router.post("/v1/context")
def save_context(request: ContextRequest):

    context_manager.update_context(
        request.merchant_id,
        request.context
    )

    return {
        "status": "success",
        "merchant_id": request.merchant_id
    }